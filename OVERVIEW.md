# The pipeline as it stands

Notion is pulled, stored in Qdrant, and served over MCP. All three modules are
involved: `connectors` pulls, `knowledge` stores, `server` exposes.

What is not built: extraction. `knowledge` receives envelopes and stores them whole. The
stage exists in the shape of the code; nothing happens inside it yet.

## The shape of it

```
uv run main.py pull                       uv run main.py serve
        │                                          │
        ▼                                          ▼
connectors/notion.py                      server/__init__.py
  POST /search, walk blocks                 4 tools, async, thin
  -> list[Envelope]                                │  asyncio.to_thread
        │                                          │
        └──────────────► knowledge/store.py ◄──────┘
                           Store — sync, Qdrant
                                    │
                                    ▼
                            Qdrant Cloud
                       one collection, one point per record
```

`main.py` is the only place that knows all three. It reads the credentials, builds the
Qdrant client, wraps it in a `Store`, and hands that to whichever verb is running.
Nothing below constructs its own dependencies.

## Two verbs

```
uv run main.py pull     one pass over Notion into the store, then exits
uv run main.py serve    the MCP server, until stopped
```

They are separate because the two ends of the pipeline run on different clocks. A pull
can be scheduled without restarting the server, and the server starts when Notion is
down. Both build the same store, which is the only thing they share.

`pull` prints a line per record and a tally — kind, block count, word count, deleted or
live, title, parent. That is how a person sees whether a pull went right before trusting
what landed in the store.

## The record

A record is an [`Envelope`](connectors/__init__.py) — the connectors' contract, and also
the stored record.

```
source        notion | slack | gmail
source_id     the platform's own stable id
url           always present — a way back to the thing
title         may be null
text          the words, with the vendor structure taken off
parent_id     may be null
created_at    timezone-aware
last_modified timezone-aware
is_deleted    no default; every producer must state it
data          the vendor payload, verbatim
```

There is no separate storage shape. The stored payload is `envelope.model_dump(mode=
"json")` plus one key, `tenant_id`. A second template would drift — a field added to
`Envelope` and forgotten there would silently stop reaching the store, and nothing would
fail when it did. `tenant_id` is stripped again on the way out, because `Envelope`
forbids unknown fields.

### Why `text` exists alongside `data`

They hold the same content and answer different questions. `data` is what the platform
sent, kept whole so extraction can later reach a detail we did not anticipate. `text` is
what a person would read, and it is the only thing that gets embedded.

The split is not tidiness. An embedding model reads a few hundred words and silently
drops the rest, and a Notion page wraps three paragraphs in about 3,000 characters of
ids, timestamps and JSON punctuation. Measured on a captured page, embedding `data`
spends **468 of 512 tokens before reaching the first word of the body** — so every page
comes out looking like every other page. Pulling the prose out is work only a connector
can do, since only it knows where its platform keeps the words.

`text` is `None` when there is nothing to read. Whether that is because the body was
never fetched or because there was none is a question `data` answers: a missing `blocks`
key means not walked, an empty one means walked and empty.

## Identity, and why writes are idempotent

`(tenant_id, source, source_id)` identifies a record. Qdrant point ids must be a UUID or
an unsigned int, so those three are hashed into one through a fixed namespace
([`Store.point_id`](knowledge/store.py)).

Sending the same record twice overwrites the stored copy instead of inserting a second
one. Re-ingesting *is* how a record is updated, which is what makes a repeated `pull`
safe. There is no separate update path and no duplicate to clean up.

Changing `_ID_NAMESPACE` orphans every stored point.

## Tenancy

`tenant_id` is a company, read from `COMPANY_TENANT_ID` on a pull and required on every
MCP tool — no default, because a default would quietly pool every caller into one tenant,
which is the exact failure the isolation exists to prevent.

It is a payload key rather than a field on `Envelope`, because a record's tenant is not a
property of the platform it was pulled from.

Isolation is enforced twice. `tenant_id` is part of the point id, so two tenants holding
the same Notion page hold two separate points and a cross-tenant read simply misses.
`get` and `delete` then re-check the payload's `tenant_id` before acting — that second
check is what stands between a `uuid5` collision and one company reading another's
records.

## Retrieval

Search is semantic, over vectors Qdrant computes itself through fastembed
(`BAAI/bge-small-en-v1.5`, 384 dimensions, cosine). Running the embedding locally keeps
retrieval clear of the undecided model provider — nothing here calls an LLM.

