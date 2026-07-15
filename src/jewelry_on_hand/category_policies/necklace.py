import re

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


_NECKLACE_TYPES = {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}
_LENGTH_CATEGORY_NAMES = {
    "choker": "贴颈链",
    "collarbone": "锁骨链",
    "upper_chest": "上胸链",
    "long": "长链",
}
NECKLACE_IMAGE_ONE_ROLE = "内部图1：底图锁定，不提供产品身份，除唯一允许修改外不得改变。"


def _build_necklace_prompt_fragments(product: ProductAnalysis) -> PromptFragments:
    structure_lines = [
        f"项链层数：{product.layer_count} 层。",
        f"长度等级：{_length_category_text(product.length_category)}。",
        f"链条/串线类型：{product.chain_or_strand_type or '未确定'}。",
        "层间上下顺序：第 1 层位于最上方且最短，层号递增时依次向下；"
        "保持各层可辨识的相对落差，不得交换、合并或重组层间上下顺序。",
    ]
    if product.has_pendant:
        structure_lines.extend(
            (
                f"主吊坠数量：{product.pendant_count}。",
                f"吊坠所属层：第 {product.pendant_layer} 层。",
                f"吊坠位置：{product.pendant_position or '未确定'}。",
                f"吊坠朝向：{product.pendant_orientation or '未确定'}。",
                f"吊坠连接：{product.connection_structure or '未确定'}。",
                "吊坠身份保持：不得换层、不得翻面、不得移位、不得复制、不得丢失，"
                "不得脱离或改变原连接关系。",
            )
        )
    else:
        structure_lines.append("主吊坠：无；不得凭空添加吊坠或吊坠连接结构。")

    return PromptFragments(
        image_one_role=NECKLACE_IMAGE_ONE_ROLE,
        category_fidelity="\n".join(structure_lines),
        display_mode=_necklace_display_mode_fragment(product),
        occlusion_physics=_necklace_occlusion_fragment(product),
        prohibitions=(
            "禁止自动补链、补扣头或推断背面结构；不得删除、缩短或重组链条。\n"
            "不得将被遮挡部分或不确定细节改写成确定性补全指令。"
        ),
    )


def _length_category_text(value: str | None) -> str:
    if value is None:
        return "未确定"
    return f"{_LENGTH_CATEGORY_NAMES[value]}（{value}）"


def _necklace_display_mode_fragment(product: ProductAnalysis) -> str:
    if product.display_mode is DisplayMode.HAND_HELD:
        return (
            "展示关系：保持底图手势不变，只重建手指与项链的真实接触；"
            "链条按原连接关系受重力自然垂落。"
        )
    return (
        "展示关系：保持底图人物和姿势不变；项链按原层数与连接关系受重力"
        "自然垂落，并与接触表面形成真实接触。"
    )


def _necklace_occlusion_fragment(product: ProductAnalysis) -> str:
    if product.display_mode is DisplayMode.HAND_HELD:
        return (
            "手指与项链必须有真实接触点，链条受重力自然垂落；手指不得穿透链条"
            "或吊坠，接触处不得悬浮或粘连。\n"
            "不得迁移内部图2中的人物颈部、衣服或皮肤；只提取项链本体的可见结构。"
        )
    return (
        "项链与颈部、锁骨或衣物表面应有真实接触、遮挡关系和自然阴影；"
        "禁止把颈部或衣服连同项链作为贴片，不得让链条穿透皮肤或衣物。\n"
        "头发和衣领只保留底图已有遮挡关系，不得借产品替换改变人物或衣物。"
    )


