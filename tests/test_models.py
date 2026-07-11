import math
from pathlib import Path

import pytest

from jewelry_on_hand.display_modes import DisplayMode, SourceImageType
from jewelry_on_hand.models import (
    ProductConfirmationSnapshot,
    ProductFidelityConstraints,
    ProductAnalysis,
    ProductDimensions,
    QcResult,
    ReferenceRow,
    ReviewDecision,
    ScoredReference,
)
from jewelry_on_hand.product_types import ProductType


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


def _modern_classification(product_type="bracelet"):
    return {
        "detected_product_type": product_type,
        "confirmed_product_type": product_type,
        "classification_confidence": "high",
        "classification_evidence": ["肉眼可见品类结构"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
    }


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


def _confirmation_snapshot(**overrides):
    data = {
        "confirmed_product_type": "pendant_necklace",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "layer_count": 2,
        "length_category": "collarbone",
        "has_pendant": True,
        "pendant_count": 1,
        "pendant_layer": 2,
        "pendant_position": "front_center",
        "pendant_orientation": "front_facing",
        "connection_structure": "metal_bail",
        "is_independent_multi_item": False,
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


def test_product_confirmation_snapshot_roundtrip_uses_typed_enums():
    snapshot = ProductConfirmationSnapshot.from_dict(_confirmation_snapshot())

    assert snapshot.confirmed_product_type is ProductType.PENDANT_NECKLACE
    assert snapshot.source_image_type is SourceImageType.WORN_SOURCE
    assert snapshot.display_mode is DisplayMode.WORN
    assert snapshot.to_dict() == _confirmation_snapshot()


def test_product_confirmation_snapshot_rejects_each_missing_field():
    for missing in _confirmation_snapshot():
        payload = _confirmation_snapshot()
        del payload[missing]

        with pytest.raises(ValueError, match=missing):
            ProductConfirmationSnapshot.from_dict(payload)


def test_product_confirmation_snapshot_requires_json_integer_layer_count():
    with pytest.raises(ValueError, match="layer_count.*JSON 整数"):
        ProductConfirmationSnapshot.from_dict(_confirmation_snapshot(layer_count="2"))


def test_review_decision_roundtrip_preserves_confirmation_snapshot():
    decision = ReviewDecision.from_dict(
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "confirmation_snapshot": _confirmation_snapshot(),
        }
    )

    assert isinstance(decision.confirmation_snapshot, ProductConfirmationSnapshot)
    assert decision.confirmation_snapshot.to_dict() == _confirmation_snapshot()


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


@pytest.mark.parametrize("invalid", ["true", "yes", "1", 1])
def test_review_decision_from_dict_requires_json_boolean_fidelity_confirmation(invalid):
    with pytest.raises(ValueError, match="fidelity_confirmed.*JSON 布尔值"):
        ReviewDecision.from_dict(
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": invalid,
            }
        )


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


@pytest.mark.parametrize(
    "critical_failure",
    [
        "must_keep_failed",
        "layer_count_mismatch",
        "length_category_mismatch",
        "pendant_layer_changed",
        "source_person_region_migrated",
    ],
)
def test_qc_result_critical_failures_forbid_pass(critical_failure):
    with pytest.raises(ValueError, match="不得标记为 pass"):
        QcResult(
            status="pass",
            passed=["构图正确"],
            failed=[],
            notes="",
            critical_failures=[critical_failure],
        )


@pytest.mark.parametrize(
    "critical_failure",
    [
        "category_mismatch",
        "core_structure_missing",
        "multi_layer_restructured",
        "auto_chain_added",
        "severe_intersection",
    ],
)
def test_qc_result_severe_failures_require_reject(critical_failure):
    with pytest.raises(ValueError, match="必须标记为 reject"):
        QcResult(
            status="rerun",
            passed=["构图正确"],
            failed=["存在严重错误"],
            notes="",
            critical_failures=[critical_failure],
        )


@pytest.mark.parametrize("invalid", [True, 1, "auto_chain_added", [""]])
def test_qc_result_rejects_invalid_critical_failure_types(invalid):
    with pytest.raises(ValueError, match="critical_failures"):
        QcResult(
            status="reject",
            passed=["构图正确"],
            failed=["自动补链"],
            notes="",
            critical_failures=invalid,
        )


