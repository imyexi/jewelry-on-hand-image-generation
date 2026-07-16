from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jewelry_on_hand.models import ReferenceRow


REFERENCE_SELECTION_FILE_NAME = "reference_selection_constraints.json"
MATCH_FIELD_NAMES = (
    "style_category",
    "scene_keywords",
    "pose_keywords",
    "recommended_usage",
    "framing",
    "visible_body_regions",
    "product_visibility",
    "hand_visibility",
    "hand_side",
    "hand_orientation",
    "visible_fingers",
    "mirror_relation",
    "collar_type",
)


def normalize_reference_selection_prompt(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    normalized: list[str] = []
    for part in re.split(r"[，,；;\r\n]+", value):
        condition = part.strip()
        if condition and condition not in normalized:
            normalized.append(condition)
    return tuple(normalized)


@dataclass(frozen=True)
class ReferenceSelectionConstraints:
    original_prompt: str
    normalized_conditions: tuple[str, ...]

    @classmethod
    def from_prompt(cls, value: str | None) -> "ReferenceSelectionConstraints":
        original_prompt = value.strip() if value else ""
        return cls(
            original_prompt=original_prompt,
            normalized_conditions=normalize_reference_selection_prompt(value),
        )

    @property
    def mode(self) -> str:
        if self.normalized_conditions:
            return "prompt_hard_gate"
        return "keyword_relevance_only"


@dataclass(frozen=True)
class CandidateConstraintEvaluation:
    reference_index: int
    matched: bool
    condition_matches: dict[str, tuple[str, ...]]


def evaluate_candidate_constraints(
    row: ReferenceRow,
    conditions: Sequence[str],
) -> CandidateConstraintEvaluation:
    condition_matches: dict[str, tuple[str, ...]] = {}
    for condition in conditions:
        needle = condition.casefold()
        condition_matches[condition] = tuple(
            field_name
            for field_name in MATCH_FIELD_NAMES
            if needle in getattr(row, field_name).casefold()
        )
    return CandidateConstraintEvaluation(
        reference_index=row.index,
        matched=all(condition_matches.values()),
        condition_matches=condition_matches,
    )


def build_reference_selection_audit(
    constraints: ReferenceSelectionConstraints,
    *,
    before_base_gates: int,
    after_base_gates: int,
    evaluations: Sequence[CandidateConstraintEvaluation],
) -> dict[str, Any]:
    matched_fields = sorted(
        {
            field_name
            for evaluation in evaluations
            for fields in evaluation.condition_matches.values()
            for field_name in fields
        }
    )
    return {
        "schema_version": 1,
        "mode": constraints.mode,
        "original_prompt": constraints.original_prompt,
        "normalized_conditions": list(constraints.normalized_conditions),
        "matched_fields": matched_fields,
        "candidate_counts": {
            "before_base_gates": before_base_gates,
            "after_base_gates": after_base_gates,
            "after_prompt_gates": sum(item.matched for item in evaluations),
        },
        "condition_match_counts": {
            condition: sum(
                bool(item.condition_matches.get(condition)) for item in evaluations
            )
            for condition in constraints.normalized_conditions
        },
        "candidate_evaluations": [
            {
                "reference_index": item.reference_index,
                "matched": item.matched,
                "condition_matches": {
                    condition: list(fields)
                    for condition, fields in item.condition_matches.items()
                },
            }
            for item in evaluations
        ],
    }


def reference_selection_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "MATCH_FIELD_NAMES",
    "REFERENCE_SELECTION_FILE_NAME",
    "CandidateConstraintEvaluation",
    "ReferenceSelectionConstraints",
    "build_reference_selection_audit",
    "evaluate_candidate_constraints",
    "normalize_reference_selection_prompt",
    "reference_selection_sha256",
]
