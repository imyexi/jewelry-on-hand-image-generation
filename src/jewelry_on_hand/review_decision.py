from __future__ import annotations

from pathlib import Path
from typing import Any

from jewelry_on_hand.models import ReviewDecision
from jewelry_on_hand.product_fidelity import require_confirmed_constraints
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


DECISION_FILE_NAME = "review_decision.json"


class ReviewGateError(RuntimeError):
    """Review 决策 Gate 未满足时抛出。"""


def write_review_decision(paths: RunPaths, data: dict[str, Any]) -> Path:
    decision = ReviewDecision.from_dict(data)
    decision_path = paths.review_dir / DECISION_FILE_NAME
    write_json(decision_path, _decision_to_dict(decision))
    return decision_path


def require_generation_decision(paths: RunPaths) -> ReviewDecision:
    decision_path = paths.review_dir / DECISION_FILE_NAME
    if not decision_path.is_file():
        raise ReviewGateError(f"缺少生成前 Review 决策文件：{decision_path}")

    try:
        decision = ReviewDecision.from_dict(read_json(decision_path))
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(f"无效的 Review 决策文件：{decision_path}；{exc}") from exc
    if decision.action == "rerank":
        raise ReviewGateError(f"{decision_path} 的 rerank 决策不允许进入生成")
    if decision.action == "manual_reference":
        raise ReviewGateError(
            f"{decision_path} 的 manual_reference 决策第一版暂不支持进入生成，请重新选择 rank"
        )
    if not decision.fidelity_confirmed:
        raise ReviewGateError(f"{decision_path} 缺少 fidelity_confirmed: true")
    constraints_path = _resolve_constraints_path(paths, decision.fidelity_constraints_path)
    if not constraints_path.is_file():
        raise ReviewGateError(f"缺少产品保真约束文件：{constraints_path}")
    try:
        require_confirmed_constraints(constraints_path)
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(f"无效的产品保真约束文件：{constraints_path}；{exc}") from exc
    return decision


def _decision_to_dict(decision: ReviewDecision) -> dict[str, Any]:
    data: dict[str, Any] = {
        "action": decision.action,
        "selected_ranks": list(decision.selected_ranks),
    }
    if decision.manual_reference is not None:
        data["manual_reference"] = decision.manual_reference
    if decision.action in {"generate_rank_1", "generate_selected", "generate_multiple"}:
        data["fidelity_confirmed"] = decision.fidelity_confirmed
        data["fidelity_constraints_path"] = decision.fidelity_constraints_path
    if decision.fidelity_notes is not None:
        data["fidelity_notes"] = decision.fidelity_notes
    return data


def _resolve_constraints_path(paths: RunPaths, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return paths.root / candidate
