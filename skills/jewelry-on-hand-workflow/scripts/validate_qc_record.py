from __future__ import annotations

import json
import hashlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_STATUS = {"pass", "rerun", "reject"}
ALLOWED_CRITICAL_FAILURES = {
    "must_keep_failed",
    "category_mismatch",
    "core_structure_missing",
    "layer_count_mismatch",
    "length_category_mismatch",
    "pendant_layer_changed",
    "multi_layer_restructured",
    "auto_chain_added",
    "source_person_region_migrated",
    "severe_intersection",
    "ring_count_mismatch",
    "hand_side_mismatch",
    "finger_position_mismatch",
    "ring_structure_mismatch",
    "centerpiece_mismatch",
    "ring_contact_error",
    "finger_deformation",
    "source_hand_leakage",
}
REJECT_CRITICAL_FAILURES = {
    "category_mismatch",
    "core_structure_missing",
    "multi_layer_restructured",
    "auto_chain_added",
    "severe_intersection",
    "ring_count_mismatch",
    "finger_position_mismatch",
    "ring_structure_mismatch",
    "centerpiece_mismatch",
    "source_hand_leakage",
}
SOURCE_WRIST_TERMS = ("原图手腕", "源图手腕", "source wrist", "source-wrist", "粗手腕")
SOURCE_ARM_TERMS = ("原图手臂", "源图手臂", "source-arm", "source arm", "局部手臂")
SOURCE_SKIN_TERMS = ("皮肤块", "局部贴片", "肤色", "皮肤纹理")
SOURCE_PERSON_TERMS = (
    "产品图中的人物",
    "产品图人物局部",
    "产品原图的人物",
    "产品图中的颈部",
    "产品图中的胸部",
    "产品图中的衣服",
    "产品图中的头发",
    "产品图中的皮肤块",
)
NEGATED_CHECK_TERMS = ("没有检查", "未检查", "没检查", "未做检查", "没有做检查", "未明确检查")
PASS_CHECK_TERMS = (
    "检查通过",
    "迁移检查通过",
    "来源一致性通过",
    "未发现",
    "未见",
    "无迁移",
    "没有迁移",
    "未迁移",
    "无源图手臂局部贴片",
)
REJECT_FAILURE_TERMS = (
    "品类错误",
    "品类不一致",
    "核心结构缺失",
    "核心配件缺失",
    "多层关系重组",
    "层间关系重组",
    "自动补链",
    "凭空补链",
    "严重穿模",
    "严重穿透",
    "戒指数量错误",
    "佩戴手指错误",
    "戒指结构错误",
    "戒面错误",
    "主石错误",
    "产品图手部迁移",
)

