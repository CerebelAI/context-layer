# #26 — A retrieved record does not say what document it belongs to

Fact-finding against primary sources: this repo's code and ADRs at `ac1b538` (branch
`research/record-context`), the live Notion workspace read read-only, and the live Qdrant
collection read read-only.

Every claim is labelled **[measured]** (I ran it and read the number) or **[inferred]**
(read from code/docs, not executed). Nothing here is a recommendation.

**Probe scripts** (scratchpad only, nothing written to the repo, Notion or the store):
`probe_store.py`, `probe_notion.py`, `analyse.py`, `probe_text.py`, `tokens.py`, `probe_db.py`
in this same directory, with raw dumps in `notion_search.json` and `texts.json`.

---

## A. What a consumer gets today

### A.1 The four MCP tools and their exact return shapes

`server/__init__.py:39-102` builds four tools. The module docstring states the API contract
verbatim (`server/__init__.py:20-22`):

> The tool docstrings are the API. Nothing else documents this server to the agent
> calling it, so they carry what a caller has to know -- what an envelope requires, and
> that re-sending a record updates it -- rather than restating the signature.

`docs/architecture.md:6-8` repeats it: *"What each one does is in its docstring —
`server/__init__.py` states that the tool docstrings are the API."*

**`search_records`** — `server/__init__.py:66`, returns `list[Match]`. Docstring verbatim
(`server/__init__.py:67-77`):

> Search a tenant's stored records and return the relevant ones.
>
> The primary read tool. Returns the records themselves rather than a written
> answer, each with the score it matched at, best match first -- so you can
> ground your own reply in them and link back to each record's `url`.
>
> Returns an empty list when nothing stored is relevant; weak matches are
> dropped rather than returned for you to judge. Records deleted on their
> platform are never returned, so use `get_record` if you need to confirm one
> is gone.

**`get_record`** — `server/__init__.py:81-83`, returns `Envelope | None`. Docstring verbatim
(`server/__init__.py:84-89`):

> Fetch one stored record by the platform it came from and its id there.
>
> Returns null when this tenant has no such record. Unlike `search_records`
> this does return records marked deleted on their platform, so `is_deleted`
> on the result is worth checking before you use it.

**[measured, by reading]** Neither docstring contains the string `parent_id`. The only tool
docstring that mentions it is `ingest_records` (`server/__init__.py:52-53`), and only to say
it may be null: *"`title` and `parent_id` may be null."* So on the repo's own stated contract —
the docstrings *are* the API — nothing tells a consumer that `parent_id` is a route to context.
This confirms issue #26's first bullet against the source.

**`Match`** — `knowledge/store.py:53-57`, exported at `knowledge/__init__.py:28-30`, imported
by `server` at `server/__init__.py:31`:

```python
class Match(BaseModel):
    """One search hit: the stored envelope and how well it matched the query."""

    envelope: Envelope
    score: float
```

Two fields, nothing else. **[inferred]** Because `server` re-exports `knowledge.Match` as the
tool return type rather than declaring its own, a field added to `Match` reaches the MCP wire
shape with no second declaration to update.

### A.2 `Envelope` fields

`connectors/__init__.py:55-71`:

| field | type | note |
|---|---|---|
| `source` | `Literal["notion"]` | closed on purpose, ADR-0009 |
| `source_id` | `str = Field(min_length=1)` | the platform's own id |
| `url` | `str` | mandatory (ADR-0001) |
| `title` | `str \| None` | |
| `text` | `str \| None` | what `knowledge` embeds |
| `parent_id` | `str \| None` | see below |
| `created_at` / `last_modified` | `AwareDatetime` | |
| `is_deleted` | `bool` | |
| `data` | `dict[str, Any]` | vendor payload |

`model_config = ConfigDict(frozen=True, extra="forbid")` (`connectors/__init__.py:55`).

**`parent_id` is typed `str | None` and nothing more.** The comment immediately above it
(`connectors/__init__.py:65-66`) is the whole promise:

```python
# Carries an id and nothing else -- not what kind of thing the parent is, and
# not a promise that it resolves (ADR-0010).
parent_id: str | None
```

