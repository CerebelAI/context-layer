import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from email.utils import mktime_tz, parsedate_tz
from typing import Any

import httpx

from connectors import Envelope

API_BASE = "https://api.notion.com/v1"
# Pinned deliberately. Notion reshapes responses between versions -- what a data
# source is, where a row's parent points -- so the version this connector was
# written and captured against is the one it keeps asking for.
API_VERSION = "2026-03-11"
# The maximum Notion accepts, and the fewest round trips at ~3 requests a second.
PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 30.0
RETRYABLE_STATUSES = frozenset({429, 529})
MAX_ATTEMPTS = 5
FALLBACK_RETRY_SECONDS = 1.0
MAX_RETRY_SECONDS = 60.0
# RFC 9110 spells the seconds form of `Retry-After` as digits and nothing else,
# so this rejects a sign, a decimal point, and the `inf` that `float` would take.
DELAY_SECONDS = re.compile(r"\d+")

# Blocks that name another record rather than holding content of their own. Both
# come back from `/search` as their own result -- a `child_page` as a page, a
# `child_database`'s rows as pages -- so descending into them here would copy every
# subpage and every row into each of its ancestors as well as storing it once.
RECORD_BOUNDARY_BLOCKS = frozenset({"child_page", "child_database"})

# Far past anything a person nests by hand -- the deepest page in the workspace is
# five toggles -- and far short of the stack. It is a bound, not a budget.
MAX_BLOCK_DEPTH = 50

Sleep = Callable[[float], Awaitable[None]]

Json = dict[str, Any]


class NotionError(Exception):
    """Notion answered with something this connector cannot honestly read."""


class _RecordGone(NotionError):
    # A 404. Separate from its parent only so that a block walk can tell the record
    # being deleted underneath it from every other reason a request fails.
    pass


def notion_client(api_key: str) -> httpx.AsyncClient:
    """An HTTP client aimed at the Notion API, carrying the credential and API version.

    Built here rather than in the caller so that nothing above `connectors` has to
    know Notion's base URL, its header names or which version we are pinned to.
    The client is the caller's to own and close -- `async with` it -- and it is what
    `pull_notion` takes, so a test can hand in one that never leaves the process.
    """
    return httpx.AsyncClient(
        base_url=API_BASE,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": API_VERSION,
            "Content-Type": "application/json",
        },
        # A full page of 100 records is regularly slower than httpx's 5s default.
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


