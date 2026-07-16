from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import validate_product_mode
from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductConfirmationSnapshot,
    ProductFidelityConstraints,
    ReferenceRow,
    ReviewDecision,
    ScoredReference,
)
from jewelry_on_hand.output_roles import normalize_output_role
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.product_analysis import (
    validate_analysis_ready_for_reference_selection,
)
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    load_product_fidelity_constraints,
    product_analysis_sha256,
    require_confirmed_constraints,
    validate_product_fidelity_constraints,
)
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME,
    ReferenceCompositionSnapshot,
    build_candidate_snapshot,
    classify_reference_run,
    reference_composition_sha256,
    require_modern_reference_run,
    require_reference_review_ready,
    validate_snapshot_binding,
)
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


DECISION_FILE_NAME = "review_decision.json"
CANONICAL_CONSTRAINTS_RELATIVE_PATH = "analysis/product_fidelity_constraints.json"
_GENERATION_ACTIONS = {"generate_rank_1", "generate_selected", "generate_multiple"}


class ReviewGateError(RuntimeError):
    """Review 决策 Gate 未满足时抛出。"""


def _require_writable_review_run(paths: RunPaths) -> None:
    try:
        require_reference_review_ready(paths)
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(str(exc)) from exc


def _require_writable_review_bundle(
    paths: RunPaths,
    decision_data: dict[str, Any],
) -> None:
    action = decision_data.get("action") if isinstance(decision_data, dict) else None
    candidates_path = paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    confirmed_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    has_generation = paths.generation_dir.is_dir() and any(
        path.is_dir() for path in paths.generation_dir.iterdir()
    )
    if (
        action in _GENERATION_ACTIONS
        and not candidates_path.exists()
        and not confirmed_path.exists()
        and not has_generation
    ):
        # 无候选快照的生成事务最终必然只读失败；先保留约束校验的精确错误。
        return
    _require_writable_review_run(paths)


def write_review_decision(paths: RunPaths, data: dict[str, Any]) -> Path:
    _require_writable_review_run(paths)
    try:
        decision = ReviewDecision.from_dict(data)
        _reject_legacy_generation_write(decision)
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
    write_json(decision_path, decision.to_dict())
    return decision_path


