"""The storefront runner's guarantees.

Three of these matter more than the rest, because they encode failures that are
invisible when they happen: a re-run that duplicates the catalog, one storefront
losing another's work, and a site refusing us being logged as a defect on our
side rather than a fact about that source.

No test here touches the network.
"""

from __future__ import annotations

import datetime
import json
import pathlib
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.genesis_api.db import engine
from api.genesis_api.models import IngestionRun, Offer, Product, Storefront
from api.genesis_api.models.enums import IngestionRunStatus, SizeSystem, StorefrontRoute
from api.genesis_api.writer import WriteSpec, write
from intelligence.catalog.fetching import Blocked, DisallowedByRobots, FetchError
from intelligence.catalog.money import FxRates
from intelligence.pipelines.ingest_storefronts import (
    ROUTE_TTL,
    StorefrontTarget,
    fetch_storefront,
    persist,
    run,
    targets,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
RATES = FxRates(
    as_of=datetime.datetime(2026, 9, 5, tzinfo=datetime.UTC),
    usd_per_unit={"EUR": Decimal("1.09")},
)
NOW = datetime.datetime(2026, 9, 5, 12, 0, tzinfo=datetime.UTC)


class FakeFetcher:
    """Serves captured documents; can be told to refuse."""

    def __init__(self, *, refuse: Exception | None = None, ucp: bool = False) -> None:
        self._refuse = refuse
        self._ucp = ucp
        self.requested: list[str] = []

    def get_json(self, url: str) -> Any:
        self.requested.append(url)
        if ".well-known/ucp" in url:
            if not self._ucp:
                raise FetchError("no ucp")
            return {
                "ucp": {
                    "version": "2026-08-25",
                    "services": {
                        "dev.ucp.shopping": [
                            {"transport": "mcp", "endpoint": "https://x.test/mcp", "version": "1"}
                        ]
                    },
                }
            }
        if self._refuse is not None:
            raise self._refuse
        if "meta.json" in url:
            return json.loads((FIXTURES / "everlane_meta.json").read_text())
        if "products.json" in url:
            return json.loads((FIXTURES / "everlane_products.json").read_text())
        raise AssertionError(f"unexpected request {url}")


@pytest.fixture
def session() -> Iterator[Session]:
    connection = engine().connect()
    transaction = connection.begin()
    sess = Session(bind=connection, expire_on_commit=False)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def storefront(session: Session) -> StorefrontTarget:
    result = write(
        session,
        [
            WriteSpec(
                entity="Storefront",
                natural_key={"domain": "runner.test"},
                values={
                    "retailer_name": "Runner Test",
                    "currency": "USD",
                    "size_system": SizeSystem.us,
                    "route": StorefrontRoute.unknown,
                    "enabled": True,
                },
            )
        ],
    )[0]
    session.flush()
    return StorefrontTarget(
        id=result.id,
        domain="runner.test",
        retailer_name="Runner Test",
        brand_name=None,
        currency="USD",
        size_system=SizeSystem.us,
        route=StorefrontRoute.unknown,
        route_checked_at=None,
    )


@contextmanager
def _factory(session: Session) -> Iterator[Session]:
    """A session factory that reuses the test's transaction, so nothing commits."""
    yield session


def test_a_storefront_is_fetched_normalized_and_written(
    session: Session, storefront: StorefrontTarget
) -> None:
    fetched = fetch_storefront(FakeFetcher(), storefront, RATES, now=NOW)
    outcome = persist(session, storefront, fetched, NOW)

    assert outcome.status is IngestionRunStatus.succeeded
    assert outcome.records_seen > 0
    assert outcome.report is not None
    assert outcome.report.products_written == outcome.records_seen


def test_a_second_run_changes_no_row_counts(session: Session, storefront: StorefrontTarget) -> None:
    """The acceptance criterion for this milestone.

    A nightly job that duplicates the catalog on its second night is worse than
    no job, and the failure is invisible until someone counts.
    """

    def counts() -> tuple[int, int]:
        return (
            session.execute(select(func.count()).select_from(Product.__table__)).scalar_one(),
            session.execute(select(func.count()).select_from(Offer.__table__)).scalar_one(),
        )

    persist(session, storefront, fetch_storefront(FakeFetcher(), storefront, RATES, now=NOW), NOW)
    first = counts()
    persist(session, storefront, fetch_storefront(FakeFetcher(), storefront, RATES, now=NOW), NOW)
    second = counts()

    assert first == second
    assert first[0] > 0, "the fixture must actually write something for this to mean anything"


def test_each_attempt_is_recorded_including_repeats(
    session: Session, storefront: StorefrontTarget
) -> None:
    """Runs are append-only: the second attempt does not overwrite the first."""
    for _ in range(2):
        persist(
            session, storefront, fetch_storefront(FakeFetcher(), storefront, RATES, now=NOW), NOW
        )
    runs = session.execute(
        select(func.count())
        .select_from(IngestionRun.__table__)
        .where(IngestionRun.__table__.c.storefront_id == storefront.id)
    ).scalar_one()
    assert runs == 2


def test_a_refusal_is_recorded_as_blocked_not_failed(
    session: Session, storefront: StorefrontTarget
) -> None:
    """A site refusing us is a fact about that source. Filing it as a failure
    would make a rising failure rate unreadable."""
    fetched = fetch_storefront(FakeFetcher(refuse=Blocked("403")), storefront, RATES, now=NOW)
    outcome = persist(session, storefront, fetched, NOW)
    assert outcome.status is IngestionRunStatus.blocked
    assert outcome.report is None
    assert outcome.error


def test_robots_disallow_is_recorded_distinctly(
    session: Session, storefront: StorefrontTarget
) -> None:
    fetched = fetch_storefront(
        FakeFetcher(refuse=DisallowedByRobots("nope")), storefront, RATES, now=NOW
    )
    assert fetched.status is IngestionRunStatus.disallowed


def test_a_broken_feed_is_a_failure(session: Session, storefront: StorefrontTarget) -> None:
    fetched = fetch_storefront(
        FakeFetcher(refuse=FetchError("not JSON")), storefront, RATES, now=NOW
    )
    assert fetched.status is IngestionRunStatus.failed
    assert "FetchError" in (fetched.error or "")


def test_a_failed_storefront_does_not_lose_a_successful_one(
    session: Session, storefront: StorefrontTarget
) -> None:
    """Each storefront commits on its own. An earlier design wrapped the whole
    run in one transaction, and a single dropped connection rolled back every
    storefront's work together."""
    good = fetch_storefront(FakeFetcher(), storefront, RATES, now=NOW)
    persist(session, storefront, good, NOW)
    written = session.execute(select(func.count()).select_from(Product.__table__)).scalar_one()

    bad = fetch_storefront(FakeFetcher(refuse=Blocked("403")), storefront, RATES, now=NOW)
    persist(session, storefront, bad, NOW)
    after = session.execute(select(func.count()).select_from(Product.__table__)).scalar_one()

    assert after == written > 0


def test_the_sanctioned_route_is_discovered_and_recorded(
    session: Session, storefront: StorefrontTarget
) -> None:
    """Recorded even though catalog calls through it are not possible yet, so
    the eventual switch is routing rather than rediscovery."""
    fetched = fetch_storefront(FakeFetcher(ucp=True), storefront, RATES, now=NOW)
    assert fetched.route is StorefrontRoute.ucp
    persist(session, storefront, fetched, NOW)
    stored = session.execute(
        select(Storefront.__table__.c.route).where(Storefront.__table__.c.id == storefront.id)
    ).scalar_one()
    assert stored is StorefrontRoute.ucp


def test_a_fresh_route_is_not_rediscovered(storefront: StorefrontTarget) -> None:
    """Discovery costs a request per storefront per run; the TTL is what stops
    it being paid every night for an answer that rarely changes."""
    fresh = StorefrontTarget(
        **{
            **storefront.__dict__,
            "route": StorefrontRoute.public_feed,
            "route_checked_at": NOW - datetime.timedelta(hours=1),
        }
    )
    fetcher = FakeFetcher()
    fetch_storefront(fetcher, fresh, RATES, now=NOW)
    assert not any(".well-known/ucp" in url for url in fetcher.requested)


def test_a_stale_route_is_rediscovered(storefront: StorefrontTarget) -> None:
    stale = StorefrontTarget(
        **{
            **storefront.__dict__,
            "route": StorefrontRoute.public_feed,
            "route_checked_at": NOW - ROUTE_TTL - datetime.timedelta(days=1),
        }
    )
    fetcher = FakeFetcher()
    fetch_storefront(fetcher, stale, RATES, now=NOW)
    assert any(".well-known/ucp" in url for url in fetcher.requested)


def test_the_registry_override_beats_the_source(storefront: StorefrontTarget) -> None:
    """The fixture storefront states USD; the registry saying EUR must win, since
    that is the operator correcting a source that is wrong about itself."""
    overridden = StorefrontTarget(**{**storefront.__dict__, "currency": "EUR"})
    fetched = fetch_storefront(FakeFetcher(), overridden, RATES, now=NOW)
    assert fetched.profile is not None
    assert fetched.profile.currency == "EUR"


def test_disabled_storefronts_are_not_visited(session: Session) -> None:
    write(
        session,
        [
            WriteSpec(
                entity="Storefront",
                natural_key={"domain": "disabled.test"},
                values={"retailer_name": "Disabled", "currency": "USD", "enabled": False},
            )
        ],
    )
    session.flush()
    domains = [t.domain for t in targets(session)]
    assert "disabled.test" not in domains


def test_the_registry_is_returned_in_a_stable_order(session: Session) -> None:
    """Unordered, Postgres may return any order, and "it reached the third
    storefront" stops meaning anything between runs."""
    for domain in ("zzz.test", "aaa.test", "mmm.test"):
        write(
            session,
            [
                WriteSpec(
                    entity="Storefront",
                    natural_key={"domain": domain},
                    values={"retailer_name": domain, "currency": "USD", "enabled": True},
                )
            ],
        )
    session.flush()
    first = [t.id for t in targets(session)]
    assert first == sorted(first)
    assert first == [t.id for t in targets(session)]


def test_run_processes_the_registry_through_the_factory(
    session: Session, storefront: StorefrontTarget
) -> None:
    summary = run(
        RATES,
        domains=["runner.test"],
        session_factory=lambda: _factory(session),
        fetcher=FakeFetcher(),
    )
    assert len(summary.outcomes) == 1
    assert summary.products_written > 0
    assert summary.quarantine_rate == 0.0


def test_quarantine_rate_has_a_denominator(storefront: StorefrontTarget) -> None:
    """A raw quarantine count says nothing without records seen."""
    from intelligence.pipelines.ingest_storefronts import StorefrontOutcome

    empty = StorefrontOutcome(
        domain="x", status=IngestionRunStatus.succeeded, route=StorefrontRoute.public_feed
    )
    assert empty.quarantine_rate == 0.0
