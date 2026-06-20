from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from jewelry_on_hand.models import ProductAnalysis, ReferenceRow, ScoredReference


TYPE_POINTS = 30
APPLICABILITY_POINTS = 25
POSE_PURPOSE_POINTS = 20
WEARING_DISPLAY_POINTS = 12
PRIORITY_STRATEGY_POINTS = 15
HIGH_CONFIDENCE_POINTS = 10
DARK_FLASH_MATCH_POINTS = 15
CLEAR_NATURAL_MATCH_POINTS = 15
RED_CHINESE_STYLE_MATCH_POINTS = 10
MIRROR_POINTS = 20
WRIST_FOREARM_AREA_POINTS = 15
GESTURE_SKIN_LIGHT_NEGATIVE_SPACE_POINTS = 10
CLOSE_UP_POINTS = 8
LARGE_BEAD_CLOSE_UP_POINTS = 15
NON_PRIORITY_POINTS = -30
NON_TARGET_JEWELRY_POINTS = -40
STILL_OBJECT_EARRING_PURPOSE_POINTS = -50
STACKED_COMPLEX_JEWELRY_POINTS = -10
CROP_RISK_POINTS = -15
DIVERSITY_SCORE_WINDOW = 40
SAME_SHOOT_GROUP_PENALTY = 35
SAME_STYLE_CLUSTER_PENALTY = 25
SAME_SCENE_CLUSTER_PENALTY = 12
SAME_POSE_CLUSTER_PENALTY = 12
BATCH_SAME_FILE_PENALTY = 1000
BATCH_SAME_SHOOT_GROUP_PENALTY = 45
BATCH_SAME_STYLE_CLUSTER_PENALTY = 10


TARGET_JEWELRY_TERMS = ("手链", "手串", "手镯")
TARGET_FILTER_TERMS = ("手链", "手串")
NON_TARGET_JEWELRY_TERMS = ("戒指", "耳饰", "耳环", "项链", "吊坠", "颈链")
BROAD_NEGATION_PREFIXES = ("没有明显", "无明显", "不是", "不适合", "未见", "没有", "无", "未")
DIRECT_NEGATION_PREFIXES = ("不", "非")
NEGATION_PREFIXES = BROAD_NEGATION_PREFIXES + DIRECT_NEGATION_PREFIXES
NON_NEGATION_PREFIXES = ("非常", "不错", "不只是", "不仅", "不但", "不单", "不止", "不局限于")
NEGATION_BOUNDARIES = " 　，,。；;：:\n\r\t"
NEGATION_CONTRAST_BOUNDARIES = ("但是", "不过", "然而", "但", "却")
NEGATION_CONNECTORS = ("或", "和", "及", "与", "/", "、")


def select_top_references(
    product: ProductAnalysis, rows: Iterable[ReferenceRow]
) -> tuple[list[ScoredReference], list[ScoredReference]]:
    filtered_rows = _filter_reference_rows([row for row in rows if row.file_exists])
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
    score = 0
    reason: list[str] = []
    risk: list[str] = []

    if _matches_target_type(product, row):
        score += TYPE_POINTS
        reason.append("饰品类型匹配手链/手串")

    if _is_applicable(row.bracelet_applicability):
        score += APPLICABILITY_POINTS
        reason.append("适用性标记为可用于手链/手串")

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

    if _contains_any(row_text, ("手腕", "前臂", "手臂")) and _contains_any(
        row_text, ("露出", "面积足", "完整", "清楚", "清晰")
    ):
        score += WRIST_FOREARM_AREA_POINTS
        reason.append("手腕/前臂露出面积足")

    if _contains_any(
        row_text,
        ("手势", "姿势", "肤色", "皮肤", "光线", "光影", "留白", "自然光", "闪光"),
    ):
        score += GESTURE_SKIN_LIGHT_NEGATIVE_SPACE_POINTS
        reason.append("手势/肤色/光线/留白信息可复用")

    if _contains_any(row_text, ("近景", "特写", "close-up", "特近")):
        score += CLOSE_UP_POINTS
        reason.append("近景构图匹配")

    if _is_large_bead(product) and _contains_any(row_text, ("近景", "特写", "close-up", "特近")):
        score += LARGE_BEAD_CLOSE_UP_POINTS
        reason.append("大珠产品适合近景参考")

    if _is_non_priority(row.default_strategy):
        score += NON_PRIORITY_POINTS
        risk.append("默认策略提示不优先使用")

    if _is_non_target_jewelry(row):
        score += NON_TARGET_JEWELRY_POINTS
        risk.append("参考图饰品类型不是目标手链/手串")

    if _has_still_object_earring_purpose(row):
        score += STILL_OBJECT_EARRING_PURPOSE_POINTS
        risk.append("用途偏静物/物品/耳饰参考")

    ignored_reference_jewelry = _ignored_reference_jewelry(row_text)
    if ignored_reference_jewelry:
        risk.append("参考图含需忽略的非目标首饰")

    if _contains_any(row_text, ("叠戴", "堆叠", "多层", "复杂", "繁复", "多件")):
        score += STACKED_COMPLEX_JEWELRY_POINTS
        risk.append("叠戴或复杂首饰会干扰替换")

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
    }


