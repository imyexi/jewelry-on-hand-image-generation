from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_prompt_contract import validate_prompt  # noqa: E402
from validate_qc_record import validate_qc  # noqa: E402

REQUIRED_GENERATION_FILES = ("model.txt", "prompt.txt", "submit.json", "result.json", "result.png", "qc.json")
PRODUCT_TYPE_TERMS = ("手链", "手串", "bracelet", "hand-string", "hand string")
GENERATE_ACTIONS = {"generate_rank_1", "generate_selected", "generate_multiple"}
BLOCKED_ACTIONS = {"rerank", "manual_reference"}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _is_json_int(value: Any) -> bool:
    return type(value) is int


def _is_bracelet_product(value: Any) -> bool:
    text = str(value or "").lower()
    return any(term.lower() in text for term in PRODUCT_TYPE_TERMS)


def _resolve_artifact_path(raw_path: str, run_root: Path, base_dir: Path | None = None) -> Path:
    artifact_path = Path(raw_path)
    if artifact_path.is_absolute():
        return artifact_path
    run_relative = (run_root / artifact_path).resolve()
    if run_relative.is_file():
        return run_relative
    if base_dir is not None:
        return (base_dir / artifact_path).resolve()
    return run_relative


def _validate_product_analysis(path: Path) -> list[str]:
    data = _load_json(path)
    if not isinstance(data, dict):
        return ["analysis/product_analysis.json must contain a JSON object"]
    if not _is_bracelet_product(data.get("product_type")):
        return ["analysis/product_analysis.json product_type must be bracelet/hand-string"]
    return []


def _validate_selected_references(path: Path, run_root: Path) -> tuple[list[str], set[int]]:
    data = _load_json(path)
    errors: list[str] = []
    ranks: set[int] = set()
    if not isinstance(data, list):
        return ["analysis/selected_references.json must contain a list"], ranks
    if len(data) < 3:
        errors.append("analysis/selected_references.json must contain Top 3 references")
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            errors.append(f"selected_references[{index}] must be an object")
            continue
        rank = item.get("rank")
        if not _is_json_int(rank) or rank < 1 or rank > 3:
            errors.append(f"selected_references[{index}].rank must be an integer from 1 to 3")
        elif rank in ranks:
            errors.append(f"selected_references rank {rank} is duplicated")
        else:
            ranks.add(rank)
        reference = item.get("selected_reference")
        if not isinstance(reference, str) or not reference.strip():
            errors.append(f"selected_references[{index}].selected_reference must be a non-empty string")
        else:
            resolved_reference = _resolve_artifact_path(reference, run_root, path.parent)
            if not resolved_reference.is_file():
                errors.append(f"selected reference file not found: {reference}")
        if "score" not in item:
            errors.append(f"selected_references[{index}].score is required")
    for required_rank in (1, 2, 3):
        if required_rank not in ranks:
            errors.append(f"analysis/selected_references.json missing rank {required_rank}")
    return errors, ranks


def _validate_review_decision(path: Path, selected_ranks_available: set[int]) -> tuple[list[str], list[int]]:
    data = _load_json(path)
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["review/review_decision.json must contain a JSON object"], []
    action = data.get("action")
    if action in BLOCKED_ACTIONS:
        errors.append(f"review_decision action {action} must not enter generation")
    if action not in GENERATE_ACTIONS:
        errors.append("review_decision action must be generate_rank_1/generate_selected/generate_multiple")

    selected = data.get("selected_ranks")
    if action == "generate_rank_1" and selected in (None, []):
        selected = [1]
    if not isinstance(selected, list) or not selected:
        errors.append("review_decision selected_ranks must be a non-empty list")
        return errors, []
    if not all(_is_json_int(rank) for rank in selected):
        errors.append("review_decision selected_ranks must contain integers")
        return errors, []

    selected_ints = list(selected)
    if len(set(selected_ints)) != len(selected_ints):
        errors.append("review_decision selected_ranks must not contain duplicates")
    invalid = [rank for rank in selected_ints if rank < 1 or rank > 3]
    if invalid:
        errors.append(f"review_decision selected_ranks out of range: {invalid}")
    missing = [rank for rank in selected_ints if rank not in selected_ranks_available]
    if missing:
        errors.append(f"review_decision selected ranks not present in selected_references.json: {missing}")
    if action == "generate_rank_1" and selected_ints != [1]:
        errors.append("generate_rank_1 must select rank 1 only")
    if action == "generate_selected" and len(selected_ints) != 1:
        errors.append("generate_selected must select exactly one rank")
    if action == "generate_multiple" and len(selected_ints) < 2:
        errors.append("generate_multiple must select at least two ranks")
    return errors, selected_ints


def _has_hand_reference(generation_dir: Path) -> bool:
    return any(path.is_file() and path.name.startswith("hand-reference") for path in generation_dir.iterdir())


