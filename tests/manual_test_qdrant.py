"""Manual round trip against the real Qdrant cluster. Run:

    uv run python -m tests.manual_test_qdrant

Named `manual_test_` so pytest does not collect it: the collected tests use a
double and never touch the network, and this one is the opposite of that. It is
what actually proves the Qdrant calls are right, which the unit tests cannot.

Writes under its own tenant and deletes what it wrote, so it is safe to re-run
against a collection holding real records. The first run downloads the embedding
model (~130MB) before anything happens.

Requires the same three QDRANT_* variables as `main.py`.
"""

import sys
from datetime import UTC, datetime

from qdrant_client import QdrantClient

from connectors import Envelope
from knowledge import Store
from main import _required

TENANT = "manual-test-tenant"
OTHER_TENANT = "manual-test-other-tenant"


def envelope(
    source_id: str, title: str, body: str, is_deleted: bool = False
) -> Envelope:
    return Envelope(
        source="notion",
        source_id=source_id,
        url=f"https://www.notion.so/{source_id}",
        title=title,
        # The searchable surface. `data` holds the same words, and deliberately
        # does not reach the embedder -- so a check that finds these records by
        # their body is checking that `text` survived the round trip.
        text=body,
        parent_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_modified=datetime(2026, 2, 1, tzinfo=UTC),
        is_deleted=is_deleted,
        data={"object": "page", "body": body},
    )


ONBOARDING = envelope(
    "manual-onboarding",
    "Engineering onboarding",
    "New engineers get a laptop on day one, then pair with a buddy for two weeks.",
)
EXPENSES = envelope(
    "manual-expenses",
    "Expense policy",
    "Claim expenses in Pleo within 30 days. Anything over 500 EUR needs approval.",
)
RETIRED = envelope(
    "manual-retired",
    "Retired runbook",
    "The old deploy runbook, since removed from the workspace.",
    is_deleted=True,
)


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def write_and_search(store: Store) -> None:
    section("upsert -> search")
    written = store.upsert([ONBOARDING, EXPENSES, RETIRED], tenant_id=TENANT)
    print(f"wrote {written} records")
    assert written == 3

    matches = store.search("how do new engineers get set up?", tenant_id=TENANT)
    for match in matches:
        print(f"  {match.score:.3f}  {match.envelope.title}")
    assert matches, "expected the onboarding record to come back"
    assert matches[0].envelope.source_id == ONBOARDING.source_id, (
        "onboarding should outrank the expense policy for this query"
    )
    # The body only exists inside `data`, so this failing means _embed_text is
    # not reaching the payload.
    assert any("buddy" in m.envelope.data["body"] for m in matches)


def deleted_records_stay_out_of_search(store: Store) -> None:
    section("search skips records deleted on their platform")
    matches = store.search("old deploy runbook", tenant_id=TENANT)
    titles = [m.envelope.title for m in matches]
    print(f"  returned: {titles}")
    assert RETIRED.title not in titles, (
        "a platform-deleted record must not be an answer"
    )

    got = store.get("notion", RETIRED.source_id, tenant_id=TENANT)
    assert got is not None, "but it must still be fetchable by key"
    assert got.is_deleted is True
    print("  still fetchable by key, is_deleted=True")


def round_trips_verbatim(store: Store) -> None:
    section("get returns exactly what was written")
    got = store.get("notion", ONBOARDING.source_id, tenant_id=TENANT)
    assert got == ONBOARDING, "the stored record must survive the round trip unchanged"
    print(f"  {got.title!r} identical after a round trip through Qdrant")


def re_ingesting_overwrites(store: Store) -> None:
    section("re-ingesting the same key updates rather than duplicating")
    revised = envelope(
        ONBOARDING.source_id,
        "Engineering onboarding, revised",
        "New engineers get a laptop on day one, then pair with a buddy for three weeks.",
    )
    store.upsert([revised], tenant_id=TENANT)

    got = store.get("notion", ONBOARDING.source_id, tenant_id=TENANT)
    assert got is not None
    assert got.title == revised.title, "the stored copy should have been updated"

    matches = store.search("how do new engineers get set up?", tenant_id=TENANT)
    same_key = [m for m in matches if m.envelope.source_id == ONBOARDING.source_id]
    print(f"  {len(same_key)} point for that key (expect 1), title now {got.title!r}")
    assert len(same_key) == 1, "re-ingesting must not create a second point"


def tenants_cannot_see_each_other(store: Store) -> None:
    section("tenant isolation")
    matches = store.search("how do new engineers get set up?", tenant_id=OTHER_TENANT)
    print(f"  other tenant search returned {len(matches)} match(es), expect 0")
    assert matches == [], "another tenant must not see these records"

    assert store.get("notion", ONBOARDING.source_id, tenant_id=OTHER_TENANT) is None
    assert store.delete("notion", ONBOARDING.source_id, tenant_id=OTHER_TENANT) is False
    print("  cross-tenant get and delete both refused")


def deletes_what_it_wrote(store: Store) -> None:
    section("delete")
    for record in (ONBOARDING, EXPENSES, RETIRED):
        assert store.delete("notion", record.source_id, tenant_id=TENANT) is True
        assert store.get("notion", record.source_id, tenant_id=TENANT) is None
    print(
        f"  removed {ONBOARDING.source_id}, {EXPENSES.source_id}, {RETIRED.source_id}"
    )

    assert store.delete("notion", ONBOARDING.source_id, tenant_id=TENANT) is False
    print("  deleting again reports False")


def discard_leftovers(store: Store) -> None:
    """Best-effort tidy-up on the way out of a failed run.

    Deliberately silent about what it finds: if an earlier step raised, that
    exception is the one worth seeing, and a cleanup assertion firing on top of it
    buries the cause under an unrelated failure.
    """
    for record in (ONBOARDING, EXPENSES, RETIRED):
        store.delete("notion", record.source_id, tenant_id=TENANT)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    client = QdrantClient(
        url=_required("QDRANT_CLUSTER_URL"), api_key=_required("QDRANT_API_KEY")
    )
    store = Store(client, _required("QDRANT_COLLECTION_NAME"))
    store.ensure_collection()

    try:
        write_and_search(store)
        deleted_records_stay_out_of_search(store)
        round_trips_verbatim(store)
        re_ingesting_overwrites(store)
        tenants_cannot_see_each_other(store)
        deletes_what_it_wrote(store)
    except Exception:
        discard_leftovers(store)
        raise

    print("\nAll Qdrant round-trip checks passed.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
