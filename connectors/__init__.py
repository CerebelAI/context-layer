"""Owns the platform connectors: pulls raw data out of the platforms we read.

Whatever platform a connector pulls from, what it produces is `Envelope` records.
That model is this module's contract with `knowledge` (ADR-0001).

Bottom of the chain `server` -> `knowledge` -> `connectors`; imports from neither
(ADR-0004). This module persists nothing (ADR-0002): a connector pulls, hands its
envelopes back and keeps no copy. The caller is `main.py`, which passes them to
`knowledge`. It reads only; it never writes to a platform (ADR-0003).

Write a connector against the real API, never an imagined one. Explore the live
endpoint first to learn the shape it actually returns, then write the tests that lock
that shape, before opening the PR. A test built on a guessed response passes against
the guess and tells you nothing.

Notion is the only connector. Slack is next and Gmail last (ADR-0009).
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__ = ["Envelope", "NotionError", "notion_client", "pull_notion"]


class Envelope(BaseModel):
    """One record pulled from a platform, in the shape the caller consumes.

    A connector's job is to turn whatever its platform returns into these, so that
    nothing downstream has to know which platform a record came from to read its
    title, its parent, when it last changed, or whether it is gone. Why the model
    is shaped this way, and why several of its fields have no defaults, is
    ADR-0001.

    Outside `data` are the fields that mean the same thing on every platform.
    `data` is the vendor payload as the platform returned it, and everything
    platform-specific belongs in it: a Notion property map, a Slack thread_ts, a
    Gmail label list. A connector may add to `data` where one call does not return
    a whole record -- Notion's search hands over a page's properties but not its
    body, so the Notion connector walks the block tree and puts it under `blocks`.
    Any key a connector adds must be named in that connector's own docstring, and
    the connector must fail rather than overwrite if the platform starts sending
    that key itself. Nothing reads `data` yet.

    `text` is the same content with the vendor structure taken off: the words a
    person would read, and nothing else. It is what `knowledge` embeds. `None`
    means the record genuinely has no prose -- a Notion data source is a schema,
    not a document -- never that the connector did not look.

    `source_id` is the platform's own stable id: not a title, not a URL, not a
    position in a list. An empty one is rejected, since it would collapse every
    record from a source onto a single upsert key.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Closed on purpose: adding a source is a deliberate edit here, which mypy
    # then turns into a list of every downstream site that needs updating. Only
    # platforms we can actually pull from belong in it (ADR-0009).
    source: Literal["notion"]
    source_id: str = Field(min_length=1)
    url: str
    title: str | None
    text: str | None
    # Carries an id and nothing else -- not what kind of thing the parent is, and
    # not a promise that it resolves (ADR-0010).
    parent_id: str | None
    created_at: AwareDatetime
    last_modified: AwareDatetime
    is_deleted: bool
    data: dict[str, Any]

    @property
    def upsert_key(self) -> tuple[str, str]:
        """The identity of this record: the same pair means the same record."""
        # Assumes one account per platform, which holds while Notion is the only
        # connector. An account-scoped key was weighed and ruled out: there are no
        # accounts to disambiguate yet (#6).
        return self.source, self.source_id


# Last, not at the top: a connector imports `Envelope` from here, so this line has
# to run after the class above exists. Every connector's public interface is
# re-exported here, because nothing outside this module may reach into a submodule.
from connectors.notion import NotionError, notion_client, pull_notion