def _evaluate_necklace_reference(
    product: ProductAnalysis, row: ReferenceRow
) -> ReferenceAdaptation:
    score = 0
    reasons: list[str] = []
    risks = _replacement_blocking_risks(row)
    product_type_matches = _matches_product_type(product.confirmed_product_type, row)
    display_mode_matches = _matches_display_mode(product.display_mode, row)

    if product_type_matches and display_mode_matches:
        score += 55
        reasons.append("项链品类与展示模式匹配")
    else:
        if not row.applicable_product_types.strip():
            risks.append("缺少明确的项链适用品类标注")
        elif not product_type_matches:
            risks.append("参考图适用品类与目标项链不匹配")
        if not row.applicable_display_modes.strip():
            risks.append("缺少明确的项链适用展示模式标注")
        elif not display_mode_matches:
            risks.append("参考图展示模式与目标项链不匹配")

    product_visibility = parse_visibility_level(row.product_visibility)
    if not row.product_visibility.strip():
        risks.append("缺少产品预计展示面积标注")
    elif product_visibility is None:
        risks.append("产品预计展示面积标注无法识别")
    elif product_visibility is ControlledLevel.LOW:
        risks.append("产品展示面积不足，无法清晰辨识项链")
    else:
        score += 15
        reasons.append("项链预计展示面积充足")

    crop_risk = parse_risk_level(row.crop_risk)
    if not row.crop_risk.strip():
        risks.append("缺少项链裁切风险标注")
    elif crop_risk is None:
        risks.append("项链裁切风险标注无法识别")
    elif crop_risk is ControlledLevel.HIGH:
        risks.append("裁切风险过高，可能无法完整展示项链")
    else:
        score += 8
        reasons.append("项链裁切风险低")

    if product.display_mode is DisplayMode.WORN:
        score += _evaluate_worn_reference(product, row, reasons, risks)
    else:
        score += _evaluate_hand_held_reference(row, reasons, risks)

    selection_tier = _selection_tier(row, risks)
    ignored = _ignored_reference_jewelry(row)
    return ReferenceAdaptation(
        eligible=not risks and selection_tier is not None,
        score_adjustment=score,
        reasons=tuple(reasons),
        risks=tuple(risks),
        ignored_reference_jewelry=ignored,
        selection_tier=selection_tier or 0,
    )


def _replacement_blocking_risks(row: ReferenceRow) -> list[str]:
    text = row.combined_text()
    risks: list[str] = []
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


def _evaluate_worn_reference(
    product: ProductAnalysis,
    row: ReferenceRow,
    reasons: list[str],
    risks: list[str],
) -> int:
    score = 0
    body_text = row.visible_body_regions
    if not body_text.strip():
        risks.append("缺少项链佩戴所需的颈部、锁骨或胸前区域标注")
    elif not contains_affirmed_any(
        body_text, ("颈部", "颈", "锁骨", "胸前", "胸口", "胸部")
    ):
        risks.append("颈部、锁骨或胸前空间不足，不能用于项链佩戴")
    else:
        score += 15
        reasons.append("颈部、锁骨和胸前空间匹配项链佩戴")

    if not row.framing.strip():
        risks.append("缺少项链长度取景范围标注")
    elif not _framing_fits_length(product, row):
        risks.append("取景范围无法完整展示目标项链长度")
    else:
        score += 12
        reasons.append("取景范围匹配项链长度")

    if not row.collar_type.strip():
        risks.append("缺少衣领类型标注")
    clothing_risk = parse_risk_level(row.clothing_occlusion_risk)
    hair_risk = parse_risk_level(row.hair_occlusion_risk)
    if not row.clothing_occlusion_risk.strip():
        risks.append("缺少衣领或衣物遮挡风险标注")
    elif clothing_risk is None:
        risks.append("衣领或衣物遮挡风险标注无法识别")
    elif clothing_risk is ControlledLevel.HIGH:
        risks.append("衣领或衣物会严重遮挡项链落点")
    if not row.hair_occlusion_risk.strip():
        risks.append("缺少头发遮挡风险标注")
    elif hair_risk is None:
        risks.append("头发遮挡风险标注无法识别")
    elif hair_risk is ControlledLevel.HIGH:
        risks.append("头发会大面积遮挡项链主要结构")
    if (
        row.collar_type.strip()
        and row.clothing_occlusion_risk.strip()
        and row.hair_occlusion_risk.strip()
        and clothing_risk in {ControlledLevel.LOW, ControlledLevel.MEDIUM}
        and hair_risk in {ControlledLevel.LOW, ControlledLevel.MEDIUM}
    ):
        score += 10
        reasons.append("衣领和头发遮挡风险低")

    if product.layer_count > 1:
        vertical_text = f"{row.framing} {row.visible_body_regions} {row.notes} {row.pose_keywords}"
        has_vertical_space = (
            parse_visibility_level(row.chest_visibility)
            in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}
            and contains_any(row.framing, ("胸", "半身", "上半身", "全身"))
            and contains_unnegated_any(
                vertical_text, ("多层垂直空间", "层间落差", "多层空间", "垂直空间")
            )
        )
        if not has_vertical_space:
            risks.append("多层项链缺少保持层间落差所需的垂直空间")
        elif contains_unnegated_any(vertical_text, ("背身", "大幅侧身", "过度侧身")):
            risks.append("身体朝向不适合建立多层项链结构")
        else:
            score += 15
            reasons.append("多层项链垂直空间充足")
    return score


