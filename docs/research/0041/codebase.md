# Codebase grounding: `connectors/notion.py` and its constraints

Read from the working tree of `main` at `/Users/wimthomzik/dev/context-layer-mvp` (not this
branch's checkout of `connectors/notion.py`, which is a snapshot of `main`'s last commit,
`7c4e750`) — that working tree carries uncommitted edits to `connectors/notion.py`,
`pyproject.toml` and `tests/test_notion.py`. Every line number below is from that live file, not
from `git show` on any commit or branch.

## A. `connectors/notion.py`, function by function (406 lines total)

| lines | function | what it owns |
|---|---|---|
| 12–36 | module constants | `API_BASE`, pinned `API_VERSION = "2026-03-11"`, `PAGE_SIZE = 100`, `REQUEST_TIMEOUT_SECONDS = 30.0`, `RETRYABLE_STATUSES = {429, 529}`, `MAX_ATTEMPTS = 5`, `FALLBACK_RETRY_SECONDS`, `MAX_RETRY_SECONDS`, `DELAY_SECONDS` regex, `RECORD_BOUNDARY_BLOCKS = {"child_page", "child_database"}`, `MAX_BLOCK_DEPTH = 50` |
| 53–70 | `notion_client(api_key)` | builds the `httpx.AsyncClient`: base URL, `Authorization`, `Notion-Version` header, `Content-Type`, 30s timeout |
| 73–135 | `pull_notion(client, *, sleep)` | orchestrates: one `_search(in_trash=False)` pass + block walk per page, then a second `_search(in_trash=True)` pass merged in by `result["id"]` so no id emits two envelopes |
| 138–155 | `_search(client, sleep, *, in_trash)` | `POST /search`, cursor loop (1st of 2 pagination loops), builds the trash-filter body |
| 158–172 | `_children(client, sleep, block_id)` | `GET /blocks/{id}/children`, cursor loop (2nd of 2 pagination loops) |
| 175–183 | `_next_cursor(payload, path)` | shared cursor-vs-`has_more` guard, used by both loops above |
| 186–198 | `_blocks_of(client, sleep, result)` | decides whether a result gets walked at all (skips non-pages and database rows/`data_source_id` parents), catches `_RecordGone` from a page trashed mid-walk |
| 200–227 | `_walk(client, sleep, block_id, depth=0)` | recursive block-tree descent; depth bound (`MAX_BLOCK_DEPTH`) against synced-block cycles; `child_page`/`child_database` boundary so a subpage isn't copied into every ancestor |
| 230–266 | `_request(client, sleep, method, path, *, json, params)` | the retry loop itself: up to `MAX_ATTEMPTS` (5), retries on `RETRYABLE_STATUSES`, treats a non-2xx/3xx as fatal (404 → `_RecordGone`, else `NotionError`), guards a 200 that isn't JSON |
| 269–278 | `_retry_after(response)` | turns a parsed wait into a bounded delay (`FALLBACK_RETRY_SECONDS` if absent, capped at `MAX_RETRY_SECONDS`) |
| 281–294 | `_advertised_wait(header)` | parses `Retry-After` in both RFC 9110 spellings (seconds via `DELAY_SECONDS`, HTTP-date via `parsedate_tz`/`mktime_tz`) |
| 297–406 | `_envelope`, `_text`, `_lines_of`, `_extended`, `_title`, `_title_runs`, `_parent_id` | shaping a Notion result + walked blocks into an `Envelope` — this half is product logic (what a record *means*), not transport, and is out of scope for #41 (it's #42's ~110 lines) |

**Lines 53–294 (`notion_client` through `_advertised_wait`) are the transport/traversal surface
the ticket names** — base client, retry/backoff, both pagination loops, the recursive walk, the
trash pass. That is 242 lines including blank lines and comments; the ticket's own count ("roughly
230") matches within the range you'd get by counting differently (e.g. excluding the module
docstring-heavy `pull_notion` body at 73–135, whose orchestration logic — the merge-by-id, the
"trashed wins" comment — is product logic, not mechanics, even though it calls the mechanical
functions).

### A.1 The pinned version and why

