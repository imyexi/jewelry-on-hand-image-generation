from dataclasses import replace
from pathlib import Path

import pytest

from jewelry_on_hand import scoring as scoring_module
from jewelry_on_hand.models import ProductAnalysis, ProductDimensions, ReferenceRow, ScoredReference
from jewelry_on_hand.output_roles import OutputRole
from jewelry_on_hand.reference_composition import build_candidate_snapshot
from jewelry_on_hand.ring_attributes import FingerPosition
from jewelry_on_hand.scoring import (
    score_reference,
    select_batch_diverse_references,
    select_top_references,
)


def composition_signature_for_row(reference, output_role):
    return scoring_module.composition_signature_for_row(reference, output_role)


def select_diverse_eligible_references(candidates, output_role, **kwargs):
    return scoring_module.select_diverse_eligible_references(
        candidates, output_role, **kwargs
    )


def row(index, exists=True, strategy="常规可优先使用", file_name=None, **overrides):
    data = {
        "purpose_category": "手部佩戴图",
        "bracelet_applicability": "是：可用于手链/手串",
        "default_strategy": strategy,
        "style_category": "暗调闪光",
        "scene_keywords": "车内 闪光",
        "jewelry_type": "手链/手串",
        "recommended_usage": "近景手腕",
        "notes": "手腕/前臂露出面积足",
        "confidence": "高",
        "product_visibility": "高",
        "crop_risk": "低",
        "applicable_product_types": "",
        "applicable_display_modes": "",
        "framing": "手部近景",
        "visible_body_regions": "左手腕、前臂",
        "hand_visibility": "完整可见",
        "collar_type": "无可见服装",
        "clothing_occlusion_risk": "无遮挡",
        "hair_occlusion_risk": "无遮挡",
        "pose_keywords": "身体未入镜；前臂自然抬起",
        "existing_jewelry": "左手腕单条手链",
        "hand_side": "左手",
        "hand_orientation": "手背朝向镜头",
    }
    data.update(overrides)
    data["notes"] = (
        f"正面视角；主体居中；{data['notes']}；无文字或平台界面"
    )
    return ReferenceRow(
        index,
        file_name or f"{index}.jpg",
        f"ref/{index}.jpg",
        Path(__file__).resolve(),
        100,
        200,
        0.1,
        data["purpose_category"],
        data["bracelet_applicability"],
        data["default_strategy"],
        data["style_category"],
        data["scene_keywords"],
        data["jewelry_type"],
        data["recommended_usage"],
        data["notes"],
        data["confidence"],
        exists,
        applicable_product_types=data["applicable_product_types"],
        applicable_display_modes=data["applicable_display_modes"],
        framing=data["framing"],
        visible_body_regions=data["visible_body_regions"],
        product_visibility=data["product_visibility"],
        hand_visibility=data["hand_visibility"],
        collar_type=data["collar_type"],
        clothing_occlusion_risk=data["clothing_occlusion_risk"],
        hair_occlusion_risk=data["hair_occlusion_risk"],
        pose_keywords=data["pose_keywords"],
        existing_jewelry=data["existing_jewelry"],
        crop_risk=data["crop_risk"],
        hand_side=data["hand_side"],
        hand_orientation=data["hand_orientation"],
    )


def product(**overrides):
    data = {
        "product_type": "手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "深红主珠",
        "color_family": ["深红"],
        "style_mood": "暗调闪光",
        "composition": "手腕近景",
        "product_dimensions": ProductDimensions(bead_diameter_mm=10),
        "needs_full_front_display": True,
        "special_requirements": ["保留主珠"],
    }
    data.update(overrides)
    return ProductAnalysis(**data)


def test_角色硬门只读取飞书用途分类字段():
    wrong_type = replace(
        row(1),
        purpose_category="主图",
        scene_keywords="手部佩戴图 生活场景图 深色背景",
        recommended_usage="手部佩戴图",
    )

    with pytest.raises(ValueError, match="手部佩戴图"):
        select_top_references(product(), [wrong_type], OutputRole.HAND_WORN)


def test_快照不完整行在评分与低重复选择前排除并记录原因():
    incomplete = replace(row(1), collar_type="")
    complete = [
        replace(row(2), framing="手腕近景"),
        replace(row(3), framing="手部中景"),
        replace(row(4), framing="半身手部构图"),
    ]
    usage = {
        composition_signature_for_row(complete[0], OutputRole.HAND_WORN): 5,
        composition_signature_for_row(complete[1], OutputRole.HAND_WORN): 0,
        composition_signature_for_row(complete[2], OutputRole.HAND_WORN): 1,
    }

    result = scoring_module.select_reference_candidates(
        product(),
        [incomplete, *complete],
        OutputRole.HAND_WORN,
        signature_usage=usage,
        audit_seed="快照就绪硬门",
    )

    assert {item.row.index for item in result.candidates} == {2, 3, 4}
    assert [item.row.index for item in result.selected] == [3, 4, 2]
    assert len(result.readiness_exclusions) == 1
    assert result.readiness_exclusions[0].row_index == 1
    assert result.readiness_exclusions[0].field_name == "clothing"


def test_低重复选择绝不越过十分质量窗口():
    references = [row(index) for index in range(1, 5)]
    scored = [
        ScoredReference(reference, score, rank, (), (), ())
        for rank, (reference, score) in enumerate(
            zip(references, [100, 96, 90, 89], strict=True),
            start=1,
        )
    ]
    selected = select_diverse_eligible_references(
        scored,
        OutputRole.HAND_WORN,
        signature_usage={
            composition_signature_for_row(scored[3].row, OutputRole.HAND_WORN): 0,
            composition_signature_for_row(scored[0].row, OutputRole.HAND_WORN): 8,
        },
        audit_seed="QY027-hand_worn",
    )

    assert [item.score for item in selected] == [100, 96, 90]
    assert 89 not in [item.score for item in selected]


def test_同分候选优先选择使用次数较少的构图签名():
    references = [
        replace(row(1), framing="手腕近景"),
        replace(row(2), framing="手部中景"),
        replace(row(3), framing="半身手部构图"),
    ]
    scored = [
        ScoredReference(reference, 100, rank, (), (), ())
        for rank, reference in enumerate(references, start=1)
    ]
    usage = {
        composition_signature_for_row(scored[0].row, OutputRole.LIFESTYLE): 5,
        composition_signature_for_row(scored[1].row, OutputRole.LIFESTYLE): 0,
        composition_signature_for_row(scored[2].row, OutputRole.LIFESTYLE): 1,
    }

    selected = select_diverse_eligible_references(
        scored,
        OutputRole.LIFESTYLE,
        signature_usage=usage,
        audit_seed="QY018",
    )

    assert selected[0].row == scored[1].row


