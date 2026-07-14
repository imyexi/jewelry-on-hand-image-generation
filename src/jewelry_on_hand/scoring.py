from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.category_policies.base import (
    ControlledLevel,
    contains_any as _contains_any,
    contains_unnegated_any as _contains_unnegated_any,
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


def select_top_references(
    product: ProductAnalysis,
    rows: Iterable[ReferenceRow],
    output_role: OutputRole | str,
    *,
    signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
) -> tuple[list[ScoredReference], list[ScoredReference]]:
    role = require_scene_replacement_role(output_role, stage="参考图选择")
    existing_rows = [row for row in rows if row.file_exists]
    role_rows = [
        row for row in existing_rows if row.purpose_category.strip() == role.display_name
    ]
    if not role_rows:
        raise ValueError(f"没有飞书用途分类为{role.display_name}的参考图")
    filtered_rows = _filter_reference_rows(product, role_rows)
    if product.confirmed_product_type is ProductType.RING and len(filtered_rows) < 3:
        raise ValueError(
            "戒指参考图至少 3 张合格候选，"
            f"当前 {len(filtered_rows)} 张（存在文件 {len(existing_rows)} 张）"
        )
    scored = [score_reference(product, row) for row in filtered_rows]
    ordered = sorted(scored, key=lambda item: (-item.score, item.row.index))
    candidates = _rerank(ordered)
    selected = select_diverse_eligible_references(
        candidates,
        role,
        signature_usage=signature_usage,
        audit_seed=audit_seed,
    )
    return selected, candidates


def composition_signature_for_row(
    row: ReferenceRow, output_role: OutputRole | str
) -> str:
    role = require_scene_replacement_role(output_role, stage="构图签名")
    profile = _diversity_profile(row)
    payload = {
        "输出角色": role.value,
        "人物取景": _normalized_signature_value(row.framing),
        "身体区域": _normalized_signature_value(row.visible_body_regions),
        "姿势": _normalized_signature_value(row.pose_keywords),
        "镜面关系": _normalized_signature_value(row.mirror_relation),
        "手侧": _normalized_signature_value(row.hand_side),
        "手部朝向": _normalized_signature_value(row.hand_orientation),
        "衣领": _normalized_signature_value(row.collar_type),
        "头发位置": profile["hair_position"],
        "身体朝向": profile["body_orientation"],
        "持握方式": profile["holding_method"],
        "场景": profile["scene_cluster"],
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _normalized_signature_value(value: str) -> str:
    return " ".join(value.strip().lower().split()) or "未标注"


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

    if _is_priority_strategy(row.default_strategy):
        score += PRIORITY_STRATEGY_POINTS
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


def _is_non_priority(text: str) -> bool:
    return _contains_any(text, ("不优先", "无特殊要求不优先", "不建议", "谨慎使用"))


def _has_still_object_earring_purpose(row: ReferenceRow) -> bool:
    text = f"{row.purpose_category} {row.recommended_usage} {row.notes} {row.jewelry_type}"
    return _contains_unnegated_any(text, ("静物", "摆拍", "平铺", "物品", "物体", "耳饰", "耳环"))
