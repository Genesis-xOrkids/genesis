"""Size normalization.

A size string is only meaningful with its system: "38" is an EU dress, an EU
shoe, and an Italian jacket, and picking one silently is how a size filter
starts excluding the right garments. The parser therefore reads the system from
the string when it is stated, accepts one the source declares, and otherwise
returns nothing rather than guessing.

Sizes are not converted between systems here. Conversion is brand-specific -
which is why StyleProfileSize scopes a size to a brand - so a global conversion
table would encode a fiction. A label that states one size in two systems, "M
(US 8)", is two facts, and both are returned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from api.genesis_api.models.enums import SizeSystem

ALPHA_SIZES = {
    "xxxs",
    "xxs",
    "xs",
    "s",
    "m",
    "l",
    "xl",
    "xxl",
    "xxxl",
    "xxxxl",
    "3xs",
    "2xl",
    "3xl",
    "4xl",
    "5xl",
    "6xl",
    # Plus sizes, kept as written: a women's 2X is not reliably a 2XL, and
    # treating them as one would be the conversion this module declines to make.
    "1x",
    "2x",
    "3x",
    "xxs/xs",
    "xs/s",
    "s/m",
    "m/l",
    "l/xl",
    "xl/xxl",
    "xl/2xl",
}

# The same letters spelled out, as some storefronts write them.
SPELLED_ALPHA = {
    "extra small": "xs",
    "small": "s",
    "medium": "m",
    "large": "l",
    "extra large": "xl",
}

ONE_SIZE = {"one size", "onesize", "one", "os", "o/s", "one-size", "1sz", "tu"}

_SYSTEM_PREFIXES: dict[str, SizeSystem] = {
    "us": SizeSystem.us,
    "usa": SizeSystem.us,
    "uk": SizeSystem.uk,
    "gb": SizeSystem.uk,
    "eu": SizeSystem.eu,
    "eur": SizeSystem.eu,
    "fr": SizeSystem.fr,
    "it": SizeSystem.it,
    "jp": SizeSystem.jp,
}

_NUMBER = r"\d+(?:\.\d+)?"
_PREFIXED = re.compile(rf"^(?P<system>[a-z]{{2,3}})[\s\-_]*(?P<value>{_NUMBER})$")
_WAIST_INSEAM = re.compile(r"^w?(?P<waist>\d{2})\s*(?:x|/|\s|l)\s*(?P<inseam>\d{2})$")
_NUMERIC = re.compile(rf"^{_NUMBER}$")
# Two letter sizes joined by a hyphen or a space, "S-M" or "XS S": the range a
# slash states, written another way.
_ALPHA_PAIR = re.compile(r"^(?P<low>[a-z0-9]+)(?:\s*-\s*|\s+)(?P<high>[a-z0-9]+)$")
# A letter size followed by a qualifier, after a dash or colon or in brackets.
_QUALIFIED = re.compile(
    r"^(?P<size>[a-z0-9/ ]+?)\s*(?:[-:]\s*(?P<after>[^()]+)|\((?P<bracketed>[^()]+)\))$"
)
# The qualifiers that restate a letter size rather than change it: a number in a
# named system, one size ("US 8") or a range of them ("US 10-13"), or after a
# dash a bare measurement ("36", Taylor Stitch's chest; "30", Marine Layer's
# inseam). A word ("Petite", "Tall") changes the garment, and a bare number in
# brackets ("(4/5)", "(6)") is the same size in a system the label does not name
# - how Stelle writes girls' sizes - so neither is read.
_IN_A_SYSTEM = re.compile(
    rf"^(?P<system>[a-z]{{2,3}})\s*(?P<value>{_NUMBER})(?P<range>\s*-\s*{_NUMBER})?$"
)
_MEASUREMENT = re.compile(rf"^{_NUMBER}$")


@dataclass(frozen=True)
class ParsedSize:
    system: SizeSystem
    value: str


def parse_sizes(raw: str, *, declared_system: SizeSystem | None = None) -> tuple[ParsedSize, ...]:
    """Every size one label states, in the systems it states them in.

    Returns nothing when the string carries no system and none was declared,
    which the caller stores as unknown. That is the honest outcome: a bare "38"
    with no context is genuinely ambiguous, and recording a guess would make the
    ambiguity invisible to everyone downstream.
    """
    text = raw.strip().lower()
    if not text:
        return ()

    if text in ONE_SIZE:
        return (ParsedSize(system=SizeSystem.one_size, value="one_size"),)

    alpha = _alpha(text)
    if alpha is not None:
        return (alpha,)

    qualified = _QUALIFIED.match(text)
    if qualified:
        facts = _qualified(qualified)
        if facts:
            return facts

    waist_inseam = _WAIST_INSEAM.match(text)
    if waist_inseam:
        return (
            ParsedSize(
                system=SizeSystem.waist_inseam,
                value=f"{waist_inseam.group('waist')}x{waist_inseam.group('inseam')}",
            ),
        )

    prefixed = _PREFIXED.match(text)
    if prefixed:
        system = _SYSTEM_PREFIXES.get(prefixed.group("system"))
        if system is not None:
            return (ParsedSize(system=system, value=_trim_number(prefixed.group("value"))),)

    if _NUMERIC.match(text):
        if declared_system is None:
            # Ambiguous on purpose: "38" means different garments in different
            # systems, and the source did not say which.
            return ()
        return (ParsedSize(system=declared_system, value=_trim_number(text)),)

    return ()


def _alpha(text: str) -> ParsedSize | None:
    """A letter size, written as letters, spelled out, or as a hyphenated pair."""
    letters = SPELLED_ALPHA.get(text, text)
    if letters in ALPHA_SIZES:
        return ParsedSize(system=SizeSystem.alpha, value=letters.upper())
    pair = _ALPHA_PAIR.match(letters)
    if pair:
        joined = f"{pair.group('low')}/{pair.group('high')}"
        if joined in ALPHA_SIZES:
            return ParsedSize(system=SizeSystem.alpha, value=joined.upper())
    return None


def _qualified(match: re.Match[str]) -> tuple[ParsedSize, ...]:
    """A letter size and the qualifier after it, when the qualifier restates it.

    "M (US 8)" is two facts, M and US 8. "L: US 10-13" is L and the shoe sizes
    it fits, which are a range rather than one size, so only L is recorded.
    """
    alpha = _alpha(match.group("size").strip())
    if alpha is None:
        return ()
    qualifier = (match.group("after") or match.group("bracketed")).strip()
    in_a_system = _IN_A_SYSTEM.match(qualifier)
    if in_a_system:
        system = _SYSTEM_PREFIXES.get(in_a_system.group("system"))
        if system is None:
            return ()
        if in_a_system.group("range"):
            return (alpha,)
        return (alpha, ParsedSize(system=system, value=_trim_number(in_a_system.group("value"))))
    if match.group("after") and _MEASUREMENT.match(qualifier):
        return (alpha,)
    return ()


def _trim_number(value: str) -> str:
    """Drop a trailing ``.0`` so "8" and "8.0" are the same size, but keep "8.5"."""
    if value.endswith(".0"):
        return value[:-2]
    return value
