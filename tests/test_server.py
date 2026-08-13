"""Locks what the MCP tools do with a call, against a store that is a double.

The tools are wrappers, so what is worth testing is the wrapping: that arguments
reach the store unmangled, that a bad record is refused before the store sees it,
and that a failure below is not turned into a plausible-looking empty result.
"""

from collections.abc import Callable, Sequence

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from connectors import Envelope
from knowledge import Match
from server import build_server

MakeEnvelope = Callable[..., Envelope]

TENANT = "acme"


class FakeStore:
    """Records what the server asked for and returns what it was told to."""

    def __init__(
        self,
        *,
        get_result: Envelope | None = None,
        search_result: list[Match] | None = None,
        delete_result: bool = True,
    ) -> None:
        self.upsert_calls: list[tuple[list[Envelope], str]] = []
        self.get_calls: list[tuple[str, str, str]] = []
        self.search_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[tuple[str, str, str]] = []
        self._get_result = get_result
        self._search_result = search_result if search_result is not None else []
        self._delete_result = delete_result

    def upsert(self, envelopes: Sequence[Envelope], tenant_id: str) -> int:
        self.upsert_calls.append((list(envelopes), tenant_id))
        return len(envelopes)

    def get(self, source: str, source_id: str, tenant_id: str) -> Envelope | None:
        self.get_calls.append((source, source_id, tenant_id))
        return self._get_result

    def search(self, query: str, tenant_id: str, limit: int = 5) -> list[Match]:
        self.search_calls.append((query, tenant_id, limit))
        return self._search_result

    def delete(self, source: str, source_id: str, tenant_id: str) -> bool:
        self.delete_calls.append((source, source_id, tenant_id))
        return self._delete_result


def server(store: FakeStore) -> MCPServer:
    # The double is structural, not a Store; the cast keeps that local.
    return build_server(store)  # type: ignore[arg-type]


async def call(mcp: MCPServer, name: str, arguments: dict[str, object]) -> object:
    """Invoke a tool the way a client would, and return its structured result."""
    result = await mcp.call_tool(name, arguments)
    assert isinstance(result, CallToolResult)
    assert not result.is_error, result.content
    return result.structured_content


@pytest.mark.anyio
async def test_exposes_the_read_and_write_tools() -> None:
    names = {tool.name for tool in await server(FakeStore()).list_tools()}

    assert names == {
        "ingest_records",
        "search_records",
        "get_record",
        "delete_record",
    }


# --- write --------------------------------------------------------------------


@pytest.mark.anyio
async def test_ingest_passes_the_envelopes_and_tenant_through(
    make_envelope: MakeEnvelope,
) -> None:
    store = FakeStore()
    envelope = make_envelope()

    result = await call(
        server(store),
        "ingest_records",
        {"envelopes": [envelope.model_dump(mode="json")], "tenant_id": TENANT},
    )

    assert store.upsert_calls == [([envelope], TENANT)]
    assert result == {"result": 1}


@pytest.mark.anyio
async def test_ingest_refuses_a_record_the_envelope_contract_rejects(
    make_envelope: MakeEnvelope,
) -> None:
    # An empty source_id would collapse every record from a platform onto one
    # key. The store must never see it.
    store = FakeStore()
    payload = make_envelope().model_dump(mode="json")
    payload["source_id"] = ""

    with pytest.raises(ToolError):
        await call(
            server(store),
            "ingest_records",
            {"envelopes": [payload], "tenant_id": TENANT},
        )

    assert store.upsert_calls == []


@pytest.mark.anyio
async def test_ingest_refuses_a_naive_timestamp(make_envelope: MakeEnvelope) -> None:
    store = FakeStore()
    payload = make_envelope().model_dump(mode="json")
    payload["last_modified"] = "2026-02-01T00:00:00"

    with pytest.raises(ToolError):
        await call(
            server(store),
            "ingest_records",
            {"envelopes": [payload], "tenant_id": TENANT},
        )

    assert store.upsert_calls == []


# --- read ---------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_returns_the_matches_with_their_scores(
    make_envelope: MakeEnvelope,
) -> None:
    envelope = make_envelope()
    store = FakeStore(search_result=[Match(envelope=envelope, score=0.87)])

    result = await call(
        server(store),
        "search_records",
        {"query": "how do we onboard", "tenant_id": TENANT},
    )

    assert store.search_calls == [("how do we onboard", TENANT, 5)]
    assert result == {
        "result": [{"envelope": envelope.model_dump(mode="json"), "score": 0.87}]
    }


@pytest.mark.anyio
async def test_search_passes_an_explicit_limit_down() -> None:
    store = FakeStore()

    await call(
        server(store),
        "search_records",
        {"query": "anything", "tenant_id": TENANT, "limit": 25},
    )

    assert store.search_calls == [("anything", TENANT, 25)]


@pytest.mark.anyio
async def test_search_returns_empty_when_nothing_is_relevant() -> None:
    result = await call(
        server(FakeStore()), "search_records", {"query": "nope", "tenant_id": TENANT}
    )

    assert result == {"result": []}


@pytest.mark.anyio
async def test_get_fetches_by_platform_id_and_tenant(
    make_envelope: MakeEnvelope,
) -> None:
    envelope = make_envelope()
    store = FakeStore(get_result=envelope)

    result = await call(
        server(store),
        "get_record",
        {"source": "notion", "source_id": envelope.source_id, "tenant_id": TENANT},
    )

    assert store.get_calls == [("notion", envelope.source_id, TENANT)]
    assert result == {"result": envelope.model_dump(mode="json")}


@pytest.mark.anyio
async def test_get_returns_null_when_the_tenant_has_no_such_record() -> None:
    result = await call(
        server(FakeStore(get_result=None)),
        "get_record",
        {"source": "notion", "source_id": "missing", "tenant_id": TENANT},
    )

    assert result == {"result": None}


@pytest.mark.anyio
async def test_get_refuses_a_source_that_is_not_a_connected_platform() -> None:
    store = FakeStore()

    for source in ("dropbox", "slack"):
        with pytest.raises(ToolError):
            await call(
                server(store),
                "get_record",
                {"source": source, "source_id": "abc123", "tenant_id": TENANT},
            )

    assert store.get_calls == []


# --- delete -------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_passes_the_key_and_tenant_through() -> None:
    store = FakeStore(delete_result=True)

    result = await call(
        server(store),
        "delete_record",
        {"source": "notion", "source_id": "abc123", "tenant_id": TENANT},
    )

    assert store.delete_calls == [("notion", "abc123", TENANT)]
    assert result == {"result": True}


@pytest.mark.anyio
async def test_delete_reports_false_when_there_was_nothing_to_erase() -> None:
    result = await call(
        server(FakeStore(delete_result=False)),
        "delete_record",
        {"source": "notion", "source_id": "missing", "tenant_id": TENANT},
    )

    assert result == {"result": False}


# --- failure ------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_store_failure_is_not_swallowed_into_an_empty_result() -> None:
    # "Nothing relevant" and "the database is down" must not look alike to a
    # caller: one is an answer, the other is a reason to stop.
    class FailingStore(FakeStore):
        def search(self, query: str, tenant_id: str, limit: int = 5) -> list[Match]:
            raise RuntimeError("vector database unreachable")

    with pytest.raises(ToolError, match="vector database unreachable"):
        await call(
            server(FailingStore()),
            "search_records",
            {"query": "x", "tenant_id": TENANT},
        )
