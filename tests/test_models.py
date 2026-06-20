from pathlib import Path

import pytest

from jewelry_on_hand.models import (
    ProductFidelityConstraints,
    ProductAnalysis,
    ProductDimensions,
    QcResult,
    ReferenceRow,
    ReviewDecision,
    ScoredReference,
)


def _analysis_data(**overrides):
    data = {
        "product_type": "朱砂手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "深红主珠居中，两侧透明茶金色圆珠围绕。",
        "color_family": ["深红", "茶金", "透明"],
        "style_mood": "暗调闪光",
        "composition": "手腕近景",
        "product_dimensions": {"bead_diameter_mm": 10, "dimension_source": "用户录入"},
    }
    data.update(overrides)
    return data


def _constraints_data(**overrides):
    data = {
        "schema_version": 1,
        "source": {
            "product_id": "JH016",
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
        },
        "detected_keywords": ["随形"],
        "must_keep": [
            {
                "name": "白水晶随形",
                "source_text": "白水晶随形",
                "normalized_keyword": "随形",
                "location": "主珠右侧",
                "visual_shape": "透明不规则随形，非圆珠",
                "relationship": "位于两颗圆珠之间",
                "forbid": ["改成圆珠", "改成椭圆珠"],
                "qc_question": "白水晶随形是否仍是不规则透明异形珠",
            }
        ],
        "must_not_change": ["珠子排列顺序"],
        "needs_user_review": True,
        "detail_crop_recommended": True,
        "review_status": "pending",
    }
    data.update(overrides)
    return data


def _reference_row():
    return ReferenceRow(
        index=1,
        file_name="ref.jpg",
        relative_path="references/ref.jpg",
        absolute_path=Path("C:/images/ref.jpg"),
        width=1024,
        height=768,
        size_mb=1.25,
        purpose_category="上手参考",
        bracelet_applicability="适合手串",
        default_strategy="优先使用",
        style_category="暗调",
        scene_keywords="手腕 室内",
        jewelry_type="手串",
        recommended_usage="生成构图参考",
        notes="适合深色珠子",
        confidence="高",
        file_exists=True,
    )


def test_product_analysis_happy_path_supports_bracelet_and_tuple_snapshot():
    analysis = ProductAnalysis.from_dict(_analysis_data())

    assert analysis.product_dimensions.bead_diameter_mm == 10
    assert analysis.product_dimensions.dimension_source == "用户录入"
    assert analysis.is_supported_product() is True
    assert analysis.color_family == ("深红", "茶金", "透明")
    assert isinstance(analysis.color_family, tuple)
    assert analysis.needs_full_front_display is True


def test_product_analysis_requires_non_empty_required_strings():
    for field_name in (
        "product_type",
        "wear_position",
        "visible_appearance",
        "style_mood",
        "composition",
    ):
        with pytest.raises(ValueError, match=field_name):
            ProductAnalysis.from_dict(_analysis_data(**{field_name: "   "}))


def test_product_analysis_requires_color_family_list_of_strings():
    data = _analysis_data()
    data.pop("color_family")
    with pytest.raises(ValueError, match="color_family"):
        ProductAnalysis.from_dict(data)

    with pytest.raises(ValueError, match="color_family"):
        ProductAnalysis.from_dict(_analysis_data(color_family=["深红", 3]))


@pytest.mark.parametrize("value, expected", [("false", False), ("0", False), ("no", False), ("n", False)])
def test_product_analysis_parses_false_string_to_false(value, expected):
    analysis = ProductAnalysis.from_dict(_analysis_data(needs_full_front_display=value))

    assert analysis.needs_full_front_display is expected


def test_product_analysis_copies_input_lists():
    color_family = ["深红", "茶金"]
    special_requirements = ["保留主珠", "保留隔圈"]
    analysis = ProductAnalysis.from_dict(
        _analysis_data(color_family=color_family, special_requirements=special_requirements)
    )

    color_family.append("透明")
    special_requirements.append("保留吊坠")

    assert analysis.color_family == ("深红", "茶金")
    assert analysis.special_requirements == ("保留主珠", "保留隔圈")


