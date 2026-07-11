from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.category_policies.base import (
    contains_any as _contains_any,
    contains_unnegated_any as _contains_unnegated_any,
)
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow, ScoredReference


POSE_PURPOSE_POINTS = 20
WEARING_DISPLAY_POINTS = 12
PRIORITY_STRATEGY_POINTS = 15
HIGH_CONFIDENCE_POINTS = 10
DARK_FLASH_MATCH_POINTS = 15
CLEAR_NATURAL_MATCH_POINTS = 15
RED_CHINESE_STYLE_MATCH_POINTS = 10
MIRROR_POINTS = 20
GESTURE_SKIN_LIGHT_NEGATIVE_SPACE_POINTS = 10
CLOSE_UP_POINTS = 8
NON_PRIORITY_POINTS = -30
STILL_OBJECT_EARRING_PURPOSE_POINTS = -50
CROP_RISK_POINTS = -15
DIVERSITY_SCORE_WINDOW = 40
SAME_SHOOT_GROUP_PENALTY = 35
SAME_STYLE_CLUSTER_PENALTY = 25
SAME_SCENE_CLUSTER_PENALTY = 12
SAME_POSE_CLUSTER_PENALTY = 12
BATCH_SAME_FILE_PENALTY = 1000
BATCH_SAME_SHOOT_GROUP_PENALTY = 45
BATCH_SAME_STYLE_CLUSTER_PENALTY = 10
SAME_FRAMING_PENALTY = 10
SAME_COLLAR_PENALTY = 8
SAME_HAIR_POSITION_PENALTY = 8
SAME_BODY_ORIENTATION_PENALTY = 10
SAME_HOLDING_METHOD_PENALTY = 10


def select_top_references(
    product: ProductAnalysis, rows: Iterable[ReferenceRow]
) -> tuple[list[ScoredReference], list[ScoredReference]]:
    filtered_rows = _filter_reference_rows(
        product, [row for row in rows if row.file_exists]
    )
    scored = [score_reference(product, row) for row in filtered_rows]
    ordered = sorted(scored, key=lambda item: (-item.score, item.row.index))
    candidates = _rerank(ordered)
    selected = _select_diverse_top_references(candidates, limit=3)
    return selected, candidates


def select_batch_diverse_references(
    candidate_sets: Iterable[Sequence[ScoredReference]],
    limit: int = 3,
    initial_usage: dict[str, dict[str, int]] | None = None,
) -> list[list[ScoredReference]]:
    batch_usage = _copy_batch_usage(initial_usage)
    selections: list[list[ScoredReference]] = []
    for candidates in candidate_sets:
        selected = _select_diverse_top_references(
            candidates,
            limit=limit,
            batch_usage=batch_usage,
        )
        selections.append(selected)
        _record_batch_usage(batch_usage, selected)
    return selections


def _copy_batch_usage(
    initial_usage: dict[str, dict[str, int]] | None = None,
) -> dict[str, dict[str, int]]:
    batch_usage: dict[str, dict[str, int]] = {
        "file": {},
        "shoot_group": {},
        "style_cluster": {},
    }
    if not initial_usage:
        return batch_usage
    for key in batch_usage:
        batch_usage[key].update(initial_usage.get(key, {}))
    return batch_usage


