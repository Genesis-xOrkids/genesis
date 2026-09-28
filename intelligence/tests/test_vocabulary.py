"""Category vocabulary and the non-apparel rule.

Titles here are real ones, read from the storefronts' own ``/products.json`` on
2026-09-28, wherever the case came from the catalog rather than from reasoning
about it. A made-up title tests the vocabulary against the words its author
expected; a real one tests it against the words merchants use.
"""

from __future__ import annotations

import pytest

from api.genesis_api.models.enums import Category
from intelligence.catalog.vocabulary import (
    CATEGORY_MODIFIER_TERMS,
    CATEGORY_TERMS,
    NON_APPAREL_TERMS,
    NonApparelKind,
    NotApparel,
    category_for,
    not_apparel,
)

# --- every term names its own category ------------------------------------


@pytest.mark.parametrize("phrase", sorted(CATEGORY_TERMS))
def test_every_category_term_standing_alone_names_its_own_category(phrase: str) -> None:
    """A longer phrase or a modifier that swallowed this one would make it dead:
    listed, and never the answer."""
    assert category_for(phrase) is CATEGORY_TERMS[phrase]


@pytest.mark.parametrize("phrase", sorted(CATEGORY_MODIFIER_TERMS))
def test_every_modifier_standing_alone_names_its_category(phrase: str) -> None:
    assert category_for(phrase) is CATEGORY_MODIFIER_TERMS[phrase]


@pytest.mark.parametrize("phrase", sorted(NON_APPAREL_TERMS))
def test_every_non_apparel_term_is_rejected_for_what_it_names(phrase: str) -> None:
    rejected = not_apparel(phrase)
    assert rejected == NotApparel(kind=NON_APPAREL_TERMS[phrase], phrase=phrase)


@pytest.mark.parametrize("phrase", sorted(NON_APPAREL_TERMS))
def test_no_non_apparel_term_is_also_a_garment(phrase: str) -> None:
    """A term in both vocabularies would be kept by the garment check every time,
    and so could never reject anything."""
    assert category_for(phrase) is None


