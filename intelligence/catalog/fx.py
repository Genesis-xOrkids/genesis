"""Exchange rates for normalizing prices to USD.

Rates are a dated snapshot, not a live feed, and the date travels with every
converted price onto the offer row. That is the property that matters: a stale
rate produces a price that is wrong by a knowable amount, auditable after the
fact, rather than one that is silently wrong forever.

Replacing this with a live source is a change to :func:`current_rates` alone.
Nothing else needs to know where a rate came from.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import structlog

from intelligence.catalog.money import FxRates

log = structlog.get_logger(__name__)

# Rates are USD per one unit of the quoted currency, as of the date below.
SNAPSHOT_DATE = datetime.datetime(2026, 9, 5, tzinfo=datetime.UTC)

SNAPSHOT: dict[str, Decimal] = {
    "EUR": Decimal("1.09"),
    "GBP": Decimal("1.27"),
    "CAD": Decimal("0.73"),
    "AUD": Decimal("0.65"),
    "CHF": Decimal("1.13"),
    "SEK": Decimal("0.093"),
    "DKK": Decimal("0.146"),
    "NOK": Decimal("0.091"),
    "JPY": Decimal("0.0067"),
    "KRW": Decimal("0.00072"),
    "SGD": Decimal("0.74"),
    "HKD": Decimal("0.128"),
    "NZD": Decimal("0.60"),
    "MXN": Decimal("0.050"),
    "BRL": Decimal("0.18"),
    "INR": Decimal("0.012"),
    "PLN": Decimal("0.25"),
    "CZK": Decimal("0.043"),
}

# Beyond this the snapshot is reported as stale on every use. Conversion still
# happens, because a listed price with a knowably old rate is more useful than
# no comparable price at all, and fx_rate_at records exactly how old.
STALE_AFTER = datetime.timedelta(days=30)


def current_rates(*, now: datetime.datetime | None = None) -> FxRates:
    """The rates to convert with, and how old they are."""
    now = now or datetime.datetime.now(datetime.UTC)
    age = now - SNAPSHOT_DATE
    if age > STALE_AFTER:
        log.warning(
            "fx_snapshot_stale",
            snapshot_date=SNAPSHOT_DATE.date().isoformat(),
            age_days=age.days,
            detail="converted prices carry this date and can be recomputed",
        )
    return FxRates(as_of=SNAPSHOT_DATE, usd_per_unit=dict(SNAPSHOT))
