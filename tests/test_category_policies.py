from pathlib import Path

import pytest

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow
from jewelry_on_hand.product_types import ProductType


def necklace_product(display_mode="worn"):
    return ProductAnalysis.from_dict(
        {
            "product_type": "普通项链",
            "detected_product_type": "necklace",
            "confirmed_product_type": "necklace",
            "classification_confidence": "high",
            "classification_evidence": ["可见完整项链结构"],
            "classification_source": "model",
            "wear_position": "颈部和锁骨",
            "visible_appearance": "单层珠链",
            "color_family": ["白色"],
            "style_mood": "清透",
            "composition": "胸前近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "source_image_type": "worn_source",
            "display_mode": display_mode,
            "layer_count": 1,
            "length_category": "collarbone",
        }
    )


def necklace_reference(**overrides):
    data = {
        "index": 1,
        "file_name": "necklace.jpg",
        "relative_path": "necklace.jpg",
        "absolute_path": Path("C:/tmp/necklace.jpg"),
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "真人佩戴构图参考",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "清透自然光",
        "scene_keywords": "锁骨 胸前",
        "jewelry_type": "项链",
        "recommended_usage": "项链真人佩戴展示",
        "notes": "颈部和胸前完整，无裁切",
        "confidence": "高",
        "file_exists": True,
        "applicable_product_types": "necklace,pendant_necklace",
        "applicable_display_modes": "worn",
        "framing": "胸前半身",
        "visible_body_regions": "颈部 锁骨 胸前",
        "product_visibility": "高",
        "neck_visibility": "高",
        "collarbone_visibility": "高",
        "chest_visibility": "高",
        "hand_visibility": "低",
        "collar_type": "低领",
        "clothing_occlusion_risk": "低",
        "hair_occlusion_risk": "低",
        "existing_jewelry": "细项链",
        "crop_risk": "低",
    }
    data.update(overrides)
    return ReferenceRow(**data)


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


def test_non_enum_product_type_has_no_policy():
    with pytest.raises(ValueError, match="产品品类.*ProductType"):
        get_category_policy("necklace")


@pytest.mark.parametrize("layer_count", [1, 2, 3])
def test_necklace_policy_accepts_one_to_three_layers(layer_count):
    policy = get_category_policy(ProductType.NECKLACE)
    policy.validate_generation(
        layer_count=layer_count,
        is_independent_multi_item=False,
    )


def test_necklace_policy_rejects_more_than_three_layers():
    policy = get_category_policy(ProductType.NECKLACE)
    with pytest.raises(ValueError, match="1 至 3 层"):
        policy.validate_generation(layer_count=4, is_independent_multi_item=False)


def test_necklace_policy_rejects_independent_multi_item_stacking():
    policy = get_category_policy(ProductType.NECKLACE)
    with pytest.raises(ValueError, match="多件独立项链"):
        policy.validate_generation(layer_count=2, is_independent_multi_item=True)


def test_pendant_necklace_policy_rejects_independent_multi_item_stacking():
    policy = get_category_policy(ProductType.PENDANT_NECKLACE)
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


@pytest.mark.parametrize(
    "product_type",
    [
        ProductType.BRACELET,
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
        ProductType.PENDANT_ONLY,
    ],
)
def test_policy_forbids_inferring_unseen_clasp_or_back_structure(product_type):
    policy = get_category_policy(product_type)
    assert "禁止推断不可见扣头或背面结构" in policy.basic_qc_items


def test_pendant_only_policy_keeps_the_no_auto_chain_constraint():
    policy = get_category_policy(ProductType.PENDANT_ONLY)
    assert "禁止自动补链" in policy.basic_qc_items


@pytest.mark.parametrize(
    ("product_type", "display_mode"),
    [
        (ProductType.BRACELET, DisplayMode.WORN),
        (ProductType.NECKLACE, DisplayMode.WORN),
        (ProductType.NECKLACE, DisplayMode.HAND_HELD),
        (ProductType.PENDANT_NECKLACE, DisplayMode.WORN),
        (ProductType.PENDANT_NECKLACE, DisplayMode.HAND_HELD),
    ],
)
def test_policy_provides_qc_items_for_each_supported_mode(
    product_type,
    display_mode,
):
    policy = get_category_policy(product_type)

    items = policy.qc_items_for_mode(display_mode)

    assert items
    assert all(isinstance(item, str) and item for item in items)
    assert set(policy.basic_qc_items).issubset(items)


def test_necklace_worn_policy_explicitly_checks_auto_and_invented_chain():
    policy = get_category_policy(ProductType.NECKLACE)

    items = policy.qc_items_for_mode(DisplayMode.WORN)

    assert "没有自动补链、凭空补链或补充不存在的连接结构" in items


def test_pendant_only_policy_has_no_supported_qc_mode():
    policy = get_category_policy(ProductType.PENDANT_ONLY)

    with pytest.raises(ValueError, match="不支持.*QC"):
        policy.qc_items_for_mode(DisplayMode.WORN)


def test_bracelet_policy_enforces_its_single_layer_limit():
    policy = get_category_policy(ProductType.BRACELET)
    with pytest.raises(ValueError, match="手串/手链.*1 层"):
        policy.validate_generation(layer_count=2, is_independent_multi_item=False)


def test_necklace_policy_exposes_testable_reference_adaptation_result():
    policy = get_category_policy(ProductType.NECKLACE)

    adaptation = policy.evaluate_reference(necklace_product(), necklace_reference())

    assert adaptation.eligible
    assert adaptation.score_adjustment > 0
    assert any("品类" in reason and "展示模式" in reason for reason in adaptation.reasons)
    assert adaptation.risks == ()


def test_necklace_policy_adaptation_reports_hard_filter_risks():
    policy = get_category_policy(ProductType.NECKLACE)

    adaptation = policy.evaluate_reference(
        necklace_product(),
        necklace_reference(
            applicable_product_types="",
            hair_occlusion_risk="高",
            crop_risk="高",
        ),
    )

    assert not adaptation.eligible
    assert any("适用品类" in risk for risk in adaptation.risks)
    assert any("头发" in risk for risk in adaptation.risks)
    assert any("裁切" in risk for risk in adaptation.risks)