def score_reference(product: ProductAnalysis, row: ReferenceRow) -> ScoredReference:
    product_text = _product_text(product)
    row_text = row.combined_text()
    policy = get_category_policy(product.confirmed_product_type)
    adaptation = policy.evaluate_reference(product, row)
    score = adaptation.score_adjustment
    reason = list(adaptation.reasons)
    risk = list(adaptation.risks)

    if _contains_any(row.purpose_category, ("上手", "姿势", "手模", "构图", "佩戴")):
        score += POSE_PURPOSE_POINTS
        reason.append("用途为上手姿势或手模构图参考")

    if _has_wearing_display_signal(row):
        score += WEARING_DISPLAY_POINTS
        reason.append("适合佩戴展示")

    if _is_priority_strategy(row.default_strategy):
        score += PRIORITY_STRATEGY_POINTS
        reason.append("默认策略为优先使用")

    if "高" in row.confidence:
        score += HIGH_CONFIDENCE_POINTS
        reason.append("判断置信度高")

    if _has_style_match(product_text, row_text, ("暗调", "闪光", "闪", "暗色")):
        score += DARK_FLASH_MATCH_POINTS
        reason.append("暗调闪光风格匹配")

    if _has_style_match(
        product_text,
        row_text,
        ("清透", "自然光", "白衬衫", "浅色", "奶油", "柔和生活感"),
    ):
        score += CLEAR_NATURAL_MATCH_POINTS
        reason.append("清晰自然风格匹配")

    if _has_style_match(product_text, row_text, ("红", "中式", "国风", "中国风", "新中式")):
        score += RED_CHINESE_STYLE_MATCH_POINTS
        reason.append("红色或中式风格匹配")

    if _contains_any(row_text, ("对镜", "镜子", "镜面", "镜像", "自拍镜")):
        score += MIRROR_POINTS
        reason.append("对镜或镜面构图可用")

    if _contains_any(
        row_text,
        ("手势", "姿势", "肤色", "皮肤", "光线", "光影", "留白", "自然光", "闪光"),
    ):
        score += GESTURE_SKIN_LIGHT_NEGATIVE_SPACE_POINTS
        reason.append("手势/肤色/光线/留白信息可复用")

    if _contains_any(row_text, ("近景", "特写", "close-up", "特近")):
        score += CLOSE_UP_POINTS
        reason.append("近景构图匹配")

    if _is_non_priority(row.default_strategy):
        score += NON_PRIORITY_POINTS
        risk.append("默认策略提示不优先使用")

    if _has_still_object_earring_purpose(row):
        score += STILL_OBJECT_EARRING_PURPOSE_POINTS
        risk.append("用途偏静物/物品/耳饰参考")

    ignored_reference_jewelry = adaptation.ignored_reference_jewelry
    if ignored_reference_jewelry:
        risk.append("参考图含需忽略的非目标首饰")

    if _contains_unnegated_any(
        row_text, ("裁切", "截断", "切手", "遮挡", "缺失", "不完整", "过近")
    ):
        score += CROP_RISK_POINTS
        risk.append("存在裁切或遮挡风险")

    return _make_scored(row, score, 1, reason, risk, ignored_reference_jewelry)


def _rerank(items: Sequence[ScoredReference]) -> list[ScoredReference]:
    return [
        _make_scored(
            item.row,
            item.score,
            rank,
            item.reason,
            item.risk,
            item.ignored_reference_jewelry,
        )
        for rank, item in enumerate(items, start=1)
    ]


def _select_diverse_top_references(
    candidates: Sequence[ScoredReference],
    limit: int,
    batch_usage: dict[str, dict[str, int]] | None = None,
) -> list[ScoredReference]:
    if len(candidates) <= limit:
        return list(candidates)

    max_score = candidates[0].score
    quality_floor = max_score - DIVERSITY_SCORE_WINDOW
    quality_pool = [item for item in candidates if item.score >= quality_floor] or list(candidates)
    safe_quality_pool = [
        item
        for item in quality_pool
        if not item.risk and not item.ignored_reference_jewelry
    ]
    if safe_quality_pool:
        quality_pool = safe_quality_pool
    quality_pool = _prefer_unused_files(quality_pool, candidates, batch_usage)
    first_item = max(
        quality_pool,
        key=lambda item: (
            _batch_adjusted_score(item, batch_usage),
            item.score,
            -item.row.index,
        ),
    )
    selected: list[ScoredReference] = [first_item]
    remaining = [item for item in candidates if item is not first_item]

    while remaining and len(selected) < limit:
        eligible = [item for item in remaining if item.score >= quality_floor] or remaining
        eligible = _prefer_unused_files(eligible, remaining, batch_usage)
        next_item = max(
            eligible,
            key=lambda item: (
                _diversity_adjusted_score(item, selected, batch_usage),
                item.score,
                -item.row.index,
            ),
        )
        selected.append(next_item)
        remaining.remove(next_item)

    return _rerank(selected)


def _prefer_unused_files(
    primary_pool: Sequence[ScoredReference],
    fallback_pool: Sequence[ScoredReference],
    batch_usage: dict[str, dict[str, int]] | None,
) -> Sequence[ScoredReference]:
    if not batch_usage:
        return primary_pool
    unused_in_primary = [
        item for item in primary_pool if batch_usage["file"].get(item.row.file_name, 0) == 0
    ]
    if unused_in_primary:
        return unused_in_primary
    unused_in_fallback = [
        item for item in fallback_pool if batch_usage["file"].get(item.row.file_name, 0) == 0
    ]
    return unused_in_fallback or primary_pool


