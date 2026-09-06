"""Mapping source vocabulary onto the canonical enums.

Retailers describe garments in their own words, and this is where those words
become the platform's terms. It runs as a deterministic pre-pass before any
model is called: a title that plainly says "midi wrap dress" should not cost a
vision call to classify, and the cases it cannot decide are left null for the
extraction route to fill.

Matching is longest-phrase-first. "Shirt dress" is a dress, not a shirt, and a
shorter pattern that fires first would get it wrong every time.
"""

from __future__ import annotations

import re

from api.genesis_api.models.enums import (
    Category,
    Fit,
    GarmentLength,
    Gender,
    Neckline,
    Pattern,
    Rise,
    Silhouette,
    SleeveLength,
    SleeveStyle,
)

CATEGORY_TERMS: dict[str, Category] = {
    "shirt dress": Category.dress,
    "shirtdress": Category.dress,
    "sweater dress": Category.dress,
    "slip dress": Category.dress,
    "maxi dress": Category.dress,
    "midi dress": Category.dress,
    "mini dress": Category.dress,
    "dress": Category.dress,
    "jumpsuit": Category.jumpsuit,
    "romper": Category.jumpsuit,
    "playsuit": Category.jumpsuit,
    "trench coat": Category.coat,
    "puffer": Category.coat,
    "parka": Category.coat,
    "overcoat": Category.coat,
    "peacoat": Category.coat,
    "pea coat": Category.coat,
    "anorak": Category.coat,
    "windbreaker": Category.coat,
    "raincoat": Category.coat,
    "coat": Category.coat,
    "blazer": Category.blazer,
    "sport coat": Category.blazer,
    "denim jacket": Category.jacket,
    "bomber": Category.jacket,
    "jacket": Category.jacket,
    "waistcoat": Category.vest,
    "vest": Category.vest,
    "gilet": Category.vest,
    "cardigan": Category.cardigan,
    "turtleneck": Category.sweater,
    "sweater": Category.sweater,
    "jumper": Category.sweater,
    "knit": Category.sweater,
    "pullover": Category.sweater,
    "hoodie": Category.sweater,
    "button down": Category.shirt,
    "button-down": Category.shirt,
    "oxford": Category.shirt,
    "blouse": Category.shirt,
    "shirt": Category.shirt,
    "t-shirt": Category.top,
    "tee": Category.top,
    "tank": Category.top,
    "camisole": Category.top,
    "bodysuit": Category.top,
    "cami": Category.top,
    "polo": Category.top,
    "top": Category.top,
    "jeans": Category.jeans,
    "jean": Category.jeans,
    "denim pant": Category.jeans,
    "trouser": Category.pants,
    "jogger": Category.pants,
    "sweatpant": Category.pants,
    "cargo pant": Category.pants,
    "chino": Category.pants,
    "legging": Category.pants,
    "pant": Category.pants,
    "slack": Category.pants,
    "shorts": Category.shorts,
    "skirt": Category.skirt,
    "sneaker": Category.sneakers,
    "trainer": Category.sneakers,
    "boot": Category.boots,
    "sandal": Category.sandals,
    "heel": Category.shoes,
    "loafer": Category.shoes,
    "flat": Category.shoes,
    "pump": Category.shoes,
    "shoe": Category.shoes,
    "handbag": Category.bag,
    "tote": Category.bag,
    "clutch": Category.bag,
    "crossbody": Category.bag,
    "backpack": Category.bag,
    "bag": Category.bag,
    "belt": Category.belt,
    "scarf": Category.scarf,
    "hat": Category.hat,
    "cap": Category.hat,
    "beanie": Category.hat,
    "sunglass": Category.eyewear,
    "watch": Category.watch,
    "necklace": Category.jewelry,
    "earring": Category.jewelry,
    "bracelet": Category.jewelry,
    "ring": Category.jewelry,
    "sock": Category.hosiery,
    "tight": Category.hosiery,
    "glove": Category.gloves,
    "swimsuit": Category.swimwear,
    "bikini": Category.swimwear,
}

