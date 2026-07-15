from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_prompt_contract import validate_prompt  # noqa: E402
from validate_qc_record import validate_qc  # noqa: E402
from validate_reference_snapshot import (  # noqa: E402
    SnapshotInputError,
    validate_reference_snapshot,
)

REQUIRED_GENERATION_FILES = ("model.txt", "prompt.txt", "submit.json", "result.json", "result.png", "qc.json")
BRACELET_PRODUCT_TYPE_TERMS = ("手链", "手串", "手镯", "bracelet", "hand-string", "hand string")
MODERN_CLASSIFICATION_FIELDS = (
    "detected_product_type",
    "confirmed_product_type",
    "classification_confidence",
    "classification_evidence",
    "classification_source",
)
SUPPORTED_PRODUCT_TYPES = {"bracelet", "necklace", "pendant_necklace"}
KNOWN_PRODUCT_TYPES = SUPPORTED_PRODUCT_TYPES | {"pendant_only", "unknown"}
SUPPORTED_SOURCE_IMAGE_TYPES = {
    "worn_source",
    "hand_held_source",
    "flat_lay_source",
    "unknown_source",
}
SUPPORTED_DISPLAY_MODES = {"worn", "hand_held"}
NECKLACE_PRODUCT_TYPES = {"necklace", "pendant_necklace"}
NECKLACE_LENGTH_CATEGORIES = {"choker", "collarbone", "upper_chest", "long"}
SNAPSHOT_FIELDS = (
    "confirmed_product_type",
    "source_image_type",
    "display_mode",
    "layer_count",
    "length_category",
    "has_pendant",
    "pendant_count",
    "pendant_layer",
    "pendant_position",
    "pendant_orientation",
    "connection_structure",
    "is_independent_multi_item",
)
GENERATE_ACTIONS = {"generate_rank_1", "generate_selected", "generate_multiple"}
BLOCKED_ACTIONS = {"rerank", "manual_reference"}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_copied_file(generation_dir: Path, value: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}.copied_file 必须是非空字符串")
        return None
    if Path(value).name != value or Path(value).is_absolute():
        errors.append(f"{label}.copied_file 禁止路径逃逸：{value}")
        return None
    path = generation_dir / value
    if not path.is_file():
        errors.append(f"{label} 固化副本不存在：{value}")
        return None
    return path


def _manifest_entry(
    generation_dir: Path,
    value: Any,
    label: str,
    errors: list[str],
    *,
    require_source: bool,
) -> tuple[Path | None, Path | None]:
    required = {"copied_file", "sha256"}
    if require_source:
        required |= {"order", "role", "source_path"}
    if not isinstance(value, dict) or set(value) != required:
        errors.append(f"{label} 字段集合不合法")
        return None, None
    copied = _safe_copied_file(generation_dir, value.get("copied_file"), label, errors)
    digest = value.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        errors.append(f"{label}.sha256 必须是 64 位摘要")
    elif copied is not None and _sha256(copied) != digest:
        errors.append(f"{label} 固化副本摘要与 manifest 不一致")
    source: Path | None = None
    if require_source:
        raw_source = value.get("source_path")
        if not isinstance(raw_source, str) or not raw_source.strip():
            errors.append(f"{label}.source_path 必须是非空路径")
        else:
            source = Path(raw_source)
            if not source.is_file():
                errors.append(f"{label} 源文件不存在：{source}")
                source = None
            elif isinstance(digest, str) and _sha256(source) != digest:
                errors.append(f"{label} 源文件摘要与 manifest 不一致")
    return copied, source


def _same_path(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_required_json(
    path: Path,
    label: str,
    errors: list[str],
) -> Any | None:
    if not path.is_file():
        errors.append(f"缺少 {label}")
        return None
    try:
        return _load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"{label} 不是有效 UTF-8 JSON")
        return None