COMMON_QC_ITEMS = (
    "产品颜色、材质、透明度、纹理、反光和比例与产品图一致",
    "元件数量、排列和关键识别点与产品图一致",
    "没有新增、删除或重组产品结构",
    "没有迁移产品图中的人物、皮肤、服装、头发或背景局部",
    "参考图原有首饰已移除",
    "人物、皮肤、手指、脸部和衣服没有明显畸变",
    "没有文字、水印或无关 logo",
)
SHARED_QC_ITEMS = ("禁止推断不可见扣头或背面结构",)
CATEGORY_QC_ITEMS = {
    "bracelet": ("产品品类与产品图一致", "产品关键结构完整", "手腕佩戴关系自然"),
    "necklace": ("产品品类与产品图一致", "项链层数、顺序和相对落差正确", "链条与身体或手部关系自然"),
    "pendant_necklace": ("产品品类与产品图一致", "项链层数、顺序和相对落差正确", "吊坠形态、连接关系和所在层正确"),
    "ring": (
        "画面中只有一枚目标戒指",
        "戒指位于确认后的左右手和目标手指根部",
        "戒圈、戒面、主石、镶嵌和装饰排列与产品图可见结构一致",
        "戒圈自然环绕手指且前后遮挡、接触和阴影真实",
        "没有迁移产品图中的手、皮肤、指甲、掌纹或背景局部",
    ),
}
MODE_QC_ITEMS = {
    ("bracelet", "worn"): (
        "手串贴合手腕，遮挡、松紧和接触阴影自然",
        "手指、手掌、手腕和皮肤纹理自然",
        "没有迁移产品图中的粗手腕、局部手臂或皮肤块",
    ),
    ("necklace", "worn"): (
        "层数、上下顺序、长度等级和层间落差与产品图一致",
        "吊坠所属层、位置、朝向和连接关系与产品图一致",
        "链条真实绕颈并在胸前自然垂落",
        "链条没有穿肤、穿衣、穿发、悬空或陷入身体",
        "衣领和头发遮挡符合真实前后关系且未遮掉主要结构",
        "多层链没有错误交叉、合并或复制",
        "没有自动补链、凭空补链或补充不存在的连接结构",
        "没有迁移产品图中的颈部、胸部、衣服、头发或皮肤块",
    ),
    ("necklace", "hand_held"): (
        "产品结构完整且关键结构可辨认",
        "手部与链条接触真实，链条自然垂落",
        "手指没有穿透链条或吊坠",
        "吊坠和关键结构没有被不合理遮挡",
        "产品比例合理，没有因近景明显放大或缩小",
        "没有虚构佩戴链路、自动补链或补充不存在的结构",
    ),
    ("ring", "worn"): CATEGORY_QC_ITEMS["ring"],
}
PENDANT_ABSENT_QC_QUESTION = "主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠"
PENDANT_PRESENT_QC_QUESTION = "现有主吊坠数量是否为 {count}，且仍位于第 {layer} 层并保持原连接关系"
NECKLACE_PRODUCT_TYPES = {"necklace", "pendant_necklace"}
PRESENT_PENDANT_CONFLICT_PHRASES = (
    "无吊坠",
    "未见吊坠",
    "吊坠不存在",
    "吊坠缺失",
    "必须新增第二颗吊坠",
    "要求生成第二颗吊坠",
)
PENDANT_SEMANTIC_ITEM_FIELDS = (
    "name",
    "source_text",
    "normalized_keyword",
    "location",
    "visual_shape",
    "relationship",
    "qc_question",
)
MODE_QC_ITEMS[("pendant_necklace", "worn")] = MODE_QC_ITEMS[("necklace", "worn")]
MODE_QC_ITEMS[("pendant_necklace", "hand_held")] = MODE_QC_ITEMS[("necklace", "hand_held")]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _iter_constraint_semantic_fields(
    constraints: dict[str, Any],
) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for list_name in ("detected_keywords", "must_not_change"):
        values = constraints.get(list_name)
        if isinstance(values, list):
            fields.extend(
                (f"{list_name}[{index}]", value)
                for index, value in enumerate(values)
                if isinstance(value, str)
            )
    must_keep = constraints.get("must_keep")
    if not isinstance(must_keep, list):
        return fields
    for index, item in enumerate(must_keep):
        if not isinstance(item, dict):
            continue
        for field_name in PENDANT_SEMANTIC_ITEM_FIELDS:
            value = item.get(field_name)
            if isinstance(value, str):
                fields.append((f"must_keep[{index}].{field_name}", value))
        forbid = item.get("forbid")
        if isinstance(forbid, list):
            fields.extend(
                (f"must_keep[{index}].forbid[{forbid_index}]", value)
                for forbid_index, value in enumerate(forbid)
                if isinstance(value, str)
            )
    return fields


def _validate_present_pendant_semantic_conflicts(
    constraints: dict[str, Any],
) -> list[str]:
    semantics = constraints.get("pendant_semantics")
    if not isinstance(semantics, dict) or semantics.get("presence") != "present":
        return []
    errors: list[str] = []
    for field_path, text in _iter_constraint_semantic_fields(constraints):
        for phrase in PRESENT_PENDANT_CONFLICT_PHRASES:
            if phrase in text:
                errors.append(f"{field_path} 与 present canonical 冲突：{phrase}")
    return errors


