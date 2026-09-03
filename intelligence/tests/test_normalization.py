"""Boundary normalization: money, color, and size.

These are pure functions, so the tests are cheap and the coverage can be real.
What they protect is the boundary contract: a source's shorthand becomes an
atomic fact, or it fails loudly, but it never becomes a confident wrong answer.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from api.genesis_api.models.enums import ColorFamily, SizeSystem
from intelligence.catalog.color import ColorError, family_for_hex, family_for_name, parse_hex
from intelligence.catalog.money import (
    CurrencyError,
    FxRates,
    exponent_for,
    from_minor_units,
    to_minor_units,
    to_usd_cents,
)
from intelligence.catalog.sizes import parse_size

RATES = FxRates(
    as_of=datetime.datetime(2026, 9, 3, tzinfo=datetime.UTC),
    usd_per_unit={
        "EUR": Decimal("1.09"),
        "GBP": Decimal("1.27"),
        "JPY": Decimal("0.0067"),
        "KRW": Decimal("0.00072"),
    },
)


# --- money ---------------------------------------------------------------


def test_zero_decimal_currencies_are_not_scaled_by_a_hundred() -> None:
    """The trap this module exists for: JPY has no minor unit."""
    assert exponent_for("JPY") == 0
    assert to_minor_units("12000", "JPY") == 12000
    assert to_minor_units("12.34", "USD") == 1234


def test_a_yen_price_does_not_become_a_dollar_price() -> None:
    """12,000 JPY is about 80 dollars, not 12,000."""
    usd_cents = to_usd_cents(12000, "JPY", RATES)
    assert 7000 < usd_cents < 9000


def test_conversion_round_trips_through_the_decimal_amount() -> None:
    assert from_minor_units(1234, "USD") == Decimal("12.34")
    assert from_minor_units(12000, "JPY") == Decimal("12000")


def test_unknown_currency_raises_rather_than_assuming_two_decimals() -> None:
    with pytest.raises(CurrencyError, match="unknown currency"):
        to_minor_units("10", "XYZ")


def test_missing_rate_raises_so_the_offer_keeps_a_null_usd_price() -> None:
    with pytest.raises(CurrencyError, match="no USD rate"):
        to_usd_cents(1000, "SEK", RATES)


def test_float_amounts_are_refused() -> None:
    """A float price has already lost precision upstream."""
    with pytest.raises(CurrencyError, match="refusing to convert float"):
        to_minor_units(12.34, "USD")


def test_negative_amounts_are_refused() -> None:
    with pytest.raises(CurrencyError):
        to_minor_units("-1", "USD")


def test_usd_needs_no_rate() -> None:
    assert to_usd_cents(4200, "USD", RATES) == 4200


# --- color ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("hex_color", "expected"),
    [
        ("#000000", ColorFamily.black),
        ("#ffffff", ColorFamily.white),
        ("#808080", ColorFamily.gray),
        ("#c0c0c0", ColorFamily.gray),
        ("#1a2b5e", ColorFamily.navy),
        ("#191970", ColorFamily.navy),
        ("#4287f5", ColorFamily.blue),
        ("#d4b896", ColorFamily.beige),
        ("#f5f5dc", ColorFamily.beige),
        ("#5c4033", ColorFamily.brown),
        ("#7b3f00", ColorFamily.brown),
        ("#cc5500", ColorFamily.orange),
        ("#8b0000", ColorFamily.red),
        ("#dc143c", ColorFamily.red),
        ("#ff69b4", ColorFamily.pink),
        ("#ffc0cb", ColorFamily.pink),
        ("#2e8b57", ColorFamily.green),
        ("#f5e050", ColorFamily.yellow),
        ("#7b3fa0", ColorFamily.purple),
    ],
)
def test_hex_classifies_into_the_expected_family(hex_color: str, expected: ColorFamily) -> None:
    assert family_for_hex(hex_color) is expected


def test_brightness_separates_brown_from_orange_at_equal_saturation() -> None:
    """Saddle brown and a vivid dark orange are both fully saturated at the same
    hue, so only brightness tells them apart."""
    assert family_for_hex("#7b3f00") is ColorFamily.brown
    assert family_for_hex("#ff8c00") is ColorFamily.orange


def test_saturation_separates_hot_pink_from_cerise_at_equal_hue() -> None:
    assert family_for_hex("#ff69b4") is ColorFamily.pink
    assert family_for_hex("#e8175d") is ColorFamily.red


def test_classification_is_total_over_valid_hex() -> None:
    """Every valid hex gets a family, so a null color_family always means the
    source gave no color - never that classification gave up."""
    for red in range(0, 256, 51):
        for green in range(0, 256, 51):
            for blue in range(0, 256, 51):
                assert isinstance(family_for_hex(f"#{red:02x}{green:02x}{blue:02x}"), ColorFamily)


def test_hex_is_normalized_to_the_form_the_check_constraint_accepts() -> None:
    assert parse_hex("#ABC") == "#aabbcc"
    assert parse_hex("A1B2C3") == "#a1b2c3"


def test_invalid_hex_raises() -> None:
    with pytest.raises(ColorError):
        parse_hex("cornflower")


def test_metallics_come_from_names_because_hex_cannot_express_them() -> None:
    assert family_for_name("Gold") is ColorFamily.gold
    assert family_for_name("multi") is ColorFamily.multicolor
    assert family_for_name("cerulean") is None, "unknown names fall through to the hex"


# --- sizes ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "system", "value"),
    [
        ("M", SizeSystem.alpha, "M"),
        ("xs", SizeSystem.alpha, "XS"),
        ("US 8", SizeSystem.us, "8"),
        ("UK12", SizeSystem.uk, "12"),
        ("EU 38", SizeSystem.eu, "38"),
        ("IT 42", SizeSystem.it, "42"),
        ("W28 L32", SizeSystem.waist_inseam, "28x32"),
        ("28x32", SizeSystem.waist_inseam, "28x32"),
        ("One Size", SizeSystem.one_size, "one_size"),
    ],
)
def test_size_labels_that_state_their_system_are_parsed(
    raw: str, system: SizeSystem, value: str
) -> None:
    parsed = parse_size(raw)
    assert parsed is not None
    assert parsed.system is system
    assert parsed.value == value


def test_a_bare_number_without_a_declared_system_is_unknown_not_guessed() -> None:
    """ "38" is an EU dress, an EU shoe, and an IT jacket. Recording a guess would
    hide the ambiguity from everyone downstream."""
    assert parse_size("38") is None


def test_a_bare_number_uses_the_system_the_source_declared() -> None:
    parsed = parse_size("38", declared_system=SizeSystem.eu)
    assert parsed is not None
    assert parsed.system is SizeSystem.eu
    assert parsed.value == "38"


def test_half_sizes_survive_but_trailing_zeros_do_not() -> None:
    assert parse_size("8.5", declared_system=SizeSystem.us).value == "8.5"  # type: ignore[union-attr]
    assert parse_size("8.0", declared_system=SizeSystem.us).value == "8"  # type: ignore[union-attr]


def test_unparseable_sizes_return_none() -> None:
    assert parse_size("") is None
    assert parse_size("please select") is None
