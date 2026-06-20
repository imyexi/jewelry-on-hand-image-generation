from pathlib import Path

from jewelry_on_hand.models import ProductAnalysis, ProductDimensions, ReferenceRow, ScoredReference
from jewelry_on_hand.scoring import (
    score_reference,
    select_batch_diverse_references,
    select_top_references,
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
