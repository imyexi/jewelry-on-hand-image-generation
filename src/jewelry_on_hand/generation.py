from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jewelry_on_hand.models import ReviewDecision
from jewelry_on_hand.review_decision import require_generation_decision
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


SELECTED_REFERENCES_FILE = "selected_references.json"
DEFAULT_MODEL_NAME = "gpt_image_2"
FALLBACK_MODEL_NAME = "nano_banana_v2"
FALLBACK_AFTER_FAILED_QC_COUNT = 1
ASPECT_RATIO = "3:4"
RESOLUTION = "2K"


class GenerationError(RuntimeError):
    """生成流程无法安全继续时抛出。"""


@dataclass(frozen=True)
class _GenerationJob:
    rank: int
    prompt: str
    reference_path: Path
    generation_dir: Path
    model_name: str


@dataclass(frozen=True)
class _GenerationHistory:
    next_output_index: int
    failed_qc_count: int


def run_generation(
    paths: RunPaths,
    product_image: str | Path,
    prompts_by_rank: Mapping[int | str, str],
    helper_script: str | Path,
    wait: bool = True,
) -> list[Path]:
    decision = require_generation_decision(paths)
    if decision.action == "manual_reference":
        raise GenerationError("manual_reference 第一版暂不支持自动生成，请改用已选 rank 决策。")

    product_path = Path(product_image)
    helper_path = Path(helper_script)
    _ensure_file(product_path, "产品图不存在")
    _ensure_file(helper_path, "AIReiter helper 不存在")

    normalized_prompts = _normalize_prompts_by_rank(prompts_by_rank)
    references_by_rank = _load_references_by_rank(
        paths.analysis_dir / SELECTED_REFERENCES_FILE
    )
    model_name = select_generation_model(paths)
    jobs = _build_generation_jobs(
        paths=paths,
        decision=decision,
        prompts_by_rank=normalized_prompts,
        references_by_rank=references_by_rank,
        model_name=model_name,
    )
    generation_dirs: list[Path] = []

    for job in jobs:
        generation_dir = _prepare_generation_dir(job.generation_dir)

        (generation_dir / "model.txt").write_text(job.model_name, encoding="utf-8")
        (generation_dir / "prompt.txt").write_text(job.prompt, encoding="utf-8")
        shutil.copy2(
            job.reference_path,
            _reference_destination(generation_dir, job.reference_path),
        )

        task_id = _make_task_id(paths.root.name, job.rank)
        submit = _run_helper(
            _submit_command(
                helper_path,
                job.prompt,
                job.reference_path,
                product_path,
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

        generation_dirs.append(generation_dir)

    return generation_dirs


def select_generation_model(paths: RunPaths) -> str:
    failed_qc_count = _generation_history(paths.generation_dir).failed_qc_count
    if failed_qc_count > FALLBACK_AFTER_FAILED_QC_COUNT:
        return FALLBACK_MODEL_NAME
    return DEFAULT_MODEL_NAME


def _generation_ranks(decision: ReviewDecision) -> list[int]:
    if decision.selected_ranks:
        _ensure_unique_ranks(decision.selected_ranks)
    if decision.action == "generate_rank_1":
        return [1]
    if decision.selected_ranks:
        return list(decision.selected_ranks)
    return [1]


def _ensure_unique_ranks(ranks: list[int]) -> None:
    seen: set[int] = set()
    for rank in ranks:
        if rank in seen:
            raise GenerationError(f"selected_ranks 中存在重复 rank {rank}")
        seen.add(rank)


def _generation_history(generation_root: Path) -> _GenerationHistory:
    max_history_index = 0
    failed_qc_count = 0
    if not generation_root.exists():
        return _GenerationHistory(next_output_index=1, failed_qc_count=0)

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
        if qc_status != "pass":
            failed_qc_count += 1

    return _GenerationHistory(
        next_output_index=max_history_index + 1,
        failed_qc_count=failed_qc_count,
    )


def _qc_status(qc_path: Path) -> str:
    qc = read_json(qc_path)
    if not isinstance(qc, Mapping):
        raise GenerationError(f"qc.json 必须是 JSON 对象: {qc_path}")
    status = qc.get("status")
    if not isinstance(status, str) or not status.strip():
        return ""
    return status.strip().lower()


def _build_generation_jobs(
    *,
    paths: RunPaths,
    decision: ReviewDecision,
    prompts_by_rank: Mapping[int, str],
    references_by_rank: Mapping[int, dict[str, Any]],
    model_name: str,
) -> list[_GenerationJob]:
    jobs: list[_GenerationJob] = []
    history = _generation_history(paths.generation_dir)
    for output_index, rank in enumerate(
        _generation_ranks(decision),
        start=history.next_output_index,
    ):
        prompt = _prompt_for_rank(prompts_by_rank, rank)
        reference_path = _reference_for_rank(references_by_rank, rank)
        generation_dir = paths.generation_dir / f"{output_index:02d}"
        _ensure_generation_dir_available(generation_dir)
        jobs.append(
            _GenerationJob(
                rank=rank,
                prompt=prompt,
                reference_path=reference_path,
                generation_dir=generation_dir,
                model_name=model_name,
            )
        )
    return jobs


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


def _prepare_generation_dir(generation_dir: Path) -> Path:
    _ensure_generation_dir_available(generation_dir)
    generation_dir.mkdir(parents=True, exist_ok=True)
    return generation_dir


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


def _reference_destination(generation_dir: Path, reference_path: Path) -> Path:
    suffix = reference_path.suffix or ".jpg"
    return generation_dir / f"hand-reference{suffix}"


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
        text=True,
        check=False,
    )
    returncode = int(getattr(completed, "returncode", 0) or 0)
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")

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


def _download_result_image(
    result: Mapping[str, Any],
    *,
    destination: Path,
    rank: int,
    generation_dir: Path,
) -> None:
    url = _extract_result_image_url(result)
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read()
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise GenerationError(
            f"下载 result.png 失败；rank {rank}；url={url}；产物目录={generation_dir}"
        ) from exc
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


__all__ = ["GenerationError", "run_generation", "select_generation_model"]
