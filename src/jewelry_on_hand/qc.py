from __future__ import annotations

import hashlib
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Set
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
from jewelry_on_hand.qc_review import build_reference_preservation_checklist
from jewelry_on_hand.reference_composition import ReferenceCompositionSnapshot
from jewelry_on_hand.run_paths import read_json, write_json


_ALLOWED_STATUS = {"pass", "rerun", "reject"}
_PENDANT_TERMS = ("吊坠", "主吊坠", "链坠", "流苏", "坠子")

_COMMON_QC_ITEMS = (
    "产品颜色、材质、透明度、纹理、反光和比例与产品图一致",
    "元件数量、排列和关键识别点与产品图一致",
    "没有新增、删除或重组产品结构",
    "没有迁移产品图中的人物、皮肤、服装、头发或背景局部",
    "参考图原有首饰已移除",
    "人物、皮肤、手指、脸部和衣服没有明显畸变",
    "没有文字、水印或无关 logo",
)


def _normalize_question(question: str) -> str:
    if not isinstance(question, str):
        raise ValueError("QC 问题必须是非空字符串")
    normalized = unicodedata.normalize("NFKC", question)
    normalized = " ".join(normalized.split())
    if not normalized or all(
        character.isspace() or unicodedata.category(character) == "Cf"
        for character in normalized
    ):
        raise ValueError("QC 问题必须是非空字符串")
    return normalized


def _semantic_view(question: str) -> str:
    normalized = _normalize_question(question)
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Cf"
    )


class QCChecklistItem(str):
    __slots__ = ()

    def __new__(cls, question: str) -> "QCChecklistItem":
        _normalize_question(question)
        return super().__new__(cls, question)

    @property
    def id(self) -> str:
        return qc_check_id(self)

    @property
    def question(self) -> str:
        return str(self)


def build_qc_checklist(
    product_type: ProductType | None = None,
    display_mode: DisplayMode | None = None,
    must_keep: Iterable[MustKeepConstraint] | None = None,
    *,
    product_analysis: ProductAnalysis | None = None,
    fidelity_constraints: ProductFidelityConstraints | None = None,
) -> tuple[QCChecklistItem, ...]:
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
        _validate_non_pendant_canonical(product_type, fidelity_constraints)
        pendant_questions = _structured_pendant_questions(
            product_type,
            fidelity_constraints,
        )
    else:
        if product_type is None or display_mode is None:
            raise ValueError("兼容 QC 必须提供 product_type 与 display_mode")
        must_keep_items = _normalize_must_keep(
            () if must_keep is None else must_keep,
            sort_items=True,
        )

    if not isinstance(product_type, ProductType):
        raise ValueError("产品品类必须使用 ProductType 枚举")
    if not isinstance(display_mode, DisplayMode):
        raise ValueError("展示模式必须使用 DisplayMode 枚举")
    policy = get_category_policy(product_type)
    policy_items = policy.qc_items_for_mode(display_mode)
    if modern_call and product_type is not ProductType.PENDANT_NECKLACE:
        policy_items = tuple(item for item in policy_items if "吊坠" not in item)
    questions = _must_keep_questions(must_keep_items)
    return _build_checklist_items(
        _COMMON_QC_ITEMS + policy_items + questions + pendant_questions
    )


def qc_check_id(question: str) -> str:
    normalized = _normalize_question(question)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"qc-{digest}"


