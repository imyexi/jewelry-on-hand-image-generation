from pathlib import Path

import pytest

import jewelry_on_hand.product_analysis as product_analysis_module
from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.product_analysis import (
    UnsupportedProductError,
    build_analysis_prompt,
    build_product_fidelity_constraints,
    load_product_analysis,
    validate_analysis_ready_for_reference_selection,
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


_CANONICAL_ANALYSIS_KEYS = (
    "product_type",
    "detected_product_type",
    "confirmed_product_type",
    "classification_confidence",
    "classification_evidence",
    "classification_source",
    "display_mode",
    "source_image_type",
    "wear_position",
    "visible_appearance",
    "color_family",
    "style_mood",
    "composition",
    "product_dimensions",
    "needs_full_front_display",
    "special_requirements",
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
)


def _ready_analysis_data(product_type):
    display_names = {
        "bracelet": "手串/手链",
        "necklace": "普通项链",
        "pendant_necklace": "带链吊坠",
        "ring": "戒指",
    }
    data = _analysis_data(display_names[product_type]) | {
        **_modern_classification(product_type),
        "display_mode": "worn",
        "source_image_type": "worn_source",
        "wear_position": "产品对应的真人佩戴位置",
        "visible_appearance": "产品主体、排列与连接结构清晰可见",
        "product_dimensions": {
            "length_mm": 180,
            "width_mm": 8.5,
            "height_mm": None,
            "bead_diameter_mm": 10,
            "dimension_source": "用户提供尺寸信息",
        },
        "layer_count": 1,
        "length_category": None,
        "chain_or_strand_type": None,
        "has_pendant": False,
        "pendant_count": 0,
        "pendant_layer": None,
        "pendant_position": None,
        "pendant_orientation": None,
        "connection_structure": None,
        "symmetry": "主体结构清晰",
        "occluded_parts": [],
        "uncertain_details": [],
        "is_independent_multi_item": False,
        "ring_count": 0,
        "hand_side": "unknown",
        "finger_position": "unknown",
        "ring_wear_style": "unknown",
    }
    if product_type in {"necklace", "pendant_necklace"}:
        data |= {
            "wear_position": "颈部至锁骨",
            "length_category": "collarbone",
            "chain_or_strand_type": "beaded",
        }
    if product_type == "pendant_necklace":
        data |= {
            "visible_appearance": "单层珠链正面中央连接一枚吊坠",
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 1,
            "pendant_position": "front_center",
            "pendant_orientation": "front_facing",
            "connection_structure": "metal_bail",
        }
    if product_type == "ring":
        data |= {
            "wear_position": "左手无名指根部",
            "visible_appearance": "单枚戒指的戒面、戒圈与主石清晰可见",
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
        }
    return data


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
            "chain_or_strand_type": "beaded",
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
            "chain_or_strand_type": "beaded",
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


@pytest.mark.parametrize(
    "product_type",
    ["bracelet", "necklace", "pendant_necklace", "ring"],
)
def test_product_analysis_canonical_projection_roundtrips_all_supported_categories(
    product_type,
):
    analysis = ProductAnalysis.from_dict(_ready_analysis_data(product_type))

    serialized = product_analysis_module.product_analysis_to_dict(analysis)
    reparsed = ProductAnalysis.from_dict(serialized)

    assert tuple(serialized) == _CANONICAL_ANALYSIS_KEYS
    assert reparsed == analysis
    assert product_analysis_module.product_analysis_to_dict(reparsed) == serialized
    assert "pendant_semantics" not in serialized


@pytest.mark.parametrize("number", [10, 10.5])
def test_product_analysis_projection_normalizes_integer_and_float_dimensions(number):
    payload = _ready_analysis_data("bracelet")
    payload["product_dimensions"]["bead_diameter_mm"] = number

    analysis = ProductAnalysis.from_dict(payload)
    serialized = product_analysis_module.product_analysis_to_dict(analysis)

    assert serialized["product_dimensions"]["bead_diameter_mm"] == float(number)
    assert isinstance(serialized["product_dimensions"]["bead_diameter_mm"], float)


def test_product_analysis_rejects_bool_disguised_as_dimension_number():
    payload = _ready_analysis_data("bracelet")
    payload["product_dimensions"]["bead_diameter_mm"] = True

    with pytest.raises(ValueError, match="bead_diameter_mm 必须是正数"):
        ProductAnalysis.from_dict(payload)


@pytest.mark.parametrize(
    "product_type",
    ["bracelet", "necklace", "pendant_necklace", "ring"],
)
def test_reference_selection_gate_accepts_all_supported_complete_categories(
    product_type,
):
    analysis = ProductAnalysis.from_dict(_ready_analysis_data(product_type))

    assert validate_analysis_ready_for_reference_selection(analysis) is None


def test_reference_selection_gate_requires_product_analysis_instance():
    with pytest.raises(ValueError, match="analysis 必须是 ProductAnalysis"):
        validate_analysis_ready_for_reference_selection({})


def test_reference_selection_gate_rejects_unsupported_category():
    analysis = ProductAnalysis.from_dict(
        _analysis_data("无法识别")
        | {
            **_modern_classification("unknown"),
            "classification_evidence": ["无法确认产品品类"],
        }
    )

    with pytest.raises(ValueError, match="当前只支持.*bracelet.*necklace.*ring"):
        validate_analysis_ready_for_reference_selection(analysis)


@pytest.mark.parametrize(
    "source_image_type",
    ["hand_held_source", "flat_lay_source", "unknown_source"],
)
def test_reference_selection_gate_requires_worn_source(source_image_type):
    payload = _ready_analysis_data("bracelet")
    payload["source_image_type"] = source_image_type
    analysis = ProductAnalysis.from_dict(payload)

    with pytest.raises(ValueError, match="source_image_type 必须为 worn_source"):
        validate_analysis_ready_for_reference_selection(analysis)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"classification_source": "auto_pending"}, "分析尚未确认"),
        ({"classification_confidence": "low"}, "分类置信度"),
        ({"classification_evidence": []}, "分类证据"),
        (
            {"detected_product_type": "unknown"},
            "自动确认的检测品类与确认品类必须一致",
        ),
    ],
)
def test_reference_selection_gate_rejects_unconfirmed_modern_analysis(
    overrides,
    error,
):
    payload = _ready_analysis_data("bracelet") | overrides
    analysis = ProductAnalysis.from_dict(payload)

    with pytest.raises(ValueError, match=error):
        validate_analysis_ready_for_reference_selection(analysis)


