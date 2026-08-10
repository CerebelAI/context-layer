"""Locks the decisions the store makes, not Qdrant's behaviour.

The client is a double throughout, so nothing here touches the network. What the
real Qdrant calls do is proven by `manual_test_qdrant.py`, which these cannot
cover and are not trying to.
"""

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client.http.models.models import QueryResponse
from qdrant_client.models import (
    Distance,
    Document,
    PointStruct,
    Record,
    ScoredPoint,
    VectorParams,
)

from connectors import Envelope
from knowledge import SCORE_THRESHOLD, KnowledgeError, Store
from knowledge.store import _EMBEDDING_MODEL, _EMBEDDING_WINDOW

MakeEnvelope = Callable[..., Envelope]

TENANT = "acme"
OTHER_TENANT = "globex"

# Distinguishes "no collection there yet" from "one is there, configured thus".
_UNSET = object()


class FakeClient:
    """Stands in for QdrantClient, recording calls and replaying canned points."""

    def __init__(
        self,
        *,
        stored: list[Record] | None = None,
        hits: list[ScoredPoint] | None = None,
        existing_vectors: Any = _UNSET,
    ) -> None:
        self.upserted: list[PointStruct] = []
        self.deleted: list[Any] = []
        self.queries: list[dict[str, Any]] = []
        self.created_indexes: list[str] = []
        self.collections_created: list[str] = []
        self._stored = stored if stored is not None else []
        self._hits = hits if hits is not None else []
        # Not _UNSET means a collection of that name is already there, configured
        # this way -- the case where someone points at somebody else's collection.
        self._existing_vectors = existing_vectors

    def collection_exists(self, collection_name: str) -> bool:
        return (
            self._existing_vectors is not _UNSET
            or collection_name in self.collections_created
        )

    def get_collection(self, collection_name: str) -> Any:
        vectors = (
            VectorParams(size=384, distance=Distance.COSINE)
            if self._existing_vectors is _UNSET
            else self._existing_vectors
        )
        return SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(vectors=vectors))
        )

    def create_collection(self, collection_name: str, **kwargs: Any) -> None:
        self.collections_created.append(collection_name)

    def create_payload_index(
        self, collection_name: str, field_name: str, **kw: Any
    ) -> None:
        self.created_indexes.append(field_name)

    def upsert(
        self, collection_name: str, points: list[PointStruct], **kw: Any
    ) -> None:
        self.upserted.extend(points)

    def retrieve(self, collection_name: str, ids: list[Any], **kw: Any) -> list[Record]:
        return [record for record in self._stored if record.id in ids]

    def delete(self, collection_name: str, points_selector: Any, **kw: Any) -> None:
        self.deleted.append(points_selector)

    def query_points(self, collection_name: str, **kwargs: Any) -> QueryResponse:
        self.queries.append(kwargs)
        return QueryResponse(points=self._hits)


def record(
    envelope: Envelope, tenant_id: str = TENANT, **payload_overrides: Any
) -> Record:
    """A stored point as the real client hands it back."""
    payload = {**envelope.model_dump(mode="json"), "tenant_id": tenant_id}
    payload.update(payload_overrides)
    return Record(id=Store.point_id(tenant_id, *envelope.upsert_key), payload=payload)


def hit(envelope: Envelope, score: float, tenant_id: str = TENANT) -> ScoredPoint:
    return ScoredPoint(
        id=Store.point_id(tenant_id, *envelope.upsert_key),
        version=1,
        score=score,
        payload={**envelope.model_dump(mode="json"), "tenant_id": tenant_id},
    )


def store(client: FakeClient) -> Store:
    # The double is structural, not a QdrantClient; the cast keeps that local.
    return Store(client, "records")  # type: ignore[arg-type]


def _embedded(client: FakeClient) -> str:
    """The text the store handed Qdrant to turn into a vector."""
    vector = client.upserted[0].vector
    assert isinstance(vector, Document)
    return vector.text


# --- identity -----------------------------------------------------------------


