from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import MustKeepConstraint, QcResult
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.run_paths import write_json


_ALLOWED_STATUS = {"pass", "rerun", "reject"}

_COMMON_QC_ITEMS = (
    "产品颜色、材质、透明度、纹理和比例与产品图一致",
    "元件数量、排列和关键识别点与产品图一致",
    "没有新增、删除或重组产品结构",
    "没有迁移产品图中的人物、皮肤、服装、头发或背景局部",
    "参考图原有首饰已移除",
    "人物、皮肤、手指、脸部和衣服没有明显畸变",
    "没有文字、水印或无关 logo",
)

_BRACELET_WORN_QC_ITEMS = (
    "手串贴合手腕，遮挡、松紧和接触阴影自然",
    "手指、手掌、手腕和皮肤纹理自然",
    "没有迁移产品图中的粗手腕、局部手臂或皮肤块",
)

_NECKLACE_WORN_QC_ITEMS = (
    "层数、上下顺序、长度等级和层间落差与产品图一致",
    "吊坠所属层、位置、朝向和连接关系与产品图一致",
    "链条真实绕颈并在胸前自然垂落",
    "链条没有穿肤、穿衣、穿发、悬空或陷入身体",
    "衣领和头发遮挡符合真实前后关系且未遮掉主要结构",
    "多层链没有错误交叉、合并或复制",
    "没有迁移产品图中的颈部、胸部、衣服、头发或皮肤块",
)

_NECKLACE_HAND_HELD_QC_ITEMS = (
    "产品结构完整且关键结构可辨认",
    "手部与链条接触真实，链条自然垂落",
    "手指没有穿透链条或吊坠",
    "吊坠和关键结构没有被不合理遮挡",
    "产品比例合理，没有因近景明显放大或缩小",
    "没有虚构佩戴链路、自动补链或补充不存在的结构",
)

_MODE_QC_ITEMS = {
    (ProductType.BRACELET, DisplayMode.WORN): _BRACELET_WORN_QC_ITEMS,
    (ProductType.NECKLACE, DisplayMode.WORN): _NECKLACE_WORN_QC_ITEMS,
    (ProductType.PENDANT_NECKLACE, DisplayMode.WORN): _NECKLACE_WORN_QC_ITEMS,
    (ProductType.NECKLACE, DisplayMode.HAND_HELD): _NECKLACE_HAND_HELD_QC_ITEMS,
    (
        ProductType.PENDANT_NECKLACE,
        DisplayMode.HAND_HELD,
    ): _NECKLACE_HAND_HELD_QC_ITEMS,
}


def build_qc_checklist(
    product_type: ProductType,
    display_mode: DisplayMode,
    must_keep: Iterable[MustKeepConstraint] = (),
) -> tuple[str, ...]:
    if not isinstance(display_mode, DisplayMode):
        raise ValueError("展示模式必须使用 DisplayMode 枚举")
    policy = get_category_policy(product_type)
    if display_mode not in policy.supported_modes:
        raise ValueError(
            f"{policy.category_name}不支持 {display_mode.value} 展示模式的 QC"
        )

    try:
        mode_items = _MODE_QC_ITEMS[(product_type, display_mode)]
    except KeyError as exc:
        raise ValueError("当前品类和展示模式没有可用的 QC 清单") from exc
    questions = _must_keep_questions(must_keep)
    return tuple(dict.fromkeys(_COMMON_QC_ITEMS + policy.basic_qc_items + mode_items + questions))


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
    qc_path = Path(generation_dir) / "qc.json"
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
