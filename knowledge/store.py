import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from connectors import Envelope

# Qdrant runs this one locally through fastembed, so retrieval needs no model
# provider.
_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
_EMBEDDING_SIZE = 384

# The model reads this many tokens and silently drops the rest -- it does not
# fail, and nothing downstream can tell a fully embedded record from a truncated
# one. Named here because it is the constraint the whole design of `_embed_text`
# answers to, and because it is what makes a long record findable only by its
# opening. One point per record stands regardless (ADR-0006).
_EMBEDDING_WINDOW = 512

SCORE_THRESHOLD = 0.5
"""Minimum cosine score for a match to count as relevant.

Carried over from the old repo, where it was tuned against this same embedding
model. It is a property of the model and the corpus, not of the caller, so it is
applied here rather than exposed for `server` to re-declare.
"""

# Point ids must be a UUID or an unsigned int and the record key is neither, so it
# is hashed into one through a fixed namespace. Changing this value orphans every
# stored point.
_ID_NAMESPACE = uuid.UUID("6f9c3f1e-2b4a-5c8d-9e0f-1a2b3c4d5e6f")

_TENANT_KEY = "tenant_id"


class KnowledgeError(Exception):
    """Raised when the store cannot serve a request."""


class Match(BaseModel):
    """One search hit: the stored envelope and how well it matched the query."""

    envelope: Envelope
    score: float


def _embed_text(envelope: Envelope) -> str:
    # `data` deliberately does not appear here. It is the vendor payload, and a
    # vendor payload is mostly ids and timestamps: embedding one Notion page from
    # it spends 468 of the model's 512 tokens before reaching the first word of
    # the body, so every page comes out looking like every other page. `text` is
    # the same content with that structure taken off, which is why connectors
    # produce it.
    #
    # `url` only stands in for a record with neither a title nor a word of prose.
    # It matches nothing a person would search for, but a point needs a vector.
    return "\n".join(part for part in (envelope.title, envelope.text) if part) or (
        envelope.url
    )


