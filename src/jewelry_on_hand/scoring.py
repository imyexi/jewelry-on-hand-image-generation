from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from jewelry_on_hand import reference_composition as _reference_composition
from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.category_policies.base import (
    ControlledLevel,
    contains_any as _contains_any,
    contains_unnegated_any as _contains_unnegated_any,
    is_role_appropriate_priority_strategy,
    parse_confidence_level,
)
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow, ScoredReference
from jewelry_on_hand.output_roles import OutputRole, require_scene_replacement_role
from jewelry_on_hand.product_types import ProductType


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
DIVERSITY_SCORE_WINDOW = 10
DEFAULT_AUDIT_SEED = "reference-replacement-v1"
DARK_BACKGROUND_TEXT_TERMS = (
    "深色背景",
    "黑色背景",
    "暗色背景",
    "低调暗色背景",
    "暗黑背景",
    "黑背景",
    "深色布景",
    "深色布面",
    "黑色布景",
    "黑色托盘",
    "黑色石材",
    "黑色岩石",
    "黑色石板",
    "黑色底座",
    "深色沥青",
    "深色路面",
    "黑色路面",
    "黑绒",
    "黑色绒布",
)
USER_APPROVED_DARK_LIFESTYLE_REFERENCE_IDS = frozenset({"RP000298"})


@dataclass(frozen=True)
class ReferenceReadinessExclusion:
    row_index: int
    file_name: str
    field_name: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "row_index": self.row_index,
            "file_name": self.file_name,
            "field_name": self.field_name,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReferenceSelectionResult:
    output_role: OutputRole
    source_count: int
    existing_count: int
    role_count: int
    category_eligible_count: int
    selected: tuple[ScoredReference, ...]
    candidates: tuple[ScoredReference, ...]
    readiness_exclusions: tuple[ReferenceReadinessExclusion, ...]

    def readiness_audit(self) -> dict[str, object]:
        return {
            "output_role": self.output_role.value,
            "source_count": self.source_count,
            "existing_count": self.existing_count,
            "role_count": self.role_count,
            "category_eligible_count": self.category_eligible_count,
            "eligible_count": len(self.candidates),
            "selected_count": len(self.selected),
            "exclusions": [
                exclusion.to_dict() for exclusion in self.readiness_exclusions
            ],
        }


def select_top_references(
    product: ProductAnalysis,
    rows: Iterable[ReferenceRow],
    output_role: OutputRole | str,
    *,
    signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
) -> tuple[list[ScoredReference], list[ScoredReference]]:
    result = select_reference_candidates(
        product,
        rows,
        output_role,
        signature_usage=signature_usage,
        audit_seed=audit_seed,
    )
    if (
        product.confirmed_product_type is ProductType.RING
        and len(result.candidates) < 3
    ):
        exclusion_text = _readiness_exclusion_summary(
            result.readiness_exclusions
        )
        raise ValueError(
            "戒指参考图至少 3 张合格候选，"
            f"当前 {len(result.candidates)} 张"
            f"（存在文件 {result.existing_count} 张）"
            f"{exclusion_text}"
        )
    return list(result.selected), list(result.candidates)


def select_reference_candidates(
    product: ProductAnalysis,
    rows: Iterable[ReferenceRow],
    output_role: OutputRole | str,
    *,
    signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
) -> ReferenceSelectionResult:
    role = require_scene_replacement_role(output_role, stage="参考图选择")
    source_rows = list(rows)
    existing_rows = [row for row in source_rows if row.file_exists]
    role_rows = [
        row for row in existing_rows if row.purpose_category.strip() == role.display_name
    ]
    if not role_rows:
        raise ValueError(f"没有飞书用途分类为{role.display_name}的参考图")
    dark_role_rows = [row for row in role_rows if _has_dark_background_signal(row)]
    if not dark_role_rows:
        raise ValueError(f"{role.display_name}没有符合深色背景要求的参考图")
    filtered_rows = _filter_reference_rows(product, dark_role_rows)
    ready_rows: list[ReferenceRow] = []
    readiness_exclusions: list[ReferenceReadinessExclusion] = []
    for row in filtered_rows:
        readiness = _reference_composition.assess_candidate_snapshot_readiness(
            product,
            row,
            role,
        )
        if readiness.ready:
            ready_rows.append(row)
            continue
        readiness_exclusions.append(
            ReferenceReadinessExclusion(
                row_index=row.index,
                file_name=row.file_name,
                field_name=readiness.field_name or "unknown",
                reason=readiness.reason or "无法确认快照完整性",
            )
        )
    scored = [score_reference(product, row) for row in ready_rows]
    ordered = sorted(scored, key=lambda item: (-item.score, item.row.index))
    candidates = _rerank(ordered)
    selected = select_diverse_eligible_references(
        candidates,
        role,
        signature_usage=signature_usage,
        audit_seed=audit_seed,
    )
    return ReferenceSelectionResult(
        output_role=role,
        source_count=len(source_rows),
        existing_count=len(existing_rows),
        role_count=len(role_rows),
        category_eligible_count=len(filtered_rows),
        selected=tuple(selected),
        candidates=tuple(candidates),
        readiness_exclusions=tuple(readiness_exclusions),
    )


