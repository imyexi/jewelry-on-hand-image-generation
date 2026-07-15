from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow, ReviewDecision
from jewelry_on_hand.output_roles import OutputRole, require_scene_replacement_role
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.qc_review import write_qc_review_page
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    ReferenceCompositionSnapshot,
    load_reference_composition_snapshot,
    reference_composition_sha256,
)
from jewelry_on_hand.review_decision import require_generation_decision
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


SELECTED_REFERENCES_FILE = "selected_references.json"
DEFAULT_MODEL_NAME = "gpt_image_2"
FALLBACK_MODEL_NAME = "nano_banana_v2"
FALLBACK_AFTER_FAILED_QC_COUNT = 1
ASPECT_RATIO = "3:4"
RESOLUTION = "2K"
REFERENCE_STRUCTURE_FAILURES = frozenset(
    {
        "reference_framing_changed",
        "reference_pose_changed",
        "reference_person_changed",
        "reference_clothing_changed",
        "reference_background_changed",
        "reference_lighting_changed",
        "reference_jewelry_leakage",
        "replacement_target_changed",
        "target_product_duplicated",
    }
)
REFERENCE_STRUCTURE_RETRY_SUFFIX = (
    "这是当前参考底图唯一一次构图纠偏重跑。逐项锁定已确认快照，"
    "除原首饰替换区域外不得重绘、裁切、移动或重构任何画面元素。"
)


class GenerationError(RuntimeError):
    """生成流程无法安全继续时抛出。"""


@dataclass(frozen=True)
class _GenerationJob:
    rank: int
    prompt: str
    reference_path: Path
    generation_dir: Path
    model_name: str
    retry_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class _GenerationHistory:
    next_output_index: int
    failed_qc_count: int
    reference_structure_rejects: int = 0
    attempted_ranks: tuple[int, ...] = ()
    latest_critical_failures: tuple[str, ...] = ()
    latest_qc_status: str = ""


@dataclass(frozen=True)
class GenerationFailureHistory:
    reference_structure_rejects: int
    model_switch_failures: int


@dataclass(frozen=True)
class _AuditSource:
    source_path: Path
    copied_file: str
    sha256: str


def run_generation(
    paths: RunPaths,
    product_image: str | Path,
    prompts_by_rank: Mapping[int | str, str],
    helper_script: str | Path,
    wait: bool = True,
    *,
    reference_snapshot: ReferenceCompositionSnapshot | None = None,
    product_analysis_path: str | Path | None = None,
    fidelity_constraints_path: str | Path | None = None,
) -> list[Path]:
    decision = require_generation_decision(paths)
    if decision.action == "generate_multiple":
        raise GenerationError(
            "历史 generate_multiple run 不允许继续生成，请回到 prepare-review 重新确认。"
        )
    require_reference_retry_allowed(paths)

    product_path = Path(product_image)
    helper_path = Path(helper_script)
    analysis_path = Path(
        product_analysis_path or paths.analysis_dir / "product_analysis.json"
    )
    canonical_path = Path(
        fidelity_constraints_path
        or paths.analysis_dir / "product_fidelity_constraints.json"
    )
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    _ensure_original_audit_path(
        product_path,
        paths.input_dir / "product-on-hand.jpg",
        "产品图",
    )
    _ensure_original_audit_path(
        analysis_path,
        paths.analysis_dir / "product_analysis.json",
        "产品分析",
    )
    _ensure_original_audit_path(
        canonical_path,
        paths.analysis_dir / "product_fidelity_constraints.json",
        "产品保真约束",
    )
    _ensure_file(product_path, "产品图不存在，请回到 prepare-review 重新确认")
    _ensure_file(helper_path, "AIReiter helper 不存在")
    _ensure_file(analysis_path, "产品分析不存在，请回到 prepare-review 重新确认")
    _ensure_file(canonical_path, "产品保真约束不存在，请回到 prepare-review 重新确认")
    _ensure_file(snapshot_path, "确认快照不存在，请回到 prepare-review 重新确认")
    supplied_snapshot = reference_snapshot
    if supplied_snapshot is None:
        try:
            supplied_snapshot = load_reference_composition_snapshot(snapshot_path)
        except ValueError as exc:
            raise GenerationError(
                "历史 run 缺少可用确认快照，请回到 prepare-review 重新确认。"
            ) from exc
    confirmed_snapshot = _validate_confirmed_snapshot(
        decision,
        supplied_snapshot,
        snapshot_path,
    )
    _validate_run_role(paths, confirmed_snapshot)

    normalized_prompts = _normalize_prompts_by_rank(prompts_by_rank)
    references_by_rank = _load_references_by_rank(
        paths.analysis_dir / SELECTED_REFERENCES_FILE
    )
    try:
        product = ProductAnalysis.from_dict(read_json(analysis_path))
    except (OSError, TypeError, ValueError) as exc:
        raise GenerationError(f"生成前无法读取完整产品分析：{analysis_path}；{exc}") from exc
    if product.confirmed_product_type is ProductType.RING:
        expected_product_path = paths.input_dir / "product-on-hand.jpg"
        if product_path.resolve() != expected_product_path.resolve():
            raise GenerationError(
                "戒指生成只允许使用当前 run 的 input/product-on-hand.jpg 作为唯一产品身份图"
            )
    _require_ring_reference_top_three(paths, decision, references_by_rank)
    validate_necklace_reference_selection(
        paths,
        product,
        decision,
        references_by_rank=references_by_rank,
    )
    model_name = select_generation_model(paths)
    jobs = _build_generation_jobs(
        paths=paths,
        decision=decision,
        prompts_by_rank=normalized_prompts,
        references_by_rank=references_by_rank,
        model_name=model_name,
        product=product,
    )
    if len(jobs) != 1:
        raise GenerationError("新快照 run 必须且只能生成唯一 selected rank，请重新确认。")
    _validate_job_snapshot(
        jobs[0],
        references_by_rank[jobs[0].rank],
        confirmed_snapshot,
        decision,
    )
    audit_sources = _build_audit_sources(
        job=jobs[0],
        product_path=product_path,
        snapshot_path=snapshot_path,
        analysis_path=analysis_path,
        canonical_path=canonical_path,
    )
    for job in jobs:
        _ensure_generation_dir_available(job.generation_dir)

    staged: list[tuple[_GenerationJob, Path]] = []
    published: list[Path] = []
    try:
        for job in jobs:
            staged.append(
                (
                    job,
                    _stage_generation_inputs(
                        job,
                        audit_sources,
                        confirmed_snapshot,
                    ),
                )
            )
        for job, staging_dir in staged:
            if job.generation_dir.exists():
                job.generation_dir.rmdir()
            staging_dir.replace(job.generation_dir)
            published.append(job.generation_dir)
    except Exception as exc:
        for _job, staging_dir in staged:
            shutil.rmtree(staging_dir, ignore_errors=True)
        for generation_dir in published:
            shutil.rmtree(generation_dir, ignore_errors=True)
        if isinstance(exc, GenerationError):
            raise
        raise GenerationError(
            "generation 输入固化失败，未提交任何任务；请回到 prepare-review 重新确认。"
        ) from exc

    generation_dirs: list[Path] = []

    for job in jobs:
        generation_dir = job.generation_dir
        scene_copy = generation_dir / _scene_reference_name(job.reference_path)
        product_copy = generation_dir / _product_reference_name(product_path)

        task_id = _make_task_id(paths.root.name, job.rank)
        submit = _run_helper(
            _submit_command(
                helper_path,
                job.prompt,
                scene_copy,
                product_copy,
                task_id,
                job.model_name,
            ),
            stage="submit",
            rank=job.rank,
            generation_dir=generation_dir,
            output_path=generation_dir / "submit.json",
        )

        if wait:
            result = _run_helper(
                _wait_command(helper_path, _extract_task_id(submit)),
                stage="wait",
                rank=job.rank,
                generation_dir=generation_dir,
                output_path=generation_dir / "result.json",
            )
            _download_result_image(
                result,
                destination=generation_dir / "result.png",
                rank=job.rank,
                generation_dir=generation_dir,
            )
            write_qc_review_page(generation_dir)

        generation_dirs.append(generation_dir)

    return generation_dirs


