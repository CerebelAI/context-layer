# Prior art: candidate Notion transport libraries

Primary-source research for issue #41. Every claim below carries a URL. Research date:
2026-08-18.

---

## 1. `notion-client` (PyPI name) / `notion-sdk-py` (GitHub repo), maintained by ramnes

- PyPI: <https://pypi.org/project/notion-client/> — current version **3.1.0**, released
  2026-05-12. Python support **3.8–3.14**. Depends on `httpx>=0.23.0`.
- GitHub: <https://github.com/ramnes/notion-sdk-py> — README: *"Notion API client SDK, rewritten
  in Python! (sync + async)"*, *"a Python version of the reference JavaScript SDK, so usage should
  be very similar between both."* MIT license. No claim of official Notion endorsement anywhere in
  the README; issues/feature requests are routed to `developers@makenotion.com` but the project
  itself is community-maintained.
- **Version pinning**: `notion_client/client.py`, `BaseClient` — the header is set from
  `self.options.notion_version`, default `"2025-09-03"`, and is a constructor parameter on both
  `Client` and `AsyncClient` via `ClientOptions`. So it is **overridable to `"2026-03-11"`**, this
  repo's pin — it does not force a different version, it just needs the value passed explicitly
  since its own default trails ours.
- **Retry/backoff**: `RetryOptions` dataclass — `max_retries`, `initial_retry_delay_ms`,
  `max_retry_delay_ms`. `_can_retry()`: 429 is always retryable; 500/503 retried only for
  idempotent methods (GET, DELETE). `_calculate_retry_delay()` does exponential backoff with full
  jitter. `_parse_retry_after_header()` parses both delta-seconds and HTTP-date `Retry-After`
  forms, source: <https://github.com/ramnes/notion-sdk-py/blob/main/notion_client/client.py>. This
  is a superset of what `connectors/notion.py:269–294` does by hand (same two `Retry-After`
  spellings, plus jitter this repo's own retry does not have) but retries **529** too, which
  `notion-sdk-py`'s hardcoded set does not — 529 is not a status Notion's docs mention and appears
  to be this repo's own defensive addition (`connectors/notion.py:20` comment does not explain the
  choice further). A candidate adopting this library would need to confirm 529 doesn't need
  separate handling, or wrap it.
- **Pagination**: `notion_client/helpers.py` — `iterate_paginated_api()`,
  `collect_paginated_api()`, and async variants `async_iterate_paginated_api()`,
  `async_collect_paginated_api()`. Docstring: *"Return an iterator over the results of any
  paginated Notion API."* Generic over any paginated endpoint — the same one function collapses
  both of this repo's hand-written cursor loops (`_search`, `_children`,
  `connectors/notion.py:138–172`). Source:
  <https://github.com/ramnes/notion-sdk-py/blob/main/notion_client/helpers.py>.
- **Recursive block-children fetching**: **not present**. No helper walks `has_children` /
  descends into nested blocks — `collect_paginated_api(client.blocks.children.list, ...)` still
  only returns one level; the caller has to recurse itself, exactly as `_walk`
  (`connectors/notion.py:200–227`) does today.