def _style_cluster(row: ReferenceRow) -> str:
    style = row.style_category.strip()
    if style:
        return style
    return _keyword_cluster(row.combined_text())


def _scene_cluster(row: ReferenceRow) -> str:
    return _keyword_cluster(f"{row.scene_keywords} {row.notes} {row.recommended_usage}")


def _pose_cluster(row: ReferenceRow) -> str:
    text = f"{row.purpose_category} {row.recommended_usage} {row.notes}"
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


def _filter_reference_rows(rows: Sequence[ReferenceRow]) -> list[ReferenceRow]:
    for predicate in (
        _passes_hard_filter,
        _passes_medium_confidence_filter,
        _passes_non_priority_filter,
        _passes_combined_jewelry_filter,
    ):
        matches = [row for row in rows if predicate(row)]
        if matches:
            return matches
    return []


def _passes_hard_filter(row: ReferenceRow) -> bool:
    return (
        _is_high_confidence(row.confidence)
        and _is_priority_strategy(row.default_strategy)
        and _is_target_only_jewelry(row)
        and _is_applicable(row.bracelet_applicability)
    )


def _passes_medium_confidence_filter(row: ReferenceRow) -> bool:
    return (
        _is_high_or_medium_confidence(row.confidence)
        and _is_priority_strategy(row.default_strategy)
        and _is_target_only_jewelry(row)
        and _is_applicable(row.bracelet_applicability)
    )


def _passes_non_priority_filter(row: ReferenceRow) -> bool:
    return (
        _is_high_or_medium_confidence(row.confidence)
        and _is_priority_or_relaxed_non_priority(row.default_strategy)
        and _is_target_only_jewelry(row)
        and _is_applicable(row.bracelet_applicability)
    )


def _passes_combined_jewelry_filter(row: ReferenceRow) -> bool:
    return (
        _is_high_or_medium_confidence(row.confidence)
        and _is_priority_or_relaxed_non_priority(row.default_strategy)
        and _is_target_combined_jewelry(row)
        and _is_applicable(row.bracelet_applicability)
    )


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


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _contains_unnegated_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    term_list = tuple(terms)
    for term in term_list:
        lowered_term = term.lower()
        start = 0
        while True:
            index = lowered.find(lowered_term, start)
            if index == -1:
                break
            if not _has_negation_prefix(text, index, term_list):
                return True
            start = index + len(lowered_term)
    return False


def _has_negation_prefix(text: str, term_start: int, terms: tuple[str, ...]) -> bool:
    prefix = _same_clause_prefix(text, term_start)
    compact_prefix = "".join(
        char for char in prefix if not char.isspace()
    )
    negation = _nearest_valid_negation(compact_prefix)
    if negation is None:
        return False
    _, negation_text = negation
    tail = compact_prefix[negation[0] + len(negation_text) :]
    if negation_text in DIRECT_NEGATION_PREFIXES:
        return tail == "" or _contains_only_terms_and_connectors(tail, terms)
    return len(tail) <= 6


def _contains_only_terms_and_connectors(text: str, terms: tuple[str, ...]) -> bool:
    remaining = text
    sorted_terms = sorted(terms, key=len, reverse=True)
    while remaining:
        for connector in NEGATION_CONNECTORS:
            if remaining.startswith(connector):
                remaining = remaining[len(connector) :]
                break
        else:
            for term in sorted_terms:
                if remaining.startswith(term):
                    remaining = remaining[len(term) :]
                    break
            else:
                return False
    return True


def _nearest_valid_negation(compact_prefix: str) -> tuple[int, str] | None:
    candidates: list[tuple[int, str]] = []
    for negation in NEGATION_PREFIXES:
        start = 0
        while True:
            index = compact_prefix.find(negation, start)
            if index == -1:
                break
            if not _is_non_negation_phrase(compact_prefix, index):
                candidates.append((index, negation))
            start = index + len(negation)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], len(item[1])))


