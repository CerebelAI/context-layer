# Context Layer

A context layer in three stages: connectors pull data from platforms (Notion, Slack, Gmail),
that data is processed into structured facts and processes, and an MCP server exposes the
resulting store to consumers for both read and write.

Status: pre-MVP. The goal is a deployed, demoable system we develop together with customers.

## Commands

- Run: `uv run main.py`
- Test: `uv run pytest`
- Single test: `uv run pytest path/to/test_x.py::test_name`
- Typecheck: `uv run mypy .`
- Lint: `uv run ruff check --fix .`
- Format: `uv run ruff format .`
- Add a dependency: `uv add <pkg>` — never `pip install`

## Module structure

- Three top-level modules, mirroring the pipeline:
  - `connectors/` — platform connectors, raw pull, landing raw data
  - `knowledge/` — extraction into facts and processes, and the store
  - `server/` — the MCP server (read and write)
- Imports flow in one direction only: `server` → `knowledge` → `connectors`. Never backwards.
- Cross-module imports go through the module's `__init__.py` only. Never reach into internals.
- This applies recursively. Submodules follow the same rule: few, large, one-directional,
  public interface only.
- Complexity goes DOWN into submodules, never OUT into new top-level modules.
- Adding a top-level module is a decision to discuss. Never do it unprompted.
- Do not create a file or module to hold a single function.

## Code style

- Async at I/O boundaries: connectors and the MCP server are `async`.
- Everything else is plain sync — extraction, transformation, business logic.
  If a function does not await anything, it is not async. Do not mix without discussing.
- Pydantic models for anything crossing a module boundary. Dicts stay internal.
- Custom exception types per module.
- IMPORTANT: never swallow an exception. No bare `except:`, no `except ...: pass`, no
  returning empty results on failure. Fail loudly.
- Docstrings on public interfaces only (whatever `__init__.py` exports). Internals need none.
- Comments explain WHY, never WHAT.

## Credentials

- All credentials live in `.env`. Never hardcode a key. Never commit `.env`.
- IMPORTANT: never write a fake, stubbed, or sample implementation of a connector to work
  around missing credentials. If a credential is missing, STOP and ask for it.
- Never invent sample or demo data to make a pipeline appear to work.
- Test doubles inside `tests/` are the exception and are expected. Tests must not make live
  API calls.

## Workflow

- Feature branches. Never commit directly to `main`.
- Commit your own work as you go, in small steps. We review via pull request.
- IMPORTANT: before any commit, all three must pass:
  `uv run pytest`, `uv run mypy .`, `uv run ruff check .`
- Test-driven by default: write the failing test first, then the code that passes it.
- Write code to be testable — dependencies passed in, not constructed inside.
- Exception: for the connectors in `connectors/`, explore the real API first to learn the actual
  response shape, then write tests that lock that shape before opening the PR. Do not invent
  an expected API response and test against it.
- This file is shared between both of us. If you learn something that belongs here, propose
  the edit rather than applying it silently — auto memory is machine-local and does not reach
  the other person.

## Working style

- This is an MVP. Optimize for something deployed and demoable, not for generality.
- Build the simplest thing that works for the current requirement. No abstraction for a
  second implementation that does not exist yet.
- No config systems, plugin registries, or base classes until there are at least two concrete
  cases demanding them.
- Prefer boring, obvious code. We need to read each other's work quickly.

## Open decisions — STOP and ask

IMPORTANT: the following are deliberately undecided. If a task requires one of them, stop and
ask. Do not pick a default silently.

- Shape of raw storage: whether `connectors/` persists raw pulls or passes through.
  Leaning toward persisting. Not settled.
- Format of stored facts and processes.
- Fact store beyond the current cloud vector database.
- Model provider. OpenRouter is temporary.

Keep persistence and model calls behind a thin interface so these stay swappable.

<!-- Maintainer note: HTML comments are stripped before this file enters context, so notes
     like this one are free. Keep this file under ~200 lines. When a section outgrows that,
     move it to .claude/rules/ with `paths:` frontmatter rather than letting this grow. -->