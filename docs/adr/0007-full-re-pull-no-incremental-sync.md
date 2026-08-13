# A pull is a full re-pull; there is no incremental sync

**Status: accepted.**

Every pull enumerates everything the credential can see and re-emits all of it. Deletions are
found by a second full pass over the platform's trash. There is no watermark, no change
detection, and nothing persisted between runs.

This is deliberate as an ordering, not as an end state: getting the mechanism to pull
faithfully is worth more right now than keeping it fresh cheaply. Fidelity first, freshness
second, breadth third — see ADR-0009 for the third.

## Full re-pull is also permanent, not only temporary

Worth knowing before treating incremental sync as a replacement rather than an addition: none
of the three platforms lets you stop doing this.

- **Notion** webhooks are documented as *at-most-once* delivery with no replay endpoint, so
  they cannot be the system of record.
- **Slack**'s Events API is explicitly best-effort with no documented backfill for downtime.
  Worse for polling: an edited message keeps its original timestamp, so it never re-enters a
  "since X" window, and a deleted message simply stops appearing in history with no tombstone.
  Poll-based incremental sync of Slack is structurally blind to both edits and deletions.
- **Gmail**'s history ids expire — "typically at least one week", sometimes much less — and a
  stale one returns 404 with full resync as the only documented recovery.

So reconciliation is a permanent code path for Notion, and is the one that exists — the second
pass over the trash in `connectors/notion.py`. Incremental sync, when it comes, is expected to
layer over reconciliation as a latency optimisation rather than replace it, with push
notifications an optimisation over that.

## The unquantified part, which is the actual risk

We do not know where full re-pull stops being correct. Nobody has numbers for the largest
workspace we expect, the longest acceptable pull, or how stale a store may be before a
customer notices — and without them "full re-pull is fine for now" is a hope rather than a
decision. It also leaves *what a pull run even is* — a batch job, a long-running service,
something else — undecided. That was tracked as #2 and closed unanswered: all three unknowns
are market facts, and there is no market yet to read them from.

Two known costs, for scale: today's Notion pull is roughly 90 sequential requests against a
seeded workspace with no concurrency; fixing database-row bodies (#5) takes it to roughly 270.
Notion's rate limit is ~3 requests/second **per connection**, shared across every customer,
so one large workspace degrades everyone. Gmail's quota is per Google Cloud project, with the
same property. Slack's is per workspace per app, and is the only one of the three that
isolates customers from each other.

## The fidelity limit, since measured

Enumeration rests on Notion's search endpoint, which Notion documents as *"not guaranteed to
return everything"*, with an index that *"may change as your connection iterates"*. Search
was chosen because it is a strict superset of walking the page tree — the tree misses every
database row — but that trade bought row coverage at the cost of exhaustiveness.

Measured since, against the live workspace (#3, #14). Two independent enumerations that
bypass the search index — querying every data source directly, and walking the block tree —
found **nothing search missed**: 225 records, reconciling exactly, stable across back-to-back
passes. The same Notion page carries a guarantee this ADR first omitted — pages *directly
shared* with a connection **are** returned — which is what turns the documented risk into a
bounded one.

What survives is a sharing limit, not an index limit: a page never shared with the
integration is invisible to every path, and no API answers for it. Two smaller limits stand —
roughly 26 seconds before a new page reaches the search index, and timestamps truncated to
the minute.
