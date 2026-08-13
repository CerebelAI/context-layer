# Architecture

Three top-level modules, mirroring the pipeline: `connectors/`, `knowledge/`, `server/`. What each
one owns is stated in its `__init__.py`.

The seam between the store and its consumers is four MCP tools: `ingest_records`,
`search_records`, `get_record`, `delete_record`. What each one does is in its docstring —
`server/__init__.py` states that the tool docstrings are the API.

## Module boundaries

- Imports flow in one direction only: `server` → `knowledge` → `connectors`. Never backwards.
- Cross-module imports go through the module's `__init__.py` only. Never reach into internals.
- This applies recursively. Submodules follow the same rule: few, large, one-directional, public
  interface only.
- Complexity goes DOWN into submodules, never OUT into new top-level modules.
- Adding a top-level module is a decision to discuss. Never do it unprompted.
- Do not create a file or module to hold a single function.

## Two verbs

Two verbs, because the flow has two ends and they run on different clocks. Keeping them apart is
what lets a pull be scheduled without restarting the server, and lets the server start when Notion
is down. Both build the same store, which is the only thing they share.

## Where things are written down

One home per fact — the split by kind says which home. `docs/` owns reasoning and decisions, and
is read once at the start of a session. Docstrings own mechanics, and are read by the agent
editing that function. The two are read by different readers wanting different things, which is
why the line falls between kinds of fact rather than between files.

- **[CONTEXT.md](../CONTEXT.md)** — the vocabulary. Which word we use for a concept, and which words
  to avoid. A glossary, nothing more.
- **[docs/adr/](adr/)** — the decisions, and why. If you need to know why the code is shaped the way
  it is, it is here or it is nowhere.
- **GitHub issues** — the open questions. Anything deliberately undecided is an issue, not a comment.
- **Docstrings** — how the code works. They explain mechanics, not reasoning. Where a decision is
  load-bearing, cite the ADR (`see ADR-0002`) rather than restating it.

IMPORTANT: if a task requires settling something an ADR leaves open or an issue is tracking, stop and
ask. Do not pick a default silently. Keep persistence behind a thin interface so it stays
swappable.

If your work contradicts an ADR, say so explicitly rather than silently overriding it — *contradicts
ADR-0007, but worth reopening because…* — and amend the ADR as part of the change.
