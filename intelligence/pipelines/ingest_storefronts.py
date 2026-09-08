"""Read the storefront registry and fill the catalog.

One storefront at a time: work out how the source should be read, read it,
translate it at the connector boundary, and write the result through the one
write door. Every attempt is recorded, successful or not.

Two properties this job has to have, both learned the hard way.

**Transactions stay short and never span network I/O.** Fetching happens with no
transaction open, and each storefront commits on its own. An earlier version
wrapped the whole run in one transaction: the connection sat idle through
minutes of HTTP, the database dropped it, and every storefront's work rolled
back together. A slow source must not be able to lose a fast one's results.

**Re-running is safe.** Every write goes through the upsert writer keyed on
natural keys, so a second pass updates rather than duplicating. A nightly job
that doubles the catalog on its second night is worse than no job.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import cast

import structlog
from sqlalchemy import Table, select, update
from sqlalchemy.orm import Session

from api.genesis_api.db import write_session
from api.genesis_api.models import Storefront
from api.genesis_api.models.enums import IngestionRunStatus, StorefrontRoute
from api.genesis_api.writer import WriteSpec, write
from intelligence.catalog.connectors.shopify_public import (
    ShopifyPublicConnector,
    StorefrontProfile,
    fetch_storefront_profile,
    iter_storefront_products,
)
from intelligence.catalog.fetching import (
    BlockedError,
    DisallowedByRobotsError,
    FetchError,
    PoliteFetcher,
)
from intelligence.catalog.ingest import IngestReport, ingest
from intelligence.catalog.money import FxRates
from intelligence.catalog.normalized import NormalizationResult
from intelligence.catalog.ucp import UcpUnavailableError, discover

log = structlog.get_logger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]

# How long a discovered route is trusted before being checked again. Merchants
# adopt the sanctioned protocol over time, so a storefront with none last month
# may have one now.
ROUTE_TTL = datetime.timedelta(days=7)


@dataclass(frozen=True)
class StorefrontTarget:
    """A registry row, detached from any session.

    Carried as plain values because the fetch happens between transactions, and
    a mapped object would be attached to a session that is no longer open.
    """

    id: int
    domain: str
    retailer_name: str
    brand_name: str | None
    currency: str | None
    size_system: object | None
    route: StorefrontRoute
    route_checked_at: datetime.datetime | None


@dataclass
class Fetched:
    """What reading one storefront produced, before anything is written."""

    route: StorefrontRoute
    profile: StorefrontProfile | None = None
    normalized: NormalizationResult | None = None
    records_seen: int = 0
    status: IngestionRunStatus = IngestionRunStatus.succeeded
    error: str | None = None


@dataclass
class StorefrontOutcome:
    domain: str
    status: IngestionRunStatus
    route: StorefrontRoute
    records_seen: int = 0
    report: IngestReport | None = None
    error: str | None = None

    @property
    def quarantine_rate(self) -> float:
        """Share of records that could not be read.

        Zero records seen reports zero rather than undefined: a storefront that
        returned nothing has a different problem, and the status says which.
        """
        if not self.records_seen:
            return 0.0
        quarantined = self.report.quarantined if self.report else self.records_seen
        return quarantined / self.records_seen


@dataclass
class RunSummary:
    outcomes: list[StorefrontOutcome] = field(default_factory=list)

    @property
    def products_written(self) -> int:
        return sum(o.report.products_written for o in self.outcomes if o.report)

    @property
    def offers_written(self) -> int:
        return sum(o.report.offers_written for o in self.outcomes if o.report)

    @property
    def records_seen(self) -> int:
        return sum(o.records_seen for o in self.outcomes)

    @property
    def quarantined(self) -> int:
        return sum(o.report.quarantined for o in self.outcomes if o.report)

    @property
    def quarantine_rate(self) -> float:
        return self.quarantined / self.records_seen if self.records_seen else 0.0

    def by_status(self, status: IngestionRunStatus) -> list[StorefrontOutcome]:
        return [o for o in self.outcomes if o.status is status]


def targets(session: Session, domains: list[str] | None = None) -> list[StorefrontTarget]:
    """Read the registry into detached values, in one short transaction."""
    table = Storefront.__table__
    statement = select(
        table.c.id,
        table.c.domain,
        table.c.retailer_name,
        table.c.brand_name,
        table.c.currency,
        table.c.size_system,
        table.c.route,
        table.c.route_checked_at,
    ).where(table.c.enabled.is_(True))
    if domains:
        statement = statement.where(table.c.domain.in_(domains))
    # Ordered so a run is reproducible and resumable. Without it Postgres is free
    # to return any order, which makes "it got to the third storefront" mean
    # nothing between runs.
    statement = statement.order_by(table.c.id)
    return [StorefrontTarget(**dict(row)) for row in session.execute(statement).mappings()]


def resolve_route(fetcher: PoliteFetcher, domain: str) -> StorefrontRoute:
    """Decide how a storefront should be read.

    One that advertises the sanctioned protocol is recorded as such even though
    catalog calls through it need an agent profile we do not yet publish.
    Recording it now makes the eventual switch a routing change rather than a
    rediscovery, and makes adoption measurable meanwhile.
    """
    try:
        discovery = discover(fetcher, domain)
    except (UcpUnavailableError, FetchError):
        return StorefrontRoute.public_feed
    return StorefrontRoute.ucp if discovery.offers_catalog else StorefrontRoute.public_feed


def fetch_storefront(
    fetcher: PoliteFetcher,
    target: StorefrontTarget,
    rates: FxRates,
    *,
    page_size: int = 250,
    max_pages: int = 40,
    now: datetime.datetime | None = None,
) -> Fetched:
    """Read and translate one storefront. No database work happens here.

    Never raises for an expected failure. A site refusing us, or a feed that has
    changed shape, is a fact to record about that source rather than something
    that should abort the job and leave the rest unread.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    route = target.route
    if (
        target.route_checked_at is None
        or route is StorefrontRoute.unknown
        or now - target.route_checked_at > ROUTE_TTL
    ):
        route = resolve_route(fetcher, target.domain)

    try:
        discovered = fetch_storefront_profile(fetcher, target.domain)
        # The registry overrides the source where an operator knows better; the
        # source fills everything else.
        profile = StorefrontProfile(
            domain=target.domain,
            retailer_name=target.retailer_name or discovered.retailer_name,
            currency=target.currency or discovered.currency,
            brand_name=target.brand_name or discovered.brand_name,
            size_system=target.size_system or discovered.size_system,  # type: ignore[arg-type]
        )
        records = list(
            iter_storefront_products(fetcher, profile, page_size=page_size, max_pages=max_pages)
        )
    except DisallowedByRobotsError as exc:
        return Fetched(route=route, status=IngestionRunStatus.disallowed, error=str(exc)[:500])
    except BlockedError as exc:
        return Fetched(route=route, status=IngestionRunStatus.blocked, error=str(exc)[:500])
    except (FetchError, ValueError) as exc:
        return Fetched(
            route=route,
            status=IngestionRunStatus.failed,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )

    connector = ShopifyPublicConnector(profile=profile, rates=rates)
    return Fetched(
        route=route,
        profile=profile,
        normalized=connector.normalize(records),
        records_seen=len(records),
    )