**[measured]** Nothing in `connectors`, `knowledge` or `server` reads `parent_id` other than
to set it (`connectors/notion.py:308`, `_parent_id` at `connectors/notion.py:399-410`) and to
print it in the pull summary (`main.py:128`). `grep -rn "parent_id"` over the three modules
returns no consumer.

### A.3 What actually reaches the consumer

**[inferred, from `knowledge/store.py:147` and `:260-266`]** `search` returns
`Match(envelope=self._to_envelope(point.payload), score=point.score)`
(`knowledge/store.py:206-208`), and the payload is the full envelope dump, so
`Match.envelope.parent_id` *is* populated on every hit. The id is there; nothing names it, and
one hop is not the chain (see B).

---

## B. The parent chain, measured on the real corpus

### B.0 The store is empty — nothing in this section comes from Qdrant

**[measured]** `probe_store.py` against the credentials in `.env`:

```
collection: CerebelV1
exists: True
points_count: 0
scrolled: 0
```

The Qdrant cluster is remote (not local), the collection exists and is correctly shaped
(384-dim, cosine — matches `_EMBEDDING_SIZE`/`Distance.COSINE` at `knowledge/store.py:24,121`),
and it holds **zero points**. No pull has been run since the #20 corpus port. So **no claim
below is verified against the store** — every measurement is against the live Notion API,
which is the same source the store would be filled from. I did not run a pull.

### B.1 The live workspace, enumerated read-only

**[measured]** `probe_notion.py` — `POST /search` only, both passes, no block walk:

