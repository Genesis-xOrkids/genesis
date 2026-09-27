"""Boundary normalization: money, color, and size.

These are pure functions, so the tests are cheap and the coverage can be real.
What they protect is the boundary contract: a source's shorthand becomes an
atomic fact, or it fails loudly, but it never becomes a confident wrong answer.
"""

from __future__ import annotations

import datetime
import pathlib
from decimal import Decimal

import pytest

from api.genesis_api.models.enums import Category, ColorFamily, Fit, Rise, SizeSystem
from intelligence.catalog import vocabulary
from intelligence.catalog.color import ColorError, family_for_hex, family_for_name, parse_hex
from intelligence.catalog.money import (
    CurrencyError,
    FxRates,
    exponent_for,
    from_minor_units,
    to_minor_units,
    to_usd_cents,
    to_usd_cents_as_of,
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


def test_a_converted_price_carries_the_date_of_the_rate_that_made_it() -> None:
    """The pair is the point. A USD value without the rate's timestamp cannot be
    audited or recomputed, which is why FxRates is dated at all."""
    usd_cents, fx_at = to_usd_cents_as_of(10000, "EUR", RATES)
    assert usd_cents == 10900
    assert fx_at == RATES.as_of


def test_no_rate_leaves_both_the_price_and_its_date_null() -> None:
    """Not one or the other. A timestamp beside a null price would claim a rate
    for a conversion that never happened - the drift three hand-written copies
    of this try/except made possible."""
    usd_cents, fx_at = to_usd_cents_as_of(1000, "SEK", RATES)
    assert usd_cents is None
    assert fx_at is None


# --- vocabulary ----------------------------------------------------------


def test_every_vocabulary_deriver_is_reached_by_the_bundle() -> None:
    """Connectors derive attributes only through ``attributes_for``. A new
    ``*_for`` helper nobody adds to it would be dead on arrival: written,
    tested, and read by no connector."""
    derivers = {
        name
        for name in dir(vocabulary)
        if name.endswith("_for") and not name.startswith("_") and name != "attributes_for"
    }
    source = pathlib.Path(vocabulary.__file__).read_text()
    body = source.split("def attributes_for(")[1].split("\ndef ")[0]
    # gender_for is the documented exception: each connector orders its own
    # gender signals, so it is called at the call site rather than in here.
    unreached = {name for name in derivers if f"{name}(" not in body} - {"gender_for"}
    assert not unreached, f"vocabulary helpers no connector reaches: {sorted(unreached)}"


def test_the_bundle_derives_what_the_text_says() -> None:
    attributes = vocabulary.attributes_for("Black High-Rise Skinny Jeans")
    assert attributes["category"] is Category.jeans
    assert attributes["rise"] is Rise.high
    assert attributes["fit"] is Fit.skinny
    assert attributes["neckline"] is None


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
    """Gold and beige are the same coordinates in hex. Only the word separates them."""
    assert family_for_name("Gold") is ColorFamily.gold
    assert family_for_name("multi") is ColorFamily.multicolor


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Black", ColorFamily.black),
        ("Washed Black", ColorFamily.black),
        ("Heather Grey", ColorFamily.gray),
        ("Off White", ColorFamily.white),
        ("Coffee Bean", ColorFamily.brown),
        ("Deep Taupe", ColorFamily.beige),
        ("Navy", ColorFamily.navy),
        ("Indigo", ColorFamily.navy),
        ("Sage Green", ColorFamily.green),
        ("Bone", ColorFamily.white),
        ("Burgundy", ColorFamily.red),
        ("Blush", ColorFamily.pink),
    ],
)
def test_colour_names_resolve_to_a_family(name: str, expected: ColorFamily) -> None:
    """Most sources give a name and no hex at all, so this is the primary path
    rather than a fallback. Shopify's public feed has no colour field whatsoever."""
    assert family_for_name(name) is expected


def test_longest_phrase_wins_over_a_shorter_contained_one() -> None:
    """ "Off white" must not resolve through "white" alone, and "dark denim" is
    navy rather than the blue that "denim" would give."""
    assert family_for_name("Off White") is ColorFamily.white
    assert family_for_name("Dark Denim") is ColorFamily.navy
    assert family_for_name("Denim") is ColorFamily.blue


def test_an_unrecognised_colour_name_returns_none() -> None:
    """Null means unknown. Guessing here would put a wrong colour on a garment,
    which a shopper filtering by colour would see immediately."""
    assert family_for_name("Tungsten Nebula") is None


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
        # Tentree writes one size as a single word.
        ("ONE", SizeSystem.one_size, "one_size"),
        # Letter sizes past the common run, and plus sizes kept as written.
        ("XXXXL", SizeSystem.alpha, "XXXXL"),
        ("6XL", SizeSystem.alpha, "6XL"),
        ("2X", SizeSystem.alpha, "2X"),
        ("XL/XXL", SizeSystem.alpha, "XL/XXL"),
        # Marine Layer spells the letters out.
        ("Extra Small", SizeSystem.alpha, "XS"),
        ("Small", SizeSystem.alpha, "S"),
        ("Medium", SizeSystem.alpha, "M"),
        ("Large", SizeSystem.alpha, "L"),
        ("Extra Large", SizeSystem.alpha, "XL"),
        # A pair joined by a hyphen or a space is the pair a slash states.
        ("S-M", SizeSystem.alpha, "S/M"),
        ("XL-XXL", SizeSystem.alpha, "XL/XXL"),
        ("XS S", SizeSystem.alpha, "XS/S"),
        # A letter size with a number restating it: Taylor Stitch's chest, Marine
        # Layer's inseam, Cozy Earth's shoe range, Stelle's and Allbirds' brackets.
        ("XS - 36", SizeSystem.alpha, "XS"),
        ("S-30", SizeSystem.alpha, "S"),
        ("L: US 10-13", SizeSystem.alpha, "L"),
        ("M/L: US 8-11", SizeSystem.alpha, "M/L"),
        ("XS (4/5)", SizeSystem.alpha, "XS"),
        ("3XS (2/3)", SizeSystem.alpha, "3XS"),
        ("S (W5-7)", SizeSystem.alpha, "S"),
        ("M/L (8-11)", SizeSystem.alpha, "M/L"),
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


@pytest.mark.parametrize(
    "raw",
    [
        # A word after the letter changes the garment rather than restating it.
        "Extra Small - Petite",
        "M (Tall)",
        # Everlane's men's and women's shoe sizes, which are not Medium or a W.
        "M 10",
        "W 10",
        # Letters run together are ambiguous: Tentree's "SM" is S/M beside "LXL"
        # and Small anywhere else.
        "SM",
        # Knix's and Organic Basics' "+" is not stated to mean anything.
        "S+",
        # A range or a waist-inseam, depending on the store: Marine Layer's pants
        # run "30-30" through "34-32", Colorful Standard's socks "36-40".
        "30-32",
        "36-40",
        # Systems the enum does not have: bra band and cup, kids' ages, a length
        # letter, a width letter, and a size stated for men and women at once.
        "34B",
        "12-18M",
        "4T",
        "10Y",
        "0R",
        "10.5D",
        "W10/M9",
        "L MEN/XL WOMEN",
    ],
)
def test_labels_whose_meaning_is_not_in_the_label_stay_unknown(raw: str) -> None:
    """Every one of these was seen live, and each is left unknown rather than read
    into the nearest system that happens to fit."""
    assert parse_size(raw) is None
    assert parse_size(raw, declared_system=SizeSystem.us) is None