def _validate_confirmed_snapshot(
    decision: ReviewDecision,
    supplied_snapshot: ReferenceCompositionSnapshot,
    snapshot_path: Path,
) -> ReferenceCompositionSnapshot:
    if not isinstance(supplied_snapshot, ReferenceCompositionSnapshot):
        raise GenerationError("reference_snapshot 必须是人工确认快照，请重新确认。")
    try:
        persisted_snapshot = load_reference_composition_snapshot(snapshot_path)
    except ValueError as exc:
        raise GenerationError(f"确认快照无效，请回到 prepare-review 重新确认：{exc}") from exc
    if persisted_snapshot != supplied_snapshot:
        raise GenerationError("传入快照与 review 确认快照不一致，请重新确认。")
    digest = reference_composition_sha256(persisted_snapshot)
    if decision.reference_snapshot_sha256 != digest:
        raise GenerationError("ReviewDecision 的快照摘要与确认快照不一致，请重新确认。")
    ranks = _generation_ranks(decision)
    if ranks != [persisted_snapshot.rank]:
        raise GenerationError("ReviewDecision 与确认快照的唯一 selected rank 不一致，请重新确认。")
    try:
        decision_role = require_scene_replacement_role(
            decision.output_role,
            stage="generation ReviewDecision",
        )
        snapshot_role = require_scene_replacement_role(
            persisted_snapshot.output_role,
            stage="generation 确认快照",
        )
    except ValueError as exc:
        raise GenerationError(f"生成角色无效，请回到 prepare-review 重新确认：{exc}") from exc
    if decision_role is not snapshot_role:
        raise GenerationError("ReviewDecision 与确认快照的角色不一致，请重新确认。")
    return persisted_snapshot


def _validate_job_snapshot(
    job: _GenerationJob,
    selected: Mapping[str, Any],
    snapshot: ReferenceCompositionSnapshot,
    decision: ReviewDecision,
) -> None:
    if job.rank != snapshot.rank:
        raise GenerationError("generation job 与确认快照 rank 不一致，请重新确认。")
    metadata = selected.get("metadata")
    if not isinstance(metadata, Mapping):
        raise GenerationError("selected 参考图缺少审核元数据，请回到 prepare-review 重新确认。")
    source_file_name = metadata.get("source_file_name") or metadata.get("文件名")
    if source_file_name != snapshot.reference_file:
        raise GenerationError("selected 参考图文件名与确认快照不一致，请重新确认。")
    actual_sha = _file_sha256(job.reference_path)
    declared_review_sha = selected.get("review_sha256") or metadata.get("review_sha256")
    if declared_review_sha != actual_sha or actual_sha != snapshot.reference_sha256:
        raise GenerationError("selected 参考图 SHA-256 与确认快照不一致，请重新确认。")
    if decision.output_role is not snapshot.output_role:
        raise GenerationError("输出角色与确认快照角色不一致，请重新确认。")


def _validate_run_role(
    paths: RunPaths,
    snapshot: ReferenceCompositionSnapshot,
) -> None:
    role_path = paths.analysis_dir / "output_role.json"
    _ensure_file(role_path, "输出角色文件不存在，请回到 prepare-review 重新确认")
    try:
        role_data = read_json(role_path)
    except (OSError, ValueError) as exc:
        raise GenerationError("输出角色文件无效，请回到 prepare-review 重新确认。") from exc
    if not isinstance(role_data, Mapping):
        raise GenerationError("输出角色文件必须是 JSON 对象，请重新确认。")
    try:
        run_role = require_scene_replacement_role(
            role_data.get("output_role"),
            stage="generation 当前 run",
        )
    except ValueError as exc:
        raise GenerationError(f"当前 run 角色无效，请重新确认：{exc}") from exc
    if run_role is not snapshot.output_role:
        raise GenerationError("当前 run 角色与确认快照角色不一致，请重新确认。")


