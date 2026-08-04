"""Owns extraction of raw pulls into facts and processes, and the store holding them.

Middle of the chain `server` -> `knowledge` -> `connectors`; imports `connectors` for
the `Envelope` type and nothing else. Wiring happens in `main.py`, not here.

It takes `Envelope` records and stores them. The first version
does only that -- no extraction, no facts, no processes yet. Envelopes come from
`connectors` and from the MCP write side in `server`; a producer that emits something
else adapts it to `Envelope` on its own side.

Sync, store write included. The write is I/O and `server` is async, so `server` bridges
with `asyncio.to_thread` rather than this module going async for one function. Revisit
if extraction's model calls make that two.

The `Envelope` is also the stored record -- one vector entry per envelope, its fields
the entry's fields. A separate storage template would drift: a field added to the
`Envelope` and forgotten there stops reaching the store, and nothing fails when it
does. What a backend needs on top, an embedding or `data` serialized because it only
takes scalars, is its encoding of that shape, not a second shape.

Undecided, and not to be settled in passing: the format facts and processes are stored
in, whether the fact store stays the current cloud vector database, and the model
provider -- OpenRouter is temporary. Keep persistence and model calls behind a thin
interface so all three stay swappable, and ask rather than picking.
"""
