# Slack is the second connector; Gmail is last

**Status: accepted.**

Notion is built. Slack comes next, deliberately thin — only enough to produce real envelopes
from real messages. Gmail comes last. The order is not about which platform customers want
most; it is about what each one costs and what each one teaches.

## Why Slack next rather than more Notion

`Envelope` was designed against exactly one platform, and Notion is the friendliest possible
one: every record has a title, a URL, a parent and a body. Slack has none of those. There is
no title. Identity is the composite `(channel, timestamp)`, not a global id. A permalink is a
separate API call per message. Threading is a pointer to another message's timestamp, not a
parent record id. And the unit worth retrieving is the thread while every change primitive is
per-message — which is the open question about the grain of a record, parked in ADR-0010 and
expiring on exactly this: Slack is the source that makes the two come apart.

The contract already contains two clauses written on Slack's behalf by imagination rather
than by contact — the rule that a connector constructs a `url` where the platform gives none,
and the concession that the upsert key breaks once a second workspace exists (#6). Every day
spent deepening Notion compounds on a contract that has never been falsified. Slack is what
falsifies it, and it should be built shallow enough that discovering the contract is wrong is
cheap.

This is a deliberate deprioritisation of known Notion work, including a live correctness bug
in database-row bodies (#5).

Until Slack exists, `Envelope.source` names only Notion. A contract claiming three platforms
while one is implemented is what licensed writing those two clauses from imagination.

## Why Gmail last: it is a compliance project, not a coding project

Every Gmail read scope is classified **restricted** by Google — including headers-only
metadata. Serving many customer domains requires restricted-scope verification plus an
**annual** third-party security assessment. Verification is documented as potentially taking
several weeks, and revalidation is required at least every twelve months. The published
exemptions — personal use, single-organization internal use — do not cover a multi-tenant
product. Google separately discourages the domain-wide-delegation route in writing.

Taking Gmail on is committing to a recurring external audit, which is a product decision with
a calendar and a cost, not a ticket.

## Both remaining platforms have a gate measured in weeks of waiting, not work

Start the clocks early, in parallel with building — they are queues, not tasks.

- **Slack:** since 2025-05-29, commercially distributed **non-Marketplace** apps are limited
  to 1 request per minute and 15 objects per request on conversation history — roughly 900
  messages per hour per workspace. Marketplace-listed apps are unaffected, and internal
  customer-built apps keep the old 50+/minute at 1,000 per request. The trap: a demo built as
  an internal app in a friendly workspace runs about sixty times faster than the distributed
  product will. Do not size anything from the demo. Tracked as #11.
- **Notion:** serving workspaces we do not control requires a public integration, not the
  internal token in use today. Its installation scope — any workspace versus selected
  workspaces — is fixed at creation and cannot be changed afterwards, and only the former is
  Marketplace-eligible. Choose it deliberately the first time.