def test_product_analysis_direct_construction_copies_lists_to_tuples():
    color_family = ["深红", "茶金"]
    special_requirements = ["保留主珠"]
    analysis = ProductAnalysis(
        product_type="朱砂手链/手串",
        wear_position="手腕",
        visible_appearance="深红主珠居中",
        color_family=color_family,
        style_mood="暗调闪光",
        composition="手腕近景",
        product_dimensions=ProductDimensions(bead_diameter_mm=10),
        needs_full_front_display="true",
        special_requirements=special_requirements,
    )

    color_family.append("透明")
    special_requirements.append("保留隔圈")

    assert analysis.color_family == ("深红", "茶金")
    assert analysis.special_requirements == ("保留主珠",)
    assert isinstance(analysis.color_family, tuple)
    assert isinstance(analysis.special_requirements, tuple)
    assert analysis.needs_full_front_display is True


def test_product_analysis_direct_construction_requires_dimensions_model():
    with pytest.raises(ValueError, match="product_dimensions"):
        ProductAnalysis(
            product_type="朱砂手链/手串",
            wear_position="手腕",
            visible_appearance="深红主珠居中",
            color_family=["深红"],
            style_mood="暗调闪光",
            composition="手腕近景",
            product_dimensions={"bead_diameter_mm": 10},
            needs_full_front_display=True,
        )


def test_product_analysis_requires_special_requirements_list_of_strings_when_provided():
    with pytest.raises(ValueError, match="special_requirements"):
        ProductAnalysis.from_dict(_analysis_data(special_requirements="保留主珠"))

    with pytest.raises(ValueError, match="special_requirements"):
        ProductAnalysis.from_dict(_analysis_data(special_requirements=["保留主珠", None]))


def test_product_dimensions_accept_numeric_strings_and_reject_invalid_values():
    dimensions = ProductDimensions.from_dict({"bead_diameter_mm": "10", "length_mm": 12})

    assert dimensions.bead_diameter_mm == 10.0
    assert dimensions.length_mm == 12.0

    for invalid in (-1, 0, True, "nan", float("nan"), "inf"):
        with pytest.raises(ValueError, match="bead_diameter_mm"):
            ProductDimensions.from_dict({"bead_diameter_mm": invalid})


def test_product_dimensions_direct_construction_parses_numeric_string_and_rejects_nan():
    dimensions = ProductDimensions(bead_diameter_mm="10")

    assert dimensions.bead_diameter_mm == 10.0

    with pytest.raises(ValueError, match="bead_diameter_mm"):
        ProductDimensions(bead_diameter_mm=float("nan"))


def test_product_dimensions_rejects_empty_dimension_source():
    with pytest.raises(ValueError, match="dimension_source"):
        ProductDimensions.from_dict({"dimension_source": "   "})


def test_product_fidelity_constraints_accepts_pending_must_keep_and_exports_detached_dict():
    constraints = ProductFidelityConstraints.from_dict(_constraints_data())

    exported = constraints.to_dict()
    exported["must_keep"][0]["forbid"].append("后续修改")

    assert constraints.schema_version == 1
    assert constraints.detected_keywords == ("随形",)
    assert constraints.must_keep[0].normalized_keyword == "随形"
    assert constraints.must_keep[0].forbid == ("改成圆珠", "改成椭圆珠")
    assert constraints.to_dict()["must_keep"][0]["forbid"] == ["改成圆珠", "改成椭圆珠"]


@pytest.mark.parametrize("status", ["pending", "confirmed", "corrected", "not_applicable"])
def test_product_fidelity_constraints_accepts_known_review_status(status):
    data = _constraints_data(review_status=status)
    if status == "not_applicable":
        data["must_keep"] = []

    constraints = ProductFidelityConstraints.from_dict(data)

    assert constraints.review_status == status


def test_product_fidelity_constraints_rejects_missing_required_must_keep_fields():
    data = _constraints_data()
    data["must_keep"][0].pop("qc_question")

    with pytest.raises(ValueError, match="qc_question"):
        ProductFidelityConstraints.from_dict(data)


def test_product_fidelity_constraints_rejects_not_applicable_with_must_keep_items():
    with pytest.raises(ValueError, match="not_applicable"):
        ProductFidelityConstraints.from_dict(_constraints_data(review_status="not_applicable"))


def test_reference_row_full_construction_and_combined_text():
    row = _reference_row()

    combined_text = row.combined_text()

    assert row.absolute_path == Path("C:/images/ref.jpg")
    for expected_text in (
        row.purpose_category,
        row.bracelet_applicability,
        row.default_strategy,
        row.style_category,
        row.scene_keywords,
        row.jewelry_type,
        row.recommended_usage,
        row.notes,
        row.confidence,
    ):
        assert expected_text in combined_text


