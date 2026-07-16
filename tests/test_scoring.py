from pathlib import Path

import pytest

from jewelry_on_hand.models import ProductAnalysis, ProductDimensions, ReferenceRow, ScoredReference
from jewelry_on_hand.output_roles import OutputRole
from jewelry_on_hand.scoring import (
    ReferenceSelectionInsufficientError,
    score_reference,
    select_batch_diverse_references,
    select_top_references,
    select_top_references_with_audit,
)


def row(index, exists=True, strategy="常规可优先使用", file_name=None, **overrides):
    data = {
        "purpose_category": "上手姿势/手模构图参考",
        "bracelet_applicability": "是：可用于手链/手串",
        "default_strategy": strategy,
        "style_category": "暗调闪光",
        "scene_keywords": "车内 闪光",
        "jewelry_type": "手链/手串",
        "recommended_usage": "近景手腕",
        "notes": "手腕/前臂露出面积足",
        "confidence": "高",
    }
    data.update(overrides)
    return ReferenceRow(
        index,
        file_name or f"{index}.jpg",
        f"ref/{index}.jpg",
        Path(f"C:/tmp/{index}.jpg"),
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


def test_select_top_references_filters_missing_and_scores_priority():
    selected, candidates = select_top_references(
        product(),
        [row(1), row(2, exists=False), row(3, strategy="无特殊要求不优先使用")],
    )
    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]
    assert any("暗调" in reason for reason in selected[0].reason)


def test_selection_without_prompt_does_not_filter_by_background_brightness():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, purpose_category="主图（静物不带人）", scene_keywords="深色背景 黑色绒布", recommended_usage="产品主图特写"),
            row(2, purpose_category="主图（静物不带人）", scene_keywords="自然光 浅色背景", recommended_usage="产品主图特写"),
            row(3, purpose_category="主图（静物不带人）", scene_keywords="户外 绿色背景", recommended_usage="产品主图特写"),
        ],
        output_role=OutputRole.HERO,
    )

    assert {item.row.index for item in selected} == {1, 2, 3}
    assert {item.row.index for item in candidates} == {1, 2, 3}


def test_selection_prompt_is_an_all_conditions_hard_gate():
    result = select_top_references_with_audit(
        product(),
        [
            row(1, purpose_category="手部佩戴图", scene_keywords="浅色背景 自然光", recommended_usage="右手 近景"),
            row(2, purpose_category="手部佩戴图", scene_keywords="浅色背景", recommended_usage="右手 近景"),
            row(3, purpose_category="手部佩戴图", scene_keywords="浅色背景 自然光", recommended_usage="左手 近景"),
            row(4, purpose_category="手部佩戴图", scene_keywords="浅色背景 自然光", recommended_usage="右手 近景"),
            row(5, purpose_category="手部佩戴图", scene_keywords="浅色背景 自然光", recommended_usage="右手 近景"),
        ],
        output_role=OutputRole.HAND_WORN,
        reference_selection_prompt="浅色背景；自然光；右手；近景",
    )

    assert [item.row.index for item in result.candidates] == [1, 4, 5]
    assert result.audit["candidate_counts"]["after_prompt_gates"] == 3


def test_selection_prompt_shortage_reports_each_condition_count():
    with pytest.raises(ReferenceSelectionInsufficientError) as exc_info:
        select_top_references_with_audit(
            product(),
            [
                row(1, purpose_category="手部佩戴图", scene_keywords="浅色背景 自然光", recommended_usage="右手 近景"),
                row(2, purpose_category="手部佩戴图", scene_keywords="浅色背景 自然光", recommended_usage="右手 近景"),
                row(3, purpose_category="手部佩戴图", scene_keywords="浅色背景", recommended_usage="左手"),
            ],
            output_role=OutputRole.HAND_WORN,
            reference_selection_prompt="浅色背景；自然光；右手；近景",
        )

    assert exc_info.value.audit["condition_match_counts"] == {
        "浅色背景": 3,
        "自然光": 2,
        "右手": 2,
        "近景": 2,
    }
    assert "浅色背景=3" in str(exc_info.value)
    assert "全部条件同时命中=2" in str(exc_info.value)


def test_hero_selection_rejects_dark_wearing_candidate_without_main_image_type():
    with pytest.raises(ValueError, match="主图"):
        select_top_references(
            product(),
            [row(1, scene_keywords="深色背景 黑色绒布", recommended_usage="近景手腕佩戴")],
            output_role=OutputRole.HERO,
        )


