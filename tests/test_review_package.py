import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from jewelry_on_hand.models import ReferenceRow, ScoredReference
from jewelry_on_hand.review_package import write_review_package
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


def constraints_data(review_status="pending"):
    return {
        "schema_version": 1,
        "source": {
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
        },
        "detected_keywords": ["随形"],
        "must_keep": [
            {
                "name": "白水晶随形",
                "source_text": "白水晶随形",
                "normalized_keyword": "随形",
                "location": "主珠右侧",
                "visual_shape": "透明不规则随形，非圆珠",
                "relationship": "位于两颗圆珠之间",
                "forbid": ["改成圆珠"],
                "qc_question": "白水晶随形是否仍是不规则透明异形珠",
            }
        ],
        "must_not_change": ["珠子排列顺序"],
        "needs_user_review": True,
        "detail_crop_recommended": True,
        "review_status": review_status,
    }


def make_scored(
    tmp_path: Path,
    index: int = 1,
    *,
    file_name: str = "ref.jpg",
    relative_path: str | None = None,
    purpose_category: str = "上手姿势/手模构图参考",
    style_category: str = "暗调闪光",
    scene_keywords: str = "车内",
    reason: list[str] | None = None,
    risk: list[str] | None = None,
    ignored_reference_jewelry: list[str] | None = None,
    reference_fields: dict[str, str] | None = None,
) -> ScoredReference:
    ref = tmp_path / file_name
    ref.write_bytes(b"ref")
    row = ReferenceRow(
        index,
        file_name,
        relative_path or file_name,
        ref,
        100,
        200,
        0.1,
        purpose_category,
        "是",
        "常规可优先使用",
        style_category,
        scene_keywords,
        "手链/手串",
        "近景",
        "手腕露出",
        "高",
        True,
        **(reference_fields or {}),
    )
    return ScoredReference(
        row,
        100 - index,
        index,
        reason or ["理由"],
        risk or ["风险"],
        ignored_reference_jewelry or ["参考图中的原有手链"],
    )


