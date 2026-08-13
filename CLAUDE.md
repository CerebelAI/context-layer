# Context Layer

A context layer in three stages: connectors pull records out of Notion as envelopes, `knowledge`
puts those envelopes in the store, and an MCP server exposes that store to consumers for both read
and write.

Status: pre-MVP. The goal is a Notion-only demo we can drive ourselves — good enough to show a
prospect and open a conversation about what they actually need.

## Commands

- Run: `uv run main.py pull` · `uv run main.py serve`
- Test: `uv run pytest` — single test: `uv run pytest path/to/test_x.py::test_name`
- Typecheck: `uv run mypy .` — lint: `uv run ruff check --fix .` — format: `uv run ruff format .`
- Add a dependency: `uv add <pkg>` — never `pip install`

## Detail

- [Language](CONTEXT.md) — the glossary: which word we use for a concept, and which to avoid
- [Decisions](docs/adr/) — the ADRs, and why the code is shaped the way it is
- [Architecture](docs/architecture.md) — the three modules, import direction, where things are written
- [Code style](docs/code-style.md) — async boundaries, exceptions, docstrings, working style
- [Credentials and data](docs/credentials.md) — `.env`, and the ban on fake connectors and invented data
- [Workflow](docs/workflow.md) — branches, commits, the pre-commit gate, TDD

Open questions are GitHub issues, not comments in the code.

## Agent skills

- [Issue tracker](docs/agents/issue-tracker.md) — GitHub issues on `CerebelAI/context-layer`, via `gh`
- [Triage labels](docs/agents/triage-labels.md) — the five canonical roles, unmapped
- [Domain docs](docs/agents/domain.md) — `CONTEXT.md` at the root, ADRs in `docs/adr/`