def test_reference_row_from_dict_supports_exact_chinese_columns_for_task5():
    row = ReferenceRow.from_dict(
        {
            "序号": "1",
            "文件名": "ref.jpg",
            "相对路径": "references/ref.jpg",
            "绝对路径": "C:/images/ref.jpg",
            "宽度": "1024",
            "高度": "768",
            "大小MB": "1.25",
            "用途分类": "上手参考",
            "手链手串适用性": "是：可用于手链/手串",
            "默认使用策略": "常规可优先使用",
            "风格分类": "暗调",
            "场景关键词": "手腕 室内",
            "饰品类型": "手串",
            "推荐使用方式": "生成构图参考",
            "备注": "适合深色珠子",
            "判断置信度": "高",
            "文件存在": True,
        }
    )

    assert row.bracelet_applicability == "是：可用于手链/手串"
    assert row.default_strategy == "常规可优先使用"


def test_reference_row_direct_construction_converts_basic_fields():
    row = ReferenceRow(
        index="1",
        file_name="ref.jpg",
        relative_path="references/ref.jpg",
        absolute_path="C:/images/ref.jpg",
        width="1024",
        height="768",
        size_mb="1.25",
        purpose_category="上手参考",
        bracelet_applicability="适合手串",
        default_strategy="优先使用",
        style_category="暗调",
        scene_keywords="手腕 室内",
        jewelry_type="手串",
        recommended_usage="生成构图参考",
        notes="适合深色珠子",
        confidence="高",
        file_exists=True,
    )

    assert row.index == 1
    assert row.absolute_path == Path("C:/images/ref.jpg")
    assert row.width == 1024
    assert row.height == 768
    assert row.size_mb == 1.25
    assert row.file_exists is True


def test_scored_reference_to_dict_contains_required_top_level_and_metadata_fields():
    row = _reference_row()
    scored = ScoredReference(
        row=row,
        score=96,
        rank=1,
        reason=["匹配手腕构图"],
        risk=["光线偏暗"],
        ignored_reference_jewelry=["忽略原图戒指"],
    )

    result = scored.to_dict()

    assert result == {
        "selected_reference": str(row.absolute_path),
        "score": 96,
        "rank": 1,
        "reason": ["匹配手腕构图"],
        "risk": ["光线偏暗"],
        "ignored_reference_jewelry": ["忽略原图戒指"],
        "metadata": {
            "index": 1,
            "序号": 1,
            "file_name": "ref.jpg",
            "文件名": "ref.jpg",
            "relative_path": "references/ref.jpg",
            "相对路径": "references/ref.jpg",
            "absolute_path": str(row.absolute_path),
            "绝对路径": str(row.absolute_path),
            "source_reference": str(row.absolute_path),
            "source_absolute_path": str(row.absolute_path),
            "source_relative_path": "references/ref.jpg",
            "source_file_name": "ref.jpg",
            "用途分类": "上手参考",
            "风格分类": "暗调",
            "场景关键词": "手腕 室内",
            "饰品类型": "手串",
            "推荐使用方式": "生成构图参考",
            "备注": "适合深色珠子",
            "判断置信度": "高",
        },
    }


def test_scored_reference_copies_lists_and_to_dict_returns_detached_lists():
    row = _reference_row()
    reason = ["匹配手腕构图"]
    risk = ["光线偏暗"]
    ignored = ["忽略原图戒指"]
    scored = ScoredReference(
        row=row,
        score=96,
        rank=1,
        reason=reason,
        risk=risk,
        ignored_reference_jewelry=ignored,
    )

    reason.append("后续修改")
    risk.append("后续风险")
    ignored.append("后续忽略")
    result = scored.to_dict()
    result["reason"].append("修改导出结果")

    assert scored.reason == ("匹配手腕构图",)
    assert scored.risk == ("光线偏暗",)
    assert scored.ignored_reference_jewelry == ("忽略原图戒指",)
    assert scored.to_dict()["reason"] == ["匹配手腕构图"]


def test_scored_reference_direct_construction_requires_reference_row():
    with pytest.raises((TypeError, ValueError), match="row"):
        ScoredReference(
            row={},
            score=1,
            rank=1,
            reason=[],
            risk=[],
            ignored_reference_jewelry=[],
        )


def test_scored_reference_direct_construction_requires_integer_score():
    with pytest.raises((TypeError, ValueError), match="score"):
        ScoredReference(
            row=_reference_row(),
            score="bad",
            rank=1,
            reason=[],
            risk=[],
            ignored_reference_jewelry=[],
        )


