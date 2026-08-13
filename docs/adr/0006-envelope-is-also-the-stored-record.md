# The envelope is also the stored record

**Status: provisional.** This holds for the demo, and expires on the trigger named below rather
than on a date: the first time the store must hold extracted knowledge alongside source records.

There is no second storage template. What a connector produces is what the store keeps,
scoped to a tenant. Re-ingesting a record overwrites the stored copy rather than inserting a
second one, which is what makes a repeated pull safe: there is no separate update path and no
duplicate to clean up.

## Consequences

- Connectors are not privileged producers. The MCP write path produces envelopes too, and
  reaches the store the same way.
- The tenant is passed alongside an envelope rather than carried on it, because a tenant is
  ours and an envelope records what a platform returned.
- One record is one point in the store, and identity, upsert and delete all rest on that.
  Which is why splitting a long record across several points is not a small change.

## The retrieval ceiling this creates

One vector represents about 400 words. A longer record is findable by its opening and
returned in full — the payload is complete regardless of what was embedded. Splitting a
record across several points is the fix and is not done, because it would break the
one-point-per-record model above. Tracked as #9.

Relatedly, the similarity threshold is not tuned: it came from another project where it gated
embeddings of a clean `title. summary`. In a fixture run against Notion pages the right record
scored 0.845 while unrelated records — including pages titled with only whitespace or emoji —
sat between 0.60 and 0.72, all above the bar. The signal is there; the cut is in the wrong
place. Re-derive it against a real pull: #10.
