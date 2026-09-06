"""The write path's guarantees, tested.

Idempotency and single-write-path are properties the whole ingestion design
rests on: if a re-sync duplicates, the catalog silently doubles, and if two
sources can reach the same fact by different routes, they diverge.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.genesis_api.models import Brand, Product, User, UserConsent
from api.genesis_api.models.enums import Category, Provenance
from api.genesis_api.writer import WriteError, WriteSpec, natural_key_columns, write


def test_write_creates_then_updates_on_the_natural_key(session: Session) -> None:
    """The same natural key written twice is one row, updated - not two rows."""
    spec = WriteSpec(
        entity="Product",
        natural_key={"source": "wtest", "source_id": "sku-1"},
        values={
            "provenance": Provenance.feed_sync,
            "title": "First title",
            "category": Category.dress,
        },
    )
    first = write(session, [spec])[0]
    assert first.created is True

    updated = WriteSpec(
        entity="Product",
        natural_key={"source": "wtest", "source_id": "sku-1"},
        values={"provenance": Provenance.feed_sync, "title": "Revised title"},
    )
    second = write(session, [updated])[0]
    assert second.id == first.id, "same natural key must resolve to the same row"

    count = session.execute(
        select(func.count())
        .select_from(Product.__table__)
        .where(Product.__table__.c.source == "wtest")
    ).scalar_one()
    assert count == 1

    title = session.execute(
        select(Product.__table__.c.title).where(Product.__table__.c.id == first.id)
    ).scalar_one()
    assert title == "Revised title", "the latest write wins"


def test_resync_of_many_rows_is_idempotent(session: Session) -> None:
    """Running the same batch twice leaves the catalog the same size."""
    specs = [
        WriteSpec(
            entity="Product",
            natural_key={"source": "wtest-batch", "source_id": f"sku-{i}"},
            values={"provenance": Provenance.feed_sync, "title": f"Product {i}"},
        )
        for i in range(25)
    ]
    write(session, specs)
    write(session, specs)

    count = session.execute(
        select(func.count())
        .select_from(Product.__table__)
        .where(Product.__table__.c.source == "wtest-batch")
    ).scalar_one()
    assert count == 25


def test_different_sources_converge_on_one_row(session: Session) -> None:
    """A fact written by a sync and then corrected by a user is one row with the
    correction, not two rows keyed by who said it."""
    key = {"source": "wtest-converge", "source_id": "sku-a"}
    write(
        session,
        [
            WriteSpec(
                entity="Product",
                natural_key=key,
                values={"provenance": Provenance.feed_sync, "title": "Sync title"},
            )
        ],
    )
    write(
        session,
        [
            WriteSpec(
                entity="Product",
                natural_key=key,
                values={"provenance": Provenance.user_entry, "title": "Corrected title"},
            )
        ],
    )
    rows = session.execute(
        select(Product.__table__.c.title, Product.__table__.c.provenance).where(
            Product.__table__.c.source == "wtest-converge"
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].title == "Corrected title"
    assert rows[0].provenance == Provenance.user_entry


def test_unknown_entity_raises(session: Session) -> None:
    with pytest.raises(WriteError, match="unknown entity"):
        write(session, [WriteSpec(entity="NotAModel", natural_key={}, values={})])


def test_missing_natural_key_raises_rather_than_inserting(session: Session) -> None:
    """No silent fallbacks: an incomplete key fails loudly instead of creating a
    row the caller cannot find again."""
    with pytest.raises(WriteError, match="natural key requires"):
        write(
            session,
            [
                WriteSpec(
                    entity="Product",
                    natural_key={"source": "wtest"},
                    values={"provenance": Provenance.feed_sync, "title": "x"},
                )
            ],
        )


def test_unknown_column_raises(session: Session) -> None:
    with pytest.raises(WriteError, match="no such columns"):
        write(
            session,
            [
                WriteSpec(
                    entity="Brand",
                    natural_key={"slug": "wtest-brand"},
                    values={"nonexistent_field": 1},
                )
            ],
        )


def test_append_only_entity_records_history(session: Session) -> None:
    """Consent is an event log: withdrawing after granting is two rows, and the
    grant is still there."""
    user = User(auth_subject="wtest-subject", email="consent@example.test")
    session.add(user)
    session.flush()

    now = datetime.datetime.now(datetime.UTC)
    specs = [
        WriteSpec(
            entity="UserConsent",
            values={
                "user_id": user.id,
                "scope": "photo_processing",
                "granted": granted,
                "decided_at": now + datetime.timedelta(seconds=offset),
                "policy_version": "2026-09",
            },
        )
        for offset, granted in enumerate([True, False])
    ]
    results = write(session, specs)
    assert [r.created for r in results] == [True, True]

    rows = (
        session.execute(
            select(UserConsent.__table__.c.granted)
            .where(UserConsent.__table__.c.user_id == user.id)
            .order_by(UserConsent.__table__.c.decided_at)
        )
        .scalars()
        .all()
    )
    assert rows == [True, False], "history is preserved, not overwritten"


def test_natural_keys_match_the_database_constraints(session: Session) -> None:
    """The key the writer upserts on is the key Postgres enforces.

    Derived rather than declared, so the two cannot drift; this asserts the
    derivation actually matches what is in the database.
    """
    from sqlalchemy import text

    actual: dict[str, set[str]] = {}
    for table_name, column_name in session.execute(
        text(
            """
            select tc.table_name, kcu.column_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
            where tc.constraint_type = 'UNIQUE' and tc.table_schema = 'public'
            """
        )
    ):
        actual.setdefault(table_name, set()).add(column_name)

    assert actual, "expected unique constraints in the database"
    assert set(natural_key_columns(Product.__mapper__)) == actual["products"]
    assert set(natural_key_columns(Brand.__mapper__)) == actual["brands"]


def test_a_batch_larger_than_the_parameter_cap_is_split(session: Session) -> None:
    """Postgres accepts at most 65535 bind parameters per statement.

    A wide table reaches that ceiling in a few thousand rows, and the failure is
    a hard error mid-ingest rather than anything graceful, so the writer has to
    split rather than trust that batches stay small.
    """
    specs = [
        WriteSpec(
            entity="Product",
            natural_key={"source": "captest", "source_id": f"sku-{i}"},
            values={
                "provenance": Provenance.feed_sync,
                "title": f"Product {i}",
                "description": "x" * 20,
                "category": Category.dress,
            },
        )
        for i in range(9000)
    ]
    results = write(session, specs)
    assert len(results) == 9000
    assert all(r.created for r in results)

    count = session.execute(
        select(func.count())
        .select_from(Product.__table__)
        .where(Product.__table__.c.source == "captest")
    ).scalar_one()
    assert count == 9000
