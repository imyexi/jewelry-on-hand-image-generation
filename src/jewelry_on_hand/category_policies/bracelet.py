from jewelry_on_hand.category_policies.base import (
    CategoryPolicy,
    ControlledLevel,
    PromptFragments,
    ReferenceAdaptation,
    SHARED_BASIC_QC_ITEMS,
    contains_affirmed_any,
    contains_any,
    contains_unnegated_any,
    parse_confidence_level,
    parse_risk_level,
    parse_visibility_level,
)
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow
from jewelry_on_hand.product_types import ProductType


_TARGET_TERMS = ("手链", "手串", "手镯")
_FILTER_TERMS = ("手链", "手串")
_NON_TARGET_TERMS = ("戒指", "耳饰", "耳环", "项链", "吊坠", "颈链")

BRACELET_PRODUCT_ISOLATION_SENTENCE = "内部图2只提取珠子、隔圈、金属件、颜色、透明度、纹理、反光和排列；禁止继承内部图2里的皮肤、手腕、手臂、掌纹、指甲、肤色、手臂粗细、背景。"
BRACELET_WRIST_SOURCE_SENTENCE = "手腕宽度、手臂轮廓、皮肤连续性和肤色必须以内部图1为准；不要把内部图2中的手串+手腕局部作为整体贴到内部图1。"
BRACELET_IMAGE_ONE_ROLE = "内部图1：自动参考图，只参考手部姿势、手模构图、场景氛围、光线和画面比例。"


def _build_bracelet_prompt_fragments(product: ProductAnalysis) -> PromptFragments:
    return PromptFragments(
        image_one_role=BRACELET_IMAGE_ONE_ROLE,
        category_fidelity=(
            "手串/手链的珠子、主珠、配珠、隔圈、金属件、排列顺序、颜色、"
            "透明度、纹理、反光和可见比例必须与内部图2一致。"
        ),
        display_mode=(
            f"真人佩戴：将内部图2的产品自然佩戴到{product.wear_position}位置；"
            "手串环绕手腕，松紧和落点自然。"
        ),
        occlusion_physics=(
            f"{BRACELET_PRODUCT_ISOLATION_SENTENCE}\n"
            f"{BRACELET_WRIST_SOURCE_SENTENCE}\n"
            "珠子与手腕应有真实接触和合理阴影，不得悬浮、嵌入皮肤或硬贴阴影。"
        ),
        prohibitions=(
            "禁止改变珠子排列顺序、主珠和配件位置关系；禁止迁移内部图2中的"
            "原手腕、手臂或皮肤块。"
        ),
    )


def _evaluate_bracelet_reference(
    product: ProductAnalysis, row: ReferenceRow
) -> ReferenceAdaptation:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    jewelry_text = row.jewelry_type
    has_target = contains_any(jewelry_text, _TARGET_TERMS)
    has_filter_target = contains_any(jewelry_text, _FILTER_TERMS)
    has_non_target = contains_any(jewelry_text, _NON_TARGET_TERMS)
    applicable = _is_applicable(row.bracelet_applicability)

    if has_target:
        score += 30
        reasons.append("饰品类型匹配手链/手串")
    if applicable:
        score += 25
        reasons.append("适用性标记为可用于手链/手串")
    if has_non_target and not has_target:
        score -= 40
        risks.append("参考图饰品类型不是目标手链/手串")

    row_text = row.combined_text()
    if contains_any(row_text, ("手腕", "前臂", "手臂")) and contains_any(
        row_text, ("露出", "面积足", "完整", "清楚", "清晰")
    ):
        score += 15
        reasons.append("手腕/前臂露出面积足")
    if contains_any(row_text, ("叠戴", "堆叠", "多层", "复杂", "繁复", "多件")):
        score -= 10
        risks.append("叠戴或复杂首饰会干扰替换")
    bead_diameter = product.product_dimensions.bead_diameter_mm
    if bead_diameter is not None and bead_diameter >= 10 and contains_any(
        row_text, ("近景", "特写", "close-up", "特近")
    ):
        score += 15
        reasons.append("大珠产品适合近景参考")

    pure_target = has_filter_target and not has_non_target
    combined_target = has_filter_target and has_non_target
    selection_tier = _selection_tier(row)
    risks.extend(_replacement_blocking_risks(row))
    eligible = (
        applicable
        and selection_tier is not None
        and (pure_target or combined_target)
        and not risks
    )
    return ReferenceAdaptation(
        eligible=eligible,
        score_adjustment=score,
        reasons=tuple(reasons),
        risks=tuple(risks),
        ignored_reference_jewelry=_ignored_reference_jewelry(row_text),
        selection_tier=selection_tier or 0,
        diversity_candidate=combined_target,
    )


