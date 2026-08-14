# #26 — A retrieved record does not say what document it belongs to

Research findings. Not a decision, and **not proposed for `main`** — this branch
(`research/record-context`) is the throwaway capture surface wayfinder asks for.

- [codebase.md](codebase.md) — this repo's code and ADRs, the live Notion workspace, the live store
- [prior-art.md](prior-art.md) — the MCP spec, Anthropic's contextual-retrieval numbers, LangChain,
  LlamaIndex, the Notion API

Everything below cites one of those two. Where they disagree with the ticket, the ticket is wrong.

---

## The short answer

The ticket asks where the connection between a fragment and its document should be assembled, and
names three candidate sites. Research settles more of that than expected:

1. **The chain already resolves end to end, at zero extra API cost.** Not "one hop is not the
   chain" — the whole chain, root included.
2. **Option 2 (denormalise at ingest) is eliminated** — on this codebase's own constraints, and
   independently by unanimous prior art.
3. **Option 3 (breadcrumb inside `text`) loses the evidence it was resting on.** The number people
   cite for it was measured on a different intervention.
4. **Option 1 (resolve at retrieval) is what both mature frameworks actually do**, and is cheaper
   here than the ticket assumes.

What survives is a real decision, but a narrower one than three-way: whether the crumb should reach
the **embedding** as well as the **response**. That is filed separately; see
[What is still open](#what-is-still-open).

---

## Four corrections to the ticket's own framing

### 1. The chain dies one hop higher than stated — and #19 costs nothing

The ticket says `Decisions / ADR-0010 / The question this parks` is *"not reachable today even by a
consumer that tries."* Measured across all 13 ADR subpages, identically ([codebase.md §B.2](codebase.md)):

```
hop 0  page         'The question this parks, kept whole'
hop 1  page (row)   'A record is one Notion object; the grain question waits…'   ← title present
hop 2  data_source  'Decisions'                                                  ← title present
hop 3  MISSING      the Decisions *database* — not a record
```

Both titles the crumb needs are at hops 1 and 2. The dangle #19 tracks is at hop 3, **above** the
last useful ancestor. A two-hop crumb needs nothing from #19.

The stronger finding is about hop 3 itself. Notion's data source object carries **two** parent
fields, and the second is easy to miss ([prior-art.md §4.2](prior-art.md)): `parent` gives the
containing `database_id`, while **`database_parent` gives the containing page directly**. Checked
against the raw `/search` dump this session: **all 9 data sources in the workspace already carry
`database_parent`, populated, in the response the connector already makes.** `Decisions` and
`Glossary` both point at `3bb1b933-7ce1-80c4-ab30-f7b57b31d402` — the `Context Layer` hub.

`_parent_id` (`connectors/notion.py:399-410`) reads only `parent`. It never looks at the sibling
field sitting next to it.

So `Context Layer / Decisions / <ADR title> / <section>` is available today, root-terminated, for
**zero extra requests**. ADR-0010's *"hopping database → containing page, seven extra requests"*
is measurably wrong, and #19 is a field read rather than a request budget.

### 2. `ADR-0010` is not a string that exists anywhere in the chain

The `Decisions` schema makes the ADR number a Notion **number property**
(`temp/port.py:142-154`), and #22 settled that numbers stay out of `text`. No mechanism can produce
the crumb `Decisions / ADR-0010 / …` as written. The real middle crumb is the full 78-character ADR
title ([codebase.md §B.3](codebase.md)).

### 3. ADR-0001 does not contain the sentence the ticket attributes to it

The clause a breadcrumb would contradict — *"the words a person would read, and nothing else"* —
lives in `CONTEXT.md:56` and `connectors/__init__.py:46`, not in ADR-0001. ADR-0001 explains *why*
`text` exists apart from `data`; its only content rule is that `text` has no default
([codebase.md §C.3](codebase.md)).

Option 3 therefore amends **three** documents, two of them under `workflow.md`'s propose-don't-apply
rule — not one ADR.

A related gap: `CONTEXT.md:32` lists *document* under _Avoid_ for **Envelope**. The ticket's own
title uses a word the glossary rejects, and the thing being named here — an ancestor path — has no
entry at all.

### 4. Option 2's stated premise is false

`store.py:78-80` claims a payload field costs no second shape. On the way back out, `_to_envelope`
strips exactly one key (`knowledge/store.py:260-266`) and `Envelope` sets `extra="forbid"`
(`connectors/__init__.py:55`), so a second payload key makes **every read-back raise**.
`tests/test_store.py:171-183` exists specifically to forbid it.

---

## Option by option

### Option 2 — denormalise an ancestor path at ingest: **eliminated**

Four independent blocks, any one of which is enough ([codebase.md §C.2](codebase.md)):

- The `extra="forbid"` round-trip above, plus a test written to prevent it.
- Putting the path on `Envelope` instead is what ADR-0001:29-30 forbids in terms: *"An envelope
  records what a platform returned at pull time; editing one downstream would make it a record of
  something else."*
- `upsert` has no batch id-map, so the MCP write path (`ingest_records`, which may carry any subset)
  cannot build a path at all — and ADR-0006:13-14 is explicit that it is not a second-class producer.
- A parent rename does not bump the child's `last_modified`, so nothing can detect the staleness, and
  records ingested through MCP are never repaired by ADR-0007's re-pull.

Prior art agrees unanimously and for the same reason: **neither LangChain nor LlamaIndex
denormalises ancestor text onto the child.** Both write an id at ingest and pay a hop at retrieval
([prior-art.md §3.5](prior-art.md)).

### Option 1 — resolve at retrieval: **corroborated, and cheaper than stated**

- `Store.point_id` is pure computation (`knowledge/store.py:98-101`) and Qdrant's `retrieve` takes a
  **list** of ids (`knowledge/store.py:241-245`). So it is **one call per chain level** — two for
  this corpus — for any number of hits. Not a lookup per hit.
- But the public surface is single-key `get()`, so doing this from `server` really would be
  hits×depth. The batched version needs a new method on `Store`, which puts the work in `knowledge`.
  That is where it belongs anyway: `server/__init__.py:5-7` forbids logic in the transport module.
- Stored data unchanged, embedding unchanged.
- MCP sanctions returning the structure ([prior-art.md §1](prior-art.md), spec revision `2026-07-28`):
  `structuredContent` with `outputSchema`, `resource_link` content blocks, and
  `annotations.audience` — the spec's only first-class lever for the shown-vs-matched question.

One caveat that cuts against relying on a consumer to do this itself: **there is no protocol
affordance signalling "this result has a resolvable parent."** `Tool.description` is documented as
*"a hint to the model"* and is the only channel. That confirms the ticket's first bullet — neither
`search_records` nor `get_record` mentions `parent_id`, so nothing tells a client to make the call.
Whatever gets decided, the docstrings change, because `server/__init__.py:20-22` says they are the API.

### Option 3 — breadcrumb inside `text`: **still open, but its supporting evidence does not transfer**

The case for Option 3 was that it improves the embedding. The number usually cited is Anthropic's
Contextual Retrieval — 35% fewer retrieval failures, 5.7% → 3.7%. Read at the source
([prior-art.md §2](prior-art.md)), what was prepended is **LLM-generated, chunk-specific prose of
50–100 tokens, different for every sibling**, on 800-token chunks in 8k-token documents at recall@20
with Gemini Text 004.

A static crumb identical across all 13 siblings of a page is a **different intervention**. The 35%
does not transfer, and Anthropic never measured sibling distinguishability at all.

The one measured signal on the downside is third-party and points the other way: arXiv:2510.24402
(28 Oct 2025) reports Claim Recall dropping **47.7 → 42.3** with contextual chunks in their strongest
pipeline, attributing it to shared added text de-emphasising a chunk's distinctive keywords. Adjacent
to this question rather than identical, single domain, n=1 — but it is the only measurement either
way.

Measured cost in our own corpus ([codebase.md §D.2](codebase.md)), with the real tokenizer: the crumb
is **+18 tokens, 3.5% of the 512-token window**. Free for all 13 ADR subpages — the largest goes
347 → 365. It bites only on the two records already over the ceiling, displacing **13–17 words of
their own tail** — and those two are exactly #18's deliberate ceiling probes, whose tails the demo
questions target.

---

## The cross-cutting question has a clean precedent

The ticket asks whether this should influence *retrieval* or only *presentation*, and notes the two
pull in different directions. LlamaIndex answers it directly: `excluded_embed_metadata_keys` and
`excluded_llm_metadata_keys` with a four-member `MetadataMode`, documented as *"bias the embeddings
for retrieval without changing what the LLM ends up reading"* ([prior-art.md §3.3](prior-art.md)).

The closest worked precedent to this exact problem is `MarkdownNodeParser`, which writes
`metadata["header_path"]` from `header_stack[:-1]` — an ancestor trail that deliberately excludes the
node's own header, stored as metadata that can be included in or excluded from the embedding
independently of what is returned.

The useful consequence: **the two axes are separable and need not be decided together.** LangChain
has no equivalent — `page_content` alone is embedded — which is why a breadcrumb there is
irreversible without re-ingest.

---

## What is still open

Option 1 answers the ticket as written: the response can carry the ancestor path, and the chain
resolves. It does not settle whether the crumb should also reach what gets embedded.

That is a genuine decision, not a research gap — it trades a **measured** cost (13–17 words off the
tail of the two records #18 probes, plus amending `CONTEXT.md`, `connectors/__init__.py` and
ADR-0001 under propose-don't-apply) against an **unmeasured** benefit, since no published evidence
covers static breadcrumbs and the one adjacent measurement is negative. It also needs a glossary word
for the thing itself, which does not exist yet.

Filed as a grilling ticket rather than settled here.

---

## What could not be verified

- **The store is empty.** Qdrant collection `CerebelV1` exists and is correctly shaped (384-dim,
  cosine) but holds **0 points** — no pull since the #20 port. Every claim above is from code and the
  live Notion API, not from stored payloads. Nothing about ranking or recall is measurable until the
  store is filled, which in practice waits on #21, since a pull today would load 282 records of which
  238 are fixtures.
- **Option 1's round-trip latency is not benchmarked** — the call shape is established from code, but
  there is nothing stored to retrieve.
- **Whether an ancestor path counts as "extracted knowledge"** — the named expiry trigger for
  ADR-0006 — is a judgement, not a fact.
- **`database_parent` is not in the Notion OpenAPI `required` list.** Documented as populated and
  measured present on all 9 of our data sources, but guard against absence rather than assume it.
- **No public head-to-head comparison of these three fixes on one corpus appears to exist.**
