import pytest

import jewelry_on_hand.review_decision as review_decision

from jewelry_on_hand.review_decision import (
    ReviewGateError,
    require_generation_decision,
    validate_confirmed_analysis,
    validate_decision_against_analysis,
    write_analysis_and_review_decision,
    write_review_decision,
)
from jewelry_on_hand.models import ProductAnalysis, ReviewDecision
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


def _constraints_data(review_status="confirmed", must_keep=None):
    if must_keep is None:
        must_keep = [
            {
                "name": "白水晶随形",
                "source_text": "白水晶随形",
                "normalized_keyword": "随形",
                "location": "主珠右侧",
                "visual_shape": "透明不规则随形，非圆珠",
                "relationship": "位于两颗圆珠之间",
                "forbid": ["改成圆珠"],
                "qc_question": "白水晶随形是否仍是不规则透明异形珠",
            }
        ]
    return {
        "schema_version": 1,
        "source": {
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
        },
        "detected_keywords": ["随形"] if must_keep else [],
        "must_keep": must_keep,
        "must_not_change": ["珠子排列顺序"],
        "needs_user_review": bool(must_keep),
        "detail_crop_recommended": bool(must_keep),
        "review_status": review_status,
    }


def _write_confirmed_constraints(paths):
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data())


def _necklace_analysis_data(**overrides):
    data = {
        "product_type": "带链吊坠",
        "detected_product_type": "pendant_necklace",
        "confirmed_product_type": "pendant_necklace",
        "classification_confidence": "high",
        "classification_evidence": ["中央存在主吊坠"],
        "classification_source": "auto_confirmed",
        "display_mode": "worn",
        "source_image_type": "worn_source",
        "wear_position": "颈部和锁骨",
        "visible_appearance": "双层珠链，第二层中央有吊坠",
        "color_family": ["白色"],
        "style_mood": "精致",
        "composition": "胸前近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
        "layer_count": 2,
        "length_category": "collarbone",
        "chain_or_strand_type": "beaded",
        "has_pendant": True,
        "pendant_count": 1,
        "pendant_layer": 2,
        "pendant_position": "front_center",
        "pendant_orientation": "front_facing",
        "connection_structure": "metal_bail",
        "symmetry": "approximately_symmetric",
        "occluded_parts": ["后颈扣头"],
        "uncertain_details": ["扣头具体结构"],
        "is_independent_multi_item": False,
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


def test_generation_requires_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    with pytest.raises(ReviewGateError, match="review_decision.json"):
        require_generation_decision(paths)


def test_write_and_read_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_confirmed_constraints(paths)
    write_review_decision(paths, {"action": "generate_selected", "selected_ranks": [2], "fidelity_confirmed": True})
    assert require_generation_decision(paths).selected_ranks == [2]


def test_generation_rejects_rerank_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_review_decision(paths, {"action": "rerank"})

    with pytest.raises(ReviewGateError, match="rerank"):
        require_generation_decision(paths)


def test_generation_rejects_manual_reference_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_review_decision(paths, {"action": "manual_reference", "manual_reference": "manual.jpg"})

    with pytest.raises(ReviewGateError, match="manual_reference"):
        require_generation_decision(paths)


def test_write_review_decision_normalizes_generate_rank_1(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")

    written_path = write_review_decision(paths, {"action": "generate_rank_1", "fidelity_confirmed": True})

    assert written_path == paths.review_dir / "review_decision.json"
    assert read_json(written_path) == {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
    }


def test_write_review_decision_normalizes_json_payload(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    data = {"action": "generate_multiple", "selected_ranks": [1, 3], "fidelity_confirmed": True}

    written_path = write_review_decision(paths, data)

    assert written_path == paths.review_dir / "review_decision.json"
    assert read_json(written_path) == data | {"fidelity_constraints_path": "analysis/product_fidelity_constraints.json"}


def test_read_decision_wraps_malformed_json(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    decision_path = paths.review_dir / "review_decision.json"
    decision_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ReviewGateError, match="review_decision.json") as exc_info:
        require_generation_decision(paths)

    assert str(decision_path) in str(exc_info.value)


def test_read_decision_wraps_persisted_invalid_action(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    decision_path = paths.review_dir / "review_decision.json"
    write_json(decision_path, {"action": "bad"})

    with pytest.raises(ReviewGateError, match="review_decision.json") as exc_info:
        require_generation_decision(paths)

    assert str(decision_path) in str(exc_info.value)


def test_read_decision_wraps_persisted_invalid_fields(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    decision_path = paths.review_dir / "review_decision.json"
    write_json(decision_path, {"action": "generate_selected"})

    with pytest.raises(ReviewGateError, match="review_decision.json") as exc_info:
        require_generation_decision(paths)

    assert str(decision_path) in str(exc_info.value)


def test_require_generation_decision_rejects_missing_fidelity_confirmation(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_confirmed_constraints(paths)
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1]})

    with pytest.raises(ReviewGateError, match="fidelity_confirmed"):
        require_generation_decision(paths)


def test_require_generation_decision_rejects_missing_constraints_file(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True})

    with pytest.raises(ReviewGateError, match="product_fidelity_constraints.json"):
        require_generation_decision(paths)


def test_require_generation_decision_rejects_pending_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="pending"))
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True})

    with pytest.raises(ReviewGateError, match="pending"):
        require_generation_decision(paths)


