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
from jewelry_on_hand.product_fidelity import (
    load_product_fidelity_constraints,
    require_confirmed_constraints,
)
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


DECISION_FILE_NAME = "review_decision.json"
CANONICAL_CONSTRAINTS_RELATIVE_PATH = "analysis/product_fidelity_constraints.json"
_GENERATION_ACTIONS = {"generate_rank_1", "generate_selected", "generate_multiple"}


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

    decision_path = paths.review_dir / DECISION_FILE_NAME
    _commit_json_transaction(
        [
            (paths.analysis_dir / "product_analysis.json", analysis_data),
            (decision_path, _decision_to_dict(decision)),
        ]
    )
    return decision_path


def write_review_bundle(
    paths: RunPaths,
    decision_data: dict[str, Any],
    *,
    analysis_data: dict[str, Any] | None = None,
) -> Path:
    """原子提交可选 analysis、decision 与规范保真约束。"""
    try:
        normalized_decision_data = dict(decision_data)
        action = normalized_decision_data.get("action")
        constraints_payload: dict[str, Any] | None = None
        if action in _GENERATION_ACTIONS:
            import_source = _constraints_import_source(normalized_decision_data)
            normalized_decision_data["fidelity_constraints_path"] = (
                CANONICAL_CONSTRAINTS_RELATIVE_PATH
            )
        else:
            import_source = None

        if analysis_data is None:
            analysis = _load_optional_analysis(paths)
        else:
            analysis = ProductAnalysis.from_dict(analysis_data)
            validate_confirmed_analysis(analysis)
        decision = ReviewDecision.from_dict(normalized_decision_data)
        if analysis is not None:
            validate_decision_against_analysis(decision, analysis)
        elif _is_generation_with_snapshot(decision):
            raise ReviewGateError("确认快照存在但缺少最终产品分析，无法校验一致性")

        if decision.action in _GENERATION_ACTIONS and decision.fidelity_confirmed:
            constraints_path = _resolve_constraints_path(paths, import_source)
            if not constraints_path.is_file():
                raise ReviewGateError(f"缺少产品保真约束导入源：{constraints_path}")
            constraints = load_product_fidelity_constraints(constraints_path)
            constraints_payload = constraints.to_dict()
            if constraints.review_status == "pending":
                constraints_payload["review_status"] = "confirmed"
    except (OSError, TypeError, ValueError, ReviewGateError) as exc:
        if isinstance(exc, ReviewGateError):
            raise
        raise ReviewGateError(f"无法提交 Review 事务：产品保真约束或决策无效；{exc}") from exc

    decision_path = paths.review_dir / DECISION_FILE_NAME
    entries: list[tuple[Path, Any]] = []
    if analysis_data is not None:
        entries.append((paths.analysis_dir / "product_analysis.json", analysis_data))
    entries.append((decision_path, _decision_to_dict(decision)))
    if constraints_payload is not None:
        entries.append(
            (
                paths.root / CANONICAL_CONSTRAINTS_RELATIVE_PATH,
                constraints_payload,
            )
        )
    _commit_json_transaction(entries)
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
    if decision.fidelity_constraints_path != CANONICAL_CONSTRAINTS_RELATIVE_PATH:
        raise ReviewGateError(
            f"{decision_path} 使用非标准产品保真约束路径 "
            f"{decision.fidelity_constraints_path!r}；请重新执行 record-decision"
        )
    try:
        analysis = _load_optional_analysis(paths)
        if analysis is not None:
            validate_decision_against_analysis(decision, analysis)
        elif _is_generation_with_snapshot(decision):
            raise ReviewGateError("确认快照存在但缺少最终产品分析，无法校验一致性")
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(f"无效的最终产品分析或确认快照：{exc}") from exc
    constraints_path = paths.root / CANONICAL_CONSTRAINTS_RELATIVE_PATH
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
        decision.action in _GENERATION_ACTIONS
        and decision.confirmation_snapshot is not None
    )


def _constraints_import_source(decision_data: dict[str, Any]) -> str:
    raw_path = decision_data.get(
        "fidelity_constraints_path",
        CANONICAL_CONSTRAINTS_RELATIVE_PATH,
    )
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("fidelity_constraints_path 必须是非空路径字符串")
    return raw_path.strip()


def _commit_json_transaction(entries: list[tuple[Path, Any]]) -> None:
    targets = [target for target, _payload in entries]
    if len(set(targets)) != len(targets):
        raise ReviewGateError("原子提交目标路径不能重复")
    previous = {
        target: target.read_bytes() if target.is_file() else None
        for target in targets
    }
    staged_entries: list[tuple[Path, Path]] = []
    replaced_targets: list[Path] = []
    label = {1: "文件", 2: "双文件", 3: "三文件"}.get(
        len(entries),
        f"{len(entries)} 文件",
    )
    try:
        for target, payload in entries:
            staged_entries.append((_stage_json(target, payload), target))
        for staged_path, target in staged_entries:
            os.replace(staged_path, target)
            replaced_targets.append(target)
    except Exception as exc:
        rollback_errors: list[str] = []
        for target in reversed(replaced_targets):
            try:
                _restore_previous_file(target, previous[target])
            except OSError as rollback_exc:
                rollback_errors.append(f"{target}: {rollback_exc}")
        if rollback_errors:
            details = "；".join(rollback_errors)
            raise ReviewGateError(
                f"{label}提交失败，且回滚未完整：{exc}；回滚异常：{details}"
            ) from exc
        raise ReviewGateError(f"{label}提交失败，已回滚：{exc}") from exc
    finally:
        for staged_path, _target in staged_entries:
            staged_path.unlink(missing_ok=True)


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
    "CANONICAL_CONSTRAINTS_RELATIVE_PATH",
    "ReviewGateError",
    "require_generation_decision",
    "validate_confirmed_analysis",
    "validate_decision_against_analysis",
    "write_analysis_and_review_decision",
    "write_review_bundle",
    "write_review_decision",
]
