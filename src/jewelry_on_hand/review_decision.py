from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import validate_product_mode
from jewelry_on_hand.models import ProductAnalysis, ProductConfirmationSnapshot, ReviewDecision
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.product_fidelity import require_confirmed_constraints
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


DECISION_FILE_NAME = "review_decision.json"


class ReviewGateError(RuntimeError):
    """Review 决策 Gate 未满足时抛出。"""


def write_review_decision(paths: RunPaths, data: dict[str, Any]) -> Path:
    try:
        decision = ReviewDecision.from_dict(data)
        analysis = _load_optional_analysis(paths)
        if analysis is not None:
            validate_decision_against_analysis(decision, analysis)
        elif _is_generation_with_snapshot(decision):
            raise ReviewGateError("确认快照存在但缺少最终产品分析，无法校验一致性")
    except (OSError, TypeError, ValueError, ReviewGateError) as exc:
        if isinstance(exc, ReviewGateError):
            raise
        raise ReviewGateError(f"无法写入 Review 决策：{exc}") from exc
    decision_path = paths.review_dir / DECISION_FILE_NAME
    write_json(decision_path, _decision_to_dict(decision))
    return decision_path


def write_analysis_and_review_decision(
    paths: RunPaths,
    analysis_data: dict[str, Any],
    decision_data: dict[str, Any],
) -> Path:
    """校验并以失败可回滚的方式同步提交 analysis 与 decision。"""
    try:
        analysis = ProductAnalysis.from_dict(analysis_data)
        validate_confirmed_analysis(analysis)
        decision = ReviewDecision.from_dict(decision_data)
        validate_decision_against_analysis(decision, analysis)
    except (TypeError, ValueError, ReviewGateError) as exc:
        if isinstance(exc, ReviewGateError):
            raise
        raise ReviewGateError(f"无法提交产品分析与 Review 决策：{exc}") from exc

    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / DECISION_FILE_NAME
    previous = {
        analysis_path: analysis_path.read_bytes() if analysis_path.is_file() else None,
        decision_path: decision_path.read_bytes() if decision_path.is_file() else None,
    }
    staged_paths: list[Path] = []
    try:
        staged_analysis = _stage_json(analysis_path, analysis_data)
        staged_paths.append(staged_analysis)
        staged_decision = _stage_json(decision_path, _decision_to_dict(decision))
        staged_paths.append(staged_decision)
        os.replace(staged_analysis, analysis_path)
        os.replace(staged_decision, decision_path)
    except Exception as exc:
        rollback_errors: list[str] = []
        for target_path, old_bytes in previous.items():
            try:
                _restore_previous_file(target_path, old_bytes)
            except OSError as rollback_exc:
                rollback_errors.append(f"{target_path}: {rollback_exc}")
        if rollback_errors:
            details = "；".join(rollback_errors)
            raise ReviewGateError(
                f"双文件提交失败，且回滚未完整：{exc}；回滚异常：{details}"
            ) from exc
        raise ReviewGateError(f"双文件提交失败，已回滚：{exc}") from exc
    finally:
        for staged_path in staged_paths:
            staged_path.unlink(missing_ok=True)
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
    try:
        analysis = _load_optional_analysis(paths)
        if analysis is not None:
            validate_decision_against_analysis(decision, analysis)
        elif _is_generation_with_snapshot(decision):
            raise ReviewGateError("确认快照存在但缺少最终产品分析，无法校验一致性")
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(f"无效的最终产品分析或确认快照：{exc}") from exc
    constraints_path = _resolve_constraints_path(paths, decision.fidelity_constraints_path)
    if not constraints_path.is_file():
        raise ReviewGateError(f"缺少产品保真约束文件：{constraints_path}")
    try:
        require_confirmed_constraints(constraints_path)
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(f"无效的产品保真约束文件：{constraints_path}；{exc}") from exc
    return decision


def validate_decision_against_analysis(
    decision: ReviewDecision,
    analysis: ProductAnalysis,
) -> None:
    """严格校验生成决策快照与最终产品分析一致。"""
    if not isinstance(decision, ReviewDecision):
        raise ReviewGateError("decision 必须是 ReviewDecision")
    if not isinstance(analysis, ProductAnalysis):
        raise ReviewGateError("analysis 必须是 ProductAnalysis")
    if decision.action not in {"generate_rank_1", "generate_selected", "generate_multiple"}:
        return

    product_type = analysis.confirmed_product_type
    validate_confirmed_analysis(analysis)

    if product_type in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}:
        if decision.confirmation_snapshot is None:
            raise ReviewGateError("项链生成决策缺少完整产品确认快照")
    elif product_type is ProductType.BRACELET and decision.confirmation_snapshot is None:
        return

    snapshot = decision.confirmation_snapshot
    if snapshot is None:
        raise ReviewGateError("生成决策缺少产品确认快照")
    expected = ProductConfirmationSnapshot.from_analysis(analysis)
    actual_data = snapshot.to_dict()
    expected_data = expected.to_dict()
    for field_name, expected_value in expected_data.items():
        actual_value = actual_data[field_name]
        if actual_value != expected_value:
            raise ReviewGateError(
                f"确认快照字段 {field_name} 与最终 analysis 不一致："
                f"快照为 {actual_value!r}，analysis 为 {expected_value!r}"
            )


def validate_confirmed_analysis(analysis: ProductAnalysis) -> None:
    """校验人工确认后的产品分析是否满足当前生成能力边界。"""
    if not isinstance(analysis, ProductAnalysis):
        raise ReviewGateError("analysis 必须是 ProductAnalysis")
    try:
        validate_product_mode(
            analysis.confirmed_product_type,
            analysis.display_mode,
            analysis.source_image_type,
        )
        get_category_policy(analysis.confirmed_product_type).validate_generation(
            layer_count=analysis.layer_count,
            is_independent_multi_item=analysis.is_independent_multi_item,
        )
    except ValueError as exc:
        raise ReviewGateError(str(exc)) from exc


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
    if decision.confirmation_snapshot is not None:
        data["confirmation_snapshot"] = decision.confirmation_snapshot.to_dict()
    return data


def _load_optional_analysis(paths: RunPaths) -> ProductAnalysis | None:
    analysis_path = paths.analysis_dir / "product_analysis.json"
    if not analysis_path.is_file():
        return None
    return ProductAnalysis.from_dict(read_json(analysis_path))


def _is_generation_with_snapshot(decision: ReviewDecision) -> bool:
    return (
        decision.action in {"generate_rank_1", "generate_selected", "generate_multiple"}
        and decision.confirmation_snapshot is not None
    )


def _stage_json(target_path: Path, data: Any) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, raw_temp_path = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=target_path.parent,
    )
    temp_path = Path(raw_temp_path)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _restore_previous_file(target_path: Path, old_bytes: bytes | None) -> None:
    if old_bytes is None:
        target_path.unlink(missing_ok=True)
        return
    file_descriptor, raw_temp_path = tempfile.mkstemp(
        prefix=f".{target_path.name}.rollback.",
        suffix=".tmp",
        dir=target_path.parent,
    )
    temp_path = Path(raw_temp_path)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(old_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _resolve_constraints_path(paths: RunPaths, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return paths.root / candidate


__all__ = [
    "ReviewGateError",
    "require_generation_decision",
    "validate_confirmed_analysis",
    "validate_decision_against_analysis",
    "write_analysis_and_review_decision",
    "write_review_decision",
]