@pytest.mark.parametrize(
    "failure_text",
    [
        "must_keep 关键识别点失败",
        "项链层数错误",
        "长度等级错误",
        "吊坠换层",
        "检测到自动补链",
        "产品图人物局部迁移",
    ],
)
def test_qc_result_human_failure_text_forbids_pass(failure_text):
    with pytest.raises(ValueError, match="不得标记为 pass"):
        QcResult(
            status="pass",
            passed=["构图正确"],
            failed=[failure_text],
            notes="",
        )


@pytest.mark.parametrize(
    "failure_text",
    [
        "品类错误",
        "核心结构缺失",
        "多层关系重组",
        "检测到自动补链",
        "链条严重穿模",
    ],
)
def test_qc_result_severe_human_failure_text_requires_reject(failure_text):
    with pytest.raises(ValueError, match="必须标记为 reject"):
        QcResult(
            status="rerun",
            passed=["构图正确"],
            failed=[failure_text],
            notes="",
        )


def test_legacy_bracelet_json_gets_normalized_defaults():
    analysis = ProductAnalysis.from_dict(_analysis_data())

    assert analysis.product_type == "朱砂手链/手串"
    assert analysis.normalized_product_type is ProductType.BRACELET
    assert analysis.detected_product_type is ProductType.BRACELET
    assert analysis.confirmed_product_type is ProductType.BRACELET
    assert analysis.classification_confidence == "high"
    assert analysis.classification_evidence == ()
    assert analysis.classification_source == "legacy_inferred"
    assert analysis.display_mode is DisplayMode.WORN
    assert analysis.source_image_type is SourceImageType.WORN_SOURCE
    assert analysis.layer_count == 1
    assert analysis.length_category is None


def test_necklace_analysis_preserves_structure():
    analysis = ProductAnalysis.from_dict(
        _analysis_data(
            product_type="带链吊坠",
            wear_position="颈部和锁骨",
            visible_appearance="双层珠链，第二层中央有吊坠",
            detected_product_type="pendant_necklace",
            confirmed_product_type="pendant_necklace",
            classification_confidence="high",
            classification_evidence=["中央存在主吊坠"],
            classification_source="auto_confirmed",
            display_mode="hand_held",
            source_image_type="worn_source",
            layer_count=2,
            length_category="collarbone",
            chain_or_strand_type="beaded",
            has_pendant=True,
            pendant_count=1,
            pendant_layer=2,
            pendant_position="front_center",
            pendant_orientation="front_facing",
            connection_structure="metal_bail",
            symmetry="approximately_symmetric",
            occluded_parts=["后颈扣头"],
            uncertain_details=["扣头具体结构"],
        )
    )

    assert analysis.normalized_product_type is ProductType.PENDANT_NECKLACE
    assert analysis.detected_product_type is ProductType.PENDANT_NECKLACE
    assert analysis.confirmed_product_type is ProductType.PENDANT_NECKLACE
    assert analysis.classification_confidence == "high"
    assert analysis.classification_evidence == ("中央存在主吊坠",)
    assert analysis.classification_source == "auto_confirmed"
    assert analysis.display_mode is DisplayMode.HAND_HELD
    assert analysis.source_image_type is SourceImageType.WORN_SOURCE
    assert analysis.layer_count == 2
    assert analysis.length_category == "collarbone"
    assert analysis.chain_or_strand_type == "beaded"
    assert analysis.has_pendant is True
    assert analysis.pendant_count == 1
    assert analysis.pendant_layer == 2
    assert analysis.pendant_position == "front_center"
    assert analysis.pendant_orientation == "front_facing"
    assert analysis.connection_structure == "metal_bail"
    assert analysis.symmetry == "approximately_symmetric"
    assert analysis.occluded_parts == ("后颈扣头",)
    assert analysis.uncertain_details == ("扣头具体结构",)


