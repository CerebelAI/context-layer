"""Locks the shapes the Notion API actually returns, against captured responses.

Everything under `tests/fixtures/notion/` is a real response from the live API,
recorded while exploring a seeded workspace. Result objects are copied verbatim;
the only edit is that most of them were dropped, so a person can read the diff.
The `has_more` / `next_cursor` envelopes are untouched, so page N still names the
cursor that fetches page N+1 and the pagination loop is exercised for real.

What the kept records cover:

    search/live.1-3.json    three pages of one `POST /search`, holding a prose page
                            under the workspace root, one under a page, a data
                            source, a 27-property database row, and every hostile
                            title the workspace has -- empty, whitespace-only, RTL,
                            emoji with zero-width joiners, embedded newline and tab,
                            and 250 characters
    search/trashed.1.json   `POST /search` with `filter: {"in_trash": true}`, the
                            only place a deleted record still shows up
    blocks/<id>.<n>.json    one `GET /blocks/{id}/children` response each: the root
                            page's `child_page` blocks, a page whose whole body is
                            `child_database` blocks, five toggles nested one inside
                            the next, and a two-page paginated body

Requests are served by `httpx.MockTransport`, so the connector builds its real
requests and nothing reaches the network. A request we have no capture for is an
error, which is what makes "does not walk X" assertable at all.
"""

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from connectors import Envelope, NotionError, notion_client, pull_notion

FIXTURES = Path(__file__).parent / "fixtures" / "notion"

# The connector's own base URL, repeated rather than imported: a test that took it
# from the module could not notice the module changing it.
BASE_URL = "https://api.notion.com/v1"

ROOT_PAGE = "3b31b933-7ce1-8022-a980-c809dc38e066"
OPERATIONS_PAGE = "3b31b933-7ce1-81c9-8367-d52b24fca739"
TOGGLE_PAGE = "3b31b933-7ce1-81f8-9fcc-e86c358b94eb"
PARAGRAPHS_PAGE = "3b31b933-7ce1-8138-a2e9-dbd9a45063a0"
EMPTY_TITLE_PAGE = "3b31b933-7ce1-8190-a200-e3a320a7dbda"
WHITESPACE_TITLE_PAGE = "3b31b933-7ce1-81dc-a3c5-ed8374b3ab7d"
RTL_TITLE_PAGE = "3b31b933-7ce1-8154-acba-d08f854c05bc"
EMOJI_TITLE_PAGE = "3b31b933-7ce1-8131-9720-ddb802c65f18"
CONTROL_TITLE_PAGE = "3b31b933-7ce1-81fe-b9af-e5029306b60d"
LONG_TITLE_PAGE = "3b31b933-7ce1-81f6-8555-dceb2860d46c"

# Rows of the Projects and Teams data sources. The first has 27 properties and an
# empty title; the second holds its title under "Name", not "title".
WIDE_ROW = "3b31b933-7ce1-81e1-8c9e-c0d1229c16b5"
TEAM_ROW = "3b31b933-7ce1-8113-9f3c-df90771e155e"
TEAMS_DATA_SOURCE = "8cc0d8ee-8a09-4795-8405-e910c0c61500"

# `child_page` blocks in the root page's body; each is also its own search result.
ROOT_SUBPAGES = (
    OPERATIONS_PAGE,
    "3b31b933-7ce1-81dc-bc9f-d6a410063224",
    "3b31b933-7ce1-8193-9a1c-f4b6c895ee6f",
)
# `child_database` blocks in the Operations page's body.
OPERATIONS_DATABASES = (
    "c9bab47e-6e6c-42d1-830c-ea2aedf45674",
    "1b700695-fad0-41fc-986d-21481476a0a5",
    "41b3437d-9718-4436-8870-61f18ed2eefb",
)

TRASHED = (
    "3b31b933-7ce1-811a-a351-d06cf6d314b8",
    "3b31b933-7ce1-81f0-8204-fe0a7b45ed0f",
    "3b31b933-7ce1-8122-a89b-d7ce16e46386",
    "3b31b933-7ce1-81c3-ad0a-f4801ec92164",
)

