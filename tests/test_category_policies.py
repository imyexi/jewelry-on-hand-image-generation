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


def ring_product():
    return ProductAnalysis.from_dict(
        {
            "product_type": "戒指",
            "detected_product_type": "ring",
            "confirmed_product_type": "ring",
            "classification_confidence": "high",
            "classification_evidence": ["单枚戒指佩戴在左手无名指根部"],
            "classification_source": "model",
            "wear_position": "左手无名指根部",
            "visible_appearance": "单枚银色素圈戒",
            "color_family": ["银色"],
            "style_mood": "简洁",
            "composition": "手部近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "source_image_type": "worn_source",
            "display_mode": "worn",
            "layer_count": 1,
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
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


def ring_reference(**overrides):
    data = {
        "index": 21,
        "file_name": "ring.jpg",
        "relative_path": "ring.jpg",
        "absolute_path": Path("C:/tmp/ring.jpg"),
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "戒指上手/手部近景参考",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "自然光手部特写",
        "scene_keywords": "手背 手指近景",
        "jewelry_type": "戒指",
        "recommended_usage": "戒指真人佩戴展示",
        "notes": "手指完整，无裁切",
        "confidence": "高",
        "file_exists": True,
        "applicable_product_types": "ring",
        "applicable_display_modes": "worn",
        "visible_body_regions": "左手全部手指",
        "product_visibility": "高",
        "hand_visibility": "高",
        "existing_jewelry": "戒指",
        "crop_risk": "低",
        "hand_side": "left",
        "visible_fingers": "thumb,index,middle,ring,little",
        "hand_orientation": "back",
        "ring_face_visibility": "高",
        "finger_separation": "高",
        "finger_occlusion_risk": "低",
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


def test_ring_policy_is_registered_and_worn_only():
    policy = get_category_policy(ProductType.RING)

    assert policy.product_type is ProductType.RING
    assert policy.max_layer_count == 1
    assert policy.supported_modes == frozenset({DisplayMode.WORN})


def test_ring_policy_rejects_multi_item_flag():
    with pytest.raises(ValueError, match="单枚戒指"):
        get_category_policy(ProductType.RING).validate_generation(
            layer_count=1,
            is_independent_multi_item=True,
        )


def test_ring_policy_provides_prompt_and_qc_contract():
    policy = get_category_policy(ProductType.RING)

    fragments = policy.build_prompt_fragments(ring_product())
    items = policy.qc_items_for_mode(DisplayMode.WORN)

    assert "内部图1中的戒指必须移除" in fragments.image_one_role
    assert "画面中只有一枚目标戒指" in items
    assert "戒指位于确认后的左右手和目标手指根部" in items
    assert "戒圈自然环绕手指" in " ".join(items)


def test_ring_policy_exposes_eligible_reference_adaptation():
    adaptation = get_category_policy(ProductType.RING).evaluate_reference(
        ring_product(),
        ring_reference(),
    )

    assert adaptation.eligible
    assert adaptation.score_adjustment > 0
    assert "参考图中的戒指" in adaptation.ignored_reference_jewelry


@pytest.mark.parametrize(
    ("overrides", "risk_text"),
    [
        ({"applicable_product_types": ""}, "适用品类"),
        ({"applicable_display_modes": ""}, "展示模式"),
        ({"visible_fingers": "thumb,index,middle"}, "目标手指"),
        ({"ring_face_visibility": "低"}, "戒面"),
        ({"finger_separation": "低"}, "分离度"),
        ({"finger_occlusion_risk": "高"}, "遮挡"),
        ({"crop_risk": "高"}, "裁切"),
    ],
)
def test_ring_policy_reports_hard_filter_risks(overrides, risk_text):
    adaptation = get_category_policy(ProductType.RING).evaluate_reference(
        ring_product(),
        ring_reference(**overrides),
    )

    assert not adaptation.eligible
    assert any(risk_text in risk for risk in adaptation.risks)


@pytest.mark.parametrize(
    ("overrides", "risk_text"),
    [
        ({"hand_side": "right"}, "左右手"),
        ({"existing_jewelry": "食指上的戒指"}, "目标手指"),
    ],
)
def test_戒指参考手侧与原戒指指位必须匹配目标(overrides, risk_text):
    adaptation = get_category_policy(ProductType.RING).evaluate_reference(
        ring_product(),
        ring_reference(**overrides),
    )

    assert not adaptation.eligible
    assert any(risk_text in risk for risk in adaptation.risks)


def test_项链参考含界面或原首饰不可识别时被硬门拒绝():
    policy = get_category_policy(ProductType.NECKLACE)
    references = [
        necklace_reference(notes="颈部完整，但画面含平台界面和状态栏"),
        necklace_reference(existing_jewelry="原首饰无法完整识别"),
    ]

    adaptations = [
        policy.evaluate_reference(necklace_product(), reference)
        for reference in references
    ]

    assert all(not adaptation.eligible for adaptation in adaptations)
    assert any("界面" in risk for risk in adaptations[0].risks)
    assert any("原首饰" in risk for risk in adaptations[1].risks)


def test_戒指参考含界面或原首饰不可识别时被硬门拒绝():
    policy = get_category_policy(ProductType.RING)
    references = [
        ring_reference(notes="手指完整，但画面含平台界面和状态栏"),
        ring_reference(existing_jewelry="原首饰无法完整识别"),
    ]

    adaptations = [
        policy.evaluate_reference(ring_product(), reference)
        for reference in references
    ]

    assert all(not adaptation.eligible for adaptation in adaptations)
    assert any("界面" in risk for risk in adaptations[0].risks)
    assert any("原首饰" in risk for risk in adaptations[1].risks)


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
        ProductType.RING,
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
        ProductType.RING,
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
        (ProductType.RING, DisplayMode.WORN),
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
