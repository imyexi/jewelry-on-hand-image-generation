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
    ):
        assert field_name in prompt
    assert "只输出 JSON" in prompt
    assert "尺寸信息只作为比例参考" in prompt
    assert "第一版只支持手串/手链" in prompt


def test_rejects_non_bracelet_analysis(tmp_path):
    path = tmp_path / "analysis.json"
    write_json(path, _analysis_data("戒指") | {"wear_position": "手指", "visible_appearance": "银色戒指"})
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


def test_build_default_fidelity_constraints_marks_not_applicable_without_keyword():
    analysis = ProductAnalysis.from_dict(_analysis_data("手链/手串"))

    constraints = build_product_fidelity_constraints(analysis)

    assert constraints.must_keep == ()
    assert constraints.review_status == "not_applicable"
    assert constraints.needs_user_review is False
