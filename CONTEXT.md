# Context Layer

The vocabulary this project uses. One word per concept, chosen deliberately — where several
words exist for the same thing, the alternatives are listed under _Avoid_ so nobody has to
guess which one we meant.

This file is a glossary and nothing else. Decisions live in [docs/adr/](docs/adr/); open
questions live in the issue tracker.

## Pulling

**Connector**:
A read-only adapter for exactly one source. It knows how to talk to that platform's API and
how to turn what comes back into envelopes; it knows nothing about what happens next.
_Avoid_: integration, importer, adapter, provider

**Source**:
The platform a connector reads from. A source is a kind of system, not a particular
customer's instance of one. Notion is the only one; ADR-0009 says which comes next.
_Avoid_: provider, vendor, integration, platform (in code; fine in prose)

**Pull**:
One complete run of one connector against its source, producing envelopes. A pull either
completes or fails; there is no partial pull.
_Avoid_: sync, fetch, import, crawl, scrape

## The record

**Envelope**:
What a connector produces: one record from a platform, in the shape everything downstream
consumes. Whatever platform it came from, an envelope reads the same.
_Avoid_: document, item, payload, message, entity

**Record**:
The thing an envelope describes — one object the platform gives an id to. On Notion: a prose
page, a database row, or a data source. A record whose every word lives in its children — a
hub page, a data source — is a record even so.

Provisional while Notion is the only source: ADR-0010 carries the grain decision, the two
candidates it parks, and what expires it.

**Upsert Key**:
The identity of a record: two envelopes carrying the same key are the same record, so a
re-pull updates the stored copy rather than adding a second one. There is no separate update
path and no duplicate to clean up.
_Avoid_: primary key, id, dedupe key

**Data**:
The vendor payload, exactly as the platform returned it. The only vendor-shaped part of an
envelope; anything platform-specific belongs here. Append-only — a connector may add to it,
never edit or drop what the platform sent.
_Avoid_: raw, payload, metadata, properties, extra

**Text**:
The same content as `data` with the vendor structure taken off: the words a person would
read, and nothing else. Producing it is work only a connector can do, because only it knows
where its platform keeps the words.
_Avoid_: body, content, plaintext

## Beyond the connectors

**Tenant**:
One of our customers, and the isolation boundary: every stored record is scoped to a tenant,
and no query crosses tenants.
_Avoid_: organization, company, customer (in code), account, workspace

**Store**:
Where envelopes live once ingested, and the only thing that persists anything.
_Avoid_: database, index, vector store, cache
