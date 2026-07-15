from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
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
)

REFERENCE_QUESTIONS = {
    "framing_preserved": "景别、裁切边界、主体大小和留白是否与参考底图一致",
    "pose_preserved": "身体、手臂、手掌朝向和手指关系是否与参考底图一致",
    "subject_placement_preserved": "人物和目标部位在画面中的位置是否保持",
    "person_preserved": "人物身份、脸、发型和可见身体区域是否保持",
    "clothing_preserved": "服装款式、衣领和遮挡关系是否保持",
    "background_preserved": "背景、道具和环境元素是否保持",
    "lighting_preserved": "光向、明暗、色温和整体色调是否保持",
    "source_jewelry_removed": "参考底图中的全部原首饰是否已清除",
    "replacement_target_preserved": "目标产品是否仅出现在确认的替换位置",
    "single_target_product": "结果中是否只有一件目标产品",
}
REFERENCE_FAILURE_CODES = {
    "framing_preserved": "reference_framing_changed",
    "pose_preserved": "reference_pose_changed",
    "subject_placement_preserved": "replacement_target_changed",
    "person_preserved": "reference_person_changed",
    "clothing_preserved": "reference_clothing_changed",
    "background_preserved": "reference_background_changed",
    "lighting_preserved": "reference_lighting_changed",
    "source_jewelry_removed": "reference_jewelry_leakage",
    "replacement_target_preserved": "replacement_target_changed",
    "single_target_product": "target_product_duplicated",
}
REFERENCE_SOURCES = {
    **{name: "scene_reference" for name in REFERENCE_QUESTIONS},
    "replacement_target_preserved": "confirmed_snapshot",
    "single_target_product": "product_identity",
}
REFERENCE_RERUN_ISSUES = {
    "source_jewelry_removed": {"minor_edge_residue"},
    "replacement_target_preserved": {
        "local_blending_artifact",
        "local_shadow_mismatch",
        "non_core_texture_mismatch",
    },
}
REFERENCE_FAILURE_SET = set(REFERENCE_FAILURE_CODES.values())
COMMON_RUNTIME_QUESTIONS = (
    "产品颜色、材质、透明度、纹理、反光和比例与产品图一致",
    "元件数量、排列和关键识别点与产品图一致",
    "没有新增、删除或重组产品结构",
    "没有迁移产品图中的人物、皮肤、服装、头发或背景局部",
    "参考图原有首饰已移除",
    "人物、皮肤、手指、脸部和衣服没有明显畸变",
    "没有文字、水印或无关 logo",
    "禁止推断不可见扣头或背面结构",
)
CATEGORY_RUNTIME_QUESTIONS = {
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
MODE_RUNTIME_QUESTIONS = {
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
}
MODE_RUNTIME_QUESTIONS[("pendant_necklace", "worn")] = MODE_RUNTIME_QUESTIONS[("necklace", "worn")]
MODE_RUNTIME_QUESTIONS[("pendant_necklace", "hand_held")] = MODE_RUNTIME_QUESTIONS[("necklace", "hand_held")]
MODE_RUNTIME_QUESTIONS[("ring", "worn")] = CATEGORY_RUNTIME_QUESTIONS["ring"]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def _stable_check_id(question: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", question).split())
    return "qc-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _fixed_json(generation_dir: Path, name: str, errors: list[str]) -> dict[str, Any] | None:
    path = generation_dir / name
    if not path.is_file():
        errors.append(f"现代 QC 缺少固化输入：{name}")
        return None
    try:
        value = _load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"现代 QC 固化输入不是有效 UTF-8 JSON：{name}")
        return None
    if not isinstance(value, dict):
        errors.append(f"现代 QC 固化输入必须是 JSON 对象：{name}")
        return None
    return value


def _expected_runtime_questions(
    analysis: dict[str, Any],
    canonical: dict[str, Any],
    errors: list[str],
) -> list[str]:
    category = analysis.get("confirmed_product_type")
    mode = analysis.get("display_mode")
    if (
        not isinstance(category, str)
        or category not in CATEGORY_RUNTIME_QUESTIONS
        or not isinstance(mode, str)
    ):
        errors.append("产品分析无法重建 runtime checklist")
        return []
    questions = list(COMMON_RUNTIME_QUESTIONS)
    questions.extend(CATEGORY_RUNTIME_QUESTIONS[category])
    questions.extend(MODE_RUNTIME_QUESTIONS.get((category, mode), ()))
    must_keep = canonical.get("must_keep")
    if not isinstance(must_keep, list):
        errors.append("canonical.must_keep 必须是列表")
        return []
    for index, item in enumerate(must_keep):
        if not isinstance(item, dict) or not isinstance(item.get("qc_question"), str):
            errors.append(f"canonical.must_keep[{index}].qc_question 无效")
            continue
        questions.append(item["qc_question"])
    semantics = canonical.get("pendant_semantics")
    if category == "pendant_necklace" and isinstance(semantics, dict):
        if semantics.get("presence") == "present":
            questions.extend(
                (
                    f"现有主吊坠数量是否仍为 {semantics.get('count')} 颗，所属层仍为第 "
                    f"{semantics.get('layer')} 层，位置仍为{semantics.get('position')}，朝向仍为"
                    f"{semantics.get('orientation')}，连接仍为{semantics.get('connection')}",
                    "是否禁止新增第二颗吊坠",
                )
            )
    return list(dict.fromkeys(questions))


def _validate_modern_fidelity(
    data: dict[str, Any], canonical: dict[str, Any], status: Any, errors: list[str]
) -> list[str]:
    raw_must_keep = canonical.get("must_keep")
    if not isinstance(raw_must_keep, list):
        errors.append("canonical.must_keep 必须是列表")
        raw_must_keep = []
    expected: list[tuple[str, str]] = []
    for index, item in enumerate(raw_must_keep):
        if not isinstance(item, dict):
            errors.append(f"canonical.must_keep[{index}] 必须是 JSON 对象")
            continue
        name = item.get("name")
        question = item.get("qc_question")
        valid = True
        if not isinstance(name, str) or not name.strip():
            errors.append(f"canonical.must_keep[{index}].name 必须是非空字符串")
            valid = False
        if not isinstance(question, str) or not question.strip():
            errors.append(
                f"canonical.must_keep[{index}].qc_question 必须是非空字符串"
            )
            valid = False
        if valid:
            expected.append((name, question))
    checks = data.get("fidelity_checks")
    if not isinstance(checks, list):
        errors.append("fidelity_checks 必须完整覆盖 canonical.must_keep")
        return []
    pairs: list[tuple[Any, Any]] = []
    results: list[str] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or set(check) != {"name", "question", "result", "notes"}:
            errors.append(f"fidelity_checks[{index}] 字段集合不合法")
            continue
        if any(
            not isinstance(check.get(field), str)
            or (field != "notes" and not check[field].strip())
            for field in ("name", "question", "result", "notes")
        ):
            errors.append(f"fidelity_checks[{index}] 字段类型不合法")
            continue
        pairs.append((check.get("name"), check.get("question")))
        result = check.get("result")
        if not isinstance(result, str) or result not in {"pass", "rerun", "fail"}:
            errors.append(f"fidelity_checks[{index}].result 无效")
        else:
            results.append(result)
    if Counter(pairs) != Counter(expected) or len(pairs) != len(set(pairs)):
        errors.append("fidelity_checks 必须按 name/question 完整唯一覆盖 canonical.must_keep")
    if status == "pass" and any(result != "pass" for result in results):
        errors.append("fidelity_checks 未全部通过时整体状态不能为 pass")
    return results


def _validate_modern_checklist(
    data: dict[str, Any], questions: list[str], status: Any, errors: list[str]
) -> list[str]:
    expected = [(_stable_check_id(question), question) for question in questions]
    checks = data.get("checklist_checks")
    if not isinstance(checks, list):
        errors.append("checklist_checks 必须完整覆盖 runtime checklist")
        return []
    pairs: list[tuple[Any, Any]] = []
    results: list[str] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or set(check) != {"id", "question", "result", "notes"}:
            errors.append(f"checklist_checks[{index}] 字段集合不合法")
            continue
        if any(
            not isinstance(check.get(field), str)
            or (field != "notes" and not check[field].strip())
            for field in ("id", "question", "result", "notes")
        ):
            errors.append(f"checklist_checks[{index}] 字段类型不合法")
            continue
        pairs.append((check.get("id"), check.get("question")))
        result = check.get("result")
        if not isinstance(result, str) or result not in {"pass", "rerun", "fail"}:
            errors.append(f"checklist_checks[{index}].result 无效")
        else:
            results.append(result)
    if Counter(pairs) != Counter(expected) or len(pairs) != len(set(pairs)):
        errors.append("checklist_checks 必须按稳定 id/question 完整唯一覆盖 runtime checklist")
    if status == "pass" and any(result != "pass" for result in results):
        errors.append("checklist_checks 未全部通过时整体状态不能为 pass")
    return results


def _validate_modern_reference(
    data: dict[str, Any], status: Any, errors: list[str]
) -> list[str]:
    checks = data.get("reference_preservation_checks")
    if not isinstance(checks, list):
        errors.append("reference_preservation_checks 必须完整覆盖十项参考底图检查")
        return []
    names: list[Any] = []
    results: list[str] = []
    required_failures: set[str] = set()
    evidence_fingerprints: list[tuple[str, str]] = []
    for index, check in enumerate(checks):
        label = f"reference_preservation_checks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{label} 必须是 JSON 对象")
            continue
        required_fields = {"name", "question", "result", "issue_code", "notes", "evidence"}
        if set(check) != required_fields:
            errors.append(f"{label} 字段集合不合法，notes 不能代替 evidence")
            continue
        name = check.get("name")
        if not isinstance(name, str):
            errors.append(f"{label}.name 必须是字符串")
            continue
        names.append(name)
        if name not in REFERENCE_QUESTIONS:
            errors.append(f"{label}.name 未知：{name}")
            continue
        if check.get("question") != REFERENCE_QUESTIONS[name]:
            errors.append(f"{label}.question 与固定问题不一致")
        result = check.get("result")
        issue = check.get("issue_code")
        if not isinstance(result, str) or result not in {"pass", "rerun", "fail"}:
            errors.append(f"{label}.result 必须是 pass/rerun/fail")
            continue
        results.append(result)
        if result == "pass" and issue is not None:
            errors.append(f"{label} pass 时 issue_code 必须为 null")
        elif result == "rerun" and (
            not isinstance(issue, str)
            or issue not in REFERENCE_RERUN_ISSUES.get(name, set())
        ):
            errors.append(f"{label} rerun issue_code 未受控")
        elif result == "fail":
            expected_issue = REFERENCE_FAILURE_CODES[name]
            if issue != expected_issue:
                errors.append(f"{label} fail 时 issue_code 必须为 {expected_issue}")
            else:
                required_failures.add(expected_issue)
        evidence = check.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"{label}.evidence 必须是 JSON 对象")
            continue
        expected_evidence_fields = {"comparison_source", "region", "observation"}
        if name == "source_jewelry_removed":
            expected_evidence_fields |= {
                "source_jewelry_subject_visible",
                "residual_scope",
            }
        if set(evidence) != expected_evidence_fields:
            errors.append(f"{label}.evidence 字段集合不合法")
        for field in ("comparison_source", "region", "observation"):
            if not isinstance(evidence.get(field), str) or not evidence[field].strip():
                errors.append(f"{label}.evidence.{field} 必须是非空字符串")
        if evidence.get("comparison_source") != REFERENCE_SOURCES[name]:
            errors.append(f"{label}.evidence.comparison_source 必须为 {REFERENCE_SOURCES[name]}")
        if isinstance(evidence.get("region"), str) and isinstance(evidence.get("observation"), str):
            evidence_fingerprints.append((evidence["region"], evidence["observation"]))
        if name == "source_jewelry_removed":
            visible = evidence.get("source_jewelry_subject_visible")
            scope = evidence.get("residual_scope")
            if (
                type(visible) is not bool
                or not isinstance(scope, str)
                or scope
                not in {
                    "none",
                    "edge_pixels",
                    "contact_shadow",
                    "subject_or_large_area",
                }
            ):
                errors.append(f"{label}.evidence 缺少合法原首饰残留 facts")
            if result == "pass" and (visible is not False or scope != "none"):
                errors.append(f"{label} pass 与残留 facts 不一致")
            if result == "rerun" and (
                visible is not False
                or not isinstance(scope, str)
                or scope not in {"edge_pixels", "contact_shadow"}
            ):
                errors.append(f"{label} rerun 存在明显泄漏，不能伪装为局部修复")
            if result == "fail" and visible is not True:
                errors.append(f"{label} fail 与残留 facts 不一致")
    if Counter(names) != Counter(REFERENCE_QUESTIONS.keys()) or len(names) != len(set(names)):
        errors.append("reference_preservation_checks 必须完整唯一覆盖十项固定检查")
    if len(evidence_fingerprints) == len(REFERENCE_QUESTIONS) and len(set(evidence_fingerprints)) == 1:
        errors.append("十项 reference evidence 不能使用统一伪证据")
    critical = data.get("critical_failures", [])
    normalized_critical: list[str] = []
    if not isinstance(critical, list):
        errors.append("critical_failures 必须是列表")
        critical = []
    else:
        allowed_critical = ALLOWED_CRITICAL_FAILURES | REFERENCE_FAILURE_SET
        normalized_critical = [item for item in critical if isinstance(item, str)]
        if len(normalized_critical) != len(critical):
            errors.append("critical_failures 只能包含字符串严重码")
        unknown = [item for item in normalized_critical if item not in allowed_critical]
        if unknown:
            errors.append("critical_failures 包含未知严重码：" + "、".join(map(str, unknown)))
        if len(normalized_critical) != len(set(normalized_critical)):
            errors.append("critical_failures 不能包含重复严重码")
    actual_reference_failures = set(normalized_critical).intersection(REFERENCE_FAILURE_SET)
    if actual_reference_failures != required_failures:
        errors.append("reference fail 与 critical_failures 严重码映射不一致")
    if status == "pass" and any(result != "pass" for result in results):
        errors.append("reference checks 未全部通过时整体状态不能为 pass")
    if any(result == "fail" for result in results) and status != "reject":
        errors.append("reference fail 时整体状态必须为 reject")
    return results