def test_完全平局顺序在相同种子下稳定且可由不同种子改变():
    scored = [
        ScoredReference(replace(row(index), framing="相同构图"), 100, index, (), (), ())
        for index in range(1, 5)
    ]

    first = select_diverse_eligible_references(
        scored, OutputRole.HAND_WORN, audit_seed="固定审计种子"
    )
    repeated = select_diverse_eligible_references(
        tuple(reversed(scored)), OutputRole.HAND_WORN, audit_seed="固定审计种子"
    )
    orders = {
        tuple(
            item.row.file_name
            for item in select_diverse_eligible_references(
                scored,
                OutputRole.HAND_WORN,
                audit_seed=f"审计种子{index}",
            )
        )
        for index in range(20)
    }

    assert [item.row.file_name for item in first] == [
        item.row.file_name for item in repeated
    ]
    assert len(orders) > 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"notes": "画面含平台界面和状态栏"},
        {"product_visibility": "低"},
        {"notes": "目标手腕与首饰区域严重遮挡"},
        {"crop_risk": "高"},
        {"existing_jewelry": "原首饰无法完整识别"},
        {
            "notes": "仅手指完整可见",
            "recommended_usage": "手指近景",
            "visible_body_regions": "手指",
        },
    ],
)
def test_硬门阻止界面低展示遮挡裁切及原首饰不可识别候选(overrides):
    rejected = replace(row(1), **overrides)
    valid = replace(
        row(2),
        product_visibility="高",
        crop_risk="低",
        existing_jewelry="完整可识别的原手串",
    )

    selected, candidates = select_top_references(
        product(), [rejected, valid], OutputRole.HAND_WORN
    )

    assert [item.row.index for item in candidates] == [2]
    assert [item.row.index for item in selected] == [2]


def test_批次选择累计构图签名使用次数():
    first = ScoredReference(replace(row(1), framing="手腕近景"), 100, 1, (), (), ())
    second = ScoredReference(replace(row(2), framing="手部中景"), 100, 2, (), (), ())

    selections = select_batch_diverse_references(
        [[first, second], [first, second]],
        [OutputRole.HAND_WORN, OutputRole.HAND_WORN],
        limit=1,
        audit_seed="批次审计",
    )

    assert composition_signature_for_row(
        selections[0][0].row, OutputRole.HAND_WORN
    ) != composition_signature_for_row(
        selections[1][0].row, OutputRole.HAND_WORN
    )


def test_不同输出角色的构图签名互不计数():
    first = replace(row(1), framing="手腕近景")
    second = replace(row(2), framing="手部中景")
    assert composition_signature_for_row(first, OutputRole.HAND_WORN) != (
        composition_signature_for_row(first, OutputRole.LIFESTYLE)
    )

    scored = [
        ScoredReference(first, 100, 1, (), (), ()),
        ScoredReference(second, 100, 2, (), (), ()),
    ]
    baseline = select_diverse_eligible_references(
        scored, OutputRole.LIFESTYLE, audit_seed="角色隔离", limit=1
    )
    with_foreign_usage = select_diverse_eligible_references(
        scored,
        OutputRole.LIFESTYLE,
        signature_usage={
            composition_signature_for_row(
                baseline[0].row, OutputRole.HAND_WORN
            ): 99
        },
        audit_seed="角色隔离",
        limit=1,
    )

    assert with_foreign_usage[0].row == baseline[0].row


def test_候选包含全部通过硬门的质量层级并按分数排序():
    references = [
        row(1, confidence="高"),
        row(2, confidence="中"),
        row(3, confidence="高", strategy="无特殊要求不优先使用"),
    ]

    _, candidates = select_top_references(
        product(), references, OutputRole.HAND_WORN
    )

    assert {item.row.index for item in candidates} == {1, 2, 3}
    assert [item.score for item in candidates] == sorted(
        [item.score for item in candidates], reverse=True
    )


def test_低重复选择即使放宽数量也最多返回三张():
    candidates = [
        ScoredReference(row(index), 100, index, (), (), ())
        for index in range(1, 6)
    ]

    selected = select_diverse_eligible_references(
        candidates, OutputRole.HAND_WORN, limit=9
    )

    assert len(selected) == 3


def test_批次候选与输出角色数量不一致时使用中文报错():
    with pytest.raises(ValueError, match="候选集合与输出角色数量必须一致"):
        select_batch_diverse_references([[]], [])


def test_select_top_references_filters_missing_and_scores_priority():
    selected, candidates = select_top_references(
        product(),
        [row(1), row(2, exists=False), row(3, strategy="无特殊要求不优先使用")],
        OutputRole.HAND_WORN,
    )
    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1, 3]
    assert any("暗调" in reason for reason in selected[0].reason)


def test_候选保留全部硬门通过项而选择仅限十分窗口():
    rows = [
        row(1),
        row(2, style_category="清晰自然", scene_keywords="自然光 留白", notes="手腕露出面积足"),
        row(3, recommended_usage="佩戴展示 近景手腕"),
        row(4, style_category="清晰自然", scene_keywords="自然光 留白", notes="手腕露出面积足"),
    ]
    selected, candidates = select_top_references(product(), rows, OutputRole.HAND_WORN)
    assert len(selected) == 1
    assert len(candidates) == 4
    assert [item.rank for item in selected] == [1]
    assert [item.rank for item in candidates] == [1, 2, 3, 4]
    assert [item.score for item in candidates] == sorted(
        [item.score for item in candidates], reverse=True
    )


def test_candidate_pool_keeps_clean_rows_and_adds_combined_jewelry_for_batch_diversity():
    clean = row(1, file_name="clean.jpg")
    combined = row(
        2,
        file_name="combined.jpg",
        jewelry_type="手链、项链、戒指组合",
        scene_keywords="对镜 室内 自然光",
        recommended_usage="对镜手腕构图",
    )

    selected, candidates = select_top_references(
        product(), [clean, combined], OutputRole.HAND_WORN
    )

    assert {item.row.file_name for item in candidates} == {"clean.jpg", "combined.jpg"}
    assert selected[0].row.file_name == "combined.jpg"
    combined_candidate = next(
        item for item in candidates if item.row.file_name == "combined.jpg"
    )
    assert combined_candidate.ignored_reference_jewelry