def _validate_v2_necklace_analysis_pendant_fields(
    analysis: dict[str, Any],
) -> list[str]:
    product_type = analysis.get("confirmed_product_type")
    if product_type == "necklace":
        expected = {
            "has_pendant": False,
            "pendant_count": 0,
            "pendant_layer": None,
        }
        label = "普通项链"
    elif product_type == "pendant_necklace":
        expected = {
            "has_pendant": True,
            "pendant_count": 1,
        }
        label = "带链吊坠"
    else:
        return []

    errors: list[str] = []
    for field_name, expected_value in expected.items():
        actual = analysis.get(field_name)
        if (
            field_name not in analysis
            or type(actual) is not type(expected_value)
            or actual != expected_value
        ):
            errors.append(
                f"v2 {label} analysis.{field_name} 必须为 {expected_value!r}"
            )
    if product_type == "pendant_necklace":
        layer = analysis.get("pendant_layer")
        if type(layer) is not int or not 1 <= layer <= 3:
            errors.append("v2 带链吊坠 analysis.pendant_layer 必须为 JSON 整数 1 至 3")
    return errors


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _string_list(data: dict[str, Any], key: str, errors: list[str]) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} 必须是列表")
        return []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{key} 只能包含非空字符串")
        return []
    return [item.strip() for item in value]


def _critical_failures(data: dict[str, Any], errors: list[str]) -> list[str]:
    if "critical_failures" not in data:
        return []
    value = data["critical_failures"]
    if not isinstance(value, list):
        errors.append("critical_failures 必须是列表")
        return []
    if not value:
        errors.append("critical_failures 不能为空列表；没有严重错误时请省略该字段")
        return []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append("critical_failures 只能包含非空字符串")
        return []
    normalized = [item.strip() for item in value]
    unknown = [item for item in normalized if item not in ALLOWED_CRITICAL_FAILURES]
    if unknown:
        errors.append("critical_failures 包含未知错误代码：" + "、".join(unknown))
    if len(set(normalized)) != len(normalized):
        errors.append("critical_failures 不能包含重复错误代码")
    return normalized


def _validate_fidelity_checks(
    data: dict[str, Any],
    status: Any,
    errors: list[str],
    expected_must_keep: list[tuple[str, str]] | None,
) -> None:
    if "fidelity_checks" not in data:
        if expected_must_keep:
            errors.append("fidelity_checks 数量必须与 must_keep 完全一致")
        return
    checks = data["fidelity_checks"]
    if not isinstance(checks, list):
        errors.append("fidelity_checks 必须是列表")
        return
    valid_checks: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        label = f"fidelity_checks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{label} 必须是 JSON 对象")
            continue
        fields_valid = True
        for key in ("name", "question", "result", "notes"):
            value = check.get(key)
            if not isinstance(value, str) or (key != "notes" and not value.strip()):
                errors.append(f"{label}.{key} 必须是字符串" + ("" if key == "notes" else "且不能为空"))
                fields_valid = False
        result = check.get("result")
        if isinstance(result, str) and result not in {"pass", "rerun", "fail"}:
            errors.append(f"{label}.result 必须是 pass/rerun/fail")
            fields_valid = False
        if status == "pass" and result != "pass":
            errors.append("must_keep 关键识别点未通过时不得标记为 pass")
        if fields_valid:
            valid_checks.append(check)
    if expected_must_keep is not None:
        _validate_must_keep_coverage(valid_checks, expected_must_keep, errors)


def _qc_check_id(question: str) -> str:
    return "qc-" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]


