from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from connectors import Envelope

# Spelled out again in the test modules that use it -- `tests` is not a package,
# so they cannot import it from here.
MakeEnvelope = Callable[..., Envelope]


# MCP tool handlers are async, so the tests that call them need a loop to run on.
# anyio ships the pytest plugin; this fixture is how it is told which backend.
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_envelope() -> MakeEnvelope:
    def factory(**overrides: Any) -> Envelope:
        fields: dict[str, Any] = {
            "source": "notion",
            "source_id": "59833787-2cf9-4fdf-8782-e53db20768a5",
            "url": "https://www.notion.so/Onboarding-598337872cf9",
            "title": "Onboarding checklist",
            "text": "New engineers get a laptop on day one.",
            "parent_id": None,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "last_modified": datetime(2026, 2, 1, tzinfo=UTC),
            "is_deleted": False,
            "data": {"object": "page", "properties": {"Owner": "platform team"}},
        }
        return Envelope(**{**fields, **overrides})

    return factory