def test_选择结果稳定且绝不为旧多样性惩罚突破质量窗口():
    rows = [
        row(30, file_name="1（30）.png", style_category="暗调高级/黑衣近景"),
        row(31, file_name="1（31）.png", style_category="暗调高级/黑衣近景"),
        row(32, file_name="1（32）.png", style_category="暗调高级/黑衣近景"),
        row(
            101,
            file_name="outdoor-101.jpg",
            style_category="户外自然光",
            scene_keywords="户外 阳光 手腕清晰",
            recommended_usage="手腕中景",
            notes="手腕/前臂露出面积足，无裁切",
        ),
        row(
            102,
            file_name="mirror-102.jpg",
            style_category="对镜生活感",
            scene_keywords="对镜 室内 自然光",
            recommended_usage="对镜手腕构图",
            notes="手腕露出完整，无裁切",
        ),
    ]

    selected, candidates = select_top_references(
        product(), rows, OutputRole.HAND_WORN, audit_seed="稳定选择"
    )
    repeated, _ = select_top_references(
        product(), reversed(rows), OutputRole.HAND_WORN, audit_seed="稳定选择"
    )

    assert [item.row.file_name for item in selected] == [
        item.row.file_name for item in repeated
    ]
    assert all(item.score >= candidates[0].score - 10 for item in selected)


def test_批次低重复不会越过质量窗口复用唯一合格构图():
    rows = [
        row(30, file_name="1（30）.png", style_category="暗调高级/黑衣近景"),
        row(31, file_name="1（31）.png", style_category="暗调高级/黑衣近景"),
        row(32, file_name="1（32）.png", style_category="暗调高级/黑衣近景"),
        row(101, file_name="outdoor-101.jpg", style_category="户外自然光"),
        row(102, file_name="mirror-102.jpg", style_category="对镜生活感"),
    ]
    _, first_candidates = select_top_references(product(), rows, OutputRole.HAND_WORN)
    _, second_candidates = select_top_references(product(), rows, OutputRole.HAND_WORN)

    first_selected, second_selected = select_batch_diverse_references(
        [first_candidates, second_candidates],
        [OutputRole.HAND_WORN, OutputRole.HAND_WORN],
    )

    assert [item.row.file_name for item in first_selected] == [
        item.row.file_name for item in second_selected
    ]


def test_批次选择遵循初始构图签名使用次数():
    rows = [
        replace(
            row(1, file_name="already-used.jpg", style_category="dark"),
            framing="手腕近景",
        ),
        replace(
            row(2, file_name="unused.jpg", style_category="light"),
            framing="手部中景",
        ),
    ]
    _, candidates = select_top_references(product(), rows, OutputRole.HAND_WORN)

    [selected] = select_batch_diverse_references(
        [candidates],
        [OutputRole.HAND_WORN],
        limit=1,
        initial_signature_usage={
            composition_signature_for_row(rows[0], OutputRole.HAND_WORN): 1,
        },
    )

    assert [item.row.file_name for item in selected] == ["unused.jpg"]


def test_批次选择不会为了低重复越过十分质量窗口():
    candidates = [
        ScoredReference(row(1, file_name="already-used.jpg"), 150, 1, (), (), ()),
        ScoredReference(row(2, file_name="lower-unused.jpg"), 80, 2, (), (), ()),
    ]

    [selected] = select_batch_diverse_references(
        [candidates],
        [OutputRole.HAND_WORN],
        limit=1,
        initial_signature_usage={
            composition_signature_for_row(candidates[0].row, OutputRole.HAND_WORN): 1,
        },
    )

    assert [item.row.file_name for item in selected] == ["already-used.jpg"]


def test_select_top_references_relaxes_to_medium_confidence_when_no_high_candidate():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, confidence="中"),
            row(2, exists=False, confidence="高"),
            row(3, confidence="低"),
        ],
        OutputRole.HAND_WORN,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_select_top_references_relaxes_to_non_priority_strategy_after_confidence():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, confidence="低"),
            row(2, strategy="无特殊要求不优先使用"),
            row(3, strategy="谨慎使用"),
        ],
        OutputRole.HAND_WORN,
    )

    assert [item.row.index for item in selected] == [2]
    assert [item.row.index for item in candidates] == [2]
    assert any("不优先" in item for item in selected[0].risk)


def test_select_top_references_relaxes_to_combined_target_jewelry_after_strategy():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, confidence="低"),
            row(2, strategy="谨慎使用"),
            row(3, jewelry_type="手链、项链、戒指组合"),
            row(4, jewelry_type="项链"),
        ],
        OutputRole.HAND_WORN,
    )

    assert [item.row.index for item in selected] == [3]
    assert [item.row.index for item in candidates] == [3]
    assert any("戒指" in item for item in selected[0].ignored_reference_jewelry)
    assert any("项链" in item for item in selected[0].ignored_reference_jewelry)


def test_score_reference_records_risks_and_ignored_reference_jewelry():
    scored = score_reference(
        product(),
        row(
            5,
            strategy="无特殊要求不优先使用",
            jewelry_type="手链/手串、戒指、项链",
            notes="叠戴复杂，存在裁切风险，参考图中有原有手链",
        ),
    )
    assert any("不优先" in item for item in scored.risk)
    assert any("叠戴" in item or "复杂" in item for item in scored.risk)
    assert any("裁切" in item for item in scored.risk)
    assert any("戒指" in item for item in scored.ignored_reference_jewelry)
    assert any("项链" in item for item in scored.ignored_reference_jewelry)
    assert any("原有手链" in item for item in scored.ignored_reference_jewelry)


def test_clear_natural_match_requires_specific_visual_signal():
    generic = score_reference(
        product(style_mood="自然真实的小红书上手试戴图"),
        row(
            201,
            style_category="清透奶油系/白衬衫",
            scene_keywords="室内自然光 白衣",
        ),
    )
    specific = score_reference(
        product(style_mood="清透浅色自然光"),
        row(
            202,
            style_category="清透奶油系/白衬衫",
            scene_keywords="室内自然光 白衣",
        ),
    )

    assert not any("清晰自然风格匹配" in reason for reason in generic.reason)
    assert any("清晰自然风格匹配" in reason for reason in specific.reason)
    assert specific.score == generic.score + 15


def test_non_target_jewelry_does_not_reuse_applicability_denial():
    not_applicable = score_reference(
        product(),
        row(17, jewelry_type="手链/手串", bracelet_applicability="否：不适用"),
    )
    neutral = score_reference(
        product(),
        row(18, jewelry_type="手链/手串", bracelet_applicability=""),
    )

    assert not any("饰品类型不是目标" in item for item in not_applicable.risk)
    assert not_applicable.score == neutral.score