def _build_audit_sources(
    *,
    job: _GenerationJob,
    product_path: Path,
    snapshot_path: Path,
    analysis_path: Path,
    canonical_path: Path,
) -> dict[str, _AuditSource]:
    sources = {
        "scene": _AuditSource(
            job.reference_path,
            _scene_reference_name(job.reference_path),
            _file_sha256(job.reference_path),
        ),
        "product": _AuditSource(
            product_path,
            _product_reference_name(product_path),
            _file_sha256(product_path),
        ),
        "snapshot": _AuditSource(
            snapshot_path,
            "reference-composition-snapshot.json",
            _file_sha256(snapshot_path),
        ),
        "analysis": _AuditSource(
            analysis_path,
            "product-analysis.json",
            _file_sha256(analysis_path),
        ),
        "canonical": _AuditSource(
            canonical_path,
            "product-fidelity-constraints.json",
            _file_sha256(canonical_path),
        ),
    }
    copied_names = [item.copied_file for item in sources.values()]
    if len(copied_names) != len(set(copied_names)):
        raise GenerationError("generation 输入复制文件名冲突，请重新确认。")
    return sources


def _stage_generation_inputs(
    job: _GenerationJob,
    sources: Mapping[str, _AuditSource],
    snapshot: ReferenceCompositionSnapshot,
) -> Path:
    staging_dir = job.generation_dir.parent / (
        f".{job.generation_dir.name}.staging-{secrets.token_hex(8)}"
    )
    try:
        staging_dir.mkdir(parents=False, exist_ok=False)
        for item in sources.values():
            _ensure_source_unchanged(item)
            destination = staging_dir / item.copied_file
            shutil.copy2(item.source_path, destination)
            _ensure_copied_digest(destination, item)
        (staging_dir / "model.txt").write_text(job.model_name, encoding="utf-8")
        (staging_dir / "prompt.txt").write_text(job.prompt, encoding="utf-8")
        (staging_dir / "reference-rank.txt").write_text(
            str(job.rank), encoding="utf-8"
        )
        if job.retry_failures:
            write_json(staging_dir / "retry-failures.json", list(job.retry_failures))
        write_json(
            staging_dir / "input-manifest.json",
            _input_manifest(sources, snapshot),
        )
        for item in sources.values():
            _ensure_source_unchanged(item)
            _ensure_copied_digest(staging_dir / item.copied_file, item)
        return staging_dir
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        if isinstance(exc, GenerationError):
            raise
        raise GenerationError(
            "generation 输入固化或 manifest 写入失败，未发布半成品；"
            "请回到 prepare-review 重新确认。"
        ) from exc


def _input_manifest(
    sources: Mapping[str, _AuditSource],
    snapshot: ReferenceCompositionSnapshot,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "output_role": snapshot.output_role.value,
        "reference_snapshot": _manifest_file(sources["snapshot"]),
        "product_analysis": _manifest_file(sources["analysis"]),
        "fidelity_constraints": _manifest_file(sources["canonical"]),
        "inputs": [
            _manifest_input(sources["scene"], order=1, role="scene_reference"),
            _manifest_input(sources["product"], order=2, role="product_identity"),
        ],
    }


def _manifest_file(source: _AuditSource) -> dict[str, str]:
    return {"copied_file": source.copied_file, "sha256": source.sha256}


def _manifest_input(
    source: _AuditSource,
    *,
    order: int,
    role: str,
) -> dict[str, Any]:
    return {
        "order": order,
        "role": role,
        "source_path": str(source.source_path.resolve()),
        "copied_file": source.copied_file,
        "sha256": source.sha256,
    }


def _ensure_source_unchanged(source: _AuditSource) -> None:
    if _file_sha256(source.source_path) != source.sha256:
        raise GenerationError(
            f"generation 输入源在固化期间被篡改：{source.source_path}；请重新确认。"
        )


def _ensure_copied_digest(destination: Path, source: _AuditSource) -> None:
    if _file_sha256(destination) != source.sha256:
        raise GenerationError(
            f"generation 输入复制后摘要不一致：{destination.name}；请重新确认。"
        )


def _ensure_original_audit_path(path: Path, expected: Path, label: str) -> None:
    if path.resolve() != expected.resolve():
        raise GenerationError(f"{label}必须使用人工确认链原始文件，请重新确认。")


def select_generation_model(paths: RunPaths) -> str:
    history = generation_failure_history(paths.generation_dir)
    if history.model_switch_failures > FALLBACK_AFTER_FAILED_QC_COUNT:
        return FALLBACK_MODEL_NAME
    return DEFAULT_MODEL_NAME


def generation_failure_history(
    generation_root: str | Path,
) -> GenerationFailureHistory:
    history = _generation_history(Path(generation_root))
    return GenerationFailureHistory(
        reference_structure_rejects=history.reference_structure_rejects,
        model_switch_failures=history.failed_qc_count,
    )


def reference_retry_suffix(history: GenerationFailureHistory) -> str:
    if not isinstance(history, GenerationFailureHistory):
        raise ValueError("history 必须是 GenerationFailureHistory")
    return (
        REFERENCE_STRUCTURE_RETRY_SUFFIX
        if history.reference_structure_rejects == 1
        else ""
    )


