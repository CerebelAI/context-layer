"""Owns the MCP server that exposes the store to consumers, for both read and write.

Top of the chain `server` -> `knowledge` -> `connectors`; imported by neither.

Every tool is a thin wrapper over the store. No retrieval, ranking or storage logic
lives here -- this module is transport, and the moment it starts deciding what counts
as a good enough match it stops being that.

`Envelope` is the wire shape in both directions, the same seam `knowledge` accepts
records on. Consumers hand envelopes in and get envelopes back, so the MCP write side
is just another producer alongside the connectors.

The store arrives injected through `build_server` rather than being constructed here,
so `main.py` stays the only place that knows the credentials and the tools can be
tested against a double instead of a live vector database.

The store is sync and MCP tool handlers are async, so every tool bridges with
`asyncio.to_thread` rather than blocking the event loop on a network round trip.

The tool docstrings are the API. Nothing else documents this server to the agent
calling it, so they carry what a caller has to know -- what an envelope requires, and
that re-sending a record updates it -- rather than restating the signature.
"""

import asyncio
from typing import Literal

from mcp.server import MCPServer

from connectors import Envelope
from knowledge import Match, Store

__all__ = ["build_server"]

# Mirrors `Envelope.source`, which is closed on purpose (ADR-0009).
Source = Literal["notion"]


def build_server(store: Store) -> MCPServer:
    """Build the MCP server exposing `store` over its read and write tools."""
    mcp = MCPServer(name="context-layer")

    @mcp.tool()
    async def ingest_records(envelopes: list[Envelope], tenant_id: str) -> int:
        """Store records under a tenant, returning how many were written.

        This is the write side. Each record is an envelope: one thing pulled from a
        platform, in the shape everything here consumes. Every envelope needs
        `source` (notion), `source_id` (that platform's own stable
        id for the record -- never a title, a URL or a position in a list), `url`,
        `created_at` and `last_modified` (both with a timezone offset), and
        `is_deleted`. `title` and `parent_id` may be null. Put the platform's own
        payload in `data` untouched; anything platform-specific belongs there and
        nowhere else.

        `(source, source_id)` identifies a record within a tenant. Sending the same
        pair again overwrites the stored copy instead of adding a second one, so
        re-sending is safe and is how you update a record.

        `tenant_id` is the company the records belong to. Records written under one
        tenant are only ever readable under that same one.
        """
        return await asyncio.to_thread(store.upsert, envelopes, tenant_id)

    @mcp.tool()
    async def search_records(query: str, tenant_id: str, limit: int = 5) -> list[Match]:
        """Search a tenant's stored records and return the relevant ones.

        The primary read tool. Returns the records themselves rather than a written
        answer, each with the score it matched at, best match first -- so you can
        ground your own reply in them and link back to each record's `url`.

        Returns an empty list when nothing stored is relevant; weak matches are
        dropped rather than returned for you to judge. Records deleted on their
        platform are never returned, so use `get_record` if you need to confirm one
        is gone.
        """
        return await asyncio.to_thread(store.search, query, tenant_id, limit)

    @mcp.tool()
    async def get_record(
        source: Source, source_id: str, tenant_id: str
    ) -> Envelope | None:
        """Fetch one stored record by the platform it came from and its id there.

        Returns null when this tenant has no such record. Unlike `search_records`
        this does return records marked deleted on their platform, so `is_deleted`
        on the result is worth checking before you use it.
        """
        return await asyncio.to_thread(store.get, source, source_id, tenant_id)

    @mcp.tool()
    async def delete_record(source: Source, source_id: str, tenant_id: str) -> bool:
        """Erase one stored record, reporting whether there was one to erase.

        This removes the stored copy outright. It is not the same as the record's
        `is_deleted` flag, which reports that the record is gone on its platform and
        is set by whoever supplied the record, not by this tool.
        """
        return await asyncio.to_thread(store.delete, source, source_id, tenant_id)

    return mcp