def _diversity_adjusted_score(
    item: ScoredReference,
    selected: Sequence[ScoredReference],
    batch_usage: dict[str, dict[str, int]] | None = None,
) -> int:
    penalty = 0
    item_profile = _diversity_profile(item.row)
    for selected_item in selected:
        selected_profile = _diversity_profile(selected_item.row)
        if item_profile["shoot_group"] == selected_profile["shoot_group"]:
            penalty += SAME_SHOOT_GROUP_PENALTY
        if item_profile["style_cluster"] == selected_profile["style_cluster"]:
            penalty += SAME_STYLE_CLUSTER_PENALTY
        if item_profile["scene_cluster"] == selected_profile["scene_cluster"]:
            penalty += SAME_SCENE_CLUSTER_PENALTY
        if item_profile["pose_cluster"] == selected_profile["pose_cluster"]:
            penalty += SAME_POSE_CLUSTER_PENALTY
        if _same_labeled_profile(item_profile, selected_profile, "framing"):
            penalty += SAME_FRAMING_PENALTY
        if _same_labeled_profile(item_profile, selected_profile, "collar"):
            penalty += SAME_COLLAR_PENALTY
        if _same_labeled_profile(item_profile, selected_profile, "hair_position"):
            penalty += SAME_HAIR_POSITION_PENALTY
        if _same_labeled_profile(item_profile, selected_profile, "body_orientation"):
            penalty += SAME_BODY_ORIENTATION_PENALTY
        if _same_labeled_profile(item_profile, selected_profile, "holding_method"):
            penalty += SAME_HOLDING_METHOD_PENALTY
    return item.score - penalty - _batch_penalty(item_profile, item.row.file_name, batch_usage)


def _batch_adjusted_score(
    item: ScoredReference,
    batch_usage: dict[str, dict[str, int]] | None,
) -> int:
    profile = _diversity_profile(item.row)
    return item.score - _batch_penalty(profile, item.row.file_name, batch_usage)


def _batch_penalty(
    profile: dict[str, str],
    file_name: str,
    batch_usage: dict[str, dict[str, int]] | None,
) -> int:
    if not batch_usage:
        return 0
    return (
        batch_usage["file"].get(file_name, 0) * BATCH_SAME_FILE_PENALTY
        + batch_usage["shoot_group"].get(profile["shoot_group"], 0)
        * BATCH_SAME_SHOOT_GROUP_PENALTY
        + batch_usage["style_cluster"].get(profile["style_cluster"], 0)
        * BATCH_SAME_STYLE_CLUSTER_PENALTY
    )


def _record_batch_usage(
    batch_usage: dict[str, dict[str, int]], selected: Sequence[ScoredReference]
) -> None:
    for item in selected:
        profile = _diversity_profile(item.row)
        _increment(batch_usage["file"], item.row.file_name)
        _increment(batch_usage["shoot_group"], profile["shoot_group"])
        _increment(batch_usage["style_cluster"], profile["style_cluster"])


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _diversity_profile(row: ReferenceRow) -> dict[str, str]:
    return {
        "style_cluster": _style_cluster(row),
        "scene_cluster": _scene_cluster(row),
        "pose_cluster": _pose_cluster(row),
        "shoot_group": _shoot_group(row.file_name),
        "framing": row.framing.strip() or "未标注",
        "collar": row.collar_type.strip() or "未标注",
        "hair_position": _hair_position_cluster(row),
        "body_orientation": _body_orientation_cluster(row),
        "holding_method": _holding_method_cluster(row),
    }


def _same_labeled_profile(
    first: dict[str, str], second: dict[str, str], key: str
) -> bool:
    return first[key] != "未标注" and first[key] == second[key]


def _hair_position_cluster(row: ReferenceRow) -> str:
    text = f"{row.pose_keywords} {row.notes} {row.recommended_usage}"
    for label, terms in (
        ("左侧", ("头发左侧", "左侧头发", "头发向左")),
        ("右侧", ("头发右侧", "右侧头发", "头发向右")),
        ("后置", ("头发后置", "头发在后", "盘发", "扎发")),
        ("双侧披发", ("披发", "散发", "头发披肩")),
    ):
        if _contains_any(text, terms):
            return label
    return "未标注"


def _body_orientation_cluster(row: ReferenceRow) -> str:
    text = f"{row.pose_keywords} {row.notes} {row.recommended_usage}"
    for label, terms in (
        ("左侧身", ("左侧身", "身体向左", "左转身")),
        ("右侧身", ("右侧身", "身体向右", "右转身")),
        ("侧身", ("侧身", "侧面")),
        ("背身", ("背身", "背面")),
        ("正面", ("正面", "面向镜头", "身体朝前")),
    ):
        if _contains_any(text, terms):
            return label
    return "未标注"


def _holding_method_cluster(row: ReferenceRow) -> str:
    text = f"{row.pose_keywords} {row.notes} {row.recommended_usage}"
    for label, terms in (
        ("双手", ("双手持", "双手展示", "双手悬挂")),
        ("捏持", ("捏持", "指尖夹持", "两指夹持")),
        ("掌托", ("掌心托住", "手掌托住", "托在掌心")),
        ("握持", ("握持", "虎口持", "虎口握")),
        ("悬挂", ("悬挂", "提起链条")),
    ):
        if _contains_any(text, terms):
            return label
    return "未标注"