def _validate_checklist_checks(
    data: dict[str, Any],
    status: Any,
    errors: list[str],
    expected_questions: list[str] | None,
) -> None:
    if expected_questions is None:
        return
    checks = data.get("checklist_checks")
    if not isinstance(checks, list):
        errors.append("checklist_checks 必须完整覆盖 runtime checklist")
        return
    actual: list[tuple[str, str]] = []
    for index, check in enumerate(checks):
        label = f"checklist_checks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{label} 必须是 JSON 对象")
            continue
        valid = True
        for key in ("id", "question", "result", "notes"):
            value = check.get(key)
            if not isinstance(value, str) or (key != "notes" and not value.strip()):
                errors.append(f"{label}.{key} 必须是字符串" + ("" if key == "notes" else "且不能为空"))
                valid = False
        result = check.get("result")
        if isinstance(result, str) and result not in {"pass", "rerun", "fail"}:
            errors.append(f"{label}.result 必须是 pass/rerun/fail")
            valid = False
        if status == "pass" and result != "pass":
            errors.append("checklist_checks 存在未通过项时不得标记为 pass")
        if valid:
            actual.append((check["id"], check["question"]))
    expected = [(_qc_check_id(question), question) for question in expected_questions]
    if len(set(actual)) != len(actual):
        errors.append("checklist_checks 的 id/question 组合必须唯一")
    elif len(actual) != len(expected) or Counter(actual) != Counter(expected):
        errors.append("checklist_checks 必须按稳定 id 与精确 question 完整覆盖 runtime checklist")


def _validate_shared_question_results(
    data: dict[str, Any], errors: list[str]
) -> None:
    fidelity_checks = data.get("fidelity_checks")
    checklist_checks = data.get("checklist_checks")
    if not isinstance(fidelity_checks, list) or not isinstance(
        checklist_checks, list
    ):
        return
    checklist_results = {
        item.get("question"): item.get("result")
        for item in checklist_checks
        if isinstance(item, dict)
        and isinstance(item.get("question"), str)
        and item.get("result") in {"pass", "rerun", "fail"}
    }
    for item in fidelity_checks:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        result = item.get("result")
        if not isinstance(question, str) or result not in {
            "pass",
            "rerun",
            "fail",
        }:
            continue
        checklist_result = checklist_results.get(question)
        if checklist_result is not None and checklist_result != result:
            errors.append(
                "fidelity_checks 与 checklist_checks 对同一 question 的 result "
                f"必须一致：{question}"
            )


def _validate_must_keep_coverage(
    checks: list[dict[str, Any]],
    expected: list[tuple[str, str]],
    errors: list[str],
) -> None:
    names = [check.get("name") for check in checks if isinstance(check.get("name"), str)]
    questions = [
        check.get("question")
        for check in checks
        if isinstance(check.get("question"), str)
    ]
    actual_pair_list = [
        (check.get("name"), check.get("question")) for check in checks
    ]
    if len(set(actual_pair_list)) != len(actual_pair_list):
        errors.append("fidelity_checks 的 name/question 组合必须唯一")
        return
    if len(checks) != len(expected):
        errors.append("fidelity_checks 数量必须与 must_keep 完全一致")
        return
    expected_names = [name for name, _ in expected]
    if Counter(names) != Counter(expected_names):
        errors.append("fidelity_checks.name 必须与 must_keep.name 完全一致")
        return
    expected_questions = [question for _, question in expected]
    if Counter(questions) != Counter(expected_questions):
        errors.append(
            "fidelity_checks.question 必须与 must_keep.qc_question 完全一致"
        )
        return
    if set(actual_pair_list) != set(expected):
        errors.append("fidelity_checks 的 name/question 对应关系与 must_keep 不一致")


