# Envelope is the contract between connectors and knowledge

**Status: accepted.**

Every connector, whatever platform it reads, produces `Envelope` records. Outside `data` are
the fields that mean the same thing on every platform — identity, url, title, text, parent,
timestamps, deleted — and inside `data` is the vendor payload verbatim. Nothing downstream
has to know which platform a record came from to read it.

## Why `text` exists separately from `data`

Because `data` cannot be embedded. Measured on a captured Notion page, embedding `data`
spends **468 of 512 tokens before reaching the first word of the body** — a page wraps three
paragraphs in roughly 3,000 characters of ids, timestamps and JSON punctuation. A record
embedded from `data` is embedded from its metadata, and every page comes out looking like
every other page. Pulling the prose out is work only a connector can do, since only it knows
where its platform keeps the words.

## Consequences

- `text` and `is_deleted` have no defaults. A connector that forgets `text` produces a record
  that stores fine, reads back fine, and can never be found. A connector that forgets
  `is_deleted` reports a deleted record as live, which is a wrong answer nothing downstream
  can detect. Both must be stated explicitly by every producer.
- `url` is mandatory. Where a platform does not hand one over — Slack and Gmail do not —
  constructing it is the connector's job, not grounds for a null.
- Timestamps must carry a timezone. A naive local timestamp, once stored, reads back as UTC
  and the record silently moves by hours; rejecting naive at the boundary keeps that out.
- Envelopes are frozen and reject unknown fields. An envelope records what a platform
  returned at pull time; editing one downstream would make it a record of something else.
- `data` is append-only. A connector may add keys where one call does not return a whole
  record, but must name each added key in its own docstring and fail rather than overwrite if
  the platform starts sending that key itself — otherwise nothing reading `data` can tell the
  vendor's value from the connector's.

Note that this contract was designed against Notion alone, and two of its clauses — the
`url`-construction rule and the shape of the upsert key (#6) — were written on behalf of
platforms nobody had called yet. See ADR-0009.