def test_write_review_package_outputs_json_and_html(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    row = ReferenceRow(
        1,
        "ref.jpg",
        "ref.jpg",
        ref,
        100,
        200,
        0.1,
        "上手姿势/手模构图参考",
        "是",
        "常规可优先使用",
        "暗调闪光",
        "车内",
        "手链/手串",
        "近景",
        "手腕露出",
        "高",
        True,
    )
    scored = [ScoredReference(row, 100, 1, ["理由"], ["风险"], ["参考图中的原有手链"])]

    html = write_review_package(paths, product, scored, scored)

    assert "Top 3 参考图" in html.read_text(encoding="utf-8")
    assert read_json(paths.analysis_dir / "selected_references.json")[0]["rank"] == 1


def test_write_review_package_displays_product_fidelity_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    from jewelry_on_hand.run_paths import write_json

    write_json(paths.analysis_dir / "product_fidelity_constraints.json", constraints_data(review_status="pending"))
    selected = [make_scored(tmp_path, 1)]

    html = write_review_package(paths, product, selected, selected).read_text(encoding="utf-8")

    assert "产品保真约束" in html
    assert "关键识别点" in html
    assert "白水晶随形" in html
    assert "改成圆珠" in html
    assert "待确认" in html


def test_write_review_package_copies_selected_references_and_writes_candidates(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    selected = [
        make_scored(tmp_path, 1, file_name="ref-one.jpg"),
        make_scored(tmp_path, 2, file_name="ref-two.jpg"),
    ]
    candidates = [*selected, make_scored(tmp_path, 3, file_name="ref-three.jpg")]

    write_review_package(paths, product, selected, candidates)

    assert (paths.review_dir / "rank-1-ref-one.jpg").read_bytes() == b"ref"
    assert (paths.review_dir / "rank-2-ref-two.jpg").read_bytes() == b"ref"
    selected_json = read_json(paths.analysis_dir / "selected_references.json")
    assert [item["rank"] for item in selected_json] == [1, 2]
    assert Path(selected_json[0]["selected_reference"]) == paths.review_dir / "rank-1-ref-one.jpg"
    assert Path(selected_json[1]["selected_reference"]) == paths.review_dir / "rank-2-ref-two.jpg"
    assert Path(selected_json[0]["selected_reference"]).read_bytes() == b"ref"
    assert selected_json[0]["metadata"]["source_reference"] == str(selected[0].row.absolute_path)
    assert selected_json[0]["metadata"]["source_absolute_path"] == str(selected[0].row.absolute_path)
    assert selected_json[0]["metadata"]["relative_path"] == selected[0].row.relative_path
    assert selected_json[0]["metadata"]["相对路径"] == selected[0].row.relative_path
    assert read_json(paths.analysis_dir / "reference_candidates.json") == [
        item.to_dict() for item in candidates
    ]


def test_write_review_package_escapes_html_fields(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    selected = [
        make_scored(
            tmp_path,
            file_name="evil-&-ref.jpg",
            purpose_category="<script>用途</script>",
            style_category='暗调"闪光"',
            scene_keywords="车内 & 户外",
            reason=["理由 <b>重要</b>"],
            risk=["风险 & 遮挡"],
            ignored_reference_jewelry=['参考图中的 "旧手链"'],
        )
    ]

    html = write_review_package(paths, product, selected, selected).read_text(encoding="utf-8")

    assert "<script>用途</script>" not in html
    assert "evil-&-ref.jpg" not in html
    assert "&lt;script&gt;用途&lt;/script&gt;" in html
    assert "evil-&amp;-ref.jpg" in html
    assert "车内 &amp; 户外" in html
    assert "&quot;旧手链&quot;" in html


def test_review_page_displays_and_escapes_product_confirmation_and_reference_risks(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    write_json(
        paths.analysis_dir / "product_analysis.json",
        {
            "product_type": "带链吊坠",
            "detected_product_type": "necklace",
            "confirmed_product_type": "pendant_necklace",
            "classification_confidence": "medium",
            "classification_evidence": ["中央结构 <可能> 是主吊坠"],
            "classification_source": "manual_override",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "wear_position": "颈部和锁骨",
            "visible_appearance": "双层珠链，第二层中央有吊坠",
            "color_family": ["白色"],
            "style_mood": "精致",
            "composition": "胸前近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "layer_count": 2,
            "length_category": "collarbone",
            "chain_or_strand_type": "beaded",
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 2,
            "pendant_position": "front_<center>",
            "pendant_orientation": "front_facing",
            "connection_structure": "metal_&bail",
            "symmetry": "approximately_symmetric",
            "occluded_parts": ["后颈 <扣头>"],
            "uncertain_details": ["扣头 & 连接方式"],
            "is_independent_multi_item": False,
        },
    )
    selected = [
        make_scored(
            tmp_path,
            reference_fields={
                "applicable_product_types": "项链 & 带链吊坠",
                "applicable_display_modes": "worn <优先>",
                "framing": "胸部以上",
                "visible_body_regions": "锁骨 / 胸前落点",
                "product_visibility": "大于 35%",
                "collar_type": "V 领",
                "clothing_occlusion_risk": "衣领 <低风险>",
                "hair_occlusion_risk": "长发 & 中风险",
                "existing_jewelry": "原有项链",
                "crop_risk": "吊坠可能被裁切",
            },
        )
    ]

    html = write_review_package(paths, product, selected, selected).read_text(encoding="utf-8")

    for expected in (
        "产品确认",
        "自动识别品类",
        "最终确认品类",
        "分类置信度",
        "分类证据",
        "分类来源",
        "输入图类型",
        "展示模式",
        "层数",
        "长度等级",
        "吊坠存在",
        "吊坠数量",
        "吊坠所属层",
        "吊坠位置",
        "吊坠朝向",
        "吊坠连接",
        "遮挡区域",
        "不确定细节",
        "支持状态",
        "适用品类",
        "适用展示模式",
        "人物取景",
        "目标落点/身体区域",
        "预计展示面积",
        "衣领类型",
        "衣物遮挡风险",
        "头发遮挡风险",
        "裁切风险",
        "原有首饰",
        "入选理由",
        "风险说明",
    ):
        assert expected in html
    assert "中央结构 <可能> 是主吊坠" not in html
    assert "中央结构 &lt;可能&gt; 是主吊坠" in html
    assert "front_&lt;center&gt;" in html
    assert "metal_&amp;bail" in html
    assert "项链 &amp; 带链吊坠" in html
    assert "worn &lt;优先&gt;" in html
    assert "长发 &amp; 中风险" in html


def test_review_page_shows_explicit_unsupported_reason(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    write_json(
        paths.analysis_dir / "product_analysis.json",
        {
            "product_type": "无链独立吊坠",
            "detected_product_type": "pendant_only",
            "confirmed_product_type": "pendant_only",
            "classification_confidence": "high",
            "classification_evidence": ["未见链条"],
            "classification_source": "auto_confirmed",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "wear_position": "胸前",
            "visible_appearance": "单个吊坠",
            "color_family": ["金色"],
            "style_mood": "简洁",
            "composition": "胸前近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "layer_count": 1,
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": None,
            "is_independent_multi_item": False,
        },
    )
    selected = [make_scored(tmp_path)]

    html = write_review_package(paths, product, selected, selected).read_text(encoding="utf-8")

    assert "当前版本不支持无链独立吊坠，且禁止自动补链" in html


def test_write_review_package_url_encodes_image_src(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    selected = [make_scored(tmp_path, 1, file_name="ref#1 %.jpg")]

    html = write_review_package(paths, product, selected, selected).read_text(encoding="utf-8")

    match = re.search(r'<img class="reference-image" src="([^"]+)"', html)
    assert match is not None
    assert "#" not in match.group(1)
    assert "%23" in match.group(1)
    assert "%20" in match.group(1)
    assert "%25" in match.group(1)
    assert (paths.review_dir / unquote(match.group(1))).is_file()


def test_write_review_package_rejects_external_product_image(tmp_path):
    paths = RunPaths.create(tmp_path / "runs", "run-1")
    external_product = tmp_path / "external-product.jpg"
    external_product.write_bytes(b"product")
    selected = [make_scored(tmp_path, 1)]

    with pytest.raises(ValueError, match="\u4ea7\u54c1\u56fe.*run"):
        write_review_package(paths, external_product, selected, selected)


def test_write_review_package_rejects_duplicate_selected_rank(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    selected = [
        make_scored(tmp_path, 1, file_name="one.jpg"),
        make_scored(tmp_path, 1, file_name="two.jpg"),
    ]

    with pytest.raises(ValueError, match="\u91cd\u590d rank"):
        write_review_package(paths, product, selected, selected)
