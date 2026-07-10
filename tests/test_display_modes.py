import pytest

from jewelry_on_hand.display_modes import (
    DisplayMode,
    SourceImageType,
    default_display_mode,
    validate_product_mode,
)
from jewelry_on_hand.product_types import ProductType


def test_necklace_defaults_to_worn():
    assert default_display_mode(ProductType.NECKLACE) is DisplayMode.WORN


@pytest.mark.parametrize("product_type", [ProductType.NECKLACE, ProductType.PENDANT_NECKLACE])
@pytest.mark.parametrize("display_mode", [DisplayMode.WORN, DisplayMode.HAND_HELD])
def test_complete_necklace_supports_worn_source_in_both_modes(product_type, display_mode):
    validate_product_mode(product_type, display_mode, SourceImageType.WORN_SOURCE)


def test_pendant_only_is_rejected_before_generation():
    with pytest.raises(ValueError, match="无链独立吊坠"):
        validate_product_mode(
            ProductType.PENDANT_ONLY,
            DisplayMode.HAND_HELD,
            SourceImageType.WORN_SOURCE,
        )


def test_unknown_product_is_rejected():
    with pytest.raises(ValueError, match="无法识别"):
        validate_product_mode(
            ProductType.UNKNOWN,
            DisplayMode.WORN,
            SourceImageType.WORN_SOURCE,
        )


@pytest.mark.parametrize(
    "source_type",
    [
        SourceImageType.FLAT_LAY_SOURCE,
        SourceImageType.HAND_HELD_SOURCE,
        SourceImageType.UNKNOWN_SOURCE,
    ],
)
def test_necklace_only_accepts_worn_source_in_first_phase(source_type):
    with pytest.raises(ValueError, match="真人佩戴原图"):
        validate_product_mode(ProductType.NECKLACE, DisplayMode.WORN, source_type)


def test_bracelet_worn_source_remains_supported():
    validate_product_mode(
        ProductType.BRACELET,
        DisplayMode.WORN,
        SourceImageType.WORN_SOURCE,
    )


def test_bracelet_hand_held_mode_does_not_expand_the_existing_boundary():
    with pytest.raises(ValueError, match="手串/手链.*手持展示"):
        validate_product_mode(
            ProductType.BRACELET,
            DisplayMode.HAND_HELD,
            SourceImageType.WORN_SOURCE,
        )


@pytest.mark.parametrize(
    ("product_type", "display_mode", "source_image_type", "message"),
    [
        ("necklace", DisplayMode.WORN, SourceImageType.WORN_SOURCE, "产品品类"),
        (ProductType.NECKLACE, "worn", SourceImageType.WORN_SOURCE, "展示模式"),
        (ProductType.NECKLACE, DisplayMode.WORN, "worn_source", "输入图类型"),
    ],
)
def test_validate_product_mode_rejects_non_enum_inputs(
    product_type,
    display_mode,
    source_image_type,
    message,
):
    with pytest.raises(ValueError, match=message):
        validate_product_mode(product_type, display_mode, source_image_type)
