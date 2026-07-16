from __future__ import annotations

from pathlib import Path

from jewelry_on_hand.models import ReferenceRow
from jewelry_on_hand.reference_selection import (
    ReferenceSelectionConstraints,
    build_reference_selection_audit,
    evaluate_candidate_constraints,
    normalize_reference_selection_prompt,
    reference_selection_sha256,
)


def _row(**overrides: object) -> ReferenceRow:
    data: dict[str, object] = {
        "index": 1,
        "file_name": "reference.jpg",
        "relative_path": "reference.jpg",
        "absolute_path": Path("reference.jpg"),
        "width": 1200,
        "height": 1600,
        "size_mb": 1.2,
        "purpose_category": "手部佩戴图",
        "bracelet_applicability": "适用",
        "default_strategy": "常规可优先使用",
        "style_category": "清透",
        "scene_keywords": "浅色背景 自然光",
        "jewelry_type": "手串",
        "recommended_usage": "右手近景佩戴展示",
        "notes": "",
        "confidence": "高",
        "file_exists": True,
        "applicable_product_types": "bracelet",
        "applicable_display_modes": "worn",
        "pose_keywords": "右手 手背",
    }
    data.update(overrides)
    return ReferenceRow(**data)  # type: ignore[arg-type]


def test_normalize_reference_selection_prompt_splits_only_declared_delimiters() -> None:
    assert normalize_reference_selection_prompt(
        " 浅色背景；自然光,右手\n近景；浅色背景 "
    ) == ("浅色背景", "自然光", "右手", "近景")
    assert normalize_reference_selection_prompt("右手 近景") == ("右手 近景",)
    assert normalize_reference_selection_prompt(" ；,\n ") == ()


def test_candidate_must_match_every_condition_in_whitelisted_fields() -> None:
    row = _row(notes="近景", recommended_usage="佩戴展示")

    evaluation = evaluate_candidate_constraints(
        row,
        ("浅色背景", "自然光", "右手", "近景"),
    )

    assert evaluation.matched is False
    assert evaluation.condition_matches["右手"] == ("pose_keywords",)
    assert evaluation.condition_matches["近景"] == ()


def test_audit_and_sha256_are_stable_for_equivalent_input() -> None:
    constraints = ReferenceSelectionConstraints.from_prompt("自然光；右手")
    rows = [
        _row(index=1),
        _row(index=2, pose_keywords="左手", recommended_usage="佩戴展示"),
    ]
    evaluations = [
        evaluate_candidate_constraints(row, constraints.normalized_conditions)
        for row in rows
    ]

    audit = build_reference_selection_audit(
        constraints,
        before_base_gates=3,
        after_base_gates=2,
        evaluations=evaluations,
    )

    assert audit["schema_version"] == 1
    assert audit["mode"] == "prompt_hard_gate"
    assert audit["condition_match_counts"] == {"自然光": 2, "右手": 1}
    assert audit["candidate_counts"] == {
        "before_base_gates": 3,
        "after_base_gates": 2,
        "after_prompt_gates": 1,
    }
    assert reference_selection_sha256(audit) == reference_selection_sha256(
        dict(reversed(list(audit.items())))
    )


def test_empty_prompt_uses_keyword_relevance_mode() -> None:
    constraints = ReferenceSelectionConstraints.from_prompt(None)

    assert constraints.original_prompt == ""
    assert constraints.normalized_conditions == ()
    assert constraints.mode == "keyword_relevance_only"
