# #41 — Can a library own the Notion API, so we stop maintaining transport?

Research findings. Not a decision, and **not proposed for `main`** — this branch
(`research/notion-transport-library`) is the throwaway capture surface wayfinder asks for.

- [codebase.md](codebase.md) — the current working tree of `connectors/notion.py`, `pyproject.toml`,
  and the ADRs a candidate would touch
- [prior-art.md](prior-art.md) — what each candidate library actually does, cited to PyPI pages,
  GitHub source and official docs

Everything below cites one of those two. Where they disagree with the ticket, the ticket is wrong.

---

## The short answer

**No — nothing on the list beats what we have, and nothing should be adopted before the demo.**

One candidate is genuinely good and worth revisiting afterwards (`notion-client`), but it owns
**about half** of the ~230 lines the ticket hoped to hand over, and the half it owns is the half
that has never caused us a problem. The other five fail on a bar the ticket already set, or on an
ADR the ticket did not anticipate.

The single most useful finding is a correction to the ticket's own framing, below: **the ~230
lines are not one thing.** They are a commodity half and a judgement half, and no library on the
list owns the judgement half.

---

## Two corrections to the ticket's framing

### 1. The ~230 lines split cleanly in two, and only one half is buyable

The ticket lists five bullets as though they were one homogeneous block of "Notion's mechanics."
Read against the current file ([codebase.md §A](codebase.md)), they are two different kinds of
code:

**Commodity — every Notion client has to write this, and several already have:**

| what | where | lines |
|---|---|---|
| base client, auth header, version header, timeout | `notion_client` (`connectors/notion.py:53–70`) | 18 |
| retry loop, 429/529, attempt cap, 200-not-JSON guard | `_request` (`:230–266`) | 37 |
| `Retry-After` in both RFC 9110 spellings, capped | `_retry_after` (`:269–278`), `_advertised_wait` (`:281–294`) | 24 |
| cursor pagination, written twice, plus its guard | loops inside `_search` (`:138–155`) and `_children` (`:158–172`), `_next_cursor` (`:175–183`) | ~44 |

**Judgement — Notion-specific decisions about what a *record* is, which no library on this list
makes for us:**

| what | where | lines |
|---|---|---|
| recursive descent, depth bound against synced-block cycles, `child_page`/`child_database` boundary | `_walk` (`:200–227`) | 28 |
| which results get walked at all; the mid-walk-trashed catch | `_blocks_of` (`:186–198`) | 13 |
| the two-pass trash merge by id, so no two envelopes share an upsert key | `pull_notion` (`:121–135`) | 15 |
| `_RecordGone` as a distinct exception so a walk can tell "trashed under me" from every other failure | `:47–50` | 4 |

The best candidate deletes the first table and none of the second. That is roughly **120 lines,
not 230** — and the second table is where every comment in the file explaining *why* lives
(`:203–206` on synced-block cycles, `:28–32` on the boundary, `:125–131` on why the trashed look
wins). The maintenance burden the ticket wants to shed is concentrated in the half that cannot be
shed.

### 2. The bar and the disqualifiers are anti-correlated

The ticket's five requirements include *"fetch a page's block children recursively, not just top
level."* Of the six named candidates, **exactly one does that**: LlamaIndex's `NotionPageReader`,
whose `_read_block()` calls itself on `has_children` ([prior-art.md §6](prior-art.md)).

And it is the one candidate that fails ADR-0001 hardest, because what it recurses *into* is
indented plain text, not the raw block tree ([prior-art.md §6](prior-art.md);
[codebase.md §C](codebase.md)). The one library that clears the recursion bar is disqualified by a
constraint the bar does not mention. That is not a coincidence — recursion is only worth a
library's while if it is flattening the tree into something, and flattening is exactly what
ADR-0001 forbids at the `data` boundary.

---

## The two ADR constraints that decide most of this

### ADR-0001 — `data` is the vendor payload, verbatim

`docs/adr/0001-envelope-is-the-connector-contract.md` requires `data` to be *"the vendor payload
exactly as the platform returned it,"* append-only, with any added key named in the connector's
docstring and a hard failure rather than an overwrite if Notion ever sends that key itself —
which is precisely what `_extended` (`connectors/notion.py:358–366`) enforces for the `"blocks"`
key ([codebase.md §C](codebase.md)).