def test_the_same_record_under_two_tenants_gets_two_points(
    make_envelope: MakeEnvelope,
) -> None:
    envelope = make_envelope()

    mine = Store.point_id(TENANT, *envelope.upsert_key)
    theirs = Store.point_id(OTHER_TENANT, *envelope.upsert_key)

    assert mine != theirs


def test_re_ingesting_a_record_overwrites_rather_than_duplicating(
    make_envelope: MakeEnvelope,
) -> None:
    client = FakeClient()
    first = make_envelope()
    repulled = make_envelope(title="Onboarding checklist, revised")

    store(client).upsert([first], tenant_id=TENANT)
    store(client).upsert([repulled], tenant_id=TENANT)

    assert len(client.upserted) == 2
    assert client.upserted[0].id == client.upserted[1].id


def test_two_different_records_get_two_points(make_envelope: MakeEnvelope) -> None:
    client = FakeClient()

    store(client).upsert(
        [make_envelope(source_id="one"), make_envelope(source_id="two")],
        tenant_id=TENANT,
    )

    assert client.upserted[0].id != client.upserted[1].id


# --- what gets written --------------------------------------------------------


def test_the_stored_payload_is_the_envelope_plus_exactly_the_tenant(
    make_envelope: MakeEnvelope,
) -> None:
    # The one place the stored record is not exactly the envelope. A third key
    # slipping in here is the drift knowledge/__init__.py warns about.
    client = FakeClient()
    envelope = make_envelope()

    store(client).upsert([envelope], tenant_id=TENANT)

    payload = client.upserted[0].payload
    assert payload is not None
    assert payload == {**envelope.model_dump(mode="json"), "tenant_id": TENANT}


def test_the_embedded_text_is_the_title_and_the_prose(
    make_envelope: MakeEnvelope,
) -> None:
    client = FakeClient()

    store(client).upsert([make_envelope()], tenant_id=TENANT)

    assert _embedded(client) == (
        "Onboarding checklist\nNew engineers get a laptop on day one."
    )


def test_the_embedded_text_does_not_carry_the_vendor_payload(
    make_envelope: MakeEnvelope,
) -> None:
    # The one that matters. `data` is ids, timestamps and JSON punctuation, and
    # the model reads 512 tokens before it stops -- so a payload in here does not
    # merely add noise, it crowds the prose out of the window entirely and leaves
    # every record embedding to roughly the same vector.
    client = FakeClient()
    envelope = make_envelope(
        data={
            "object": "page",
            "id": "59833787-2cf9-4fdf-8782-e53db20768a5",
            "created_time": "2026-01-01T00:00:00.000Z",
            "properties": {"Owner": "platform team"},
        }
    )

    store(client).upsert([envelope], tenant_id=TENANT)

    embedded = _embedded(client)
    assert "59833787" not in embedded
    assert "created_time" not in embedded
    assert "platform team" not in embedded
    assert "{" not in embedded


def test_a_record_with_neither_title_nor_prose_still_gets_something_to_embed(
    make_envelope: MakeEnvelope,
) -> None:
    # Qdrant needs a vector for every point. The url matches nothing anyone would
    # search for, which is the honest outcome for a record carrying no words.
    client = FakeClient()

    store(client).upsert([make_envelope(title=None, text=None)], tenant_id=TENANT)

    assert _embedded(client) == "https://www.notion.so/Onboarding-598337872cf9"


def test_the_embedded_text_of_a_real_notion_page_is_prose_within_the_model_budget(
    make_envelope: MakeEnvelope,
) -> None:
    # The doubles cannot see truncation -- nothing in them embeds anything -- so
    # this is the one test that tokenizes. It is the check that would have caught
    # `data` being embedded: measured against a captured Notion page, that spent
    # 468 of 512 tokens before reaching the first word of the body.
    fastembed = pytest.importorskip("fastembed")
    tokenizer = fastembed.TextEmbedding(_EMBEDDING_MODEL).model.tokenizer

    page = json.loads(
        (
            Path(__file__).parent / "fixtures" / "notion" / "search" / "live.1.json"
        ).read_text(encoding="utf-8")
    )["results"][0]
    client = FakeClient()
    store(client).upsert(
        [
            make_envelope(
                title="Weekly ops review", text="Deploys go out on Tuesday.", data=page
            )
        ],
        tenant_id=TENANT,
    )

    embedded = _embedded(client)
    tokens = len(tokenizer.encode(embedded).ids)
    assert tokens < _EMBEDDING_WINDOW, f"{tokens} tokens would be truncated"
    # Every token spent is spent on words rather than on the page's plumbing.
    assert embedded == "Weekly ops review\nDeploys go out on Tuesday."


