"""Currency handling at the connector boundary.

A price is two facts - an amount and the currency it is quoted in - plus one
derived value, the USD equivalent, which only exists once somebody records the
rate that produced it. Storing a bare number invites the failure this module
exists to prevent: a JPY 12,000 listing read as $12,000.

Minor units are the second trap. "Amount in minor units" is not "amount times
100": JPY and KRW have no minor unit at all, and the dinar currencies have three
decimal places. A converter that assumes two is wrong by a factor of a hundred
in one direction and a thousand in the other.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 exponents for the currencies fashion retail actually quotes in.
# Anything absent is rejected rather than assumed to have two decimals, because
# a wrong guess here is silent and large.
CURRENCY_EXPONENTS: dict[str, int] = {
    "AED": 2,
    "AUD": 2,
    "BRL": 2,
    "CAD": 2,
    "CHF": 2,
    "CNY": 2,
    "CZK": 2,
    "DKK": 2,
    "EUR": 2,
    "GBP": 2,
    "HKD": 2,
    "HUF": 2,
    "IDR": 2,
    "ILS": 2,
    "INR": 2,
    "ISK": 0,
    "JPY": 0,
    "KRW": 0,
    "MXN": 2,
    "MYR": 2,
    "NOK": 2,
    "NZD": 2,
    "PHP": 2,
    "PLN": 2,
    "RON": 2,
    "SEK": 2,
    "SGD": 2,
    "THB": 2,
    "TRY": 2,
    "TWD": 2,
    "USD": 2,
    "VND": 0,
    "ZAR": 2,
}

USD = "USD"


class CurrencyError(ValueError):
    """Raised when an amount cannot be interpreted with certainty.

    Always raised, never defaulted: a price silently coerced to the wrong
    magnitude reaches a user as a recommendation they cannot afford, or a
    budget filter that quietly excludes everything.
    """


def exponent_for(currency: str) -> int:
    code = currency.strip().upper()
    if code not in CURRENCY_EXPONENTS:
        raise CurrencyError(
            f"unknown currency {currency!r}; add its ISO 4217 exponent to "
            "CURRENCY_EXPONENTS rather than assuming two decimal places"
        )
    return CURRENCY_EXPONENTS[code]


def to_minor_units(amount: Decimal | str | int | float, currency: str) -> int:
    """Convert a decimal amount to whole minor units for its currency.

    ``12.34 USD`` is 1234 cents; ``12000 JPY`` is 12000 yen, not 1200000.
    """
    if isinstance(amount, float):
        # A float price has already lost precision; make the caller pass the
        # string or Decimal the source actually gave us.
        raise CurrencyError(
            f"refusing to convert float {amount!r}: pass the source's string or "
            "Decimal so rounding happens once, here"
        )
    value = Decimal(str(amount))
    if value < 0:
        raise CurrencyError(f"negative amount {amount!r}")
    scaled = value.scaleb(exponent_for(currency))
    if scaled != scaled.to_integral_value():
        # More precision than the currency has. Round explicitly rather than
        # truncating silently.
        scaled = scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(scaled)


def from_minor_units(minor: int, currency: str) -> Decimal:
    """Inverse of :func:`to_minor_units`, for display and for FX."""
    return Decimal(minor).scaleb(-exponent_for(currency))


@dataclass(frozen=True)
class FxRates:
    """A dated set of rates to USD.

    Dated on purpose. ``price_usd_cents`` is a derived value, and a derived value
    without the inputs that produced it cannot be audited or recomputed, so the
    timestamp travels with the conversion onto the offer row.
    """

    as_of: datetime.datetime
    usd_per_unit: dict[str, Decimal]

    def rate(self, currency: str) -> Decimal:
        code = currency.strip().upper()
        if code == USD:
            return Decimal(1)
        if code not in self.usd_per_unit:
            raise CurrencyError(
                f"no USD rate for {code} as of {self.as_of.isoformat()}; the offer "
                "keeps its listed amount and currency, and price_usd_cents stays null"
            )
        return self.usd_per_unit[code]


def to_usd_cents(minor: int, currency: str, rates: FxRates) -> int:
    """Convert an amount in minor units to USD cents.

    Goes through the decimal amount rather than scaling minor units directly:
    minor units are not comparable across currencies with different exponents,
    which is exactly how a JPY price becomes a dollar price a hundred times too
    large.
    """
    amount = from_minor_units(minor, currency)
    usd = amount * rates.rate(currency)
    return int(usd.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP))
