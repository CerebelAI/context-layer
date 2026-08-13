# Adapters declare their sync guarantees; the shared layer branches on them

**Status: proposed. Nothing here is built.** This ADR records a design intention so that the
second connector can confirm or refute it, rather than settling it silently in an afternoon.

## The problem

Once there is more than one connector, something has to own scheduling, watermarks,
reconciliation cadence, per-account rate budget, and escalation to a full pull when a
watermark goes stale. Two obvious homes are both wrong:

- **Push it all into each connector** and every platform reimplements the same scheduler.
- **Pull it all into a shared layer above** and that layer has to know that Notion needs a
  trash pass while Gmail has a history feed — platform knowledge, outside the platform module,
  which is the thing an adapter exists to prevent.

## The intended shape

The *algorithm* is genuinely shared and worth writing once, because all three platforms force
periodic reconciliation anyway (ADR-0007). What is irreducibly platform-specific is not the
algorithm but the **guarantees underneath it**:

| | detects edits incrementally | detects deletes incrementally | enumeration exhaustive | watermark can expire |
|---|---|---|---|---|
| Notion | yes, at page grain | webhooks only | not guaranteed, though nothing was missed when measured | no |
| Slack | **no** (edits keep their timestamp) | events only (no tombstone) | yes | no |
| Gmail | yes | yes, while history lives | yes | **yes** |

A `changed_since(watermark)` that means "sound and complete" for Gmail, "additions only" for
Slack, and "best-effort, possibly incomplete" for Notion is a uniform signature over
non-uniform semantics — a leaking abstraction wearing a clean interface.

So: an adapter declares what its change primitive can and cannot see, and the shared layer
branches on that declaration to decide reconciliation cadence. Uniform interface, no lying.

## The prediction this makes, and how to falsify it

Building the Slack connector is the experiment. This ADR predicts that after two real
connectors, the shared surface is **more than** a function returning envelopes — that
capability flags of roughly this shape earn their place.

The honest alternative outcome is that the two connectors share nothing but their return
type, in which case there is no interface to write and the current naming convention was
right all along. Amend this ADR rather than building toward it.

Deliberately not built yet, because the project's own rule is no base classes until there are
at least two concrete cases demanding them, and every row of that table except Notion's comes
from reading documentation rather than from a connector we have run.

## The fact that decided the Notion row, since measured

Whether editing a block deep inside a Notion page moves that page's `last_edited_time` is
**undocumented** — neither the Page nor the Block reference states it. Measured live (#4,
#14): it does. A paragraph edited three levels deep bumped its page, on a prose page and on a
database row alike. So Notion can be polled by timestamp, and the webhook is not its only
sound change primitive.

Two riders, both load-bearing for anything built on this. The **intermediate blocks did not
move** — propagation targets the page and skips every ancestor block, so pruning a block walk
by a container's timestamp would silently skip edited subtrees; the page is the only unit
whose timestamp can be trusted. And timestamps are truncated to the minute, so a watermark
would need an overlap window of at least a minute or it misses same-minute edits.
