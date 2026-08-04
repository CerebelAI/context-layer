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
"""


def main() -> None:
    pass


if __name__ == "__main__":
    main()
