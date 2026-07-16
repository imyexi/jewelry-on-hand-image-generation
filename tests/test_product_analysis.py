from pathlib import Path

import pytest

from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.product_analysis import (
    UnsupportedProductError,
    build_analysis_prompt,
    build_product_fidelity_constraints,
    load_product_analysis,
)
from jewelry_on_hand.run_paths import write_json


def _analysis_data(product_type):
    return {
        "product_type": product_type,
        "wear_position": "手腕",
        "visible_appearance": "圆珠手链",
        "color_family": ["红色"],
        "style_mood": "清透",
        "composition": "手部近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
    }


def _modern_classification(product_type):
    return {
        "detected_product_type": product_type,
        "confirmed_product_type": product_type,
        "classification_confidence": "high",
        "classification_evidence": ["肉眼可见品类结构"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
    }


def test_prompt_forbids_material_guessing(tmp_path):
    prompt = build_analysis_prompt(tmp_path / "product.jpg", {"bead_diameter_mm": 10})
    assert "只描述肉眼可见外观" in prompt
    assert "不要猜测材质名" in prompt


def test_prompt_includes_contract_fields_path_and_dimension_reference(tmp_path):
    image_path = tmp_path / "product.jpg"
    prompt = build_analysis_prompt(image_path, {"bead_diameter_mm": 10})

    assert str(image_path) in prompt
    assert "bead_diameter_mm" in prompt
    assert "10" in prompt
    for field_name in (
        "product_type",
        "wear_position",
        "visible_appearance",
        "color_family",
        "style_mood",
        "composition",
        "product_dimensions",
        "length_mm",
        "width_mm",
        "height_mm",
        "bead_diameter_mm",
        "dimension_source",
        "needs_full_front_display",
        "special_requirements",
        "detected_product_type",
        "confirmed_product_type",
        "classification_confidence",
        "classification_evidence",
        "classification_source",
        "display_mode",
        "source_image_type",
        "layer_count",
        "length_category",
        "chain_or_strand_type",
        "has_pendant",
        "pendant_count",
        "pendant_layer",
        "pendant_position",
        "pendant_orientation",
        "connection_structure",
        "symmetry",
        "occluded_parts",
        "uncertain_details",
        "is_independent_multi_item",
        "ring_count",
        "hand_side",
        "finger_position",
        "ring_wear_style",
    ):
        assert field_name in prompt
    assert "只输出 JSON" in prompt
    assert "尺寸信息只作为比例参考" in prompt
    assert "手串/手链、普通项链、带链吊坠和戒指" in prompt
    assert "第一阶段只接受真人佩戴原图" in prompt
    assert "普通项链和带链吊坠的默认 display_mode 也是 worn" in prompt
    assert "只有用户在后续人工确认中主动切换" in prompt
    assert "upper_chest" in prompt
    assert "无链独立吊坠没有链层" in prompt
    assert "pendant_layer=null" in prompt
    assert "戒指只允许 ring_count=1" in prompt
    assert "finger_base" in prompt
    assert "第一版只支持手串/手链" not in prompt


def test_schema_uses_spec_default_mode_length_values_and_classification_source():
    schema_path = Path(__file__).parents[1] / "reference" / "product-analysis-schema.md"
    schema = schema_path.read_text(encoding="utf-8")

    assert "默认 `worn`" in schema
    assert "只有用户在后续人工确认中主动切换" in schema
    assert "upper_chest" in schema
    assert "manual_override" in schema
    assert "manual_confirmed" not in schema
    assert "无链独立吊坠没有链层，`pendant_layer` 必须为 `null`" in schema


def test_rejects_unsupported_product_analysis(tmp_path):
    path = tmp_path / "analysis.json"
    write_json(
        path,
        _analysis_data("戒指")
        | {
            **_modern_classification("unknown"),
            "wear_position": "手指",
            "visible_appearance": "银色戒指",
        },
    )
    with pytest.raises(UnsupportedProductError, match="手串/手链"):
        load_product_analysis(path)


def test_load_product_analysis_uses_product_analysis_supported_gate(tmp_path, monkeypatch):
    path = tmp_path / "analysis.json"
    write_json(path, _analysis_data("手链"))
    monkeypatch.setattr(ProductAnalysis, "is_supported_product", lambda self: False)

    with pytest.raises(UnsupportedProductError, match="手串/手链"):
        load_product_analysis(path)


@pytest.mark.parametrize("product_type", ["手链", "手串"])
def test_accepts_supported_bracelet_analysis(tmp_path, product_type):
    path = tmp_path / "analysis.json"
    write_json(path, _analysis_data(product_type))

    analysis = load_product_analysis(path)

    assert isinstance(analysis, ProductAnalysis)
    assert analysis.product_type == product_type


def test_build_default_fidelity_constraints_detects_keyword_from_visible_appearance():
    analysis = ProductAnalysis.from_dict(
        _analysis_data("手链/手串")
        | {
            "visible_appearance": "主珠右侧有一颗透明白色不规则随形，旁边连接海蓝宝跑环。",
            "special_requirements": ["保留白水晶随形", "不要丢失跑环"],
        }
    )

    constraints = build_product_fidelity_constraints(
        analysis,
        product_id="JH016",
        product_image="input/product-on-hand.jpg",
    )

    assert constraints.review_status == "pending"
    assert constraints.needs_user_review is True
    assert constraints.detail_crop_recommended is True
    assert constraints.detected_keywords == ("随形", "跑环")
    assert [item.normalized_keyword for item in constraints.must_keep] == ["随形", "跑环"]
    assert "珠子排列顺序" in constraints.must_not_change
    assert constraints.source["product_id"] == "JH016"


def test_running_ring_constraint_is_a_closed_independent_small_bead_loop():
    analysis = ProductAnalysis.from_dict(
        _analysis_data("手链/手串")
        | {
            "visible_appearance": "黄色主珠旁套接一个红色小珠跑环。",
            "special_requirements": ["保持跑环套接黄色主珠的关系"],
        }
    )

    constraints = build_product_fidelity_constraints(analysis)
    running_ring = next(
        item for item in constraints.must_keep if item.normalized_keyword == "跑环"
    )

    assert "多颗小珠" in running_ring.visual_shape
    assert "独立闭合小环" in running_ring.visual_shape
    assert "环绕、套接或连接对象" in running_ring.relationship
    assert "并入手串主串" in running_ring.forbid
    assert "改成绳结或普通珠结" in running_ring.forbid
    assert "改成单个金属环、金属片或连接扣" in running_ring.forbid
    assert "改成流苏或链坠" in running_ring.forbid
    assert "多颗小珠" in running_ring.qc_question
    assert "连接对象" in running_ring.qc_question


@pytest.mark.parametrize("text", ["红色小珠结", "普通珠结", "金色连接环"])
def test_knot_or_metal_ring_text_does_not_trigger_running_ring(text):
    analysis = ProductAnalysis.from_dict(
        _analysis_data("手链/手串") | {"visible_appearance": text}
    )

    constraints = build_product_fidelity_constraints(analysis)

    assert "跑环" not in constraints.detected_keywords


def test_build_default_fidelity_constraints_marks_not_applicable_without_keyword():
    analysis = ProductAnalysis.from_dict(_analysis_data("手链/手串"))

    constraints = build_product_fidelity_constraints(analysis)

    assert constraints.must_keep == ()
    assert constraints.review_status == "not_applicable"
    assert constraints.needs_user_review is False


def test_built_constraints_bind_to_normalized_product_analysis_sha256():
    analysis = ProductAnalysis.from_dict(_analysis_data("手链/手串"))

    constraints = build_product_fidelity_constraints(analysis)

    assert constraints.source["product_analysis"] == "analysis/product_analysis.json"
    digest = constraints.source["product_analysis_sha256"]
    assert isinstance(digest, str)
    assert len(digest) == 64


def test_build_default_fidelity_constraints_for_ring_covers_all_visible_facts():
    visible_appearance = (
        "单枚银色金属光泽开口戒，椭圆戒面中央有一颗透明圆形主石，"
        "戒圈两个开口端点各有一颗小石，两侧装饰对称排列"
    )
    special_requirements = (
        "保持主石竖向朝向",
        "保留开口端点与两侧小石的排列顺序",
    )
    analysis = ProductAnalysis.from_dict(
        _analysis_data("戒指")
        | {
            **_modern_classification("ring"),
            "wear_position": "左手无名指根部",
            "visible_appearance": visible_appearance,
            "color_family": ["银色", "透明"],
            "special_requirements": list(special_requirements),
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
            "occluded_parts": ["戒圈背面"],
            "uncertain_details": ["镶嵌背面结构"],
        }
    )

    constraints = build_product_fidelity_constraints(analysis)

    assert constraints.review_status == "pending"
    assert constraints.needs_user_review is True
    assert constraints.detail_crop_recommended is True
    assert constraints.must_keep
    assert constraints.must_keep[0].source_text == visible_appearance
    assert all(
        color in " ".join(item.source_text for item in constraints.must_keep)
        for color in analysis.color_family
    )
    assert all(
        any(item.source_text == requirement for item in constraints.must_keep)
        for requirement in special_requirements
    )
    for visible_fact in ("戒面", "主石", "戒圈", "开口端点", "装饰排列"):
        assert visible_fact in constraints.must_keep[0].qc_question
    assert "关闭现有开口或新增开口" in constraints.must_keep[0].forbid
    assert (
        "把不可见戒圈背面、镶嵌背面或连接结构补写为确定结构"
        in constraints.must_keep[0].forbid
    )
    serialized = str(constraints.to_dict())
    assert "戒圈背面" in serialized
    assert "镶嵌背面" in serialized
    assert "不可推断" in serialized
    assert "珠子排列顺序" not in serialized
    assert "主珠" not in serialized


def test_accepts_necklace_analysis_with_worn_source(tmp_path):
    path = tmp_path / "analysis.json"
    write_json(
        path,
        _analysis_data("普通项链")
        | {
            **_modern_classification("necklace"),
            "wear_position": "颈部和锁骨",
            "visible_appearance": "单层珠链",
            "source_image_type": "worn_source",
            "display_mode": "worn",
            "layer_count": 1,
            "length_category": "collarbone",
        },
    )

    analysis = load_product_analysis(path)

    assert analysis.normalized_product_type.value == "necklace"


def test_rejects_necklace_flat_lay_source(tmp_path):
    path = tmp_path / "analysis.json"
    write_json(
        path,
        _analysis_data("普通项链")
        | {
            **_modern_classification("necklace"),
            "wear_position": "白底平铺",
            "source_image_type": "flat_lay_source",
            "display_mode": "worn",
            "layer_count": 1,
            "length_category": "collarbone",
        },
    )

    with pytest.raises(UnsupportedProductError, match="真人佩戴原图"):
        load_product_analysis(path)


def test_rejects_pendant_only_before_generation(tmp_path):
    path = tmp_path / "analysis.json"
    write_json(
        path,
        _analysis_data("无链独立吊坠")
        | {
            **_modern_classification("pendant_only"),
            "wear_position": "颈部",
            "source_image_type": "worn_source",
            "display_mode": "hand_held",
            "layer_count": 1,
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": None,
        },
    )

    with pytest.raises(UnsupportedProductError, match="无链独立吊坠"):
        load_product_analysis(path)