def test_crop_risk_ignores_negated_crop_and_occlusion_terms():
    cases = (
        "无遮挡，无裁切，不缺失",
        "没有裁切",
        "没有裁切或遮挡",
        "没有明显裁切/遮挡",
    )

    for index, notes in enumerate(cases, start=19):
        scored = score_reference(product(), row(index, notes=notes))
        assert not any("裁切" in item or "遮挡" in item or "缺失" in item for item in scored.risk)


def test_ignored_reference_jewelry_ignores_negated_jewelry_terms():
    cases = (
        "无戒指，没有项链，无耳饰",
        "无戒指或项链",
        "没有佩戴戒指",
    )

    for index, notes in enumerate(cases, start=30):
        scored = score_reference(product(), row(index, notes=notes))
        assert scored.ignored_reference_jewelry == ()


def test_still_object_earring_purpose_ignores_negated_earring_terms():
    cases = ("无耳饰", "没有耳饰", "未见耳环")

    for index, notes in enumerate(cases, start=40):
        scored = score_reference(product(), row(index, notes=notes))
        assert not any("耳饰参考" in item for item in scored.risk)


def test_still_object_purpose_ignores_negated_still_life_terms():
    baseline = score_reference(product(), row(50, notes="普通参考"))
    cases = ("不是静物参考", "没有物品摆拍", "非静物摆拍")

    for index, notes in enumerate(cases, start=51):
        scored = score_reference(product(), row(index, notes=notes))
        assert not any("静物/物品/耳饰参考" in item for item in scored.risk)
        assert scored.score == baseline.score

    positive = score_reference(product(), row(60, notes="静物摆拍"))

    assert any("静物/物品/耳饰参考" in item for item in positive.risk)
    assert positive.score == baseline.score - 50


def test_still_object_purpose_keeps_positive_words_with_non_negation_prefixes():
    baseline = score_reference(product(), row(61, notes="普通参考"))
    cases = (
        "非常适合静物摆拍",
        "不错的静物摆拍",
        "非传统静物摆拍",
        "非典型静物摆拍",
        "不止静物摆拍",
        "不局限于静物摆拍",
    )

    for index, notes in enumerate(cases, start=62):
        scored = score_reference(product(), row(index, notes=notes))
        assert any("静物/物品/耳饰参考" in item for item in scored.risk)
        assert scored.score == baseline.score - 50


def test_non_target_jewelry_type_still_deducts_for_necklace():
    neutral = score_reference(product(), row(21, jewelry_type="未知", bracelet_applicability=""))
    necklace = score_reference(product(), row(22, jewelry_type="项链", bracelet_applicability=""))

    assert any("饰品类型不是目标" in item for item in necklace.risk)
    assert necklace.score == neutral.score - 40


def test_type_points_only_use_reference_jewelry_type():
    target = score_reference(product(), row(6, jewelry_type="手链/手串"))
    necklace = score_reference(
        product(),
        row(7, jewelry_type="项链", bracelet_applicability="是：可用于手链/手串"),
    )

    assert any("饰品类型匹配" in item for item in target.reason)
    assert not any("饰品类型匹配" in item for item in necklace.reason)
    assert target.score >= necklace.score + 30


def test_wearing_display_requires_explicit_display_usage():
    implicit = score_reference(product(), row(8, recommended_usage="近景手腕"))
    explicit = score_reference(product(), row(9, recommended_usage="佩戴展示 近景手腕"))

    assert not any("佩戴展示" in item for item in implicit.reason)
    assert any("佩戴展示" in item for item in explicit.reason)
    assert explicit.score >= implicit.score + 12


def test_wearing_display_ignores_pose_and_stacked_purpose_without_usage_signal():
    pose_reference = score_reference(
        product(),
        row(14, purpose_category="佩戴姿势参考", recommended_usage="近景手腕"),
    )
    stacked_reference = score_reference(
        product(),
        row(15, purpose_category="叠戴复杂参考", recommended_usage="近景手腕"),
    )
    explicit = score_reference(product(), row(16, recommended_usage="佩戴展示"))

    assert not any("佩戴展示" in item for item in pose_reference.reason)
    assert not any("佩戴展示" in item for item in stacked_reference.reason)
    assert any("佩戴展示" in item for item in explicit.reason)


def test_select_top_references_uses_model_rank_without_bypass():
    rows = [row(10), row(11), row(12), row(13)]

    _, candidates = select_top_references(product(), rows, OutputRole.HAND_WORN)

    assert [item.rank for item in candidates] == [1, 2, 3, 4]


def ring_product():
    return ProductAnalysis.from_dict(
        {
            "product_type": "戒指",
            "detected_product_type": "ring",
            "confirmed_product_type": "ring",
            "classification_confidence": "high",
            "classification_evidence": ["单枚戒指佩戴在左手无名指根部"],
            "classification_source": "model",
            "wear_position": "左手无名指根部",
            "visible_appearance": "单枚银色素圈戒",
            "color_family": ["银色"],
            "style_mood": "清透自然",
            "composition": "手部近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "source_image_type": "worn_source",
            "display_mode": "worn",
            "layer_count": 1,
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
        }
    )


def ring_row(index, **overrides):
    data = {
        "index": index,
        "file_name": f"ring-{index}.jpg",
        "relative_path": f"ring-{index}.jpg",
        "absolute_path": Path(__file__).resolve(),
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "手部佩戴图",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "清透自然光",
        "scene_keywords": "深色背景 手背 手指近景",
        "jewelry_type": "戒指",
        "recommended_usage": "戒指真人佩戴展示",
        "notes": "手指完整，无裁切",
        "confidence": "高",
        "file_exists": True,
        "applicable_product_types": "ring",
        "applicable_display_modes": "worn",
        "framing": "手部近景",
        "visible_body_regions": "左手全部手指",
        "product_visibility": "高",
        "hand_visibility": "高",
        "collar_type": "无可见服装",
        "clothing_occlusion_risk": "无遮挡",
        "hair_occlusion_risk": "无遮挡",
        "pose_keywords": "身体未入镜；前臂自然抬起",
        "existing_jewelry": "戒指",
        "crop_risk": "低",
        "hand_side": "left",
        "visible_fingers": "thumb,index,middle,ring,little",
        "hand_orientation": "back",
        "ring_face_visibility": "高",
        "finger_separation": "高",
        "finger_occlusion_risk": "低",
    }
    data.update(overrides)
    data["notes"] = (
        f"正面视角；主体居中；{data['notes']}；无文字或平台界面"
    )
    return ReferenceRow(**data)