def test_hand_worn_selection_requires_hand_worn_image_type():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, purpose_category="手部佩戴图（手腕局部）", scene_keywords="黑色背景"),
            row(2, purpose_category="生活场景图（带穿搭）", scene_keywords="黑色背景"),
            row(3, purpose_category="主图（静物不带人）", scene_keywords="黑色背景"),
        ],
        output_role=OutputRole.HAND_WORN,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_lifestyle_selection_requires_lifestyle_image_type():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, purpose_category="手部佩戴图（手腕局部）", scene_keywords="黑色背景"),
            row(2, purpose_category="生活场景图（带穿搭）", scene_keywords="黑色背景"),
            row(3, purpose_category="主图（静物不带人）", scene_keywords="黑色背景"),
        ],
        output_role=OutputRole.LIFESTYLE,
    )

    assert [item.row.index for item in selected] == [2]
    assert [item.row.index for item in candidates] == [2]


@pytest.mark.parametrize("scene_keywords", ["低调暗色背景，产品完整清晰", "暗黑背景，产品完整清晰"])
def test_lifestyle_selection_accepts_explicit_dark_scene_supplement(scene_keywords):
    selected, candidates = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="生活场景图（带穿搭）",
                scene_keywords=scene_keywords,
                strategy="可作为场景或细节补充",
            )
        ],
        output_role=OutputRole.LIFESTYLE,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_lifestyle_selection_accepts_applicable_non_wrist_scene_as_last_fallback():
    selected, candidates = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="生活场景图（带穿搭）",
                scene_keywords="低调暗色背景，手腕手串完整可见",
                strategy="非手腕构图，默认不优先",
            )
        ],
        output_role=OutputRole.LIFESTYLE,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_lifestyle_selection_accepts_approved_dark_lifestyle_reference_without_text_signal():
    selected, candidates = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="生活场景图（带穿搭）",
                scene_keywords="背景干净，产品完整清晰",
                strategy="非手腕构图，默认不优先",
                notes="素材编号：RP000298",
            )
        ],
        output_role=OutputRole.LIFESTYLE,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_lifestyle_type_gate_applies_before_category_priority_selection():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, purpose_category="手部佩戴图（手腕局部）", scene_keywords="黑色背景"),
            row(
                2,
                purpose_category="生活场景图（带穿搭）",
                scene_keywords="黑色背景",
                strategy="无特殊要求不优先使用",
            ),
        ],
        output_role=OutputRole.LIFESTYLE,
    )

    assert [item.row.index for item in selected] == [2]
    assert [item.row.index for item in candidates] == [2]


def test_hero_selection_uses_dark_main_image_even_when_not_bracelet_worn_reference():
    selected, candidates = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="主图（静物不带人）",
                scene_keywords="深色背景 产品完整",
                bracelet_applicability="否",
                jewelry_type="项链 吊坠 通用",
            )
        ],
        output_role=OutputRole.HERO,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_hero_selection_accepts_black_support_surface_as_dark_background():
    selected, _ = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="主图（静物不带人）",
                scene_keywords="黑色石材 产品完整展示",
            )
        ],
        output_role=OutputRole.HERO,
    )

    assert [item.row.index for item in selected] == [1]


def test_hero_selection_accepts_user_approved_dark_main_image_without_text_signal():
    selected, _ = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="主图（静物不带人）",
                scene_keywords="背景干净 产品完整展示",
                notes="素材编号：RP000137",
            )
        ],
        output_role=OutputRole.HERO,
    )

    assert [item.row.index for item in selected] == [1]


def test_hero_selection_accepts_each_user_approved_dark_main_image():
    selected, _ = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="主图（静物不带人）",
                scene_keywords="背景干净 产品完整展示",
                notes="素材编号：RP000144",
            )
        ],
        output_role=OutputRole.HERO,
    )

    assert [item.row.index for item in selected] == [1]


def test_hero_selection_accepts_clean_background_without_style_prompt():
    selected, candidates = select_top_references(
        product(),
        [
            row(
                1,
                purpose_category="主图（静物不带人）",
                scene_keywords="背景干净 产品完整展示",
            )
        ],
        output_role=OutputRole.HERO,
    )

    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]