def _validate_modern_qc(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    generation_dir = path.parent
    analysis = _fixed_json(generation_dir, "product-analysis.json", errors)
    canonical = _fixed_json(generation_dir, "product-fidelity-constraints.json", errors)
    _fixed_json(generation_dir, "reference-composition-snapshot.json", errors)
    status = data.get("status")
    if not isinstance(status, str) or status not in ALLOWED_STATUS:
        errors.append("status 必须是 pass/rerun/reject")
    required_fields = {
        "status",
        "passed",
        "failed",
        "notes",
        "fidelity_checks",
        "checklist_checks",
        "reference_preservation_checks",
    }
    allowed_fields = required_fields | {"critical_failures"}
    if not required_fields <= set(data) or not set(data) <= allowed_fields:
        errors.append("现代 qc.json 字段集合不合法")
    passed = data.get("passed")
    failed = data.get("failed")
    if not isinstance(passed, list) or any(not isinstance(item, str) or not item.strip() for item in passed):
        errors.append("passed 必须是非空字符串列表")
    if not isinstance(failed, list) or any(not isinstance(item, str) or not item.strip() for item in failed):
        errors.append("failed 必须是非空字符串列表")
    if not isinstance(data.get("notes"), str):
        errors.append("notes 必须是字符串，且不能替代结构化 evidence")
    if status == "pass" and failed:
        errors.append("status 为 pass 时 failed 必须为空")
    if analysis is None or canonical is None:
        return errors
    source = canonical.get("source")
    if not isinstance(source, dict):
        errors.append("canonical.source 必须是 JSON 对象")
    else:
        expected_digest = hashlib.sha256(
            json.dumps(
                analysis,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if source.get("product_analysis_sha256") != expected_digest:
            errors.append("canonical.source.product_analysis_sha256 与固化产品分析不一致")
    fidelity_results = _validate_modern_fidelity(data, canonical, status, errors)
    questions = _expected_runtime_questions(analysis, canonical, errors)
    checklist_results = _validate_modern_checklist(data, questions, status, errors)
    reference_results = _validate_modern_reference(data, status, errors)
    all_results = fidelity_results + checklist_results + reference_results
    raw_fidelity_checks = data.get("fidelity_checks")
    if not isinstance(raw_fidelity_checks, list):
        raw_fidelity_checks = []
    raw_checklist_checks = data.get("checklist_checks")
    if not isinstance(raw_checklist_checks, list):
        raw_checklist_checks = []
    fidelity_by_question = {
        item.get("question"): item.get("result")
        for item in raw_fidelity_checks
        if isinstance(item, dict) and isinstance(item.get("question"), str)
    }
    checklist_by_question = {
        item.get("question"): item.get("result")
        for item in raw_checklist_checks
        if isinstance(item, dict) and isinstance(item.get("question"), str)
    }
    for question in fidelity_by_question.keys() & checklist_by_question.keys():
        if fidelity_by_question[question] != checklist_by_question[question]:
            errors.append("fidelity_checks 与 checklist_checks 同一问题的 result 必须一致")
    raw_critical = data.get("critical_failures", [])
    critical_failures = (
        [item for item in raw_critical if isinstance(item, str)]
        if isinstance(raw_critical, list)
        else []
    )
    reject_critical = REJECT_CRITICAL_FAILURES | REFERENCE_FAILURE_SET
    if status == "pass" and critical_failures:
        errors.append("存在关键 QC critical_failures 时 overall status 不能为 pass")

    expected_status: str | None
    if any(result == "fail" for result in all_results) or any(
        failure in reject_critical for failure in critical_failures
    ):
        expected_status = "reject"
    elif any(result == "rerun" for result in all_results):
        expected_status = "rerun"
    elif critical_failures:
        expected_status = None
    else:
        expected_status = "pass"
    if (
        expected_status is not None
        and isinstance(status, str)
        and status in ALLOWED_STATUS
        and status != expected_status
    ):
        errors.append(
            f"三层 QC 与 critical_failures 合并后的最高严重度要求 overall status 为 {expected_status}"
        )
    return errors


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

    if (path.parent / "input-manifest.json").is_file():
        return _validate_modern_qc(path, data)

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
        if not _contains_any(combined, PASS_CHECK_TERMS):
            errors.append("status 为 pass 时必须明确记录人物局部迁移检查通过")
    if status != "reject" and (
        any(item in REJECT_CRITICAL_FAILURES for item in critical_failures)
        or _contains_any(" ".join(failed), REJECT_FAILURE_TERMS)
    ):
        errors.append("品类、核心结构、多层关系、自动补链或严重穿模错误必须标记为 reject")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] in {"-h", "--help"}:
        print("用法：validate_qc_record.py <qc.json>")
        return 0
    if len(argv) != 2:
        print("用法：validate_qc_record.py <qc.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"找不到 qc 文件：{path}", file=sys.stderr)
        return 2
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"qc 文件不是有效 UTF-8 JSON：{exc}", file=sys.stderr)
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