def require_three_review_candidates(result: ReferenceSelectionResult) -> None:
    if len(result.selected) == 3:
        return
    details = [
        f"{result.output_role.display_name}可审核候选不足 3 张",
        f"合格候选 {len(result.selected)} 张",
        f"快照完整且通过硬门 {len(result.candidates)} 张",
    ]
    if len(result.selected) < len(result.candidates):
        details.append(f"十分质量窗口内 {len(result.selected)} 张")
    summary = _readiness_exclusion_summary(result.readiness_exclusions)
    if summary:
        details.append(summary.lstrip("；"))
    raise ValueError("：".join((details[0], "；".join(details[1:]))))


def _readiness_exclusion_summary(
    exclusions: Sequence[ReferenceReadinessExclusion],
) -> str:
    if not exclusions:
        return ""
    counts = Counter(exclusion.field_name for exclusion in exclusions)
    fields = "、".join(
        f"{field_name} {count} 张"
        for field_name, count in sorted(counts.items())
    )
    return f"；快照完整性排除 {len(exclusions)} 张（{fields}）"


def composition_signature_for_row(
    row: ReferenceRow, output_role: OutputRole | str
) -> str:
    role = require_scene_replacement_role(output_role, stage="构图签名")
    background_markers = (
        "背景",
        "布景",
        "布面",
        "路面",
        "托盘",
        "石材",
        "岩石",
        "石板",
        "底座",
        "绒布",
    )
    visible_body_regions = _signature_review_values(row.visible_body_regions)
    pose = _reference_composition.ReferencePose(
        body=_signature_pose_segment(
            row.pose_keywords,
            ("身体", "躯干", "上半身", "全身", "半身", "未入镜"),
        ),
        arm=_signature_pose_segment(
            row.pose_keywords,
            ("手臂", "前臂", "臂", "胳膊"),
        ),
        hand=_signature_value(row.hand_orientation),
        hand_side=_signature_value(row.hand_side),
    )
    source_jewelry = _signature_value(row.existing_jewelry)
    replacement_target = _reference_composition.ReplacementTarget(
        body_region=_reference_composition._replacement_body_region(
            pose.hand_side,
            visible_body_regions,
            _reference_composition._unique_target_selector(source_jewelry),
        ),
        source_jewelry=source_jewelry,
        target_product_count=1,
    )
    return _reference_composition._composition_signature(
        output_role=role,
        framing=_signature_value(row.framing),
        pose=pose,
        background=_reference_composition._required_review_value(
            _reference_composition._join_unique_review_values(
                *_reference_composition._extract_matching_review_segments(
                    row.scene_keywords,
                    background_markers,
                ),
                *_reference_composition._extract_matching_review_segments(
                    row.notes,
                    background_markers,
                ),
            ),
            "background",
        ),
        lighting=_reference_composition._join_review_values(
            _signature_value(row.style_category),
            *_reference_composition._extract_matching_review_segments(
                row.notes,
                (
                    "光线",
                    "光影",
                    "自然光",
                    "侧光",
                    "逆光",
                    "柔光",
                    "闪光",
                    "照明",
                    "曝光",
                    "阴影",
                ),
            ),
        ),
        replacement_target=replacement_target,
    )