async def pull_notion(
    client: httpx.AsyncClient, *, sleep: Sleep = asyncio.sleep
) -> list[Envelope]:
    """Pull every record in the workspace the token can see, as `Envelope`s.

    Enumeration is `POST /search`, which returns every page -- prose pages and
    database rows alike -- plus every data source, with the rows' properties
    already filled in. It is a strict superset of walking the page tree, which
    misses every row, so the tree is never walked for enumeration.

    A prose page's body is not in that response, so its block tree is fetched and
    recursed into. It lands under `data["blocks"]`, and a block holding a block
    carries them under its own `"children"`. Those two keys are the only things
    this connector adds to `data`; everything else there is Notion's own, and a
    payload already carrying either key is an error rather than an overwrite.

    The same body, with Notion's structure taken off, is what `text` carries: the
    `plain_text` of every run, one block to a line, nested blocks included. `data`
    keeps the version that can be re-read for a detail; `text` is the version that
    can be embedded. A record whose tree was never walked has `text=None`, which
    is why a data source has none and, for now, neither does a row.

    Database rows and data sources get no block walk: a data source is a schema
    whose rows are records in their own right, and a row is taken to be its
    properties, which search has already filled in.

    TODO: that last part is wrong for a real workspace, not merely incomplete. A
    row is a page, so it can carry a body of blocks underneath its properties,
    and skipping the walk drops every word of it. This is no longer hypothetical:
    "Prose Body In Row Check" in Projects carries eight blocks nested three deep
    and comes back with `text=None` and no `blocks` key, so words are being lost
    today. It was written into the workspace to be captured, because the other
    174 rows are empty and no fixture could otherwise show the case. Its
    `Summary` property is filled too, so a test can tell what search returns from
    what only a walk would. Fixing it means one request per row: 175 against this
    workspace, where the whole pull is currently about 90. See #5.

    Deleted records are invisible to an ordinary search, so a second pass runs with
    Notion's trash filter and the records it returns come back `is_deleted=True`.
    Nothing else reports a deletion, and a record that is gone on the platform but
    live in the store is a wrong answer nothing downstream can detect. Every record
    yields exactly one envelope even so, including one trashed between the passes
    and therefore returned by both, so no two envelopes share an `upsert_key`.

    Nothing is persisted here: the envelopes are returned to the caller, `main.py`,
    which hands them to `knowledge`.

    Takes an `httpx.AsyncClient` -- see `notion_client` -- and, so that a test does
    not have to spend the wait, the coroutine used to honour a `Retry-After`.

    Raises `NotionError` on any response this connector cannot read.
    """
    pulled: dict[str, tuple[Json, list[Json] | None]] = {
        result["id"]: (result, await _blocks_of(client, sleep, result))
        for result in await _search(client, sleep, in_trash=False)
    }
    # A trashed record is pulled for its identity, not its body: the store needs to
    # know the record is gone, and what it used to say is already stored. One
    # trashed between the two passes comes back from both, and two envelopes
    # sharing an upsert key would leave the stored answer to whichever order
    # `knowledge` applied them in. The trashed look is the later one and the only
    # one that says it is gone, so it wins -- keeping the body from the pass that
    # walked it, because no second search would return one.
    for result in await _search(client, sleep, in_trash=True):
        walked = pulled.get(result["id"])
        pulled[result["id"]] = (result, walked[1] if walked else None)
    return [_envelope(result, blocks) for result, blocks in pulled.values()]


async def _search(
    client: httpx.AsyncClient, sleep: Sleep, *, in_trash: bool
) -> list[Json]:
    results: list[Json] = []
    cursor: str | None = None
    while True:
        body: Json = {"page_size": PAGE_SIZE}
        if in_trash:
            body["filter"] = {"in_trash": True}
        if cursor is not None:
            body["start_cursor"] = cursor
        # No `query`: under the trash filter it is not reliably applied, and the
        # sweep has to see every trashed record rather than a plausible subset.
        payload = await _request(client, sleep, "POST", "/search", json=body)
        results.extend(payload["results"])
        cursor = _next_cursor(payload, "/search")
        if cursor is None:
            return results


async def _children(
    client: httpx.AsyncClient, sleep: Sleep, block_id: str
) -> list[Json]:
    path = f"/blocks/{block_id}/children"
    blocks: list[Json] = []
    cursor: str | None = None
    while True:
        params: Json = {"page_size": PAGE_SIZE}
        if cursor is not None:
            params["start_cursor"] = cursor
        payload = await _request(client, sleep, "GET", path, params=params)
        blocks.extend(payload["results"])
        cursor = _next_cursor(payload, path)
        if cursor is None:
            return blocks


def _next_cursor(payload: Json, path: str) -> str | None:
    if not payload["has_more"]:
        return None
    # `next_cursor` is on every response and holds null only on the last one, so a
    # loop that tests for the key rather than for its value never terminates.
    cursor = payload["next_cursor"]
    if not cursor:
        raise NotionError(f"{path} reported more results but handed back no cursor")
    return str(cursor)


async def _blocks_of(
    client: httpx.AsyncClient, sleep: Sleep, result: Json
) -> list[Json] | None:
    if result["object"] != "page" or result["parent"]["type"] == "data_source_id":
        return None
    try:
        return await _walk(client, sleep, result["id"])
    except _RecordGone:
        # Trashed since the search named it, minutes back. The envelope keeps the
        # identity search gave us and loses only the body, which is what the trash
        # sweep is about to report gone anyway.
        return None


