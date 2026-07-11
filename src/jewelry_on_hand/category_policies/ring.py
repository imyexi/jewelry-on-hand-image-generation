import re

from jewelry_on_hand.category_policies.base import (
    CategoryPolicy,
    ControlledLevel,
    PromptFragments,
    ReferenceAdaptation,
    SHARED_BASIC_QC_ITEMS,
    contains_any,
    contains_unnegated_any,
    parse_confidence_level,
    parse_risk_level,
    parse_visibility_level,
)
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.ring_attributes import FingerPosition, HandSide


RING_IMAGE_ONE_ROLE = (
    "内部图1：自动参考图，只提供手部姿势、手模、构图、光线和场景；"
    "内部图1中的戒指必须移除且不提供产品身份。"
)

RING_BASIC_QC_ITEMS = (
    "画面中只有一枚目标戒指",
    "戒指位于确认后的左右手和目标手指根部",
    "戒圈、戒面、主石、镶嵌和装饰排列与产品图可见结构一致",
    "戒圈自然环绕手指且前后遮挡、接触和阴影真实",
    "没有迁移产品图中的手、皮肤、指甲、掌纹或背景局部",
)


def _build_ring_prompt_fragments(product: ProductAnalysis) -> PromptFragments:
    hand_name = product.hand_side.display_name
    finger_name = product.finger_position.display_name
    return PromptFragments(
        image_one_role=RING_IMAGE_ONE_ROLE,
        category_fidelity=(
            "只生成一枚目标戒指；戒圈粗细、开口、戒面、主石、镶嵌、颜色、"
            "朝向和装饰排列必须与内部图2肉眼可见结构一致。"
        ),
        display_mode=(
            f"真人佩戴：戒指必须佩戴在已确认的{hand_name}{finger_name}根部，"
            "不得静默换手、换指或改成指关节/跨指佩戴。"
        ),
        occlusion_physics=(
            "戒圈必须自然环绕手指，前侧可见部分与背侧遮挡关系真实，并具有"
            "合理接触和阴影；不得悬浮、贴片、嵌入皮肤或穿透手指。"
        ),
        prohibitions=(
            "不得迁移内部图2中的手、皮肤、指甲、掌纹或背景局部；"
            "不得把不可见戒圈背面或镶嵌背面补写成确定结构。"
        ),
    )


def _evaluate_ring_reference(
    product: ProductAnalysis, row: ReferenceRow
) -> ReferenceAdaptation:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []

    if _annotation_matches(row.applicable_product_types, {"ring", "戒指", "指环"}):
        score += 30
        reasons.append("戒指适用品类匹配")
    else:
        risks.append("缺少明确的戒指适用品类标注")

    if _annotation_matches(row.applicable_display_modes, {"worn", "佩戴", "真人佩戴"}):
        score += 25
        reasons.append("戒指展示模式匹配真人佩戴")
    else:
        risks.append("缺少明确的戒指适用展示模式标注")

    hand_visibility = parse_visibility_level(row.hand_visibility)
    if hand_visibility not in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}:
        risks.append("手部可见度不足，无法建立真实戒指佩戴关系")
    else:
        score += 12
        reasons.append("手部清晰可见")

    product_visibility = parse_visibility_level(row.product_visibility)
    if product_visibility not in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}:
        risks.append("戒指预计展示面积不足")
    else:
        score += 12
        reasons.append("戒指预计展示面积充足")

    if not _target_finger_visible(product.finger_position, row.visible_fingers):
        risks.append("目标手指不可见或可见手指标注缺失")
    else:
        score += 20
        reasons.append("目标手指完整可见")

    ring_face_visibility = parse_visibility_level(row.ring_face_visibility)
    if ring_face_visibility not in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}:
        risks.append("戒面可见度不足")
    else:
        score += 15
        reasons.append("戒面可见度充足")

    finger_separation = parse_visibility_level(row.finger_separation)
    if finger_separation not in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}:
        risks.append("手指分离度不足")
    else:
        score += 10
        reasons.append("手指分离度适合戒指展示")

    finger_occlusion = parse_risk_level(row.finger_occlusion_risk)
    if finger_occlusion not in {ControlledLevel.LOW, ControlledLevel.MEDIUM}:
        risks.append("手指遮挡风险过高或标注缺失")
    else:
        score += 8
        reasons.append("手指遮挡风险可控")

    crop_risk = parse_risk_level(row.crop_risk)
    if crop_risk not in {ControlledLevel.LOW, ControlledLevel.MEDIUM}:
        risks.append("目标手指或戒指区域裁切风险过高")
    else:
        score += 8
        reasons.append("目标手指裁切风险可控")

    normalized_side = row.hand_side.strip().lower()
    if normalized_side not in {HandSide.LEFT.value, HandSide.RIGHT.value}:
        risks.append("缺少有效的参考图左右手标注")
    elif normalized_side == product.hand_side.value:
        score += 8
        reasons.append("参考图左右手与确认指位一致")
    else:
        reasons.append("参考图为相反手，仅复用姿势且不覆盖确认指位")

    if not row.hand_orientation.strip():
        risks.append("缺少手部朝向标注")
    else:
        score += 5
        reasons.append("手部朝向已明确标注")

    selection_tier = _selection_tier(row, risks)
    return ReferenceAdaptation(
        eligible=not risks and selection_tier is not None,
        score_adjustment=score,
        reasons=tuple(reasons),
        risks=tuple(risks),
        ignored_reference_jewelry=_ignored_reference_jewelry(row),
        selection_tier=selection_tier or 0,
    )