def _is_non_negation_phrase(compact_prefix: str, index: int) -> bool:
    return any(compact_prefix.startswith(phrase, index) for phrase in NON_NEGATION_PREFIXES)


def _same_clause_prefix(text: str, term_start: int) -> str:
    prefix = text[:term_start]
    clause_start = 0
    for boundary in NEGATION_BOUNDARIES:
        index = prefix.rfind(boundary)
        if index >= clause_start:
            clause_start = index + len(boundary)
    for boundary in NEGATION_CONTRAST_BOUNDARIES:
        index = prefix.rfind(boundary)
        if index >= clause_start:
            clause_start = index + len(boundary)
    return prefix[clause_start:]


def _has_style_match(product_text: str, row_text: str, terms: Iterable[str]) -> bool:
    term_list = tuple(terms)
    return _contains_any(product_text, term_list) and _contains_any(row_text, term_list)


def _matches_target_type(product: ProductAnalysis, row: ReferenceRow) -> bool:
    product_targets = tuple(term for term in TARGET_JEWELRY_TERMS if term in product.product_type)
    if not product_targets:
        product_targets = TARGET_JEWELRY_TERMS
    return _contains_any(row.jewelry_type, product_targets)


def _has_wearing_display_signal(row: ReferenceRow) -> bool:
    explicit_text = row.recommended_usage
    return _contains_any(
        explicit_text,
        ("佩戴展示", "上手展示", "真人佩戴", "佩戴效果", "戴手上展示"),
    )


def _is_applicable(text: str) -> bool:
    return _contains_any(text, ("是", "可用于", "适用", "手链", "手串")) and not _contains_any(
        text, ("否", "不适用", "不可用")
    )


def _is_priority_strategy(text: str) -> bool:
    return _contains_any(text, ("优先使用", "可优先", "优先")) and not _is_non_priority(text)


def _is_non_priority(text: str) -> bool:
    return _contains_any(text, ("不优先", "无特殊要求不优先", "不建议", "谨慎使用"))


def _is_relaxed_non_priority(text: str) -> bool:
    return _contains_any(text, ("无特殊要求不优先使用", "无特殊要求不优先"))


def _is_priority_or_relaxed_non_priority(text: str) -> bool:
    return _is_priority_strategy(text) or _is_relaxed_non_priority(text)


def _is_high_confidence(text: str) -> bool:
    return "高" in text


def _is_high_or_medium_confidence(text: str) -> bool:
    return _is_high_confidence(text) or "中" in text


def _is_large_bead(product: ProductAnalysis) -> bool:
    bead_diameter = product.product_dimensions.bead_diameter_mm
    return bead_diameter is not None and bead_diameter >= 10


def _is_non_target_jewelry(row: ReferenceRow) -> bool:
    jewelry_text = row.jewelry_type
    has_non_target = _contains_any(jewelry_text, NON_TARGET_JEWELRY_TERMS)
    has_target = _contains_any(jewelry_text, TARGET_JEWELRY_TERMS)
    return has_non_target and not has_target


def _is_target_only_jewelry(row: ReferenceRow) -> bool:
    jewelry_text = row.jewelry_type
    return _contains_any(jewelry_text, TARGET_FILTER_TERMS) and not _contains_any(
        jewelry_text, NON_TARGET_JEWELRY_TERMS
    )


def _is_target_combined_jewelry(row: ReferenceRow) -> bool:
    jewelry_text = row.jewelry_type
    return _contains_any(jewelry_text, TARGET_FILTER_TERMS) and _contains_any(
        jewelry_text, NON_TARGET_JEWELRY_TERMS
    )


def _has_still_object_earring_purpose(row: ReferenceRow) -> bool:
    text = f"{row.purpose_category} {row.recommended_usage} {row.notes} {row.jewelry_type}"
    return _contains_unnegated_any(text, ("静物", "摆拍", "平铺", "物品", "物体", "耳饰", "耳环"))


def _ignored_reference_jewelry(text: str) -> tuple[str, ...]:
    ignored: list[str] = []
    if _contains_unnegated_any(text, ("戒指",)):
        ignored.append("参考图中的戒指")
    if _contains_unnegated_any(text, ("耳饰", "耳环")):
        ignored.append("参考图中的耳饰")
    if _contains_unnegated_any(text, ("项链", "吊坠", "颈链")):
        ignored.append("参考图中的项链")
    if _contains_unnegated_any(
        text, ("原有手链", "原手链", "已有手链", "旧手链", "原有手串", "已有手串")
    ):
        ignored.append("参考图中的原有手链")
    return tuple(ignored)
