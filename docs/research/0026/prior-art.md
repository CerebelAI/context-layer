# Prior art: where does a search hit's ancestry get assembled?

Primary-source research for the "hits carry no parent" problem. Every claim below carries a URL.
Dates and versions are given wherever the source shows them.

Research date: 2026-08-14.

---

## 1. MCP: how much structure may a tool result carry?

### 1.1 Current spec revision

The current protocol revision is **`2026-07-28`**. Revisions are date strings, `YYYY-MM-DD`,
marking "the last date backwards incompatible changes were made", and are marked Draft / Current /
Final. The versioning page states plainly: "The **current** protocol version is
[**2026-07-28**](/specification/2026-07-28/)."
— <https://modelcontextprotocol.io/specification/versioning>

The spec is authoritative *as the TypeScript schema*: "This specification defines the authoritative
protocol requirements, based on the TypeScript schema in schema.ts."
— <https://modelcontextprotocol.io/specification/latest>

Machine-readable schema for this revision:
<https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2026-07-28/schema.ts>

The previous revision `2025-11-25` is still in the repo
(<https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2025-11-25/schema.ts>);
version is negotiated per-request via `io.modelcontextprotocol/protocolVersion` in `_meta` rather
than by a one-time handshake, and "Clients and servers **MAY** support multiple protocol versions
simultaneously" (versioning page, as above).

### 1.2 What a tool result may carry

`CallToolResult` has exactly three payload fields (schema.ts, 2026-07-28):

```typescript
export interface CallToolResult extends Result {
  /** A list of content objects that represent the unstructured result of the tool call. */
  content: ContentBlock[];
  /** An optional JSON value that represents the structured result of the tool call. */
  structuredContent?: unknown;
  /** Whether the tool call ended in an error. */
  isError?: boolean;
}

export type ContentBlock =
  TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource;
```

So the five unstructured content types are `text`, `image`, `audio`, `resource_link`, `resource`
(embedded). Source: schema.ts (link above) and the Tools page
<https://modelcontextprotocol.io/specification/2026-07-28/server/tools>.

**Structured content.** The Tools page:

> "**Structured** content is returned as a JSON value in the `structuredContent` field of a result.
> This can be any JSON value (object, array, string, number, boolean, or null) that conforms to the
> tool's `outputSchema` if one is defined."

and

> "For backwards compatibility, a tool that returns structured content SHOULD also return the
> serialized JSON in a TextContent block."

