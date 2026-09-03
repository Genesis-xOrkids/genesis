"""Color normalization.

The hex is the fact a source or a vision model gives us. The family is a
canonical atomic value derived from it and stored alongside, never instead of
it - the same shape as filling a normalized price from an amount and a rate.

Classification runs in HSV rather than by nearest neighbour to a named palette,
because the boundaries that matter to a stylist are saturation and lightness
bands: an unsaturated dark red is brown, and a light one is pink, even though
both sit at the same hue.
"""

from __future__ import annotations

import colorsys
import re

from api.genesis_api.models.enums import ColorFamily

HEX_PATTERN = re.compile(r"^#?([0-9a-fA-F]{6})$")
SHORT_HEX_PATTERN = re.compile(r"^#?([0-9a-fA-F]{3})$")


class ColorError(ValueError):
    """Raised when a color string cannot be read as a hex value."""


def parse_hex(raw: str) -> str:
    """Normalize a hex string to lowercase ``#rrggbb``.

    Returns the canonical form the ``products.color_hex`` check constraint
    accepts, so a value that would violate it fails here with a useful message
    instead of at insert time.
    """
    candidate = raw.strip()
    match = HEX_PATTERN.match(candidate)
    if match:
        return f"#{match.group(1).lower()}"
    short = SHORT_HEX_PATTERN.match(candidate)
    if short:
        digits = short.group(1).lower()
        return "#" + "".join(digit * 2 for digit in digits)
    raise ColorError(f"not a hex color: {raw!r}")


def _hsv(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, saturation, brightness = colorsys.rgb_to_hsv(r, g, b)
    return hue * 360, saturation, brightness


def family_for_hex(hex_color: str) -> ColorFamily:
    """Classify a hex color into the canonical family.

    Deterministic and total: every valid hex maps to exactly one family, so this
    never returns null. A null ``color_family`` in the database means the source
    gave us no color at all, not that classification gave up.
    """
    hue, saturation, brightness = _hsv(parse_hex(hex_color))

    if brightness <= 0.12:
        return ColorFamily.black
    if saturation <= 0.10:
        if brightness >= 0.90:
            return ColorFamily.white
        return ColorFamily.gray

    # Low-saturation warm tones read as neutrals, not as pale oranges. This band
    # is where beige and brown live, and it has to be checked before hue.
    if saturation <= 0.35 and 20 <= hue <= 60:
        return ColorFamily.beige if brightness >= 0.65 else ColorFamily.brown
    # Brown is a dark orange, and brightness alone separates the two: saddle
    # brown and a vivid dark orange are both fully saturated at the same hue, so
    # a saturation cap here would push saddle brown into orange.
    if 10 <= hue <= 45 and brightness <= 0.55:
        return ColorFamily.brown

    if hue >= 345 or hue < 15:
        # True red. Pale and washed out is pink; anything else is red.
        return ColorFamily.pink if brightness >= 0.85 and saturation <= 0.45 else ColorFamily.red
    if hue < 45:
        return ColorFamily.orange
    if hue < 70:
        return ColorFamily.yellow
    if hue < 170:
        return ColorFamily.green
    if hue < 250:
        # Dark blues are navy, which matters more in apparel than anywhere else.
        return ColorFamily.navy if brightness <= 0.45 else ColorFamily.blue
    if hue < 325:
        return ColorFamily.purple
    # Magenta shading back into red. Saturation separates them: hot pink is a
    # softer magenta, cerise is a saturated red, and they sit at the same hue.
    return ColorFamily.pink if saturation <= 0.75 else ColorFamily.red


# Metallics cannot be told from hex - gold and beige occupy the same coordinates -
# so they are recognised from the source's own words or not at all.
_NAMED_OVERRIDES: dict[str, ColorFamily] = {
    "gold": ColorFamily.gold,
    "golden": ColorFamily.gold,
    "silver": ColorFamily.silver,
    "metallic silver": ColorFamily.silver,
    "multi": ColorFamily.multicolor,
    "multicolor": ColorFamily.multicolor,
    "multicolour": ColorFamily.multicolor,
    "multi-color": ColorFamily.multicolor,
    "printed": ColorFamily.multicolor,
}


def family_for_name(name: str) -> ColorFamily | None:
    """Recognise the families a hex value cannot express.

    Returns None rather than guessing, so an unrecognised name falls through to
    the hex classifier instead of overriding it with a worse answer.
    """
    return _NAMED_OVERRIDES.get(name.strip().lower())
