# Code style

- Async at I/O boundaries: connectors and the MCP server are `async`. Everything else is plain sync.
  If a function does not await anything, it is not async. Do not mix without discussing. See
  [ADR-0005](adr/0005-knowledge-stays-sync.md).
- Pydantic models for anything crossing a module boundary. Dicts stay internal.
- Custom exception types per module.
- IMPORTANT: never swallow an exception. No `except ...: pass`, no returning empty results on
  failure. Fail loudly.
- Docstrings on public interfaces only (whatever `__init__.py` exports). Internals need none.
- Docstrings explain how the code works, not why it was decided that way. Reasoning lives in
  `docs/adr/`; cite it (`see ADR-0002`) rather than restating it.
- Comments explain WHY, never WHAT.

## Working style

- This is an MVP. Optimize for something deployed and demoable, not for generality.
- Build the simplest thing that works for the current requirement. No abstraction for a second
  implementation that does not exist yet.
- No config systems, plugin registries, or base classes until there are at least two concrete cases
  demanding them.
- Prefer boring, obvious code. We need to read each other's work quickly.
