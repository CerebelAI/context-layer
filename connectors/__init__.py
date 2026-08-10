"""Owns the platform connectors: pulls raw data out of Notion, Slack and Gmail.

Whatever platform a connector pulls from, what it produces is `Envelope` records.
That model is this module's contract with `knowledge`.

Bottom of the chain `server` -> `knowledge` -> `connectors`; imports from neither.

Write a connector against the real API, never an imagined one. Explore the live
endpoint first to learn the shape it actually returns, then write the tests that lock
that shape, before opening the PR. A test built on a guessed response passes against
the guess and tells you nothing.

Settled: this module persists nothing. A connector pulls, hands its envelopes back
and keeps no copy, and the caller is `main.py`, which passes them to `knowledge`. A
raw-pull store would be a second copy of the platform's own data, stale the moment
it is written and answering no question the platform cannot answer better itself;
the copy worth keeping is the one `knowledge` makes. Re-pulling is cheap and always
current, so a pull is a pass-through. What this costs us is that a pull we did not
keep cannot be replayed -- a change to extraction means going back to the platform
rather than to a cached response. That is the trade we are taking.
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__ = ["Envelope", "NotionError", "notion_client", "pull_notion"]


class Envelope(BaseModel):
    """One record pulled from a platform, in the shape caller consumes.

    A connector's job is to turn whatever its platform returns into these. A
    Notion page, a Slack message and a Gmail thread all arrive as envelopes, and
    nothing downstream has to know which platform a record came from to read its
    title, its parent, when it last changed, or whether it is gone.

    Outside `data` are the fields that mean the same thing on every platform.
    Inside `data` is the vendor payload as the platform returned it. `data` is
    the only vendor-shaped field, and everything platform-specific belongs in
    it: a Notion property map, a Slack thread_ts, a Gmail label list.

    A connector may add to `data` where one call does not return a whole record.
    Notion's search hands over a page's properties but not its body, so the
    Notion connector walks the block tree and puts it under `blocks`. What a
    connector may not do is edit or drop what the platform sent. Any key it adds
    has to be named in its own docstring, and it has to fail rather than
    overwrite if the platform starts sending that key itself -- otherwise
    nothing reading `data` can tell the vendor's value from the connector's.

    Nothing reads `data` yet. It is carried so that extraction can reach a detail
    we did not anticipate without going back to the platform for another pull.

    `text` is the same content with the vendor structure taken off: the words a
    person would read, and nothing else. It is what `knowledge` embeds, and the
    reason it exists is that `data` cannot be embedded. Notion wraps three
    paragraphs in around 3,000 characters of ids, timestamps and JSON, and an
    embedding model reads a few hundred words before it stops -- so a record
    embedded from `data` is embedded from its metadata, and every page comes out
    looking like every other page. Pulling the prose out is work only a connector
    can do, since only it knows where its platform keeps the words.

    It has no default, for the same reason `is_deleted` has none: a connector that
    forgets it produces a record that stores fine, reads back fine, and can never
    be found. `None` is for a record that genuinely has no prose -- a Notion data
    source is a schema, not a document -- not for one whose connector did not
    look.

    `(source, source_id)` is the upsert key, exposed as `upsert_key`. Two
    envelopes with the same pair are the same record, so re-pulling updates the
    stored copy instead of inserting a second one. A connector must therefore put
    the platform's own stable id in `source_id` -- not a title, not a URL, not a
    position in a list. An empty one is rejected outright, since it would collapse
    every record from a source onto a single upsert key.

    Every envelope has a `url`, and it is not optional. Whatever a platform keeps
    information in is something a person can open, so a record with no way back
    to the thing it came from is barely a record. The platform does not always
    hand one over, though: Notion returns a page URL, while Slack and Gmail do
    not. Constructing one there is the connector's job, not grounds for a null.

    `created_at` and `last_modified` must carry a timezone. They get compared
    across platforms -- ordering records, deciding whether a re-pull is newer
    than the stored copy -- and Python refuses to compare a naive datetime with
    an aware one, so one connector dropping the offset breaks ordering for every
    other. Worse is the case that does not raise: a naive local timestamp, once
    stored, reads back as UTC and the record silently moves by hours. Rejecting
    naive at the boundary keeps both out of the store.

    `is_deleted` has no default and every connector has to state it. Defaulting it
    to `False` would mean a connector that forgets it reports every record as
    live, and a record that is gone on the platform but live in the store is a
    wrong answer nothing downstream can detect.

    Frozen, and unknown fields are rejected. An envelope records what a platform
    returned at pull time; editing one downstream would make it a record of
    something else.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["notion", "slack", "gmail"]
    source_id: str = Field(min_length=1)
    url: str
    title: str | None
    text: str | None
    # Carries an id and nothing else: it does not say whether the parent is a
    # page, a database or the workspace root, which in Notion are three
    # different things. Unresolved until we have explored the real API and know
    # what knowledge needs from a parent.
    parent_id: str | None
    created_at: AwareDatetime
    last_modified: AwareDatetime
    is_deleted: bool
    data: dict[str, Any]

    @property
    def upsert_key(self) -> tuple[str, str]:
        """The identity of this record: the same pair means the same record."""
        # Assumes one account per platform. Notion page ids are UUIDs, so it
        # holds today. Slack ids are per-workspace, so two connected workspaces
        # would collide here. The long-term key is probably
        # (source, account_id, source_id), once a second account is real.
        return self.source, self.source_id


# Last, not at the top: a connector imports `Envelope` from here, so this line has
# to run after the class above exists. Every connector's public interface is
# re-exported here, because nothing outside this module may reach into a submodule.
from connectors.notion import NotionError, notion_client, pull_notion
