from __future__ import annotations

import hashlib
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import (
    MustKeepConstraint,
    ProductAnalysis,
    ProductFidelityConstraints,
    QcResult,
)
from jewelry_on_hand.product_fidelity import (
    load_product_fidelity_constraints,
    validate_product_fidelity_constraints,
)
from jewelry_on_hand.product_types import ProductType
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
    product_type: ProductType | None = None,
    display_mode: DisplayMode | None = None,
    must_keep: Iterable[MustKeepConstraint] | None = None,
    *,
    product_analysis: ProductAnalysis | None = None,
    fidelity_constraints: ProductFidelityConstraints | None = None,
) -> tuple[str, ...]:
    modern_call = product_analysis is not None or fidelity_constraints is not None
    pendant_questions: tuple[str, ...] = ()
    if modern_call:
        if product_analysis is None or fidelity_constraints is None:
            raise ValueError(
                "现代 QC 必须同时提供 product_analysis 与 fidelity_constraints"
            )
        validate_product_fidelity_constraints(
            product_analysis,
            fidelity_constraints,
        )
        if not fidelity_constraints.is_confirmed_for_generation():
            raise ValueError(
                "产品保真约束 review_status 尚未确认，不得用于生成 QC"
            )

        analysis_product_type = product_analysis.normalized_product_type
        if product_type is not None and product_type is not analysis_product_type:
            raise ValueError("QC 参数 product_type 与 ProductAnalysis 品类不一致")
        if display_mode is not None and display_mode is not product_analysis.display_mode:
            raise ValueError("QC 参数 display_mode 与 ProductAnalysis 展示模式不一致")

        canonical_must_keep = fidelity_constraints.must_keep
        if must_keep is not None:
            provided_must_keep = _normalize_must_keep(must_keep)
            if provided_must_keep != canonical_must_keep:
                raise ValueError("QC 参数 must_keep 与产品保真约束不一致")
        product_type = analysis_product_type
        display_mode = product_analysis.display_mode
        must_keep_items = canonical_must_keep
        pendant_questions = _structured_pendant_questions(
            product_type,
            fidelity_constraints,
        )
    else:
        if product_type is None or display_mode is None:
            raise ValueError("兼容 QC 必须提供 product_type 与 display_mode")
        must_keep_items = _normalize_must_keep(must_keep or ())

    if not isinstance(product_type, ProductType):
        raise ValueError("产品品类必须使用 ProductType 枚举")
    if not isinstance(display_mode, DisplayMode):
        raise ValueError("展示模式必须使用 DisplayMode 枚举")
    policy = get_category_policy(product_type)
    policy_items = policy.qc_items_for_mode(display_mode)
    if modern_call and product_type is not ProductType.PENDANT_NECKLACE:
        policy_items = tuple(item for item in policy_items if "吊坠" not in item)
    questions = _must_keep_questions(must_keep_items)
    return tuple(
        dict.fromkeys(
            _COMMON_QC_ITEMS + policy_items + questions + pendant_questions
        )
    )


def qc_check_id(question: str) -> str:
    if not isinstance(question, str):
        raise ValueError("QC 问题必须是非空字符串")
    normalized = " ".join(unicodedata.normalize("NFKC", question).split())
    if not normalized:
        raise ValueError("QC 问题必须是非空字符串")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"qc-{digest}"


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


def _normalize_must_keep(
    must_keep: Iterable[MustKeepConstraint],
) -> tuple[MustKeepConstraint, ...]:
    if isinstance(must_keep, (str, bytes, bytearray, Mapping)):
        raise ValueError("must_keep 必须是 MustKeepConstraint 列表")
    items = tuple(must_keep)
    if any(not isinstance(item, MustKeepConstraint) for item in items):
        raise ValueError("must_keep 只能包含 MustKeepConstraint")
    return items


def _must_keep_questions(
    must_keep: Iterable[MustKeepConstraint],
) -> tuple[str, ...]:
    return tuple(item.qc_question for item in _normalize_must_keep(must_keep))


def _structured_pendant_questions(
    product_type: ProductType,
    constraints: ProductFidelityConstraints,
) -> tuple[str, ...]:
    if product_type is not ProductType.PENDANT_NECKLACE:
        return ()
    semantics = constraints.pendant_semantics
    if semantics is None or semantics.presence != "present":
        raise ValueError("带链吊坠 QC 缺少可用的主吊坠结构")
    return (
        f"现有主吊坠数量是否仍为 {semantics.count} 颗，所属层仍为第 "
        f"{semantics.layer} 层，位置仍为{semantics.position}，朝向仍为"
        f"{semantics.orientation}，连接仍为{semantics.connection}",
        "是否禁止新增第二颗吊坠",
    )


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


__all__ = [
    "build_qc_checklist",
    "qc_check_id",
    "write_qc_result",
]