# --- the terms added for C2, on the titles that asked for them -------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # lingerie
        ("Revolution V-Neck Bra", Category.lingerie),
        ("Core Rib Triangle Bralette", Category.lingerie),
        ("Essential No-Show Thong", Category.lingerie),
        ("Core Briefs 3-Pack", Category.lingerie),
        ("Flex Hipster 3-pack", Category.lingerie),
        ("Teen Light Leakproof No-Show Boyshort", Category.lingerie),
        ("Leakproof UltraThin No-Show Boybrief", Category.lingerie),
        ("Men's Best Damn™ Cotton Modal Boxer Brief 5\"", Category.lingerie),
        ("Men's Poplin Boxer in Lapis Confection Stripe", Category.lingerie),
        ("Core Trunks 12-Pack", Category.lingerie),
        ("Women's Seamless Underwear", Category.lingerie),
        ("Core Play String Bikini Briefs", Category.lingerie),
        ("Nippies Skin Adhesive Reusable Nipple Covers Coco", Category.lingerie),
        ("Pasties in Sand", Category.lingerie),
        ("Embroidery Lift Up Corset Ecru", Category.lingerie),
        ("Effortless Lace Teddy Black", Category.lingerie),
        # activewear
        ("Catalyst Sports Bra", Category.activewear),
        ("Girls Performance Flutter Sleeve Leotard", Category.activewear),
        ("Girls Gymnastics Unitard", Category.activewear),
        # sleepwear
        ("Washable Silk Robe", Category.sleepwear),
        ("Bathe Me Bathrobe", Category.sleepwear),
        ("The Lux Nightgown", Category.sleepwear),
        ("The Footie Pajama", Category.sleepwear),
        ("Baby Sleeper in French Blue", Category.sleepwear),
        ("The Sleep Sack", Category.sleepwear),
        ("The Quintessential Sleep Set", Category.sleepwear),
        ("Breathable Button Up Sleep Shirt", Category.sleepwear),
        ("The Tiny Sully PJ Set", Category.sleepwear),
        ("Women's Bamboo Stretch-Knit Pajama Short", Category.sleepwear),
        ("Pima After Bath Wrap in Baltic Blue", Category.sleepwear),
        ("The Towel Wrap", Category.sleepwear),
        ("Classic Pyjama Set", Category.sleepwear),
        ("Lace Nightie", Category.sleepwear),
        ("Striped Nightshirt", Category.sleepwear),
        ("Organic Sleepwear Set", Category.sleepwear),
        # shoes, boots, sandals
        ("The Casual Clog", Category.shoes),
        ("The Almond Slingback", Category.shoes),
        ("Twist Sling-Back Flat", Category.shoes),
        ("The Cruiser Mary Jane", Category.shoes),
        ("The Scuff Slipper", Category.shoes),
        ("The Driver", Category.shoes),
        ("The Max Square Ballerina", Category.shoes),
        ("The D'Orsay Espadrille", Category.shoes),
        ("The Penny Loafer Mule", Category.shoes),
        ("The Wedge", Category.shoes),
        ("Collegium x Everlane Moc Toe Derby", Category.shoes),
        ("Suede Moccasin", Category.shoes),
        ("The Western Bootie", Category.boots),
        ("The Weekend Slide", Category.sandals),
        ("The Men's Flip Flop", Category.sandals),
        # bags
        ("The Wristlet", Category.bag),
        ("The Universal Pouch", Category.bag),
        ("The Party Pouches", Category.bag),
        ("Zip Around Wallet", Category.bag),
        ("Card Holder", Category.bag),
        ("The Carryall", Category.bag),
        ("The Travel Duffel", Category.bag),
        ("The Weekender", Category.bag),
        ("The Belt Bag", Category.bag),
        ("Nylon Fanny Pack", Category.bag),
        # jewelry
        ("Capri Anklet", Category.jewelry),
        ("Petite Puff Charm", Category.jewelry),
        ("The Friendship Talisman Pendant", Category.jewelry),
        ("Three Diamond Choker", Category.jewelry),
        ("Sterling Silver Bangle", Category.jewelry),
        ("Tiny Pavé Nose Stud 14K", Category.jewelry),
        ("Seamless Titanium Piercing Hoop in Gold", Category.jewelry),
        ("Pearl Cluster Brooch", Category.jewelry),
        # hats, scarves, gloves, hosiery, eyewear
        ("Airlift Solar Visor", Category.hat),
        ("Wool Beret", Category.hat),
        ("Cashmere Snood", Category.scarf),
        ("Silk Scarves Set", Category.scarf),
        ("Cashmere Mittens", Category.gloves),
        ("MeMoí Thigh High Stockings Black", Category.hosiery),
        ("Sheer Pantyhose", Category.hosiery),
        ("ALO Wire Frame Sunglasses", Category.eyewear),
        # swimwear
        ("Laguna One Piece", Category.swimwear),
        ("Teen Racerback Tankini Swim Top", Category.swimwear),
        ("The Alexia Rashguard", Category.swimwear),
        ("Long Sleeve Rash Guard", Category.swimwear),
        ("Micro Chenille Cropped V-Neck Coverup", Category.swimwear),
        ("Polar Fleece Retreat Cover Up", Category.swimwear),
        ("Maxi Sarong Tigris", Category.swimwear),
        ("Swim High Waist Bottom in Black", Category.swimwear),
        # tops, shirts, sweaters, cardigans
        ("Modal Rib Long Sleeve", Category.top),
        ("SuperForm Rib Longsleeve", Category.top),
        ("CloudKnit Boxy Shortsleeve", Category.top),
        ("Women's Chelsea Short Sleeve", Category.top),
        ("Luxe Jersey Henley", Category.top),
        ("The Doris Mini Tunic", Category.top),
        ("The Canal Popover in Rinsed Indigo", Category.shirt),
        ("Pacifica Stretch Twill Overshirt", Category.shirt),
        ("Cloud 9 Terry Relaxed Crewneck", Category.sweater),
        ("Classic Crew Neck", Category.sweater),
        ("Cloud 9 Terry Sweatshirt", Category.sweater),
        ("Women Organic Quarter Zip", Category.sweater),
        ("Cloud 9 Fleece Half Zip", Category.sweater),
        ("Nimbus 1/4 Zip", Category.sweater),
        ("Whipped Cardi in Garnet", Category.cardigan),
        # jackets, jumpsuits, dresses, skirts
        ("Quilted Shacket", Category.jacket),
        ("The Jillee Ruffle Onesie", Category.jumpsuit),
        ("The Utility Coverall in Linen", Category.jumpsuit),
        ("Girls Flutter-Sleeve Bow Back Sundress", Category.dress),
        ("Studio Skort", Category.skirt),
    ],
)
def test_the_added_terms_resolve_the_titles_they_were_added_for(
    title: str, expected: Category
) -> None:
    assert category_for(title) is expected


