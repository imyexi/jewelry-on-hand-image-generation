import pytest

from jewelry_on_hand.review_decision import (
    ReviewGateError,
    require_generation_decision,
    write_review_decision,
)
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


def test_require_generation_decision_allows_not_applicable_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="not_applicable", must_keep=[]))
    write_review_decision(paths, {"action": "generate_rank_1", "fidelity_confirmed": True})

    assert require_generation_decision(paths).selected_ranks == [1]
