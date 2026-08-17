# Decisions

Why the code is shaped the way it is. If a decision is hard to reverse, surprising without
context, or the result of a real trade-off, it belongs here — one paragraph is enough.

Vocabulary lives in [CONTEXT.md](../../CONTEXT.md); open questions live in the issue tracker.
If your work contradicts an ADR, say so and amend it as part of the change.

| | Decision |
|---|---|
| [0001](0001-envelope-is-the-connector-contract.md) | Envelope is the contract between connectors and knowledge |
| [0002](0002-connectors-persist-nothing.md) | Connectors persist nothing |
| [0003](0003-connectors-are-read-only.md) | Connectors are read-only |
| [0004](0004-one-directional-module-imports.md) | Imports flow one way: server → knowledge → connectors |
| [0005](0005-knowledge-stays-sync.md) | knowledge is sync; server bridges |
| [0006](0006-envelope-is-also-the-stored-record.md) | The envelope is also the stored record *(provisional — expires on extracted knowledge)* |
| [0007](0007-full-re-pull-no-incremental-sync.md) | A pull is a full re-pull; there is no incremental sync |
| [0008](0008-adapters-declare-their-sync-guarantees.md) | Adapters declare their sync guarantees *(proposed — nothing built)* |
| [0009](0009-slack-second-gmail-last.md) | Slack is the second connector; Gmail is last |
| [0010](0010-record-is-one-notion-object.md) | A record is one Notion object *(provisional — expires on a divergent source)* |
| [0011](0011-a-record-embeds-its-parent.md) | What a record embeds depends on its parent |