@pytest.mark.parametrize("layer_count", [0, 4])
def test_necklace_rejects_layer_count_out_of_range(layer_count):
    with pytest.raises(ValueError, match="layer_count|1 至 3 层"):
        ProductAnalysis.from_dict(
            _analysis_data(
                product_type="普通项链",
                **_modern_classification("necklace"),
                layer_count=layer_count,
            )
        )


def test_pendant_layer_must_not_exceed_layer_count():
    with pytest.raises(ValueError, match="pendant_layer"):
        ProductAnalysis.from_dict(
            _analysis_data(
                product_type="带链吊坠",
                **_modern_classification("pendant_necklace"),
                layer_count=1,
                has_pendant=True,
                pendant_count=1,
                pendant_layer=2,
            )
        )


def test_necklace_rejects_independent_multi_item_stacking():
    with pytest.raises(ValueError, match="多件独立项链"):
        ProductAnalysis.from_dict(
            _analysis_data(
                product_type="普通项链",
                **_modern_classification("necklace"),
                layer_count=2,
                is_independent_multi_item=True,
            )
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("detected_product_type", False),
        ("confirmed_product_type", ["necklace"]),
    ],
)
def test_product_analysis_rejects_invalid_product_type_field_types(
    field_name, invalid_value
):
    classification = _modern_classification()
    classification[field_name] = invalid_value
    with pytest.raises(ValueError, match=field_name):
        ProductAnalysis.from_dict(_analysis_data(**classification))


def test_product_analysis_rejects_fractional_pendant_count():
    with pytest.raises(ValueError, match="pendant_count.*整数"):
        ProductAnalysis.from_dict(_analysis_data(pendant_count=1.5))


@pytest.mark.parametrize(
    "field_name",
    ["layer_count", "pendant_count", "pendant_layer"],
)
def test_product_analysis_rejects_infinite_integer_fields_with_chinese_error(
    field_name,
):
    with pytest.raises(ValueError, match=f"{field_name}.*整数"):
        ProductAnalysis.from_dict(_analysis_data(**{field_name: math.inf}))


@pytest.mark.parametrize(
    "missing_field",
    [
        "detected_product_type",
        "confirmed_product_type",
        "classification_confidence",
        "classification_evidence",
        "classification_source",
    ],
)
def test_modern_classification_contract_rejects_each_missing_field(missing_field):
    data = _analysis_data(**_modern_classification())
    data.pop(missing_field)

    with pytest.raises(ValueError, match=f"现代分类契约.*{missing_field}"):
        ProductAnalysis.from_dict(data)


@pytest.mark.parametrize(
    "product_type",
    ["普通项链", "带链吊坠", "无链独立吊坠", "戒指", "疑似手链"],
)
def test_non_legacy_product_without_modern_classification_is_rejected(product_type):
    with pytest.raises(ValueError, match="旧手串/手链.*现代分类契约"):
        ProductAnalysis.from_dict(_analysis_data(product_type=product_type))


def test_modern_classification_requires_explicit_source_image_type():
    data = _analysis_data(**_modern_classification())
    data.pop("source_image_type")

    with pytest.raises(ValueError, match="现代分类.*source_image_type.*显式"):
        ProductAnalysis.from_dict(data)


@pytest.mark.parametrize(
    ("pendant_fields", "error_pattern"),
    [
        (
            {"has_pendant": False, "pendant_count": 1, "pendant_layer": None},
            "has_pendant=false.*pendant_count",
        ),
        (
            {"has_pendant": False, "pendant_count": 0, "pendant_layer": 1},
            "has_pendant=false.*pendant_layer",
        ),
        (
            {"has_pendant": True, "pendant_count": 0, "pendant_layer": 1},
            "has_pendant=true.*pendant_count",
        ),
        (
            {"has_pendant": True, "pendant_count": 1, "pendant_layer": None},
            "has_pendant=true.*pendant_layer",
        ),
    ],
)
def test_pendant_structure_requires_consistent_presence_fields(
    pendant_fields, error_pattern
):
    with pytest.raises(ValueError, match=error_pattern):
        ProductAnalysis.from_dict(_analysis_data(**pendant_fields))


