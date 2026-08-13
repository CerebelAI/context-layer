# Connectors persist nothing

**Status: accepted.**

A connector pulls, hands its envelopes back, and keeps no copy. A raw-pull store would be a
second copy of the platform's own data, stale the moment it is written, answering no question
the platform cannot answer better itself. The copy worth keeping is the one the store makes.

## Consequences

- A pull we did not keep cannot be replayed. A change to extraction means going back to the
  platform rather than to a cached response. That is the trade we are taking.