class Store:
    """The store holding envelopes, backed by a Qdrant collection.

    One vector entry per envelope. The payload is the envelope's own JSON dump
    plus `tenant_id`, and nothing else: a field added to `Envelope` reaches the
    store without a second shape having to be updated to match.

    `tenant_id` is the isolation key -- a company. It is a payload key rather than
    a field on `Envelope` because the envelope is the connectors' contract and a
    record's tenant is not a property of the platform it came from. It is also
    part of the point id, so two tenants holding the same Notion page hold two
    separate points.

    Sync, write included. `server` bridges to it with `asyncio.to_thread`.

    The client is passed in rather than built here, so `main.py` stays the only
    place that knows the credentials and tests can hand in a double.
    """

    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self._collection = collection

    @staticmethod
    def point_id(tenant_id: str, source: str, source_id: str) -> str:
        """The stable id of a record: the same three parts always give the same id."""
        return str(uuid.uuid5(_ID_NAMESPACE, f"{tenant_id}:{source}:{source_id}"))

    def ensure_collection(self) -> None:
        """Create the collection and the indexes search filters on, if absent.

        Called once at startup from `main.py`. Safe to repeat.

        Raises:
            KnowledgeError: if a collection of that name already exists but is not
                shaped the way this store writes. Starting anyway turns a
                configuration mistake into an opaque rejection on first write, or
                worse into envelopes landing in a collection holding some other
                kind of record.
        """
        if self._client.collection_exists(self._collection):
            self._check_shape()
        else:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=_EMBEDDING_SIZE, distance=Distance.COSINE
                ),
            )
        self._client.create_payload_index(
            collection_name=self._collection,
            field_name=_TENANT_KEY,
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self._client.create_payload_index(
            collection_name=self._collection,
            field_name="is_deleted",
            field_schema=PayloadSchemaType.BOOL,
        )

    def upsert(self, envelopes: Sequence[Envelope], tenant_id: str) -> int:
        """Store envelopes under a tenant, returning how many were written.

        A record already stored under the same `(tenant_id, source, source_id)` is
        overwritten, so re-ingesting is how a record is updated.
        """
        if not envelopes:
            return 0
        points = [
            PointStruct(
                id=self.point_id(tenant_id, *envelope.upsert_key),
                vector=Document(text=_embed_text(envelope), model=_EMBEDDING_MODEL),
                payload={**envelope.model_dump(mode="json"), _TENANT_KEY: tenant_id},
            )
            for envelope in envelopes
        ]
        self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    def get(self, source: str, source_id: str, tenant_id: str) -> Envelope | None:
        """Fetch one envelope by its key, or None if this tenant has no such record.

        Returns records marked deleted on their platform; `search` does not.
        """
        payload = self._owned_payload(source, source_id, tenant_id)
        return None if payload is None else self._to_envelope(payload)

    def delete(self, source: str, source_id: str, tenant_id: str) -> bool:
        """Remove one record from the store, reporting whether there was one.

        This erases the stored copy. It is not `Envelope.is_deleted`, which is a
        connector reporting that the record is gone on the platform.
        """
        if self._owned_payload(source, source_id, tenant_id) is None:
            return False
        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(
                points=[self.point_id(tenant_id, source, source_id)]
            ),
        )
        return True

    def search(self, query: str, tenant_id: str, limit: int = 5) -> list[Match]:
        """Semantic search over this tenant's envelopes, best match first.

        Returns only matches worth returning: anything below `SCORE_THRESHOLD` is
        dropped, so an empty list means nothing stored is relevant. Records
        deleted on their platform are excluded -- they are kept so a consumer can
        see that a record is gone, not so they can come back as an answer.
        """
        response = self._client.query_points(
            collection_name=self._collection,
            query=Document(text=query, model=_EMBEDDING_MODEL),
            query_filter=Filter(
                must=[
                    FieldCondition(key=_TENANT_KEY, match=MatchValue(value=tenant_id))
                ],
                must_not=[
                    FieldCondition(key="is_deleted", match=MatchValue(value=True))
                ],
            ),
            limit=limit,
            with_payload=True,
        )
        matches: list[Match] = []
        for point in response.points:
            if point.payload is None:
                raise KnowledgeError(f"stored point {point.id} carries no payload")
            if point.score < SCORE_THRESHOLD:
                continue
            matches.append(
                Match(envelope=self._to_envelope(point.payload), score=point.score)
            )
        return matches

    def _check_shape(self) -> None:
        """Refuse a pre-existing collection this store cannot write to.

        The case this is really about is pointing at a collection some other
        system built. `company-brain` made one through fastembed's helper, which
        names its vector, and filled it with a different kind of record -- so the
        write fails with `Not existing vector name` and, had it not, its points
        would not validate as envelopes on the way back out.
        """
        vectors = self._client.get_collection(self._collection).config.params.vectors
        if isinstance(vectors, dict):
            raise KnowledgeError(
                f"collection {self._collection!r} uses named vectors "
                f"({', '.join(sorted(vectors))}); this store writes an unnamed one. "
                "Point QDRANT_COLLECTION_NAME at a new collection."
            )
        if vectors is None or (vectors.size, vectors.distance) != (
            _EMBEDDING_SIZE,
            Distance.COSINE,
        ):
            raise KnowledgeError(
                f"collection {self._collection!r} is configured as {vectors!r}, "
                f"but this store writes {_EMBEDDING_SIZE}-dimension cosine vectors. "
                "Point QDRANT_COLLECTION_NAME at a new collection."
            )

    def _owned_payload(
        self, source: str, source_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """The stored payload for a key, but only if this tenant owns it."""
        records = self._client.retrieve(
            collection_name=self._collection,
            ids=[self.point_id(tenant_id, source, source_id)],
            with_payload=True,
        )
        if not records:
            return None
        payload = records[0].payload
        if payload is None:
            raise KnowledgeError(
                f"stored point for ({tenant_id}, {source}, {source_id}) carries no payload"
            )
        # Tenancy is already in the point id, so this only bites on a uuid5
        # collision. It is the difference between that collision being a wrong
        # answer and it being a leak across companies.
        if payload.get(_TENANT_KEY) != tenant_id:
            return None
        return payload

    @staticmethod
    def _to_envelope(payload: dict[str, Any]) -> Envelope:
        # `Envelope` forbids unknown fields, so the one key the store adds has to
        # come back off before it will validate.
        return Envelope.model_validate(
            {key: value for key, value in payload.items() if key != _TENANT_KEY}
        )