@pytest.mark.parametrize(
    "pendant_fields",
    [
        {"has_pendant": False, "pendant_count": 0, "pendant_layer": None},
        {"has_pendant": True, "pendant_count": 0, "pendant_layer": 1},
        {"has_pendant": True, "pendant_count": 1, "pendant_layer": None},
    ],
)
def test_pendant_necklace_requires_complete_main_pendant(pendant_fields):
    with pytest.raises(ValueError, match="带链吊坠.*主吊坠"):
        ProductAnalysis.from_dict(
            _analysis_data(
                product_type="带链吊坠",
                **_modern_classification("pendant_necklace"),
                **pendant_fields,
            )
        )


def test_plain_necklace_rejects_main_pendant_fields():
    with pytest.raises(ValueError, match="普通项链.*主吊坠"):
        ProductAnalysis.from_dict(
            _analysis_data(
                product_type="普通项链",
                **_modern_classification("necklace"),
                has_pendant=True,
                pendant_count=1,
                pendant_layer=1,
            )
        )


def test_pendant_only_parses_without_chain_layer():
    analysis = ProductAnalysis.from_dict(
        _analysis_data(
            product_type="无链独立吊坠",
            **_modern_classification("pendant_only"),
            has_pendant=True,
            pendant_count=1,
            pendant_layer=None,
        )
    )

    assert analysis.confirmed_product_type is ProductType.PENDANT_ONLY
    assert analysis.has_pendant is True
    assert analysis.pendant_count == 1
    assert analysis.pendant_layer is None


@pytest.mark.parametrize("product_type", ["necklace", "pendant_necklace"])
@pytest.mark.parametrize(
    "length_category",
    ["choker", "collarbone", "upper_chest", "long"],
)
def test_necklace_types_accept_closed_length_categories(
    product_type, length_category
):
    pendant_fields = (
        {"has_pendant": True, "pendant_count": 1, "pendant_layer": 1}
        if product_type == "pendant_necklace"
        else {}
    )

    analysis = ProductAnalysis.from_dict(
        _analysis_data(
            product_type=("普通项链" if product_type == "necklace" else "带链吊坠"),
            **_modern_classification(product_type),
            length_category=length_category,
            **pendant_fields,
        )
    )

    assert analysis.length_category == length_category


@pytest.mark.parametrize("product_type", ["necklace", "pendant_necklace"])
def test_necklace_types_reject_unknown_length_category(product_type):
    pendant_fields = (
        {"has_pendant": True, "pendant_count": 1, "pendant_layer": 1}
        if product_type == "pendant_necklace"
        else {}
    )

    with pytest.raises(
        ValueError,
        match="length_category.*choker.*collarbone.*upper_chest.*long",
    ):
        ProductAnalysis.from_dict(
            _analysis_data(
                product_type=(
                    "普通项链" if product_type == "necklace" else "带链吊坠"
                ),
                **_modern_classification(product_type),
                length_category="princess",
                **pendant_fields,
            )
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "companion_fields"),
    [
        ("layer_count", "1", {}),
        ("layer_count", True, {}),
        (
            "pendant_count",
            "1",
            {"has_pendant": True, "pendant_layer": 1},
        ),
        (
            "pendant_count",
            True,
            {"has_pendant": True, "pendant_layer": 1},
        ),
        (
            "pendant_layer",
            "1",
            {"has_pendant": True, "pendant_count": 1},
        ),
        (
            "pendant_layer",
            True,
            {"has_pendant": True, "pendant_count": 1},
        ),
    ],
)
def test_new_integer_fields_require_json_integers(
    field_name, invalid_value, companion_fields
):
    with pytest.raises(ValueError, match=f"{field_name}.*JSON 整数"):
        ProductAnalysis.from_dict(
            _analysis_data(
                **companion_fields,
                **{field_name: invalid_value},
            )
        )


@pytest.mark.parametrize(
    "field_name",
    ["has_pendant", "is_independent_multi_item"],
)
def test_new_boolean_fields_reject_string_json_values(field_name):
    with pytest.raises(ValueError, match=f"{field_name}.*JSON 布尔值"):
        ProductAnalysis.from_dict(_analysis_data(**{field_name: "false"}))