# --- collisions ------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # "short" is the singular of "shorts", and it is also a sleeve length.
        ("Breezeweight Active Short Sleeve Tee", Category.top),
        ("Stretch Selvage Short Sleeve Shirt", Category.shirt),
        ("Women's Bamboo Stretch-Knit Short Sleeve Pajama Top", Category.sleepwear),
        ("Girls Short Sleeve Celestial Sequin Tutu Dress", Category.dress),
        ("Girls Performance Short-Sleeve Leotard", Category.activewear),
        ('Solemate™ 2.5" Short', Category.shorts),
        # A modifier names the garment only when no noun does.
        ("Conquer Reform Crewneck Short Sleeve", Category.top),
        ("Organic Cotton Crewneck Tee", Category.top),
        ("Cotton Henley Dress", Category.dress),
        ("Long Sleeve Mini Dress", Category.dress),
        ("Pima Long Sleeve Nightgown in Parisian Green", Category.sleepwear),
        ("Quarter Zip Jacket", Category.jacket),
        ("Popover Dress", Category.dress),
        ("One Piece Jumpsuit", Category.jumpsuit),
        ("Corset Dress", Category.dress),
        ("Teddy Fleece Jacket", Category.jacket),
        ("The Teddy Slipper", Category.shoes),
        ("Cozy Slipper Socks", Category.hosiery),
        ("Wedge Heel Boot", Category.boots),
        ("Slide Buckle Belt", Category.belt),
        ("The ReWool Duffle Coat", Category.coat),
        ("Kangaroo Pouch Pocket Tee", Category.top),
        ("Pearl Charm Bracelet", Category.jewelry),
        ("Hoop Earrings", Category.jewelry),
        ("Choker Neck Top", Category.top),
        ("Ballerina Wrap Top", Category.top),
        ("Driver Cap", Category.hat),
        ("Derby Hat", Category.hat),
        ("Stud Detail Boot", Category.boots),
        # Nouns that meet inside one title.
        ("Bra Top", Category.top),
        ("Thong Sandal", Category.sandals),
        ("Classic Swim Shorts", Category.swimwear),
        ('5" Vintage Swim Trunk', Category.swimwear),
        ("Swim Brief", Category.swimwear),
        ("Sweatshirt Dress", Category.dress),
        ("Girls Glittery Mary Jane Dress Shoe", Category.shoes),
        ("Kids Ballet Booties", Category.boots),
        ("Sieve Thong in Buff (Pack)", Category.lingerie),
        ("Sculpt Cheeky Low Rise Swim Bottom", Category.swimwear),
    ],
)
def test_colliding_terms_resolve_to_the_garment_the_title_names(
    title: str, expected: Category
) -> None:
    assert category_for(title) is expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Girls Ballet Dresses", Category.dress),
        ("Luxury Watches", Category.watch),
        ("Silk Scarves", Category.scarf),
        ("Beaded Pouches", Category.bag),
    ],
)
def test_sibilant_plurals_match(title: str, expected: Category) -> None:
    """ "Dresses" is "dress" plus "es", and until it was accepted a whole product
    type of dresses matched nothing."""
    assert category_for(title) is expected


def test_within_one_text_a_modifier_outranks_nothing_but_across_texts_order_holds() -> None:
    """The title leads, as for every attribute. A modifier in the title answers
    before a noun on the shelf, because the shelf is the merchant's filing and
    the title is the garment's name."""
    assert category_for("Relaxed Crewneck", "T-Shirts") is Category.sweater
    assert category_for("The Monty", "Womens Shoes") is Category.shoes
    assert category_for(None, "Underwear_Bras_Scoop") is Category.lingerie