def test_select_top_references_keeps_hard_filtered_candidates_and_top_three_ranks():
    rows = [
        row(1),
        row(2, style_category="清晰自然", scene_keywords="自然光 留白", notes="手腕露出面积足"),
        row(3, recommended_usage="佩戴展示 近景手腕"),
        row(4, style_category="清晰自然", scene_keywords="自然光 留白", notes="手腕露出面积足"),
    ]
    selected, candidates = select_top_references(product(), rows)
    assert len(selected) == 3
    assert len(candidates) == 4
    assert [item.rank for item in selected] == [1, 2, 3]
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

    selected, candidates = select_top_references(product(), [clean, combined])

    assert {item.row.file_name for item in candidates} == {"clean.jpg", "combined.jpg"}
    assert selected[0].row.file_name == "clean.jpg"
    combined_candidate = next(
        item for item in candidates if item.row.file_name == "combined.jpg"
    )
    assert combined_candidate.ignored_reference_jewelry


def test_select_top_references_diversifies_same_score_shoot_group():
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

    selected, _ = select_top_references(product(), rows)

    assert selected[0].row.index == 30
    assert {item.row.index for item in selected[1:]} == {101, 102}


def test_select_batch_diverse_references_penalizes_reused_files_across_products():
    rows = [
        row(30, file_name="1（30）.png", style_category="暗调高级/黑衣近景"),
        row(31, file_name="1（31）.png", style_category="暗调高级/黑衣近景"),
        row(32, file_name="1（32）.png", style_category="暗调高级/黑衣近景"),
        row(101, file_name="outdoor-101.jpg", style_category="户外自然光"),
        row(102, file_name="mirror-102.jpg", style_category="对镜生活感"),
    ]
    _, first_candidates = select_top_references(product(), rows)
    _, second_candidates = select_top_references(product(), rows)

    first_selected, second_selected = select_batch_diverse_references(
        [first_candidates, second_candidates]
    )

    assert [item.row.file_name for item in first_selected] != [
        item.row.file_name for item in second_selected
    ]
    assert first_selected[0].row.file_name != second_selected[0].row.file_name


def test_select_batch_diverse_references_honors_initial_file_usage():
    rows = [
        row(1, file_name="already-used.jpg", style_category="dark"),
        row(2, file_name="unused.jpg", style_category="light"),
    ]
    _, candidates = select_top_references(product(), rows)

    [selected] = select_batch_diverse_references(
        [candidates],
        limit=1,
        initial_usage={
            "file": {"already-used.jpg": 1},
            "shoot_group": {},
            "style_cluster": {},
        },
    )

    assert [item.row.file_name for item in selected] == ["unused.jpg"]


def test_batch_selection_uses_lower_reuse_risky_candidate_after_safe_candidate_is_overused():
    safe = ScoredReference(row(1, file_name="safe.jpg"), 150, 1, (), (), ())
    risky = ScoredReference(
        row(2, file_name="risky.jpg"),
        120,
        2,
        (),
        ("参考首饰需要移除",),
        (),
    )

    [selected] = select_batch_diverse_references(
        [[safe, risky]],
        limit=1,
        initial_usage={
            "file": {"safe.jpg": 5, "risky.jpg": 1},
            "shoot_group": {},
            "style_cluster": {},
        },
    )

    assert [item.row.file_name for item in selected] == ["risky.jpg"]


def test_select_batch_diverse_references_uses_lower_score_when_quality_window_is_used():
    candidates = [
        ScoredReference(row(1, file_name="already-used.jpg"), 150, 1, (), (), ()),
        ScoredReference(row(2, file_name="lower-unused.jpg"), 80, 2, (), (), ()),
    ]

    [selected] = select_batch_diverse_references(
        [candidates],
        limit=1,
        initial_usage={
            "file": {"already-used.jpg": 1},
            "shoot_group": {},
            "style_cluster": {},
        },
    )

    assert [item.row.file_name for item in selected] == ["lower-unused.jpg"]


