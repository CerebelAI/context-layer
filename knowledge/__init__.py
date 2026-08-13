"""Owns the store: takes `Envelope` records and holds them.

Middle of the chain `server` -> `knowledge` -> `connectors`; imports `connectors` for
the `Envelope` type and nothing else. Wiring happens in `main.py`, not here.

Envelopes come from `connectors` and from the MCP write side in `server`; a producer
that emits something else adapts it to `Envelope` on its own side.

Sync, store write included. The write is I/O and `server` is async, so `server` bridges
with `asyncio.to_thread` rather than this module going async for one function
(ADR-0005).

The `Envelope` is also the stored record -- one vector entry per envelope, its fields
the entry's fields. A separate storage template would drift: a field added to the
`Envelope` and forgotten there stops reaching the store, and nothing fails when it
does. What a backend needs on top, an embedding or `data` serialized because it only
takes scalars, is its encoding of that shape, not a second shape.

The store is Qdrant, and a record is scoped to a `tenant_id` -- a company. That is the
isolation boundary: entries written under one tenant are only ever readable under the
same one. It is a payload key rather than a field on `Envelope`, because a record's
tenant is not a property of the platform it was pulled from.

Retrieval embeds locally through Qdrant's own fastembed, so nothing here calls out to a
model provider.
"""

from knowledge.store import SCORE_THRESHOLD, KnowledgeError, Match, Store

__all__ = ["SCORE_THRESHOLD", "KnowledgeError", "Match", "Store"]
