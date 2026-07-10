import pytest

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType


def test_bracelet_policy_preserves_existing_category():
    policy = get_category_policy(ProductType.BRACELET)
    assert policy.product_type is ProductType.BRACELET
    assert DisplayMode.WORN in policy.supported_modes


@pytest.mark.parametrize("product_type", [ProductType.NECKLACE, ProductType.PENDANT_NECKLACE])
def test_necklace_policy_supports_worn_and_hand_held(product_type):
    policy = get_category_policy(product_type)
    assert policy.max_layer_count == 3
    assert policy.supported_modes == frozenset({DisplayMode.WORN, DisplayMode.HAND_HELD})


def test_pendant_only_policy_explains_current_block():
    policy = get_category_policy(ProductType.PENDANT_ONLY)
    with pytest.raises(ValueError, match="不支持无链独立吊坠"):
        policy.validate_generation(layer_count=1, is_independent_multi_item=False)


def test_unknown_has_no_policy():
    with pytest.raises(ValueError, match="无法识别"):
        get_category_policy(ProductType.UNKNOWN)


def test_necklace_policy_rejects_more_than_three_layers():
    policy = get_category_policy(ProductType.NECKLACE)
    with pytest.raises(ValueError, match="1 至 3 层"):
        policy.validate_generation(layer_count=4, is_independent_multi_item=False)


def test_necklace_policy_rejects_independent_multi_item_stacking():
    policy = get_category_policy(ProductType.NECKLACE)
    with pytest.raises(ValueError, match="多件独立项链"):
        policy.validate_generation(layer_count=2, is_independent_multi_item=True)


@pytest.mark.parametrize(
    "product_type",
    [
        ProductType.BRACELET,
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
        ProductType.PENDANT_ONLY,
    ],
)
def test_policy_exposes_category_name_and_basic_qc_items(product_type):
    policy = get_category_policy(product_type)

    assert policy.category_name == product_type.display_name
    assert policy.basic_qc_items
    assert all(isinstance(item, str) and item for item in policy.basic_qc_items)


def test_bracelet_policy_enforces_its_single_layer_limit():
    policy = get_category_policy(ProductType.BRACELET)
    with pytest.raises(ValueError, match="手串/手链.*1 层"):
        policy.validate_generation(layer_count=2, is_independent_multi_item=False)
