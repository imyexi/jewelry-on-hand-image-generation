from __future__ import annotations

import json
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
}
REJECT_CRITICAL_FAILURES = {
    "category_mismatch",
    "core_structure_missing",
    "multi_layer_restructured",
    "auto_chain_added",
    "severe_intersection",
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