def test_ring_selects_three_eligible_references_and_ignores_original_rings():
    selected, candidates = select_top_references(
        ring_product(),
        [ring_row(401), ring_row(402), ring_row(403), ring_row(404)],
        OutputRole.HAND_WORN,
    )

    assert len(selected) == 3
    assert len(candidates) == 4
    assert all("参考图中的戒指" in item.ignored_reference_jewelry for item in selected)


def test_ring_hard_filter_removes_ineligible_reference():
    rejected = ring_row(405, visible_fingers="thumb,index,middle")
    valid = [ring_row(406), ring_row(407), ring_row(408)]

    selected, candidates = select_top_references(
        ring_product(), [rejected, *valid], OutputRole.HAND_WORN
    )
    rejected_score = score_reference(ring_product(), rejected)

    assert {item.row.index for item in selected} == {406, 407, 408}
    assert {item.row.index for item in candidates} == {406, 407, 408}
    assert any("目标手指" in risk for risk in rejected_score.risk)


def test_ring_requires_three_eligible_references():
    with pytest.raises(ValueError, match="戒指.*至少 3 张.*当前 2 张"):
        select_top_references(
            ring_product(),
            [ring_row(409), ring_row(410)],
            OutputRole.HAND_WORN,
        )


def test_戒指相反手参考不能进入替换候选():
    same_side = score_reference(ring_product(), ring_row(411, hand_side="left"))
    other_side = score_reference(ring_product(), ring_row(412, hand_side="right"))

    assert same_side.score > other_side.score
    assert any("左右手" in risk and "不匹配" in risk for risk in other_side.risk)


def necklace_product(display_mode="worn", length_category="collarbone", layer_count=1):
    return ProductAnalysis.from_dict({
        "product_type": "普通项链",
        "detected_product_type": "necklace",
        "confirmed_product_type": "necklace",
        "classification_confidence": "high",
        "classification_evidence": ["可见完整项链结构"],
        "classification_source": "model",
        "wear_position": "颈部和锁骨",
        "visible_appearance": "单层珠链",
        "color_family": ["白色"],
        "style_mood": "清透",
        "composition": "胸前近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
        "source_image_type": "worn_source",
        "display_mode": display_mode,
        "layer_count": layer_count,
        "length_category": length_category,
    })


def necklace_row(index, **overrides):
    data = {
        "index": index,
        "file_name": f"necklace-{index}.jpg",
        "relative_path": f"necklace-{index}.jpg",
        "absolute_path": Path(__file__).resolve(),
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "生活场景图",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "清透自然光",
        "scene_keywords": "深色背景 锁骨 胸前",
        "jewelry_type": "项链",
        "recommended_usage": "项链真人佩戴展示",
        "notes": "颈部和胸前完整，无裁切",
        "confidence": "高",
        "file_exists": True,
        "applicable_product_types": "necklace,pendant_necklace",
        "applicable_display_modes": "worn",
        "framing": "胸前半身",
        "visible_body_regions": "颈部 锁骨 胸前",
        "product_visibility": "高",
        "neck_visibility": "高",
        "collarbone_visibility": "高",
        "chest_visibility": "高",
        "hand_visibility": "低",
        "collar_type": "低领",
        "clothing_occlusion_risk": "低",
        "hair_occlusion_risk": "低",
        "pose_keywords": "上半身直立；手臂自然下垂",
        "existing_jewelry": "细项链",
        "crop_risk": "低",
        "hand_side": "双手未入镜",
        "hand_orientation": "手部未入镜",
    }
    data.update(overrides)
    data["notes"] = (
        f"正面视角；主体居中；{data['notes']}；无文字或平台界面"
    )
    return ReferenceRow(**data)


def _三品类候选索引(品类, candidate):
    if 品类 == "手串":
        _, candidates = select_top_references(
            product(),
            [candidate, row(990)],
            OutputRole.HAND_WORN,
        )
    elif 品类 == "项链":
        _, candidates = select_top_references(
            necklace_product(),
            [candidate, necklace_row(990)],
            OutputRole.LIFESTYLE,
        )
    else:
        _, candidates = select_top_references(
            ring_product(),
            [candidate, ring_row(990), ring_row(991), ring_row(992)],
            OutputRole.HAND_WORN,
        )
    return {item.row.index for item in candidates}


def _三品类参考行(品类, index, **overrides):
    if 品类 == "手串":
        return row(index, **overrides)
    if 品类 == "项链":
        return necklace_row(index, **overrides)
    return ring_row(index, **overrides)


@pytest.mark.parametrize(
    "field_name",
    ["product_visibility", "crop_risk"],
    ids=["展示面积", "裁切风险"],
)
@pytest.mark.parametrize("value", ["", "待确认"], ids=["缺失", "未知"])
@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类展示面积与裁切风险缺失或未知时关闭硬门(
    品类, field_name, value
):
    candidate = _三品类参考行(
        品类,
        801,
        **{field_name: value},
    )

    assert candidate.index not in _三品类候选索引(品类, candidate)


@pytest.mark.parametrize(
    "危险描述",
    ["画面含大面积文字", "文字界面风险为 blocking"],
    ids=["大面积文字", "阻断字面值"],
)
@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类大面积文字与阻断字面值均被硬门拒绝(品类, 危险描述):
    candidate = _三品类参考行(品类, 811, notes=危险描述)

    assert candidate.index not in _三品类候选索引(品类, candidate)


@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类文字界面否定描述安全而冲突描述关闭硬门(品类):
    safe = _三品类参考行(
        品类,
        821,
        notes="无大面积文字，不含 blocking 风险",
    )
    conflict = _三品类参考行(
        品类,
        831,
        notes="无大面积文字，但另一处有大面积文字",
    )

    assert safe.index in _三品类候选索引(品类, safe)
    assert conflict.index not in _三品类候选索引(品类, conflict)


@pytest.mark.parametrize(
    ("危险描述", "安全描述"),
    [
        ("原首饰无法清除", "不存在原首饰无法清除的问题"),
        ("原首饰无法完整识别", "原首饰并非无法完整识别"),
    ],
)
@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类只拒绝肯定的原首饰不可清除或不可识别(
    品类, 危险描述, 安全描述
):
    dangerous = _三品类参考行(
        品类,
        841,
        existing_jewelry=危险描述,
    )
    safe = _三品类参考行(
        品类,
        851,
        existing_jewelry=安全描述,
    )

    assert dangerous.index not in _三品类候选索引(品类, dangerous)
    assert safe.index in _三品类候选索引(品类, safe)