def _expected_must_keep_for_qc(
    qc_path: Path, errors: list[str]
) -> list[tuple[str, str]] | None:
    constraints_path = _constraints_path_for_qc(qc_path)
    if constraints_path is None or not constraints_path.is_file():
        return None
    try:
        constraints = _load_json(constraints_path)
    except json.JSONDecodeError:
        errors.append("产品保真约束文件不是有效 JSON")
        return None
    except (OSError, UnicodeError):
        errors.append("产品保真约束文件无法按 UTF-8 文本读取")
        return None
    if not isinstance(constraints, dict):
        errors.append("产品保真约束文件必须包含 JSON 对象")
        return None
    must_keep = constraints.get("must_keep")
    if not isinstance(must_keep, list):
        errors.append("产品保真约束的 must_keep 必须是列表")
        return None

    expected: list[tuple[str, str]] = []
    for index, item in enumerate(must_keep):
        if not isinstance(item, dict):
            errors.append(f"must_keep[{index}] 必须是 JSON 对象")
            return None
        name = item.get("name")
        question = item.get("qc_question")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"must_keep[{index}].name 必须是非空字符串")
            return None
        if not isinstance(question, str) or not question.strip():
            errors.append(f"must_keep[{index}].qc_question 必须是非空字符串")
            return None
        expected.append((name.strip(), question.strip()))
    if len(set(expected)) != len(expected):
        errors.append("must_keep 的 name/qc_question 组合必须唯一")
        return None
    return expected


def _constraints_path_for_qc(qc_path: Path) -> Path | None:
    generation_dir = qc_path.parent
    if generation_dir.parent.name != "generation":
        return None
    return (
        generation_dir.parent.parent
        / "analysis"
        / "product_fidelity_constraints.json"
    )


