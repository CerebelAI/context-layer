# Connectors are read-only

**Status: accepted.**

A connector reads from a platform and never writes to one. We write only into our own store.
If writing back to a source platform ever becomes a product requirement — creating a Notion
page, posting to Slack — it is a different module, not a capability added to connectors.

The boundary is worth stating out loud because "connector" suggests two-way traffic and the
MCP server does expose a write path, which writes into the store rather than out to a vendor.

Write-back has a different failure model in every dimension that matters: idempotency (a
retried write can post twice), user attribution (whose account is it posted as), permission
scopes (writing needs scopes reading does not, and on Gmail those are more heavily reviewed
still), and partial failure. Mixing those concerns into a module whose whole job is faithful
reading would compromise both.