def test_戒指指位只读取与原戒指肯定关联的手指():
    safe = ring_row(861, existing_jewelry="无名指有原戒指，食指无戒指")
    dangerous = ring_row(862, existing_jewelry="食指有原戒指，无名指无戒指")
    multiple = ring_row(863, existing_jewelry="无名指和食指各有一枚原戒指")

    assert safe.index in _三品类候选索引("戒指", safe)
    assert dangerous.index not in _三品类候选索引("戒指", dangerous)
    assert multiple.index not in _三品类候选索引("戒指", multiple)


@pytest.mark.parametrize(
    ("field_name", "安全描述"),
    [
        ("notes", "不含blocking风险"),
        ("notes", "不含 BLOCKING 风险"),
        ("existing_jewelry", "不存在任何原首饰无法清除的问题"),
        ("existing_jewelry", "不存在 原首饰无法完整识别问题"),
    ],
    ids=["无空格", "大小写与空格", "插入修饰词", "分隔空格"],
)
@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类通用否定变体不会误拒(field_name, 安全描述, 品类):
    candidate = _三品类参考行(品类, 880, **{field_name: 安全描述})

    assert candidate.index in _三品类候选索引(品类, candidate)


@pytest.mark.parametrize(
    ("field_name", "危险描述"),
    [
        ("notes", "存在 blocking 风险"),
        ("existing_jewelry", "原首饰确实无法清除"),
    ],
    ids=["阻断风险", "原首饰无法清除"],
)
@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类插入修饰词的肯定危险仍被拒绝(field_name, 危险描述, 品类):
    candidate = _三品类参考行(品类, 881, **{field_name: 危险描述})

    assert candidate.index not in _三品类候选索引(品类, candidate)


@pytest.mark.parametrize(
    ("field_name", "冲突描述"),
    [
        ("notes", "不含blocking风险，但另一处存在 blocking 风险"),
        (
            "existing_jewelry",
            "不存在任何原首饰无法清除的问题，"
            "但另一枚原首饰确实无法清除",
        ),
    ],
    ids=["文字界面冲突", "原首饰冲突"],
)
@pytest.mark.parametrize("品类", ["手串", "项链", "戒指"])
def test_三品类安全否定与独立肯定冲突时关闭硬门(field_name, 冲突描述, 品类):
    candidate = _三品类参考行(品类, 882, **{field_name: 冲突描述})

    assert candidate.index not in _三品类候选索引(品类, candidate)


@pytest.mark.parametrize(
    "existing_jewelry",
    [
        "无名指有原戒指而食指无戒指",
        "无名指有原戒指、同时食指没有戒指",
        "无名指有原戒指同时食指没有戒指",
        "无名指有原戒指并且食指没有戒指",
        "无名指有原戒指且食指没有戒指",
        "无名指有原戒指和食指没有戒指",
        "无名指有原戒指与食指没有戒指",
    ],
    ids=["转折", "顿号同时", "同时", "并且", "且", "和", "与"],
)
def test_戒指逐手指关联忽略异指否定谓词(existing_jewelry):
    candidate = ring_row(883, existing_jewelry=existing_jewelry)

    assert candidate.index in _三品类候选索引("戒指", candidate)


def test_戒指目标食指时仍识别无名指的肯定原戒指():
    target_index_product = replace(ring_product(), finger_position=FingerPosition.INDEX)
    candidate = ring_row(885, existing_jewelry="无名指有原戒指而食指无戒指")

    _, candidates = select_top_references(
        target_index_product,
        [candidate, ring_row(990), ring_row(991), ring_row(992)],
        OutputRole.HAND_WORN,
    )

    assert candidate.index not in {item.row.index for item in candidates}


@pytest.mark.parametrize(
    "existing_jewelry",
    [
        "无名指和食指都有原戒指",
        "无名指与食指都有原戒指",
        "无名指及食指都有原戒指",
        "无名指和食指且中指都有原戒指",
        "食指有原戒指而无名指无戒指",
    ],
    ids=["和连接的多枚肯定", "与连接的多枚肯定", "及连接的多枚肯定", "三个肯定指位", "异指肯定目标指否定"],
)
def test_戒指逐手指关联拒绝异指肯定谓词(existing_jewelry):
    candidate = ring_row(884, existing_jewelry=existing_jewelry)

    assert candidate.index not in _三品类候选索引("戒指", candidate)


def _完整构图参考(tmp_path):
    path = tmp_path / "完整构图参考.jpg"
    path.write_bytes(b"reference-image")
    return replace(
        row(870, file_name=path.name),
        absolute_path=path,
        relative_path=path.name,
        framing="手部近景",
        visible_body_regions="左手、手腕、前臂",
        pose_keywords="身体未入镜，前臂斜向右上",
        hand_side="左手",
        hand_orientation="掌心朝上",
        collar_type="无可见服装",
        clothing_occlusion_risk="无遮挡",
        scene_keywords="深色布面，室内",
        style_category="左上侧柔光，高对比暗背景",
        notes="正面视角；主体位于画面中下部；无文字或平台界面",
        existing_jewelry="左手腕两条同类手链中的内侧那条",
        product_visibility="展示面积充足",
        crop_risk="无裁切",
    )


def test_行级构图签名与任务二快照构图签名完全相等(tmp_path):
    reference = _完整构图参考(tmp_path)
    scored = ScoredReference(reference, 100, 1, (), (), ())
    snapshot = build_candidate_snapshot(
        product(), scored, OutputRole.HAND_WORN
    )

    assert composition_signature_for_row(
        reference, OutputRole.HAND_WORN
    ) == snapshot.composition_signature


def test_构图签名区分背景光线与唯一替换目标且保持稳定(tmp_path):
    reference = _完整构图参考(tmp_path)
    baseline = composition_signature_for_row(reference, OutputRole.HAND_WORN)
    same = composition_signature_for_row(reference, OutputRole.HAND_WORN)
    background = composition_signature_for_row(
        replace(reference, scene_keywords="白墙，室内"),
        OutputRole.HAND_WORN,
    )
    lighting = composition_signature_for_row(
        replace(reference, style_category="右侧自然光，低对比"),
        OutputRole.HAND_WORN,
    )
    target = composition_signature_for_row(
        replace(
            reference,
            existing_jewelry="左手腕两条同类手链中的外侧那条",
        ),
        OutputRole.HAND_WORN,
    )
    other_role = composition_signature_for_row(reference, OutputRole.LIFESTYLE)

    assert baseline == same
    assert len({baseline, background, lighting, target, other_role}) == 5


