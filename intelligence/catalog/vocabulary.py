"""Mapping source vocabulary onto the canonical enums.

Retailers describe garments in their own words, and this is where those words
become the platform's terms. It runs as a deterministic pre-pass before any
model is called: a title that plainly says "midi wrap dress" should not cost a
vision call to classify, and the cases it cannot decide are left null for the
extraction route to fill.

Matching is longest-phrase-first. "Shirt dress" is a dress, not a shirt, and a
shorter pattern that fires first would get it wrong every time.

It also decides what is not a fashion item at all. Storefronts sell towels,
bedding, gift cards and loyalty rewards through the same feed as their
clothing, and every connector asks :func:`not_apparel` before translating a
record, so the rule is one rule however many sources there are.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import TypedDict

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
    "sweatshirt dress": Category.dress,
    "sundress": Category.dress,
    "kaftan": Category.dress,
    "caftan": Category.dress,
    "dress": Category.dress,
    "jumpsuit": Category.jumpsuit,
    "romper": Category.jumpsuit,
    "playsuit": Category.jumpsuit,
    "coverall": Category.jumpsuit,
    "onesie": Category.jumpsuit,
    "trench coat": Category.coat,
    "puffer": Category.coat,
    "parka": Category.coat,
    "overcoat": Category.coat,
    "peacoat": Category.coat,
    "pea coat": Category.coat,
    "anorak": Category.coat,
    "poncho": Category.coat,
    "cape": Category.coat,
    "windbreaker": Category.coat,
    "raincoat": Category.coat,
    "coat": Category.coat,
    "blazer": Category.blazer,
    "sport coat": Category.blazer,
    "denim jacket": Category.jacket,
    "bomber": Category.jacket,
    "shacket": Category.jacket,
    "overshirt": Category.jacket,
    "jacket": Category.jacket,
    "waistcoat": Category.vest,
    "vest": Category.vest,
    "gilet": Category.vest,
    "cardigan": Category.cardigan,
    "cardi": Category.cardigan,
    "turtleneck": Category.sweater,
    "sweater": Category.sweater,
    "jumper": Category.sweater,
    "pullover": Category.sweater,
    "hoodie": Category.sweater,
    "sweatshirt": Category.sweater,
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
    "tunic": Category.top,
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
    "skirt": Category.skirt,
    "skort": Category.skirt,
    "sports bra": Category.activewear,
    "leotard": Category.activewear,
    "unitard": Category.activewear,
    "nipple cover": Category.lingerie,
    "underwear": Category.lingerie,
    "bralette": Category.lingerie,
    "pasties": Category.lingerie,
    "boxer": Category.lingerie,
    "bra": Category.lingerie,
    "sleep shirt": Category.sleepwear,
    "sleep sack": Category.sleepwear,
    "sleep set": Category.sleepwear,
    "sleepwear": Category.sleepwear,
    "nightgown": Category.sleepwear,
    "nightshirt": Category.sleepwear,
    "nightie": Category.sleepwear,
    "bathrobe": Category.sleepwear,
    "sleeper": Category.sleepwear,
    "pajama": Category.sleepwear,
    "pyjama": Category.sleepwear,
    "robe": Category.sleepwear,
    "kimono": Category.sleepwear,
    "wearable blanket": Category.sleepwear,
    "pj": Category.sleepwear,
    "sneaker": Category.sneakers,
    "trainer": Category.sneakers,
    "bootie": Category.boots,
    "boot": Category.boots,
    "flip flop": Category.sandals,
    "slide": Category.sandals,
    "sandal": Category.sandals,
    "mary jane": Category.shoes,
    "espadrille": Category.shoes,
    "slingback": Category.shoes,
    "sling back": Category.shoes,
    "moccasin": Category.shoes,
    "heel": Category.shoes,
    "loafer": Category.shoes,
    "flat": Category.shoes,
    "pump": Category.shoes,
    "clog": Category.shoes,
    "mule": Category.shoes,
    "shoe": Category.shoes,
    "handbag": Category.bag,
    "tote": Category.bag,
    "clutch": Category.bag,
    "crossbody": Category.bag,
    "backpack": Category.bag,
    "belt bag": Category.bag,
    "fanny pack": Category.bag,
    "card holder": Category.bag,
    "wristlet": Category.bag,
    "carryall": Category.bag,
    "wallet": Category.bag,
    "bag": Category.bag,
    "belt": Category.belt,
    "scarves": Category.scarf,
    "scarf": Category.scarf,
    "snood": Category.scarf,
    "shawl": Category.scarf,
    "hat": Category.hat,
    "cap": Category.hat,
    "beanie": Category.hat,
    "beret": Category.hat,
    "visor": Category.hat,
    "sunglass": Category.eyewear,
    "watch": Category.watch,
    "necklace": Category.jewelry,
    "earring": Category.jewelry,
    "bracelet": Category.jewelry,
    "ring": Category.jewelry,
    "pendant": Category.jewelry,
    "anklet": Category.jewelry,
    "bangle": Category.jewelry,
    "brooch": Category.jewelry,
    "sock": Category.hosiery,
    "tight": Category.hosiery,
    "stocking": Category.hosiery,
    "pantyhose": Category.hosiery,
    "glove": Category.gloves,
    "mitten": Category.gloves,
    "swimsuit": Category.swimwear,
    "bikini": Category.swimwear,
    "tankini": Category.swimwear,
    "rash guard": Category.swimwear,
    "rashguard": Category.swimwear,
    "cover up": Category.swimwear,
    "coverup": Category.swimwear,
    "sarong": Category.swimwear,
    "swim": Category.swimwear,
}

# Words that name an item standing alone and only describe it beside another
# noun. "Relaxed Crewneck" is a sweatshirt; a "Crewneck Tee" is a tee. "The
# Scuff Slipper" is a shoe; a "Slipper Sock" is a sock. "The Travel Duffel" is a
# bag; a "Duffle Coat" is a coat. "Knit" is a construction rather than a garment:
# as a noun it filed "Knit Tank Top", "Stretch-Knit Pant" and "Knit Kimono Robe"
# as sweaters.
#
# Longest-first matching cannot express that, because the modifier is often the
# longer word, so these are a second tier: removed before nouns are matched, and
# consulted only when no noun is left (see :func:`category_for`). Removing them
# first is also what keeps "Short Sleeve Tee", "Short Robe" and "Short Pajama Set"
# out of shorts: "short" names shorts alone ("Bike Short"), and beside another
# garment it describes a length. The same holds for the cuts of underwear, which
# describe swimwear as readily: a "Hipster Bikini Bottom" and a "Swim Boyshort"
# are swimwear, a "Core Thong" is lingerie. "Bikini brief" is a cut of underwear
# in its own right, so it is listed whole and outlasts the "bikini" inside it.
CATEGORY_MODIFIER_TERMS: dict[str, Category] = {
    "short": Category.shorts,
    "jean short": Category.shorts,
    "denim short": Category.shorts,
    "chino short": Category.shorts,
    "cargo short": Category.shorts,
    "sweat short": Category.shorts,
    "board short": Category.shorts,
    "shawl collar": Category.sweater,
    "bikini brief": Category.lingerie,
    "boyshort": Category.lingerie,
    "boybrief": Category.lingerie,
    "hipster": Category.lingerie,
    "thong": Category.lingerie,
    "brief": Category.lingerie,
    "trunk": Category.lingerie,
    "short sleeve": Category.top,
    "shortsleeve": Category.top,
    "long sleeve": Category.top,
    "longsleeve": Category.top,
    "henley": Category.top,
    "popover": Category.shirt,
    "knit": Category.sweater,
    "crewneck": Category.sweater,
    "crew neck": Category.sweater,
    "quarter zip": Category.sweater,
    "half zip": Category.sweater,
    "1/4 zip": Category.sweater,
    "one piece": Category.swimwear,
    "corset": Category.lingerie,
    "teddy": Category.lingerie,
    "ballerina": Category.shoes,
    "slipper": Category.shoes,
    "driver": Category.shoes,
    "wedge": Category.shoes,
    "derby": Category.shoes,
    "weekender": Category.bag,
    "duffel": Category.bag,
    "duffle": Category.bag,
    "pouch": Category.bag,
    "choker": Category.jewelry,
    "charm": Category.jewelry,
    "hoop": Category.jewelry,
    "stud": Category.jewelry,
}

# Things a person wears that the taxonomy has no category for. A name or shelf
# naming one and no garment leaves the category null, which stops a tag or a
# description supplying a wrong one: Hill House tags its hair bows "Dresses".
# Whether these get a category of their own is an open decision, not this list's.
UNCATEGORISED_TERMS: dict[str, None] = dict.fromkeys(
    (
        "hair bow",
        "bow",
        "scrunchie",
        "headband",
        "claw clip",
        "hair clip",
        "hair tie",
        "barrette",
        "barette",
    )
)

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


class NonApparelKind(enum.Enum):
    """What a record is when it is not something a person wears.

    Not stored anywhere: it names the reason a record was quarantined, so the
    quarantine can be counted by cause.
    """

    home_goods = "home_goods"
    gift_or_service = "gift_or_service"
    loyalty_reward = "loyalty_reward"
    personal_care = "personal_care"
    fitness_equipment = "fitness_equipment"


# Words that, in a title naming no garment, say the record is not a fashion
# item. The garment check comes first (see :func:`not_apparel`), so a "Bath
# Robe", a "Blanket Scarf" and a "Sun Protection Shirt" are clothing whatever
# else their titles say.
NON_APPAREL_TERMS: dict[str, NonApparelKind] = {
    "towel": NonApparelKind.home_goods,
    "washcloth": NonApparelKind.home_goods,
    "wash cloth": NonApparelKind.home_goods,
    "sheet": NonApparelKind.home_goods,
    "pillowcase": NonApparelKind.home_goods,
    "pillow case": NonApparelKind.home_goods,
    "pillow": NonApparelKind.home_goods,
    "sham": NonApparelKind.home_goods,
    "duvet": NonApparelKind.home_goods,
    "quilt": NonApparelKind.home_goods,
    "blanket": NonApparelKind.home_goods,
    "throw": NonApparelKind.home_goods,
    "coverlet": NonApparelKind.home_goods,
    "bedding": NonApparelKind.home_goods,
    "mattress": NonApparelKind.home_goods,
    "bath": NonApparelKind.home_goods,
    "mat": NonApparelKind.home_goods,
    "placemat": NonApparelKind.home_goods,
    "coaster": NonApparelKind.home_goods,
    "napkin": NonApparelKind.home_goods,
    "candle": NonApparelKind.home_goods,
    "mug": NonApparelKind.home_goods,
    "water bottle": NonApparelKind.home_goods,
    "tray": NonApparelKind.home_goods,
    "dish": NonApparelKind.home_goods,
    "catchall": NonApparelKind.home_goods,
    "ornament": NonApparelKind.home_goods,
    "chair": NonApparelKind.home_goods,
    "packing cube": NonApparelKind.home_goods,
    "jewelry box": NonApparelKind.home_goods,
    "jewellery box": NonApparelKind.home_goods,
    "keepsake tin": NonApparelKind.home_goods,
    "gift card": NonApparelKind.gift_or_service,
    "e-gift": NonApparelKind.gift_or_service,
    "egift": NonApparelKind.gift_or_service,
    "gift voucher": NonApparelKind.gift_or_service,
    "gift certificate": NonApparelKind.gift_or_service,
    "gift code": NonApparelKind.gift_or_service,
    "gift wrap": NonApparelKind.gift_or_service,
    "gift wrapping": NonApparelKind.gift_or_service,
    "gift envelope": NonApparelKind.gift_or_service,
    "gift box": NonApparelKind.gift_or_service,
    "warranty": NonApparelKind.gift_or_service,
    "insurance": NonApparelKind.gift_or_service,
    "package protection": NonApparelKind.gift_or_service,
    "shipping protection": NonApparelKind.gift_or_service,
    "returns coverage": NonApparelKind.gift_or_service,
    "returns": NonApparelKind.gift_or_service,
    "shipping": NonApparelKind.gift_or_service,
    "donation": NonApparelKind.gift_or_service,
    "carbon offset": NonApparelKind.gift_or_service,
    "extended care": NonApparelKind.gift_or_service,
    "membership": NonApparelKind.gift_or_service,
    "subscription": NonApparelKind.gift_or_service,
    "personalization": NonApparelKind.gift_or_service,
    "swatch": NonApparelKind.gift_or_service,
    "sample": NonApparelKind.gift_or_service,
    "reward": NonApparelKind.loyalty_reward,
    "shampoo": NonApparelKind.personal_care,
    "conditioner": NonApparelKind.personal_care,
    "body wash": NonApparelKind.personal_care,
    "detangler": NonApparelKind.personal_care,
    "curler": NonApparelKind.personal_care,
    "supplement": NonApparelKind.personal_care,
    "multivitamin": NonApparelKind.personal_care,
    "cleanser": NonApparelKind.personal_care,
    "cleansing cloth": NonApparelKind.personal_care,
    "polishing cloth": NonApparelKind.personal_care,
    "moisturizer": NonApparelKind.personal_care,
    "serum": NonApparelKind.personal_care,
    "eye cream": NonApparelKind.personal_care,
    "night cream": NonApparelKind.personal_care,
    "body butter": NonApparelKind.personal_care,
    "body oil": NonApparelKind.personal_care,
    "essential oil": NonApparelKind.personal_care,
    "mousse": NonApparelKind.personal_care,
    "comb": NonApparelKind.personal_care,
    "yoga block": NonApparelKind.fitness_equipment,
    "yoga wheel": NonApparelKind.fitness_equipment,
    "yoga strap": NonApparelKind.fitness_equipment,
    "yoga mat": NonApparelKind.fitness_equipment,
}


@dataclass(frozen=True)
class NotApparel:
    """A title that names something other than apparel, and the words that said so."""

    kind: NonApparelKind
    phrase: str

    def __str__(self) -> str:
        """The quarantine reason, led by a name a count can group on."""
        return f"not_apparel: {self.kind.value} ({self.phrase})"


def _tokens(text: str) -> str:
    """Reduce text to space-separated words.

    Punctuation carries no meaning here and varies by retailer: "V-Neck",
    "v neck", and "V_Neck" are the same claim about the same garment. Both the
    haystack and the patterns go through this, so they meet in one form.
    """
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def _match[T](text: str, terms: dict[str, T]) -> T | None:
    phrase = _phrase_in(text, terms)
    return None if phrase is None else terms[phrase]


def _phrase_in[T](text: str, terms: dict[str, T]) -> str | None:
    """The longest of ``terms`` the text contains.

    "Shirt dress" contains "shirt", so a shorter pattern firing first would file
    every shirt dress under shirts. Between two phrases of equal length the one
    listed first wins, which is why "top" is listed before "bra": a "Bra Top" is
    a top.
    """
    haystack = _tokens(text)
    for phrase in sorted(terms, key=len, reverse=True):
        if any(f" {form} " in haystack for form in _inflections(_tokens(phrase).strip())):
            return phrase
    return None


def _without[T](text: str, terms: dict[str, T]) -> str:
    """The text, with every one of ``terms`` taken out of it."""
    haystack = _tokens(text)
    for phrase in sorted(terms, key=len, reverse=True):
        for form in _inflections(_tokens(phrase).strip()):
            while f" {form} " in haystack:
                haystack = haystack.replace(f" {form} ", " ")
    return haystack


def _inflections(phrase: str) -> tuple[str, ...]:
    """The phrase, plus the plural and singular it might appear as.

    Both directions are needed and only one was there originally. Titles say
    "Sailor Jean" where the vocabulary says "jeans", so matching only
    phrase-plus-s filed a whole category of denim under trousers. A sibilant
    ending takes "-es", and until it was accepted "Dresses", "Watches" and
    "Sunglasses" matched nothing at all.

    The singular is a trap as well as a fix: "short" is the singular of
    "shorts", and so is the "short" in "Short Sleeve Tee". That one is answered
    by :data:`CATEGORY_MODIFIER_TERMS` rather than here, because "Bike Short" is
    shorts.
    """
    forms = {phrase, f"{phrase}s"}
    if phrase.endswith(("s", "x", "z", "ch", "sh")):
        forms.add(f"{phrase}es")
    if phrase.endswith("es") and len(phrase) > 3:
        forms.add(phrase[:-2])
    if phrase.endswith("s") and len(phrase) > 2:
        forms.add(phrase[:-1])
    return tuple(forms)


class GarmentAttributes(TypedDict):
    """Every attribute derivable from a garment's own descriptive text.

    Unpacked straight into ``NormalizedProduct(**attributes_for(*texts))``, so
    the keys are the model's field names rather than the helpers' names. It is a
    ``TypedDict`` and not a dataclass for exactly that reason: mypy checks the
    unpacking key by key, so a key that stops matching a ``NormalizedProduct``
    field is a type error rather than a silent runtime one.
    """

    category: Category | None
    silhouette: Silhouette | None
    neckline: Neckline | None
    sleeve_length: SleeveLength | None
    sleeve_style: SleeveStyle | None
    garment_length: GarmentLength | None
    rise: Rise | None
    fit: Fit | None
    pattern: Pattern | None


def attributes_for(*texts: str | None) -> GarmentAttributes:
    """Derive every text-derived attribute at once, in trustworthiness order.

    Connectors differ in where a garment's descriptive text comes from - a
    Shopify product type, an affiliate feed's category column - but not in what
    is derived from it once they have it. Keeping that list here means a tenth
    attribute is added in one place rather than in every connector, and no
    connector can quietly derive eight of the nine.

    Gender is deliberately absent: it is almost never in a title and almost
    always in a tag, so each connector passes its own ordering to
    :func:`gender_for`. That difference is real, not duplication.
    """
    return GarmentAttributes(
        category=category_for(*texts),
        silhouette=silhouette_for(*texts),
        neckline=neckline_for(*texts),
        sleeve_length=sleeve_length_for(*texts),
        sleeve_style=sleeve_style_for(*texts),
        garment_length=length_for(*texts),
        rise=rise_for(*texts),
        fit=fit_for(*texts),
        pattern=pattern_for(*texts),
    )


def category_for(*texts: str | None) -> Category | None:
    """What the item is, from the first text that says.

    Texts come in order of trustworthiness, as for every attribute (see
    :func:`_first`), and every connector passes the item's own name first and
    the merchant's category for it second. A noun outranks a modifier (see
    :data:`CATEGORY_MODIFIER_TERMS`) across those two: the modifiers are taken
    out before the nouns are looked for, and named only when neither text has a
    noun left. A modifier describes the garment and the shelf's noun names it,
    so a "Super Fine Cashmere Long Sleeve Crewneck" filed under "Crew Neck
    Sweaters" is a sweater, and "Long Sleeve" alone is a top.

    Tags and descriptions follow one text at a time, because they name the
    garments an item is worn with as readily as the item itself. That is also
    why a text naming something worn that has no category (see
    :data:`UNCATEGORISED_TERMS`) ends the search with null rather than handing
    it on to them.
    """
    for group in (texts[:2], *((text,) for text in texts[2:])):
        nouns = tuple(_without(text, CATEGORY_MODIFIER_TERMS) if text else None for text in group)
        found = _first(CATEGORY_TERMS, nouns)
        if found is not None:
            return found
        if _names_any(UNCATEGORISED_TERMS, nouns):
            return None
        found = _first(CATEGORY_MODIFIER_TERMS, group)
        if found is not None:
            return found
    return None


def _names_any[T](terms: dict[str, T], texts: tuple[str | None, ...]) -> bool:
    return any(text and _phrase_in(text, terms) is not None for text in texts)


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


def not_apparel(title: str, *shelves: str | None) -> NotApparel | None:
    """Why a record is not a fashion item, when its title says so.

    Conservative by construction, in two directions. Only the title can reject:
    a department called "Home" also shelves the robes. The merchant's category
    for the item can protect it as well as the title: a record is apparel if its
    title, or any of ``shelves`` (the product type or feed category), names
    something worn, however much else the title says. So a "Bath Robe" stays, a
    "Bra Trio Bundle" stays, and a "Waffle Bath Wrap" filed under "Robes" stays.
    A set or bundle is judged by what it names, and a "Bath Towel Set" names
    only towels. A title naming neither is kept and left uncategorised, because
    not knowing what a thing is does not show that it is not clothing.

    Tags and descriptions cannot protect. Both name what an item is sold beside
    as readily as the item: Alo tags its yoga blocks with its tops, and Cozy
    Earth tags its bedding bundles with its slippers.
    """
    texts = (title, *shelves)
    if category_for(*texts) is not None or _names_any(UNCATEGORISED_TERMS, texts):
        return None
    phrase = _phrase_in(title, NON_APPAREL_TERMS)
    if phrase is None:
        return None
    return NotApparel(kind=NON_APPAREL_TERMS[phrase], phrase=phrase)


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