def test_require_generation_decision_rejects_historical_noncanonical_path(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_confirmed_constraints(paths)
    imported_path = paths.review_dir / "historical-constraints.json"
    write_json(imported_path, _constraints_data(review_status="confirmed"))
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "review/historical-constraints.json",
        },
    )

    with pytest.raises(ReviewGateError, match="非标准.*重新.*record-decision"):
        require_generation_decision(paths)


def test_require_generation_decision_allows_not_applicable_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="not_applicable", must_keep=[]))
    write_review_decision(paths, {"action": "generate_rank_1", "fidelity_confirmed": True})

    assert require_generation_decision(paths).selected_ranks == [1]


def test_necklace_generation_write_requires_confirmation_snapshot(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_analysis.json", _necklace_analysis_data())

    with pytest.raises(ReviewGateError, match="确认快照"):
        write_review_decision(
            paths,
            {"action": "generate_rank_1", "fidelity_confirmed": True},
        )


def test_necklace_snapshot_requires_final_analysis_on_write_and_read(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    payload = {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "confirmation_snapshot": _confirmation_snapshot(),
    }

    with pytest.raises(ReviewGateError, match="缺少最终产品分析"):
        write_review_decision(paths, payload)

    _write_confirmed_constraints(paths)
    write_json(paths.review_dir / "review_decision.json", payload)
    with pytest.raises(ReviewGateError, match="缺少最终产品分析"):
        require_generation_decision(paths)


def test_necklace_decision_snapshot_roundtrip_and_strict_validation(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    analysis_data = _necklace_analysis_data()
    write_json(paths.analysis_dir / "product_analysis.json", analysis_data)
    _write_confirmed_constraints(paths)

    decision_path = write_review_decision(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "confirmation_snapshot": _confirmation_snapshot(),
        },
    )

    assert read_json(decision_path)["confirmation_snapshot"] == _confirmation_snapshot()
    decision = require_generation_decision(paths)
    validate_decision_against_analysis(decision, ProductAnalysis.from_dict(analysis_data))


def test_strict_validation_rejects_snapshot_that_differs_from_final_analysis(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_analysis.json", _necklace_analysis_data())
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
            "confirmation_snapshot": _confirmation_snapshot(layer_count=1, pendant_layer=1),
        },
    )

    with pytest.raises(ReviewGateError, match="layer_count.*不一致"):
        require_generation_decision(paths)


def test_read_rejects_incomplete_persisted_confirmation_snapshot(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_analysis.json", _necklace_analysis_data())
    _write_confirmed_constraints(paths)
    snapshot = _confirmation_snapshot()
    del snapshot["pendant_orientation"]
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "confirmation_snapshot": snapshot,
        },
    )

    with pytest.raises(ReviewGateError, match="pendant_orientation"):
        require_generation_decision(paths)


def test_historical_bracelet_generation_without_snapshot_remains_compatible(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(
        paths.analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "wear_position": "手腕",
            "visible_appearance": "红色圆珠",
            "color_family": ["红色"],
            "style_mood": "简洁",
            "composition": "手腕近景",
            "product_dimensions": {},
        },
    )
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
        },
    )

    assert require_generation_decision(paths).confirmation_snapshot is None


def test_historical_bracelet_without_snapshot_still_checks_mode_compatibility(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(
        paths.analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "detected_product_type": "bracelet",
            "confirmed_product_type": "bracelet",
            "classification_confidence": "high",
            "classification_evidence": ["佩戴在手腕"],
            "classification_source": "auto_confirmed",
            "display_mode": "hand_held",
            "source_image_type": "worn_source",
            "wear_position": "手腕",
            "visible_appearance": "红色圆珠",
            "color_family": ["红色"],
            "style_mood": "简洁",
            "composition": "手腕近景",
            "product_dimensions": {},
        },
    )
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
        },
    )

    with pytest.raises(ReviewGateError, match="手串/手链与手持展示模式不兼容"):
        require_generation_decision(paths)


def test_confirmed_analysis_validation_does_not_depend_on_decision_action():
    analysis = ProductAnalysis.from_dict(
        _necklace_analysis_data(source_image_type="flat_lay_source")
    )

    with pytest.raises(ReviewGateError, match="第一阶段只接受真人佩戴原图"):
        validate_confirmed_analysis(analysis)