def write_qc_result(
    generation_dir: str | Path,
    status: str,
    passed: Any,
    failed: Any,
    notes: Any,
    fidelity_checks: Any = None,
    checklist_checks: Any = None,
    reference_preservation_checks: Any = None,
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
        checklist_checks=tuple(_normalize_checklist_checks(checklist_checks)),
        reference_preservation_checks=tuple(
            _normalize_reference_preservation_checks(
                reference_preservation_checks
            )
        ),
        critical_failures=tuple(_normalize_critical_failures(critical_failures)),
    )
    generation_path = Path(generation_dir)
    if (generation_path / "input-manifest.json").is_file():
        _validate_modern_qc_layers(generation_path, result)
    else:
        constraints_path = _constraints_path_for_generation_dir(generation_path)
        if constraints_path is not None and constraints_path.is_file():
            constraints = load_product_fidelity_constraints(constraints_path)
            _validate_must_keep_coverage(
                constraints.must_keep,
                result.fidelity_checks,
            )

    qc_path = generation_path / "qc.json"
    payload = {
        "status": result.status,
        "passed": list(result.passed),
        "failed": list(result.failed),
        "notes": result.notes,
        "fidelity_checks": [check.to_dict() for check in result.fidelity_checks],
    }
    if result.reference_preservation_checks:
        payload["reference_preservation_checks"] = [
            check.to_dict() for check in result.reference_preservation_checks
        ]
    if result.checklist_checks:
        payload["checklist_checks"] = [
            check.to_dict() for check in result.checklist_checks
        ]
    if result.critical_failures:
        payload["critical_failures"] = list(result.critical_failures)
    write_json(qc_path, payload)
    return qc_path


def _validate_modern_qc_layers(generation_path: Path, result: QcResult) -> None:
    analysis_path = generation_path / "product-analysis.json"
    constraints_path = generation_path / "product-fidelity-constraints.json"
    snapshot_path = generation_path / "reference-composition-snapshot.json"
    for path, label in (
        (analysis_path, "产品分析"),
        (constraints_path, "产品保真约束"),
        (snapshot_path, "参考构图快照"),
    ):
        if not path.is_file():
            raise ValueError(f"现代 QC 缺少{label}固化副本：{path.name}")

    analysis = ProductAnalysis.from_dict(read_json(analysis_path))
    constraints = load_product_fidelity_constraints(constraints_path)
    snapshot = ReferenceCompositionSnapshot.from_dict(read_json(snapshot_path))
    _validate_must_keep_coverage(constraints.must_keep, result.fidelity_checks)
    expected_checklist = build_qc_checklist(
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )
    _validate_checklist_coverage(expected_checklist, result.checklist_checks)
    _validate_reference_preservation_coverage(
        snapshot,
        result.reference_preservation_checks,
    )
    _validate_cross_layer_results(
        result.fidelity_checks,
        result.checklist_checks,
    )


def _validate_reference_preservation_coverage(
    snapshot: ReferenceCompositionSnapshot,
    checks: tuple[Any, ...],
) -> None:
    expected = build_reference_preservation_checklist(snapshot)
    actual = [(check.name, check.question) for check in checks]
    if len(actual) != len(set(actual)):
        raise ValueError("reference_preservation_checks 的 name/question 必须唯一")
    expected_names = [name for name, _question in expected]
    actual_names = [check.name for check in checks]
    if Counter(actual_names) != Counter(expected_names):
        raise ValueError(
            "reference_preservation_checks 必须按固定 name 完整覆盖，且不得包含未知项"
        )
    if Counter(actual) != Counter(expected):
        raise ValueError(
            "reference_preservation_checks.question 必须与预期问题完全一致"
        )
    for check in checks:
        if check.result == "rerun" and check.name != "source_jewelry_removed":
            raise ValueError(
                "构图、人物、姿势、服装、背景、光线和替换位置问题不得使用 rerun"
            )
        if check.name == "source_jewelry_removed" and check.result == "rerun":
            if any(
                term in check.notes
                for term in ("肉眼可辨", "主体残留", "完整珠体", "明显残留", "大面积")
            ):
                raise ValueError(
                    "肉眼可辨的原首饰主体残留必须使用 "
                    "reference_jewelry_leakage 并标记 reject"
                )


def _validate_checklist_coverage(
    expected_questions: tuple[QCChecklistItem, ...],
    checks: tuple[Any, ...],
) -> None:
    expected = [(item.id, item.question) for item in expected_questions]
    actual = [(check.id, check.question) for check in checks]
    if len(actual) != len(set(actual)):
        raise ValueError("checklist_checks 的 id/question 必须唯一")
    if len(actual) != len(expected):
        raise ValueError("checklist_checks 必须完整覆盖 runtime checklist")
    if Counter(actual) != Counter(expected):
        raise ValueError(
            "checklist_checks 必须按稳定 id 与精确 question 完整覆盖 runtime checklist"
        )