# --- the non-apparel rule ---------------------------------------------------


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("Luxe Bath Towels", NonApparelKind.home_goods),
        ("Nantucket Washcloths", NonApparelKind.home_goods),
        ("Bamboo Fitted Sheet", NonApparelKind.home_goods),
        ("Luxe Bath Sheets", NonApparelKind.home_goods),
        ("Bamboo Pillowcases", NonApparelKind.home_goods),
        ("Striped Linen Throw Pillow", NonApparelKind.home_goods),
        ("Soft-Wash Cotton Quilted Shams", NonApparelKind.home_goods),
        ("Bamboo Duvet Cover", NonApparelKind.home_goods),
        ("Bubble Cuddle Blanket", NonApparelKind.home_goods),
        ("Down Alternative Throw", NonApparelKind.home_goods),
        ("Waterfront Coverlet", NonApparelKind.home_goods),
        ("Bamboo Bedding Basic Bundle", NonApparelKind.home_goods),
        ("Complete Luxe Bath Bundle", NonApparelKind.home_goods),
        ("Plush Loop Bath Mat", NonApparelKind.home_goods),
        ("Everlane x Peace & Quiet Welcome Mat", NonApparelKind.home_goods),
        ("The Placemat (Set of 4)", NonApparelKind.home_goods),
        ("The Coaster (Set of 4)", NonApparelKind.home_goods),
        ("The Cocktail Napkin Set", NonApparelKind.home_goods),
        ("The Candle in Drift", NonApparelKind.home_goods),
        ("Gah! Water Bottle", NonApparelKind.home_goods),
        ("Jewelry Tray", NonApparelKind.home_goods),
        ("Vintage Silver Shell Dish", NonApparelKind.home_goods),
        ("Everlane x Peace & Quiet Suede Catchall", NonApparelKind.home_goods),
        ("Cosmic Star Ornament", NonApparelKind.home_goods),
        ("The Packing Cubes", NonApparelKind.home_goods),
        ("Travel Mini Jewellery Box", NonApparelKind.home_goods),
        ("Keepsake Tin", NonApparelKind.home_goods),
        ("Cooling Mattress Protector", NonApparelKind.home_goods),
        ("Coronado Lounge Chair", NonApparelKind.home_goods),
        ("Digital Gift Card", NonApparelKind.gift_or_service),
        ("ALO e-Gift Card", NonApparelKind.gift_or_service),
        ("£50 Gift Voucher", NonApparelKind.gift_or_service),
        ("E-Gift Code", NonApparelKind.gift_or_service),
        ("Signature Gift Wrapping", NonApparelKind.gift_or_service),
        ("Small DIY Gift Envelope", NonApparelKind.gift_or_service),
        ("Stelle Gift Box", NonApparelKind.gift_or_service),
        ("ShipInsure Package Protection", NonApparelKind.gift_or_service),
        ("Expedited shipping", NonApparelKind.gift_or_service),
        ("Free Returns Coverage", NonApparelKind.gift_or_service),
        ("Easy Returns", NonApparelKind.gift_or_service),
        ("Cozy Earth Annual Membership", NonApparelKind.gift_or_service),
        ("Bamboo Sheet Swatch", NonApparelKind.gift_or_service),
        ("Alo Access Reward", NonApparelKind.loyalty_reward),
        ("Mini Shampoo & Conditioner Duo", NonApparelKind.personal_care),
        ("Mega-C Body Wash", NonApparelKind.personal_care),
        ("Hill House x Wet Brush Pro Detangler Brush", NonApparelKind.personal_care),
        ("Hill House x Wet Brush Heatless Curler Set", NonApparelKind.personal_care),
        ("Enzyme Facial Cleanser", NonApparelKind.personal_care),
        ("Hydrating Serum", NonApparelKind.personal_care),
        ("Chill & Unwind Essential Oil (Lavender)", NonApparelKind.personal_care),
        ("Cashmere Comb", NonApparelKind.personal_care),
        ("Uplifting Yoga Block", NonApparelKind.fitness_equipment),
        ("Bend It Yoga Wheel", NonApparelKind.fitness_equipment),
        ("Extra Long Yoga Strap", NonApparelKind.fitness_equipment),
    ],
)
def test_titles_that_name_only_non_apparel_are_rejected(title: str, kind: NonApparelKind) -> None:
    rejected = not_apparel(title)
    assert rejected is not None
    assert rejected.kind is kind


@pytest.mark.parametrize(
    "title",
    [
        # A garment beside a non-apparel word is a garment.
        "Luxe Bath Robe",
        "Ribbed Terry Bath Robe",
        "Blanket Scarf",
        "Throw-On Midi Dress",
        "UPF 50+ Long Sleeve Sun Protection Shirt",
        "Places To Go UV Protection Jacket",
        "Pepper Pillows Reusable Nipple Covers (1 Pair)",
        "Pillow Slide",
        "Quilted Colville Overshirt",
        "Sample Sale Midi Dress",
        "Free Shipping Tee",
        "Yoga Mat Sock",
        # A set or bundle of garments is apparel.
        "The Classic All You Bra Trio Bundle",
        "Women's Bamboo Stretch-Knit Short Sleeve Pajama Set",
        "Mixed Metal Cosmic Dome Hoops Gift Set",
        "Supima® Cotton Wirefree Bra Duo Black",
        # Not knowing what a thing is does not show it is not clothing.
        "The Point II",
        "Teen Leakproof Starter Kit",
        "The Belle Bow",
        "UPF 50+ Sun Protection Face Mask",
        "",
    ],
)
def test_garments_and_unknowns_are_kept(title: str) -> None:
    assert not_apparel(title) is None


def test_the_quarantine_reason_leads_with_a_name_a_count_can_group_on() -> None:
    rejected = not_apparel("Luxe Bath Towel Set")
    assert str(rejected) == "not_apparel: home_goods (towel)"
