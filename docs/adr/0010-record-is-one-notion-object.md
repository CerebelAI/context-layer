# A record is one Notion object; the grain question waits for a divergent source

**Status: provisional.** This holds while Notion is the only connector, and expires on the
trigger named below rather than on a date.

One record is one object Notion gives an id to: a prose page, a database row (a page too, as
far as Notion is concerned), or a data source. That is what the connector already emits —
`RECORD_BOUNDARY_BLOCKS` stops the block walk at `child_page` and `child_database`, so a
page's body never swallows a record that stands on its own.

Notion-only this is close to forced, because the platform object and the unit worth
retrieving are the same thing: a page has its own id, title and URL, and a person would open
exactly that page to read the answer. The question is only hard where those two come apart.

## The question this parks, kept whole

Issue #7 asked which of two grains a record follows. It is recorded here rather than left
open, because nothing can act on it until a second connector exists:

- **(a) One platform object** — a Notion page, a Slack message, a Gmail message. Assembling
  threads is `knowledge`'s problem.
- **(b) One retrievable unit** — a Notion page, a Slack *thread*, a Gmail *thread*. The
  connector assembles and emits one envelope per thread.

They agree on Notion and diverge on the other two, because the grain that is cheap to detect
changes on is smaller than the grain worth retrieving:

- Slack: every change primitive is per-message (`conversations.history`, `message_changed`,
  `message_deleted`), but the meaningful unit is the thread. Replies are not even returned by
  `conversations.history` — they need `conversations.replies` per parent, so enumeration is a
  two-level fan-out either way.
- Gmail: `users.history.list` is message-level only, but a thread carries its own `historyId`.
  A new message joining a thread changes the thread's meaning with no thread-level event.

Option (b) also makes records longer, which makes the ~400-word embedding ceiling bite
sooner (#9).

## What expires this

**The first source whose change primitive is smaller than the unit worth retrieving.** Not
"a second source" — a second page-shaped platform leaves this decision intact, and expiring
it then would cost a re-decision for nothing. Slack is the expected trigger (ADR-0009), and
whoever builds it settles (a) versus (b) for real, then amends this ADR.

## A record with no words of its own is still a record

A hub page — one whose body is nothing but links to its children — carries no prose, because
every word lives in a record of its own. Measured on the live workspace: of the 42 blocks
across wordless prose pages, 40 are `child_page` or `child_database`. `Northwind Robotics` is
one paragraph and three child pages; `Operations` is three child databases. A data source is
the same shape — a schema whose rows are records in their own right.

They stay records anyway. Identity and deletion need them: a hub that is trashed has to be
able to say so, and it can only say so if it is a record. The `parent_id` chain resolves to
them. And their titles are real retrieval signal — `Operations`, `Projects` — which is
exactly what a person searches for when they do not know which page holds the answer.

The cost is real and belongs to a different question: on the live workspace this is 45
records embedded on their title alone, and three with neither title nor prose that fall back
to their URL, which matches nothing a person would type. Whether a wordless record earns a
place in the *index* is #16, not this. One record is still one point, so ADR-0006 is
untouched.

## `parent_id` relays the platform's pointer; it may dangle

It carries the id Notion gives as the parent and nothing else — not what kind of thing the
parent is. It is **not** a promise that the parent is a record we hold.

Measured: 230 of 238 parent ids resolve to a record in the same pull, one is the workspace
root, and **seven dangle — every data source**. A data source's parent is a `database_id`,
while `/search` returns *data sources*, and the two have been different ids since API version
`2025-09-03`. Notion is not lying; we simply do not hold databases as records.

Typing the field would not fix that — knowing an id names a database still does not name
anything we hold — and for the 230 that resolve, the id alone is unambiguous, because you
hold the thing it names and can ask it what it is. So the field stays as it is and the
promise it makes gets written down instead. Making the chain resolve — hopping database →
containing page, seven extra requests — is filed as build work, and is what would promote
this from a relay to a real pointer.

Issue #8 asked whether to keep it untyped, type it, or drop it; this is the answer for as
long as Notion is the only source. What a parent *means* across platforms stays undecidable
until there is a second one: on Slack it is `thread_ts` — a pointer to another message's
timestamp, not a parent record id, and a parent retains it even after every reply is deleted.
On Gmail it is thread membership, which is not a parent relationship at all.