Note the widening, and check your target revision. The previous revision **`2025-11-25` says
"Structured content is returned as a JSON **object** in the `structuredContent` field"**
(<https://modelcontextprotocol.io/specification/2025-11-25/server/tools>), whereas `2026-07-28`
allows **any JSON value**, and `outputSchema` is full JSON Schema 2020-12 with no `type: "object"`
root constraint (input schemas keep that constraint). This came in via SEP-2106:
<https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2106-json-schema-2020-12.md>
For us this means a top-level `[{hit, ancestors}, …]` array is legal at `2026-07-28` but must be
wrapped in an object (e.g. `{"results": [...]}`) to be legal at `2025-11-25`.

**Output schema is normative.** From the same page:

> "If an output schema is provided:
> * Servers **MUST** provide structured results that conform to this schema.
> * Clients **SHOULD** validate structured results against this schema."

**Resource links.** From the same page:

> "A tool **MAY** return links to [Resources], to provide additional context or data. In this case,
> the tool will return a URI that can be subscribed to or fetched by the client"

with the shape `{"type": "resource_link", "uri": ..., "name": ..., "description": ..., "mimeType": ...}`.
Caveat the spec flags explicitly: "Resource links returned by tools are not guaranteed to appear in
the results of a `resources/list` request."

**Annotations** apply to every content block, not just resources:

> "All content types (text, image, audio, resource links, and embedded resources) support optional
> annotations that provide metadata about audience, priority, and modification times. This is the
> same annotation format used by resources and prompts."

The annotation fields (<https://modelcontextprotocol.io/specification/2026-07-28/server/resources>,
§Annotations):

- `audience`: array, valid values `"user"` and `"assistant"`. "Describes who the intended audience
  of this object or data is." (schema.ts, `Annotations`)
- `priority`: 0.0–1.0. "A value of 1 means 'most important,' and indicates that the data is
  effectively required, while 0 means 'least important,' and indicates that the data is entirely
  optional."
- `lastModified`: ISO 8601 timestamp.

And what clients do with them: "Clients can use these annotations to: Filter resources based on
their intended audience; Prioritize which resources to include in context; Display modification
times or sort by recency."

**`_meta`.** Every content block, every Resource, and Tool itself carries an optional
`_meta?: MetaObject`. Keys are namespaced: prefixes "SHOULD use reverse DNS notation (e.g.,
`com.example/` …)", and any prefix whose second label is `modelcontextprotocol` or `mcp` is reserved
for MCP. (schema.ts, `MetaObject`; general rules at
<https://modelcontextprotocol.io/specification/2026-07-28/basic/index#meta>.)

### 1.3 Is there a sanctioned way to return a hit *plus* its ancestry as structured data?

**Yes — three sanctioned mechanisms, none of which require baking a breadcrumb into prose.**

1. **`structuredContent` + `outputSchema`.** This is the closest thing to a blessed answer. The
   spec's own worked example returns a nested/array JSON payload alongside a human-readable text
   block — see the `list_users` example on the Tools page, where `content` carries the prose
   ("Found 2 users: Alice … and Bob …") and `structuredContent` carries the array of typed records.
   The spec lists the benefits verbatim:

   > "Providing an output schema helps clients and LLMs understand and properly handle structured
   > tool outputs by:
   > * Enabling strict schema validation of responses
   > * Providing type information for better integration with programming languages
   > * Guiding clients and LLMs to properly parse and utilize the returned data
   > * Supporting better documentation and developer experience"

   An `ancestors: [{id, title}]` field on each hit is exactly this shape. Nothing in the spec
   constrains the *semantics* of the output schema.

2. **`resource_link` content blocks.** A hit could be returned as text, and its ancestors as
   `resource_link` blocks pointing at the parent document's URI — "to provide additional context or
   data" is the spec's own stated purpose for them. This gives the client a fetchable handle rather
   than inlined parent text.

3. **`annotations.audience`.** This is the spec's only first-class lever for the
   *matches-vs-shown* distinction (your cross-cutting question 4). A breadcrumb block annotated
   `{"audience": ["user"]}` is declared as display material; `["assistant"]` declares it as model
   material. Clients "can use these annotations to filter resources based on their intended
   audience".

**One important caveat on `content` vs `structuredContent`:** the spec as of 2026-07-28 does *not*
tell you which to prefer. There is an open SEP explicitly filed because this is unclear —
**SEP-1624, "Clarify `structuredContent` vs `content` Usage Guidance"**,
<https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1624>. It **is a proposal, not
adopted spec** (status: proposal, issue open). Its proposed wording — cite it as a proposal, not as
the spec:

> `content`: "Model-oriented output optimized for readability and token efficiency. Preferred for
> conversational agents and direct model prompting."
> `structuredContent`: "Machine-oriented output for programmatic tool use, code generation,
> type-safe orchestration, and strict schema validation."

The practical consequence for us: **many clients today feed `content` to the model and ignore
`structuredContent`.** If ancestry lives only in `structuredContent`, whether the model ever sees it
is client-dependent and unspecified. The spec's own "SHOULD also return the serialized JSON in a
TextContent block" hedge exists for exactly this reason.

### 1.4 Tool descriptions as the contract — would a client ever know to make a second call?

The spec is blunt that a description is a hint aimed at the model, not a machine contract
(schema.ts, `Tool`):

> "A human-readable description of the tool. This can be used by clients to improve the LLM's
> understanding of available tools. It can be thought of like a 'hint' to the model."

The same "hint" wording appears on `Resource.description`. And `ToolAnnotations` carries a stronger
warning:

> "NOTE: all properties in `ToolAnnotations` are **hints**. They are not guaranteed to provide a
> faithful description of tool behavior (including descriptive properties like `title`). Clients
> should never make tool use decisions based on `ToolAnnotations` received from untrusted servers."

**The directly on-point passage** is the new non-normative **"Stateful Tools"** section of the
2026-07-28 Tools page. It concedes that MCP has no protocol-level way to relate one call to the
next, and that the *only* channel for telling the model about a follow-up call is the description:

> "MCP has no protocol-level session, so a server cannot rely on implicit per-connection state to
> relate one tool call to the next."

and, on lifetime:

> "Because handles outlive any single connection, the server's retention policy should be stated in
> the creation tool's description (e.g., 'baskets expire after 24 hours of inactivity') so the model
> can see it when deciding to create state."

Read against our question: **there is no protocol affordance that tells a client "this result has a
parent you can resolve".** No `follow` link relation, no typed relationship edge, no
`relatedTools`. If a `search` tool returns a `parent_id` and a separate `get_page` tool can resolve
it, the *only* thing that makes the second hop happen is prose in the tool description that the
model happens to read and act on. That is a probabilistic mechanism, not a contract.

Reinforcing this from the SDK side: in the MCP Python SDK, the tool description *is* the function
docstring — "Two type-hinted Python functions and a docstring", and `@mcp.tool()` turns
`"""Add two numbers."""` into the description with no separate declaration.
<https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md>

And Anthropic's first-party guidance says the same thing about relationships between resources
specifically. From **"Writing effective tools for AI agents"** (Anthropic Engineering,
**11 September 2025**), <https://www.anthropic.com/engineering/writing-tools-for-agents>:

- "When writing tool descriptions and specs, think of how you would describe your tool to a new hire
  on your team" — making explicit "the specialized query formats, definitions of niche terminology,
  and **relationships between underlying resources**" you'd otherwise bring implicitly.
- "Even small refinements to tool descriptions can yield dramatic improvements." (They cite
  Claude Sonnet 3.5's SWE-bench Verified result following description refinements.)
- On identifiers vs names — directly relevant to returning a bare `parent_id`: "Agents also tend to
  grapple with natural language names, terms, or identifiers significantly more successfully than
  they do with cryptic identifiers", and resolving "arbitrary alphanumeric UUIDs to more
  semantically meaningful and interpretable language … significantly improves Claude's precision in
  retrieval tasks." **No effect size is given for this claim in the post** — it is stated
  qualitatively.
- They recommend a `response_format` enum parameter (`"concise"` / `"detailed"`) so the agent
  chooses verbosity — a first-party pattern for separating what is returned from what is stored.

**Takeaway for the ADR.** A bare `parent_id` in a result is, per Anthropic's own guidance, close to
the worst case: a cryptic identifier with no protocol-level signal that it is resolvable. Either
resolve it server-side, or (if you insist on the hop) return a resolved *title* and say in the tool
description that a second call exists — and accept that whether it happens is up to the model.

---

## 2. Does prepending context to a chunk before embedding actually help?

### 2.1 The primary source and what was prepended

**Anthropic, "Introducing Contextual Retrieval"**, Anthropic Engineering — published
**19 September 2024**. Canonical URLs (both live, same content):
<https://www.anthropic.com/news/contextual-retrieval> and
<https://www.anthropic.com/engineering/contextual-retrieval>

Definition, verbatim:

> "Contextual Retrieval solves this problem by prepending chunk-specific explanatory context to each
> chunk before embedding ('Contextual Embeddings') and creating the BM25 index ('Contextual BM25')."

What gets prepended is **LLM-generated, chunk-specific prose**, not a static breadcrumb. Their
worked example of the prepended string:

> "This chunk is from an SEC filing on ACME corp's performance in Q2 2023; the previous quarter's
> revenue was $314 million."

The generating prompt (post; also in the Anthropic cookbook):

> "Please give a short succinct context to situate this chunk within the overall document for the
> purposes of improving search retrieval of the chunk. Answer only with the succinct context and
> nothing else."

Length of the generated context: "usually 50-100 tokens".

**This distinction matters for our decision.** Anthropic's technique is *not* "prepend the document
title / breadcrumb". It is "prepend an LLM-written summary of how this chunk sits in this document",
which is chunk-*specific* — different for every sibling. Candidate fix (3) in our ticket, a static
breadcrumb identical across all siblings of a page, is a **different intervention**, and the 35%
number below does **not** transfer to it. See §2.3.

### 2.2 The measured numbers, and the conditions

All three headline results, verbatim:

> "Contextual Embeddings reduced the top-20-chunk retrieval failure rate by 35% (5.7% → 3.7%)."

> "Combining Contextual Embeddings and Contextual BM25 reduced the top-20-chunk retrieval failure
> rate by 49% (5.7% → 2.9%)."

> "Reranked Contextual Embedding and Contextual BM25 reduced the top-20-chunk retrieval failure
> rate by 67% (5.7% → 1.9%)."

Note that the 35 / 49 / 67 figures are *relative* reductions on an already-small base. In absolute
terms the best case moves failure rate 5.7% → 1.9%, i.e. **3.8 percentage points**.

Conditions attached to those numbers:

- **Metric**: recall@20 failure rate — the fraction of queries where none of the top-20 chunks
  contained the answer.
- **Top-k**: "We tried delivering 5, 10, and 20 chunks, and found using 20 to be the most performant
  of these options."
- **Embedding model for the headline figure**: the "top-performing embedding configuration
  (Gemini Text 004)". Voyage and others were also evaluated.
- **Reranking**: retrieve top 150, rerank, "select the top-K chunks (we used the top 20)". Reranker:
  Cohere.
- **Context generator**: Claude 3 Haiku.
- **Chunk / document sizes**: "Assuming 800 token chunks, 8k token documents".
- **Corpora**: codebases, fiction, ArXiv papers, science papers. The post does **not** name the
  specific datasets.
- **Generality claim**: "contextualizing improves performance in every embedding-source combination
  we evaluated."
- **Cost**: "the one-time cost to generate contextualized chunks is $1.02 per million document
  tokens", achieved via prompt caching — "you don't need to pass in the reference document for every
  chunk. You simply load the document into the cache once and then reference the previously cached
  content."

Their own "Considerations to keep in mind", verbatim and complete:

> "1. **Chunk boundaries:** Consider how you split your documents into chunks. The choice of chunk
> size, chunk boundary, and chunk overlap can affect retrieval performance.
> 2. **Embedding model:** Whereas Contextual Retrieval improves performance across all embedding
> models we tested, some models may benefit more than others.
> 3. **Custom contextualizer prompts:** While the generic prompt we provided works well, you may be
> able to achieve even better results with prompts tailored to your specific domain or use case.
> 4. **Number of chunks:** Adding more chunks into the context window increases the chances that you
> include the relevant information."

### 2.3 The cost side: does prepended shared context make siblings less distinguishable?

**Anthropic does not address this.** Nothing in the post, including the Considerations list quoted
above, measures or mentions inter-chunk discriminability. I found **no first-party Anthropic source
on this question at all** — flagged as unverified.

**One third-party paper does measure a directly relevant regression.** "Metadata-Driven
Retrieval-Augmented Generation for Financial Question Answering", Dadopoulos, Ladas, Moschidis,
Negkakis, **arXiv:2510.24402v1, submitted 28 October 2025**.
<https://arxiv.org/abs/2510.24402> · HTML: <https://arxiv.org/html/2510.24402v1>

They run the same pipeline with "Standard" (Std) vs "Contextual" (Ctx) chunks. Extract of their
Table 1:

| Architecture | Chunks | F1 | Claim Recall | Context Precision |
|---|---|---|---|---|
| Hybrid Retrieval | Std | 30.4 | 41.1 | 16.1 |
| Hybrid Retrieval | Ctx | 37.6 | 45.1 | 17.6 |
| Hybrid + Reranking (Cohere) | Std | 38.9 | **50.7** | 23.0 |
| Hybrid + Reranking (Cohere) | Ctx | 44.1 | **48.2** | 22.3 |
| Filtering + Rewriting + Reranking (Cohere) | Std | 37.3 | **47.7** | 22.0 |
| Filtering + Rewriting + Reranking (Cohere) | Ctx | 44.4 | **42.3** | 44.4 |

Their reading of it: contextual chunks lift end-to-end generation quality (F1) across the board, but
in the stronger pipelines **retrieval-side Claim Recall drops** — 50.7 → 48.2, and 47.7 → 42.3 in
the most advanced configuration. The authors' explanation is that "contextual metadata helps align
the chunk with the query's broader intent, [but] it can occasionally de-emphasize the specific
keywords needed to match ground-truth claims."

**Read this carefully — it is adjacent to, not identical with, our question.** The mechanism the
authors name is *dilution of the chunk's own distinctive keywords by added shared text*. That is the
same mechanism that would make siblings less distinguishable, and it is measured. But they did not
measure sibling-vs-sibling separation directly, and the caveats are: single domain (financial QA),
single paper, n=1 on the configurations that regressed, and it is not first-party.

**Related primary sources, for completeness:**

- "Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models", Günther, Mohr,
  Williams, Wang, Xiao (Jina AI). **arXiv:2409.04701v3** (v1 Sep 2024, revised **7 July 2025**).
  <https://arxiv.org/abs/2409.04701> · <https://arxiv.org/html/2409.04701v3>
  §4.5 "Comparison to Contextual Embedding" compares late chunking directly against Anthropic's
  approach. Both correctly rank the relevant chunk top-1 where naive chunking fails; scores are
  comparable. Their stated objection to Anthropic's method is **cost, not discriminability**: "This
  is however computationally more expensive, as LLMs are typically much larger than embedding models
  or even require paid access to LLM API." **The paper itself describes §4.5 as small-scale** — one
  fictional financial document, five chunks. Treat it as an illustration, not a benchmark.
- "Context is Gold to find the Gold Passage: Evaluating and Training Contextual Document
  Embeddings", Conti, Faysse, Viaud, Bosselut, Hudelot, Colombo. **arXiv:2505.24782**, submitted
  **30 May 2025**. <https://arxiv.org/abs/2505.24782>
  Introduces the ConTEB benchmark; finds "state-of-the-art embedding models struggle in retrieval
  scenarios where context is required", and that their contextualised training makes chunks "more
  robust to suboptimal chunking strategies and larger retrieval corpus sizes". **I could not confirm
  from the abstract/metadata that they measure sibling homogenisation** — flagged as unverified.

**Bottom line for §2:** the 35% figure is real, first-party, and well-specified — but it is for
LLM-generated *per-chunk* context on 800-token chunks in 8k-token documents at recall@20. It is not
evidence for a static breadcrumb. The one measured signal on the downside (arXiv:2510.24402) says
adding shared context can *cost* you retrieval recall in a reranked pipeline even while it improves
answer quality. **Nobody has published a first-party measurement of sibling-chunk discriminability
under shared prepended context.**

---

## 3. Prior art: where does ancestry get assembled?

**Two navigation warnings first — both frameworks moved their docs, and stale URLs bounce:**

- `python.langchain.com/docs/how_to/*` now **308-redirects to
  `https://docs.langchain.com/oss/python/langchain/overview`**, a generic overview. The specific
  how-to prose is gone from the live site. API reference moved to `reference.langchain.com`.
- `docs.llamaindex.ai/en/stable/*` now **301-redirects to `developers.llamaindex.ai/python/...`**.

Versions at time of research (2026-08-14, from the PyPI JSON API): `langchain` **1.3.15**,
`langchain-classic` **1.0.8**, `llama-index-core` **0.14.23**. **No LlamaIndex or LangChain doc page
examined carried a version number or last-updated date** — cite them by URL plus access date.

### 3.1 LangChain `ParentDocumentRetriever` — ingest-time id, retrieval-time hop

**It has been demoted to `langchain-classic` in the 1.0 restructure.** The old import path is gone;
current source:

- <https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/retrievers/parent_document_retriever.py>
- <https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/retrievers/multi_vector.py>
- API ref: <https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/ParentDocumentRetriever>

**The mechanism is two-phase, and the split is exactly our question.**

*Ingest* — the parent id is denormalised into every child chunk's metadata
(`parent_document_retriever.py`, `_split_docs_for_adding`):

```python
for _doc in sub_docs:
    _doc.metadata[self.id_key] = _id
```

`id_key` is defined on the superclass with default **`"doc_id"`** (`multi_vector.py`). Then the write
fans out to two stores:

```python
self.vectorstore.add_documents(docs, **kwargs)   # children → vector store
if add_to_docstore:
    self.docstore.mset(full_docs)                # parents → docstore
```

`docstore` is typed `BaseStore[str, Document]` — a plain key-value store, entirely separate from the
vector store.

*Retrieval* — a **second lookup hop** swaps children for parents
(`MultiVectorRetriever._get_relevant_documents`):

```python
sub_docs = self.vectorstore.similarity_search(query, **self.search_kwargs)
ids = []
for d in sub_docs:
    if self.id_key in d.metadata and d.metadata[self.id_key] not in ids:
        ids.append(d.metadata[self.id_key])
docs = self.docstore.mget(ids)
return [d for d in docs if d is not None]
```

Two behaviours worth carrying into the ADR: **the child chunk text is discarded** — only parents are
returned; and **a missing docstore entry is silently dropped**, not raised.

**What the docs say about the trade-off.** The chunking trade-off is stated clearly, in the class
docstring and the how-to:

> "You may want to have small documents, so that their embeddings can most accurately reflect their
> meaning. If too long, then the embeddings can lose meaning."

and, from the multi-vector how-to: "it can be useful to retrieve larger chunks of information, but
embed smaller chunks"
(<https://github.com/langchain-ai/langchain/blob/master/docs/docs/how_to/multi_vector.ipynb>).

**On staleness, docstore/vector-store sync, deletion, or update semantics: nothing. This is a clean
negative finding**, checked four ways:

1. **No delete or update API exists.** Grepping both source files for `def delete`, `def adelete`,
   `def update` returns zero matches. The retrievers expose only `add_documents` / `aadd_documents`
   and the two `_get_relevant_documents` methods. There is no supported way to remove or revise a
   parent.
2. Neither how-to notebook mentions staleness, sync, or deletion.
3. **LangChain's indexing API — which *is* the sync story — does not cover the docstore.** The
   indexing how-to says it keeps documents in sync "into a **vector store**", with cleanup modes
   `None`/`incremental`/`full`/`scoped_full`, and requires stores supporting delete-by-id. Keyword
   counts across that entire notebook: `docstore` → 0, `ParentDocument` → 0, `MultiVector` → 0,
   `byte_store` → 0. (Recovered from the v0.3.27 tag:
   `https://raw.githubusercontent.com/langchain-ai/langchain/langchain%3D%3D0.3.27/docs/docs/how_to/indexing.ipynb`)
4. The live retrieval docs page <https://docs.langchain.com/oss/python/langchain/retrieval> does not
   mention `ParentDocumentRetriever`, `MultiVectorRetriever`, or parent-document retrieval at all.

**Implication for us.** LangChain's docstore is *unmanaged*. Re-indexing a changed source cleans the
vector store while leaving orphaned parents behind, and the retriever then silently returns fewer
documents than chunks matched. The framework that most resembles candidate fix (1) — retrieval-time
hop — ships no answer at all to the staleness question, and no hook to build one.

### 3.2 LlamaIndex — hierarchical parser (ingest) + auto-merging retriever (query)

**Ingest: denormalised, bidirectionally.**
<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/relational/hierarchical.py>

```python
def _add_parent_child_relationship(parent_node: BaseNode, child_node: BaseNode) -> None:
    child_list = parent_node.child_nodes or []
    child_list.append(child_node.as_related_node_info())
    parent_node.relationships[NodeRelationship.CHILD] = child_list
    child_node.relationships[NodeRelationship.PARENT] = parent_node.as_related_node_info()
```

`NodeRelationship` is an enum with `SOURCE, PREVIOUS, NEXT, PARENT, CHILD`; values are
`RelatedNodeInfo(node_id, node_type, metadata, hash)` (`llama_index/core/schema.py`). Default
hierarchy is `chunk_sizes = [2048, 512, 128]`, `chunk_overlap=20`, each level a `SentenceSplitter`.
Relationships are deliberately skipped at level 0 so top-level `Document` objects aren't wired as
parents. Helpers `get_leaf_nodes` (no `CHILD` key) and `get_root_nodes` (no `PARENT` key) exist in
source but are **undocumented** in any module guide or API reference page.

Docs:
<https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/> —
"This node parser will chunk nodes into hierarchical nodes... with each node containing a reference
to it's parent node."

Note that `RelatedNodeInfo` carries a `hash` — a denormalisation-staleness affordance LangChain
lacks, though I found no doc page explaining an intended invalidation workflow built on it.

**Query time: resolved via docstore, gated by a ratio threshold.**
<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/retrievers/auto_merging_retriever.py>

The threshold is a constructor param `simple_ratio_thresh: float = 0.5`, and the merge rule is:

```python
parent_num_children = len(parent_child_nodes) if parent_child_nodes else 1
parent_cur_children = parent_cur_children_dict[parent_node_id]
ratio = len(parent_cur_children) / parent_num_children
if ratio > self._simple_ratio_thresh:
```

So: **if strictly more than 50% of a parent's children were retrieved, those children are removed
from the result set and replaced by the single parent node**, scored as the mean of the replaced
children's scores. Parents are fetched by `docstore.get_document(parent_node_id)` with a per-call
cache dict. Two further details:

- **It loops to a fixed point** (`while is_changed:`), so merged parents can themselves merge into
  grandparents — the hierarchy collapses upward across levels within one query.
- **`_fill_in_nodes` runs first** and uses `NEXT`/`PREV` relationships to splice in a gap node
  between two adjacent-but-one retrieved nodes, which can push a parent over the threshold.

Storage split, from the auto-merging example
(<https://developers.llamaindex.ai/python/examples/retrievers/auto_merging_retriever/>): "We define a
docstore, which we load all nodes into. We then define a `VectorStoreIndex` containing just the
leaf-level nodes." Rationale: "This allows us to consolidate potentially disparate, smaller contexts
into a larger context that might help synthesis."

**So: ingest-time denormalisation of the *edge*, query-time resolution of the *content*.** This is
the hybrid, and it is worth noting that neither framework denormalises the parent's *text* onto the
child. Candidate fix (2) in our ticket — copying an ancestor path onto the stored record — has **no
direct analogue in either framework**; both keep an id and pay for a hop.

**`RecursiveRetriever` is a different mechanism** and does not use `NodeRelationship` at all
(<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/retrievers/recursive_retriever.py>).
It keys off `IndexNode` (a `TextNode` subclass adding `index_id: str` and `obj: Any`); at retrieval,
`if isinstance(node, IndexNode)` it recurses into a retriever/query-engine looked up by `index_id`,
guarded by a `visited_ids` set. Docs: "During query-time, if an `IndexNode` is fetched, then the
underlying query engine/retriever will be queried"
(<https://developers.llamaindex.ai/python/examples/retrievers/recursive_retriever_nodes/>). The docs
there name two patterns — "Chunk references" and "Metadata references: Summaries + Generated
Questions referring to a bigger chunk" — i.e. a summary as a *retrieval surface pointing at* a
chunk, rather than text glued onto it.

### 3.3 The key question: separating what is embedded from what is returned

#### LlamaIndex: yes, first-class, per-metadata-key

All verified in
<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/schema.py>.

`MetadataMode` has exactly four members:

```python
class MetadataMode(str, Enum):
    ALL = "all"; EMBED = "embed"; LLM = "llm"; NONE = "none"
```

Fields on `BaseNode` (and `text_template` on `TextNode`):

| Field | Default | Source description |
|---|---|---|
| `excluded_embed_metadata_keys: List[str]` | `[]` | "Metadata keys that are excluded from text for the embed model." |
| `excluded_llm_metadata_keys: List[str]` | `[]` | "Metadata keys that are excluded from text for the LLM." |
| `metadata_template: str` | `"{key}: {value}"` | "Template for how metadata is formatted, with {key} and {value} placeholders." |
| `metadata_separator: str` | `"\n"` | "Separator between metadata fields when converting to string." |
| `text_template: str` (`TextNode`) | `"{metadata_str}\n\n{content}"` | "Template for how text is formatted, with {content} and {metadata_str} placeholders." |

**Spelling correction, worth getting right in the ADR:** the field is now `metadata_separator`, with
the historical misspelling kept as a Pydantic alias — `alias="metadata_seperator"`. The docs still
show the misspelling. Both work; prefer the correct spelling in new code.

The filtering logic (`get_metadata_str`) is a set difference over metadata keys before rendering:

```python
if mode == MetadataMode.NONE: return ""
usable_metadata_keys = set(self.metadata.keys())
if mode == MetadataMode.LLM:
    for key in self.excluded_llm_metadata_keys: ...remove
elif mode == MetadataMode.EMBED:
    for key in self.excluded_embed_metadata_keys: ...remove
return self.metadata_separator.join(
    self.metadata_template.format(key=key, value=str(value)) ...)
```

`MetadataMode.ALL` falls through both branches, so no exclusions are applied.

`TextNode.get_content` is `def get_content(self, metadata_mode: MetadataMode = MetadataMode.NONE)`.
**The concrete default is `NONE`**, not `ALL` (the abstract declaration on `BaseNode` defaults to
`ALL`; the `TextNode` and `Node` overrides default to `NONE`). A bare `node.get_content()` therefore
returns raw text with no metadata.

**The docs state the purpose in almost exactly our terms**
(<https://developers.llamaindex.ai/python/framework/module_guides/loading/documents_and_nodes/usage_documents/>,
"Advanced - Metadata Customization"):

> "A key advantage of doing this is to bias the embeddings for retrieval without changing what the
> LLM ends up reading."

> "In this case, you can specifically exclude metadata visible to the embedding model, in case you
> DON'T want particular text to bias the embeddings."

**Where `EMBED` is actually applied** — this closes the loop. In
<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/indices/utils.py>,
both `embed_nodes` and `async_embed_nodes` do:

```python
texts_to_embed.append(node.get_content(metadata_mode=MetadataMode.EMBED))
```

So in LlamaIndex **metadata is rendered into the embedded string by default**, and the `excluded_*`
lists are the opt-out — not the opt-in. Inheritance is handled: `build_nodes_from_splits` copies both
exclusion lists from document to node
(<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/node_utils.py>).

**This is the single most decision-relevant finding in section 3.** LlamaIndex answers our
cross-cutting question 4 — should ancestry influence what matches, or only what is shown? — with
"you choose, per metadata key, and the two axes are independent (`EMBED` vs `LLM`)."

#### LangChain: no equivalent — confirmed negative

**There is no way in LangChain to include a metadata field in the returned `Document` but exclude it
from the embedded text, because metadata is never embedded in the first place.** The default is the
inverse of LlamaIndex's, so the exclusion problem cannot arise — and the opposite problem
(*getting* a field into the embedding) has no declarative solution.

Checked four ways:

1. **`langchain_core.documents.base.Document`**
   (<https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/documents/base.py>).
   Complete field set: `page_content: str`, `type: Literal["Document"]`, plus `id` and `metadata`
   from `BaseMedia`. No templates, no exclusion lists, no metadata mode, no `get_content`-style
   renderer. The only content accessor is the attribute itself.
2. **`VectorStore.add_documents` / `add_texts`**
   (<https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py>)
   — the text handed to the embedding model is uniformly `texts = [doc.page_content for doc in
   documents]`. Metadata rides along as a filterable payload only.
3. **`InMemoryVectorStore`**, the reference implementation
   (<https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/in_memory.py>)
   — `texts = [doc.page_content for doc in documents]` then `self.embedding.embed_documents(texts)`.
4. The live retrieval docs (<https://docs.langchain.com/oss/python/langchain/retrieval>) do not
   discuss metadata inclusion in or exclusion from embedded text at all.

**LangChain's actual answer to "embed one thing, return another" is `MultiVectorRetriever` itself** —
but at *whole-Document* granularity, not per-field. The three documented strategies in the
multi-vector how-to are smaller chunks; "Summary: create a summary for each document, embed that
along with (or instead of) the document"; and hypothetical questions. The store split is stated
plainly: "a distinction between the vector store, which indexes embeddings of the (sub) documents,
and the document store, which houses the 'parent' documents".

**Consequence for candidate fix (3).** In LangChain you must mutate `page_content` yourself before
indexing, and the breadcrumb is then permanently part of the child's text — irreversible without
re-ingest. In LlamaIndex the same effect is declarative and reversible on a single node.

### 3.4 Breadcrumb / header injection into embedded text

**LlamaIndex — yes, and it happens as a side effect you should know about.** Metadata extractors
write to `node.metadata`, which by the mechanism above lands in the embedded text
(<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/extractors/interface.py>):

```python
node.metadata.update(cur_metadata_list[idx])
if excluded_embed_metadata_keys is not None:      # default None → no exclusion
    node.excluded_embed_metadata_keys.extend(...)
if not self.disable_template_rewrite:             # default False → rewrite happens
    cast(TextNode, node).text_template = self.node_text_template
```

So **by default nothing is excluded** — extracted values do enter the embedding — and extractors
**rewrite the node's `text_template`** to:

```
[Excerpt from document]\n{metadata_str}\nExcerpt:\n-----\n{content}\n-----\n
```

That is literal breadcrumb-prepending, applied as a side effect of running an extractor. **No docs
page states this consequence**; it is confirmed from source.

Keys written
(<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/extractors/metadata_extractors.py>):
`TitleExtractor` → `document_title`; `KeywordExtractor` → `excerpt_keywords`;
`QuestionsAnsweredExtractor` → `questions_this_excerpt_can_answer`; `SummaryExtractor` →
`section_summary` / `prev_section_summary` / `next_section_summary`. Stated motivation
(<https://developers.llamaindex.ai/python/framework/module_guides/indexing/metadata_extraction/>):
"A chunk of text may lack the context necessary to disambiguate the chunk from other similar chunks
of text."

**`MarkdownNodeParser` does both, and is the closest prior art to our exact problem**
(<https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/file/markdown.py>):

- *Into text*: the header line is retained as the first line of its section —
  `current_section = "#" * header_level + f" {header_text}\n"`.
- *Into metadata*: `node.metadata["header_path"] = ...`, built from
  `self.header_path_separator.join(h[1] for h in header_stack[:-1])`, default separator `"/"`,
  producing `"/header1/header2/"` or `"/"`.

Note `header_stack[:-1]` — **the path deliberately excludes the section's own header** (already in
the text) and carries only its ancestors. That is precisely an ancestor breadcrumb, stored as a
metadata key, which the `excluded_embed_metadata_keys` mechanism can then include in or exclude from
the embedding independently of what is returned. If we want a worked precedent for our decision,
this is it.

**LangChain — headers go to metadata and are stripped from text by default**
(<https://github.com/langchain-ai/langchain/blob/master/libs/text-splitters/langchain_text_splitters/markdown.py>).
`MarkdownHeaderTextSplitter` takes `strip_headers: bool = True`, documented as "Strip split headers
from the content of the chunk". Headers are written into metadata keyed by the caller-supplied names
from `headers_to_split_on`; the content branch is guarded by `if not self.strip_headers`.
`ExperimentalMarkdownSyntaxTextSplitter` mirrors this.

**So LangChain's default is the opposite of what a breadcrumb strategy wants:** the header is removed
from the embedded text and parked in metadata, where nothing will ever embed it. `strip_headers=False`
puts it back into `page_content` and therefore into the embedding — but then gives you no way to keep
it out of what is returned. There is no equivalent of `header_path` (an ancestor trail distinct from
the immediate header) in either LangChain splitter.

### 3.5 Summary table

| | LangChain | LlamaIndex |
|---|---|---|
| Parent edge written at | ingest — `child.metadata["doc_id"]` | ingest — `relationships[NodeRelationship.PARENT]`, plus reverse `CHILD` |
| Parent content fetched at | retrieval — `docstore.mget(ids)` | retrieval — `docstore.get_document(parent_id)` |
| Replacement rule | always: children discarded, parents returned | conditional: `ratio > simple_ratio_thresh` (0.5), looped to a fixed point |
| Ancestor *text* denormalised onto child | no | no |
| Embedded text | `page_content` **only** | `get_content(MetadataMode.EMBED)` = metadata + text |
| Embed-vs-return separation | whole-Document only (MultiVectorRetriever) | **per-metadata-key** (`excluded_embed_metadata_keys`) |
| Markdown header default | stripped from text → metadata | kept in text **and** `header_path` metadata |
| Deletion/update of parents | **no API at all** | docstore is a first-class managed store |



## 4. Notion API: what ancestry does the platform actually give you?

**API version these claims hold for: `Notion-Version: 2026-03-11`**, the current latest. The
versioning page shows the header as `-H "Notion-Version: 2026-03-11"`.
— <https://developers.notion.com/reference/versioning>
Version history: `2026-03-11`, `2025-09-03`, `2022-06-28`, `2022-02-22`, `2021-08-16`, `2021-05-13`
(<https://developers.notion.com/reference/changes-by-version>). Versions are minted only for
backwards-incompatible changes.

### 4.1 Immediate parent only — no ancestor chain, no path endpoint

**Every Notion object exposes exactly one level of parentage.** There is no ancestor array, no path,
no breadcrumb field on any object, and **no endpoint anywhere in the API returns an ancestor path.**

Verified against Notion's own machine-readable spec at
<https://developers.notion.com/openapi.json>: scanning every schema property name for `ancestor`,
`lineage`, `path`, `hierarch`, `depth`, `trail` returns exactly one hit — `breadcrumb`, which is the
*breadcrumb block type* (`breadcrumbBlockObjectResponse`) whose value is `emptyObject`. That is a UI
block Notion's own client renders; it carries no ancestry data over the API.

The page object's complete field list is `object, id, created_time, last_edited_time, in_trash,
is_archived, is_locked, url, public_url, parent, properties, icon, cover, created_by,
last_edited_by` (<https://developers.notion.com/reference/page>). `parent` is the only structural
field. Same story for block (<https://developers.notion.com/reference/block>) and database.

**Parent types** (<https://developers.notion.com/reference/parent-object>, confirmed against the
OpenAPI union `parentForBlockBasedObjectResponse`):

| `type` | Payload fields |
|---|---|
| `database_id` | `database_id` |
| `data_source_id` | `data_source_id` **and** `database_id` |
| `page_id` | `page_id` |
| `block_id` | `block_id` |
| `workspace` | `workspace: true` |
| `agent_id` | `agent_id` |

Which types apply where differs per object, and the OpenAPI spec is precise about it:

- **Page** (`pageObjectResponse.parent`) → `parentForBlockBasedObjectResponse`: all six.
- **Block** → same union, all six.
- **Database** (`databaseObjectResponse.parent`) → `parentOfDatabaseResponse`, a *narrower* union of
  four: `page_id`, `workspace`, `database_id`, `block_id`. So yes — a database's parent can be a
  page or the workspace. (`database_id` is the wiki case.)
- **Data source** (`dataSourceObjectResponse.parent`) → `parentOfDataSourceResponse`, only two:
  `database_id` (normal) or `data_source_id` (externally synced).

`agent_id` is newer and thinly documented — worth handling defensively in any exhaustive match.

**Search does not help.** `POST /v1/search`
(<https://developers.notion.com/reference/post-search>) filters only by object type
(`page` / `data_source`) and trash status, returns each result's immediate `parent` only, and cannot
be scoped to a subtree.

**Assembling a full path costs N calls, one per level** — walk `parent` upward until
`type: "workspace"`, each hop a separate `GET /v1/pages/{page_id}`
(<https://developers.notion.com/reference/retrieve-a-page>) or `GET /v1/blocks/{block_id}`
(<https://developers.notion.com/reference/retrieve-a-block>). Depth is not knowable in advance and
every hop counts against the rate limit of roughly 3 requests/second average
(<https://developers.notion.com/reference/request-limits>). **This is implied by the reference
rather than stated in it** — the docs never describe path assembly, because the API has no concept
of a path.

### 4.2 The data source layer — and the answer to "does the chain dangle?"

**Context.** As of version `2025-09-03`, a database became a *container* and the tables moved down a
level into **data sources**, each with its own schema. `/v1/databases` split into `/v1/databases`
(container) and `/v1/data_sources` (individual tables).

- Upgrade guide: <https://developers.notion.com/docs/upgrade-guide-2025-09-03>
  (canonical: <https://developers.notion.com/guides/get-started/upgrade-guide-2025-09-03>)
- FAQs: <https://developers.notion.com/docs/upgrade-faqs-2025-09-03>
- Changelog entry "Important API update coming September 3rd", dated **26 August 2025**, effective
  **3 September 2025** — <https://developers.notion.com/page/changelog>

**The finding: the chain does NOT dangle.** The data source object carries **two** parent fields, and
the second one is easy to miss (<https://developers.notion.com/reference/data-source>):

```jsonc
"parent":          { … }   // parentOfDataSourceResponse: database_id | data_source_id
"database_parent": { … }   // parentOfDatabaseResponse: page_id | workspace | database_id | block_id
```

Verbatim descriptions from the reference:

- `parent` — "Information about the data source's immediate parent. Most data sources are parented
  by a database (`type: "database_id"`). Some externally synced data sources can be parented by
  another data source (`type: "data_source_id"`) and include the containing `database_id`."
  Example: `{"type": "database_id", "database_id": "842a0286-cef0-46a8-abba-eac4c8ca644e"}`
- `database_parent` — "Information about the containing database's parent."
  Example: `{ "type": "page_id", "page_id": "af5f89b5-a8ff-4c56-a5e8-69797d11b9f8" }`

Note: **there is no bare top-level `database_id` field** on the data source object — the database ID
lives inside `parent.database_id`.

**Data source → containing page, concretely.**

Fast route, **one call**:
```
GET /v1/data_sources/{data_source_id}
  → database_parent  →  {"type": "page_id", "page_id": "..."}      ← the page
```
`database_parent` is precomputed by Notion specifically to save the database round-trip.

Long route, **two calls**:
```
GET /v1/data_sources/{data_source_id}   → parent.database_id
GET /v1/databases/{database_id}         → parent → {"type":"page_id","page_id":"..."}
```

Because `database_parent` is a `parentOfDatabaseResponse`, it may terminate or continue:

- `page_id` → done, you have the page.
- `workspace` → the database is top-level; there **is** no containing page. Correctly terminal.
- `block_id` → inline database inside a block; one more `GET /v1/blocks/{block_id}` to reach a page.
- `database_id` → the wiki case; another hop.

For externally synced data sources (`parent.type == "data_source_id"`), `database_parent` is still
populated on the object, so the shortcut survives.

**What `parent` do pages returned by a data source query carry? Both IDs.**
`POST /v1/data_sources/{data_source_id}/query`
(<https://developers.notion.com/reference/query-a-data-source>) returns pages whose parent is a
`dataSourceParentResponse`, and the OpenAPI spec marks all three fields **required**:

```json
{
  "type": "data_source_id",
  "data_source_id": "1a44be12-0953-4631-b498-9e5817518db8",
  "database_id": "d9824bdc-8445-4327-be8b-5b47500af6ce"
}
```

So a row page hands you the data source ID *and* the database ID for free — `database_id` is
documented as a convenience field. It still does **not** give you the page the database sits on; the
full walk from a row page to its containing page is **2 calls** (query result → retrieve data source
→ read `database_parent`). Webhooks gained a `data_source_id` field under `data.parent` for the same
reason (upgrade guide).

### 4.3 Caveats on the Notion findings

- **`database_parent` is not in the OpenAPI `required` list** for `dataSourceObjectResponse`. The
  documented behaviour says it is populated; the schema does not guarantee it. Guard against absence
  rather than assume.
- **Doc/spec drift:** the rendered data source reference still lists `archived` as a deprecated
  alias, while the OpenAPI spec at `2026-03-11` omits it — consistent with `archived` having been
  removed in that version in favour of `in_trash`. Trust the spec. (Also: the OpenAPI page schema
  carries *both* `in_trash` and `is_archived`, which the rendered reference does not explain.)
- **None of this was tested against a live workspace.** Everything above is read off the reference,
  the upgrade guide, the changelog, and `openapi.json`.
- **`agent_id` parent type**: present in the reference and the OpenAPI union, but I found no guide
  explaining when a connector encounters it in practice.

**Practical takeaway.** Ancestry in Notion is not a field you read, it is a walk you perform and
cache. The single gift the platform gives you is `database_parent`, which collapses the
data-source → page lookup from two calls to one. Everything above that point is N calls at ~3 req/s.
Parent pointers are stable, and `page.moved` / `database.moved` / `data source.moved` webhooks exist
to invalidate a cache when they are not.

---

## What I could not verify, and why

Listed so nothing above reads as more settled than it is.

**§1 — MCP**

- **No spec guidance on `content` vs `structuredContent` preference.** Neither `2026-07-28` nor
  `2025-11-25` says which the client should feed to the model. SEP-1624 exists precisely because
  this is unclear and is **an open proposal, not adopted spec**
  (<https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1624>). I did not survey
  actual client implementations, so "many clients feed `content` and ignore `structuredContent`" is
  **an inference from the spec's own backwards-compatibility hedge, not a measured claim.**
- **No protocol affordance for "this result has a resolvable parent".** I searched the tools,
  resources, and schema pages; there is no link-relation, typed edge, or `relatedTools` concept. I am
  asserting a negative from reading the spec surface, not from an exhaustive index of every SEP.
- The **Stateful Tools** section is explicitly labelled "non-normative guidance for tool design".
  Cite it as guidance, not as a requirement.

**§2 — Contextual Retrieval**

- **Anthropic publishes no measurement of sibling-chunk discriminability.** The Considerations list
  is quoted complete above and does not touch it. **I found no first-party source on this question
  from anyone.**
- The Anthropic post **does not name the specific datasets** behind the codebases / fiction / ArXiv /
  science-paper corpora, so the 5.7% baseline cannot be independently reproduced from the post alone.
- **The 35% figure does not transfer to a static breadcrumb.** Anthropic prepended LLM-generated,
  *chunk-specific* prose (50–100 tokens, different per sibling). Candidate fix (3) is a shared,
  identical string. **No source I found measures that specific intervention.** Treating the two as
  equivalent would be the single easiest way to get this ADR wrong.
- The one measured regression (arXiv:2510.24402, Claim Recall 47.7 → 42.3) is **third-party, single
  domain (financial QA), single paper, and n=1 on the configurations that regressed.** Its mechanism
  — added shared text diluting a chunk's distinctive keywords — is adjacent to our question but the
  authors did not measure sibling-vs-sibling separation directly.
- **arXiv:2505.24782 ("Context is Gold"):** I read the abstract and metadata only. **I could not
  confirm whether it measures sibling homogenisation.** If this question turns out to be decisive,
  that paper's full text is the next thing to read.
- **arXiv:2409.04701 §4.5** (late chunking vs contextual embedding) is described by its own authors
  as small-scale: one fictional financial document, five chunks. Illustration, not benchmark.

**§3 — LlamaIndex / LangChain**

- **No version or date stamp on any doc page examined** in either framework. Package versions came
  from the PyPI JSON API; source claims are against `master`/`main` HEAD as of 2026-08-14, which may
  drift from the released version.
- **LangChain's how-to prose is recovered from the v0.3.27 git tag**, not the live site, because the
  live site 308-redirects those paths to a generic overview. The class docstrings quoted *are* from
  current `master`. **There may be no citable live URL for that prose** — flagged as a genuine gap.
- The **LangChain negative finding is scoped to `langchain-core`'s contract.** All first-party paths
  embed `page_content` only; I did not audit every third-party vectorstore integration, though they
  all receive `page_content` as the text to embed.
- **`get_leaf_nodes`, `get_root_nodes`, and `simple_ratio_thresh` are undocumented** — confirmed from
  LlamaIndex source only, absent from the module guides and API reference (the `auto_merging`
  reference page renders truncated with the class body missing). Relying on them means relying on
  unversioned surface.
- **`RelatedNodeInfo.hash`** exists and looks like a staleness affordance, but **I found no doc page
  describing an intended invalidation workflow built on it.** Do not assume one exists.
- I did not benchmark either framework; all §3 claims are about mechanism and documentation, **not
  about retrieval quality.**

**§4 — Notion**

- **`database_parent` is not in the OpenAPI `required` list** for `dataSourceObjectResponse`. The
  reference documents it as present; the schema does not guarantee it. Guard against absence.
- **Nothing was tested against a live workspace.** All of §4 is read off the reference, the upgrade
  guide, the changelog, and `openapi.json`.
- The **`agent_id` parent type** is thinly documented — present in the reference and the OpenAPI
  union, but I found no guide explaining when a connector encounters it in practice.
- **I did not separately verify the publication date of the `2026-03-11` upgrade guide page**; the
  changelog entry is dated 11 March 2026.
- Doc/spec drift on `archived` / `in_trash` / `is_archived` is noted in §4.3 and unresolved in the
  published docs.

**Cross-cutting**

- **Nobody I found has published a controlled comparison of the three candidate fixes** — retrieval-
  time resolution vs ingest-time denormalisation vs embedded breadcrumb — on the same corpus. The
  frameworks pick a design; the papers measure contextualisation in general. **The specific
  head-to-head this ticket asks about does not appear to exist in public.**