def _annotation_matches(value: str, aliases: set[str]) -> bool:
    parts = {
        part.strip().lower()
        for part in re.split(r"[,，、;/|]+", value)
        if part.strip()
    }
    return bool(parts & aliases)


def _target_finger_visible(
    finger_position: FingerPosition, visible_fingers: str
) -> bool:
    aliases = {
        FingerPosition.THUMB: {"thumb", "拇指", "大拇指"},
        FingerPosition.INDEX: {"index", "index_finger", "食指"},
        FingerPosition.MIDDLE: {"middle", "middle_finger", "中指"},
        FingerPosition.RING: {"ring", "ring_finger", "无名指"},
        FingerPosition.LITTLE: {"little", "little_finger", "小指", "尾指"},
    }
    return _annotation_matches(visible_fingers, aliases[finger_position])


def _selection_tier(row: ReferenceRow, risks: list[str]) -> int | None:
    confidence = parse_confidence_level(row.confidence)
    priority = contains_any(row.default_strategy, ("优先使用", "可优先", "优先")) and not contains_any(
        row.default_strategy, ("不优先", "不建议", "谨慎使用")
    )
    relaxed = contains_any(
        row.default_strategy, ("无特殊要求不优先使用", "无特殊要求不优先")
    )
    if confidence is ControlledLevel.HIGH and priority:
        return 0
    if confidence is ControlledLevel.MEDIUM and priority:
        return 1
    if confidence in {ControlledLevel.HIGH, ControlledLevel.MEDIUM} and relaxed:
        return 2
    risks.append("参考图基础质量或默认使用策略不满足要求")
    return None


def _ignored_reference_jewelry(row: ReferenceRow) -> tuple[str, ...]:
    text = f"{row.existing_jewelry} {row.jewelry_type} {row.notes}"
    ignored: list[str] = []
    for label, terms in (
        ("参考图中的戒指", ("戒指", "指环")),
        ("参考图中的手链/手串", ("手链", "手串", "手镯")),
        ("参考图中的项链", ("项链", "吊坠", "颈链")),
        ("参考图中的耳饰", ("耳饰", "耳环")),
    ):
        if contains_unnegated_any(text, terms):
            ignored.append(label)
    return tuple(ignored)


RING_POLICY = CategoryPolicy(
    product_type=ProductType.RING,
    supported_modes=frozenset({DisplayMode.WORN}),
    max_layer_count=1,
    basic_qc_items=SHARED_BASIC_QC_ITEMS + RING_BASIC_QC_ITEMS,
    mode_qc_items={DisplayMode.WORN: RING_BASIC_QC_ITEMS},
    reference_evaluator=_evaluate_ring_reference,
    prompt_fragment_builder=_build_ring_prompt_fragments,
)


__all__ = ["RING_BASIC_QC_ITEMS", "RING_IMAGE_ONE_ROLE", "RING_POLICY"]
