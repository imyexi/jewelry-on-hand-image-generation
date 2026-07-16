from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_prompt_contract import validate_prompt  # noqa: E402
from validate_qc_record import (  # noqa: E402
    _validate_present_pendant_semantic_conflicts,
    _validate_v2_necklace_analysis_pendant_fields,
    validate_qc,
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
SUPPORTED_PRODUCT_TYPES = {"bracelet", "necklace", "pendant_necklace", "ring"}
KNOWN_PRODUCT_TYPES = SUPPORTED_PRODUCT_TYPES | {"pendant_only", "unknown"}
SUPPORTED_SOURCE_IMAGE_TYPES = {
    "worn_source",
    "hand_held_source",
    "flat_lay_source",
    "unknown_source",
}
SUPPORTED_DISPLAY_MODES = {"worn", "hand_held"}
NECKLACE_PRODUCT_TYPES = {"necklace", "pendant_necklace"}
RING_FIELDS = ("ring_count", "hand_side", "finger_position", "ring_wear_style")
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
PENDANT_SENSITIVE_TERMS = ("吊坠", "主吊坠", "链坠", "流苏", "坠子")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def _validate_fidelity_constraints_data(
    analysis: dict[str, Any],
    constraints: dict[str, Any],
) -> tuple[list[str], bool]:
    schema_version = constraints.get("schema_version")
    if schema_version == 1 and type(schema_version) is int:
        return [], True
    if schema_version != 2 or type(schema_version) is not int:
        return ["analysis/product_fidelity_constraints.json：schema_version 必须为 1 或 2"], False

    semantics = constraints.get("pendant_semantics")
    if not isinstance(semantics, dict):
        return ["analysis/product_fidelity_constraints.json：v2 的 pendant_semantics 必须是 JSON 对象"], False
    presence = semantics.get("presence")
    count = semantics.get("count")
    layer = semantics.get("layer")
    policy = semantics.get("creation_policy")
    errors: list[str] = []
    if "layer" not in semantics:
        errors.append("v2 pendant_semantics.layer 必填；absent 时必须显式为 null")
    if presence not in {"present", "absent"}:
        errors.append("v2 pendant_semantics.presence 必须是 present 或 absent")
    if type(count) is not int or count not in {0, 1}:
        errors.append("v2 pendant_semantics.count 必须是整数 0 或 1")
    if layer is not None and (type(layer) is not int or not 1 <= layer <= 3):
        errors.append("v2 pendant_semantics.layer 必须是 null 或 1 至 3")
    if policy != "forbid":
        errors.append("v2 pendant_semantics.creation_policy 必须为 forbid")
    if presence == "absent" and (count != 0 or layer is not None):
        errors.append("v2 presence=absent 时 count 必须为 0 且 layer 必须为 null")
    if presence == "present" and (count != 1 or layer is None):
        errors.append("v2 presence=present 时 count 必须为 1 且 layer 必须为 1 至 3")

    product_type = analysis.get("confirmed_product_type")
    errors.extend(_validate_v2_necklace_analysis_pendant_fields(analysis))
    expected = (
        ("present", 1, analysis.get("pendant_layer"))
        if product_type == "pendant_necklace"
        else ("absent", 0, None)
    )
    if product_type in NECKLACE_PRODUCT_TYPES and (presence, count, layer) != expected:
        errors.append(
            "v2 吊坠结构与最终 analysis 不一致："
            f"analysis={product_type}/count={analysis.get('pendant_count')}/"
            f"layer={analysis.get('pendant_layer')}，canonical={semantics}"
        )
    if errors:
        return errors, False

    must_keep = constraints.get("must_keep")
    if not isinstance(must_keep, list):
        return ["v2 canonical 的 must_keep 必须是列表"], False
    detected_keywords = constraints.get("detected_keywords")
    must_not_change = constraints.get("must_not_change")
    if not isinstance(detected_keywords, list) or not all(
        isinstance(item, str) for item in detected_keywords
    ):
        errors.append("v2 canonical 的 detected_keywords 必须是字符串列表")
    if not isinstance(must_not_change, list) or not all(
        isinstance(item, str) for item in must_not_change
    ):
        errors.append("v2 canonical 的 must_not_change 必须是字符串列表")
    for index, item in enumerate(must_keep):
        if not isinstance(item, dict):
            errors.append(f"must_keep[{index}] 必须是 JSON 对象")
            continue
        for field in (
            "name", "source_text", "normalized_keyword", "location",
            "visual_shape", "relationship", "qc_question",
        ):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"must_keep[{index}].{field} 必须是非空字符串")
        forbid = item.get("forbid")
        if not isinstance(forbid, list) or not all(
            isinstance(value, str) and value.strip() for value in forbid
        ):
            errors.append(f"must_keep[{index}].forbid 必须是非空字符串列表")
    if errors:
        return errors, False
    if presence == "absent":
        semantic_fields: list[tuple[str, Any]] = []
        for index, value in enumerate(detected_keywords):
            semantic_fields.append((f"detected_keywords[{index}]", value))
        for index, value in enumerate(must_not_change):
            semantic_fields.append((f"must_not_change[{index}]", value))
        for index, item in enumerate(must_keep):
            for field in (
                "name", "source_text", "normalized_keyword", "location",
                "visual_shape", "relationship", "qc_question",
            ):
                semantic_fields.append((f"must_keep[{index}].{field}", item.get(field)))
            for forbid_index, value in enumerate(item["forbid"]):
                semantic_fields.append((f"must_keep[{index}].forbid[{forbid_index}]", value))
        for field_path, value in semantic_fields:
            if not isinstance(value, str):
                continue
            for term in PENDANT_SENSITIVE_TERMS:
                if term in value:
                    errors.append(f"v2 无吊坠 canonical 的 {field_path} 不得包含敏感词：{term}")
    else:
        if product_type in NECKLACE_PRODUCT_TYPES:
            errors.extend(_validate_present_pendant_semantic_conflicts(constraints))
        pendant_items = [
            item for item in must_keep
            if isinstance(item, dict)
            and item.get("normalized_keyword") in PENDANT_SENSITIVE_TERMS
        ]
        if len(pendant_items) != 1:
            errors.append("v2 有吊坠 canonical 必须有且只有一项可追溯主吊坠 must_keep")
        elif f"第 {layer} 层" not in str(pendant_items[0].get("relationship", "")):
            errors.append(f"v2 主吊坠 must_keep.relationship 必须包含第 {layer} 层")
    return errors, False


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
    if detected_product_type not in KNOWN_PRODUCT_TYPES:
        errors.append(_analysis_error("detected_product_type 必须是规范品类"))
    if product_type not in KNOWN_PRODUCT_TYPES:
        errors.append(_analysis_error("confirmed_product_type 必须是规范品类"))
        return errors
    if product_type == "unknown":
        errors.append(_analysis_error("产品品类无法识别，必须先人工纠正"))
        return errors
    if product_type == "pendant_only":
        errors.append(_analysis_error("当前版本不支持无链独立吊坠，且禁止自动补链"))
        return errors

    source_image_type = data.get("source_image_type")
    if source_image_type not in SUPPORTED_SOURCE_IMAGE_TYPES:
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
    if display_mode not in SUPPORTED_DISPLAY_MODES:
        errors.append(_analysis_error("display_mode 必须是 worn 或 hand_held"))
    elif product_type in {"bracelet", "ring"} and display_mode != "worn":
        label = "手串/手链" if product_type == "bracelet" else "戒指"
        errors.append(_analysis_error(f"{label}与手持展示模式不兼容"))

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
    elif product_type in NECKLACE_PRODUCT_TYPES and not 1 <= layer_count <= 3:
        errors.append(error_builder("项链产品只支持 1 至 3 层"))
    elif product_type in {"bracelet", "ring"} and layer_count != 1:
        label = "手串/手链" if product_type == "bracelet" else "戒指"
        errors.append(error_builder(f"{label}只支持 1 层"))

    independent = data.get("is_independent_multi_item")
    if type(independent) is not bool:
        errors.append(error_builder("is_independent_multi_item 必须是 JSON 布尔值"))
    elif independent:
        if product_type in NECKLACE_PRODUCT_TYPES:
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
    if product_type == "ring" and (
        has_pendant is not False or pendant_count != 0 or pendant_layer is not None
    ):
        errors.append(error_builder("戒指不得声明吊坠结构"))
    if (
        _is_json_int(layer_count)
        and _is_json_int(pendant_layer)
        and pendant_layer > layer_count
    ):
        errors.append(error_builder("pendant_layer 不能大于 layer_count"))

    length_category = data.get("length_category")
    if product_type in NECKLACE_PRODUCT_TYPES:
        if length_category is None:
            errors.append(
                error_builder(
                    "现代项链 length_category 不能为空；必须在参考评分前人工纠正为 "
                    "choker、collarbone、upper_chest 或 long"
                )
            )
        elif length_category not in NECKLACE_LENGTH_CATEGORIES:
            errors.append(
                error_builder(
                    "项链 length_category 必须是 choker、collarbone、upper_chest 或 long"
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
    if product_type == "ring":
        missing_ring_fields = [field for field in RING_FIELDS if field not in data]
        if missing_ring_fields:
            errors.append(
                error_builder("戒指契约不完整，缺少字段：" + "、".join(missing_ring_fields))
            )
        else:
            if data.get("ring_count") != 1 or not _is_json_int(data.get("ring_count")):
                errors.append(error_builder("戒指只支持 ring_count=1"))
            if data.get("hand_side") not in {"left", "right"}:
                errors.append(error_builder("戒指 hand_side 必须是 left 或 right"))
            if data.get("finger_position") not in {
                "thumb", "index", "middle", "ring", "little"
            }:
                errors.append(error_builder("戒指 finger_position 必须是明确手指"))
            if data.get("ring_wear_style") != "finger_base":
                errors.append(error_builder("戒指 ring_wear_style 必须是 finger_base"))
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
    if action in BLOCKED_ACTIONS:
        errors.append(f"review_decision 的 action={action} 不允许进入生成")
    if action not in GENERATE_ACTIONS:
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
    if product_type in NECKLACE_PRODUCT_TYPES | {"ring"} and snapshot is None:
        label = "项链" if product_type in NECKLACE_PRODUCT_TYPES else "戒指"
        errors.append(f"review/review_decision.json：{label}生成决策缺少完整产品确认快照")
        return errors
    if snapshot is None:
        return errors
    if not isinstance(snapshot, dict):
        errors.append("review/review_decision.json：confirmation_snapshot 必须是 JSON 对象")
        return errors

    required_snapshot_fields = SNAPSHOT_FIELDS + (
        RING_FIELDS if product_type == "ring" else ()
    )
    missing = [
        field_name for field_name in required_snapshot_fields if field_name not in snapshot
    ]
    if missing:
        errors.append(
            "review/review_decision.json：确认快照不完整，缺少字段："
            + "、".join(missing)
        )
        return errors

    snapshot_product_type = snapshot.get("confirmed_product_type")
    if snapshot_product_type not in KNOWN_PRODUCT_TYPES:
        errors.append("review/review_decision.json：快照 confirmed_product_type 必须是规范品类")
    snapshot_source = snapshot.get("source_image_type")
    if snapshot_source not in SUPPORTED_SOURCE_IMAGE_TYPES:
        errors.append("review/review_decision.json：快照 source_image_type 值无效")
    snapshot_mode = snapshot.get("display_mode")
    if snapshot_mode not in SUPPORTED_DISPLAY_MODES:
        errors.append("review/review_decision.json：快照 display_mode 值无效")
    errors.extend(
        _validate_product_structure(
            snapshot,
            snapshot_product_type,
            lambda message: f"review/review_decision.json：确认快照 {message}",
        )
    )

    for field_name in required_snapshot_fields:
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

    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    if product_analysis is not None and constraints_path.is_file():
        loaded_constraints = _load_json(constraints_path)
        if not isinstance(loaded_constraints, dict):
            errors.append("analysis/product_fidelity_constraints.json 必须包含 JSON 对象")
        else:
            constraint_errors, _legacy_read_only = _validate_fidelity_constraints_data(
                product_analysis,
                loaded_constraints,
            )
            errors.extend(constraint_errors)

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
    if len(argv) not in (2, 3):
        print("用法：inspect_run_artifacts.py <run-root> [final-summary.json]", file=sys.stderr)
        return 2
    run_root = Path(argv[1])
    if not run_root.is_dir():
        print(f"run 根目录不存在：{run_root}", file=sys.stderr)
        return 2
    final_summary = _resolve_artifact_path(argv[2], run_root) if len(argv) == 3 else None
    errors = inspect_run(run_root, final_summary)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("run 产物检查通过")
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    legacy_read_only = False
    if constraints_path.is_file():
        constraints = _load_json(constraints_path)
        legacy_read_only = (
            isinstance(constraints, dict)
            and constraints.get("schema_version") == 1
            and type(constraints.get("schema_version")) is int
        )
    print(f"legacy_read_only={'true' if legacy_read_only else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