def write_analysis_and_review_decision(
    paths: RunPaths,
    analysis_data: dict[str, Any],
    decision_data: dict[str, Any],
) -> Path:
    """校验并以失败可回滚的方式同步提交 analysis 与 decision。"""
    _require_writable_review_run(paths)
    try:
        analysis = ProductAnalysis.from_dict(analysis_data)
        validate_confirmed_analysis(analysis)
        decision = ReviewDecision.from_dict(decision_data)
        _reject_legacy_generation_write(decision)
        validate_decision_against_analysis(decision, analysis)
    except (TypeError, ValueError, ReviewGateError) as exc:
        if isinstance(exc, ReviewGateError):
            raise
        raise ReviewGateError(f"无法提交产品分析与 Review 决策：{exc}") from exc

    decision_path = paths.review_dir / DECISION_FILE_NAME
    _commit_json_transaction(
        [
            (paths.analysis_dir / "product_analysis.json", analysis_data),
            (decision_path, decision.to_dict()),
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
    _require_writable_review_bundle(paths, decision_data)
    try:
        normalized_decision_data = dict(decision_data)
        action = normalized_decision_data.get("action")
        analysis_payload = analysis_data
        constraints_payload: dict[str, Any] | None = None
        if action in _GENERATION_ACTIONS:
            if action == "generate_multiple":
                raise ReviewGateError(
                    "generate_multiple 仅保留历史读取，不允许记录新的参考快照决策"
                )
            import_source = _constraints_import_source(normalized_decision_data)
            normalized_decision_data["fidelity_constraints_path"] = (
                CANONICAL_CONSTRAINTS_RELATIVE_PATH
            )
        else:
            import_source = None

        if analysis_data is None:
            analysis_path = paths.analysis_dir / "product_analysis.json"
            if analysis_path.is_file():
                persisted_analysis_data = read_json(analysis_path)
                analysis = ProductAnalysis.from_dict(persisted_analysis_data)
                if action in _GENERATION_ACTIONS:
                    analysis_payload = persisted_analysis_data
            else:
                analysis = None
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
            if (
                analysis is not None
                and analysis_data is not None
                and import_source == CANONICAL_CONSTRAINTS_RELATIVE_PATH
            ):
                previous_analysis = _load_optional_analysis(paths)
                if (
                    previous_analysis is not None
                    and previous_analysis.confirmed_product_type
                    is not analysis.confirmed_product_type
                ):
                    raise ReviewGateError(
                        "最终产品品类发生变化；不得沿用旧品类 canonical 的 must_keep，"
                        "请使用 --fidelity-constraints-path 显式导入基于最终 analysis "
                        "重新生成并确认的产品保真约束"
                    )
                rebound = constraints.to_dict()
                rebound["source"]["product_analysis_sha256"] = (
                    product_analysis_sha256(analysis)
                )
                rebound["must_not_change"] = list(
                    build_product_fidelity_constraints(analysis).must_not_change
                )
                constraints = ProductFidelityConstraints.from_dict(rebound)
            if analysis is not None:
                validate_product_fidelity_constraints(analysis, constraints)
            constraints_payload = constraints.to_dict()
            if constraints.review_status == "pending":
                constraints_payload["review_status"] = "confirmed"

            snapshot, selected_reference = _confirmed_reference_snapshot_data(
                paths,
                decision,
            )
            if analysis is None:
                raise ReviewGateError("新快照 run 缺少最终 product_analysis.json")
            _validate_candidate_snapshot_draft(
                snapshot,
                selected_reference,
                analysis,
            )
            normalized_decision_data["reference_snapshot_sha256"] = (
                reference_composition_sha256(snapshot)
            )
            decision = ReviewDecision.from_dict(normalized_decision_data)
        else:
            snapshot = None
    except (OSError, TypeError, ValueError, ReviewGateError) as exc:
        if isinstance(exc, ReviewGateError):
            raise
        raise ReviewGateError(f"无法提交 Review 事务：产品保真约束或决策无效；{exc}") from exc

    decision_path = paths.review_dir / DECISION_FILE_NAME
    entries: list[tuple[Path, Any]] = []
    if analysis_payload is not None:
        entries.append((paths.analysis_dir / "product_analysis.json", analysis_payload))
    entries.append((decision_path, decision.to_dict()))
    if constraints_payload is not None:
        entries.append(
            (
                paths.root / CANONICAL_CONSTRAINTS_RELATIVE_PATH,
                constraints_payload,
            )
        )
    if snapshot is not None:
        entries.append(
            (
                paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
                snapshot.to_dict(),
            )
        )
    _commit_json_transaction(entries)
    return decision_path


def require_generation_decision(paths: RunPaths) -> ReviewDecision:
    decision_path = paths.review_dir / DECISION_FILE_NAME
    if not decision_path.is_file():
        raise ReviewGateError(f"缺少生成前 Review 决策文件：{decision_path}")

    try:
        decision_data = read_json(decision_path)
        try:
            decision = ReviewDecision.from_dict(
                decision_data,
                require_reference_snapshot_sha256=True,
            )
        except ValueError as strict_exc:
            if (
                isinstance(decision_data, dict)
                and decision_data.get("action") not in _GENERATION_ACTIONS
            ):
                decision = ReviewDecision.from_dict(decision_data)
            elif (
                isinstance(decision_data, dict)
                and decision_data.get("action") in _GENERATION_ACTIONS
            ):
                if classify_reference_run(paths) == "legacy_read_only":
                    try:
                        require_modern_reference_run(paths)
                    except ValueError as gate_exc:
                        raise ReviewGateError(str(gate_exc)) from gate_exc
                raise ReviewGateError(
                    f"无效的 Review 决策文件：{decision_path}；{strict_exc}；"
                    "请重新执行 prepare-review 并确认参考构图快照"
                ) from strict_exc
            else:
                raise
    except ReviewGateError:
        raise
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
        constraints = require_confirmed_constraints(constraints_path)
        if analysis is not None:
            validate_product_fidelity_constraints(analysis, constraints)
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewGateError(f"无效的产品保真约束文件：{constraints_path}；{exc}") from exc
    try:
        require_modern_reference_run(paths)
    except ValueError as exc:
        raise ReviewGateError(str(exc)) from exc
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
    elif product_type is ProductType.RING:
        if decision.confirmation_snapshot is None:
            raise ReviewGateError("戒指生成决策缺少完整产品确认快照")
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
        validate_analysis_ready_for_reference_selection(analysis)
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


def _confirmed_reference_snapshot(
    paths: RunPaths,
    decision: ReviewDecision,
) -> ReferenceCompositionSnapshot:
    snapshot, _selected_reference = _confirmed_reference_snapshot_data(paths, decision)
    return snapshot


def _confirmed_reference_snapshot_data(
    paths: RunPaths,
    decision: ReviewDecision,
) -> tuple[ReferenceCompositionSnapshot, dict[str, Any]]:
    if decision.action == "generate_multiple":
        raise ReviewGateError(
            "generate_multiple 仅保留历史读取，不允许记录新的参考快照决策"
        )
    if len(decision.selected_ranks) != 1:
        raise ReviewGateError("新快照 run 必须且只能确认一个 selected rank")
    rank = decision.selected_ranks[0]
    snapshots_data = read_json(
        paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    )
    if not isinstance(snapshots_data, list):
        raise ReviewGateError("候选参考构图快照必须是 JSON 列表")
    matches = [
        item
        for item in snapshots_data
        if isinstance(item, dict) and item.get("rank") == rank
    ]
    if len(matches) != 1:
        raise ReviewGateError(f"selected rank {rank} 必须对应唯一候选构图快照")
    try:
        snapshot = ReferenceCompositionSnapshot.from_dict(matches[0])
    except (TypeError, ValueError) as exc:
        raise ReviewGateError(f"selected rank {rank} 的候选构图快照无效：{exc}") from exc

    selected_data = read_json(paths.analysis_dir / "selected_references.json")
    if not isinstance(selected_data, list):
        raise ReviewGateError("selected_references.json 必须是 JSON 列表")
    selected_matches = [
        item
        for item in selected_data
        if isinstance(item, dict) and item.get("rank") == rank
    ]
    if len(selected_matches) != 1:
        raise ReviewGateError(f"selected rank {rank} 必须对应唯一参考图")
    selected = selected_matches[0]
    selected_reference = _required_selected_path(
        selected,
        "selected_reference",
        rank,
    )
    metadata = selected.get("metadata")
    if not isinstance(metadata, dict):
        raise ReviewGateError(f"selected rank {rank} 的 metadata 必须是 JSON 对象")
    source_value = (
        metadata.get("source_reference")
        or metadata.get("source_absolute_path")
        or metadata.get("absolute_path")
    )
    if not isinstance(source_value, str) or not source_value.strip():
        raise ReviewGateError(f"selected rank {rank} 缺少源参考图路径")
    source_reference = Path(source_value.strip())

    source_sha = _selected_sha256(selected, metadata, "source_sha256", rank)
    review_sha = _selected_sha256(selected, metadata, "review_sha256", rank)
    if not source_reference.is_file():
        raise ReviewGateError(f"selected rank {rank} 的源参考图路径不存在")
    if not selected_reference.is_file():
        raise ReviewGateError(f"selected rank {rank} 的审核参考图路径不存在")
    actual_source_sha = _file_sha256(source_reference)
    actual_review_sha = _file_sha256(selected_reference)
    if source_sha != actual_source_sha:
        raise ReviewGateError(f"selected rank {rank} 的 source_sha256 与源参考图不一致")
    if review_sha != actual_review_sha:
        raise ReviewGateError(f"selected rank {rank} 的 review_sha256 与审核参考图不一致")
    if source_sha != review_sha:
        raise ReviewGateError(f"selected rank {rank} 的 source_sha256 与 review_sha256 不一致")

    role_path = paths.analysis_dir / "output_role.json"
    role_data = read_json(role_path)
    if not isinstance(role_data, dict):
        raise ReviewGateError("analysis/output_role.json 必须是 JSON 对象")
    try:
        run_role = normalize_output_role(role_data.get("output_role"))
    except ValueError as exc:
        raise ReviewGateError(f"analysis/output_role.json 的 output_role 无效：{exc}") from exc
    if decision.output_role is None or decision.output_role is not run_role:
        raise ReviewGateError("decision output_role 与当前 run 的 output_role 不一致")
    try:
        validate_snapshot_binding(
            snapshot,
            reference_file=source_reference,
            output_role=decision.output_role,
            expected_rank=rank,
        )
    except ValueError as exc:
        if "composition_signature" in str(exc):
            raise ReviewGateError(
                "候选参考构图快照不可直接编辑；"
                "请修订语义源并重新执行 prepare-review"
            ) from exc
        raise ReviewGateError(str(exc)) from exc
    return snapshot, selected


def _validate_candidate_snapshot_draft(
    snapshot: ReferenceCompositionSnapshot,
    selected: dict[str, Any],
    analysis: ProductAnalysis,
) -> None:
    metadata = selected["metadata"]
    source_value = (
        metadata.get("source_reference")
        or metadata.get("source_absolute_path")
        or metadata.get("absolute_path")
    )
    row_data = dict(metadata)
    row_data["absolute_path"] = source_value
    row_data["file_exists"] = True
    try:
        scored = ScoredReference(
            row=ReferenceRow.from_dict(row_data),
            score=selected.get("score"),
            rank=selected.get("rank"),
            reason=selected.get("reason", []),
            risk=selected.get("risk", []),
            ignored_reference_jewelry=selected.get("ignored_reference_jewelry", []),
        )
        expected = build_candidate_snapshot(analysis, scored, snapshot.output_role)
    except (TypeError, ValueError) as exc:
        raise ReviewGateError(
            "selected 参考图语义字段无法重建候选快照，请重新执行 prepare-review；"
            f"{exc}"
        ) from exc
    actual_data = snapshot.to_dict()
    expected_data = expected.to_dict()
    for field_name, expected_value in expected_data.items():
        if actual_data[field_name] != expected_value:
            raise ReviewGateError(
                f"候选参考构图快照字段 {field_name} 不可直接编辑；"
                "请修订语义源并重新执行 prepare-review"
            )


def _required_selected_path(
    selected: dict[str, Any],
    field_name: str,
    rank: int,
) -> Path:
    value = selected.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ReviewGateError(f"selected rank {rank} 缺少参考图路径 {field_name}")
    return Path(value.strip())


def _selected_sha256(
    selected: dict[str, Any],
    metadata: dict[str, Any],
    field_name: str,
    rank: int,
) -> str:
    value = selected.get(field_name)
    metadata_value = metadata.get(field_name)
    if value != metadata_value:
        raise ReviewGateError(
            f"selected rank {rank} 的顶层与 metadata {field_name} 不一致"
        )
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReviewGateError(f"selected rank {rank} 的 {field_name} 必须是 64 位小写十六进制")
    return value


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _reject_legacy_generation_write(decision: ReviewDecision) -> None:
    if decision.action in _GENERATION_ACTIONS:
        raise ReviewGateError(
            "旧写入接口不得创建新的生成决策；请使用 write_review_bundle "
            "原子固化人工确认参考快照"
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
    label = f"{len(entries)} 文件"
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
    "_confirmed_reference_snapshot",
    "require_generation_decision",
    "validate_confirmed_analysis",
    "validate_decision_against_analysis",
    "write_analysis_and_review_decision",
    "write_review_bundle",
    "write_review_decision",
]