async def _walk(
    client: httpx.AsyncClient, sleep: Sleep, block_id: str, depth: int = 0
) -> list[Json]:
    # A synced block's children come back under the id of the block it mirrors, so
    # a page mirroring one of its own ancestors is a cycle nothing in the response
    # marks as one. No page here does, and the depth is what says so out loud
    # rather than recursing until Python runs out of stack.
    if depth >= MAX_BLOCK_DEPTH:
        raise NotionError(
            f"block {block_id} is nested deeper than {MAX_BLOCK_DEPTH} levels"
        )
    tree: list[Json] = []
    for block in await _children(client, sleep, block_id):
        # A container never inlines its body, so every level costs its own request.
        # `has_children` is not the whole answer, though: a `child_database` reports
        # false while holding hundreds of rows, because its rows live in the data
        # source and not in the block tree at all.
        if block["has_children"] and block["type"] not in RECORD_BOUNDARY_BLOCKS:
            tree.append(
                _extended(
                    block,
                    "children",
                    await _walk(client, sleep, block["id"], depth + 1),
                )
            )
        else:
            tree.append(block)
    return tree


async def _request(
    client: httpx.AsyncClient,
    sleep: Sleep,
    method: str,
    path: str,
    *,
    json: Json | None = None,
    params: Json | None = None,
) -> Json:
    for attempt in range(MAX_ATTEMPTS):
        response = await client.request(method, path, json=json, params=params)
        if response.status_code in RETRYABLE_STATUSES:
            # Not after the last one. The delay buys a retry we are not going to
            # make, and Notion advertises seven seconds of it.
            if attempt + 1 < MAX_ATTEMPTS:
                await sleep(_retry_after(response))
            continue
        # Not `is_error`: that lets a 3xx through, and a redirect body is not the
        # JSON we are about to parse.
        if not response.is_success:
            failed = _RecordGone if response.status_code == 404 else NotionError
            raise failed(
                f"{method} {path} answered {response.status_code}: {response.text}"
            )
        # A 200 is not a promise of JSON: a gateway in front of Notion answers one
        # with HTML, and the decode error that follows names none of this request.
        try:
            payload: Json = response.json()
        except ValueError as undecodable:
            raise NotionError(
                f"{method} {path} answered {response.status_code} with a body that "
                f"is not JSON: {response.text[:200]}"
            ) from undecodable
        return payload
    raise NotionError(
        f"{method} {path} stayed rate limited across {MAX_ATTEMPTS} attempts"
    )


def _retry_after(response: httpx.Response) -> float:
    # Notion sends the wait in whole seconds on 429 and 529. Where it does not,
    # waiting a second beats hammering the endpoint that just asked us to stop.
    advertised = _advertised_wait(response.headers.get("Retry-After"))
    if advertised is None:
        return FALLBACK_RETRY_SECONDS
    # A wait we take literally can be worse than one we cap. `inf` from a
    # malformed header would hang the pull rather than end it, and a date a year
    # out is not a delay anything can sit through.
    return min(max(advertised, 0.0), MAX_RETRY_SECONDS)


def _advertised_wait(header: str | None) -> float | None:
    if header is None:
        return None
    value = header.strip()
    # RFC 9110 spells this either way, and only Notion itself is known to prefer
    # the seconds -- a proxy answering 429 in front of it may send the date.
    if DELAY_SECONDS.fullmatch(value):
        return float(value)
    # `parsedate_tz` reports an unreadable date by returning None rather than
    # raising, so a header we cannot parse never has to be caught and discarded.
    parsed = parsedate_tz(value)
    if parsed is None or parsed[9] is None:
        return None
    return mktime_tz(parsed) - time.time()