def require_reference_retry_allowed(paths: RunPaths) -> None:
    history = generation_failure_history(paths.generation_dir)
    if history.reference_structure_rejects >= 2:
        raise GenerationError(
            "当前参考图已连续两次发生结构严重错误，必须停用当前参考图并重新 "
            "prepare-review；不得自动改用未确认 rank。"
        )


def _generation_ranks(
    decision: ReviewDecision,
    *,
    product: ProductAnalysis | None = None,
    history: _GenerationHistory | None = None,
    available_ranks: tuple[int, ...] = (),
) -> list[int]:
    if decision.selected_ranks:
        _ensure_unique_ranks(decision.selected_ranks)
    if decision.action == "generate_rank_1":
        requested = [1]
    elif decision.selected_ranks:
        requested = list(decision.selected_ranks)
    else:
        requested = [1]

    if (
        product is None
        or product.confirmed_product_type is not ProductType.RING
        or history is None
        or history.failed_qc_count == 0
        or history.latest_qc_status == "pass"
        or len(requested) != 1
    ):
        return requested

    attempted = set(history.attempted_ranks)
    if history.failed_qc_count and not attempted:
        raise GenerationError("无法识别历史戒指生成使用的参考图 Rank，拒绝盲目重试")
    for rank in sorted(available_ranks):
        if rank not in attempted:
            return [rank]
    raise GenerationError("戒指参考图 Top 3 已全部尝试，请重新审核或补充素材")


def _ensure_unique_ranks(ranks: list[int]) -> None:
    seen: set[int] = set()
    for rank in ranks:
        if rank in seen:
            raise GenerationError(f"selected_ranks 中存在重复 rank {rank}")
        seen.add(rank)


def _generation_history(
    generation_root: Path,
    references_by_rank: Mapping[int, dict[str, Any]] | None = None,
) -> _GenerationHistory:
    max_history_index = 0
    failed_qc_count = 0
    reference_structure_rejects = 0
    if not generation_root.exists():
        return _GenerationHistory(
            next_output_index=1,
            failed_qc_count=0,
            reference_structure_rejects=0,
        )

    attempted_ranks: list[int] = []
    latest_critical_failures: tuple[str, ...] = ()
    latest_qc_status = ""

    for generation_dir in sorted(generation_root.iterdir()):
        if not generation_dir.is_dir() or not generation_dir.name.isdigit():
            continue
        if not any(generation_dir.iterdir()):
            continue

        qc_path = generation_dir / "qc.json"
        if not qc_path.is_file():
            raise GenerationError(f"生成目录缺少 qc.json，拒绝跳过历史结果: {generation_dir}")

        max_history_index = max(max_history_index, int(generation_dir.name))
        qc_status = _qc_status(qc_path)
        latest_qc_status = qc_status
        if qc_status != "pass":
            latest_critical_failures = _qc_critical_failures(qc_path)
            if REFERENCE_STRUCTURE_FAILURES.intersection(
                latest_critical_failures
            ):
                reference_structure_rejects += 1
            else:
                failed_qc_count += 1
        rank = _generation_reference_rank(generation_dir, references_by_rank)
        if rank is not None:
            attempted_ranks.append(rank)

    return _GenerationHistory(
        next_output_index=max_history_index + 1,
        failed_qc_count=failed_qc_count,
        reference_structure_rejects=reference_structure_rejects,
        attempted_ranks=tuple(attempted_ranks),
        latest_critical_failures=latest_critical_failures,
        latest_qc_status=latest_qc_status,
    )


def _qc_status(qc_path: Path) -> str:
    qc = read_json(qc_path)
    if not isinstance(qc, Mapping):
        raise GenerationError(f"qc.json 必须是 JSON 对象: {qc_path}")
    status = qc.get("status")
    if not isinstance(status, str) or not status.strip():
        return ""
    return status.strip().lower()


def _qc_critical_failures(qc_path: Path) -> tuple[str, ...]:
    qc = read_json(qc_path)
    if not isinstance(qc, Mapping):
        return ()
    failures = qc.get("critical_failures", [])
    if not isinstance(failures, list):
        return ()
    return tuple(
        failure.strip()
        for failure in failures
        if isinstance(failure, str) and failure.strip()
    )