def test_necklace_worn_prefers_neck_and_chest_reference():
    scored = score_reference(necklace_product(), necklace_row(101))
    assert any("项链" in reason and "匹配" in reason for reason in scored.reason)
    assert not any("饰品类型不是目标" in risk for risk in scored.risk)


def test_necklace_worn_filter_rejects_wrist_only_reference():
    good = necklace_row(102)
    wrist = necklace_row(
        103,
        applicable_product_types="bracelet",
        applicable_display_modes="worn",
        visible_body_regions="手腕 前臂",
        neck_visibility="低",
        collarbone_visibility="低",
        chest_visibility="低",
        jewelry_type="手链/手串",
    )
    selected, _ = select_top_references(
        necklace_product(), [wrist, good], OutputRole.LIFESTYLE
    )
    assert [item.row.index for item in selected] == [102]


@pytest.mark.parametrize(
    "overrides",
    [
        {"applicable_product_types": ""},
        {"applicable_display_modes": ""},
        {"visible_body_regions": ""},
        {"product_visibility": ""},
        {"collar_type": ""},
        {"clothing_occlusion_risk": ""},
        {"hair_occlusion_risk": ""},
        {"crop_risk": ""},
    ],
)
def test_necklace_worn_filter_rejects_missing_required_annotations(overrides):
    missing = necklace_row(108, **overrides)
    good = necklace_row(109)

    selected, candidates = select_top_references(
        necklace_product(), [missing, good], OutputRole.LIFESTYLE
    )

    assert [item.row.index for item in selected] == [109]
    assert [item.row.index for item in candidates] == [109]


@pytest.mark.parametrize(
    ("overrides", "expected_risk"),
    [
        ({"product_visibility": "低"}, "展示面积"),
        ({"clothing_occlusion_risk": "高", "collar_type": "高领"}, "衣领"),
        ({"hair_occlusion_risk": "高"}, "头发"),
        ({"crop_risk": "高"}, "裁切"),
    ],
)
def test_necklace_worn_filter_rejects_visibility_occlusion_and_crop_risks(
    overrides, expected_risk
):
    rejected = necklace_row(110, **overrides)
    good = necklace_row(111)

    selected, candidates = select_top_references(
        necklace_product(), [rejected, good], OutputRole.LIFESTYLE
    )
    rejected_score = score_reference(necklace_product(), rejected)

    assert [item.row.index for item in selected] == [111]
    assert [item.row.index for item in candidates] == [111]
    assert any(expected_risk in risk for risk in rejected_score.risk)


def test_long_necklace_filter_rejects_collarbone_crop():
    cropped = necklace_row(104, framing="锁骨特写", chest_visibility="低", crop_risk="高")
    full = necklace_row(105, framing="胸前半身", chest_visibility="高", crop_risk="低")
    selected, _ = select_top_references(
        necklace_product(length_category="long"),
        [cropped, full],
        OutputRole.LIFESTYLE,
    )
    assert [item.row.index for item in selected] == [105]


def test_multi_layer_necklace_requires_vertical_chest_space_and_rewards_it():
    tight = necklace_row(
        112,
        framing="锁骨特写",
        chest_visibility="低",
        notes="颈部完整，但没有多层垂直空间",
    )
    spacious = necklace_row(
        113,
        framing="胸前半身",
        chest_visibility="高",
        notes="颈部和胸前完整，有多层垂直空间和层间落差",
    )

    selected, candidates = select_top_references(
        necklace_product(length_category="upper_chest", layer_count=3),
        [tight, spacious],
        OutputRole.LIFESTYLE,
    )

    assert [item.row.index for item in selected] == [113]
    assert [item.row.index for item in candidates] == [113]
    assert any("多层" in reason and "垂直空间" in reason for reason in selected[0].reason)


def test_necklace_hand_held_requires_visible_hand_and_mode():
    worn = necklace_row(106, applicable_display_modes="worn", hand_visibility="低")
    held = necklace_row(
        107,
        applicable_display_modes="hand_held",
        visible_body_regions="手指 掌心",
        hand_visibility="高",
        recommended_usage="项链手持展示，链条可自然垂落",
        notes="手指与链条真实接触，完整链条无裁切",
    )
    selected, _ = select_top_references(
        necklace_product(display_mode="hand_held"),
        [worn, held],
        OutputRole.LIFESTYLE,
    )
    assert [item.row.index for item in selected] == [107]


@pytest.mark.parametrize(
    ("overrides", "expected_risk"),
    [
        (
            {"visible_body_regions": "手腕 前臂", "hand_visibility": "高"},
            "腕部",
        ),
        (
            {"visible_body_regions": "", "hand_visibility": "低"},
            "手指、掌心或双手",
        ),
        (
            {
                "recommended_usage": "项链手持展示",
                "notes": "手指与链条真实接触，但画面没有链条垂落空间",
            },
            "垂落空间",
        ),
        (
            {
                "recommended_usage": "项链悬空展示，链条可自然垂落",
                "notes": "手部靠近产品但没有真实接触",
            },
            "真实接触",
        ),
        (
            {
                "recommended_usage": "项链手持展示，链条可自然垂落",
                "notes": "手指与链条真实接触，但关键结构严重遮挡",
                "crop_risk": "高",
            },
            "关键结构",
        ),
    ],
)
def test_necklace_hand_held_filter_rejects_invalid_compositions(
    overrides, expected_risk
):
    rejected_data = {
        "applicable_display_modes": "hand_held",
        "visible_body_regions": "手指 掌心",
        "hand_visibility": "高",
        "recommended_usage": "项链手持展示，链条可自然垂落",
        "notes": "手指与链条真实接触，完整链条无裁切",
    }
    rejected_data.update(overrides)
    rejected = necklace_row(114, **rejected_data)
    good = necklace_row(
        115,
        applicable_display_modes="hand_held",
        visible_body_regions="手指 掌心",
        hand_visibility="高",
        recommended_usage="项链手持展示，链条可自然垂落",
        notes="手指与链条真实接触，完整链条无裁切",
    )

    product = necklace_product(display_mode="hand_held")
    selected, candidates = select_top_references(
        product, [rejected, good], OutputRole.LIFESTYLE
    )
    rejected_score = score_reference(product, rejected)

    assert [item.row.index for item in selected] == [115]
    assert [item.row.index for item in candidates] == [115]
    assert any(expected_risk in risk for risk in rejected_score.risk)