**Consequence: any candidate that returns its own parsed object model instead of raw Notion JSON
breaks the contract outright.** `data` would stop being what Notion sent and become the library's
reinterpretation of it, and nothing downstream — `knowledge`, the MCP `data` field — could tell
the two apart. This eliminates `ultimate-notion` (returns `Page`/`Block` objects,
[prior-art.md §2](prior-art.md)) and LlamaIndex (returns `Document` objects carrying flattened
text, [prior-art.md §6](prior-art.md)) as *transport* candidates regardless of their other merits.
It is also the reason `notion-client` survives where its own downstream wrappers do not: it hands
back raw dicts and nothing more ([prior-art.md §1](prior-art.md)).

This constraint is not one the ticket lists, and it does more eliminating than any bullet the
ticket does list.

### ADR-0007 — the trash pass is permanent, not a stopgap

`docs/adr/0007-full-re-pull-no-incremental-sync.md` states in terms: *"reconciliation is a
permanent code path for Notion, and is the one that exists — the second pass over the trash in
`connectors/notion.py`."* Incremental sync, when it arrives, is expected to *layer over*
reconciliation rather than replace it ([codebase.md §C](codebase.md)).

**Consequence: "can it see trashed records" is not a nice-to-have that a future incremental-sync
decision might moot.** A candidate that cannot see trash is a candidate that cannot ever be the
whole transport layer here, at any point on the roadmap. That rules `dlt` and Airbyte's manifest
out on a permanent basis rather than a pre-MVP one, and it is why `notion-client`'s
straight-through `filter` kwarg ([prior-art.md §1](prior-art.md)) matters more than it looks.

It also cuts the other way, in `notion-client`'s favour and against the ticket's hope: even with
a library that passes `filter={"in_trash": True}` through, **the two-pass merge-by-id in
`pull_notion` (`connectors/notion.py:121–135`) stays ours.** No library runs two searches and
reconciles them into one envelope per id. That is product logic about upsert-key uniqueness, not
transport.

---

## Candidate by candidate

### 1. `notion-client` / `notion-sdk-py` — **adopt after the demo**

<https://pypi.org/project/notion-client/> · <https://github.com/ramnes/notion-sdk-py> · MIT ·
v3.1.0 (2026-05-12) · Python 3.8–3.14 · built on `httpx`

The only candidate that clears every bar it can clear ([prior-art.md §1](prior-art.md)):

- **Version pinning**: `notion_version` is a `ClientOptions` constructor parameter on both
  `Client` and `AsyncClient`, so `"2026-03-11"` (`connectors/notion.py:16`) is passable. Its own
  default is `"2025-09-03"` — older than our pin, so we override rather than accept.
- **Retry**: `RetryOptions` with exponential backoff and full jitter, 429 always retryable,
  500/503 only for idempotent methods, and `_parse_retry_after_header()` handling **both** RFC
  9110 spellings — a superset of `_retry_after`/`_advertised_wait` (`:269–294`), with jitter we
  do not have.
- **Pagination**: `async_iterate_paginated_api` / `async_collect_paginated_api` are generic over
  any paginated endpoint, so one helper replaces both hand-written cursor loops.
- **Async**: first-class `AsyncClient`, on `httpx` — already a direct dependency
  ([codebase.md §B](codebase.md)), so no second HTTP stack enters the repo.
- **Typing**: `py.typed` present in `notion_client/`, confirmed from the GitHub contents API, so
  PEP 561 applies and `mypy --strict` reads its own annotations.
- **Trash**: `SearchEndpoint` passes `filter` through untouched, so `{"in_trash": True}` works.
- **Raw dicts out**, so ADR-0001 holds.

**What it deletes, concretely** — `notion_client` (`:53–70`, replaced by its constructor),
`_request` (`:230–266`), `_retry_after` (`:269–278`), `_advertised_wait` (`:281–294`),
`_next_cursor` (`:175–183`), and the cursor loop bodies inside `_search` (`:138–155`) and
`_children` (`:158–172`), which collapse to one `async_collect_paginated_api` call each. Also the
module constants those depend on (`:17–26`). Call it ~120 lines of 406.

**What it does not delete**: `_walk` (`:200–227`), `_blocks_of` (`:186–198`), the trash merge
(`:121–135`), and everything from `_envelope` (`:297`) down. No recursive block helper exists in
`helpers.py` ([prior-art.md §1](prior-art.md)) — `collect_paginated_api(blocks.children.list, …)`
still returns one level.