- **Trash visibility**: the PyPI changelog entry surfaced via search states version **2.3.0**
  "adds support for pages in trash" (search result, PyPI page
  <https://pypi.org/project/notion-client/0.9.0/> region and general PyPI history). The
  `Search` endpoint (`notion_client/api_endpoints.py`, `SearchEndpoint.__call__`) passes
  `filter`, `sort`, `query`, `start_cursor`, `page_size` straight through as `**kwargs`
  (`pick(kwargs, "query", "sort", "filter", "start_cursor", "page_size")`,
  <https://github.com/ramnes/notion-sdk-py/blob/main/notion_client/api_endpoints.py>) — so
  `filter={"in_trash": True}`, exactly what `_search(..., in_trash=True)`
  (`connectors/notion.py:145–146`) builds, passes through unmodified. The library does not run the
  two-pass merge-by-id `pull_notion` does (`:121–135`) — that orchestration logic stays ours either
  way.
- **Type stubs**: confirmed via the GitHub API file listing of `notion_client/` — a `py.typed`
  marker file is present alongside `client.py`, `helpers.py`, `typing.py`, `webhooks.py`
  (fetched programmatically from
  `https://api.github.com/repos/ramnes/notion-sdk-py/contents/notion_client`, 2026-08-18). PEP
  561 compliant, so `mypy --strict` reads its own annotations rather than needing a stub package.

## 2. `ultimate-notion`

- PyPI: <https://pypi.org/project/ultimate-notion/> — version **0.10.1**, released 2026-06-28.
  *"A high-level Python client for the Notion API"*, built **on top of `notion-sdk-py`**, Python
  **3.10–3.14**. MIT license. Badges show mypy integration ("Types - Mypy").
- Docs: <https://ultimate-notion.com/latest/usage/getting_started/>.
- **Execution model**: synchronous — the documented usage (`notion.search_page()`, context
  managers) is blocking, wrapping `notion-sdk-py`'s sync `Client` rather than its `AsyncClient`.
- **Recursive block fetching**: **explicitly does not**. Source
  (`https://raw.githubusercontent.com/ultimate-notion/ultimate-notion/main/src/ultimate_notion/page.py`,
  fetched 2026-08-18), `Page.to_markdown()` docstring states verbatim: *"This will not include
  nested blocks, i.e. the children of top-level blocks."* The `subpages` property only filters
  immediate `children`, no recursive descent. A caller would have to write the recursive walk
  itself on top of this library — the exact code the ticket wants deleted.
- **Trash visibility**: no first-class query surface found for `in_trash`; a 2026-08-18 web search
  turned up the adjacent JS-SDK issue **makenotion/notion-sdk-js#524**, *"No way to query
  archived/in_trash items"* — a JS-SDK-side gap, not evidence about `ultimate-notion` specifically,
  but no `ultimate-notion` documentation surfaced a trash-aware search method either.

## 3. `notional`

- GitHub: <https://github.com/jheddings/notional> — **archived 2024-10-26, read-only.**
  Maintainer's note, quoted verbatim from the repo: *"⚠️ Discontinued: I have moved away from
  Notion to Obsidian and will no longer update this project."* The same note recommends
  `ultimate-notion` as the successor, which reused some of `notional`'s code.
- PyPI: <https://pypi.org/project/notional/> — last release **0.8.2**, requires Python
  **≥3.8.1**, MIT license, built on `notion-sdk-py`.
- **Ruled out on maintenance status alone** — a discontinued project is not something to adopt
  pre-MVP regardless of its feature fit, and its own maintainer's stated replacement
  (`ultimate-notion`) is independently in this shortlist and does no better on recursion (§2).

## 4. `dlt`'s Notion verified source

- Docs: <https://dlthub.com/docs/dlt-ecosystem/verified-sources/notion>.
- Source: `sources/notion/__init__.py` and `sources/notion/helpers/client.py` in
  <https://github.com/dlt-hub/verified-sources> (raw content fetched 2026-08-18).
- **What it fetches**: `notion_databases()` yields database rows via `NotionDatabase.query()`;
  `notion_pages()` fetches page blocks via `client.fetch_resource("blocks", page["id"],
  "children")` and yields them **if present, but only that one call** — no recursive descent into
  child blocks was found in either file. The docstring content fetched describes it as
  database-row-oriented, consistent with `dlt`'s general framing as an ELT tool moving rows into a
  destination warehouse.
- **`NotionClient` (`helpers/client.py`)**: implements cursor-based pagination in `search()`
  (loops on `has_more`/`next_cursor`), but calls `response.raise_for_status()` with **no retry
  logic, no backoff, no `Retry-After` handling** found in the fetched source. No method targets
  `blocks/{id}/children` on the client class itself (block fetching goes through a generic
  `fetch_resource()` in the pipeline module instead, called once, not recursively).
  `search(filter_criteria=...)` exists but no trash/archive-specific handling was found; the
  README text fetched describes coverage as pages "shared with an integration," not trash.
- **Deployment shape**: requires a `dlt`-supported destination (DuckDB, BigQuery, Databricks, S3,
  etc.) per the docs page, and is designed to be run as a `dlt` pipeline (`pip install -r
  requirements.txt`, then a pipeline script) rather than imported as a plain async function
  returning records to a caller. **This is the direct conflict with ADR-0002 ("connectors persist
  nothing")** — `dlt`'s whole model is extract-and-load into *its own* destination, which this repo
  would then have to read back out of before handing envelopes to `knowledge`, i.e. a second store
  ADR-0002 forbids, not a transport library.
- **Fails the recursion bar outright**: one level of block children, no walk, no depth guard —
  the ticket's second requirement ("fetch a page's block children recursively, not just top
  level") is unmet on the evidence read.

## 5. Airbyte `source-notion`

- Repo path: <https://github.com/airbytehq/airbyte/tree/master/airbyte-integrations/connectors/source-notion>
  — file listing fetched 2026-08-18 via GitHub API: `manifest.yaml`, `components.py`,
  `acceptance-test-config.yml`, `metadata.yaml`, `integration_tests/`, `unit_tests/`. No
  `client.py`/`source.py` implementing raw HTTP calls — **this connector is now a declarative
  low-code manifest** (Airbyte's Connector Builder / low-code CDK format), not a hand-written
  Python client.
- Docs referenced from the repo: Airbyte's Low-Code CDK and "Developing Connectors Locally" pages
  frame this as built and run **inside the Airbyte platform** — either Airbyte Cloud or a
  self-hosted Airbyte instance (Docker/Kubernetes), invoked through Airbyte's sync scheduling and
  writing to an Airbyte-configured destination, not importable as a standalone Python function.
- **This is the clearest "forces hosting" candidate on the list.** Adopting it means standing up
  or paying for the Airbyte platform (a new piece of infrastructure with its own scheduler,
  destination-writing model, and operational surface) to replace ~230 lines run in-process today —
  directly contradicting the pre-MVP, one-dev, "no candidate that forces a decision we're
  deliberately deferring" bar, and specifically the "hosting" disqualifier the wayfinder map (#40)
  names in its Fog section.

## 6. LlamaIndex `NotionPageReader`

- Docs: <https://developers.llamaindex.ai/python/framework-api-reference/readers/notion/>
  (canonical docs.llamaindex.ai URL 301-redirects here as of 2026-08-18).
- Source:
  `llama-index-integrations/readers/llama-index-readers-notion/llama_index/readers/notion/base.py`
  in <https://github.com/run-llama/llama_index> (raw content fetched 2026-08-18). Class docstring:
  *"Notion Page reader. Reads a set of Notion pages."*
- Packaging: the lightweight `llama-index-readers-notion` package (not the full `llama-index`
  meta-package) — extends `BasePydanticReader` from `llama_index.core.readers.base`.
- **Recursive block fetching**: **yes** — `_read_block()` calls itself for nested content:
  `children_text = self._read_block(result_block_id, num_tabs=num_tabs + 1)` whenever a block's
  `has_children` is true, building an indented text tree. This is the only shortlisted candidate
  besides the code we already have that actually recurses.
- **Pagination**: yes, both in `_read_block()` (loops on `next_cursor`) and `query_database()`
  (loops on `has_more`/`next_cursor`).
- **Retries**: `_request_with_retry()` checks for HTTP 429 specifically and reads
  `response.headers.get('Retry-After', 1)` — a real but noticeably thinner implementation than
  `connectors/notion.py`'s (`connectors/notion.py:269–294`): one status code, no `MAX_ATTEMPTS`
  cap visible in the fetched excerpt, no HTTP-date `Retry-After` form handled, no distinct handling
  of a 404-mid-walk (`_RecordGone`'s whole reason for existing, `connectors/notion.py:47–50`).
- **Sync/async**: **synchronous only** — built on `requests`, no `httpx`/`aiohttp`/`asyncio` found
  in the fetched source.
- **Trash/archive visibility**: **no filtering logic found** — the reader walks whatever `search()`
  or an explicit page-id list returns; no `in_trash` handling.
- **Architecture mismatch with ADR-0001**: `_read_block()`'s output is already flattened,
  indented **text**, not the raw block JSON tree — the reader's job is producing LlamaIndex
  `Document` objects (text + metadata) for retrieval, not preserving Notion's payload shape. This
  repo's `Envelope.data` is required to be *"the vendor payload, exactly as the platform
  returned it"* (ADR-0001) with `text` derived *separately* — see
  [codebase.md](codebase.md) §C. Reusing this reader for `data` would mean reconstructing the raw
  block tree from indented text, or running the reader for `text` while still writing the walk by
  hand for `data`, which keeps most of `_walk` alive anyway.

## 7. Considered and not deep-dived: other Notion Python packages seen during search

- **`notion-py` (jamalex)** — <https://github.com/jamalex/notion-py> — README states *"Unofficial
  Python API client for Notion.so."* Predates Notion's public API (reverse-engineered against the
  private one); the public API this repo targets makes it a different generation of tool. Not
  investigated further.
- **`getsyncr/notion-sdk`** — surfaced once in search results as *"A simple and easy to use Python
  client for the Notion API,"* no independent verification of maintenance status, recursion, or
  trash support attempted; far lower visibility (stars/activity) than `notion-client` in search
  results, and duplicates what `notion-client` already covers on the surface. Not pursued given
  diminishing returns against the ticket's named shortlist.

## 8. Notion's own API — the fact the pin is checked against

- Notion's upgrade guide for the version this connector is pinned to:
  <https://developers.notion.com/guides/get-started/upgrade-guide-2026-03-11> — surfaced in a
  2026-08-18 web search, title matching `API_VERSION = "2026-03-11"`
  (`connectors/notion.py:16`) exactly.
- The same search surfaced, from Notion's own docs indexed content: *"The archived field has been
  renamed to in_trash across all API responses and request parameters for pages, databases,
  blocks, and data sources. The archived field was deprecated in April 2024."* — confirms
  `result["in_trash"]` (`connectors/notion.py:311`) and the `filter: {"in_trash": True}` search
  body (`connectors/notion.py:146`) are reading/writing the current, non-deprecated field name.