def test_pair_write_updates_analysis_and_decision_together(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    analysis_data = _necklace_analysis_data()
    decision_data = {
        "action": "rerank",
        "confirmation_snapshot": _confirmation_snapshot(),
    }

    decision_path = write_analysis_and_review_decision(
        paths,
        analysis_data,
        decision_data,
    )

    assert read_json(paths.analysis_dir / "product_analysis.json") == analysis_data
    assert decision_path == paths.review_dir / "review_decision.json"
    assert read_json(decision_path)["confirmation_snapshot"] == _confirmation_snapshot()


def test_pair_write_rolls_back_both_files_when_second_replace_fails(tmp_path, monkeypatch):
    import os

    paths = RunPaths.create(tmp_path, "run-1")
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    old_analysis = b'{"old_analysis": true}\n'
    old_decision = b'{"old_decision": true}\n'
    analysis_path.write_bytes(old_analysis)
    decision_path.write_bytes(old_decision)
    original_replace = os.replace
    replace_count = 0

    def fail_second_replace(source, target):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("模拟第二次替换失败")
        return original_replace(source, target)

    monkeypatch.setattr("jewelry_on_hand.review_decision.os.replace", fail_second_replace)

    with pytest.raises(ReviewGateError, match="双文件提交失败.*模拟第二次替换失败"):
        write_analysis_and_review_decision(
            paths,
            _necklace_analysis_data(),
            {
                "action": "rerank",
                "confirmation_snapshot": _confirmation_snapshot(),
            },
        )

    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert not list(paths.analysis_dir.glob("*.tmp"))
    assert not list(paths.review_dir.glob("*.tmp"))


def test_review_bundle_imports_pending_constraints_to_canonical_and_confirms(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    imported_path = paths.review_dir / "imported-constraints.json"
    write_json(imported_path, _constraints_data(review_status="pending"))

    decision_path = review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "review/imported-constraints.json",
        },
    )

    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    assert read_json(canonical_path)["review_status"] == "confirmed"
    assert read_json(imported_path)["review_status"] == "pending"
    assert read_json(decision_path)["fidelity_constraints_path"] == (
        "analysis/product_fidelity_constraints.json"
    )


@pytest.mark.parametrize("review_status", ["confirmed", "corrected", "not_applicable"])
def test_review_bundle_preserves_already_reviewed_constraint_status(
    tmp_path,
    review_status,
):
    paths = RunPaths.create(tmp_path, f"run-{review_status}")
    imported_path = paths.review_dir / "imported-constraints.json"
    write_json(
        imported_path,
        _constraints_data(
            review_status=review_status,
            must_keep=[] if review_status == "not_applicable" else None,
        ),
    )

    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "fidelity_constraints_path": str(imported_path),
        },
    )

    canonical = read_json(paths.analysis_dir / "product_fidelity_constraints.json")
    assert canonical["review_status"] == review_status


@pytest.mark.parametrize("source_kind", ["missing", "malformed"])
def test_review_bundle_validates_constraints_before_any_replace(
    tmp_path,
    monkeypatch,
    source_kind,
):
    paths = RunPaths.create(tmp_path, f"run-{source_kind}")
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    old_analysis = b'{"old_analysis": true}\n'
    old_decision = b'{"old_decision": true}\n'
    old_constraints = b'{"old_constraints": true}\n'
    analysis_path.write_bytes(old_analysis)
    decision_path.write_bytes(old_decision)
    canonical_path.write_bytes(old_constraints)
    imported_path = paths.review_dir / "imported-constraints.json"
    if source_kind == "malformed":
        write_json(imported_path, {"review_status": "pending"})
    replace_calls = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda source, target: replace_calls.append((source, target)),
    )

    with pytest.raises(ReviewGateError, match="产品保真约束"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
            },
            analysis_data=_necklace_analysis_data(),
        )

    assert replace_calls == []
    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints


def test_review_bundle_rolls_back_analysis_decision_and_constraints_on_third_replace(
    tmp_path,
    monkeypatch,
):
    import os

    paths = RunPaths.create(tmp_path, "run-rollback-three")
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    old_analysis = b'{"old_analysis": true}\n'
    old_decision = b'{"old_decision": true}\n'
    old_constraints = b'{"old_constraints": true}\n'
    analysis_path.write_bytes(old_analysis)
    decision_path.write_bytes(old_decision)
    canonical_path.write_bytes(old_constraints)
    imported_path = paths.review_dir / "imported-constraints.json"
    write_json(imported_path, _constraints_data(review_status="pending"))
    original_replace = os.replace
    replace_count = 0

    def fail_third_replace(source, target):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 3:
            raise OSError("模拟第三次替换失败")
        return original_replace(source, target)

    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        fail_third_replace,
    )

    with pytest.raises(ReviewGateError, match="三文件提交失败.*模拟第三次替换失败"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
            },
            analysis_data=_necklace_analysis_data(),
        )

    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints
    assert not list(paths.analysis_dir.glob("*.tmp"))
    assert not list(paths.review_dir.glob("*.tmp"))