def _replacement_blocking_risks(row: ReferenceRow) -> list[str]:
    text = row.combined_text()
    risks: list[str] = []
    target_text = f"{row.visible_body_regions} {row.recommended_usage} {row.notes}"
    if not contains_affirmed_any(target_text, ("手腕", "腕部", "前臂")):
        risks.append("缺少可替换目标所在的手腕或前臂区域")
    product_visibility = parse_visibility_level(row.product_visibility)
    if not row.product_visibility.strip():
        risks.append("缺少产品预计展示面积标注")
    elif product_visibility is None:
        risks.append("产品预计展示面积标注无法识别")
    elif product_visibility is ControlledLevel.LOW:
        risks.append("产品预计展示面积过低")
    crop_risk = parse_risk_level(row.crop_risk)
    if not row.crop_risk.strip():
        risks.append("缺少目标手腕或首饰区域裁切风险标注")
    elif crop_risk is None:
        risks.append("目标手腕或首饰区域裁切风险标注无法识别")
    elif crop_risk is ControlledLevel.HIGH:
        risks.append("目标手腕或首饰区域裁切风险过高")
    if contains_unnegated_any(text, ("严重遮挡", "大面积遮挡")):
        risks.append("目标手腕或首饰区域存在严重遮挡")
    if contains_unnegated_any(
        text,
        (
            "大面积文字",
            "blocking",
            "平台界面",
            "手机界面",
            "网页界面",
            "状态栏",
            "操作按钮",
        ),
    ):
        risks.append("画面含阻断替换的平台界面元素")
    if contains_unnegated_any(
        text,
        (
            "原首饰无法完整识别",
            "原有首饰无法完整识别",
            "原首饰不可完整识别",
            "原有首饰不可完整识别",
            "原首饰无法清除",
            "原有首饰无法清除",
            "无法完整识别",
            "不可完整识别",
            "无法清除",
        ),
    ):
        risks.append("原首饰无法完整识别或安全清除")
    return risks


def _selection_tier(row: ReferenceRow) -> int | None:
    confidence = parse_confidence_level(row.confidence)
    priority = _is_priority_strategy(row.default_strategy)
    relaxed = contains_any(
        row.default_strategy, ("无特殊要求不优先使用", "无特殊要求不优先")
    )
    if confidence is ControlledLevel.HIGH and priority:
        return 0
    if confidence is ControlledLevel.MEDIUM and priority:
        return 1
    if confidence in {ControlledLevel.HIGH, ControlledLevel.MEDIUM} and relaxed:
        return 2
    return None


def _is_applicable(text: str) -> bool:
    return contains_any(text, ("是", "可用于", "适用", "手链", "手串")) and not contains_any(
        text, ("否", "不适用", "不可用")
    )


def _is_priority_strategy(text: str) -> bool:
    return contains_any(text, ("优先使用", "可优先", "优先")) and not contains_any(
        text, ("不优先", "无特殊要求不优先", "不建议", "谨慎使用")
    )


def _ignored_reference_jewelry(text: str) -> tuple[str, ...]:
    ignored: list[str] = []
    if contains_unnegated_any(text, ("戒指",)):
        ignored.append("参考图中的戒指")
    if contains_unnegated_any(text, ("耳饰", "耳环")):
        ignored.append("参考图中的耳饰")
    if contains_unnegated_any(text, ("项链", "吊坠", "颈链")):
        ignored.append("参考图中的项链")
    if contains_unnegated_any(
        text, ("原有手链", "原手链", "已有手链", "旧手链", "原有手串", "已有手串")
    ):
        ignored.append("参考图中的原有手链")
    return tuple(ignored)


BRACELET_POLICY = CategoryPolicy(
    product_type=ProductType.BRACELET,
    supported_modes=frozenset({DisplayMode.WORN}),
    max_layer_count=1,
    basic_qc_items=SHARED_BASIC_QC_ITEMS
    + (
        "产品品类与产品图一致",
        "产品关键结构完整",
        "手腕佩戴关系自然",
    ),
    mode_qc_items={
        DisplayMode.WORN: (
            "手串贴合手腕，遮挡、松紧和接触阴影自然",
            "手指、手掌、手腕和皮肤纹理自然",
            "没有迁移产品图中的粗手腕、局部手臂或皮肤块",
        )
    },
    reference_evaluator=_evaluate_bracelet_reference,
    prompt_fragment_builder=_build_bracelet_prompt_fragments,
)