def test_an_untitled_record_is_embedded_from_its_prose(
    make_envelope: MakeEnvelope,
) -> None:
    # A Slack message has no title and is nothing but text, so a title-only
    # embedding would make that whole platform unsearchable.
    client = FakeClient()

    store(client).upsert([make_envelope(title=None)], tenant_id=TENANT)

    assert _embedded(client) == "New engineers get a laptop on day one."


def test_upsert_reports_how_many_it_wrote(make_envelope: MakeEnvelope) -> None:
    client = FakeClient()

    written = store(client).upsert(
        [make_envelope(source_id="one"), make_envelope(source_id="two")],
        tenant_id=TENANT,
    )

    assert written == 2


def test_upsert_of_nothing_does_not_call_the_client() -> None:
    client = FakeClient()

    assert store(client).upsert([], tenant_id=TENANT) == 0
    assert client.upserted == []


# --- reading back -------------------------------------------------------------


def test_get_returns_the_envelope_without_the_tenant_key(
    make_envelope: MakeEnvelope,
) -> None:
    # Envelope forbids unknown fields, so a tenant_id left on the payload would
    # make every stored record unreadable.
    envelope = make_envelope()
    client = FakeClient(stored=[record(envelope)])

    got = store(client).get("notion", envelope.source_id, tenant_id=TENANT)

    assert got == envelope


def test_get_returns_none_when_nothing_is_stored() -> None:
    assert store(FakeClient()).get("notion", "missing", tenant_id=TENANT) is None


def test_get_refuses_a_record_owned_by_another_tenant(
    make_envelope: MakeEnvelope,
) -> None:
    # Tenancy is in the point id, so a cross-tenant read normally just misses.
    # This forces the miss not to happen: the point sits at *our* id but the
    # payload says someone else owns it. The ownership check is what refuses, and
    # it is the thing standing between a hash collision and a data leak.
    envelope = make_envelope()
    planted = Record(
        id=Store.point_id(TENANT, *envelope.upsert_key),
        payload={**envelope.model_dump(mode="json"), "tenant_id": OTHER_TENANT},
    )
    client = FakeClient(stored=[planted])

    assert store(client).get("notion", envelope.source_id, tenant_id=TENANT) is None


def test_get_still_returns_a_record_deleted_on_its_platform(
    make_envelope: MakeEnvelope,
) -> None:
    envelope = make_envelope(is_deleted=True)
    client = FakeClient(stored=[record(envelope)])

    got = store(client).get("notion", envelope.source_id, tenant_id=TENANT)

    assert got is not None
    assert got.is_deleted is True


def test_a_stored_point_with_no_payload_raises_rather_than_reading_as_missing(
    make_envelope: MakeEnvelope,
) -> None:
    envelope = make_envelope()
    client = FakeClient(
        stored=[Record(id=Store.point_id(TENANT, *envelope.upsert_key), payload=None)]
    )

    with pytest.raises(KnowledgeError):
        store(client).get("notion", envelope.source_id, tenant_id=TENANT)


# --- search -------------------------------------------------------------------


def test_search_returns_matches_with_their_score(make_envelope: MakeEnvelope) -> None:
    envelope = make_envelope()
    client = FakeClient(hits=[hit(envelope, 0.87)])

    matches = store(client).search("how do we onboard", tenant_id=TENANT)

    assert [(m.envelope, m.score) for m in matches] == [(envelope, 0.87)]