def _evaluate_hand_held_reference(
    row: ReferenceRow, reasons: list[str], risks: list[str]
) -> int:
    score = 0
    body_text = row.visible_body_regions
    has_hand_region = contains_affirmed_any(
        body_text, ("手指", "掌心", "手掌", "双手")
    )
    wrist_only = (
        contains_affirmed_any(body_text, ("手腕", "前臂"))
        and not has_hand_region
    )
    if wrist_only:
        risks.append("仅腕部构图，不能用于项链手持展示")
    elif (
        not body_text.strip()
        or not has_hand_region
        or parse_visibility_level(row.hand_visibility)
        not in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}
    ):
        risks.append("手指、掌心或双手不可清晰辨识")
    else:
        score += 15
        reasons.append("手指、掌心或双手清晰可见")

    hand_text = f"{row.recommended_usage} {row.notes} {row.pose_keywords} {row.framing}"
    if not contains_unnegated_any(
        hand_text, ("自然垂落", "垂落空间", "完整链条", "链条完整")
    ):
        risks.append("画面缺少完整链条所需的垂落空间")
    else:
        score += 15
        reasons.append("完整链条具有自然垂落空间")
    if not contains_unnegated_any(
        hand_text, ("真实接触", "合理接触", "捏持", "托住", "握持", "夹持")
    ):
        risks.append("手部与项链缺少明确的真实接触点")
    else:
        score += 12
        reasons.append("手部与项链接触关系真实")

    if parse_risk_level(row.crop_risk) is ControlledLevel.HIGH:
        risks.append("项链关键结构存在严重遮挡或裁切")
    risks.extend(_hand_held_severe_risks(hand_text))
    return score


def _hand_held_severe_risks(text: str) -> list[str]:
    risks: list[str] = []
    if contains_affirmed_any(
        text, ("手部明显畸变", "手部严重畸变", "手指明显畸变", "手指严重畸变")
    ):
        risks.append("手部存在明显畸变，不能建立真实手持关系")
    if contains_affirmed_any(
        text,
        (
            "手指严重遮挡吊坠",
            "手指严重遮挡关键结构",
            "关键结构严重遮挡",
            "吊坠严重遮挡",
            "链条严重遮挡",
        ),
    ):
        risks.append("手指严重遮挡吊坠或项链关键结构")
    if contains_affirmed_any(
        text, ("画面空间不足", "展示空间不足", "垂落空间不足")
    ):
        risks.append("画面空间不足，无法完整容纳项链")
    if contains_affirmed_any(
        text,
        (
            "链条下半段超出画面",
            "链条超出画面",
            "链条下半段被裁切",
            "链条被裁切",
            "链条下半段不完整",
            "链条不完整",
        ),
    ):
        risks.append("链条下半段超出画面、被裁切或不完整")
    return risks


def _matches_product_type(product_type: ProductType, row: ReferenceRow) -> bool:
    if product_type not in _NECKLACE_TYPES:
        return False
    aliases = {
        ProductType.NECKLACE: {"necklace", "普通项链", "项链", "珠链"},
        ProductType.PENDANT_NECKLACE: {
            "pendant_necklace",
            "pendant necklace",
            "带链吊坠",
            "吊坠项链",
        },
    }[product_type]
    values = _split_annotation(row.applicable_product_types)
    return bool(values & aliases)


def _matches_display_mode(display_mode: DisplayMode, row: ReferenceRow) -> bool:
    aliases = {
        DisplayMode.WORN: {"worn", "佩戴", "真人佩戴"},
        DisplayMode.HAND_HELD: {"hand_held", "hand held", "手持", "手持展示"},
    }[display_mode]
    return bool(_split_annotation(row.applicable_display_modes) & aliases)


def _split_annotation(value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in re.split(r"[,，、;/|]+", value)
        if item.strip()
    }