def test_select_top_references_relaxes_to_medium_confidence_when_no_high_candidate():
    selected, candidates = select_top_references(
        product(),
        [
            row(1, confidence="中"),
            row(2, exists=False, confidence="高"),
            row(3, confidence="低"),
        ],
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

    _, candidates = select_top_references(product(), rows)

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
        "absolute_path": Path(f"C:/tmp/ring-{index}.jpg"),
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "戒指上手/手部近景参考",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "清透自然光",
        "scene_keywords": "手背 手指近景",
        "jewelry_type": "戒指",
        "recommended_usage": "戒指真人佩戴展示",
        "notes": "手指完整，无裁切",
        "confidence": "高",
        "file_exists": True,
        "applicable_product_types": "ring",
        "applicable_display_modes": "worn",
        "visible_body_regions": "左手全部手指",
        "product_visibility": "高",
        "hand_visibility": "高",
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
    return ReferenceRow(**data)


def test_ring_selects_three_eligible_references_and_ignores_original_rings():
    selected, candidates = select_top_references(
        ring_product(),
        [ring_row(401), ring_row(402), ring_row(403), ring_row(404)],
    )

    assert len(selected) == 3
    assert len(candidates) == 4
    assert all("参考图中的戒指" in item.ignored_reference_jewelry for item in selected)


def test_ring_hard_filter_removes_ineligible_reference():
    rejected = ring_row(405, visible_fingers="thumb,index,middle")
    valid = [ring_row(406), ring_row(407), ring_row(408)]

    selected, candidates = select_top_references(ring_product(), [rejected, *valid])
    rejected_score = score_reference(ring_product(), rejected)

    assert {item.row.index for item in selected} == {406, 407, 408}
    assert {item.row.index for item in candidates} == {406, 407, 408}
    assert any("目标手指" in risk for risk in rejected_score.risk)


def test_ring_requires_three_eligible_references():
    with pytest.raises(ValueError, match="戒指.*至少 3 张.*当前 2 张"):
        select_top_references(ring_product(), [ring_row(409), ring_row(410)])


def test_ring_same_hand_side_scores_higher_without_replacing_confirmed_side():
    same_side = score_reference(ring_product(), ring_row(411, hand_side="left"))
    other_side = score_reference(ring_product(), ring_row(412, hand_side="right"))

    assert same_side.score > other_side.score
    assert not any("不匹配" in risk for risk in other_side.risk)


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
        "absolute_path": Path(f"C:/tmp/necklace-{index}.jpg"),
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "真人佩戴构图参考",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "清透自然光",
        "scene_keywords": "锁骨 胸前",
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
        "existing_jewelry": "细项链",
        "crop_risk": "低",
    }
    data.update(overrides)
    return ReferenceRow(**data)


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
    selected, _ = select_top_references(necklace_product(), [wrist, good])
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

    selected, candidates = select_top_references(necklace_product(), [missing, good])

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

    selected, candidates = select_top_references(necklace_product(), [rejected, good])
    rejected_score = score_reference(necklace_product(), rejected)

    assert [item.row.index for item in selected] == [111]
    assert [item.row.index for item in candidates] == [111]
    assert any(expected_risk in risk for risk in rejected_score.risk)


def test_long_necklace_filter_rejects_collarbone_crop():
    cropped = necklace_row(104, framing="锁骨特写", chest_visibility="低", crop_risk="高")
    full = necklace_row(105, framing="胸前半身", chest_visibility="高", crop_risk="低")
    selected, _ = select_top_references(necklace_product(length_category="long"), [cropped, full])
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
    selected, _ = select_top_references(necklace_product(display_mode="hand_held"), [worn, held])
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
    selected, candidates = select_top_references(product, [rejected, good])
    rejected_score = score_reference(product, rejected)

    assert [item.row.index for item in selected] == [115]
    assert [item.row.index for item in candidates] == [115]
    assert any(expected_risk in risk for risk in rejected_score.risk)


def test_necklace_diversity_penalizes_repeated_framing_collar_hair_and_orientation():
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

    selected, _ = select_top_references(necklace_product(), rows)

    assert [item.row.index for item in selected[:2]] == [201, 203]


def test_hand_held_diversity_penalizes_repeated_holding_method():
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

    selected, _ = select_top_references(necklace_product(display_mode="hand_held"), rows)

    assert [item.row.index for item in selected[:2]] == [211, 213]


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

    selected, candidates = select_top_references(necklace_product(), [rejected])
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

    selected, candidates = select_top_references(product, [rejected])
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

    selected, candidates = select_top_references(necklace_product(), [reference])

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

    selected, candidates = select_top_references(product, [rejected])
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
        product(), [row(305, confidence=confidence)]
    )

    assert selected == []
    assert candidates == []