Two filters are pushed down into Qdrant rather than applied afterwards: the tenant, and
`is_deleted`. Filtering after the fact would silently shrink `limit` and would put the
isolation boundary on a code path that could forget it.

Records deleted on their platform are excluded from search but still returned by `get`.
They are kept so a consumer can see a record is gone, not so they can come back as an
answer.

### The ceiling

One vector represents about 400 words. A longer record is **findable by its opening and
returned in full** — the payload is complete regardless of what was embedded.

Splitting a record across several points is the fix and is not done. It would break the
one-point-per-record model that identity, upsert and delete all rest on. Extraction
solves the same problem better by embedding short facts rather than whole documents,
which is what `knowledge` was always meant to store.

### The threshold is not tuned

`SCORE_THRESHOLD = 0.5` came from `company-brain`, where it gated embeddings of a clean
`title. summary`. Against Notion pages it is close to no filter at all: in a fixture run,
the right record scored 0.845 while unrelated records — including pages titled with only
whitespace or emoji — sat between 0.60 and 0.72, all of them above the bar.

Re-derive it against a real pull. The signal is there; the cut is in the wrong place.

## The MCP tools

Four, all thin. The tool docstrings are the API — nothing else documents this server to
the agent calling it.

| Tool | |
|---|---|
| `ingest_records(envelopes, tenant_id) -> int` | Write. Re-sending a record updates it. |
| `search_records(query, tenant_id, limit=5) -> list[Match]` | Semantic search, scored, best first. |
| `get_record(source, source_id, tenant_id) -> Envelope \| None` | Exact fetch. Returns platform-deleted records. |
| `delete_record(source, source_id, tenant_id) -> bool` | Erases the stored copy. Not `is_deleted`. |

`server` decides nothing. It validates input against `Envelope`, calls the store, returns
the result. Ranking, thresholds and tenant enforcement all live below it.

`knowledge` is sync, including the write, and MCP handlers are async — so each tool
bridges with `asyncio.to_thread` rather than blocking the event loop on a network round
trip.

## Failure

Nothing is swallowed. No bare excepts, no empty result standing in for an error.

A stored point with no payload raises `KnowledgeError` rather than reading as absent. A
store failure reaches the MCP client as a tool error rather than an empty list — "nothing
relevant" and "the database is down" must not look alike to a caller.

`ensure_collection` refuses to start on a collection this store cannot write to. The case
it was written for is real: a collection built by `company-brain` names its vector after
the embedding model and holds a different kind of record, and without the check that
surfaced as an opaque `400 Not existing vector name` on the first write.

## Running it

Six variables in `.env`, all listed in `.env.example`. Any one missing and the run
refuses to start, naming the variable.

```
NOTION_API_KEY          integration token; the pull sees only pages it was given
QDRANT_CLUSTER_URL
QDRANT_API_KEY
QDRANT_COLLECTION_NAME  created on first run; must be this repo's own
COMPANY_TENANT_ID       the company these records belong to
OPENROUTER_API_KEY      unused today
```

The first run downloads the embedding model (~130MB) from HuggingFace.

## Testing

```
uv run pytest        # 114 tests, no network
uv run mypy .
uv run ruff check .
```

All three pass before any commit.

The collected tests never reach the network. `tests/test_notion.py` serves captured live
responses through `httpx.MockTransport`, so the connector builds its real requests and a
request with no capture is an error — which is what makes "does not walk X" assertable.
`tests/test_store.py` and `tests/test_server.py` drive the store and the tools against
doubles.

One test tokenizes. The doubles cannot see truncation, because nothing in them embeds
anything — so there is a single test that measures `_embed_text`'s output against the
model's window. It is the check that would have caught `data` being embedded.

`tests/manual_test_qdrant.py` is the live round trip the doubles cannot replace:

```
uv run python -m tests.manual_test_qdrant
```

Write, search, verbatim read-back, overwrite-not-duplicate, tenant isolation, delete. It
writes under its own tenant and cleans up after itself.

## What is not here

No extraction and no LLM anywhere, so no written answers — a consumer that wants one
composes it from what `search_records` returns. Both wait on the model provider decision
recorded in `knowledge/__init__.py`.

No Slack or Gmail connector. `Envelope.text` is the seam they will fill: message text for
Slack, the body for Gmail.

Database rows get no block walk, so a row with prose in it loses that prose and its
`text` is `None` — recorded as a TODO in the connector's own docstring, with a note that
fixing it costs one request per row.

No record of when *we* wrote something. `Envelope` carries the platform's `created_at`
and `last_modified`, which is what "when did this change" usually means, but an
incremental re-pull would want our own write timestamp.
