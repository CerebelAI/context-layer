# Workflow

- Commit to `main`. Branch when a change is big enough to want a review surface.
- Commit your own work as you go, in small steps, and open the pull request when the branch is
  ready. We review there.
- IMPORTANT: before any commit, all three must pass:
  `uv run pytest`, `uv run mypy .`, `uv run ruff check .`
- Test-driven by default: write the failing test first, then the code that passes it.
- Write code to be testable — dependencies passed in, not constructed inside.
- `CLAUDE.md` and everything under `docs/` is shared with the other maintainer. Propose an edit to
  them rather than applying it silently — machine-local auto memory does not reach the other person.