- **270 live records, 12 trashed, 282 total.**
- Live kinds: **67 pages, 195 database rows, 8 data sources**.
- Trashed kinds: 4 pages, 7 rows, 1 data source.
- This reconciles exactly with ADR-0010: 282 = 238 (its measured pre-port count) + 44 (the
  #20 corpus). Its 7 dangling data sources + the 2 the port created = 9 = 8 live + 1 trashed.

**Parent resolution across all 270 live records [measured]:**

| | count |
|---|---|
| resolves to a record in the same enumeration | **260** |
| workspace root (`parent_id is None`) | **2** |
| **dangles** | **8** |

All 8 dangling records are data sources, and every one of them dangles on a `database_id`:

```
data_source 'Glossary'      -> database_id e7adec82-9783-418a-893e-dd9845be7810
data_source 'Decisions'     -> database_id de6d7b64-333f-42da-85f2-1968250e67b2
data_source 'Acknowledgments (initial_data_source variant)' -> database_id ce150032-...
data_source 'Handbook Acknowledgments' -> database_id 4722cf9c-...
data_source 'Notes'         -> database_id 41b3437d-...
data_source 'Projects'      -> database_id 1b700695-...
data_source '150+ Rows'     -> database_id c7bb706e-...
data_source 'Teams'         -> database_id c9bab47e-...
```

**Issue #19 is confirmed against real ids, not restated.** The proportion is unchanged from
ADR-0010's measurement (7/238 → 8/270); the corpus port added one more instance of exactly the
same break.

### B.2 The corpus, and where the chain dies

**[measured]** `temp/state.json` holds 45 ids. Two of them — `decisions`
(`de6d7b64-333f-42da-85f2-1968250e67b2`) and `glossary`
(`e7adec82-9783-418a-893e-dd9845be7810`) — are **absent from `/search` entirely**. Those are
the two *database* ids. The remaining 43 plus the hub page `Context Layer`
(`3bb1b933-7ce1-80c4-ab30-f7b57b31d402`, parent `workspace`, itself in the search results)
make **44 records**, matching `temp/README.md:32`.

Corpus by kind **[measured]**: 22 pages (9 prose pages incl. the hub + 13 ADR subpages),
20 rows (10 ADR + 10 glossary terms), 2 data sources.

**All 13 ADR subpages have an identical chain [measured]** — every one, no exceptions:

```
hop0  page         3bb1b933-7ce1-8128-ae65-e58fa2a19650  'The question this parks, kept whole'
hop1  page (row)   3bb1b933-7ce1-8141-bb8f-e33981cff76a  'A record is one Notion object; the grain
                                                          question waits for a divergent source'
hop2  data_source  8cef0954-086b-4696-a17e-fc76e838d95f  'Decisions'
hop3  MISSING      de6d7b64-333f-42da-85f2-1968250e67b2  <the Decisions *database* — not a record>
```

- All 13 subpage parents are `page_id` and all 13 resolve to an ADR row. **[measured]**
- All 10 ADR rows have parent type `data_source_id`, and all 10 point at the same id,
  `8cef0954-086b-4696-a17e-fc76e838d95f` (`Decisions`). **[measured]**
- All 10 glossary term rows likewise have parent type `data_source_id`. **[measured]**

**The chain dies at hop 3 — the data source → database hop.** Not at hop 1, not at hop 2.
13 of 13 subpages, identical.

### B.3 How many hops the breadcrumb actually needs — and a correction to the issue

Issue #26 says: *"So `Decisions / ADR-0010 / The question this parks` is not reachable today
even by a consumer that tries."*

**[measured] That is not quite right, and the difference matters.** The two ancestor titles the
breadcrumb needs sit at hop 1 and hop 2, both of which resolve to records we hold:

| hop | record | title present? | `text` after a pull? |
|---|---|---|---|
| 0 | the subpage | yes — *The question this parks, kept whole* | **yes**, 176 words |
| 1 | the ADR row | yes — *A record is one Notion object; the grain question waits for a divergent source* | **no — `text=None`** |
| 2 | the `Decisions` data source | yes — *Decisions* | **no — `text=None`** |
| 3 | the `Decisions` database | **not a record at all** | n/a |

So **two hops** produce the breadcrumb content, and both hops land on records that carry the
needed title. What is *not* reachable today is a **complete, root-terminated** path — i.e.
`Context Layer / Decisions / <ADR title> / <section>` — because a walker cannot get past hop 3
and cannot tell "I reached the top" from "the pointer dangles". The dangle is one hop *above*
the last useful ancestor.

**The `text=None` at hops 1 and 2 is confirmed from the code, not assumed.**
`connectors/notion.py:193` is the gate:

```python
if result["object"] != "page" or result["parent"]["type"] == "data_source_id":
    return None
```

A row (parent type `data_source_id`) and a data source both get `blocks=None`, and `_text`
returns `None` for `blocks is None` (`connectors/notion.py:340-341`). That is #5/#22.

**[measured]** The words exist in Notion regardless: a targeted read-only walk of the ADR-0010
row found **7 top-level child blocks, 131 words**; the ADR-0009 row **14 blocks, 542 words**.
Both come back `text=None` today.

**The literal string `ADR-0010` does not exist as text anywhere in the chain. [measured]**
`temp/port.py:142-154, 256-260` shows the `Decisions` schema is
`Name` (title), `Number` (number), `Status` (select), `Date` (date). The ADR number is a
*number property*. #22 explicitly excludes numbers from `text` (*"Everything else stays in
`data` — numbers, dates, ids, timestamps, relations, rollups"*). So the middle crumb any
mechanism can actually produce is the full 78-character ADR title, not `ADR-0010`.

### B.4 Does #19's hop close the chain?

**[measured]** `probe_db.py`, one read-only `GET /databases/{id}` each:

```
Decisions (database) de6d7b64-...  parent = {'type': 'page_id',
                                             'page_id': '3bb1b933-7ce1-80c4-ab30-f7b57b31d402'}
                                   -> that page id IS the `Context Layer` hub
Glossary  (database) e7adec82-...  parent = same hub page
```

So #19's one-hop fix (`data source → database → containing page`) does complete the chain:
subpage → ADR row → `Decisions` ds → **(database)** → `Context Layer` hub → workspace root.
Cost is exactly as #19 states: one extra request per data source, 8 against this workspace.

---

## C. What each candidate site costs in this codebase

### C.0 The import direction, verified

**[measured]** Actual imports, not the doc's claim:

- `connectors/__init__.py` — imports only `typing`/`pydantic` and its own submodule
  (`connectors/__init__.py:19-21, 85`). Imports neither sibling.
- `knowledge/store.py:19` — `from connectors import Envelope`. That is its only cross-module import.
- `server/__init__.py:30-31` — `from connectors import Envelope`, `from knowledge import Match, Store`.
- `main.py:47-49` — imports all three.

ADR-0004 (**Status: accepted**, `docs/adr/0004-one-directional-module-imports.md:3`) holds
exactly as written: `server → knowledge → connectors`. All three options are import-legal.
The binding constraints are elsewhere.

### C.1 Option 1 — resolve at retrieval, in `server` or `knowledge`

**Files touched:** `knowledge/store.py` (a new lookup + a wider `Match`), `knowledge/__init__.py`
if a new type is exported, `server/__init__.py` (docstring only, if `Match` carries the field),
`tests/test_store.py`, `tests/test_server.py`.

**Mechanics of resolving one `parent_id` [measured, from code]:**

- There **is** a point-id lookup by key: `Store.point_id(tenant_id, source, source_id)` —
  a static method, `knowledge/store.py:98-101`, `uuid5` over `f"{tenant_id}:{source}:{source_id}"`.
  It is pure computation, no round trip.
- A Notion parent is always another Notion record, so `source` is known (`"notion"`) and a
  `parent_id` converts directly to a point id. **No search, no payload index needed.**
- `get` → `_owned_payload` → `self._client.retrieve(collection_name=..., ids=[point_id],
  with_payload=True)` (`knowledge/store.py:241-245`). **Qdrant's `retrieve` takes a *list* of
  ids** — it is inherently batchable. The store's own `_owned_payload` passes a one-element list.
- **So: N ancestors for M hits is NOT N×M calls.** It is **one `retrieve` per chain level**,
  because you need level *k*'s payloads to learn level *k+1*'s parent ids. For the corpus:
  **2 extra `retrieve` calls to produce the full breadcrumb for any number of hits**
  (level 1 = all the ADR rows in one call; level 2 = the data source). Depth is the cost driver,
  not hit count.
- **Caveat [measured]:** the *public* store API has no batch form — `get(source, source_id,
  tenant_id)` (`knowledge/store.py:154`) takes exactly one key. Option 1 done through the
  existing public surface from `server` really is M×D round trips. Getting the D-call version
  means a new method on `Store`, which puts the work in `knowledge`, not `server`.
- `_owned_payload` also re-checks `payload.get(_TENANT_KEY) != tenant_id`
  (`knowledge/store.py:256-258`), so a batched ancestor fetch must keep that check or lose the
  cross-tenant guard it exists for.

**What blocks doing it in `server` [quoted]** — `server/__init__.py:5-7`:

> Every tool is a thin wrapper over the store. No retrieval, ranking or storage logic
> lives here -- this module is transport, and the moment it starts deciding what counts
> as a good enough match it stops being that.

Plus `docs/code-style.md:6`: *"Pydantic models for anything crossing a module boundary. Dicts
stay internal."* — an ancestor list crossing `knowledge → server` has to be a model, and
models for the store's shapes live in `knowledge/store.py`.

**Stored data changed:** none. **Embedding changed:** none — `_embed_text`
(`knowledge/store.py:60-72`) is only called from `upsert` (`knowledge/store.py:146`).

### C.2 Option 2 — denormalise an ancestor path at ingest

**The payload claim, quoted** (`knowledge/store.py:78-80`):

> One vector entry per envelope. The payload is the envelope's own JSON dump
> plus `tenant_id`, and nothing else: a field added to `Envelope` reaches the
> store without a second shape having to be updated to match.

Implemented at `knowledge/store.py:147`:
`payload={**envelope.model_dump(mode="json"), _TENANT_KEY: tenant_id}`.

**[measured, from code] The answer to "can the payload carry an extra field without a second
shape being updated" is *no*, and the reason is on the way back out.** `_to_envelope`
(`knowledge/store.py:260-266`) strips exactly one key:

```python
return Envelope.model_validate(
    {key: value for key, value in payload.items() if key != _TENANT_KEY}
)
```

and `Envelope` sets `extra="forbid"` (`connectors/__init__.py:55`). A second store-added
payload key would make **every read-back raise a validation error**, so Option 2 requires
editing `_to_envelope`'s filter, plus whatever carries the path out (`Match` and/or `get`'s
return type). The docstring's "no second shape" property is a property of adding a field to
`Envelope` — not of adding a payload key.