def _style_cluster(row: ReferenceRow) -> str:
    style = row.style_category.strip()
    if style:
        return style
    return _keyword_cluster(row.combined_text())


def _scene_cluster(row: ReferenceRow) -> str:
    return _keyword_cluster(f"{row.scene_keywords} {row.notes} {row.recommended_usage}")


def _pose_cluster(row: ReferenceRow) -> str:
    text = f"{row.purpose_category} {row.recommended_usage} {row.notes} {row.pose_keywords}"
    if _contains_any(text, ("对镜", "镜子", "镜面", "镜中")):
        return "对镜"
    if _contains_any(text, ("双手", "交叠")):
        return "双手"
    if _contains_any(text, ("掌心", "手掌", "托物")):
        return "掌心/托物"
    if _contains_any(text, ("手背", "指背")):
        return "手背"
    if _contains_any(text, ("前臂", "手臂")):
        return "前臂"
    if _contains_any(text, ("近景", "特写", "close-up", "特近")):
        return "近景"
    return "其他姿势"


def _keyword_cluster(text: str) -> str:
    if _contains_any(text, ("对镜", "镜子", "镜面", "镜中", "mirror")):
        return "对镜"
    if _contains_any(text, ("车内", "车里", "驾驶")):
        return "车内"
    if _contains_any(text, ("户外", "阳光", "室外")):
        return "户外"
    if _contains_any(text, ("白衬衫", "白衣", "奶油", "浅色")):
        return "清透白衣"
    if _contains_any(text, ("暗调", "暗光", "黑衣", "黑底", "闪光")):
        return "暗调"
    if _contains_any(text, ("床", "床品", "被子", "布料")):
        return "床品"
    return "其他场景"


def _shoot_group(file_name: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", file_name.strip())
    grouped = re.sub(r"\s*[（(]\d+[）)]\s*$", "", stem)
    if grouped != stem:
        return grouped
    grouped = re.sub(r"[-_]\d+$", "", stem)
    return grouped or stem


def _make_scored(
    row: ReferenceRow,
    score: int,
    rank: int,
    reason: Sequence[str],
    risk: Sequence[str],
    ignored_reference_jewelry: Sequence[str],
) -> ScoredReference:
    return ScoredReference(
        row,
        score,
        rank,
        tuple(reason),
        tuple(risk),
        tuple(ignored_reference_jewelry),
    )


def _filter_reference_rows(
    product: ProductAnalysis, rows: Sequence[ReferenceRow]
) -> list[ReferenceRow]:
    policy = get_category_policy(product.confirmed_product_type)
    evaluated = [(row, policy.evaluate_reference(product, row)) for row in rows]
    primary = [
        (row, adaptation)
        for row, adaptation in evaluated
        if adaptation.eligible and not adaptation.diversity_candidate
    ]
    if primary:
        best_tier = min(adaptation.selection_tier for _, adaptation in primary)
        primary_rows = [
            row for row, adaptation in primary if adaptation.selection_tier == best_tier
        ]
    else:
        primary_rows = []
    diversity_rows = [
        row
        for row, adaptation in evaluated
        if adaptation.eligible and adaptation.diversity_candidate
    ]
    if not primary_rows:
        return diversity_rows

    primary_indexes = {row.index for row in primary_rows}
    return [
        *primary_rows,
        *(row for row in diversity_rows if row.index not in primary_indexes),
    ]


def _product_text(product: ProductAnalysis) -> str:
    parts = (
        product.product_type,
        product.wear_position,
        product.visible_appearance,
        " ".join(product.color_family),
        product.style_mood,
        product.composition,
        " ".join(product.special_requirements),
    )
    return " ".join(part for part in parts if part)


def _has_style_match(product_text: str, row_text: str, terms: Iterable[str]) -> bool:
    term_list = tuple(terms)
    return _contains_any(product_text, term_list) and _contains_any(row_text, term_list)


def _has_wearing_display_signal(row: ReferenceRow) -> bool:
    explicit_text = row.recommended_usage
    return _contains_any(
        explicit_text,
        ("佩戴展示", "上手展示", "真人佩戴", "佩戴效果", "戴手上展示"),
    )


def _is_priority_strategy(text: str) -> bool:
    return _contains_any(text, ("优先使用", "可优先", "优先")) and not _is_non_priority(text)


def _is_non_priority(text: str) -> bool:
    return _contains_any(text, ("不优先", "无特殊要求不优先", "不建议", "谨慎使用"))


def _has_still_object_earring_purpose(row: ReferenceRow) -> bool:
    text = f"{row.purpose_category} {row.recommended_usage} {row.notes} {row.jewelry_type}"
    return _contains_unnegated_any(text, ("静物", "摆拍", "平铺", "物品", "物体", "耳饰", "耳环"))