def test_项链选择不再使用构图惩罚并保持审计顺序稳定():
    duplicate_profile = {
        "framing": "胸前近景",
        "collar_type": "低领",
        "pose_keywords": "正面 头发左侧",
    }
    rows = [
        necklace_row(201, file_name="first.jpg", **duplicate_profile),
        necklace_row(202, file_name="duplicate.jpg", **duplicate_profile),
        necklace_row(
            203,
            file_name="diverse.jpg",
            framing="上半身",
            collar_type="V领",
            pose_keywords="右侧身 头发右侧",
        ),
        necklace_row(204, file_name="another-duplicate.jpg", **duplicate_profile),
    ]

    selected, candidates = select_top_references(
        necklace_product(), rows, OutputRole.LIFESTYLE, audit_seed="项链稳定选择"
    )
    repeated, _ = select_top_references(
        necklace_product(), reversed(rows), OutputRole.LIFESTYLE, audit_seed="项链稳定选择"
    )

    assert [item.row.file_name for item in selected] == [
        item.row.file_name for item in repeated
    ]
    assert all(item.score >= candidates[0].score - 10 for item in selected)


def test_手持选择不再使用持握惩罚并保持审计顺序稳定():
    common = {
        "applicable_display_modes": "hand_held",
        "visible_body_regions": "手指 掌心",
        "hand_visibility": "高",
        "notes": "手指与链条真实接触，完整链条无裁切",
    }
    rows = [
        necklace_row(
            211,
            file_name="pinch-first.jpg",
            recommended_usage="单手捏持项链，链条自然垂落",
            **common,
        ),
        necklace_row(
            212,
            file_name="pinch-duplicate.jpg",
            recommended_usage="单手捏持项链，链条自然垂落",
            **common,
        ),
        necklace_row(
            213,
            file_name="palm-diverse.jpg",
            recommended_usage="虎口握持项链，链条自然垂落",
            **common,
        ),
        necklace_row(
            214,
            file_name="pinch-another.jpg",
            recommended_usage="单手捏持项链，链条自然垂落",
            **common,
        ),
    ]

    selected, candidates = select_top_references(
        necklace_product(display_mode="hand_held"),
        rows,
        OutputRole.LIFESTYLE,
        audit_seed="手持稳定选择",
    )
    repeated, _ = select_top_references(
        necklace_product(display_mode="hand_held"),
        reversed(rows),
        OutputRole.LIFESTYLE,
        audit_seed="手持稳定选择",
    )

    assert [item.row.file_name for item in selected] == [
        item.row.file_name for item in repeated
    ]
    assert all(item.score >= candidates[0].score - 10 for item in selected)


@pytest.mark.parametrize(
    ("overrides", "expected_risk"),
    [
        ({"product_visibility": "不清晰"}, "展示面积"),
        (
            {"visible_body_regions": "不含颈部、锁骨或胸前，仅手腕"},
            "颈部、锁骨或胸前空间",
        ),
        (
            {"visible_body_regions": "颈部不可见，仅手腕"},
            "颈部、锁骨或胸前空间",
        ),
    ],
)
def test_necklace_worn_negative_visibility_and_regions_override_bare_keywords(
    overrides, expected_risk
):
    rejected = necklace_row(301, **overrides)

    selected, candidates = select_top_references(
        necklace_product(), [rejected], OutputRole.LIFESTYLE
    )
    scored = score_reference(necklace_product(), rejected)

    assert selected == []
    assert candidates == []
    assert any(expected_risk in risk for risk in scored.risk)


def test_necklace_hand_visibility_rejects_negated_clear_signal():
    rejected = necklace_row(
        302,
        applicable_display_modes="hand_held",
        visible_body_regions="手指 掌心",
        hand_visibility="不清晰",
        recommended_usage="项链手持展示，链条自然垂落",
        notes="手指与链条真实接触，完整链条无裁切",
    )
    product = necklace_product(display_mode="hand_held")

    selected, candidates = select_top_references(
        product, [rejected], OutputRole.LIFESTYLE
    )
    scored = score_reference(product, rejected)

    assert selected == []
    assert candidates == []
    assert any("手指、掌心或双手不可清晰辨识" in risk for risk in scored.risk)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("hair_occlusion_risk", "无严重遮挡"),
        ("hair_occlusion_risk", "无明显遮挡"),
        ("hair_occlusion_risk", "轻微遮挡"),
        ("crop_risk", "不高"),
        ("crop_risk", "无裁切"),
        ("crop_risk", "中"),
    ],
)
def test_necklace_risk_levels_honor_negation_before_risk_keywords(
    field_name, value
):
    reference = necklace_row(303, **{field_name: value})

    selected, candidates = select_top_references(
        necklace_product(), [reference], OutputRole.LIFESTYLE
    )

    assert [item.row.index for item in selected] == [303]
    assert [item.row.index for item in candidates] == [303]


@pytest.mark.parametrize(
    "notes",
    [
        "手指与链条真实接触，链条自然垂落，但手部明显畸变",
        "手指与链条真实接触，链条自然垂落，但手指严重遮挡吊坠",
        "手指与链条真实接触，链条自然垂落，但手指严重遮挡关键结构",
        "手指与链条真实接触，链条自然垂落，但画面空间不足",
        "手指与链条真实接触，链条自然垂落，但链条下半段超出画面",
        "手指与链条真实接触，链条自然垂落，但链条下半段被裁切",
        "手指与链条真实接触，链条自然垂落，但链条不完整",
    ],
)
def test_necklace_hand_held_severe_negative_signals_override_positive_drop(notes):
    rejected = necklace_row(
        304,
        applicable_display_modes="hand_held",
        visible_body_regions="手指 掌心",
        hand_visibility="高",
        recommended_usage="项链手持展示，链条可自然垂落",
        notes=notes,
        crop_risk="低",
    )
    product = necklace_product(display_mode="hand_held")

    selected, candidates = select_top_references(
        product, [rejected], OutputRole.LIFESTYLE
    )
    scored = score_reference(product, rejected)

    assert selected == []
    assert candidates == []
    assert any(
        keyword in risk
        for risk in scored.risk
        for keyword in ("畸变", "遮挡", "空间不足", "超出画面", "裁切", "不完整")
    )


@pytest.mark.parametrize("confidence", ["不高", "中低"])
def test_bracelet_confidence_rejects_negated_or_ambiguous_levels(confidence):
    selected, candidates = select_top_references(
        product(), [row(305, confidence=confidence)], OutputRole.HAND_WORN
    )

    assert selected == []
    assert candidates == []