LIVE = (
    ROOT_PAGE,
    OPERATIONS_PAGE,
    TOGGLE_PAGE,
    PARAGRAPHS_PAGE,
    EMPTY_TITLE_PAGE,
    WHITESPACE_TITLE_PAGE,
    RTL_TITLE_PAGE,
    EMOJI_TITLE_PAGE,
    CONTROL_TITLE_PAGE,
    LONG_TITLE_PAGE,
    WIDE_ROW,
    TEAM_ROW,
    TEAMS_DATA_SOURCE,
)

CHILDREN_PATH = re.compile(r"^/v1/blocks/([0-9a-f-]+)/children$")

Response = dict[str, Any]


def _read(*parts: str) -> Response:
    payload: Response = json.loads(
        FIXTURES.joinpath(*parts).read_text(encoding="utf-8")
    )
    return payload


def _captured_search(prefix: str) -> list[Response]:
    return [
        _read("search", path.name)
        for path in sorted((FIXTURES / "search").glob(f"{prefix}.*.json"))
    ]


def _captured_blocks() -> dict[str, list[Response]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in (FIXTURES / "blocks").glob("*.json"):
        grouped[path.name.partition(".")[0]].append(path)
    return {
        block_id: [_read("blocks", path.name) for path in sorted(paths)]
        for block_id, paths in grouped.items()
    }


def _by_cursor(responses: Sequence[Response]) -> dict[str | None, Response]:
    """Index responses by the cursor that asks for them; the first has none."""
    chain: dict[str | None, Response] = {}
    cursor: str | None = None
    for response in responses:
        chain[cursor] = response
        cursor = response["next_cursor"]
    return chain


class Notion:
    """The captured workspace, served over `httpx.MockTransport`.

    `stall` responses are handed out before any captured one, which is how a 429
    or a 400 gets in front of a request that would otherwise succeed.
    """

    def __init__(
        self,
        *,
        live: Sequence[Response] | None = None,
        trashed: Sequence[Response] | None = None,
        blocks: dict[str, list[Response]] | None = None,
        stall: Sequence[httpx.Response] = (),
        gone: Sequence[str] = (),
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.stall = list(stall)
        self.gone = set(gone)
        self.live = _by_cursor(live if live is not None else _captured_search("live"))
        self.trashed = _by_cursor(
            trashed if trashed is not None else _captured_search("trashed")
        )
        self.blocks = {**_captured_blocks(), **(blocks or {})}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.stall:
            return self.stall.pop(0)
        if request.url.path == "/v1/search":
            body = json.loads(request.content)
            chain = self.trashed if body.get("filter") else self.live
            return self._serve(chain, body.get("start_cursor"), request)
        children = CHILDREN_PATH.match(request.url.path)
        if children is None:
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        block_id = children.group(1)
        if block_id in self.gone:
            return httpx.Response(
                404,
                json={
                    "object": "error",
                    "status": 404,
                    "code": "object_not_found",
                    "message": "Could not find block.",
                },
            )
        if block_id not in self.blocks:
            raise AssertionError(
                f"asked for children of {block_id}, which was never captured"
            )
        return self._serve(
            _by_cursor(self.blocks[block_id]),
            request.url.params.get("start_cursor"),
            request,
        )

    def _serve(
        self,
        chain: dict[str | None, Response],
        cursor: str | None,
        request: httpx.Request,
    ) -> httpx.Response:
        if cursor not in chain:
            raise AssertionError(
                f"no captured response for cursor {cursor!r} on {request.url}"
            )
        return httpx.Response(200, json=chain[cursor])

    def searches(self) -> list[Response]:
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path == "/v1/search"
        ]

    def walked(self) -> list[str]:
        return [
            match.group(1)
            for request in self.requests
            if (match := CHILDREN_PATH.match(request.url.path))
        ]


def pull(notion: Notion, sleeps: list[float] | None = None) -> list[Envelope]:
    async def run() -> list[Envelope]:
        async def record(seconds: float) -> None:
            (sleeps if sleeps is not None else []).append(seconds)

        transport = httpx.MockTransport(notion)
        async with httpx.AsyncClient(base_url=BASE_URL, transport=transport) as client:
            return await pull_notion(client, sleep=record)

    return asyncio.run(run())


def by_id(envelopes: Sequence[Envelope]) -> dict[str, Envelope]:
    return {envelope.source_id: envelope for envelope in envelopes}


def test_client_carries_the_credential_and_the_pinned_api_version() -> None:
    client = notion_client("secret-token")

    assert str(client.base_url) == f"{BASE_URL}/"  # httpx normalises the trailing slash
    assert client.headers["Authorization"] == "Bearer secret-token"
    # A connector written against one version of the API is only correct against
    # that version; letting Notion pick would silently reshape every response.
    assert client.headers["Notion-Version"] == "2026-03-11"


def test_every_search_result_becomes_an_envelope() -> None:
    envelopes = pull(Notion())

    assert set(by_id(envelopes)) == set(LIVE) | set(TRASHED)
    assert len(envelopes) == len(LIVE) + len(TRASHED)
    assert {envelope.upsert_key for envelope in envelopes} == {
        ("notion", source_id) for source_id in set(LIVE) | set(TRASHED)
    }
    # Notion hands over a URL for every record, so none has to be constructed.
    assert all(
        envelope.url == _one_result(envelope.source_id)["url"] for envelope in envelopes
    )


def test_search_follows_the_cursor_to_the_last_page() -> None:
    notion = Notion()

    pull(notion)

    live = [body for body in notion.searches() if "filter" not in body]
    assert len(live) == 3
    assert live[0] == {"page_size": 100}
    assert live[1] == {
        "page_size": 100,
        "start_cursor": "3b31b933-7ce1-8184-8316-ec22079f7ee1",
    }
    assert live[2] == {
        "page_size": 100,
        "start_cursor": "3b31b933-7ce1-81d7-b66c-d71a7760b69d",
    }


def test_a_null_next_cursor_ends_the_loop_rather_than_a_missing_key() -> None:
    # The real shape of an exhausted listing: the key is there, holding null. A
    # loop testing for the key rather than for its value never terminates, so the
    # shape is asserted and then the loop is actually made to stop on it.
    last = _captured_search("live")[-1]
    assert last["has_more"] is False
    assert "next_cursor" in last
    assert last["next_cursor"] is None

    notion = Notion(live=[last])
    pull(notion)

    assert len(notion.searches()) == 2  # the live pass, then the trash sweep


def test_more_results_without_a_cursor_is_an_error_not_a_silent_stop() -> None:
    first, *_ = _captured_search("live")
    lying = {**first, "has_more": True, "next_cursor": None}

    with pytest.raises(NotionError, match="cursor"):
        pull(Notion(live=[lying]))


@pytest.mark.parametrize(
    ("source_id", "expected"),
    [
        (ROOT_PAGE, "Northwind Robotics"),
        (TEAMS_DATA_SOURCE, "Teams"),
        # A row's title sits under whatever the schema named that column.
        (TEAM_ROW, "Design"),
        (WHITESPACE_TITLE_PAGE, "   "),
        (CONTROL_TITLE_PAGE, "Line one\nLine two\tTabbed end"),
        (RTL_TITLE_PAGE, "مرحبا بالعالم"),
        (EMOJI_TITLE_PAGE, "🎉👨‍👩‍👧‍👦🇩🇪🚀"),
        (LONG_TITLE_PAGE, "Long-" + "x" * 245),
    ],
)
def test_titles_survive_verbatim(source_id: str, expected: str) -> None:
    # Notion stores a title byte for byte, so trimming or normalising here would
    # make the stored record disagree with the page a person opens.
    assert by_id(pull(Notion()))[source_id].title == expected


@pytest.mark.parametrize("source_id", [EMPTY_TITLE_PAGE, WIDE_ROW])
def test_an_absent_title_is_none_not_an_empty_string(source_id: str) -> None:
    assert by_id(pull(Notion()))[source_id].title is None


@pytest.mark.parametrize(
    ("parent", "expected"),
    [
        # Four of these are lifted from captured responses. `block_id` appears on
        # Every one of these is lifted from a captured response. Notion documents
        # `block_id` and `agent_id` too, but no page in this workspace has either,
        # so there is nothing here to lock: a row asserting the documented shape
        # would be a dict written to satisfy the rule it claims to be testing.
        # What happens to a shape we have not seen is a question of its own, and
        # `test_a_parent_that_does_not_name_its_id_is_an_error` is where it lives.
        ({"type": "workspace", "workspace": True}, None),
        ({"type": "page_id", "page_id": ROOT_PAGE}, ROOT_PAGE),
        ({"type": "database_id", "database_id": "c9bab47e-6e6c"}, "c9bab47e-6e6c"),
        (
            {
                "type": "data_source_id",
                "data_source_id": TEAMS_DATA_SOURCE,
                "database_id": "c9bab47e-6e6c",
            },
            TEAMS_DATA_SOURCE,
        ),
    ],
)
def test_parent_id_is_read_from_the_field_the_type_names(
    parent: dict[str, Any], expected: str | None
) -> None:
    envelopes = pull(_carrying_parent(parent))

    assert by_id(envelopes)[WHITESPACE_TITLE_PAGE].parent_id == expected


def _carrying_parent(parent: dict[str, Any]) -> Notion:
    # Carried on a page whose captured body is empty, so that a parent which makes
    # it a prose page is walked against a real response rather than nothing.
    first = _captured_search("live")[0]
    lone = {
        **first,
        "results": [{**_one_result(WHITESPACE_TITLE_PAGE), "parent": parent}],
        "has_more": False,
        "next_cursor": None,
    }
    return Notion(live=[lone])


@pytest.mark.parametrize(
    "parent",
    [
        # The shape the id field is named after the type does not survive: a type
        # we have never seen, and a known type that carries no id at all.
        {"type": "sector_id", "id": "3b31b933-7ce1-81e2"},
        {"type": "page_id"},
    ],
)
def test_a_parent_that_does_not_name_its_id_is_an_error(parent: dict[str, Any]) -> None:
    # Reading `parent[parent["type"]]` off a shape that does not hold makes a
    # KeyError, and a connector that documents NotionError has told a lie.
    with pytest.raises(NotionError, match="parent"):
        pull(_carrying_parent(parent))


def test_a_success_that_is_not_json_is_an_error() -> None:
    # A 200 is not a promise of JSON. A gateway or a captive portal answers one
    # with HTML, and `response.json()` raises something no caller is expecting.
    notion = Notion(stall=[httpx.Response(200, text="<html>gateway</html>")])

    with pytest.raises(NotionError, match="not JSON"):
        pull(notion)


def test_block_nesting_without_end_is_an_error_not_a_crash() -> None:
    # A synced block's children come back under the id of the block it mirrors, so
    # a page mirroring one of its own ancestors is a cycle the walk cannot see from
    # inside it. Recursing until Python runs out of stack is not how we find out.
    loop = {
        "results": [{"id": TOGGLE_PAGE, "type": "toggle", "has_children": True}],
        "has_more": False,
        "next_cursor": None,
    }

    with pytest.raises(NotionError, match="nested deeper"):
        pull(Notion(blocks={TOGGLE_PAGE: [loop]}))


def test_timestamps_arrive_as_aware_utc() -> None:
    envelope = by_id(pull(Notion()))[ROOT_PAGE]

    assert envelope.created_at.utcoffset() is not None
    assert envelope.last_modified.utcoffset() is not None
    assert envelope.created_at.isoformat() == "2026-08-05T18:12:00+00:00"


def test_the_trash_sweep_is_a_second_unfiltered_pass() -> None:
    notion = Notion()

    pull(notion)

    sweeps = [body for body in notion.searches() if "filter" in body]
    assert len(sweeps) == 1
    assert sweeps[0] == {"page_size": 100, "filter": {"in_trash": True}}
    # The filter does not reliably apply a `query`, so the sweep must not send one.
    assert "query" not in sweeps[0]


def test_only_the_trashed_records_are_marked_deleted() -> None:
    envelopes = by_id(pull(Notion()))

    assert {source_id for source_id, e in envelopes.items() if e.is_deleted} == set(
        TRASHED
    )
    # `is_archived` is false on every trashed record here, so it cannot be the signal.
    assert all(e.data.get("is_archived") is not True for e in envelopes.values())


def test_a_trashed_record_keeps_its_identity() -> None:
    envelope = by_id(pull(Notion()))[TRASHED[0]]

    assert envelope.title == "ZEdgeDelete TrashedOnly"
    assert envelope.url.startswith("https://")
    assert envelope.parent_id is not None
    # Pulled for its identity, not its body: nothing walks a record already gone.
    assert "blocks" not in envelope.data


def test_a_record_trashed_between_the_passes_is_one_envelope_not_two() -> None:
    # Both passes return it, and two envelopes sharing an upsert key make the
    # stored answer depend on which order `knowledge` happens to apply them in.
    victim = _one_result(OPERATIONS_PAGE)
    first = _captured_search("live")[0]
    both = Notion(
        live=[{**first, "results": [victim], "has_more": False, "next_cursor": None}],
        trashed=[
            {
                **first,
                "results": [{**victim, "in_trash": True}],
                "has_more": False,
                "next_cursor": None,
            }
        ],
    )

    envelopes = pull(both)

    assert len(envelopes) == 1
    # The trashed look is the later one and the only one that says it is gone, so
    # it wins -- but it keeps the body, which only the pass that walked it has.
    assert envelopes[0].is_deleted is True
    assert (
        envelopes[0].data["blocks"]
        == _read("blocks", f"{OPERATIONS_PAGE}.1.json")["results"]
    )


def test_a_prose_page_carries_its_block_tree() -> None:
    envelope = by_id(pull(Notion()))[OPERATIONS_PAGE]
    captured = _read("blocks", f"{OPERATIONS_PAGE}.1.json")["results"]

    # The search payload verbatim, with the body it did not carry beside it and
    # nothing else invented.
    assert envelope.data == {**_one_result(OPERATIONS_PAGE), "blocks": captured}


def test_a_result_already_using_our_blocks_key_is_an_error_not_an_overwrite() -> None:
    # `blocks` and `children` are the connector's, added to a namespace that is
    # Notion's. Were Notion to start sending either, the merge would quietly win
    # and nothing downstream could tell the platform's value from ours.
    first = _captured_search("live")[0]
    squatting = {
        **first,
        "results": [{**_one_result(OPERATIONS_PAGE), "blocks": "Notion's own"}],
        "has_more": False,
        "next_cursor": None,
    }

    with pytest.raises(NotionError, match="blocks"):
        pull(Notion(live=[squatting]))


def test_a_block_already_using_our_children_key_is_an_error_not_an_overwrite() -> None:
    captured = _read("blocks", f"{TOGGLE_PAGE}.1.json")
    squatting = {
        **captured,
        "results": [
            {**block, "children": "Notion's own"} for block in captured["results"]
        ],
    }

    with pytest.raises(NotionError, match="children"):
        pull(Notion(blocks={TOGGLE_PAGE: [squatting]}))


def test_nested_blocks_are_walked_to_the_leaf() -> None:
    envelope = by_id(pull(Notion()))[TOGGLE_PAGE]

    block = envelope.data["blocks"][0]
    for level in range(1, 6):
        assert block["type"] == "toggle"
        assert (
            block["toggle"]["rich_text"][0]["plain_text"]
            == f"Toggle level {level} of 5"
        )
        block = block["children"][0]
    assert block["type"] == "paragraph"
    assert block["has_children"] is False
    assert "children" not in block


def test_a_paginated_block_body_is_collected_in_full() -> None:
    notion = Notion()

    envelope = by_id(pull(notion))[PARAGRAPHS_PAGE]

    first, second = (_read("blocks", f"{PARAGRAPHS_PAGE}.{n}.json") for n in (1, 2))
    assert envelope.data["blocks"] == first["results"] + second["results"]
    cursors = [
        request.url.params.get("start_cursor")
        for request in notion.requests
        if request.url.path == f"/v1/blocks/{PARAGRAPHS_PAGE}/children"
    ]
    assert cursors == [None, first["next_cursor"]]


def test_a_page_trashed_during_its_walk_keeps_the_rest_of_the_pull() -> None:
    # Minutes separate the search from the last block request. Someone trashing a
    # page inside that window used to throw away every envelope already built,
    # which is a far worse answer than the one page's missing body.
    notion = Notion(gone=[OPERATIONS_PAGE])

    envelopes = by_id(pull(notion))

    assert len(envelopes) == len(LIVE) + len(TRASHED)
    assert envelopes[OPERATIONS_PAGE].title == "Operations"
    assert "blocks" not in envelopes[OPERATIONS_PAGE].data


def test_a_block_walk_failing_for_any_other_reason_still_stops_the_pull() -> None:
    # Only the record going away is survivable. A 401 means the whole pull is
    # unauthorised and every envelope in it is suspect.
    notion = Notion(stall=[httpx.Response(401, json={"object": "error"})])

    with pytest.raises(NotionError, match="401"):
        pull(notion)


def test_a_database_row_is_not_walked_for_blocks() -> None:
    notion = Notion()

    envelopes = by_id(pull(notion))

    assert WIDE_ROW not in notion.walked()
    assert TEAM_ROW not in notion.walked()
    # Its content is the properties the search already returned, so nothing is added.
    assert envelopes[WIDE_ROW].data == _one_result(WIDE_ROW)
    assert len(envelopes[WIDE_ROW].data["properties"]) == 27


def test_a_data_source_is_not_walked_for_blocks() -> None:
    notion = Notion()

    envelopes = by_id(pull(notion))

    assert TEAMS_DATA_SOURCE not in notion.walked()
    assert envelopes[TEAMS_DATA_SOURCE].data == _one_result(TEAMS_DATA_SOURCE)


def test_a_child_page_block_is_left_to_its_own_envelope() -> None:
    notion = Notion()

    envelopes = by_id(pull(notion))

    # The root's body names three subpages, each of which search returns in its own
    # right; descending here would store every subpage twice, once inside each of
    # its ancestors. Every one of them claims `has_children`, so only the type keeps
    # us out.
    blocks = envelopes[ROOT_PAGE].data["blocks"]
    assert [block["id"] for block in blocks[1:]] == list(ROOT_SUBPAGES)
    assert all(block["has_children"] for block in blocks[1:])
    assert all("children" not in block for block in blocks)
    # Operations is walked because it is a search result, not because it is a block,
    # and walked exactly once. The other two are in neither list.
    assert OPERATIONS_PAGE in envelopes
    assert notion.walked().count(OPERATIONS_PAGE) == 1
    assert all(subpage not in notion.walked() for subpage in ROOT_SUBPAGES[1:])


def test_a_child_database_block_is_not_walked() -> None:
    notion = Notion()

    pull(notion)

    assert all(database not in notion.walked() for database in OPERATIONS_DATABASES)


def test_a_child_database_is_skipped_even_when_it_claims_children() -> None:
    # Every captured `child_database` reports `has_children: false` while holding
    # rows, so the type guard is what keeps us out -- and stays untested unless the
    # flag is flipped by hand, which the live API never does.
    captured = _read("blocks", f"{OPERATIONS_PAGE}.1.json")
    claiming = {
        **captured,
        "results": [{**block, "has_children": True} for block in captured["results"]],
    }
    notion = Notion(blocks={OPERATIONS_PAGE: [claiming]})

    pull(notion)

    assert all(database not in notion.walked() for database in OPERATIONS_DATABASES)


@pytest.mark.parametrize("status", [429, 529])
def test_a_throttled_request_waits_the_advertised_delay_and_retries(
    status: int,
) -> None:
    notion = Notion(stall=[httpx.Response(status, headers={"Retry-After": "7"})])
    sleeps: list[float] = []

    envelopes = pull(notion, sleeps)

    assert sleeps == [7.0]
    assert len(envelopes) == len(LIVE) + len(TRASHED)


def test_a_throttled_request_without_a_delay_still_waits() -> None:
    notion = Notion(stall=[httpx.Response(429)])
    sleeps: list[float] = []

    pull(notion, sleeps)

    assert sleeps == [1.0]


def _throttled_by(header: str) -> list[float]:
    notion = Notion(stall=[httpx.Response(429, headers={"Retry-After": header})])
    sleeps: list[float] = []
    pull(notion, sleeps)
    return sleeps


def test_a_retry_after_date_already_past_waits_no_time() -> None:
    # RFC 9110 allows an HTTP-date here as well as a count of seconds, and Notion
    # is not the only thing that can answer 429 -- a proxy in front of it is
    # entitled to send one.
    assert _throttled_by("Wed, 21 Oct 2015 07:28:00 GMT") == [0.0]


def test_a_retry_after_date_is_honoured_as_the_wait_until_then() -> None:
    when = datetime.now(UTC) + timedelta(seconds=30)

    waited = _throttled_by(format_datetime(when, usegmt=True))

    assert 25.0 <= waited[0] <= 30.0


def test_a_retry_after_beyond_all_reason_is_capped_not_honoured() -> None:
    when = datetime.now(UTC) + timedelta(days=365)

    assert _throttled_by(format_datetime(when, usegmt=True)) == [60.0]
    assert _throttled_by("999999") == [60.0]


@pytest.mark.parametrize("header", ["inf", "nan", "-5", "soon", "7 seconds", "7.5"])
def test_a_retry_after_we_cannot_read_falls_back_rather_than_crashing(
    header: str,
) -> None:
    # `inf` is the dangerous one: honoured literally it hangs the pull instead of
    # ending it, which is worse than the crash the others would cause. RFC 9110
    # spells the seconds form as digits only, so a float or a sign is malformed.
    assert _throttled_by(header) == [1.0]


def test_retrying_is_bounded_and_ends_in_an_error() -> None:
    forever = [httpx.Response(429, headers={"Retry-After": "0"}) for _ in range(50)]
    notion = Notion(stall=forever)
    sleeps: list[float] = []

    with pytest.raises(NotionError, match="rate limited"):
        pull(notion, sleeps)

    assert len(notion.requests) == 5
    # One wait between each pair of attempts and none after the last. Sitting out
    # a delay we have already decided not to act on is time spent on nothing --
    # seven seconds of it, at the delay Notion actually advertises.
    assert len(sleeps) == 4


def test_an_error_response_fails_loudly_with_the_status_and_the_body() -> None:
    body = {
        "object": "error",
        "status": 400,
        "code": "validation_error",
        "message": "bad cursor",
    }
    notion = Notion(stall=[httpx.Response(400, json=body)])

    with pytest.raises(NotionError) as raised:
        pull(notion)

    assert "400" in str(raised.value)
    assert "validation_error" in str(raised.value)


def test_an_unrecognised_object_is_an_error_not_a_titleless_envelope() -> None:
    # Search returns pages and data sources today. Anything else has a title we have
    # not learned to read, and guessing `None` would store a record with no name.
    page = _captured_search("live")[0]
    surprise = {**page["results"][0], "object": "comment"}
    lone = {**page, "results": [surprise], "has_more": False, "next_cursor": None}

    with pytest.raises(NotionError, match="comment"):
        pull(Notion(live=[lone]))


def test_a_pages_body_becomes_its_text_in_document_order() -> None:
    # `text` is what gets embedded, so the order it comes out in is the order a
    # reader would meet the words, not whatever order the blocks were fetched in.
    envelopes = by_id(pull(Notion()))

    assert envelopes[PARAGRAPHS_PAGE].text == (
        "Paragraph 1 of 160\n"
        "Paragraph 2 of 160\n"
        "Paragraph 3 of 160\n"
        "Paragraph 101 of 160\n"
        "Paragraph 102 of 160\n"
        "Paragraph 103 of 160"
    )


def test_text_reaches_the_words_inside_nested_blocks() -> None:
    # A toggle keeps its body one level down, so text that stopped at the top
    # level would drop every word a person had to click to see.
    envelopes = by_id(pull(Notion()))

    text = envelopes[TOGGLE_PAGE].text
    assert text is not None
    assert text.startswith("Toggle level 1 of 5")
    assert "Toggle level 5 of 5" in text


def test_a_body_holding_no_words_is_no_text_rather_than_an_empty_string() -> None:
    # This page's whole body is `child_database` blocks -- containers naming other
    # records, carrying no prose of their own.
    envelopes = by_id(pull(Notion()))

    assert envelopes[OPERATIONS_PAGE].data["blocks"], "the page was walked"
    assert envelopes[OPERATIONS_PAGE].text is None


@pytest.mark.parametrize("source_id", [WIDE_ROW, TEAMS_DATA_SOURCE])
def test_a_record_that_is_never_walked_has_no_text(source_id: str) -> None:
    envelopes = by_id(pull(Notion()))

    assert envelopes[source_id].text is None


def test_text_does_not_disturb_the_payload_it_was_read_from() -> None:
    # `text` is a second view of the body, not a replacement for it: `data` still
    # has to survive verbatim so extraction can go back for a detail `text` drops.
    envelopes = by_id(pull(Notion()))
    envelope = envelopes[PARAGRAPHS_PAGE]

    blocks = envelope.data["blocks"]
    assert [block["type"] for block in blocks] == ["paragraph"] * 6
    assert blocks[0]["paragraph"]["rich_text"][0]["plain_text"] == "Paragraph 1 of 160"


def _one_result(source_id: str) -> Response:
    for response in _captured_search("live") + _captured_search("trashed"):
        for result in response["results"]:
            if result["id"] == source_id:
                found: Response = result
                return found
    raise AssertionError(f"{source_id} is not in the captured search responses")