def _generation_reference_rank(
    generation_dir: Path,
    references_by_rank: Mapping[int, dict[str, Any]] | None,
) -> int | None:
    rank_path = generation_dir / "reference-rank.txt"
    if rank_path.is_file():
        try:
            rank = int(rank_path.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
        return rank if rank >= 1 else None
    if not references_by_rank:
        return None
    audit_references = sorted(generation_dir.glob("scene-reference.*"))
    if not audit_references:
        audit_references = sorted(generation_dir.glob("hand-reference.*"))
    if len(audit_references) != 1:
        return None
    digest = _file_sha256(audit_references[0])
    for rank, reference in references_by_rank.items():
        path_value = reference.get("selected_reference")
        if isinstance(path_value, str) and Path(path_value).is_file():
            if _file_sha256(Path(path_value)) == digest:
                return rank
    return None


def _build_generation_jobs(
    *,
    paths: RunPaths,
    decision: ReviewDecision,
    prompts_by_rank: Mapping[int, str],
    references_by_rank: Mapping[int, dict[str, Any]],
    model_name: str,
    product: ProductAnalysis | None = None,
) -> list[_GenerationJob]:
    jobs: list[_GenerationJob] = []
    history = _generation_history(paths.generation_dir, references_by_rank)
    for output_index, rank in enumerate(
        _generation_ranks(
            decision,
            product=product,
            history=history,
            available_ranks=tuple(references_by_rank),
        ),
        start=history.next_output_index,
    ):
        prompt = _prompt_for_rank(prompts_by_rank, rank)
        reference_path = _reference_for_rank(references_by_rank, rank)
        retry_failures: tuple[str, ...] = ()
        if (
            product is not None
            and product.confirmed_product_type is ProductType.RING
            and history.failed_qc_count
            and history.latest_qc_status != "pass"
        ):
            retry_failures = history.latest_critical_failures
            correction = _ring_retry_correction(retry_failures)
            if correction:
                prompt = _build_ring_retry_prompt(
                    prompt,
                    correction,
                    reference_path.suffix,
                )
        retry_suffix = reference_retry_suffix(
            GenerationFailureHistory(
                reference_structure_rejects=(
                    history.reference_structure_rejects
                ),
                model_switch_failures=history.failed_qc_count,
            )
        )
        if retry_suffix:
            prompt = _append_reference_retry_suffix(prompt, retry_suffix)
        generation_dir = paths.generation_dir / f"{output_index:02d}"
        jobs.append(
            _GenerationJob(
                rank=rank,
                prompt=prompt,
                reference_path=reference_path,
                generation_dir=generation_dir,
                model_name=model_name,
                retry_failures=retry_failures,
            )
        )
    return jobs


def _append_reference_retry_suffix(prompt: str, suffix: str) -> str:
    if REFERENCE_STRUCTURE_RETRY_SUFFIX in prompt:
        raise GenerationError("基础 Prompt 不得预置参考结构纠偏后缀")
    return f"{prompt.rstrip()}\n\n{suffix}"


_RING_RETRY_CORRECTIONS = {
    "finger_position_mismatch": "上次指位错误；必须佩戴在确认的目标手指根部，其他手指不得戴戒指。",
    "hand_side_mismatch": "上次左右手错误；必须使用确认手和目标手指，不得镜像换手。",
    "centerpiece_mismatch": "上次主石错误；严格保持主石数量、形状、颜色、朝向和相对尺寸。",
    "ring_structure_mismatch": "上次结构错误；严格保持戒面、戒圈、开口端点和装饰排列，不得重设计。",
    "ring_count_mismatch": "上次数量错误；只允许一枚目标戒指，禁止任何额外首饰。",
    "ring_contact_error": "上次接触错误；戒圈必须连续环绕目标手指，背侧真实遮挡，不得悬浮或贴片。",
    "source_hand_leakage": "上次发生来源迁移；产品图只提供戒指身份，不得继承源手、皮肤、衣服或背景。",
    "source_person_region_migrated": "上次发生来源迁移；产品图只提供戒指身份，不得继承源手、皮肤、衣服或背景。",
    "finger_deformation": "上次手部变形；保持五指解剖正常，禁止多指、融指或断指。",
}


def _ring_retry_correction(failures: tuple[str, ...]) -> str:
    corrections = list(
        dict.fromkeys(
            _RING_RETRY_CORRECTIONS[failure]
            for failure in failures
            if failure in _RING_RETRY_CORRECTIONS
        )
    )
    if not corrections:
        return ""
    return "【本轮纠偏】" + "".join(corrections)


def _build_ring_retry_prompt(
    prompt: str,
    correction: str,
    reference_suffix: str,
) -> str:
    retry_prompt = f"{prompt}\n\n{correction}"
    if len(retry_prompt) <= 1200:
        return retry_prompt

    occlusion_start = retry_prompt.rfind("【遮挡与接触物理】")
    reference_start = retry_prompt.rfind(
        "【参考构图场景】",
        0,
        occlusion_start,
    )
    if reference_start >= 0 and occlusion_start >= 0:
        reference_section = retry_prompt[reference_start:occlusion_start]
        submitted_reference_name = f"scene-reference{reference_suffix or '.jpg'}"
        compacted_section = re.sub(
            r"(?m)^参考图文件：[^；\r\n]+；",
            f"参考图文件：{submitted_reference_name}；",
            reference_section,
            count=1,
        )
        compacted_section = re.sub(
            r"(?m)^输出用途：手部佩戴图[^\r\n]*$",
            "输出用途：手部佩戴图。深色背景；产品完整清晰；"
            "无文字/水印/logo/平台标识；佩戴在确认手指根部；接触和阴影真实。",
            compacted_section,
            count=1,
        )
        compacted_section = re.sub(
            r"(?m)^镜面构图：无，不要额外添加镜中反射手部。$",
            "镜面构图：无。",
            compacted_section,
            count=1,
        )
        retry_prompt = (
            retry_prompt[:reference_start]
            + compacted_section
            + retry_prompt[occlusion_start:]
        )
    if len(retry_prompt) > 1200:
        raise GenerationError(
            f"戒指重试 Prompt 长度为 {len(retry_prompt)}，超过 1200 字上限"
        )
    return retry_prompt


def _normalize_prompts_by_rank(prompts_by_rank: Mapping[int | str, str]) -> dict[int, str]:
    normalized: dict[int, str] = {}
    for raw_rank, prompt in prompts_by_rank.items():
        rank = _normalize_rank(raw_rank, "prompts_by_rank")
        if rank in normalized:
            raise GenerationError(f"prompts_by_rank 中存在重复 rank {rank}")
        normalized[rank] = prompt
    return normalized


def _normalize_rank(value: int | str, source: str) -> int:
    if isinstance(value, bool):
        raise GenerationError(f"{source} 中存在无效 rank: {value!r}")
    if isinstance(value, int):
        rank = value
    elif isinstance(value, str):
        text = value.strip()
        if not text.isdigit():
            raise GenerationError(f"{source} 中存在无效 rank: {value!r}")
        rank = int(text)
    else:
        raise GenerationError(f"{source} 中存在无效 rank: {value!r}")
    if rank < 1:
        raise GenerationError(f"{source} 中存在无效 rank: {value!r}")
    return rank


def _load_references_by_rank(path: Path) -> dict[int, dict[str, Any]]:
    _ensure_file(path, "缺少 selected_references.json")
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"{path} 必须是列表")

    references: dict[int, dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"{path} 中的参考图条目必须是对象")
        rank = _rank_from_reference(item, path)
        if rank in references:
            raise GenerationError(f"{path} 中存在重复 rank {rank}")
        references[rank] = item
    return references