def _validate_cross_layer_results(
    fidelity_checks: tuple[Any, ...],
    checklist_checks: tuple[Any, ...],
) -> None:
    checklist_by_question = {
        check.question: check.result for check in checklist_checks
    }
    for check in fidelity_checks:
        checklist_result = checklist_by_question.get(check.question)
        if checklist_result is not None and checklist_result != check.result:
            raise ValueError(
                "fidelity_checks 与 checklist_checks 对同一 question 的 result 必须一致"
            )


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


def _normalize_checklist_checks(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("checklist_checks 必须是列表")
    return value


def _normalize_reference_preservation_checks(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("reference_preservation_checks 必须是列表")
    return value


def _normalize_critical_failures(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("critical_failures 必须是列表")
    return value


def _normalize_must_keep(
    must_keep: Iterable[MustKeepConstraint],
    *,
    sort_items: bool = False,
) -> tuple[MustKeepConstraint, ...]:
    if isinstance(must_keep, (str, bytes, bytearray, Mapping)):
        raise ValueError("must_keep 必须是 MustKeepConstraint 列表")
    if isinstance(must_keep, Set):
        raise ValueError(
            "must_keep 必须是有序的 MustKeepConstraint 列表，不接受无序集合"
        )
    try:
        items = tuple(must_keep)
    except TypeError as exc:
        raise ValueError("must_keep 必须是 MustKeepConstraint 列表") from exc
    if any(not isinstance(item, MustKeepConstraint) for item in items):
        raise ValueError("must_keep 只能包含 MustKeepConstraint")
    if sort_items:
        return tuple(sorted(items, key=_must_keep_sort_key))
    return items


def _must_keep_sort_key(
    item: MustKeepConstraint,
) -> tuple[Any, ...]:
    string_fields = (
        "name",
        "source_text",
        "normalized_keyword",
        "location",
        "visual_shape",
        "relationship",
        "qc_question",
    )
    values: list[str] = []
    for field_name in string_fields:
        value = getattr(item, field_name)
        if not isinstance(value, str):
            raise ValueError(f"must_keep.{field_name} 必须是字符串")
        values.append(value)
    if not isinstance(item.forbid, (tuple, list)) or any(
        not isinstance(value, str) for value in item.forbid
    ):
        raise ValueError("must_keep.forbid 必须是字符串列表")
    return (
        *values[:6],
        tuple(item.forbid),
        values[6],
    )


def _must_keep_questions(
    must_keep: tuple[MustKeepConstraint, ...],
) -> tuple[str, ...]:
    return tuple(item.qc_question for item in must_keep)


def _build_checklist_items(
    questions: tuple[str, ...],
) -> tuple[QCChecklistItem, ...]:
    items: list[QCChecklistItem] = []
    normalized_questions: set[str] = set()
    id_to_question: dict[str, str] = {}
    for question in questions:
        normalized = _normalize_question(question)
        if normalized in normalized_questions:
            continue
        item = QCChecklistItem(question)
        check_id = item.id
        previous = id_to_question.get(check_id)
        if previous is not None and previous != normalized:
            raise ValueError("不同 QC 问题生成了相同稳定 ID，发生碰撞")
        normalized_questions.add(normalized)
        id_to_question[check_id] = normalized
        items.append(item)
    return tuple(items)


def _validate_non_pendant_canonical(
    product_type: ProductType,
    constraints: ProductFidelityConstraints,
) -> None:
    if product_type is ProductType.PENDANT_NECKLACE:
        return
    for item in constraints.must_keep:
        question = _semantic_view(item.qc_question)
        if any(term in question for term in _PENDANT_TERMS):
            raise ValueError(
                f"产品品类 {product_type.value} 与吊坠要求冲突：{item.qc_question}"
            )


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
    "QCChecklistItem",
    "build_qc_checklist",
    "qc_check_id",
    "write_qc_result",
]