**What it forces us to accept:**

- **A new direct dependency** in a flat `dependencies` list with no extras mechanism to isolate it
  ([codebase.md §B](codebase.md)) — it ships in the same wheel as everything else.
- **529 is not in its retry set.** `RETRYABLE_STATUSES` here is `{429, 529}`
  (`connectors/notion.py:20`); the library retries 429 plus 500/503-on-idempotent. Either 529 needs
  a wrapper, or someone confirms it was defensive rather than observed — the comment at `:20` does
  not say which, and nobody currently knows.
- **A new exception-mapping shim.** `_RecordGone` (`:47–50`) exists so `_blocks_of` can catch a
  page trashed mid-walk. Under the library, that becomes catching its `APIResponseError` and
  re-raising on a 404 — new code that partially offsets the deletion.
- **An `Any`-shaped seam.** Its endpoints are `**kwargs: Any` returning `SyncAsync[Any]`
  ([prior-art.md §1](prior-art.md)). `py.typed` means strict mode does not *error*, but
  `warn_return_any` will bite wherever a library result is returned directly, so every call site
  needs an explicit annotation. Cheap, but it is annotation work replacing annotation work, not a
  net win on the typing axis.
- **Unverified**: whether v3.1.0's endpoint surface knows the `data_source` object our pin depends
  on (`_title` at `:370`, `_parent_id` at `:399` both branch on it). Its default version predates
  our pin. This needs a spike before adoption, not a reading.

**Verdict: adopt after the demo.** It is a real, defensible ~120-line deletion of code that has
never broken. Doing it before the demo spends the one dev's time rewriting a working connector's
plumbing, and buys nothing a prospect will see.

### 2. Keep what we have — **adopt now** (i.e. the status quo wins the demo window)

Argued against rather than assumed, as #40 requires. The genuine case against it:

- The 429/`Retry-After`/cursor code is **commodity we are maintaining for no differentiation** —
  the exact charge #40 levels. `notion-client` does it better in one place (jitter, which we lack).
- Two cursor loops written twice (`:138–155`, `:158–172`) is duplication a helper would remove.
- One dev maintaining a bespoke retry policy means one dev is the only person who knows why
  `MAX_ATTEMPTS` is 5 and why the cap is 60s.

Why it still wins today:

- **It works, and there is no reported defect in it.** Every bug the repo actually has in this
  file is in the *judgement* half — #5 (row bodies unwalked, `:99–104`) — which no candidate fixes.
- **It is the only thing on the list that satisfies all five of the ticket's bars simultaneously**,
  because it was written to.
- Swapping it is a nonzero-risk change to the only code path that produces any data at all,
  immediately before a demo, in exchange for deleting lines nobody is currently paying for.
- The deletion is not going anywhere. It is the same ~120 lines in three months.

### 3. `ultimate-notion` — **no**

<https://pypi.org/project/ultimate-notion/> · MIT · v0.10.1 · wraps `notion-sdk-py`

Three independent failures ([prior-art.md §2](prior-art.md)): **synchronous** (wraps the sync
`Client`, so it fails the async bar and would need a thread); **explicitly non-recursive** —
`Page.to_markdown()`'s docstring says verbatim *"This will not include nested blocks, i.e. the
children of top-level blocks"*, so `_walk` (`:200–227`) survives untouched; and it returns its own
`Page`/`Block` object model, which breaks ADR-0001 at the `data` boundary. Its mypy story is the
best of the wrappers, which is not enough. If we ever want it, we want the `notion-sdk-py`
underneath it instead.

### 4. LlamaIndex `NotionPageReader` — **no**

<https://developers.llamaindex.ai/python/framework-api-reference/readers/notion/> ·
`llama-index-readers-notion`