def test_scored_reference_direct_construction_rejects_bool_score():
    with pytest.raises((TypeError, ValueError), match="score"):
        ScoredReference(
            row=_reference_row(),
            score=True,
            rank=1,
            reason=[],
            risk=[],
            ignored_reference_jewelry=[],
        )


def test_scored_reference_direct_construction_requires_positive_integer_rank():
    with pytest.raises((TypeError, ValueError), match="rank"):
        ScoredReference(
            row=_reference_row(),
            score=1,
            rank=0,
            reason=[],
            risk=[],
            ignored_reference_jewelry=[],
        )

    with pytest.raises((TypeError, ValueError), match="rank"):
        ScoredReference(
            row=_reference_row(),
            score=1,
            rank=True,
            reason=[],
            risk=[],
            ignored_reference_jewelry=[],
        )


def test_scored_reference_allows_rank_above_top_three_for_candidates():
    scored = ScoredReference(
        row=_reference_row(),
        score=1,
        rank=4,
        reason=[],
        risk=[],
        ignored_reference_jewelry=[],
    )

    assert scored.rank == 4


def test_review_decision_generate_rank_1_defaults_only_for_missing_or_empty_list():
    assert ReviewDecision.from_dict({"action": "generate_rank_1", "fidelity_confirmed": True}).selected_ranks == [1]
    assert ReviewDecision.from_dict({"action": "generate_rank_1", "selected_ranks": [], "fidelity_confirmed": True}).selected_ranks == [1]
    assert ReviewDecision.from_dict({"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True}).selected_ranks == [1]

    for invalid in (0, False, ""):
        with pytest.raises(ValueError, match="selected_ranks"):
            ReviewDecision.from_dict({"action": "generate_rank_1", "selected_ranks": invalid, "fidelity_confirmed": True})


def test_review_decision_generate_rank_1_rejects_non_rank_1_selection():
    with pytest.raises(ValueError, match="generate_rank_1"):
        ReviewDecision.from_dict({"action": "generate_rank_1", "selected_ranks": [2], "fidelity_confirmed": True})

    with pytest.raises(ValueError, match="generate_rank_1"):
        ReviewDecision(action="generate_rank_1", selected_ranks=[2])


def test_review_decision_generate_rank_1_selected_ranks_is_frozen_list():
    decision = ReviewDecision.from_dict({"action": "generate_rank_1", "fidelity_confirmed": True})

    with pytest.raises(AttributeError):
        decision.selected_ranks.append(2)


def test_review_decision_generate_selected_returns_list_compatible_ranks():
    decision = ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": [2], "fidelity_confirmed": True})

    assert decision.selected_ranks == [2]


def test_review_decision_generation_actions_require_fidelity_confirmed_true():
    for action, ranks in (
        ("generate_rank_1", None),
        ("generate_selected", [1]),
        ("generate_multiple", [1, 2]),
    ):
        payload = {"action": action}
        if ranks is not None:
            payload["selected_ranks"] = ranks
        with pytest.raises(ValueError, match="fidelity_confirmed"):
            ReviewDecision.from_dict(payload)
        with pytest.raises(ValueError, match="fidelity_confirmed"):
            ReviewDecision.from_dict(payload | {"fidelity_confirmed": False})

    decision = ReviewDecision.from_dict(
        {"action": "generate_selected", "selected_ranks": [1], "fidelity_confirmed": True}
    )
    assert decision.fidelity_confirmed is True
    assert decision.fidelity_constraints_path == "analysis/product_fidelity_constraints.json"


def test_review_decision_direct_construction_copies_selected_ranks_to_frozen_list():
    ranks = [1]
    decision = ReviewDecision(
        action="generate_rank_1",
        selected_ranks=ranks,
        manual_reference=None,
    )

    ranks.append(2)

    assert decision.selected_ranks == [1]
    with pytest.raises(AttributeError):
        decision.selected_ranks.append(2)


def test_review_decision_direct_construction_defaults_empty_generate_rank_1_to_rank_1():
    decision = ReviewDecision(action="generate_rank_1", selected_ranks=[])

    assert decision.selected_ranks == [1]


def test_review_decision_direct_construction_requires_selected_ranks_for_selected_action():
    with pytest.raises(ValueError, match="selected_ranks"):
        ReviewDecision(
            action="generate_selected",
            selected_ranks=[],
            manual_reference=None,
        )


def test_review_decision_selected_actions_require_selected_ranks():
    for action in ("generate_selected", "generate_multiple"):
        with pytest.raises(ValueError, match="selected_ranks"):
            ReviewDecision.from_dict({"action": action, "selected_ranks": [], "fidelity_confirmed": True})

    selected = ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": [3], "fidelity_confirmed": True})
    assert selected.selected_ranks == [3]

    multiple = ReviewDecision.from_dict({"action": "generate_multiple", "selected_ranks": [1, 3], "fidelity_confirmed": True})
    assert multiple.selected_ranks == [1, 3]


def test_review_decision_generate_selected_rejects_multiple_ranks():
    with pytest.raises(ValueError, match="generate_selected"):
        ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": [1, 3], "fidelity_confirmed": True})

    with pytest.raises(ValueError, match="generate_selected"):
        ReviewDecision(action="generate_selected", selected_ranks=[1, 3])


def test_review_decision_generate_multiple_rejects_single_rank():
    with pytest.raises(ValueError, match="generate_multiple"):
        ReviewDecision.from_dict({"action": "generate_multiple", "selected_ranks": [2], "fidelity_confirmed": True})

    with pytest.raises(ValueError, match="generate_multiple"):
        ReviewDecision(action="generate_multiple", selected_ranks=[2])


def test_review_decision_rejects_duplicate_selected_ranks():
    with pytest.raises(ValueError, match="重复"):
        ReviewDecision.from_dict({"action": "generate_multiple", "selected_ranks": [1, 1], "fidelity_confirmed": True})

    with pytest.raises(ValueError, match="重复"):
        ReviewDecision(action="generate_multiple", selected_ranks=[1, 1])


@pytest.mark.parametrize("rank", [0, 4, True])
def test_review_decision_rejects_invalid_ranks(rank):
    with pytest.raises(ValueError, match="selected_ranks"):
        ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": [rank], "fidelity_confirmed": True})


def test_review_decision_manual_reference_requires_non_empty_string_and_passes_valid_value():
    for manual_reference in (None, "   "):
        with pytest.raises(ValueError, match="manual_reference"):
            ReviewDecision.from_dict(
                {"action": "manual_reference", "manual_reference": manual_reference}
            )

    decision = ReviewDecision.from_dict(
        {"action": "manual_reference", "manual_reference": "C:/images/manual.jpg"}
    )

    assert decision.manual_reference == "C:/images/manual.jpg"


def test_qc_result_can_be_constructed_with_contract_fields():
    result = QcResult(status="rerun", passed=["手部自然"], failed=["光线不足"], notes="需要重跑")

    assert result.status == "rerun"
    assert result.passed == ("手部自然",)
    assert result.failed == ("光线不足",)
    assert result.notes == "需要重跑"


def test_qc_result_validates_runtime_contract_and_copies_lists():
    with pytest.raises(ValueError, match="status"):
        QcResult(status="bad", passed=[], failed=[], notes="x")

    with pytest.raises(ValueError, match="passed"):
        QcResult(status="pass", passed=[1], failed=[], notes="x")

    passed = ["手部自然"]
    failed = ["光线不足"]
    result = QcResult(status="pass", passed=passed, failed=failed, notes="通过")
    passed.append("后续修改")
    failed.append("后续失败")

    assert result.passed == ("手部自然",)
    assert result.failed == ("光线不足",)


def test_qc_result_rejects_pass_when_fidelity_check_failed():
    with pytest.raises(ValueError, match="must_keep"):
        QcResult(
            status="pass",
            passed=["构图正确"],
            failed=[],
            notes="",
            fidelity_checks=[
                {
                    "name": "白水晶随形",
                    "question": "白水晶随形是否仍是不规则透明异形珠",
                    "result": "fail",
                    "notes": "变成圆珠",
                }
            ],
        )


def test_qc_result_accepts_fidelity_checks_for_rerun_and_copies_items():
    checks = [
        {
            "name": "白水晶随形",
            "question": "白水晶随形是否仍是不规则透明异形珠",
            "result": "fail",
            "notes": "变成圆珠",
        }
    ]

    result = QcResult(status="rerun", passed=["构图正确"], failed=["关键识别点失败"], notes="重跑", fidelity_checks=checks)
    checks[0]["result"] = "pass"

    assert result.fidelity_checks[0].result == "fail"