def persist(
    session: Session,
    target: StorefrontTarget,
    fetched: Fetched,
    started_at: datetime.datetime,
) -> StorefrontOutcome:
    """Write one storefront's results. Short, and holds no network I/O open."""
    report: IngestReport | None = None
    if fetched.normalized is not None:
        report = ingest(session, fetched.normalized)

    table = cast(Table, Storefront.__table__)
    values: dict[str, object] = {"route": fetched.route, "route_checked_at": started_at}
    if fetched.status is IngestionRunStatus.succeeded:
        values["last_ingested_at"] = started_at
        if fetched.profile is not None:
            values["currency"] = fetched.profile.currency
    session.execute(update(table).where(table.c.id == target.id).values(**values))

    write(
        session,
        [
            WriteSpec(
                entity="IngestionRun",
                values={
                    "storefront_id": target.id,
                    "status": fetched.status,
                    "route": fetched.route,
                    "started_at": started_at,
                    "finished_at": datetime.datetime.now(datetime.UTC),
                    "records_seen": fetched.records_seen,
                    "products_written": report.products_written if report else 0,
                    "offers_written": report.offers_written if report else 0,
                    "images_written": report.images_written if report else 0,
                    "sizes_written": report.sizes_written if report else 0,
                    "quarantined": report.quarantined if report else 0,
                    "error": fetched.error,
                },
            )
        ],
    )

    outcome = StorefrontOutcome(
        domain=target.domain,
        status=fetched.status,
        route=fetched.route,
        records_seen=fetched.records_seen,
        report=report,
        error=fetched.error,
    )
    log.info(
        "storefront_ingested",
        domain=outcome.domain,
        status=outcome.status.value,
        route=outcome.route.value,
        records_seen=outcome.records_seen,
        products=report.products_written if report else 0,
        quarantined=report.quarantined if report else 0,
        error=outcome.error,
    )
    return outcome


def run(
    rates: FxRates,
    *,
    domains: list[str] | None = None,
    page_size: int = 250,
    max_pages: int = 40,
    session_factory: SessionFactory = write_session,
    fetcher: PoliteFetcher | None = None,
) -> RunSummary:
    """Ingest every enabled storefront, or a named subset.

    Takes a session factory rather than a session: each storefront commits
    independently, so one slow or failing source cannot roll back another's work.
    """
    with session_factory() as session:
        registry = targets(session, domains)

    summary = RunSummary()

    def process(active: PoliteFetcher) -> None:
        for target in registry:
            started = datetime.datetime.now(datetime.UTC)
            # Deliberately outside any transaction: this is where the minutes go.
            fetched = fetch_storefront(
                active, target, rates, page_size=page_size, max_pages=max_pages, now=started
            )
            with session_factory() as session:
                summary.outcomes.append(persist(session, target, fetched, started))

    if fetcher is not None:
        process(fetcher)
    else:
        with PoliteFetcher() as owned:
            process(owned)
    return summary