def _envelope(result: Json, blocks: list[Json] | None) -> Envelope:
    return Envelope(
        source="notion",
        source_id=result["id"],
        url=result["url"],
        title=_title(result),
        text=_text(blocks),
        parent_id=_parent_id(result["parent"]),
        # Left as the strings Notion sent. They are ISO 8601 in UTC, and rejecting
        # anything that is not is the Envelope's job, not this connector's.
        created_at=result["created_time"],
        last_modified=result["last_edited_time"],
        # Notion's own deletion flag. `is_archived` is a separate, read-only thing
        # here and is false on trashed records, so it tracks nothing we need.
        is_deleted=result["in_trash"],
        data=result if blocks is None else _extended(result, "blocks", blocks),
    )


def _text(blocks: list[Json] | None) -> str | None:
    """The prose of a page's body, one block to a line, in document order.

    Every kind of block that holds words holds them the same way: a `rich_text`
    array under a key named after the block's own type, each run carrying a
    `plain_text` already stripped of Notion's link and annotation structure. So
    the runs are collected by that key rather than by branching on the forty-odd
    block types, and a type we have never seen contributes its words without this
    function having to learn it first.

    A block holding no words -- a divider, an image, a `child_database` -- adds no
    line rather than a blank one, so a page whose whole body is containers comes
    out with no text at all.

    `None` means there is nothing to read, without saying why: a tree we never
    walked and a tree walked and found wordless both land here. The distinction is
    already in `data`, where a missing `blocks` key means not walked and an empty
    one means walked and empty. Repeating it in a second field would mean keeping
    the two in agreement forever for no reader that needs it.
    """
    if blocks is None:
        return None
    lines = [line for block in blocks for line in _lines_of(block)]
    return "\n".join(lines) or None


def _lines_of(block: Json) -> list[str]:
    lines = []
    body = block.get(block["type"])
    if isinstance(body, dict):
        runs = body.get("rich_text")
        if isinstance(runs, list):
            line = "".join(run["plain_text"] for run in runs)
            if line.strip():
                lines.append(line)
    # Nested blocks are the connector's own key, and their words are as much part
    # of the page as the ones at the top level.
    for child in block.get("children", []):
        lines.extend(_lines_of(child))
    return lines


def _extended(payload: Json, key: str, value: Any) -> Json:
    # `data` is Notion's namespace and this key is ours. If Notion ever starts
    # sending one of its own under the same name, overwriting it would leave
    # nothing downstream able to tell the platform's value from the connector's.
    if key in payload:
        raise NotionError(
            f"Notion sent its own {key!r}, which is the key this connector adds"
        )
    return {**payload, key: value}


def _title(result: Json) -> str | None:
    if result["object"] == "data_source":
        runs = result["title"]
    elif result["object"] == "page":
        runs = _title_runs(result)
    else:
        raise NotionError(
            f"search returned an object this connector cannot read: {result['object']}"
        )
    # Notion round-trips a title byte for byte -- emoji, right-to-left text, a
    # literal newline, 250 characters, whitespace only -- so the one title we are
    # entitled to rewrite is the one that is not there.
    return "".join(run["plain_text"] for run in runs) or None


def _title_runs(page: Json) -> list[Json]:
    # There is no flat title field, and the property key is whatever the schema
    # named that column -- "title" on a prose page, "Name" on a row -- so the
    # property's type is the only stable handle on it.
    for prop in page["properties"].values():
        if prop["type"] == "title":
            runs: list[Json] = prop["title"]
            return runs
    raise NotionError(f"page {page['id']} has no property of type title")


def _parent_id(parent: Json) -> str | None:
    # Notion names the id field after the parent type: `"page_id": "..."` under
    # type `page_id`. The workspace root is the one type carrying no id.
    parent_type = parent["type"]
    if parent_type == "workspace":
        return None
    if parent_type not in parent:
        raise NotionError(
            f"parent of type {parent_type!r} carries no {parent_type!r}: {parent}"
        )
    parent_id: str = parent[parent_type]
    return parent_id
