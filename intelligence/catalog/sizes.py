"""Size normalization.

A size string is only meaningful with its system: "38" is an EU dress, an EU
shoe, and an Italian jacket, and picking one silently is how a size filter
starts excluding the right garments. The parser therefore reads the system from
the string when it is stated, accepts one the source declares, and otherwise
returns None rather than guessing.

Sizes are not converted between systems here. Conversion is brand-specific -
which is why StyleProfileSize scopes a size to a brand - so a global conversion
table would encode a fiction.
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
    "2xl",
    "3xl",
    "4xl",
    "5xl",
    "xs/s",
    "s/m",
    "m/l",
    "l/xl",
}

ONE_SIZE = {"one size", "onesize", "os", "o/s", "one-size", "1sz", "tu"}

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

_PREFIXED = re.compile(r"^(?P<system>[a-z]{2,3})[\s\-_]*(?P<value>\d+(?:\.\d+)?)$")
_WAIST_INSEAM = re.compile(r"^w?(?P<waist>\d{2})\s*(?:x|/|\s|l)\s*(?P<inseam>\d{2})$")
_NUMERIC = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class ParsedSize:
    system: SizeSystem
    value: str


def parse_size(raw: str, *, declared_system: SizeSystem | None = None) -> ParsedSize | None:
    """Parse one size label.

    Returns None when the string carries no system and none was declared, which
    the caller stores as unknown. That is the honest outcome: a bare "38" with no
    context is genuinely ambiguous, and recording a guess would make the
    ambiguity invisible to everyone downstream.
    """
    text = raw.strip().lower()
    if not text:
        return None

    if text in ONE_SIZE:
        return ParsedSize(system=SizeSystem.one_size, value="one_size")

    if text in ALPHA_SIZES:
        return ParsedSize(system=SizeSystem.alpha, value=text.upper())

    waist_inseam = _WAIST_INSEAM.match(text)
    if waist_inseam:
        return ParsedSize(
            system=SizeSystem.waist_inseam,
            value=f"{waist_inseam.group('waist')}x{waist_inseam.group('inseam')}",
        )

    prefixed = _PREFIXED.match(text)
    if prefixed:
        system = _SYSTEM_PREFIXES.get(prefixed.group("system"))
        if system is not None:
            return ParsedSize(system=system, value=_trim_number(prefixed.group("value")))

    if _NUMERIC.match(text):
        if declared_system is None:
            # Ambiguous on purpose: "38" means different garments in different
            # systems, and the source did not say which.
            return None
        return ParsedSize(system=declared_system, value=_trim_number(text))

    return None


def _trim_number(value: str) -> str:
    """Drop a trailing ``.0`` so "8" and "8.0" are the same size, but keep "8.5"."""
    if value.endswith(".0"):
        return value[:-2]
    return value
