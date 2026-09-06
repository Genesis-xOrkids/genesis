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


# Colour names, because most sources give a name and no hex at all. Shopify's
# public product feed has no colour field whatsoever: the colour is in the
# variant options, the tags, and the back half of the title. Without this
# lexicon every product from those sources lands with no colour, which removes
# one of the two filters a shopper reaches for first.
#
# Metallics are here for a different reason: gold and beige occupy the same
# coordinates in hex, so no classifier can separate them. Only the word can.
_COLOR_NAMES: dict[str, ColorFamily] = {
    # neutrals
    "black": ColorFamily.black,
    "jet": ColorFamily.black,
    "onyx": ColorFamily.black,
    "white": ColorFamily.white,
    "ivory": ColorFamily.white,
    "cream": ColorFamily.white,
    "ecru": ColorFamily.white,
    "bone": ColorFamily.white,
    "chalk": ColorFamily.white,
    "optic white": ColorFamily.white,
    "off white": ColorFamily.white,
    "grey": ColorFamily.gray,
    "gray": ColorFamily.gray,
    "charcoal": ColorFamily.gray,
    "heather grey": ColorFamily.gray,
    "heather gray": ColorFamily.gray,
    "slate": ColorFamily.gray,
    "graphite": ColorFamily.gray,
    "ash": ColorFamily.gray,
    "beige": ColorFamily.beige,
    "tan": ColorFamily.beige,
    "camel": ColorFamily.beige,
    "taupe": ColorFamily.beige,
    "khaki": ColorFamily.beige,
    "sand": ColorFamily.beige,
    "oatmeal": ColorFamily.beige,
    "natural": ColorFamily.beige,
    "stone": ColorFamily.beige,
    "putty": ColorFamily.beige,
    "nude": ColorFamily.beige,
    "biscuit": ColorFamily.beige,
    "brown": ColorFamily.brown,
    "chocolate": ColorFamily.brown,
    "espresso": ColorFamily.brown,
    "cocoa": ColorFamily.brown,
    "walnut": ColorFamily.brown,
    "chestnut": ColorFamily.brown,
    "coffee": ColorFamily.brown,
    "mocha": ColorFamily.brown,
    "toffee": ColorFamily.brown,
    "cognac": ColorFamily.brown,
    "sienna": ColorFamily.brown,
    # blues
    "navy": ColorFamily.navy,
    "midnight": ColorFamily.navy,
    "ink": ColorFamily.navy,
    "indigo": ColorFamily.navy,
    "dark denim": ColorFamily.navy,
    "blue": ColorFamily.blue,
    "sky": ColorFamily.blue,
    "cobalt": ColorFamily.blue,
    "azure": ColorFamily.blue,
    "denim": ColorFamily.blue,
    "chambray": ColorFamily.blue,
    "cornflower": ColorFamily.blue,
    "powder blue": ColorFamily.blue,
    "teal": ColorFamily.blue,
    "turquoise": ColorFamily.blue,
    "aqua": ColorFamily.blue,
    # greens
    "green": ColorFamily.green,
    "olive": ColorFamily.green,
    "sage": ColorFamily.green,
    "forest": ColorFamily.green,
    "emerald": ColorFamily.green,
    "mint": ColorFamily.green,
    "moss": ColorFamily.green,
    "fern": ColorFamily.green,
    "hunter": ColorFamily.green,
    "pistachio": ColorFamily.green,
    "seafoam": ColorFamily.green,
    # warms
    "yellow": ColorFamily.yellow,
    "mustard": ColorFamily.yellow,
    "butter": ColorFamily.yellow,
    "lemon": ColorFamily.yellow,
    "ochre": ColorFamily.yellow,
    "orange": ColorFamily.orange,
    "rust": ColorFamily.orange,
    "terracotta": ColorFamily.orange,
    "apricot": ColorFamily.orange,
    "amber": ColorFamily.orange,
    "clay": ColorFamily.orange,
    "red": ColorFamily.red,
    "burgundy": ColorFamily.red,
    "wine": ColorFamily.red,
    "maroon": ColorFamily.red,
    "crimson": ColorFamily.red,
    "scarlet": ColorFamily.red,
    "cherry": ColorFamily.red,
    "brick": ColorFamily.red,
    "oxblood": ColorFamily.red,
    "pink": ColorFamily.pink,
    "blush": ColorFamily.pink,
    "rose": ColorFamily.pink,
    "fuchsia": ColorFamily.pink,
    "magenta": ColorFamily.pink,
    "coral": ColorFamily.pink,
    "salmon": ColorFamily.pink,
    "peach": ColorFamily.pink,
    "purple": ColorFamily.purple,
    "lilac": ColorFamily.purple,
    "lavender": ColorFamily.purple,
    "plum": ColorFamily.purple,
    "violet": ColorFamily.purple,
    "aubergine": ColorFamily.purple,
    "mauve": ColorFamily.purple,
    # metallics and prints, which hex cannot express
    "gold": ColorFamily.gold,
    "golden": ColorFamily.gold,
    "brass": ColorFamily.gold,
    "silver": ColorFamily.silver,
    "pewter": ColorFamily.silver,
    "chrome": ColorFamily.silver,
    "multi": ColorFamily.multicolor,
    "multicolor": ColorFamily.multicolor,
    "multicolour": ColorFamily.multicolor,
    "multi-color": ColorFamily.multicolor,
    "printed": ColorFamily.multicolor,
    "print": ColorFamily.multicolor,
    "floral": ColorFamily.multicolor,
    "stripe": ColorFamily.multicolor,
}

_NAME_TOKENS = re.compile(r"[^a-z]+")


def family_for_name(name: str) -> ColorFamily | None:
    """Read a colour family out of a colour name.

    Two passes, because colour names are modifier-then-head. Multi-word entries
    are matched first, so "off white" resolves as white and "dark denim" as navy
    rather than through their component words. Everything else is read
    right-to-left, because the last colour word is the actual colour and the ones
    before it qualify it: "Natural Black" is black, "Deep Navy" is navy, and
    "Heather Grey" is grey. Matching longest-word-first instead makes "Natural
    Black" beige, which is how this was wrong the first time.

    Returns None rather than guessing. An unrecognised name falls through to the
    hex classifier where one exists, and to no colour where none does, which is
    honest: null means we do not know.
    """
    tokens = [token for token in _NAME_TOKENS.sub(" ", name.lower()).split() if token]
    if not tokens:
        return None

    padded = " " + " ".join(tokens) + " "
    for phrase, family in sorted(
        ((p, f) for p, f in _COLOR_NAMES.items() if " " in p),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if f" {phrase} " in padded:
            return family

    for token in reversed(tokens):
        single = _COLOR_NAMES.get(token)
        if single is not None:
            return single
    return None