def test_search_drops_matches_under_the_threshold(make_envelope: MakeEnvelope) -> None:
    strong = make_envelope(source_id="strong")
    weak = make_envelope(source_id="weak")
    client = FakeClient(
        hits=[hit(strong, SCORE_THRESHOLD), hit(weak, SCORE_THRESHOLD - 0.01)]
    )

    matches = store(client).search("anything", tenant_id=TENANT)

    assert [m.envelope.source_id for m in matches] == ["strong"]


def test_search_asks_qdrant_to_scope_to_the_tenant_and_skip_deleted() -> None:
    # Filtering here rather than after the fact: a post-filter would silently
    # shrink `limit` and could return another tenant's record on a code path that
    # forgot to check.
    client = FakeClient()

    store(client).search("anything", tenant_id=TENANT, limit=3)

    query = client.queries[0]
    assert query["limit"] == 3
    conditions = repr(query["query_filter"])
    assert TENANT in conditions
    assert "is_deleted" in conditions


def test_search_returns_empty_when_nothing_matched() -> None:
    assert store(FakeClient()).search("nothing stored", tenant_id=TENANT) == []


def test_a_matched_point_with_no_payload_raises(make_envelope: MakeEnvelope) -> None:
    client = FakeClient(
        hits=[ScoredPoint(id="abc", version=1, score=0.9, payload=None)]
    )

    with pytest.raises(KnowledgeError):
        store(client).search("anything", tenant_id=TENANT)


# --- delete -------------------------------------------------------------------


def test_delete_removes_the_point_and_reports_it(make_envelope: MakeEnvelope) -> None:
    envelope = make_envelope()
    client = FakeClient(stored=[record(envelope)])

    assert store(client).delete("notion", envelope.source_id, tenant_id=TENANT) is True
    assert len(client.deleted) == 1


def test_delete_of_something_not_stored_reports_false() -> None:
    client = FakeClient()

    assert store(client).delete("notion", "missing", tenant_id=TENANT) is False
    assert client.deleted == []


def test_delete_refuses_a_record_owned_by_another_tenant(
    make_envelope: MakeEnvelope,
) -> None:
    # Same planted collision as the get case. Refusing to read the wrong tenant's
    # record is bad enough; destroying it is worse.
    envelope = make_envelope()
    planted = Record(
        id=Store.point_id(TENANT, *envelope.upsert_key),
        payload={**envelope.model_dump(mode="json"), "tenant_id": OTHER_TENANT},
    )
    client = FakeClient(stored=[planted])

    assert store(client).delete("notion", envelope.source_id, tenant_id=TENANT) is False
    assert client.deleted == []


# --- setup --------------------------------------------------------------------


def test_ensure_collection_creates_it_once_and_indexes_what_search_filters_on() -> None:
    client = FakeClient()

    store(client).ensure_collection()
    store(client).ensure_collection()

    assert client.collections_created == ["records"]
    assert set(client.created_indexes) == {"tenant_id", "is_deleted"}


def test_starting_on_a_collection_built_for_named_vectors_refuses() -> None:
    # What company-brain's collection actually looks like: fastembed's helper
    # names the vector after the model. Writing an unnamed vector to it fails with
    # "Not existing vector name" on the first upsert, long after the mistake.
    client = FakeClient(
        existing_vectors={
            "fast-bge-small-en-v1.5": VectorParams(size=384, distance=Distance.COSINE)
        }
    )

    with pytest.raises(KnowledgeError, match="named vectors"):
        store(client).ensure_collection()


def test_starting_on_a_collection_of_the_wrong_dimension_refuses() -> None:
    client = FakeClient(
        existing_vectors=VectorParams(size=1536, distance=Distance.COSINE)
    )

    with pytest.raises(KnowledgeError, match="1536|384"):
        store(client).ensure_collection()


def test_starting_on_a_matching_collection_leaves_it_alone() -> None:
    client = FakeClient(
        existing_vectors=VectorParams(size=384, distance=Distance.COSINE)
    )

    store(client).ensure_collection()

    assert client.collections_created == []
    assert set(client.created_indexes) == {"tenant_id", "is_deleted"}
