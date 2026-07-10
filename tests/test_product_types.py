import pytest

from jewelry_on_hand.product_types import ProductType, normalize_product_type


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("手链", ProductType.BRACELET),
        ("手串/手链", ProductType.BRACELET),
        ("朱砂手链/手串", ProductType.BRACELET),
        ("bracelet", ProductType.BRACELET),
        ("普通项链", ProductType.NECKLACE),
        ("珠链", ProductType.NECKLACE),
        ("necklace", ProductType.NECKLACE),
        ("带链吊坠", ProductType.PENDANT_NECKLACE),
        ("吊坠项链", ProductType.PENDANT_NECKLACE),
        ("pendant necklace", ProductType.PENDANT_NECKLACE),
        ("无链独立吊坠", ProductType.PENDANT_ONLY),
        ("pendant only", ProductType.PENDANT_ONLY),
        ("戒指", ProductType.UNKNOWN),
    ],
)
def test_normalize_product_type(raw, expected):
    assert normalize_product_type(raw) is expected


def test_empty_product_type_is_unknown():
    assert normalize_product_type("") is ProductType.UNKNOWN


def test_ambiguous_free_text_is_not_silently_guessed():
    assert normalize_product_type("手链或项链") is ProductType.UNKNOWN


@pytest.mark.parametrize(
    "raw",
    [
        "不是项链",
        "这是项链吗？",
        "疑似项链",
        "可能是项链",
        "项链或戒指",
        "项链和戒指组合",
        "项链和耳钉",
        "项链搭配耳钉",
        "项链和其他饰品",
        "耳钉搭配项链",
    ],
)
def test_uncertain_or_mixed_category_text_is_unknown(raw):
    assert normalize_product_type(raw) is ProductType.UNKNOWN


@pytest.mark.parametrize(
    "raw",
    [
        "maybe necklace",
        "necklace with earrings",
        "spring necklace",
        "knot necklace",
    ],
)
def test_english_free_text_beyond_complete_alias_is_unknown(raw):
    assert normalize_product_type(raw) is ProductType.UNKNOWN