def _expected_runtime_checklist_for_qc(
    qc_path: Path, errors: list[str]
) -> list[str] | None:
    generation_dir = qc_path.parent
    if generation_dir.parent.name != "generation":
        return None
    analysis_dir = generation_dir.parent.parent / "analysis"
    analysis_path = analysis_dir / "product_analysis.json"
    constraints_path = analysis_dir / "product_fidelity_constraints.json"
    if not analysis_path.is_file() and not constraints_path.is_file():
        return None
    if not analysis_path.is_file() or not constraints_path.is_file():
        errors.append("标准现代 run 必须同时包含 product_analysis.json 和 product_fidelity_constraints.json")
        return []
    try:
        analysis = _load_json(analysis_path)
        constraints = _load_json(constraints_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append("无法读取标准现代 run 的 analysis 或 canonical")
        return []
    if not isinstance(analysis, dict) or not isinstance(constraints, dict):
        errors.append("标准现代 run 的 analysis 和 canonical 必须是 JSON 对象")
        return []
    product_type = analysis.get("confirmed_product_type")
    schema_version = constraints.get("schema_version")
    pendant_question: str | None = None
    if schema_version == 2 and type(schema_version) is int:
        semantics = constraints.get("pendant_semantics")
        if not isinstance(semantics, dict):
            errors.append("v2 canonical 的 pendant_semantics 必须是 JSON 对象")
            return []
        presence = semantics.get("presence")
        count = semantics.get("count")
        layer = semantics.get("layer")
        policy = semantics.get("creation_policy")
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
        if product_type in NECKLACE_PRODUCT_TYPES:
            errors.extend(_validate_v2_necklace_analysis_pendant_fields(analysis))
            expected = (
                ("present", 1, analysis.get("pendant_layer"))
                if product_type == "pendant_necklace"
                else ("absent", 0, None)
            )
            if (presence, count, layer) != expected:
                errors.append("v2 吊坠结构与最终 analysis 不一致")
            errors.extend(_validate_present_pendant_semantic_conflicts(constraints))
        if errors:
            return []
        if product_type in NECKLACE_PRODUCT_TYPES:
            pendant_question = (
                PENDANT_ABSENT_QC_QUESTION
                if presence == "absent"
                else PENDANT_PRESENT_QC_QUESTION.format(count=count, layer=layer)
            )
    elif schema_version != 1 or type(schema_version) is not int:
        errors.append("canonical schema_version 必须为 1 或 2")
        return []
    display_mode = analysis.get("display_mode")
    category_items = CATEGORY_QC_ITEMS.get(product_type)
    mode_items = MODE_QC_ITEMS.get((product_type, display_mode))
    if category_items is None or mode_items is None:
        errors.append("标准现代 run 的产品品类或展示模式不支持 runtime checklist")
        return []
    must_keep = constraints.get("must_keep")
    if not isinstance(must_keep, list):
        errors.append("产品保真约束的 must_keep 必须是列表")
        return []
    questions: list[str] = []
    for item in must_keep:
        if isinstance(item, dict) and isinstance(item.get("qc_question"), str):
            questions.append(item["qc_question"])
    pendant_questions = (pendant_question,) if pendant_question is not None else ()
    combined = (
        COMMON_QC_ITEMS
        + SHARED_QC_ITEMS
        + category_items
        + mode_items
        + tuple(questions)
        + pendant_questions
    )
    return list(dict.fromkeys(combined))


def validate_qc(path: Path) -> list[str]:
    try:
        data = _load_json(path)
    except json.JSONDecodeError:
        return ["qc 文件不是有效 JSON，无法校验"]
    except (OSError, UnicodeError):
        return ["qc 文件无法按 UTF-8 文本读取"]
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["qc 文件必须包含 JSON 对象"]

    status = data.get("status")
    if not isinstance(status, str) or status not in ALLOWED_STATUS:
        errors.append("status 必须是 pass/rerun/reject 字符串")

    passed = _string_list(data, "passed", errors)
    failed = _string_list(data, "failed", errors)
    if not isinstance(data.get("notes"), str):
        errors.append("notes 必须是字符串")
    if isinstance(data.get("passed"), list) and isinstance(data.get("failed"), list):
        if not data["passed"] and not data["failed"]:
            errors.append("passed 和 failed 不能同时为空列表")

    notes = data.get("notes") if isinstance(data.get("notes"), str) else ""
    combined = " ".join(passed + failed) + " " + notes
    critical_failures = _critical_failures(data, errors)
    expected_must_keep = _expected_must_keep_for_qc(path, errors)
    _validate_fidelity_checks(data, status, errors, expected_must_keep)
    expected_runtime = _expected_runtime_checklist_for_qc(path, errors)
    _validate_checklist_checks(data, status, errors, expected_runtime)
    _validate_shared_question_results(data, errors)

    if expected_runtime is None:
        has_generic_source_person_check = _contains_any(combined, SOURCE_PERSON_TERMS)
        if not has_generic_source_person_check:
            if not _contains_any(combined, SOURCE_WRIST_TERMS):
                errors.append("QC 必须记录产品原图手腕迁移检查")
            if not _contains_any(combined, SOURCE_ARM_TERMS):
                errors.append("QC 必须记录产品原图手臂迁移检查")
            if not _contains_any(combined, SOURCE_SKIN_TERMS):
                errors.append("QC 必须记录产品原图皮肤块或皮肤连续性检查")
        if _contains_any(combined, NEGATED_CHECK_TERMS):
            errors.append("QC 不得声明未执行产品图人物局部迁移检查")

    if status == "pass":
        if failed:
            errors.append("status 为 pass 时 failed 必须为空")
        if critical_failures:
            errors.append("存在关键或严重错误时不得标记为 pass")
        if expected_runtime is None and not _contains_any(combined, PASS_CHECK_TERMS):
            errors.append("status 为 pass 时必须明确记录人物局部迁移检查通过")
    if status != "reject" and (
        any(item in REJECT_CRITICAL_FAILURES for item in critical_failures)
        or _contains_any(" ".join(failed), REJECT_FAILURE_TERMS)
    ):
        errors.append("品类、核心结构、多层关系、自动补链或严重穿模错误必须标记为 reject")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：validate_qc_record.py <qc.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"找不到 qc 文件：{path}", file=sys.stderr)
        return 2
    errors = validate_qc(path)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("qc 记录校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