def _validate_generation_dir(generation_dir: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_GENERATION_FILES:
        if not (generation_dir / name).is_file():
            errors.append(f"missing generation/{generation_dir.name}/{name}")
    if generation_dir.is_dir() and not _has_hand_reference(generation_dir):
        errors.append(f"missing generation/{generation_dir.name}/hand-reference.*")

    model_path = generation_dir / "model.txt"
    if model_path.is_file():
        model_name = model_path.read_text(encoding="utf-8").strip()
        if model_name not in {"gpt_image_2", "nano_banana_v2"}:
            errors.append(f"generation/{generation_dir.name}/model.txt has unsupported model: {model_name}")

    prompt_path = generation_dir / "prompt.txt"
    if prompt_path.is_file():
        for error in validate_prompt(prompt_path):
            errors.append(f"generation/{generation_dir.name}/prompt.txt: {error}")

    qc_path = generation_dir / "qc.json"
    if qc_path.is_file():
        for error in validate_qc(qc_path):
            errors.append(f"generation/{generation_dir.name}/qc.json: {error}")

    result_json = generation_dir / "result.json"
    if result_json.is_file():
        data = _load_json(result_json)
        status = None
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            status = data["data"].get("status")
        if status != "completed":
            errors.append(f"generation/{generation_dir.name}/result.json status is not completed")
    return errors


def _qc_status_for_generation(generation_dir: Path) -> str | None:
    qc_path = generation_dir / "qc.json"
    if not qc_path.is_file():
        return None
    data = _load_json(qc_path)
    if not isinstance(data, dict):
        return None
    return data.get("status") if isinstance(data.get("status"), str) else None


def _flatten_entries(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("accepted", "accepted_outputs", "outputs", "images", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _validate_final_summary(summary_path: Path, run_root: Path) -> list[str]:
    data = _load_json(summary_path)
    entries = _flatten_entries(data)
    errors: list[str] = []
    if not entries:
        return [f"final summary has no accepted entries: {summary_path}"]
    for index, entry in enumerate(entries, start=1):
        entry_status = entry.get("status") if isinstance(entry, dict) else None
        if entry_status is not None and entry_status != "pass":
            errors.append(f"final summary entry {index} status is not pass")
        raw_path = entry.get("path") or entry.get("image") or entry.get("result") if isinstance(entry, dict) else entry
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"final summary entry {index} must include an image path")
            continue
        image_path = _resolve_artifact_path(raw_path, run_root, summary_path.parent)
        if not image_path.is_file():
            errors.append(f"final summary entry {index} image not found: {image_path}")
            continue
        if image_path.name != "result.png":
            errors.append(f"final summary entry {index} must reference result.png: {image_path}")
            continue
        try:
            relative = image_path.resolve().relative_to(run_root.resolve())
        except ValueError:
            errors.append(f"final summary entry {index} image is outside run root: {image_path}")
            continue
        parts = relative.parts
        if len(parts) != 3 or parts[0] != "generation" or parts[2] != "result.png":
            errors.append(f"final summary entry {index} image is not generation/NN/result.png: {image_path}")
            continue
        generation_dir = run_root / "generation" / parts[1]
        if _qc_status_for_generation(generation_dir) != "pass":
            errors.append(f"final summary entry {index} does not reference a QC-pass generation: {image_path}")
    return errors


def inspect_run(run_root: Path, final_summary: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not (run_root / "input" / "product-on-hand.jpg").is_file():
        errors.append("missing input/product-on-hand.jpg")

    product_path = run_root / "analysis" / "product_analysis.json"
    if not product_path.is_file():
        errors.append("missing analysis/product_analysis.json")
    else:
        errors.extend(_validate_product_analysis(product_path))

    selected_path = run_root / "analysis" / "selected_references.json"
    selected_ranks: set[int] = set()
    if not selected_path.is_file():
        errors.append("missing analysis/selected_references.json")
    else:
        selected_errors, selected_ranks = _validate_selected_references(selected_path, run_root)
        errors.extend(selected_errors)

    decision_path = run_root / "review" / "review_decision.json"
    selected_decision_ranks: list[int] = []
    if not decision_path.is_file():
        errors.append("missing review/review_decision.json")
    else:
        decision_errors, selected_decision_ranks = _validate_review_decision(decision_path, selected_ranks)
        errors.extend(decision_errors)

    generation_root = run_root / "generation"
    if not generation_root.is_dir():
        errors.append("missing generation directory")
        return errors

    generation_dirs = sorted(path for path in generation_root.iterdir() if path.is_dir())
    if not generation_dirs:
        errors.append("missing generation/NN directory")
        return errors
    if selected_decision_ranks and len(generation_dirs) < len(selected_decision_ranks):
        errors.append("generation directory count is lower than selected_ranks count")

    for generation_dir in generation_dirs:
        errors.extend(_validate_generation_dir(generation_dir))

    if final_summary is not None:
        summary_candidates = [final_summary]
    else:
        summary_candidates = [path for path in (run_root / "final-summary.json", run_root / "final" / "accepted.json") if path.is_file()]
    for summary_path in summary_candidates:
        if not summary_path.is_file():
            errors.append(f"final summary not found: {summary_path}")
        else:
            errors.extend(_validate_final_summary(summary_path, run_root))
    return errors


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: inspect_run_artifacts.py <run-root> [final-summary.json]", file=sys.stderr)
        return 2
    run_root = Path(argv[1])
    if not run_root.is_dir():
        print(f"run root not found: {run_root}", file=sys.stderr)
        return 2
    final_summary = _resolve_artifact_path(argv[2], run_root) if len(argv) == 3 else None
    errors = inspect_run(run_root, final_summary)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("run artifacts OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