`API_VERSION = "2026-03-11"` (`connectors/notion.py:16`), with the comment: *"Pinned
deliberately. Notion reshapes responses between versions -- what a data source is, where a row's
parent points -- so the version this connector was written and captured against is the one it
keeps asking for."* This is the exact version Notion's own upgrade-guide page for `2026-03-11`
documents (see [prior-art.md](prior-art.md) §5) — the release that renamed `archived` to
`in_trash` and introduced the `data_source` object this connector's `_title`/`_parent_id`
branch on (`connectors/notion.py:370`, `:399`).

### A.2 The trash pass, concretely

`pull_notion` (`:121–135`) runs `_search(..., in_trash=False)` then `_search(..., in_trash=True)`,
merging by `result["id"]` into one dict so a record trashed between the two passes — returned by
both — still yields exactly one envelope, keeping the walked body from the first pass (comment at
`:125–131`). No candidate that only exposes a single `search()` call replicates this merge
without the connector writing it again on top.

### A.3 The recursion bound, concretely

`_walk` (`:200–227`) recurses with a `depth` parameter, raising `NotionError` at `MAX_BLOCK_DEPTH
= 50` (`:36`, comment: *"Far past anything a person nests by hand ... and far short of the
stack. It is a bound, not a budget."*) — this exists specifically because a synced block's
children come back under the id of the block it mirrors, so a page mirroring one of its own
ancestors is a cycle nothing in the response marks as one (`:203–206`). It also stops recursing at
`child_page`/`child_database` (`RECORD_BOUNDARY_BLOCKS`, `:32`) because those name another record
rather than holding content of their own — descending into them would copy every subpage and every
database row into each of its ancestors as well as storing it once.

### A.4 Retry shape, concretely

`_request` (`:230–266`): 5 attempts, retries on `{429, 529}` only, does not retry on `500`/`503`
(no idempotency reasoning is written down — this connector retries a narrower set than
`notion-client` does by default, see [prior-art.md](prior-art.md) §2.3), and distinguishes a 404
into `_RecordGone` (`:47–50`) so a block walk can tell "this record was trashed under me" from
every other failure. `_retry_after`/`_advertised_wait` (`:269–294`) parse both RFC 9110 spellings
of `Retry-After` and cap the wait at `MAX_RETRY_SECONDS = 60.0`.

## B. `pyproject.toml` (working tree, with uncommitted edits)

```toml
[project]
name = "context-layer"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "httpx>=0.28.1",
    "mcp>=2.0.0",
    "pydantic>=2.13.4",
    "python-dotenv>=1.2.2",
    "qdrant-client[fastembed]>=1.19.0",
]

[dependency-groups]
dev = [
    "mypy>=2.3.0",
    "pytest>=9.1.1",
    "ruff>=0.16.1",
]

[tool.mypy]
strict = true
files = ["."]
exclude = ["^temp/"]          # uncommitted addition

[tool.pytest.ini_options]
pythonpath = ["."]
norecursedirs = ["temp"]      # uncommitted addition

[tool.ruff]
extend-exclude = ["temp"]     # uncommitted addition (new section)
```

Load-bearing for this ticket:

- **`requires-python = ">=3.13"`** — a candidate targeting an older Python floor is fine (nothing
  here forbids 3.13 running an older-targeted package), but a candidate whose *stubs* lag current
  typing syntax is a real risk under `mypy --strict`.
- **`httpx>=0.28.1` is already a direct dependency**, used for `notion_client`'s `AsyncClient`
  (`connectors/notion.py:8, 61`) and by `knowledge`/tests elsewhere. Any candidate built on `httpx`
  rather than `requests` or its own transport adds no new HTTP stack to reason about; one built on
  `requests` adds a second one.
- **`[tool.mypy] strict = true` with `files = ["."]`** — every file under the repo root is
  strict-checked *except* `temp/` (excluded by the uncommitted edit above, with the comment
  explaining scratch tooling is deliberately held to no bar at all). A new dependency under
  `connectors/` does not get a mypy exclusion for free; it type-checks under strict or ships
  stubs, exactly as the ticket's bar says.
- **`temp/` is excluded from mypy, ruff and pytest identically** (see `temp/README.md`,
  quoted in the `pyproject.toml` comment above) — this is the project's own precedent for
  "not held to the bar" tooling, useful context for judging whether a throwaway spike belongs in
  `connectors/` or in `temp/`.
- No dependency group yet exists for connector-only extras — `dependencies` is one flat list, so
  adding a Notion library means adding it to the main `dependencies` array (it ships in the same
  wheel as everything else; no optional-extras mechanism is set up to isolate it).

## C. Relevant ADRs

### ADR-0001 — Envelope is the connector/knowledge contract
`docs/adr/0001-envelope-is-the-connector-contract.md`. `data` must be the vendor payload
**exactly as the platform returned it**, append-only, and a connector "may add keys where one
call does not return a whole record, but must name each added key in its own docstring and fail
rather than overwrite if the platform starts sending that key itself." This is precisely what
`_extended` (`connectors/notion.py:358–366`) enforces for the `"blocks"` key `_walk` adds. **Any
candidate that returns its own parsed/normalised object instead of the raw block JSON breaks this
ADR outright** — `data` would no longer be Notion's payload, it would be the library's
reinterpretation of it, and nothing downstream (`knowledge`, the MCP `data` field) could
distinguish "what Notion sent" from "what the library decided that meant." See
[prior-art.md](prior-art.md) §4 for which candidates return raw JSON vs. their own object model.

### ADR-0002 — Connectors persist nothing
Not implicated by any candidate here — none of the shortlisted libraries impose a required
destination/cache by themselves except `dlt` (see §D below), which is the one that would violate
this ADR outright.

### ADR-0003 — Connectors are read-only
Not implicated — none of the candidates are being considered for write-back.

### ADR-0004 — One-directional module imports
Not implicated by transport choice; whatever library lands still sits entirely inside
`connectors/notion.py` or a new `connectors/` submodule, importing nothing from `knowledge` or
`server`.

### ADR-0007 — Full re-pull, no incremental sync (accepted)
States the trash pass **is** the reconciliation mechanism today and is expected to be *permanent*,
not a stopgap: *"reconciliation is a permanent code path for Notion, and is the one that exists —
the second pass over the trash in `connectors/notion.py`."* It also records the measured cost:
*"today's Notion pull is roughly 90 sequential requests against a seeded workspace with no
concurrency; fixing database-row bodies (#5) takes it to roughly 270,"* against Notion's ~3
req/s/connection limit. **A candidate that cannot see trashed records at all — not "leaves us a
way to," but structurally cannot — would force reopening this ADR's reconciliation story, which is
exactly the kind of deferred decision the ticket says a candidate must not force.**

### ADR-0008 — Adapters declare their sync guarantees (status: proposed, nothing built)
Explicitly *parked*: *"Deliberately not built yet, because the project's own rule is no base
classes until there are at least two concrete cases demanding them."* Its capability table already
records Notion's row as *"detects deletes incrementally: webhooks only,"* i.e. polling-based trash
detection (what `connectors/notion.py` does today) is the *documented* fallback, not a gap ADR-0008
is waiting to close. **A transport candidate is not what would settle ADR-0008** — that ADR is
about a cross-connector scheduling abstraction above individual adapters, which is explicitly
deferred until Slack exists (ADR-0009) — so nothing in this ticket's shortlist should be read as
answering it. Noted here only because the wayfinder map (#40) flags ADR-0007/0008 as the decisions
most likely to be contradicted by an answer in this map, and the honest read is: *not by this one.*

## D. One constraint from `docs/credentials.md` worth naming

*"Never invent sample or demo data to make a pipeline appear to work"* and *"never write a fake,
stubbed, or sample implementation of a connector to work around missing credentials."* Not
directly about library choice, but it rules out one shape of "adopt a platform instead of a
library" answer for connectors specifically — e.g. a SaaS ETL platform's hosted Notion connector
that requires configuring a destination and running through *its* scheduler rather than this
repo's `pull_notion`/`main.py serve` split (`docs/architecture.md` — "Two verbs... lets a pull be
scheduled without restarting the server"). Airbyte's `source-notion` is the concrete case; see
[findings.md](findings.md).