`tests/test_store.py:171-183` locks this precisely
(`test_the_stored_payload_is_the_envelope_plus_exactly_the_tenant`,
asserting `payload == {**envelope.model_dump(mode="json"), "tenant_id": TENANT}`), so this
option starts by rewriting a test that exists to forbid it.

**Putting the path on `Envelope` instead is blocked by ADR-0001's stated consequence**
(`docs/adr/0001-envelope-is-the-connector-contract.md:29-30`):

> Envelopes are frozen and reject unknown fields. An envelope records what a platform
> returned at pull time; editing one downstream would make it a record of something else.

`knowledge` writing an ancestor path onto an envelope is exactly "editing one downstream".

**A second, independent problem: `upsert` has no way to see the batch.** `upsert(envelopes:
Sequence[Envelope], tenant_id)` (`knowledge/store.py:135`) is a comprehension over envelopes
(`:143-150`) with no id map and no lookup of already-stored parents. Building a path at ingest
needs either (a) an in-batch map — fine for a full pull, where `main.py:100-108` passes all 270
envelopes in one list, but **not** for the MCP write path, where `ingest_records`
(`server/__init__.py:44`) may carry any subset — or (b) an extra read per envelope, at which
point ingest is doing Option 1's work on the wrong side.

**What goes stale, and whether ADR-0007 repairs it.** ADR-0007 (**Status: accepted**),
`docs/adr/0007-full-re-pull-no-incremental-sync.md:5-7`:

> Every pull enumerates everything the credential can see and re-emits all of it. Deletions are
> found by a second full pass over the platform's trash. There is no watermark, no change
> detection, and nothing persisted between runs.

**[inferred]** Because a pull is unconditional and `upsert` overwrites on
`(tenant_id, source, source_id)` (`knowledge/store.py:138-139`), a full re-pull *does* rewrite
every child's payload and therefore *does* repair a stale ancestor path. Two qualifications:

1. **Nothing triggers the repair.** ADR-0007 itself says
   (`docs/adr/0007-full-re-pull-no-incremental-sync.md:36-39`) that
   *"what a pull run even is — a batch job, a long-running service, something else — undecided.
   That was tracked as #2 and closed unanswered."* The repair exists; its latency is unbounded
   and unspecified.
2. **The MCP write path is never repaired by it.** A record ingested through `ingest_records`
   is not re-emitted by the Notion pull, so a denormalised path on such a record goes stale
   permanently. ADR-0006 (`docs/adr/0006-envelope-is-also-the-stored-record.md:13-14`) is
   explicit that this producer is not second-class: *"Connectors are not privileged producers.
   The MCP write path produces envelopes too, and reaches the store the same way."*
3. A parent rename does **not** change the child's `last_modified`, so nothing downstream can
   detect the staleness — the same class of silent-wrongness ADR-0001 rejects `is_deleted`
   defaults over (`docs/adr/0001-envelope-is-the-connector-contract.md:22-24`).

### C.3 Option 3 — a breadcrumb inside `text`, in the connector

**ADR-0001's status: accepted** (`docs/adr/0001-envelope-is-the-connector-contract.md:3`).

**Important precision: ADR-0001 does not contain the sentence the issue attributes to it.**
**[measured]** `grep -rn "nothing else" docs/adr/` returns no hit in ADR-0001. What ADR-0001
actually says about `text` is *why it exists*, not *what may be in it*
(`docs/adr/0001-envelope-is-the-connector-contract.md:10-17`):

> ## Why `text` exists separately from `data`
>
> Because `data` cannot be embedded. Measured on a captured Notion page, embedding `data`
> spends **468 of 512 tokens before reaching the first word of the body** — a page wraps three
> paragraphs in roughly 3,000 characters of ids, timestamps and JSON punctuation. A record
> embedded from `data` is embedded from its metadata, and every page comes out looking like
> every other page. Pulling the prose out is work only a connector can do, since only it knows
> where its platform keeps the words.

Its only content constraint on `text` is the no-default rule
(`docs/adr/0001-envelope-is-the-connector-contract.md:21-24`): *"`text` and `is_deleted` have
no defaults. A connector that forgets `text` produces a record that stores fine, reads back
fine, and can never be found."*

**The sentence a breadcrumb would contradict lives in two other places, and both would need
amending too:**