def test_reference_selection_gate_accepts_manual_category_override():
    payload = _ready_analysis_data("necklace") | {
        "detected_product_type": "unknown",
        "classification_confidence": "low",
        "classification_source": "manual_override",
    }
    analysis = ProductAnalysis.from_dict(payload)

    assert validate_analysis_ready_for_reference_selection(analysis) is None


@pytest.mark.parametrize("product_type", ["bracelet", "necklace"])
def test_reference_selection_gate_rejects_pendant_semantics_on_non_pendant_categories(
    product_type,
):
    payload = _ready_analysis_data(product_type)
    if product_type == "bracelet":
        payload |= {
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 1,
            "pendant_position": "front_center",
            "pendant_orientation": "front_facing",
            "connection_structure": "metal_bail",
        }
    else:
        payload["pendant_position"] = "不应残留的吊坠位置"
    analysis = ProductAnalysis.from_dict(payload)

    with pytest.raises(ValueError, match="非吊坠品类不得声明吊坠语义"):
        validate_analysis_ready_for_reference_selection(analysis)


def test_reference_selection_gate_applies_committed_single_pendant_semantics():
    payload = _ready_analysis_data("pendant_necklace")
    payload["pendant_count"] = 2
    analysis = ProductAnalysis.from_dict(payload)

    with pytest.raises(ValueError, match=r"pendant_semantics\.count"):
        validate_analysis_ready_for_reference_selection(analysis)


@pytest.mark.parametrize(
    ("product_type", "field", "error"),
    [
        ("necklace", "length_category", "length_category"),
        ("necklace", "chain_or_strand_type", "chain_or_strand_type"),
        ("pendant_necklace", "length_category", "length_category"),
        ("pendant_necklace", "chain_or_strand_type", "chain_or_strand_type"),
        ("pendant_necklace", "pendant_position", "pendant_position"),
        ("pendant_necklace", "pendant_orientation", "pendant_orientation"),
        ("pendant_necklace", "connection_structure", "connection_structure"),
    ],
)
def test_reference_selection_gate_rejects_missing_required_structure(
    product_type,
    field,
    error,
):
    payload = _ready_analysis_data(product_type)
    payload[field] = None
    analysis = ProductAnalysis.from_dict(payload)

    with pytest.raises(ValueError, match=error):
        validate_analysis_ready_for_reference_selection(analysis)


@pytest.mark.parametrize("field", ["hand_side", "finger_position"])
def test_ring_analysis_rejects_missing_hand_identity_before_gate(field):
    payload = _ready_analysis_data("ring")
    payload.pop(field)

    with pytest.raises(ValueError, match=f"戒指分析契约不完整.*{field}"):
        ProductAnalysis.from_dict(payload)


def test_reference_selection_gate_does_not_interpret_composition_or_style_mood():
    first = ProductAnalysis.from_dict(_ready_analysis_data("bracelet"))
    second = ProductAnalysis.from_dict(
        _ready_analysis_data("bracelet")
        | {
            "composition": "白底产品静物、参考图人物与镜头语言描述",
            "style_mood": "电影感、杂志感、复古风格描述",
        }
    )

    assert validate_analysis_ready_for_reference_selection(first) is None
    assert validate_analysis_ready_for_reference_selection(second) is None
