"""Composition root for the context layer.

The intended end-to-end flow, once the three modules have something in them:

    a trigger fires -- for now a person running this file, later a schedule or a
    request arriving at the MCP server

        connectors     connects to Notion / Slack / Gmail and pulls raw records,
                       returning each one as an `Envelope`

        knowledge      ingests those envelopes, extracts facts and processes out
                       of them, and puts the result in the store

        server         exposes that store over MCP, for read and for write

The `Envelope` is the seam: it is the only form in which `knowledge` accepts a
record, so nothing platform-shaped gets through. Connectors are not the only
producer -- the MCP write side hands envelopes in too.

Two directions run across that seam and they are not the same direction. Imports run
down the chain `server` -> `knowledge` -> `connectors` and never back up it; each
module's docstring states its own position on it.

Calls start here. This file triggers the pull: it asks `connectors` to fetch,
receives the envelopes back, and passes them into `knowledge`. `knowledge` never
constructs a connector and never triggers a pull -- it imports the `Envelope` type,
but it does not call the module that defines it. Envelopes arrive already pulled,
handed in from here.

Being the only place that knows all three, this file constructs the concrete pieces
-- connectors, store, server -- and hands them to each other, so nothing below has
to reach sideways or upwards to find its dependencies.

Two verbs, because the flow has two ends and they run on different clocks:

    uv run main.py pull     one pass over Notion into the store, then exits
    uv run main.py serve    the MCP server, until stopped

Keeping them apart is what lets a pull be scheduled without restarting the server,
and lets the server start when Notion is down. Both build the same store, which is
the only thing they share.

`knowledge` still does no extraction, so `pull` puts envelopes in the store whole.
The stage is real; what happens inside it is not built yet.
"""

import argparse
import asyncio
import os
from collections import Counter
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from connectors import Envelope, notion_client, pull_notion
from knowledge import Store
from server import build_server

# Long enough that a title stays recognisable, short enough that a record stays on
# one line of a terminal.
TITLE_WIDTH = 40


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("pull", help="pull Notion into the store, then exit")
    verbs.add_parser("serve", help="run the MCP server over the store")
    verb = parser.parse_args().verb

    # The library code never loads the environment, so the entrypoint does.
    load_dotenv()
    store = _store()

    if verb == "pull":
        _pull_into(store)
    else:
        build_server(store).run()  # stdio transport by default


def _store() -> Store:
    client = QdrantClient(
        url=_required("QDRANT_CLUSTER_URL"), api_key=_required("QDRANT_API_KEY")
    )
    store = Store(client, _required("QDRANT_COLLECTION_NAME"))
    store.ensure_collection()
    return store


def _required(name: str) -> str:
    """Read an environment variable, refusing to start without it.

    A missing URL or key would otherwise reach the Qdrant client as `None` and
    fail later as a connection error that says nothing about the real cause.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env (see .env.example)")
    return value


def _pull_into(store: Store) -> None:
    tenant_id = _required("COMPANY_TENANT_ID")
    # Only a missing key is worth a word here. A wrong one fails at Notion, whose
    # own message about it says more than anything we could check for.
    api_key = _required("NOTION_API_KEY")

    envelopes = asyncio.run(_pull(api_key))
    for envelope in envelopes:
        print(_summary(envelope))
    _print_tally(envelopes)

    # Every envelope, including the deleted ones: the store has to be told a record
    # is gone, and a pull that quietly dropped them would leave the last live copy
    # answering questions forever.
    written = store.upsert(envelopes, tenant_id=tenant_id)
    print(f"\nstored {written} records under tenant {tenant_id!r}")


async def _pull(api_key: str) -> list[Envelope]:
    # The client is the caller's to own and close, and the caller is this file.
    async with notion_client(api_key) as client:
        return await pull_notion(client)


def _summary(envelope: Envelope) -> str:
    return "  ".join(
        (
            envelope.source,
            f"{_kind(envelope):<11}",
            f"{_body(envelope):>10}",
            f"{_words(envelope):>9}",
            envelope.last_modified.isoformat(timespec="minutes"),
            "DELETED" if envelope.is_deleted else "live   ",
            f"{_title(envelope.title):<{TITLE_WIDTH}}",
            f"parent {envelope.parent_id or '(workspace root)'}",
        )
    )


def _kind(envelope: Envelope) -> str:
    obj: str = envelope.data["object"]
    if obj != "page":
        return obj
    # A row is a page like any other to Notion and only its parent says otherwise.
    # Worth separating out because a row is the kind whose body is not walked.
    return "row" if envelope.data["parent"]["type"] == "data_source_id" else "page"


def _body(envelope: Envelope) -> str:
    # A record with no `blocks` key was never walked; one with an empty list was
    # walked and found empty. Different facts, and a single count would hide it.
    if "blocks" not in envelope.data:
        return "no body"
    blocks: list[Any] = envelope.data["blocks"]
    return f"{len(blocks)} blocks"


def _words(envelope: Envelope) -> str:
    # What the record is actually findable by. A page with blocks but no words is
    # a page that will only ever be found by its title, and that is worth seeing
    # in the run rather than discovering through a search that returns nothing.
    if envelope.text is None:
        return "no words"
    return f"{len(envelope.text.split())} words"


def _title(title: str | None) -> str:
    # Notion round-trips a title byte for byte -- a literal newline, 250
    # characters, whitespace only -- and none of those survive a column.
    collapsed = " ".join(title.split()) if title else ""
    if not collapsed:
        return "(no title)"
    if len(collapsed) > TITLE_WIDTH:
        return collapsed[: TITLE_WIDTH - 1] + "…"
    return collapsed


def _print_tally(envelopes: list[Envelope]) -> None:
    bodied = [envelope for envelope in envelopes if "blocks" in envelope.data]
    empty = sum(1 for envelope in bodied if not envelope.data["blocks"])
    deleted = sum(1 for envelope in envelopes if envelope.is_deleted)
    wordless = sum(1 for envelope in envelopes if envelope.text is None)
    kinds = Counter(_kind(envelope) for envelope in envelopes)
    print()
    print(f"{len(envelopes)} envelopes, {deleted} of them deleted")
    print(f"{len(bodied)} walked for a body, {empty} of those empty")
    print(f"{len(envelopes) - len(bodied)} not walked at all")
    # Searchable by title alone, which for an untitled record means not at all.
    print(f"{wordless} carry no text to embed")
    print(", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items())))


if __name__ == "__main__":
    main()
