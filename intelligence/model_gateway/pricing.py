"""Model prices, and what a call actually cost.

Every model call is priced from its reported ``usage`` rather than estimated, so
per-tenant cost attribution is a measurement. Prices are list rates in USD per
million tokens as of September 2026; a negotiated discount is applied downstream
in billing, not here, because this table's job is to be the honest list price.

Cache economics, which is why the gateway bothers with breakpoints: a 5-minute
cache write costs 1.25x base input and a read costs 0.1x, so caching pays for
itself after a single hit. A 1-hour write costs 2x. The gateway writes 5-minute
entries; the agents that work on this repository write both, and their runs are
priced from this same table (`scripts/agent_report.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input_usd: Decimal
    output_usd: Decimal
    cache_read_usd: Decimal
    cache_write_5m_usd: Decimal
    cache_write_1h_usd: Decimal


# Keyed by the bare model id. Provider prefixes are stripped before lookup so
# the same table prices a call on either platform.
MODEL_PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": ModelPrice(
        input_usd=Decimal("5"),
        output_usd=Decimal("25"),
        cache_read_usd=Decimal("0.50"),
        cache_write_5m_usd=Decimal("6.25"),
        cache_write_1h_usd=Decimal("10"),
    ),
    "claude-sonnet-5": ModelPrice(
        input_usd=Decimal("2"),
        output_usd=Decimal("10"),
        cache_read_usd=Decimal("0.20"),
        cache_write_5m_usd=Decimal("2.50"),
        cache_write_1h_usd=Decimal("4"),
    ),
    "claude-haiku-4-5": ModelPrice(
        input_usd=Decimal("1"),
        output_usd=Decimal("5"),
        cache_read_usd=Decimal("0.10"),
        cache_write_5m_usd=Decimal("1.25"),
        cache_write_1h_usd=Decimal("2"),
    ),
}

_MILLION = Decimal("1000000")


class UnknownModelError(KeyError):
    """Raised when a model has no price.

    Deliberately fatal: a call priced at zero silently corrupts every cost
    dashboard and per-tenant budget that reads from it, which is worse than a
    failed request.
    """


def bare_model_id(model: str) -> str:
    """Strip a provider prefix so one price table serves both platforms."""
    return model.removeprefix("anthropic.")


def price_for(model: str) -> ModelPrice:
    key = bare_model_id(model)
    if key not in MODEL_PRICES:
        raise UnknownModelError(
            f"no price for model {model!r}; add it to MODEL_PRICES rather than "
            "letting its cost be recorded as zero"
        )
    return MODEL_PRICES[key]


def cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_write_1h_tokens: int = 0,
) -> Decimal:
    """Cost of one call, from its reported usage.

    ``input_tokens`` is the uncached remainder: the API reports cache reads and
    writes separately, and counting them twice would overstate every cached
    conversation. ``cache_write_tokens`` are 5-minute writes and
    ``cache_write_1h_tokens`` 1-hour writes, because the two are priced apart.
    """
    price = price_for(model)
    return (
        Decimal(input_tokens) * price.input_usd
        + Decimal(output_tokens) * price.output_usd
        + Decimal(cache_read_tokens) * price.cache_read_usd
        + Decimal(cache_write_tokens) * price.cache_write_5m_usd
        + Decimal(cache_write_1h_tokens) * price.cache_write_1h_usd
    ) / _MILLION