def _signature_value(value: str) -> str:
    return value.strip() or "未标注"


def _signature_review_values(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ("未标注",)
    return _reference_composition._split_review_values(
        value,
        "visible_body_regions",
    )


def _signature_pose_segment(value: str, markers: Sequence[str]) -> str:
    if not value.strip():
        return "未标注"
    try:
        return _reference_composition._extract_review_segment(
            value,
            markers,
            "构图签名姿势",
        )
    except ValueError:
        return "未标注"


def _audit_tie_break(seed: str, signature: str, file_name: str) -> str:
    payload = f"{seed}\0{signature}\0{file_name}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_diverse_eligible_references(
    candidates: Sequence[ScoredReference],
    output_role: OutputRole | str,
    *,
    signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
    limit: int = 3,
) -> list[ScoredReference]:
    role = require_scene_replacement_role(output_role, stage="低重复参考图选择")
    if not candidates or limit <= 0:
        return []
    usage = signature_usage or {}
    floor = max(item.score for item in candidates) - DIVERSITY_SCORE_WINDOW
    pool = [item for item in candidates if item.score >= floor]

    def ordering_key(item: ScoredReference) -> tuple[int, int, str]:
        signature = composition_signature_for_row(item.row, role)
        return (
            usage.get(signature, 0),
            -item.score,
            _audit_tie_break(audit_seed, signature, item.row.file_name),
        )

    return _rerank(sorted(pool, key=ordering_key)[: min(limit, 3)])


def select_batch_diverse_references(
    candidate_sets: Sequence[Sequence[ScoredReference]],
    output_roles: Sequence[OutputRole | str],
    *,
    limit: int = 3,
    initial_signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
) -> list[list[ScoredReference]]:
    if len(candidate_sets) != len(output_roles):
        raise ValueError("候选集合与输出角色数量必须一致")
    usage = dict(initial_signature_usage or {})
    selections: list[list[ScoredReference]] = []
    for index, (candidates, role) in enumerate(
        zip(candidate_sets, output_roles, strict=True)
    ):
        selected = select_diverse_eligible_references(
            candidates,
            role,
            signature_usage=usage,
            audit_seed=f"{audit_seed}:{index}",
            limit=limit,
        )
        selections.append(selected)
        for item in selected:
            signature = composition_signature_for_row(item.row, role)
            usage[signature] = usage.get(signature, 0) + 1
    return selections


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

    if is_role_appropriate_priority_strategy(row):
        score += PRIORITY_STRATEGY_POINTS
        if _is_lifestyle_non_wrist_strategy(row):
            reason.append("生活场景角色匹配非手腕构图策略")
        else:
            reason.append("默认策略为优先使用")

    if parse_confidence_level(row.confidence) is ControlledLevel.HIGH:
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

    if _is_non_priority(
        row.default_strategy
    ) and not _is_lifestyle_non_wrist_strategy(row):
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
    return [row for row, adaptation in evaluated if adaptation.eligible]


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


def _is_lifestyle_non_wrist_strategy(row: ReferenceRow) -> bool:
    return (
        row.purpose_category.strip() == OutputRole.LIFESTYLE.display_name
        and _contains_any(
            row.default_strategy,
            ("非手腕构图，默认不优先", "非手腕构图"),
        )
    )


def _has_dark_background_signal(row: ReferenceRow) -> bool:
    if _contains_any(row.combined_text(), DARK_BACKGROUND_TEXT_TERMS):
        return True
    if row.purpose_category.strip() != OutputRole.LIFESTYLE.display_name:
        return False
    return any(
        f"素材编号：{reference_id}" in row.notes
        for reference_id in USER_APPROVED_DARK_LIFESTYLE_REFERENCE_IDS
    )


def _is_non_priority(text: str) -> bool:
    return _contains_any(text, ("不优先", "无特殊要求不优先", "不建议", "谨慎使用"))


def _has_still_object_earring_purpose(row: ReferenceRow) -> bool:
    text = f"{row.purpose_category} {row.recommended_usage} {row.notes} {row.jewelry_type}"
    return _contains_unnegated_any(text, ("静物", "摆拍", "平铺", "物品", "物体", "耳饰", "耳环"))