- `CONTEXT.md:54-57`, the **Text** glossary entry:
  > The same content as `data` with the vendor structure taken off: the words a person would
  > read, and nothing else. Producing it is work only a connector can do, because only it knows
  > where its platform keeps the words.
- `connectors/__init__.py:45-48`, the `Envelope` docstring:
  > `text` is the same content with the vendor structure taken off: the words a person would
  > read, and nothing else. It is what `knowledge` embeds.

**The precise clause contradicted is "the words a person would read, and nothing else"** — a
breadcrumb is words nobody wrote on that page. `CONTEXT.md:32` also lists *document* under
_Avoid_ for **Envelope**, so #26's own framing ("what document it belongs to") has no settled
word in the glossary yet.

**Files touched:** `connectors/notion.py` (`_envelope` at `:301-317` would need the id→result
map that `pull_notion` already builds at `:125-128`), `CONTEXT.md`, `connectors/__init__.py`,
`docs/adr/0001-*.md`, `tests/test_notion.py`.

**[measured] The ancestor titles are free in the connector.** `pull_notion` already builds
`pulled: dict[id, (result, blocks)]` over every search result (`connectors/notion.py:125-128`)
before constructing any envelope, so 260 of 270 parents are resolvable in-process at **zero
extra requests**. `_envelope` is currently called without that map (`connectors/notion.py:139`),
so the change is threading the map through, not new I/O. The 8 data-source dangles are still
dangles — Option 3 does not avoid needing #19 for a root-terminated path.

**Also worth stating:** `docs/architecture.md:41-43` — *"IMPORTANT: if a task requires settling
something an ADR leaves open or an issue is tracking, stop and ask. Do not pick a default
silently."* — and `:45-46` — *"If your work contradicts an ADR, say so explicitly rather than
silently overriding it … and amend the ADR as part of the change."* `docs/workflow.md:10-11`
adds that `CLAUDE.md` and everything under `docs/` is shared with the other maintainer and edits
get **proposed, not applied**. Option 3 is the only one of the three that requires a doc-set
change under that rule; Option 2 requires none but rewrites a test that exists to forbid it.

---

## D. The surrounding constraints

### D.1 The ADRs, quoted with statuses

**ADR-0006 — The envelope is also the stored record. Status: provisional**
(`docs/adr/0006-envelope-is-also-the-stored-record.md:3-4`), expiring on
*"the first time the store must hold extracted knowledge alongside source records."*

> There is no second storage template. What a connector produces is what the store keeps,
> scoped to a tenant. (`:6-7`)
>
> - One record is one point in the store, and identity, upsert and delete all rest on that.
>   Which is why splitting a long record across several points is not a small change. (`:17-18`)
>
> ## The retrieval ceiling this creates
>
> One vector represents about 400 words. A longer record is findable by its opening and
> returned in full — the payload is complete regardless of what was embedded. (`:20-22`)

An ancestor path is arguably "extracted knowledge", which is the named expiry trigger. **[inferred]**

**ADR-0007 — A pull is a full re-pull. Status: accepted.** Quoted at C.2 above.

**ADR-0010 — A record is one Notion object. Status: provisional**
(`docs/adr/0010-record-is-one-notion-object.md:3-4`). The `parent_id` section verbatim
(`:64-79`):

> ## `parent_id` relays the platform's pointer; it may dangle
>
> It carries the id Notion gives as the parent and nothing else — not what kind of thing the
> parent is. It is **not** a promise that the parent is a record we hold.
>
> Measured: 230 of 238 parent ids resolve to a record in the same pull, one is the workspace
> root, and **seven dangle — every data source**. …
>
> Typing the field would not fix that — knowing an id names a database still does not name
> anything we hold — and for the 230 that resolve, the id alone is unambiguous, because you
> hold the thing it names and can ask it what it is. So the field stays as it is and the
> promise it makes gets written down instead. Making the chain resolve — hopping database →
> containing page, seven extra requests — is filed as build work, and is what would promote
> this from a relay to a real pointer.

ADR-0010 also states, on hub-shaped records (`:54-56`): *"The `parent_id` chain resolves to
them. And their titles are real retrieval signal — `Operations`, `Projects` — which is exactly
what a person searches for when they do not know which page holds the answer."* That is the
existing in-repo argument that ancestor titles carry retrieval value.

