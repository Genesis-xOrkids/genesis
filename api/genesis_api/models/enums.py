"""Closed value sets, as Postgres enums.

Per CLAUDE.md: lowercase values, member names equal their values (SQLAlchemy
uses member names as DB labels), and the database enforces validity.

Only genuinely closed sets live here. Open or seasonally versioned vocabularies
(aesthetics, trend labels, brand codes, the long tail of garment details) are
reference tables in ``taxonomy.py`` so they can grow without a migration.
"""

from __future__ import annotations

import enum


class Provenance(enum.Enum):
    """Where a stored fact came from.

    Provenance creates rows, never columns: every source writes its atomic value
    into the same column and records itself here.
    """

    feed_sync = "feed_sync"
    partner_api = "partner_api"
    model_extraction = "model_extraction"
    user_entry = "user_entry"
    stylist_entry = "stylist_entry"
    document_extraction = "document_extraction"
    derived = "derived"


class Gender(enum.Enum):
    """Merchandising gender of a product, not a person's identity."""

    womens = "womens"
    mens = "mens"
    unisex = "unisex"
    girls = "girls"
    boys = "boys"


class SizeSystem(enum.Enum):
    us = "us"
    uk = "uk"
    eu = "eu"
    fr = "fr"
    it = "it"
    jp = "jp"
    alpha = "alpha"
    waist_inseam = "waist_inseam"
    one_size = "one_size"


class ColorFamily(enum.Enum):
    """Canonical color bucket. Derived from color_hex when the source omits it;
    stored alongside the hex, never instead of it."""

    black = "black"
    white = "white"
    gray = "gray"
    beige = "beige"
    brown = "brown"
    navy = "navy"
    blue = "blue"
    green = "green"
    yellow = "yellow"
    orange = "orange"
    red = "red"
    pink = "pink"
    purple = "purple"
    gold = "gold"
    silver = "silver"
    multicolor = "multicolor"


class Category(enum.Enum):
    """Top-level garment category, after the Fashionpedia apparel categories."""

    top = "top"
    shirt = "shirt"
    sweater = "sweater"
    cardigan = "cardigan"
    dress = "dress"
    jumpsuit = "jumpsuit"
    skirt = "skirt"
    pants = "pants"
    jeans = "jeans"
    shorts = "shorts"
    jacket = "jacket"
    coat = "coat"
    blazer = "blazer"
    vest = "vest"
    activewear = "activewear"
    swimwear = "swimwear"
    lingerie = "lingerie"
    sleepwear = "sleepwear"
    shoes = "shoes"
    boots = "boots"
    sandals = "sandals"
    sneakers = "sneakers"
    bag = "bag"
    belt = "belt"
    hat = "hat"
    scarf = "scarf"
    jewelry = "jewelry"
    eyewear = "eyewear"
    watch = "watch"
    hosiery = "hosiery"
    gloves = "gloves"


class Silhouette(enum.Enum):
    """Overall line of the garment."""

    a_line = "a_line"
    column = "column"
    sheath = "sheath"
    shift = "shift"
    fit_and_flare = "fit_and_flare"
    empire = "empire"
    wrap = "wrap"
    balloon = "balloon"
    cocoon = "cocoon"
    drop_waist = "drop_waist"
    boxy = "boxy"
    oversized = "oversized"
    slim = "slim"
    straight = "straight"
    tapered = "tapered"
    wide_leg = "wide_leg"
    flared = "flared"
    bodycon = "bodycon"
    peplum = "peplum"
    trapeze = "trapeze"


class Neckline(enum.Enum):
    crew = "crew"
    v_neck = "v_neck"
    scoop = "scoop"
    boat = "boat"
    square = "square"
    sweetheart = "sweetheart"
    halter = "halter"
    off_shoulder = "off_shoulder"
    one_shoulder = "one_shoulder"
    strapless = "strapless"
    turtleneck = "turtleneck"
    mock_neck = "mock_neck"
    cowl = "cowl"
    collared = "collared"
    henley = "henley"
    plunge = "plunge"


class SleeveLength(enum.Enum):
    sleeveless = "sleeveless"
    cap = "cap"
    short = "short"
    elbow = "elbow"
    three_quarter = "three_quarter"
    long = "long"
    extra_long = "extra_long"


class SleeveStyle(enum.Enum):
    set_in = "set_in"
    raglan = "raglan"
    drop_shoulder = "drop_shoulder"
    puff = "puff"
    bishop = "bishop"
    balloon = "balloon"
    bell = "bell"
    flutter = "flutter"
    dolman = "dolman"
    kimono = "kimono"


class GarmentLength(enum.Enum):
    """Hem length. Meaning is relative to the category (a mini skirt and a mini
    dress both sit here); the category column supplies the frame."""

    cropped = "cropped"
    hip = "hip"
    mini = "mini"
    above_knee = "above_knee"
    knee = "knee"
    midi = "midi"
    below_knee = "below_knee"
    ankle = "ankle"
    maxi = "maxi"
    floor = "floor"


class Rise(enum.Enum):
    low = "low"
    mid = "mid"
    high = "high"
    ultra_high = "ultra_high"


class Fit(enum.Enum):
    skinny = "skinny"
    slim = "slim"
    tailored = "tailored"
    regular = "regular"
    relaxed = "relaxed"
    loose = "loose"
    oversized = "oversized"


class Pattern(enum.Enum):
    solid = "solid"
    stripe = "stripe"
    check = "check"
    plaid = "plaid"
    floral = "floral"
    polka_dot = "polka_dot"
    animal = "animal"
    geometric = "geometric"
    abstract = "abstract"
    paisley = "paisley"
    camouflage = "camouflage"
    colorblock = "colorblock"
    logo = "logo"
    tie_dye = "tie_dye"


class PriceTier(enum.Enum):
    budget = "budget"
    mid = "mid"
    contemporary = "contemporary"
    premium = "premium"
    luxury = "luxury"


class BrandRelation(enum.Enum):
    """How a user relates to a brand. One row per (profile, brand, relation)."""

    shop = "shop"
    aspire = "aspire"
    avoid = "avoid"


class MarketSegment(enum.Enum):
    """Where a trend observation was seen. Drives cross-segment lead/lag."""

    runway = "runway"
    designer = "designer"
    contemporary = "contemporary"
    instagram_native = "instagram_native"
    mass = "mass"
    social = "social"
    resale = "resale"


class OutfitSlotRole(enum.Enum):
    """The job an item does in an outfit, independent of its category."""

    top = "top"
    bottom = "bottom"
    dress = "dress"
    layer = "layer"
    outerwear = "outerwear"
    footwear = "footwear"
    bag = "bag"
    belt = "belt"
    jewelry = "jewelry"
    accessory = "accessory"


class AttributeSource(enum.Enum):
    """Kept distinct from Provenance: this records how an attribute value was
    determined, where Provenance records which system supplied the record."""

    source_field = "source_field"
    model_vision = "model_vision"
    model_text = "model_text"
    human_label = "human_label"
    derived = "derived"