def _framing_fits_length(product: ProductAnalysis, row: ReferenceRow) -> bool:
    framing = row.framing
    if product.length_category in {"upper_chest", "long"}:
        return (
            contains_any(framing, ("胸", "半身", "上半身", "全身"))
            and parse_visibility_level(row.chest_visibility)
            in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}
            and not contains_any(framing, ("锁骨特写", "颈部特写"))
        )
    return contains_any(framing, ("颈", "锁骨", "胸", "半身", "上半身")) and (
        parse_visibility_level(row.neck_visibility)
        in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}
        or parse_visibility_level(row.collarbone_visibility)
        in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}
        or parse_visibility_level(row.chest_visibility)
        in {ControlledLevel.HIGH, ControlledLevel.MEDIUM}
    )


def _selection_tier(row: ReferenceRow, risks: list[str]) -> int | None:
    priority = contains_any(row.default_strategy, ("优先使用", "可优先", "优先")) and not contains_any(
        row.default_strategy, ("不优先", "不建议", "谨慎使用")
    )
    relaxed = contains_any(
        row.default_strategy, ("无特殊要求不优先使用", "无特殊要求不优先")
    )
    confidence = parse_confidence_level(row.confidence)
    if confidence is ControlledLevel.HIGH and priority:
        return 0
    if confidence is ControlledLevel.MEDIUM and priority:
        return 1
    if confidence in {ControlledLevel.HIGH, ControlledLevel.MEDIUM} and relaxed:
        return 2
    risks.append("参考图基础质量或默认使用策略不满足要求")
    return None


def _ignored_reference_jewelry(row: ReferenceRow) -> tuple[str, ...]:
    text = f"{row.existing_jewelry} {row.notes}"
    ignored: list[str] = []
    for label, terms in (
        ("参考图中的原有项链", ("项链", "吊坠", "颈链")),
        ("参考图中的手链/手串", ("手链", "手串", "手镯")),
        ("参考图中的戒指", ("戒指",)),
        ("参考图中的耳饰", ("耳饰", "耳环")),
    ):
        if contains_unnegated_any(text, terms):
            ignored.append(label)
    return tuple(ignored)


_NECKLACE_MODE_QC_ITEMS = {
    DisplayMode.WORN: (
        "层数、上下顺序、长度等级和层间落差与产品图一致",
        "吊坠所属层、位置、朝向和连接关系与产品图一致",
        "链条真实绕颈并在胸前自然垂落",
        "链条没有穿肤、穿衣、穿发、悬空或陷入身体",
        "衣领和头发遮挡符合真实前后关系且未遮掉主要结构",
        "多层链没有错误交叉、合并或复制",
        "没有自动补链、凭空补链或补充不存在的连接结构",
        "没有迁移产品图中的颈部、胸部、衣服、头发或皮肤块",
    ),
    DisplayMode.HAND_HELD: (
        "产品结构完整且关键结构可辨认",
        "手部与链条接触真实，链条自然垂落",
        "手指没有穿透链条或吊坠",
        "吊坠和关键结构没有被不合理遮挡",
        "产品比例合理，没有因近景明显放大或缩小",
        "没有虚构佩戴链路、自动补链或补充不存在的结构",
    ),
}


NECKLACE_POLICY = CategoryPolicy(
    product_type=ProductType.NECKLACE,
    supported_modes=frozenset({DisplayMode.WORN, DisplayMode.HAND_HELD}),
    max_layer_count=3,
    basic_qc_items=SHARED_BASIC_QC_ITEMS
    + (
        "产品品类与产品图一致",
        "项链层数、顺序和相对落差正确",
        "链条与身体或手部关系自然",
    ),
    mode_qc_items=_NECKLACE_MODE_QC_ITEMS,
    reference_evaluator=_evaluate_necklace_reference,
    prompt_fragment_builder=_build_necklace_prompt_fragments,
)

PENDANT_NECKLACE_POLICY = CategoryPolicy(
    product_type=ProductType.PENDANT_NECKLACE,
    supported_modes=frozenset({DisplayMode.WORN, DisplayMode.HAND_HELD}),
    max_layer_count=3,
    basic_qc_items=SHARED_BASIC_QC_ITEMS
    + (
        "产品品类与产品图一致",
        "项链层数、顺序和相对落差正确",
        "吊坠形态、连接关系和所在层正确",
    ),
    mode_qc_items=_NECKLACE_MODE_QC_ITEMS,
    reference_evaluator=_evaluate_necklace_reference,
    prompt_fragment_builder=_build_necklace_prompt_fragments,
)