SILHOUETTE_TERMS: dict[str, Silhouette] = {
    "a-line": Silhouette.a_line,
    "a line": Silhouette.a_line,
    "fit and flare": Silhouette.fit_and_flare,
    "fit-and-flare": Silhouette.fit_and_flare,
    "drop waist": Silhouette.drop_waist,
    "dropped waist": Silhouette.drop_waist,
    "wide leg": Silhouette.wide_leg,
    "wide-leg": Silhouette.wide_leg,
    "straight leg": Silhouette.straight,
    "straight-leg": Silhouette.straight,
    "bodycon": Silhouette.bodycon,
    "body-con": Silhouette.bodycon,
    "empire": Silhouette.empire,
    "peplum": Silhouette.peplum,
    "trapeze": Silhouette.trapeze,
    "cocoon": Silhouette.cocoon,
    "balloon": Silhouette.balloon,
    "column": Silhouette.column,
    "sheath": Silhouette.sheath,
    "shift": Silhouette.shift,
    "wrap": Silhouette.wrap,
    "oversized": Silhouette.oversized,
    "boxy": Silhouette.boxy,
    "tapered": Silhouette.tapered,
    "flared": Silhouette.flared,
    "slim": Silhouette.slim,
}

NECKLINE_TERMS: dict[str, Neckline] = {
    "v-neck": Neckline.v_neck,
    "v neck": Neckline.v_neck,
    "crew neck": Neckline.crew,
    "crewneck": Neckline.crew,
    "scoop neck": Neckline.scoop,
    "boat neck": Neckline.boat,
    "bateau": Neckline.boat,
    "square neck": Neckline.square,
    "sweetheart": Neckline.sweetheart,
    "halter": Neckline.halter,
    "off the shoulder": Neckline.off_shoulder,
    "off-the-shoulder": Neckline.off_shoulder,
    "one shoulder": Neckline.one_shoulder,
    "strapless": Neckline.strapless,
    "turtleneck": Neckline.turtleneck,
    "mock neck": Neckline.mock_neck,
    "cowl": Neckline.cowl,
    "henley": Neckline.henley,
    "plunge": Neckline.plunge,
    "collared": Neckline.collared,
}

SLEEVE_LENGTH_TERMS: dict[str, SleeveLength] = {
    "sleeveless": SleeveLength.sleeveless,
    "cap sleeve": SleeveLength.cap,
    "short sleeve": SleeveLength.short,
    "elbow sleeve": SleeveLength.elbow,
    "three quarter": SleeveLength.three_quarter,
    "3/4 sleeve": SleeveLength.three_quarter,
    "long sleeve": SleeveLength.long,
    "extra long sleeve": SleeveLength.extra_long,
}

SLEEVE_STYLE_TERMS: dict[str, SleeveStyle] = {
    "drop shoulder": SleeveStyle.drop_shoulder,
    "dropped shoulder": SleeveStyle.drop_shoulder,
    "raglan": SleeveStyle.raglan,
    "puff sleeve": SleeveStyle.puff,
    "bishop sleeve": SleeveStyle.bishop,
    "balloon sleeve": SleeveStyle.balloon,
    "bell sleeve": SleeveStyle.bell,
    "flutter sleeve": SleeveStyle.flutter,
    "dolman": SleeveStyle.dolman,
    "kimono sleeve": SleeveStyle.kimono,
}

LENGTH_TERMS: dict[str, GarmentLength] = {
    "cropped": GarmentLength.cropped,
    "crop": GarmentLength.cropped,
    "above the knee": GarmentLength.above_knee,
    "knee length": GarmentLength.knee,
    "below the knee": GarmentLength.below_knee,
    "floor length": GarmentLength.floor,
    "ankle length": GarmentLength.ankle,
    "midi": GarmentLength.midi,
    "maxi": GarmentLength.maxi,
    "mini": GarmentLength.mini,
}

RISE_TERMS: dict[str, Rise] = {
    "ultra high rise": Rise.ultra_high,
    "ultra-high-rise": Rise.ultra_high,
    "high rise": Rise.high,
    "high-rise": Rise.high,
    "high waist": Rise.high,
    "mid rise": Rise.mid,
    "mid-rise": Rise.mid,
    "low rise": Rise.low,
    "low-rise": Rise.low,
}

FIT_TERMS: dict[str, Fit] = {
    "skinny": Fit.skinny,
    "slim fit": Fit.slim,
    "tailored": Fit.tailored,
    "relaxed": Fit.relaxed,
    "loose": Fit.loose,
    "oversized": Fit.oversized,
    "regular fit": Fit.regular,
    "classic fit": Fit.regular,
}