def _load_modern_run_context(run_root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    context: dict[str, Any] = {
        "run_root": run_root,
        "product_source": run_root / "input" / "product-on-hand.jpg",
        "analysis_path": run_root / "analysis" / "product_analysis.json",
        "canonical_path": run_root / "analysis" / "product_fidelity_constraints.json",
        "selected_path": run_root / "analysis" / "selected_references.json",
        "role_path": run_root / "analysis" / "output_role.json",
        "decision_path": run_root / "review" / "review_decision.json",
        "snapshot_path": run_root / "review" / "reference_composition_snapshot.json",
    }
    if not context["product_source"].is_file():
        errors.append("缺少 input/product-on-hand.jpg 产品原图")

    analysis = _load_required_json(
        context["analysis_path"], "analysis/product_analysis.json", errors
    )
    canonical = _load_required_json(
        context["canonical_path"],
        "analysis/product_fidelity_constraints.json",
        errors,
    )
    selected = _load_required_json(
        context["selected_path"], "analysis/selected_references.json", errors
    )
    role_data = _load_required_json(
        context["role_path"], "analysis/output_role.json", errors
    )
    decision = _load_required_json(
        context["decision_path"], "review/review_decision.json", errors
    )
    snapshot = _load_required_json(
        context["snapshot_path"],
        "review/reference_composition_snapshot.json",
        errors,
    )
    context.update(
        analysis=analysis,
        canonical=canonical,
        selected=selected,
        decision=decision,
        snapshot=snapshot,
    )

    root_role: str | None = None
    if not isinstance(role_data, dict):
        if role_data is not None:
            errors.append("analysis/output_role.json 必须是 JSON 对象")
    else:
        candidate = role_data.get("output_role")
        if not isinstance(candidate, str) or candidate not in {"hand_worn", "lifestyle"}:
            errors.append("analysis/output_role.json 的 output_role 无效")
        else:
            root_role = candidate
    context["output_role"] = root_role

    selected_ranks_available: set[int] = set()
    if selected is not None:
        selected_errors, selected_ranks_available = _validate_selected_references(
            context["selected_path"], run_root
        )
        errors.extend(selected_errors)

    selected_rank: int | None = None
    if not isinstance(decision, dict):
        if decision is not None:
            errors.append("review/review_decision.json 必须是 JSON 对象")
    else:
        decision_errors, decision_ranks = _validate_review_decision(
            context["decision_path"],
            selected_ranks_available,
            analysis if isinstance(analysis, dict) else None,
        )
        errors.extend(decision_errors)
        if len(decision_ranks) != 1:
            errors.append("review_decision 的 selected rank 必须是唯一 JSON 整数")
        else:
            selected_rank = decision_ranks[0]
        decision_role = decision.get("output_role")
        if not isinstance(decision_role, str) or decision_role not in {
            "hand_worn",
            "lifestyle",
        }:
            errors.append("review_decision.output_role 无效")
        elif root_role is not None and decision_role != root_role:
            errors.append("review_decision.output_role 与 analysis/output_role.json 不一致")
        if isinstance(snapshot, dict):
            expected_digest = _canonical_json_sha256(snapshot)
            if decision.get("reference_snapshot_sha256") != expected_digest:
                errors.append("review_decision 的参考构图快照摘要不一致")
    context["selected_rank"] = selected_rank

    if not isinstance(snapshot, dict):
        if snapshot is not None:
            errors.append("review/reference_composition_snapshot.json 必须是 JSON 对象")
    else:
        snapshot_rank = snapshot.get("rank")
        if type(snapshot_rank) is not int or snapshot_rank < 1:
            errors.append("根参考构图快照 rank 必须是正 JSON 整数")
        elif selected_rank is not None and snapshot_rank != selected_rank:
            errors.append("参考构图快照 rank 与 review_decision selected rank 不一致")
        snapshot_role = snapshot.get("output_role")
        if not isinstance(snapshot_role, str) or snapshot_role not in {
            "hand_worn",
            "lifestyle",
        }:
            errors.append("根参考构图快照 output_role 无效")
        elif root_role is not None and snapshot_role != root_role:
            errors.append("根参考构图快照 output_role 与 analysis/output_role.json 不一致")

    selected_item: dict[str, Any] | None = None
    if not isinstance(selected, list):
        if selected is not None:
            errors.append("analysis/selected_references.json 必须是 JSON 列表")
    else:
        matches = [
            item
            for item in selected
            if (
                isinstance(item, dict)
                and type(item.get("rank")) is int
                and item.get("rank") == selected_rank
            )
        ]
        if selected_rank is not None and len(matches) != 1:
            errors.append("analysis/selected_references.json 必须唯一包含 selected rank")
        elif matches:
            selected_item = matches[0]
    context["selected_item"] = selected_item

    source_reference: Path | None = None
    review_reference: Path | None = None
    if selected_item is not None:
        raw_review = selected_item.get("selected_reference")
        if not isinstance(raw_review, str) or not raw_review.strip():
            errors.append("selected_reference 必须是非空路径")
        else:
            review_reference = _resolve_artifact_path(
                raw_review, run_root, context["selected_path"].parent
            )
            if not review_reference.is_file():
                errors.append("selected_reference 对应的 review 副本不存在")
                review_reference = None
        metadata = selected_item.get("metadata")
        if not isinstance(metadata, dict):
            errors.append("selected reference metadata 必须是 JSON 对象")
        else:
            raw_source = metadata.get("source_reference")
            if not isinstance(raw_source, str) or not raw_source.strip():
                errors.append("selected metadata.source_reference 必须是非空路径")
            else:
                source_reference = _resolve_artifact_path(
                    raw_source, run_root, context["selected_path"].parent
                )
                if not source_reference.is_file():
                    errors.append("selected metadata.source_reference 不存在")
                    source_reference = None
            if source_reference is not None:
                source_digest = _sha256(source_reference)
                if selected_item.get("source_sha256") != source_digest:
                    errors.append("selected reference source_sha256 与原始参考图不一致")
                if metadata.get("source_sha256") != source_digest:
                    errors.append("selected metadata.source_sha256 与原始参考图不一致")
            if review_reference is not None:
                review_digest = _sha256(review_reference)
                if selected_item.get("review_sha256") != review_digest:
                    errors.append("selected reference review_sha256 与 review 副本不一致")
                if metadata.get("review_sha256") != review_digest:
                    errors.append("selected metadata.review_sha256 与 review 副本不一致")
        if source_reference is not None and review_reference is not None:
            if _sha256(source_reference) != _sha256(review_reference):
                errors.append("selected_reference review 副本与原始参考图摘要不一致")
    context["source_reference"] = source_reference
    context["review_reference"] = review_reference

    if isinstance(snapshot, dict) and source_reference is not None and root_role is not None:
        try:
            errors.extend(
                f"根快照：{error}"
                for error in validate_reference_snapshot(
                    context["snapshot_path"], source_reference, root_role
                )
            )
        except SnapshotInputError as exc:
            errors.append(str(exc))
    return context, errors


def _validate_task9_generation(
    generation_dir: Path,
    context: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if list(generation_dir.glob("hand-reference.*")):
        errors.append("现代 generation 禁止出现 hand-reference.*")
    manifest_path = generation_dir / "input-manifest.json"
    if not manifest_path.is_file():
        return [*errors, "现代 generation 缺少 input-manifest.json，属于 damaged run"]
    try:
        manifest = _load_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [*errors, "input-manifest.json 不是有效 UTF-8 JSON"]
    fields = {
        "schema_version",
        "output_role",
        "reference_snapshot",
        "product_analysis",
        "fidelity_constraints",
        "inputs",
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        return [*errors, "input-manifest.json 字段集合不合法"]
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        errors.append("input-manifest.schema_version 必须是 JSON 整数 1")
    role = manifest.get("output_role")
    if not isinstance(role, str) or role not in {"hand_worn", "lifestyle"}:
        errors.append("input-manifest.output_role 只能是 hand_worn/lifestyle")

    copied_fixed: dict[str, Path | None] = {}
    for key, expected_name in (
        ("reference_snapshot", "reference-composition-snapshot.json"),
        ("product_analysis", "product-analysis.json"),
        ("fidelity_constraints", "product-fidelity-constraints.json"),
    ):
        copied, _source = _manifest_entry(
            generation_dir,
            manifest.get(key),
            f"input-manifest.{key}",
            errors,
            require_source=False,
        )
        copied_fixed[key] = copied
        if copied is not None and copied.name != expected_name:
            errors.append(f"input-manifest.{key}.copied_file 必须为 {expected_name}")
    run_root = generation_dir.parent.parent
    fixed_sources = {
        "reference_snapshot": run_root / "review" / "reference_composition_snapshot.json",
        "product_analysis": run_root / "analysis" / "product_analysis.json",
        "fidelity_constraints": run_root / "analysis" / "product_fidelity_constraints.json",
    }
    for key, source_path in fixed_sources.items():
        if not source_path.is_file():
            errors.append(f"input-manifest.{key} 对应源文件不存在：{source_path.name}")
            continue
        entry = manifest.get(key)
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if isinstance(digest, str) and _sha256(source_path) != digest:
            errors.append(f"input-manifest.{key} 源文件摘要与 manifest 不一致")

    if context is not None:
        if isinstance(role, str) and context.get("output_role") is not None:
            if role != context["output_role"]:
                errors.append("input-manifest.output_role 与 run 根 output_role 不一致")

    inputs = manifest.get("inputs")
    scene_source: Path | None = None
    product_source: Path | None = None
    if not isinstance(inputs, list) or len(inputs) != 2:
        errors.append("input-manifest.inputs 必须恰好包含两个有序图片输入")
    else:
        expected = ((1, "scene_reference", "scene-reference."), (2, "product_identity", "product-reference."))
        for index, (item, (order, input_role, prefix)) in enumerate(zip(inputs, expected)):
            copied, source = _manifest_entry(
                generation_dir,
                item,
                f"input-manifest.inputs[{index}]",
                errors,
                require_source=True,
            )
            if isinstance(item, dict):
                if type(item.get("order")) is not int or item.get("order") != order:
                    errors.append("图片输入顺序必须为 scene_reference 后 product_identity")
                if item.get("role") != input_role:
                    errors.append("图片输入角色顺序必须为 scene_reference 后 product_identity")
            if copied is not None and not copied.name.startswith(prefix):
                errors.append(f"{input_role} copied_file 命名不合法")
            if index == 0:
                scene_source = source
            else:
                product_source = source

    if context is not None:
        expected_scene = context.get("review_reference")
        if expected_scene is not None and not _same_path(scene_source, expected_scene):
            errors.append("scene_reference.source_path 必须精确绑定 selected_reference review 副本")
        expected_product = context.get("product_source")
        if expected_product is not None and not _same_path(product_source, expected_product):
            errors.append("product_identity.source_path 必须精确绑定 input/product-on-hand.jpg 产品原图")

    for name in ("model.txt", "reference-rank.txt", "prompt.txt", "submit.json"):
        if not (generation_dir / name).is_file():
            errors.append(f"现代 generation 缺少 {name}")
    snapshot_path = copied_fixed.get("reference_snapshot")
    analysis_path = copied_fixed.get("product_analysis")
    canonical_path = copied_fixed.get("fidelity_constraints")
    prompt_path = generation_dir / "prompt.txt"
    snapshot_reference = (
        context.get("source_reference") if context is not None else scene_source
    )
    if snapshot_path is not None and snapshot_reference is not None and isinstance(role, str):
        try:
            errors.extend(
                f"快照：{error}"
                for error in validate_reference_snapshot(snapshot_path, snapshot_reference, role)
            )
        except SnapshotInputError as exc:
            errors.append(str(exc))
        rank_path = generation_dir / "reference-rank.txt"
        try:
            snapshot_data = _load_json(snapshot_path)
            expected_rank = snapshot_data.get("rank") if isinstance(snapshot_data, dict) else None
            actual_rank = int(rank_path.read_text(encoding="utf-8").strip())
            if type(expected_rank) is not int or actual_rank != expected_rank:
                errors.append("reference-rank.txt 与确认快照 rank 不一致")
            if (
                context is not None
                and context.get("selected_rank") is not None
                and actual_rank != context["selected_rank"]
            ):
                errors.append("reference-rank.txt 与 review_decision selected rank 不一致")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            errors.append("reference-rank.txt 无法与确认快照 rank 交叉校验")
    if all(path is not None for path in (snapshot_path, analysis_path, canonical_path)) and prompt_path.is_file():
        errors.extend(
            f"Prompt：{error}"
            for error in validate_prompt(prompt_path, snapshot_path, analysis_path, canonical_path)
        )

    result_path = generation_dir / "result.json"
    completed = False
    if result_path.is_file():
        try:
            result_data = _load_json(result_path)
            completed = (
                isinstance(result_data, dict)
                and isinstance(result_data.get("data"), dict)
                and result_data["data"].get("status") == "completed"
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append("result.json 不是有效 UTF-8 JSON")
    if completed:
        for name in ("result.png", "qc-review.html", "qc.json"):
            if not (generation_dir / name).is_file():
                errors.append(f"已完成 generation 缺少 {name}")
        qc_path = generation_dir / "qc.json"
        if qc_path.is_file():
            errors.extend(f"QC：{error}" for error in validate_qc(qc_path))
    return errors


def _validate_legacy_generation(generation_dir: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_GENERATION_FILES:
        if not (generation_dir / name).is_file():
            errors.append(f"缺少 generation/{generation_dir.name}/{name}")
    hand_references = [
        path
        for path in generation_dir.iterdir()
        if path.is_file() and path.name.startswith("hand-reference.")
    ]
    if len(hand_references) != 1:
        errors.append(
            f"generation/{generation_dir.name} 必须恰好包含一个 hand-reference.*"
        )

    model_path = generation_dir / "model.txt"
    if model_path.is_file():
        try:
            model_name = model_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            errors.append(f"generation/{generation_dir.name}/model.txt 无法按 UTF-8 读取")
        else:
            if model_name not in {"gpt_image_2", "nano_banana_v2"}:
                errors.append(
                    f"generation/{generation_dir.name}/model.txt 使用了不支持的模型：{model_name}"
                )

    result_path = generation_dir / "result.json"
    if result_path.is_file():
        try:
            result = _load_json(result_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"generation/{generation_dir.name}/result.json 不是有效 JSON")
        else:
            completed = (
                isinstance(result, dict)
                and isinstance(result.get("data"), dict)
                and result["data"].get("status") == "completed"
            )
            if not completed:
                errors.append(
                    f"generation/{generation_dir.name}/result.json 的 status 不是 completed"
                )
    qc_path = generation_dir / "qc.json"
    if qc_path.is_file():
        errors.extend(
            f"generation/{generation_dir.name}/qc.json: {error}"
            for error in validate_qc(qc_path)
        )
    return errors


def _validate_legacy_root(run_root: Path) -> list[str]:
    errors: list[str] = []
    if not (run_root / "input" / "product-on-hand.jpg").is_file():
        errors.append("缺少 input/product-on-hand.jpg")
    analysis_path = run_root / "analysis" / "product_analysis.json"
    analysis: dict[str, Any] | None = None
    if not analysis_path.is_file():
        errors.append("缺少 analysis/product_analysis.json")
    else:
        errors.extend(_validate_product_analysis(analysis_path))
        loaded = _load_json(analysis_path)
        if isinstance(loaded, dict):
            analysis = loaded
    selected_path = run_root / "analysis" / "selected_references.json"
    ranks: set[int] = set()
    if not selected_path.is_file():
        errors.append("缺少 analysis/selected_references.json")
    else:
        selected_errors, ranks = _validate_selected_references(selected_path, run_root)
        errors.extend(selected_errors)
    decision_path = run_root / "review" / "review_decision.json"
    if not decision_path.is_file():
        errors.append("缺少 review/review_decision.json")
    else:
        decision_errors, _selected = _validate_review_decision(
            decision_path, ranks, analysis
        )
        errors.extend(decision_errors)
    return errors


def inspect_run_state(run_root: Path) -> dict[str, Any]:
    generation_root = run_root / "generation"
    generation_dirs = (
        sorted(path for path in generation_root.iterdir() if path.is_dir())
        if generation_root.is_dir()
        else []
    )
    modern_markers = {
        "input-manifest.json",
        "reference-composition-snapshot.json",
        "product-analysis.json",
        "product-fidelity-constraints.json",
        "reference-rank.txt",
        "qc-review.html",
    }
    modern: list[Path] = []
    legacy: list[Path] = []
    damaged: list[Path] = []
    for directory in generation_dirs:
        names = {path.name for path in directory.iterdir() if path.is_file()}
        has_modern_marker = (
            bool(names.intersection(modern_markers))
            or any(name.startswith("scene-reference.") for name in names)
            or any(name.startswith("product-reference.") for name in names)
        )
        has_legacy_marker = any(name.startswith("hand-reference.") for name in names)
        if has_modern_marker:
            modern.append(directory)
        elif has_legacy_marker:
            legacy.append(directory)
        else:
            damaged.append(directory)
    if modern:
        context, errors = _load_modern_run_context(run_root)
        if legacy:
            errors.append("同一 run 不得混合现代 generation 与历史 hand-reference generation")
        for directory in damaged:
            errors.append(f"generation/{directory.name}: damaged generation 目录无法分类")
        for directory in modern:
            errors.extend(
                f"generation/{directory.name}: {error}"
                for error in _validate_task9_generation(directory, context)
            )
        return {"classified": True, "legacy_read_only": False, "errors": errors}
    if legacy:
        errors = _validate_legacy_root(run_root)
        for directory in legacy:
            errors.extend(_validate_legacy_generation(directory))
        for directory in damaged:
            errors.append(f"generation/{directory.name}: damaged generation 目录无法分类")
        return {"classified": True, "legacy_read_only": True, "errors": errors}
    if damaged:
        return {
            "classified": True,
            "legacy_read_only": False,
            "errors": [
                f"generation/{directory.name}: damaged generation 目录无法分类"
                for directory in damaged
            ],
        }
    return {"classified": False, "legacy_read_only": False, "errors": []}


def _is_json_int(value: Any) -> bool:
    return type(value) is int


def _is_legacy_bracelet_product(value: Any) -> bool:
    text = str(value or "").lower()
    return any(term.lower() in text for term in BRACELET_PRODUCT_TYPE_TERMS)


def _is_modern_analysis(data: dict[str, Any]) -> bool:
    return any(field_name in data for field_name in MODERN_CLASSIFICATION_FIELDS)


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _analysis_error(message: str) -> str:
    return f"analysis/product_analysis.json：{message}"


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
        return [_analysis_error("必须包含 JSON 对象")]
    return _validate_product_analysis_data(data)


def _validate_product_analysis_data(data: dict[str, Any]) -> list[str]:
    if not _is_modern_analysis(data):
        if _is_legacy_bracelet_product(data.get("product_type")):
            return _validate_legacy_bracelet_explicit_fields(data)
        return [
            _analysis_error(
                "只有旧手串/手链记录可以省略现代分类契约；其他品类必须提供完整现代分类字段"
            )
        ]

    errors: list[str] = []
    missing_classification = [
        field_name
        for field_name in MODERN_CLASSIFICATION_FIELDS
        if field_name not in data
    ]
    if missing_classification:
        errors.append(
            _analysis_error(
                "现代分类契约不完整，缺少字段：" + "、".join(missing_classification)
            )
        )
        return errors

    for field_name in (
        "detected_product_type",
        "confirmed_product_type",
        "classification_confidence",
        "classification_source",
    ):
        if not _is_non_empty_string(data.get(field_name)):
            errors.append(_analysis_error(f"现代分类契约字段 {field_name} 必须是非空字符串"))
    evidence = data.get("classification_evidence")
    if not isinstance(evidence, list) or not all(
        _is_non_empty_string(item) for item in evidence
    ):
        errors.append(
            _analysis_error("现代分类契约字段 classification_evidence 必须是非空字符串列表")
        )

    product_type = data.get("confirmed_product_type")
    detected_product_type = data.get("detected_product_type")
    if (
        not isinstance(detected_product_type, str)
        or detected_product_type not in KNOWN_PRODUCT_TYPES
    ):
        errors.append(_analysis_error("detected_product_type 必须是规范品类"))
    if not isinstance(product_type, str) or product_type not in KNOWN_PRODUCT_TYPES:
        errors.append(_analysis_error("confirmed_product_type 必须是规范品类"))
        return errors
    if product_type == "unknown":
        errors.append(_analysis_error("产品品类无法识别，必须先人工纠正"))
        return errors
    if product_type == "pendant_only":
        errors.append(_analysis_error("当前版本不支持无链独立吊坠，且禁止自动补链"))
        return errors

    source_image_type = data.get("source_image_type")
    if (
        not isinstance(source_image_type, str)
        or source_image_type not in SUPPORTED_SOURCE_IMAGE_TYPES
    ):
        errors.append(
            _analysis_error(
                "source_image_type 必须显式使用 worn_source、hand_held_source、"
                "flat_lay_source 或 unknown_source"
            )
        )
    elif source_image_type == "flat_lay_source":
        errors.append(
            _analysis_error("输入图类型为白底或平铺产品图；第一阶段只接受真人佩戴原图")
        )
    elif source_image_type != "worn_source":
        errors.append(
            _analysis_error(
                f"输入图类型 {source_image_type} 不兼容；第一阶段只接受真人佩戴原图"
            )
        )

    display_mode = data.get("display_mode")
    if not isinstance(display_mode, str) or display_mode not in SUPPORTED_DISPLAY_MODES:
        errors.append(_analysis_error("display_mode 必须是 worn 或 hand_held"))
    elif product_type == "bracelet" and display_mode != "worn":
        errors.append(_analysis_error("手串/手链与手持展示模式不兼容"))

    errors.extend(_validate_product_structure(data, product_type, _analysis_error))
    return errors


def _validate_legacy_bracelet_explicit_fields(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "source_image_type" in data:
        source_image_type = data.get("source_image_type")
        if source_image_type == "flat_lay_source":
            errors.append(
                _analysis_error("输入图类型为白底或平铺产品图；第一阶段只接受真人佩戴原图")
            )
        elif source_image_type != "worn_source":
            errors.append(
                _analysis_error(
                    f"输入图类型 {source_image_type!r} 不兼容；第一阶段只接受真人佩戴原图"
                )
            )
    if "display_mode" in data:
        display_mode = data.get("display_mode")
        if display_mode == "hand_held":
            errors.append(_analysis_error("手串/手链与手持展示模式不兼容"))
        elif display_mode != "worn":
            errors.append(_analysis_error("display_mode 必须是 worn 或 hand_held"))
    if "layer_count" in data:
        layer_count = data.get("layer_count")
        if not _is_json_int(layer_count) or layer_count != 1:
            errors.append(_analysis_error("手串/手链的 layer_count 必须是 JSON 整数 1"))
    if "is_independent_multi_item" in data:
        independent = data.get("is_independent_multi_item")
        if type(independent) is not bool:
            errors.append(
                _analysis_error("is_independent_multi_item 必须是 JSON 布尔值")
            )
        elif independent:
            errors.append(_analysis_error("当前版本不支持多件独立首饰组合叠戴"))
    return errors


def _validate_product_structure(
    data: dict[str, Any],
    product_type: str,
    error_builder,
) -> list[str]:
    errors: list[str] = []
    layer_count = data.get("layer_count")
    if not _is_json_int(layer_count) or layer_count < 1:
        errors.append(error_builder("layer_count 必须是大于等于 1 的 JSON 整数"))
    elif (
        isinstance(product_type, str)
        and product_type in NECKLACE_PRODUCT_TYPES
        and not 1 <= layer_count <= 3
    ):
        errors.append(error_builder("项链产品只支持 1 至 3 层"))
    elif product_type == "bracelet" and layer_count != 1:
        errors.append(error_builder("手串/手链只支持 1 层"))

    independent = data.get("is_independent_multi_item")
    if type(independent) is not bool:
        errors.append(error_builder("is_independent_multi_item 必须是 JSON 布尔值"))
    elif independent:
        if isinstance(product_type, str) and product_type in NECKLACE_PRODUCT_TYPES:
            errors.append(error_builder("当前版本不支持多件独立项链组合叠戴"))
        else:
            errors.append(error_builder("当前版本不支持多件独立首饰组合叠戴"))

    has_pendant = data.get("has_pendant")
    pendant_count = data.get("pendant_count")
    pendant_layer = data.get("pendant_layer")
    if type(has_pendant) is not bool:
        errors.append(error_builder("has_pendant 必须是 JSON 布尔值"))
    if not _is_json_int(pendant_count) or pendant_count < 0:
        errors.append(error_builder("pendant_count 必须是大于等于 0 的 JSON 整数"))
    if pendant_layer is not None and (
        not _is_json_int(pendant_layer) or pendant_layer < 1
    ):
        errors.append(error_builder("pendant_layer 必须是大于等于 1 的 JSON 整数或 null"))

    if product_type == "pendant_necklace" and (
        has_pendant is not True
        or not _is_json_int(pendant_count)
        or pendant_count < 1
        or not _is_json_int(pendant_layer)
        or pendant_layer < 1
    ):
        errors.append(
            error_builder(
                "带链吊坠必须声明完整主吊坠结构：has_pendant=true、"
                "pendant_count 大于等于 1 且 pendant_layer 有效"
            )
        )
    if product_type == "necklace" and (
        has_pendant is not False or pendant_count != 0 or pendant_layer is not None
    ):
        errors.append(error_builder("普通项链不得声明主吊坠结构"))
    if (
        _is_json_int(layer_count)
        and _is_json_int(pendant_layer)
        and pendant_layer > layer_count
    ):
        errors.append(error_builder("pendant_layer 不能大于 layer_count"))

    length_category = data.get("length_category")
    if isinstance(product_type, str) and product_type in NECKLACE_PRODUCT_TYPES and (
        length_category is not None
        and (
            not isinstance(length_category, str)
            or length_category not in NECKLACE_LENGTH_CATEGORIES
        )
    ):
        errors.append(
            error_builder(
                "项链 length_category 必须是 choker、collarbone、upper_chest、long 或 null"
            )
        )
    for field_name in (
        "length_category",
        "pendant_position",
        "pendant_orientation",
        "connection_structure",
    ):
        value = data.get(field_name)
        if value is not None and not _is_non_empty_string(value):
            errors.append(error_builder(f"{field_name} 必须是非空字符串或 null"))
    return errors


def _validate_selected_references(path: Path, run_root: Path) -> tuple[list[str], set[int]]:
    data = _load_json(path)
    errors: list[str] = []
    ranks: set[int] = set()
    if not isinstance(data, list):
        return ["analysis/selected_references.json 必须包含 JSON 列表"], ranks
    if len(data) < 3:
        errors.append("analysis/selected_references.json 必须包含 Top 3 参考图")
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            errors.append(f"selected_references[{index}] 必须是 JSON 对象")
            continue
        rank = item.get("rank")
        if not _is_json_int(rank) or rank < 1 or rank > 3:
            errors.append(f"selected_references[{index}].rank 必须是 1 至 3 的 JSON 整数")
        elif rank in ranks:
            errors.append(f"selected_references 中的 rank {rank} 重复")
        else:
            ranks.add(rank)
        reference = item.get("selected_reference")
        if not isinstance(reference, str) or not reference.strip():
            errors.append(f"selected_references[{index}].selected_reference 必须是非空字符串")
        else:
            resolved_reference = _resolve_artifact_path(reference, run_root, path.parent)
            if not resolved_reference.is_file():
                errors.append(f"选中参考图文件不存在：{reference}")
        if "score" not in item:
            errors.append(f"selected_references[{index}].score 为必填字段")
    for required_rank in (1, 2, 3):
        if required_rank not in ranks:
            errors.append(f"analysis/selected_references.json 缺少 rank {required_rank}")
    return errors, ranks


def _validate_review_decision(
    path: Path,
    selected_ranks_available: set[int],
    analysis: dict[str, Any] | None = None,
) -> tuple[list[str], list[int]]:
    data = _load_json(path)
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["review/review_decision.json 必须包含 JSON 对象"], []
    action = data.get("action")
    if isinstance(action, str) and action in BLOCKED_ACTIONS:
        errors.append(f"review_decision 的 action={action} 不允许进入生成")
    if not isinstance(action, str) or action not in GENERATE_ACTIONS:
        errors.append(
            "review_decision 的 action 必须是 generate_rank_1、generate_selected 或 generate_multiple"
        )

    selected = data.get("selected_ranks")
    if action == "generate_rank_1" and selected in (None, []):
        selected = [1]
    if not isinstance(selected, list) or not selected:
        errors.append("review_decision 的 selected_ranks 必须是非空列表")
        return errors, []
    if not all(_is_json_int(rank) for rank in selected):
        errors.append("review_decision 的 selected_ranks 必须只包含 JSON 整数")
        return errors, []

    selected_ints = list(selected)
    if len(set(selected_ints)) != len(selected_ints):
        errors.append("review_decision 的 selected_ranks 不得包含重复 rank")
    invalid = [rank for rank in selected_ints if rank < 1 or rank > 3]
    if invalid:
        errors.append(f"review_decision 的 selected_ranks 超出 1 至 3：{invalid}")
    missing = [rank for rank in selected_ints if rank not in selected_ranks_available]
    if missing:
        errors.append(f"review_decision 选择的 rank 不在 selected_references.json 中：{missing}")
    if action == "generate_rank_1" and selected_ints != [1]:
        errors.append("generate_rank_1 只能选择 rank 1")
    if action == "generate_selected" and len(selected_ints) != 1:
        errors.append("generate_selected 必须且只能选择一个 rank")
    if action == "generate_multiple" and len(selected_ints) < 2:
        errors.append("generate_multiple 至少必须选择两个 rank")
    if (
        isinstance(analysis, dict)
        and _is_modern_analysis(analysis)
        and isinstance(action, str)
        and action in GENERATE_ACTIONS
    ):
        errors.extend(_validate_modern_decision(data, analysis))
    return errors, selected_ints


def _validate_modern_decision(
    decision: dict[str, Any],
    analysis: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if decision.get("fidelity_confirmed") is not True:
        errors.append("review/review_decision.json：现代生成决策的 fidelity_confirmed 必须为 true")

    product_type = analysis.get("confirmed_product_type")
    snapshot = decision.get("confirmation_snapshot")
    if (
        isinstance(product_type, str)
        and product_type in NECKLACE_PRODUCT_TYPES
        and snapshot is None
    ):
        errors.append("review/review_decision.json：项链生成决策缺少完整产品确认快照")
        return errors
    if snapshot is None:
        return errors
    if not isinstance(snapshot, dict):
        errors.append("review/review_decision.json：confirmation_snapshot 必须是 JSON 对象")
        return errors

    missing = [field_name for field_name in SNAPSHOT_FIELDS if field_name not in snapshot]
    if missing:
        errors.append(
            "review/review_decision.json：确认快照不完整，缺少字段："
            + "、".join(missing)
        )
        return errors

    snapshot_product_type = snapshot.get("confirmed_product_type")
    if (
        not isinstance(snapshot_product_type, str)
        or snapshot_product_type not in KNOWN_PRODUCT_TYPES
    ):
        errors.append("review/review_decision.json：快照 confirmed_product_type 必须是规范品类")
    snapshot_source = snapshot.get("source_image_type")
    if (
        not isinstance(snapshot_source, str)
        or snapshot_source not in SUPPORTED_SOURCE_IMAGE_TYPES
    ):
        errors.append("review/review_decision.json：快照 source_image_type 值无效")
    snapshot_mode = snapshot.get("display_mode")
    if not isinstance(snapshot_mode, str) or snapshot_mode not in SUPPORTED_DISPLAY_MODES:
        errors.append("review/review_decision.json：快照 display_mode 值无效")
    errors.extend(
        _validate_product_structure(
            snapshot,
            snapshot_product_type,
            lambda message: f"review/review_decision.json：确认快照 {message}",
        )
    )

    for field_name in SNAPSHOT_FIELDS:
        expected = analysis.get(field_name)
        actual = snapshot.get(field_name)
        if actual != expected:
            errors.append(
                f"review/review_decision.json：确认快照字段 {field_name} "
                f"与最终 analysis 不一致：快照为 {actual!r}，analysis 为 {expected!r}"
            )
    return errors


def _has_hand_reference(generation_dir: Path) -> bool:
    return any(path.is_file() and path.name.startswith("hand-reference") for path in generation_dir.iterdir())


def _validate_generation_dir(generation_dir: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_GENERATION_FILES:
        if not (generation_dir / name).is_file():
            errors.append(f"缺少 generation/{generation_dir.name}/{name}")
    if generation_dir.is_dir() and not _has_hand_reference(generation_dir):
        errors.append(f"缺少 generation/{generation_dir.name}/hand-reference.*")

    model_path = generation_dir / "model.txt"
    if model_path.is_file():
        model_name = model_path.read_text(encoding="utf-8").strip()
        if model_name not in {"gpt_image_2", "nano_banana_v2"}:
            errors.append(f"generation/{generation_dir.name}/model.txt 使用了不支持的模型：{model_name}")

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
            errors.append(f"generation/{generation_dir.name}/result.json 的 status 不是 completed")
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
        return [f"最终汇总没有已接受条目：{summary_path}"]
    for index, entry in enumerate(entries, start=1):
        entry_status = entry.get("status") if isinstance(entry, dict) else None
        if entry_status is not None and entry_status != "pass":
            errors.append(f"最终汇总第 {index} 项的 status 不是 pass")
        raw_path = entry.get("path") or entry.get("image") or entry.get("result") if isinstance(entry, dict) else entry
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"最终汇总第 {index} 项必须包含图片路径")
            continue
        image_path = _resolve_artifact_path(raw_path, run_root, summary_path.parent)
        if not image_path.is_file():
            errors.append(f"最终汇总第 {index} 项的图片不存在：{image_path}")
            continue
        if image_path.name != "result.png":
            errors.append(f"最终汇总第 {index} 项必须引用 result.png：{image_path}")
            continue
        try:
            relative = image_path.resolve().relative_to(run_root.resolve())
        except ValueError:
            errors.append(f"最终汇总第 {index} 项的图片位于 run 根目录之外：{image_path}")
            continue
        parts = relative.parts
        if len(parts) != 3 or parts[0] != "generation" or parts[2] != "result.png":
            errors.append(f"最终汇总第 {index} 项的图片不是 generation/NN/result.png：{image_path}")
            continue
        generation_dir = run_root / "generation" / parts[1]
        if _qc_status_for_generation(generation_dir) != "pass":
            errors.append(f"最终汇总第 {index} 项未引用 QC 通过的生成结果：{image_path}")
    return errors


def inspect_run(run_root: Path, final_summary: Path | None = None) -> list[str]:
    state = inspect_run_state(run_root)
    if state["classified"]:
        return list(state["errors"])
    errors: list[str] = []
    if not (run_root / "input" / "product-on-hand.jpg").is_file():
        errors.append("缺少 input/product-on-hand.jpg")

    product_path = run_root / "analysis" / "product_analysis.json"
    product_analysis: dict[str, Any] | None = None
    if not product_path.is_file():
        errors.append("缺少 analysis/product_analysis.json")
    else:
        errors.extend(_validate_product_analysis(product_path))
        loaded_analysis = _load_json(product_path)
        if isinstance(loaded_analysis, dict):
            product_analysis = loaded_analysis

    selected_path = run_root / "analysis" / "selected_references.json"
    selected_ranks: set[int] = set()
    if not selected_path.is_file():
        errors.append("缺少 analysis/selected_references.json")
    else:
        selected_errors, selected_ranks = _validate_selected_references(selected_path, run_root)
        errors.extend(selected_errors)

    decision_path = run_root / "review" / "review_decision.json"
    selected_decision_ranks: list[int] = []
    if not decision_path.is_file():
        errors.append("缺少 review/review_decision.json")
    else:
        decision_errors, selected_decision_ranks = _validate_review_decision(
            decision_path,
            selected_ranks,
            product_analysis,
        )
        errors.extend(decision_errors)

    generation_root = run_root / "generation"
    if not generation_root.is_dir():
        errors.append("缺少 generation 目录")
        return errors

    generation_dirs = sorted(path for path in generation_root.iterdir() if path.is_dir())
    if not generation_dirs:
        errors.append("缺少 generation/NN 目录")
        return errors
    if selected_decision_ranks and len(generation_dirs) < len(selected_decision_ranks):
        errors.append("generation 结果目录数量少于 selected_ranks 数量")

    for generation_dir in generation_dirs:
        errors.extend(_validate_generation_dir(generation_dir))

    if final_summary is not None:
        summary_candidates = [final_summary]
    else:
        summary_candidates = [path for path in (run_root / "final-summary.json", run_root / "final" / "accepted.json") if path.is_file()]
    for summary_path in summary_candidates:
        if not summary_path.is_file():
            errors.append(f"最终汇总文件不存在：{summary_path}")
        else:
            errors.extend(_validate_final_summary(summary_path, run_root))
    return errors


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] in {"-h", "--help"}:
        print("用法：inspect_run_artifacts.py <run-root> [final-summary.json]")
        return 0
    if len(argv) not in (2, 3):
        print("用法：inspect_run_artifacts.py <run-root> [final-summary.json]", file=sys.stderr)
        return 2
    run_root = Path(argv[1])
    if not run_root.is_dir():
        print(f"run 根目录不存在：{run_root}", file=sys.stderr)
        return 2
    for json_path in sorted(run_root.rglob("*.json")):
        try:
            json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"JSON 输入无法读取或语法错误：{json_path}；{exc}", file=sys.stderr)
            return 2
    final_summary = _resolve_artifact_path(argv[2], run_root) if len(argv) == 3 else None
    errors = inspect_run(run_root, final_summary)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("run 产物检查通过")
    state = inspect_run_state(run_root)
    print(f"legacy_read_only={'true' if state['legacy_read_only'] else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
