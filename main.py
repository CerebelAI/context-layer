"""Composition root for the context layer.

The intended end-to-end flow, once the three modules have something in them:

    a trigger fires -- for now a person running this file, later a schedule or a
    request arriving at the MCP server

        connectors     connects to Notion / Slack / Gmail and pulls raw records

        knowledge      ingests those records, extracts facts and processes out of
                       them, and puts the result in the store

        server         exposes that store over MCP, for read and for write

This file is the only place that knows about all three. It constructs the concrete
pieces -- connectors, store, server -- and hands them to each other, so that nothing
below has to reach sideways or upwards to find its dependencies.
"""


def main() -> None:
    pass


if __name__ == "__main__":
    main()
