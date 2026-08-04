"""Locks the connectors -> knowledge contract: what an Envelope guarantees.

Every test here fails if one of our decisions is reversed. Tests that would only
re-exercise Pydantic are deliberately absent.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from connectors import Envelope

# Shaped like a Notion page object, so that what `data` has to survive is
# concrete rather than a toy dict. Nothing here claims Notion actually returns
# this -- the real response shape gets locked by the Notion connector's own
# tests once we have explored the API. This pins only what an Envelope carries.
NOTION_PAGE: dict[str, Any] = {
    "object": "page",
    "id": "59833787-2cf9-4fdf-8782-e53db20768a5",
    "created_time": "2022-03-01T19:05:00.000Z",
    "last_edited_time": "2022-07-06T19:16:00.000Z",
    "created_by": {"object": "user", "id": "ee5f0f84-409a-440f-983a-a5315961c6e4"},
    "cover": {"type": "external", "external": {"url": "https://example.com/cover.jpg"}},
    "icon": {"type": "emoji", "emoji": "🥬"},
    "parent": {
        "type": "database_id",
        "database_id": "d9824bdc-8445-4327-be8b-5b47500af6ce",
    },
    "archived": False,
    "in_trash": False,
    "properties": {
        "Name": {
            "id": "title",
            "type": "title",
            "title": [
                {
                    "type": "text",
                    "text": {"content": "Tuscan kale", "link": None},
                    "annotations": {"bold": False, "code": False, "color": "default"},
                    "plain_text": "Tuscan kale",
                    "href": None,
                }
            ],
        },
        "Store availability": {
            "id": "%3AUPp",
            "type": "multi_select",
            "multi_select": [
                {"id": "t|O@", "name": "Rainbow Grocery", "color": "yellow"}
            ],
        },
        "Number of meals": {"id": "Z%5CeU", "type": "number", "number": 2},
    },
    "url": "https://www.notion.so/Tuscan-kale-598337872cf94fdf8782e53db20768a5",
    "public_url": None,
}

BASE: dict[str, Any] = {
    "source": "notion",
    "source_id": "59833787-2cf9-4fdf-8782-e53db20768a5",
    "url": "https://www.notion.so/Tuscan-kale-598337872cf94fdf8782e53db20768a5",
    "title": "Tuscan kale",
    "parent_id": "d9824bdc-8445-4327-be8b-5b47500af6ce",
    "created_at": datetime(2022, 3, 1, 19, 5, tzinfo=UTC),
    "last_modified": datetime(2022, 7, 6, 19, 16, tzinfo=UTC),
    "is_deleted": False,
    "data": NOTION_PAGE,
}


def make_envelope(**overrides: Any) -> Envelope:
    return Envelope(**{**BASE, **overrides})


def test_envelope_has_exactly_these_fields() -> None:
    # extra="forbid" rejects unknown input; it says nothing about a field added
    # to the model. Reversing "visibility and owner stay out", or slipping in a
    # `kind`, is otherwise silent.
    assert set(Envelope.model_fields) == {
        "source",
        "source_id",
        "url",
        "title",
        "parent_id",
        "created_at",
        "last_modified",
        "is_deleted",
        "data",
    }


def test_data_survives_a_round_trip_verbatim() -> None:
    envelope = make_envelope()

    restored = Envelope.model_validate_json(envelope.model_dump_json())

    assert restored.data == NOTION_PAGE
    assert restored == envelope

    # The four ways a payload degrades quietly: a null dropped, nesting
    # flattened, a number stringified, and a string that happens to look like a
    # timestamp getting parsed into one.
    assert restored.data["public_url"] is None
    assert restored.data["properties"]["Name"]["title"][0]["text"]["content"] == (
        "Tuscan kale"
    )
    assert restored.data["properties"]["Number of meals"]["number"] == 2
    assert isinstance(restored.data["created_time"], str)


def test_unknown_top_level_field_is_rejected() -> None:
    fields = dict(BASE)
    fields["kind"] = "page"

    with pytest.raises(ValidationError):
        Envelope(**fields)


@pytest.mark.parametrize("field", ["created_at", "last_modified"])
def test_naive_datetime_is_rejected(field: str) -> None:
    fields = dict(BASE)
    # The missing tzinfo is the subject of the test, not an oversight.
    fields[field] = datetime(2022, 3, 1, 19, 5)  # noqa: DTZ001

    with pytest.raises(ValidationError):
        Envelope(**fields)


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_envelope(source_id="")


def test_is_deleted_has_no_default() -> None:
    fields = dict(BASE)
    del fields["is_deleted"]

    with pytest.raises(ValidationError):
        Envelope(**fields)


def test_envelope_is_frozen() -> None:
    envelope = make_envelope()

    with pytest.raises(ValidationError):
        envelope.title = "Renamed after the fact"


def test_title_may_be_none() -> None:
    assert make_envelope(title=None).title is None


def test_top_level_record_with_no_parent_is_representable() -> None:
    workspace_root = {**NOTION_PAGE, "parent": {"type": "workspace", "workspace": True}}

    envelope = make_envelope(parent_id=None, data=workspace_root)

    assert envelope.parent_id is None
    # The vendor's own idea of a workspace parent stays inside `data`. The
    # source-agnostic field says only that there is no parent record.
    assert envelope.data["parent"] == {"type": "workspace", "workspace": True}


def test_upsert_key_is_source_and_source_id() -> None:
    first = make_envelope()
    repulled = make_envelope(
        title="Tuscan kale, renamed",
        last_modified=datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
        data={"object": "page", "id": "59833787-2cf9-4fdf-8782-e53db20768a5"},
    )
    another_record = make_envelope(source_id="d9824bdc-8445-4327-be8b-5b47500af6ce")

    assert first.upsert_key == ("notion", "59833787-2cf9-4fdf-8782-e53db20768a5")
    # A re-pull of the same record updates it; a different record inserts.
    assert repulled.upsert_key == first.upsert_key
    assert another_record.upsert_key != first.upsert_key
