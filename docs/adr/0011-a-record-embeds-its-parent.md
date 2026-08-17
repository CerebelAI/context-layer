# What a record embeds depends on its parent

**Status: accepted.**

`knowledge` hands the embedder a composed string: the title of the record's parent, then the
record's own title, then its `text`. Until now that string was assembled from one envelope —
`_embed_text` rearranged fields the record already carried. The parent's title comes from a
different record, so a record's vector stops being a function of that record alone. That is
the decision here; the crumb itself is small.

## Why a record's own words are not enough

The #20 port split five ADRs into subpages, and a subpage's title is a section header — *The
question this parks, kept whole*. The words naming its subject live in the parent's title and
appear nowhere in the child. Thirteen of the 44 records are such sections, and four of #18's
ten demo questions target them; against their own words alone there is nothing for those
questions to match.

## Only the immediate parent

The full chain is `Context Layer / Decisions / <ADR title>`. `Context Layer` is on all 44
records and `Decisions` on 23, so both spend tokens and discriminate nothing; the ADR title is
shared by one to four siblings and carries the entire benefit.

Measured with the real tokenizer: the parent title is **+18 tokens, 3.5% of the 512-token
window** — free for all 13 subpages, the largest going 347 → 365, and displacing 13–17 words
of tail on the two records already over the ceiling.

The evidence usually cited for this move does not transfer. Anthropic's Contextual Retrieval
(5.7% → 3.7% failure) prepends LLM-generated prose *specific to each chunk*; a title identical
across siblings is a different intervention, and sibling distinguishability was never measured
there. The one adjacent measurement runs the other way — arXiv:2510.24402 reports Claim Recall
47.7 → 42.3 with contextual chunks, attributed to shared text de-emphasising a chunk's
distinctive keywords. That is the argument for the immediate parent and nothing above it.

## What is stored does not change

The payload is still one envelope and one point, so ADR-0006 is untouched, and `text` is still
the words a person would read and nothing else — the parent's title never enters it, so
neither ADR-0001 nor the connector's job changes. Composition happens in `knowledge`, at
upsert, and the composed string is never stored.

Putting the path in the payload instead was rejected (#26): `Envelope` forbids extra keys, a
test exists to keep it that way, and the MCP write path has no id map to build a path with.

## An unresolved parent is not an error

Resolve from the batch, then from the store, then embed without it. An MCP client may name a
`parent_id` in neither. The record is left weaker, not unfindable, and failing the upsert
would make the write path reject records it has no way to fix. The pull tally reports how many
were embedded without a parent, beside the wordless count it already prints.

## A stale parent title is tolerable here

A rename does not bump the child's `last_modified`, so an embedded parent title can drift.
ADR-0007's full re-pull re-embeds every pulled record, so drift repairs itself each pull; a
record written through MCP is never re-pulled and keeps what it had.

This is tolerable only because the embedded path is never shown. What a reader sees is
resolved live at retrieval (#26), so drift can shift a ranking slightly but can never state
something false. The same staleness in the payload would have been a wrong answer with a
straight face, which is why that option went and this one stays.

## Consequences

- `Store` gains a batched read, needed by the retrieval side (#26) regardless.
- ADR-0010's "seven extra requests" for the database → containing page hop is wrong: every
  data source already carries `database_parent` in the `/search` response the connector makes.
  Amended there.
- `Path` and `Embedded Text` enter the glossary.