def _rank_from_reference(item: dict[str, Any], path: Path) -> int:
    rank = item.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise ValueError(f"{path} 中存在无效 rank: {rank!r}")
    return rank


def _require_ring_reference_top_three(
    paths: RunPaths,
    decision: ReviewDecision,
    references_by_rank: Mapping[int, dict[str, Any]],
) -> None:
    snapshot = decision.confirmation_snapshot
    if snapshot is None or snapshot.confirmed_product_type is not ProductType.RING:
        return

    required_ranks = {1, 2, 3}
    actual_ranks = set(references_by_rank)
    if actual_ranks != required_ranks:
        details: list[str] = []
        missing = sorted(required_ranks - actual_ranks)
        extra = sorted(actual_ranks - required_ranks)
        if missing:
            details.append("缺少 rank " + "、".join(str(rank) for rank in missing))
        if extra:
            details.append("多出 rank " + "、".join(str(rank) for rank in extra))
        raise GenerationError(
            "戒指生成必须恰好具备 rank 1、2、3 三张合格 Top 3 参考图；"
            + "；".join(details)
        )

    analysis_path = paths.analysis_dir / "product_analysis.json"
    try:
        product = ProductAnalysis.from_dict(read_json(analysis_path))
    except (OSError, TypeError, ValueError) as exc:
        raise GenerationError(f"戒指生成前无法读取完整产品分析：{analysis_path}；{exc}") from exc

    policy = get_category_policy(ProductType.RING)
    source_paths: dict[str, int] = {}
    review_paths: dict[str, int] = {}
    content_digests: dict[str, int] = {}
    review_root = paths.review_dir.resolve()
    for rank in sorted(required_ranks):
        reference = references_by_rank[rank]
        review_value = reference.get("selected_reference")
        if not isinstance(review_value, str) or not review_value.strip():
            raise GenerationError(f"戒指 Top 3 的 rank {rank} 缺少 review 副本路径")
        review_path = Path(review_value).resolve()
        try:
            review_path.relative_to(review_root)
        except ValueError as exc:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} review 副本必须位于当前 run 的 review_dir："
                f"{review_root}；实际为 {review_path}"
            ) from exc
        if not review_path.is_file():
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} review 副本不存在：{review_path}"
            )
        review_identity = str(review_path.resolve()).casefold()
        if review_identity in review_paths:
            raise GenerationError(
                "戒指 Top 3 的 review 副本路径重复："
                f"rank {review_paths[review_identity]} 与 rank {rank}"
            )
        review_paths[review_identity] = rank

        metadata = reference.get("metadata")
        if not isinstance(metadata, dict) or not metadata:
            raise GenerationError(f"戒指 Top 3 的 rank {rank} 缺少完整 metadata")

        source_values = {
            field_name: _required_ring_metadata_string(metadata, rank, field_name)
            for field_name in (
                "source_reference",
                "source_absolute_path",
                "absolute_path",
            )
        }
        source_path = Path(source_values["source_reference"]).resolve()
        source_identity = str(source_path).casefold()
        for field_name in ("source_absolute_path", "absolute_path"):
            if str(Path(source_values[field_name]).resolve()).casefold() != source_identity:
                raise GenerationError(
                    f"戒指 Top 3 的 rank {rank} metadata 中 {field_name} "
                    "与 source_reference 冲突"
                )
        if not source_path.is_file():
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 指向的源文件不存在：{source_path}"
            )
        if metadata.get("file_exists") is not True:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 的 file_exists 必须为 true"
            )
        recorded_source_sha256 = _required_ring_metadata_string(
            metadata, rank, "source_sha256"
        )
        recorded_review_sha256 = _required_ring_metadata_string(
            metadata, rank, "review_sha256"
        )
        actual_source_sha256 = _file_sha256(source_path)
        actual_review_sha256 = _file_sha256(review_path)
        if recorded_source_sha256 != actual_source_sha256:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} 源图 SHA-256 与审核记录不一致"
            )
        if recorded_review_sha256 != actual_review_sha256:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} review 副本 SHA-256 与审核记录不一致，副本可能被篡改"
            )
        if actual_source_sha256 != actual_review_sha256:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} review 副本内容与审核时源图不一致"
            )
        if actual_source_sha256 in content_digests:
            raise GenerationError(
                "戒指 Top 3 的内容摘要重复："
                f"rank {content_digests[actual_source_sha256]} 与 rank {rank}"
            )
        content_digests[actual_source_sha256] = rank

        source_relative_path = _required_ring_metadata_string(
            metadata, rank, "source_relative_path"
        )
        relative_path = _required_ring_metadata_string(metadata, rank, "relative_path")
        if source_relative_path != relative_path:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 中 "
                "source_relative_path 与 relative_path 冲突"
            )
        relative_name = Path(source_relative_path.replace("\\", "/")).name
        if relative_name.casefold() != source_path.name.casefold():
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 中 "
                "source_relative_path/relative_path 与源文件名冲突"
            )

        source_file_name = _required_ring_metadata_string(
            metadata, rank, "source_file_name"
        )
        file_name = _required_ring_metadata_string(metadata, rank, "file_name")
        if source_file_name != file_name:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 中 "
                "source_file_name 与 file_name 冲突"
            )
        if source_file_name.casefold() != source_path.name.casefold():
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 中 "
                "source_file_name/file_name 与源文件名冲突"
            )

        if source_identity in source_paths:
            raise GenerationError(
                "戒指 Top 3 的源图重复："
                f"rank {source_paths[source_identity]} 与 rank {rank}"
            )
        source_paths[source_identity] = rank

        row_data = dict(metadata)
        try:
            row = ReferenceRow.from_dict(row_data)
        except (TypeError, ValueError) as exc:
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 无法重建 ReferenceRow：{exc}"
            ) from exc
        adaptation = policy.evaluate_reference(product, row)
        if not adaptation.eligible:
            risks = "；".join(adaptation.risks) or "不满足戒指参考图策略"
            raise GenerationError(
                f"戒指 Top 3 的 rank {rank} metadata 不合格：{risks}"
            )