The only candidate that recurses ([prior-art.md §6](prior-art.md)) — and it recurses into indented
**plain text**, producing `Document` objects for retrieval, not raw block JSON. That is an
ADR-0001 violation at the `data` boundary, and it makes the reader unusable for the half of
`connectors/notion.py` it appears to address. Also synchronous (built on `requests`, a second HTTP
stack), no trash filtering at all (fails ADR-0007's permanent reconciliation path), and its retry
is thinner than ours — 429 only, no HTTP-date `Retry-After`, no distinct 404 handling.

Worth a second look under **#42** (payload → words), not #41: if `text` extraction is the
question, "flattens a block tree into indented prose" is the right shape for that ticket even
though it is the wrong shape for this one.

### 5. `dlt` Notion verified source — **no**

<https://dlthub.com/docs/dlt-ecosystem/verified-sources/notion>

Fails on three counts ([prior-art.md §4](prior-art.md)). **No recursion** — `notion_pages()` calls
`fetch_resource("blocks", page_id, "children")` exactly once, one level deep. **No retry at all** —
`NotionClient` calls `raise_for_status()` with no backoff and no `Retry-After` handling, so
adopting it would *add* work at `_request` (`:230–266`), not remove it. **No trash handling.** And
architecturally it is an ELT tool that loads into its own destination (DuckDB, BigQuery, S3),
which is a second store — **ADR-0002, "connectors persist nothing"**, contradicted directly
([codebase.md §C](codebase.md)). Not a transport library; a different shape of system.

### 6. Airbyte `source-notion` — **no**

<https://github.com/airbytehq/airbyte/tree/master/airbyte-integrations/connectors/source-notion>

Now a declarative low-code manifest (`manifest.yaml` + `components.py`, no hand-written client
module), runnable only inside the Airbyte platform — Airbyte Cloud, or self-hosted Docker/K8s with
its own scheduler and destination model ([prior-art.md §5](prior-art.md)). Adopting it means
standing up or paying for a platform to replace ~230 in-process lines, and it breaks
`docs/architecture.md`'s two-verb split (a pull scheduled without restarting the server). This is
the candidate #40's Fog section describes in advance: **hosting and cost disqualify it regardless
of code deleted.**

### 7. `notional` — **no**, one line

<https://github.com/jheddings/notional> — **archived 2024-10-26**, maintainer's notice verbatim:
*"⚠️ Discontinued: I have moved away from Notion to Obsidian and will no longer update this
project"* ([prior-art.md §3](prior-art.md)). Its own recommended successor is `ultimate-notion`,
already ruled out above.

### Also seen, not pursued — one line each

- **`notion-py` (jamalex)** — reverse-engineered against Notion's *private* API, a different
  generation of tool from the public API this connector targets ([prior-art.md §7](prior-art.md)).
- **`getsyncr/notion-sdk`** — surfaced once in search, far lower visibility than `notion-client`
  and duplicating its surface; not investigated further ([prior-art.md §7](prior-art.md)).

---

## The ranked call

| rank | candidate | call |
|---|---|---|
| 1 | **Keep what we have** | **adopt now** — nothing displaces it before the demo |
| 2 | `notion-client` / `notion-sdk-py` | **adopt after the demo**, behind a spike on the `data_source` endpoint surface and the 529 question |
| 3 | LlamaIndex `NotionPageReader` | **no** for #41; re-examine under **#42** |
| 4 | `ultimate-notion` | **no** — sync, non-recursive, own object model |
| 5 | `dlt` Notion source | **no** — no recursion, no retry, no trash, and ADR-0002 |
| 6 | Airbyte `source-notion` | **no** — platform, hosting, cost |
| 7 | `notional` | **no** — archived |

Stated plainly, as the ticket asks: **nothing beats what we have.** One thing ties it on
correctness and beats it on line count, and that one thing is worth doing when there is no demo
in the way.

---

## What could not be verified

- **Whether `notion-client` v3.1.0's endpoint surface covers the `data_source` object** our pin
  (`2026-03-11`) depends on. Its own default is `2025-09-03`. The `filter`/`query` kwargs pass
  through untouched, so this is probably fine, but `_title` (`:369–381`) and `_parent_id`
  (`:395–406`) both branch on `data_source` and nobody has run it. **This is a one-hour spike, not
  a reading**, and it gates the rank-2 call.
- **Why `529` is in `RETRYABLE_STATUSES`** (`:20`). Not a status Notion documents. If it was
  observed in the wild, that is a fact worth writing down; if it was defensive, the library's set
  is sufficient and the wrapper is unnecessary.
- **`ultimate-notion`'s trash story.** No trash-aware search surfaced in its docs, and the closest
  primary evidence is an adjacent JS-SDK issue (makenotion/notion-sdk-js#524, *"No way to query
  archived/in_trash items"*), which is not evidence about this library
  ([prior-art.md §2](prior-art.md)). Moot given three other failures, but not established.
- **Nothing was benchmarked.** No candidate was installed, run, or type-checked against this repo.
  Every claim is from published source and documentation, per the read-only scope of this ticket.