PATTERN_TERMS: dict[str, Pattern] = {
    "polka dot": Pattern.polka_dot,
    "pinstripe": Pattern.stripe,
    "striped": Pattern.stripe,
    "stripe": Pattern.stripe,
    "gingham": Pattern.check,
    "checked": Pattern.check,
    "check": Pattern.check,
    "plaid": Pattern.plaid,
    "tartan": Pattern.plaid,
    "floral": Pattern.floral,
    "leopard": Pattern.animal,
    "zebra": Pattern.animal,
    "snake": Pattern.animal,
    "animal print": Pattern.animal,
    "geometric": Pattern.geometric,
    "abstract": Pattern.abstract,
    "paisley": Pattern.paisley,
    "camouflage": Pattern.camouflage,
    "camo": Pattern.camouflage,
    "colorblock": Pattern.colorblock,
    "colour block": Pattern.colorblock,
    "tie dye": Pattern.tie_dye,
    "tie-dye": Pattern.tie_dye,
    "logo": Pattern.logo,
    "solid": Pattern.solid,
}

GENDER_TERMS: dict[str, Gender] = {
    "women": Gender.womens,
    "womens": Gender.womens,
    "female": Gender.womens,
    "ladies": Gender.womens,
    "men": Gender.mens,
    "mens": Gender.mens,
    "male": Gender.mens,
    "unisex": Gender.unisex,
    "girls": Gender.girls,
    "boys": Gender.boys,
}


def _tokens(text: str) -> str:
    """Reduce text to space-separated words.

    Punctuation carries no meaning here and varies by retailer: "V-Neck",
    "v neck", and "V_Neck" are the same claim about the same garment. Both the
    haystack and the patterns go through this, so they meet in one form.
    """
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def _match[T](text: str, terms: dict[str, T]) -> T | None:
    """Longest phrase wins.

    "Shirt dress" contains "shirt", so a shorter pattern firing first would file
    every shirt dress under shirts. Sorting by length removes any dependence on
    dictionary order. A trailing "s" is accepted so "boots" matches "boot".
    """
    haystack = _tokens(text)
    for phrase in sorted(terms, key=len, reverse=True):
        normalized = _tokens(phrase).strip()
        if any(f" {form} " in haystack for form in _inflections(normalized)):
            return terms[phrase]
    return None


def _inflections(phrase: str) -> tuple[str, ...]:
    """The phrase, plus the plural and singular it might appear as.

    Both directions are needed and only one was there originally. Titles say
    "Sailor Jean" where the vocabulary says "jeans", so matching only
    phrase-plus-s filed a whole category of denim under trousers.
    """
    forms = {phrase, f"{phrase}s"}
    if phrase.endswith("es") and len(phrase) > 3:
        forms.add(phrase[:-2])
    if phrase.endswith("s") and len(phrase) > 2:
        forms.add(phrase[:-1])
    return tuple(forms)


def category_for(*texts: str | None) -> Category | None:
    return _first(CATEGORY_TERMS, texts)


def silhouette_for(*texts: str | None) -> Silhouette | None:
    return _first(SILHOUETTE_TERMS, texts)


def neckline_for(*texts: str | None) -> Neckline | None:
    return _first(NECKLINE_TERMS, texts)


def sleeve_length_for(*texts: str | None) -> SleeveLength | None:
    return _first(SLEEVE_LENGTH_TERMS, texts)


def sleeve_style_for(*texts: str | None) -> SleeveStyle | None:
    return _first(SLEEVE_STYLE_TERMS, texts)


def length_for(*texts: str | None) -> GarmentLength | None:
    return _first(LENGTH_TERMS, texts)


def rise_for(*texts: str | None) -> Rise | None:
    return _first(RISE_TERMS, texts)


def fit_for(*texts: str | None) -> Fit | None:
    return _first(FIT_TERMS, texts)


def pattern_for(*texts: str | None) -> Pattern | None:
    return _first(PATTERN_TERMS, texts)


def gender_for(*texts: str | None) -> Gender | None:
    return _first(GENDER_TERMS, texts)


def _first[T](terms: dict[str, T], texts: tuple[str | None, ...]) -> T | None:
    """First non-empty text that yields a match wins.

    Callers pass fields in order of trustworthiness, and for what a garment *is*
    that order starts with its own name. A merchandising department is a shelf,
    not a description: storefronts file "Knit Cami Mini Dress" under Sweaters
    because that is where a shopper browsing knitwear should find it, and taking
    the department at its word labelled three dresses as sweaters.

    Facts that names do not carry are the exception. Gender is almost never in a
    title and almost always in a tag, so it reads those first.
    """
    for text in texts:
        if not text:
            continue
        found = _match(text, terms)
        if found is not None:
            return found
    return None
