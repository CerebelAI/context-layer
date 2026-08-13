# knowledge is sync; server bridges

**Status: accepted.**

Async lives at the I/O boundaries: connectors and the MCP server are `async`. Everything else
is plain sync. `knowledge` is sync including the store write, and `server` bridges it with
`asyncio.to_thread` rather than the whole module going async for one function.

Revisit if extraction's model calls make that two.