def validate_necklace_reference_selection(
    paths: RunPaths,
    product: ProductAnalysis,
    decision: ReviewDecision,
    *,
    references_by_rank: Mapping[int, dict[str, Any]] | None = None,
) -> None:
    if product.confirmed_product_type not in {
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
    }:
        return
    if decision.output_role is OutputRole.HERO:
        return
    if references_by_rank is None:
        references_by_rank = _load_references_by_rank(
            paths.analysis_dir / SELECTED_REFERENCES_FILE
        )

    review_root = paths.review_dir.resolve()
    policy = get_category_policy(product.confirmed_product_type)
    for rank, reference in sorted(references_by_rank.items()):
        review_value = reference.get("selected_reference")
        if not isinstance(review_value, str) or not review_value.strip():
            raise GenerationError(f"项链参考图 rank {rank} 缺少 review 副本路径")
        review_path = Path(review_value).resolve()
        try:
            review_path.relative_to(review_root)
        except ValueError as exc:
            raise GenerationError(
                f"项链参考图 rank {rank} 必须位于当前 run 的 review_dir："
                f"{review_root}；实际为 {review_path}"
            ) from exc
        if not review_path.is_file():
            raise GenerationError(f"项链参考图 rank {rank} 的 review 副本不存在：{review_path}")

        metadata = reference.get("metadata")
        if not isinstance(metadata, dict) or not metadata:
            raise GenerationError(f"项链参考图 rank {rank} 缺少审核时 metadata")
        recorded_source_sha256 = _required_reference_metadata_string(
            metadata,
            rank,
            "source_sha256",
            "项链",
        )
        recorded_review_sha256 = _required_reference_metadata_string(
            metadata,
            rank,
            "review_sha256",
            "项链",
        )
        actual_review_sha256 = _file_sha256(review_path)
        if recorded_review_sha256 != actual_review_sha256:
            raise GenerationError(
                f"项链参考图 rank {rank} 的 review 副本 SHA-256 与审核时摘要不一致"
            )
        if recorded_source_sha256 != actual_review_sha256:
            raise GenerationError(
                f"项链参考图 rank {rank} 的 review 副本内容与审核时源图摘要不一致"
            )

        row_data = dict(metadata)
        row_data["absolute_path"] = str(review_path)
        row_data["file_exists"] = True
        try:
            row = ReferenceRow.from_dict(row_data)
        except (TypeError, ValueError) as exc:
            raise GenerationError(
                f"项链参考图 rank {rank} 的审核 metadata 无法重建 ReferenceRow：{exc}"
            ) from exc
        adaptation = policy.evaluate_reference(product, row)
        if not adaptation.eligible:
            risks = "；".join(adaptation.risks) or "不满足最终项链参考图策略"
            raise GenerationError(
                f"项链参考图 rank {rank} 与最终品类、展示模式、长度、裁切或手持策略不兼容："
                f"{risks}"
            )


def _required_reference_metadata_string(
    metadata: Mapping[str, Any],
    rank: int,
    field_name: str,
    label: str,
) -> str:
    value = metadata.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(
            f"{label}参考图 rank {rank} 的 metadata 缺少关键字段 {field_name}"
        )
    return value.strip()


def _required_ring_metadata_string(
    metadata: Mapping[str, Any],
    rank: int,
    field_name: str,
) -> str:
    value = metadata.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(
            f"戒指 Top 3 的 rank {rank} metadata 缺少关键字段 {field_name}"
        )
    return value.strip()


def _file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise GenerationError(
            f"无法读取 generation 输入文件：{path}；请重新确认。"
        ) from exc


def _prompt_for_rank(prompts_by_rank: Mapping[int, str], rank: int) -> str:
    try:
        prompt = prompts_by_rank[rank]
    except KeyError as exc:
        raise KeyError(f"缺少 rank {rank} 的 prompt") from exc
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"rank {rank} 的 prompt 不能为空")
    return prompt


def _reference_for_rank(
    references_by_rank: Mapping[int, dict[str, Any]],
    rank: int,
) -> Path:
    try:
        reference = references_by_rank[rank]
    except KeyError as exc:
        raise KeyError(f"缺少 rank {rank} 的 selected_reference") from exc

    reference_path = reference.get("selected_reference")
    if not isinstance(reference_path, str) or not reference_path.strip():
        raise ValueError(f"rank {rank} 的 selected_reference 不能为空")
    path = Path(reference_path)
    _ensure_file(path, "参考图不存在")
    return path


def _ensure_generation_dir_available(generation_dir: Path) -> None:
    if generation_dir.exists() and any(generation_dir.iterdir()):
        raise GenerationError(f"生成目录已存在且非空，拒绝覆盖: {generation_dir}")
    probe_dir = generation_dir if generation_dir.exists() else generation_dir.parent
    try:
        _ensure_writable_probe(probe_dir)
    except OSError as exc:
        raise GenerationError(
            f"生成目录写入预检失败: {generation_dir}；探针目录={probe_dir}"
        ) from exc


def _ensure_writable_probe(directory: Path) -> None:
    probe = directory / f".write-test-{secrets.token_hex(8)}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        raise


def _scene_reference_name(reference_path: Path) -> str:
    suffix = reference_path.suffix or ".jpg"
    return f"scene-reference{suffix}"


def _product_reference_name(product_path: Path) -> str:
    suffix = product_path.suffix or ".jpg"
    return f"product-reference{suffix}"


