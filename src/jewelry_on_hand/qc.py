from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import MustKeepConstraint, QcResult
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.product_fidelity import load_product_fidelity_constraints
from jewelry_on_hand.run_paths import write_json


_ALLOWED_STATUS = {"pass", "rerun", "reject"}

_COMMON_QC_ITEMS = (
    "产品颜色、材质、透明度、纹理、反光和比例与产品图一致",
    "元件数量、排列和关键识别点与产品图一致",
    "没有新增、删除或重组产品结构",
    "没有迁移产品图中的人物、皮肤、服装、头发或背景局部",
    "参考图原有首饰已移除",
    "人物、皮肤、手指、脸部和衣服没有明显畸变",
    "没有文字、水印或无关 logo",
)

def build_qc_checklist(
    product_type: ProductType,
    display_mode: DisplayMode,
    must_keep: Iterable[MustKeepConstraint] = (),
) -> tuple[str, ...]:
    if not isinstance(display_mode, DisplayMode):
        raise ValueError("展示模式必须使用 DisplayMode 枚举")
    policy = get_category_policy(product_type)
    policy_items = policy.qc_items_for_mode(display_mode)
    questions = _must_keep_questions(must_keep)
    return tuple(dict.fromkeys(_COMMON_QC_ITEMS + policy_items + questions))


def write_qc_result(
    generation_dir: str | Path,
    status: str,
    passed: Any,
    failed: Any,
    notes: Any,
    fidelity_checks: Any = None,
    critical_failures: Any = None,
) -> Path:
    if status not in _ALLOWED_STATUS:
        raise ValueError("status 必须是 pass/rerun/reject")

    result = QcResult(
        status=status,
        passed=tuple(_normalize_string_list(passed)),
        failed=tuple(_normalize_string_list(failed)),
        notes="" if notes is None else str(notes),
        fidelity_checks=tuple(_normalize_fidelity_checks(fidelity_checks)),
        critical_failures=tuple(_normalize_critical_failures(critical_failures)),
    )
    generation_path = Path(generation_dir)
    constraints_path = _constraints_path_for_generation_dir(generation_path)
    if constraints_path is not None and constraints_path.is_file():
        constraints = load_product_fidelity_constraints(constraints_path)
        _validate_must_keep_coverage(constraints.must_keep, result.fidelity_checks)

    qc_path = generation_path / "qc.json"
    payload = {
        "status": result.status,
        "passed": list(result.passed),
        "failed": list(result.failed),
        "notes": result.notes,
        "fidelity_checks": [check.to_dict() for check in result.fidelity_checks],
    }
    if result.critical_failures:
        payload["critical_failures"] = list(result.critical_failures)
    write_json(qc_path, payload)
    return qc_path


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return [_to_readable_string(value)]
    if isinstance(value, Iterable):
        return [_to_readable_string(item) for item in value]
    return [_to_readable_string(value)]


def _to_readable_string(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return str(value)
    return str(value)


def _normalize_fidelity_checks(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("fidelity_checks 必须是列表")
    return value


def _normalize_critical_failures(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("critical_failures 必须是列表")
    return value


def _must_keep_questions(
    must_keep: Iterable[MustKeepConstraint],
) -> tuple[str, ...]:
    if isinstance(must_keep, (str, bytes, bytearray, Mapping)):
        raise ValueError("must_keep 必须是 MustKeepConstraint 列表")
    questions: list[str] = []
    for item in must_keep:
        if not isinstance(item, MustKeepConstraint):
            raise ValueError("must_keep 只能包含 MustKeepConstraint")
        questions.append(item.qc_question)
    return tuple(questions)


def _constraints_path_for_generation_dir(generation_dir: Path) -> Path | None:
    if generation_dir.parent.name != "generation":
        return None
    return generation_dir.parent.parent / "analysis" / "product_fidelity_constraints.json"


def _validate_must_keep_coverage(
    must_keep: tuple[MustKeepConstraint, ...],
    fidelity_checks: tuple[Any, ...],
) -> None:
    names = [check.name for check in fidelity_checks]
    questions = [check.question for check in fidelity_checks]
    actual_pairs = [(check.name, check.question) for check in fidelity_checks]
    if len(set(actual_pairs)) != len(actual_pairs):
        raise ValueError("fidelity_checks 的 name/question 组合必须唯一")
    if len(fidelity_checks) != len(must_keep):
        raise ValueError("fidelity_checks 数量必须与 must_keep 完全一致")

    expected_names = [item.name for item in must_keep]
    if Counter(names) != Counter(expected_names):
        raise ValueError("fidelity_checks.name 必须与 must_keep.name 完全一致")
    expected_questions = [item.qc_question for item in must_keep]
    if Counter(questions) != Counter(expected_questions):
        raise ValueError(
            "fidelity_checks.question 必须与 must_keep.qc_question 完全一致"
        )
    expected_pairs = {(item.name, item.qc_question) for item in must_keep}
    if set(actual_pairs) != expected_pairs:
        raise ValueError("fidelity_checks 的 name/question 对应关系与 must_keep 不一致")