**ADR-0004 — accepted. ADR-0001 — accepted. ADR-0002/0003/0005/0009 — accepted.
ADR-0008 — proposed, nothing built.** **[measured]** `grep -n "Status" docs/adr/*.md`.

### D.2 The 512-token window: how much a breadcrumb costs

`_embed_text` (`knowledge/store.py:60-72`) joins `title` and `text` with `\n`, falling back to
`url`. `_EMBEDDING_WINDOW = 512` with the comment (`knowledge/store.py:26-31`):

> The model reads this many tokens and silently drops the rest -- it does not
> fail, and nothing downstream can tell a fully embedded record from a truncated
> one.

**[measured]** Read-only block walk of the real records via the connector's own `_walk`/`_text`,
tokenised with the actual `BAAI/bge-small-en-v1.5` tokenizer, truncation disabled:

| record | words | tokens (`title`+`text`) | headroom to 512 |
|---|---|---|---|
| *The question this parks, kept whole* (subpage) | 176 | **272** | +240 |
| *`parent_id` relays…* (longest subpage) | 272 | **347** | +165 |
| *Issue tracker: GitHub* (the 573-word probe, #18) | 534 | **1041** | **−529** |
| ADR-0010 row (would-be text, not pulled today) | 131 | 186 | +326 |
| ADR-0009 row (would-be text, not pulled today) | 542 | 719 | **−207** |

**Breadcrumb cost [measured]:**

| crumb | tokens standalone | marginal cost when prepended |
|---|---|---|
| `Decisions / <full ADR-0010 title>` | 20 | **+18** |
| `Decisions / <ADR title> / <section title>` | 28 | +26 |
| `Context Layer / Decisions / <ADR title>` (needs #19) | 23 | +21 |
| `Decisions` alone | 3 | +1 |

**+18 tokens is 3.5% of the window.** For all 13 ADR subpages the crumb is free —
the largest goes 347 → 365, still 147 tokens under. **[measured]**

**What happens to a record already at the ceiling [measured]:** the crumb displaces its own
size off the tail.

- *Issue tracker: GitHub* — today **269 of 537 words** sit inside the window. With the crumb,
  272 of 553 — i.e. 256 of the record's **own** words, so **13 words of its own prose are
  pushed out**. Note the deeper fact: the repo's "~400 words" rule of thumb is optimistic for
  this document; measured, only 269 words fit.
- ADR-0009's would-be row text — 391 of 550 today, 390 of 566 with the crumb, so **17 of its
  own words displaced**.

**[inferred]** So the trade in Option 3 is: a certain gain in findability for the 13 fragments
that need it, against ~13–17 words of tail lost on the two records that are already over the
ceiling — and those two are exactly #18's deliberate ceiling probes
(`docs/agents/issue-tracker.md`, ADR-0009), which are the records whose *tails* the demo
questions target.

### D.3 What `docs/` constrains about where the logic may live

- `docs/architecture.md:12-18` — one-directional imports; *"Complexity goes DOWN into
  submodules, never OUT into new top-level modules"*; *"Do not create a file or module to hold
  a single function."*
- `docs/architecture.md:6-8` — the four MCP tools are the seam, and the docstrings are the API.
  **[inferred]** Any option that changes what a consumer receives is a docstring change by that
  rule, regardless of which module the mechanism lands in.
- `docs/architecture.md:41-46` — stop and ask rather than settling something an ADR leaves open;
  amend a contradicted ADR as part of the change.
- `docs/code-style.md:6` — Pydantic models across module boundaries.
- `docs/code-style.md:17-20` — *"This is an MVP. Optimize for something deployed and demoable…
  Build the simplest thing that works for the current requirement."*
- `docs/code-style.md:10-12` — docstrings on public interfaces only; reasoning lives in ADRs.
- `docs/workflow.md:8` — *"Test-driven by default: write the failing test first."*
- `docs/workflow.md:10-11` — `docs/` and `CLAUDE.md` edits are **proposed**, not applied.
- `docs/credentials.md:6` — *"Never invent sample or demo data to make a pipeline appear to
  work."*

### D.4 The named issues: prerequisite, overlapping, or unrelated

| issue | title | relation to #26 | why |
|---|---|---|---|
| **#5** | Notion database rows lose their prose body | **Overlapping, not a prerequisite** | #26 needs the parent's *title*, which is present regardless (B.3). #5 decides whether hopping to that parent yields anything *beyond* the title. #26's own body says the title happens to be sufficient here and calls that "luck, not design". #5 also enlarges the problem: once ADR rows carry 131–542 words, two more records cross the 512-token ceiling. |
| **#19** | A data source's `parent_id` dangles: hop database to containing page | **Prerequisite only for a root-terminated path** | Measured (B.2/B.4): the dangle is at hop 3, one hop *above* the last ancestor a `Decisions / <ADR>` crumb needs. A 2-hop crumb ships without #19. A crumb that must reach `Context Layer`, or a walker that must distinguish "top" from "broken", needs #19 first. |
| **#22** | Row properties never reach `text` | **Overlapping** | Same family as #5; costs zero extra requests. Relevant to #26 in one specific way: it settles that number properties stay out of `text`, so the `Number` property that would render `ADR-0010` is not available to any crumb. It is a prerequisite for #18's glossary questions, not for #26. |
| **#23** | Stored is not retrievable: exclude wordless records from search | **Overlapping, with a direct interaction** | It removes wordless records (both data sources, hub pages) from *search results* while keeping them in the store and in `get_record`. So it does **not** break ancestor resolution — but it does mean the `Decisions` data source is a record you can only ever see as somebody's ancestor. It also deletes the `_embed_text` URL fallback (`knowledge/store.py:69-72`), which is the same function Option 3 would edit. |
| **#25** | Table cells never reach `text` | **Unrelated to the mechanism, overlapping in the demo** | Purely a `_lines_of` extraction gap (`connectors/notion.py:346-359`). It shares no code path or decision with #26. It lands on two of the same corpus records (*The intended shape*, *Triage Labels*), so both show up in #18's scoring, but nothing about #26's three options depends on it. |

**One more, not named in #26 but load-bearing [measured]:** #18's resolution comment states
*"four on #26, which is a **hard gate on the #13 bar, not a nice-to-have**: 13 of the 21 records
that carry retrievable words are ADR subpages"*, and names questions 3, 4, 9, 10 as the ones
#26 gates. #18 is closed with the ten questions written, so #26 has a concrete acceptance test
waiting for it.

---

## What I could not verify, and why

1. **Nothing was verified against the store.** The Qdrant collection `CerebelV1` exists and is
   correctly shaped but holds **0 points** (`probe_store.py`, measured). No pull has been run
   since the corpus port. Every "what a consumer gets today" claim in section A is read from
   code, and every chain fact in section B is read from the live Notion API — the source the
   store would be filled from — not from stored payloads. I did not run a pull to fix this,
   per the ticket.

2. **Round-trip cost of Option 1 is not benchmarked.** I established the *call shape*
   (batchable `retrieve`, D calls for depth D) by reading `knowledge/store.py:241-245` and the
   `qdrant_client` signature. I did not measure wall-clock latency against the cluster, because
   there is nothing stored to retrieve.

3. **`text` values are from a targeted walk, not a full pull.** I walked 5 records
   (`probe_text.py`) using the connector's own `_walk`/`_text`, so the strings are what
   `pull_notion` would produce for those 5. I did not re-verify the other 39 corpus records;
   for those I rely on `temp/README.md`, #20's resolution comment and #18's, which report the
   word counts from a real `verify.py` run.

4. **The two ADR-row word counts (131 and 542) are "would-be" numbers.** I walked those rows
   deliberately, which the connector does *not* do today (`connectors/notion.py:193`). They
   show what #5 would deliver. They are not in the store and would not be in a pull today.

5. **Whether an ancestor path counts as "extracted knowledge"** — the named expiry trigger for
   ADR-0006 — is a judgement, not a fact. I flagged it as inferred and left it.

6. **Retrieval-versus-presentation effects were not measured.** Whether prepending a crumb
   actually improves recall for a given query needs the store populated and #18's ten questions
   run. The token arithmetic in D.2 is measured; its effect on ranking is not, and I have not
   claimed one.