def _make_task_id(run_id: str, rank: int) -> str:
    return f"{run_id}-rank-{rank:02d}-{secrets.token_hex(4)}"


def _submit_command(
    helper_path: Path,
    prompt: str,
    reference_path: Path,
    product_path: Path,
    task_id: str,
    model_name: str,
) -> list[str]:
    return [
        sys.executable,
        "-X",
        "utf8",
        str(helper_path),
        "submit",
        "--model",
        model_name,
        "--prompt",
        prompt,
        "--aspect-ratio",
        ASPECT_RATIO,
        "--resolution",
        RESOLUTION,
        "--task-id",
        task_id,
        "--image",
        str(reference_path),
        "--image",
        str(product_path),
    ]


def _wait_command(helper_path: Path, task_id: str) -> list[str]:
    return [
        sys.executable,
        "-X",
        "utf8",
        str(helper_path),
        "wait",
        "--task-id",
        task_id,
    ]


def _run_helper(
    command: list[str],
    *,
    stage: str,
    rank: int,
    generation_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=False,
        check=False,
    )
    returncode = int(getattr(completed, "returncode", 0) or 0)
    raw_stdout = getattr(completed, "stdout", "")
    stderr = _decode_helper_diagnostic(getattr(completed, "stderr", ""))

    try:
        stdout = _decode_helper_protocol(raw_stdout)
    except UnicodeDecodeError:
        raise GenerationError(
            _helper_error_message(
                stage=stage,
                rank=rank,
                returncode=returncode,
                generation_dir=generation_dir,
                command=command,
                stdout=_decode_helper_diagnostic(raw_stdout),
                stderr=stderr,
                reason="AIReiter helper stdout 不是有效 UTF-8",
            )
        ) from None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GenerationError(
            _helper_error_message(
                stage=stage,
                rank=rank,
                returncode=returncode,
                generation_dir=generation_dir,
                command=command,
                stdout=stdout,
                stderr=stderr,
                reason="AIReiter helper 返回非 JSON",
            )
        ) from exc

    write_json(output_path, data)
    if not isinstance(data, dict):
        raise GenerationError(
            _helper_error_message(
                stage=stage,
                rank=rank,
                returncode=returncode,
                generation_dir=generation_dir,
                command=command,
                stdout=stdout,
                stderr=stderr,
                reason="AIReiter helper 返回 JSON 对象以外的内容",
            )
        )

    if returncode != 0:
        raise GenerationError(
            _helper_error_message(
                stage=stage,
                rank=rank,
                returncode=returncode,
                generation_dir=generation_dir,
                command=command,
                stdout=stdout,
                stderr=stderr,
                reason="AIReiter helper 非 0 退出",
            )
        )
    return data


def _decode_helper_protocol(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    return str(value or "")


def _decode_helper_diagnostic(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return str(value or "")


def _download_result_image(
    result: Mapping[str, Any],
    *,
    destination: Path,
    rank: int,
    generation_dir: Path,
) -> None:
    url = _extract_result_image_url(result)
    content = b""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                content = response.read()
            if content:
                break
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(2 ** attempt)
    if not content and last_error is not None:
        raise GenerationError(
            f"下载 result.png 失败；rank {rank}；url={url}；产物目录={generation_dir}"
        ) from last_error
    if not content:
        raise GenerationError(
            f"下载 result.png 失败；rank {rank}；url={url}；响应内容为空；产物目录={generation_dir}"
        )
    destination.write_bytes(content)


def _extract_result_image_url(result: Mapping[str, Any]) -> str:
    data = result.get("data")
    outputs: Any = None
    if isinstance(data, Mapping):
        outputs = data.get("output") or data.get("outputs")
    if outputs is None:
        outputs = result.get("output") or result.get("outputs")

    for output in _iter_outputs(outputs):
        if isinstance(output, Mapping):
            url = output.get("url") or output.get("image_url")
        else:
            url = output
        if isinstance(url, str) and url.strip():
            return url.strip()
    raise GenerationError("result.json 缺少 data.output[].url，无法下载 result.png")


def _iter_outputs(outputs: Any) -> list[Any]:
    if isinstance(outputs, list):
        return outputs
    if isinstance(outputs, tuple):
        return list(outputs)
    if isinstance(outputs, Mapping) or isinstance(outputs, str):
        return [outputs]
    return []


def _helper_error_message(
    *,
    stage: str,
    rank: int,
    returncode: int,
    generation_dir: Path,
    command: list[str],
    stdout: str,
    stderr: str,
    reason: str,
) -> str:
    return (
        f"{reason}；阶段={stage}；rank {rank}；returncode={returncode}；"
        f"产物目录={generation_dir}；命令={_command_summary(command)}；"
        f"stdout={_short_text(stdout)}；stderr={_short_text(stderr)}"
    )


def _command_summary(command: list[str]) -> str:
    summary: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            skip_next = False
            continue
        if item == "--prompt":
            summary.extend([item, "<prompt>"])
            skip_next = True
        else:
            summary.append(item)
    return " ".join(summary)


def _short_text(value: str, limit: int = 500) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _extract_task_id(submit: Mapping[str, Any]) -> str:
    data = submit.get("data")
    if isinstance(data, Mapping):
        task_id = data.get("out_task_id") or data.get("task_id")
    else:
        task_id = submit.get("out_task_id") or submit.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise GenerationError("submit.json 缺少 out_task_id")
    return task_id.strip()


def _ensure_file(path: Path, message: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{message}: {path}")


__all__ = [
    "GenerationFailureHistory",
    "GenerationError",
    "REFERENCE_STRUCTURE_FAILURES",
    "REFERENCE_STRUCTURE_RETRY_SUFFIX",
    "generation_failure_history",
    "reference_retry_suffix",
    "require_reference_retry_allowed",
    "run_generation",
    "select_generation_model",
    "validate_necklace_reference_selection",
]
