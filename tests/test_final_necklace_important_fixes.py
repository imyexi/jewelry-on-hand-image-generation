from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

from jewelry_on_hand.cli import main
from jewelry_on_hand.models import (
    PendantSemantics,
    ProductAnalysis,
    ProductConfirmationSnapshot,
    ProductFidelityConstraints,
    ReferenceRow,
)
from jewelry_on_hand.product_analysis import load_product_analysis
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    validate_product_fidelity_constraints,
)
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.run_paths import RunPaths, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAIN_DOUBLE_LOOP_ANALYSIS = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "final_necklace"
    / "plain_double_loop_necklace_analysis.json"
)
ARTIFACT_INSPECTOR = (
    PROJECT_ROOT
    / "skills"
    / "jewelry-on-hand-workflow"
    / "scripts"
    / "inspect_run_artifacts.py"
)
PENDANT_TERMS = ("吊坠", "主吊坠", "链坠", "流苏", "坠子")


def _plain_double_loop_analysis_data() -> dict[str, object]:
    return json.loads(PLAIN_DOUBLE_LOOP_ANALYSIS.read_text(encoding="utf-8"))


def test_plain_double_loop_fixture_is_valid_modern_necklace() -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())

    assert product.confirmed_product_type is ProductType.NECKLACE
    assert product.layer_count == 2
    assert product.has_pendant is False
    assert product.pendant_count == 0


def _constraints_for_text(text: str) -> ProductFidelityConstraints:
    data = _plain_double_loop_analysis_data()
    data["visible_appearance"] = text
    data["special_requirements"] = []
    return build_product_fidelity_constraints(ProductAnalysis.from_dict(data))


def test_plain_double_loop_negative_pendant_descriptions_do_not_create_positive_canonical() -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())

    constraints = build_product_fidelity_constraints(product)

    assert constraints.schema_version == 2
    assert constraints.pendant_semantics == PendantSemantics(
        "absent", 0, None, "forbid"
    )
    canonical_text = json.dumps(constraints.to_dict(), ensure_ascii=False)
    assert all(term not in canonical_text for term in PENDANT_TERMS)
    validate_product_fidelity_constraints(product, constraints)


def test_plain_double_loop_attachment_remains_one_necklace() -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())

    constraints = build_product_fidelity_constraints(product)
    canonical_text = json.dumps(constraints.to_dict(), ensure_ascii=False)

    assert product.layer_count == 2
    assert product.is_independent_multi_item is False
    assert constraints.pendant_semantics == PendantSemantics(
        "absent", 0, None, "forbid"
    )
    assert all(text not in canonical_text for text in ("三圈", "第三圈", "第 3 层"))
    assert all(term not in canonical_text for term in PENDANT_TERMS)


@pytest.mark.parametrize(
    "description",
    [
        "线路中的圆珠不是悬挂吊坠",
        "完整链条没有吊坠",
        "完整链条无流苏",
        "中央圆珠并非链坠",
        "正面未见吊坠",
        "链条不含流苏",
        "链条不带链坠",
        "产品不存在吊坠",
    ],
)
def test_negative_pendant_aliases_are_not_extracted(description: str) -> None:
    constraints = _constraints_for_text(description)

    assert constraints.pendant_semantics == PendantSemantics(
        "absent", 0, None, "forbid"
    )
    canonical_text = json.dumps(constraints.to_dict(), ensure_ascii=False)
    assert all(term not in canonical_text for term in PENDANT_TERMS)


@pytest.mark.parametrize(
    ("description", "source_alias"),
    [
        ("正面中心有水滴形吊坠", "吊坠"),
        ("没有吊坠，但正面中心有一束流苏", "流苏"),
        ("并非流苏，而是链条中央连接一枚链坠", "链坠"),
    ],
)
def test_positive_and_mixed_pendant_clauses_keep_positive_alias(
    description: str,
    source_alias: str,
) -> None:
    data = _plain_double_loop_analysis_data()
    data.update(
        {
            "product_type": "带链吊坠",
            "detected_product_type": "pendant_necklace",
            "confirmed_product_type": "pendant_necklace",
            "visible_appearance": description,
            "special_requirements": [],
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 2,
            "pendant_position": "front_center",
            "pendant_orientation": "front_facing",
        }
    )

    constraints = build_product_fidelity_constraints(ProductAnalysis.from_dict(data))

    assert constraints.pendant_semantics == PendantSemantics(
        "present", 1, 2, "forbid"
    )
    pendant_items = [
        item for item in constraints.must_keep if item.normalized_keyword == "吊坠"
    ]
    assert len(pendant_items) == 1
    assert source_alias in pendant_items[0].source_text
    assert "第 2 层" in pendant_items[0].relationship


@pytest.mark.parametrize("tamper_kind", ["normalized_keyword", "positive_semantics"])
def test_necklace_without_pendant_rejects_positive_pendant_canonical(
    tamper_kind: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    if tamper_kind == "normalized_keyword":
        payload["detected_keywords"] = ["吊坠"]
        payload["must_keep"] = [
            {
                "name": "吊坠",
                "source_text": "正面中心有吊坠",
                "normalized_keyword": "吊坠",
                "location": "正面中心",
                "visual_shape": "垂坠结构",
                "relationship": "保持吊坠连接",
                "forbid": ["不得删除吊坠"],
                "qc_question": "吊坠是否保持",
            }
        ]
        payload["needs_user_review"] = True
        payload["detail_crop_recommended"] = True
        payload["review_status"] = "pending"
    else:
        payload["must_not_change"].append("必须保留主吊坠及其连接关系")

    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    ("field_name", "semantic_text"),
    [
        ("name", "保有吊坠"),
        ("source_text", "不可改变吊坠连接"),
        ("normalized_keyword", "链坠"),
        ("location", "不可删除吊坠所在位置"),
        ("visual_shape", "维持主吊坠形状"),
        ("relationship", "继续保有吊坠连接"),
        ("forbid", "不得对主吊坠进行任何改变"),
        ("qc_question", "是否保全吊坠"),
        ("must_not_change", "不得让主吊坠发生改变"),
        ("detected_keywords", "流苏"),
    ],
)
def test_plain_double_loop_necklace_rejects_positive_pendant_semantics_in_every_canonical_field(
    field_name: str,
    semantic_text: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    if field_name == "detected_keywords":
        payload["detected_keywords"] = [semantic_text]
    elif field_name == "must_not_change":
        payload["must_not_change"].append(semantic_text)
    else:
        item = {
            "name": "链条结构",
            "source_text": "同一条连续微珠链",
            "normalized_keyword": "链条结构",
            "location": "颈部至胸前",
            "visual_shape": "保持链条可见形态",
            "relationship": "保持链条原有连接关系",
            "forbid": ["不得改变链条结构"],
            "qc_question": "链条结构是否保持",
        }
        if field_name == "forbid":
            item["forbid"] = ["不得改变链条结构", semantic_text]
        else:
            item[field_name] = semantic_text
        payload["must_keep"] = [item]
        payload["needs_user_review"] = True
        payload["detail_crop_recommended"] = True
        payload["review_status"] = "pending"
    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    "semantic_text",
    [
        "不得对主吊坠进行任何改变",
        "不得让主吊坠发生改变",
        "主吊坠不得发生任何改变",
        "不允许对现有吊坠做删除或替换",
    ],
)
def test_necklace_without_pendant_rejects_order_independent_preservation_semantics(
    semantic_text: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    payload["must_not_change"].append(semantic_text)
    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    "semantic_text",
    [
        "不得新增吊坠且必须保留既有吊坠",
        "禁止补造吊坠且维持原有吊坠",
        "无需新增吊坠以及保有现有吊坠",
    ],
)
def test_necklace_without_pendant_compound_text_keeps_structured_absent(
    semantic_text: str,
) -> None:
    constraints = _constraints_for_text(semantic_text)

    assert constraints.pendant_semantics == PendantSemantics(
        "absent", 0, None, "forbid"
    )
    canonical_text = json.dumps(constraints.to_dict(), ensure_ascii=False)
    assert all(term not in canonical_text for term in PENDANT_TERMS)


@pytest.mark.parametrize(
    "connector",
    ["且", "以及", "并", "并且", "同时", "而且", "但", "但是", "不过", "然而", "又"],
)
def test_necklace_without_pendant_connector_text_keeps_structured_absent(
    connector: str,
) -> None:
    constraints = _constraints_for_text(
        f"不得新增吊坠{connector}必须保留既有吊坠"
    )

    assert constraints.pendant_semantics == PendantSemantics(
        "absent", 0, None, "forbid"
    )
    canonical_text = json.dumps(constraints.to_dict(), ensure_ascii=False)
    assert all(term not in canonical_text for term in PENDANT_TERMS)


@pytest.mark.parametrize(
    "absence",
    ["没有吊坠", "不是吊坠", "无吊坠", "中央圆珠并非吊坠"],
)
def test_necklace_without_pendant_rejects_explicit_absence_text_in_canonical(
    absence: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    payload["must_not_change"].append(absence)
    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    "prohibition",
    [
        "不得新增吊坠",
        "不得改成吊坠",
        "不得转成吊坠",
        "不得悬挂化吊坠",
        "禁止补造吊坠",
    ],
)
def test_necklace_without_pendant_rejects_creation_prohibitions_in_canonical(
    prohibition: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    payload["must_not_change"].append(prohibition)
    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    "prohibition",
    [
        "不要保留吊坠",
        "不保留吊坠",
        "不需要保留吊坠",
        "不应保留吊坠",
        "禁止保留吊坠",
        "无需保留吊坠",
    ],
)
def test_necklace_without_pendant_rejects_preservation_rejections_in_canonical(
    prohibition: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    payload["must_not_change"].append(prohibition)
    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    "prohibition",
    [
        "不得改变既有吊坠",
        "不得删除既有吊坠",
        "不得丢失既有吊坠",
        "不得替换既有吊坠",
    ],
)
def test_necklace_without_pendant_rejects_prohibited_destruction_of_pendant(
    prohibition: str,
) -> None:
    product = ProductAnalysis.from_dict(_plain_double_loop_analysis_data())
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    payload["must_not_change"].append(prohibition)
    constraints = ProductFidelityConstraints.from_dict(payload)

    with pytest.raises(ValueError, match="v2 无吊坠 canonical.*不得包含敏感词"):
        validate_product_fidelity_constraints(product, constraints)


def test_pendant_necklace_allows_positive_pendant_preservation_semantics() -> None:
    data = _plain_double_loop_analysis_data()
    data.update(
        {
            "product_type": "带链吊坠",
            "detected_product_type": "pendant_necklace",
            "confirmed_product_type": "pendant_necklace",
            "visible_appearance": "链条正面中心连接一枚主吊坠",
            "special_requirements": [],
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 2,
            "pendant_position": "front_center",
            "pendant_orientation": "front_facing",
        }
    )
    product = ProductAnalysis.from_dict(data)
    payload = copy.deepcopy(build_product_fidelity_constraints(product).to_dict())
    payload["must_not_change"].extend(
        ["不得改变主吊坠", "维持主吊坠形状", "继续保有吊坠连接", "保全吊坠"]
    )
    constraints = ProductFidelityConstraints.from_dict(payload)

    assert validate_product_fidelity_constraints(product, constraints) is constraints


def _analysis_with_length(length_category: str | None) -> dict[str, object]:
    data = _plain_double_loop_analysis_data()
    data["visible_appearance"] = "同一条连续微珠链绕颈形成上下两圈"
    data["special_requirements"] = []
    data["length_category"] = length_category
    return data


def _worn_necklace_reference(
    tmp_path: Path,
    *,
    index: int = 1,
    name: str = "necklace-worn-reference",
) -> ReferenceRow:
    reference_path = tmp_path / f"{name}.jpg"
    reference_path.write_bytes(b"reference")
    return ReferenceRow(
        index=index,
        file_name=reference_path.name,
        relative_path=reference_path.name,
        absolute_path=reference_path,
        width=1200,
        height=1600,
        size_mb=0.2,
        purpose_category="生活场景图；深色背景；真人佩戴构图参考",
        bracelet_applicability="否",
        default_strategy="优先使用",
        style_category="自然精致",
        scene_keywords="自然光",
        jewelry_type="项链",
        recommended_usage="颈部至胸前完整佩戴展示",
        notes="无原有首饰，画面空间充足",
        confidence="高",
        file_exists=True,
        applicable_product_types="necklace",
        applicable_display_modes="worn",
        framing="颈部至胸前半身",
        visible_body_regions="颈部、锁骨、胸前",
        product_visibility="高",
        neck_visibility="高",
        collarbone_visibility="高",
        chest_visibility="高",
        hand_visibility="低",
        collar_type="低领",
        clothing_occlusion_risk="低",
        hair_occlusion_risk="低",
        pose_keywords="正面",
        existing_jewelry="无",
        crop_risk="低",
    )


def _worn_necklace_references(tmp_path: Path) -> list[ReferenceRow]:
    return [
        _worn_necklace_reference(
            tmp_path,
            index=index,
            name=(
                "necklace-worn-reference"
                if index == 1
                else f"necklace-worn-reference-alt-{index}"
            ),
        )
        for index in range(1, 4)
    ]


def _write_null_length_run(tmp_path: Path) -> tuple[RunPaths, ProductAnalysis]:
    paths = RunPaths.create(tmp_path / "runs", "null-length")
    (paths.input_dir / "product-on-hand.jpg").write_bytes(b"product")
    data = _analysis_with_length(None)
    product = ProductAnalysis.from_dict(data)
    write_json(paths.analysis_dir / "product_analysis.json", data)
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        build_product_fidelity_constraints(product).to_dict(),
    )
    write_json(
        paths.analysis_dir / "output_role.json",
        {"output_role": "lifestyle"},
    )
    return paths, product


def test_prepare_review_rejects_null_necklace_length_before_top_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    product_image = tmp_path / "product.jpg"
    product_image.write_bytes(b"product")
    analysis_path = tmp_path / "analysis.json"
    write_json(analysis_path, _analysis_with_length(None))
    monkeypatch.setattr(
        "jewelry_on_hand.cli.sync_and_load_reference_rows",
        lambda _config: [_worn_necklace_reference(tmp_path)],
    )
    output_root = tmp_path / "runs"

    result = main(
        [
            "prepare-review",
            "--product-image",
            str(product_image),
            "--analysis-json",
            str(analysis_path),
            "--output-root",
            str(output_root),
            "--run-id",
            "prepare-null-length",
            "--output-role",
            "lifestyle",
        ]
    )

    assert result == 1
    assert "length_category" in capsys.readouterr().err
    assert not (
        output_root / "prepare-null-length" / "analysis" / "selected_references.json"
    ).exists()


def test_record_decision_rejects_null_necklace_length(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, _product = _write_null_length_run(tmp_path)

    result = main(
        [
            "record-decision",
            "--run-root",
            str(paths.root),
            "--action",
            "generate_rank_1",
            "--fidelity-confirmed",
            "--output-role",
            "lifestyle",
        ]
    )

    assert result == 1
    assert "length_category" in capsys.readouterr().err
    assert not (paths.review_dir / "review_decision.json").exists()


def test_generate_rejects_null_necklace_length_before_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, product = _write_null_length_run(tmp_path)
    reference = _worn_necklace_reference(tmp_path)
    write_json(
        paths.analysis_dir / "selected_references.json",
        [
            {
                "selected_reference": str(reference.absolute_path),
                "score": 100,
                "rank": 1,
                "reason": [],
                "risk": [],
                "ignored_reference_jewelry": [],
                "metadata": reference.metadata_dict(),
            }
        ],
    )
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
            "confirmation_snapshot": {
                **ProductConfirmationSnapshot.from_analysis(product).to_dict(),
                "length_category": None,
            },
        },
    )
    helper_called = False

    def fake_run_generation(*_args, **_kwargs):
        nonlocal helper_called
        helper_called = True
        return []

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    result = main(
        [
            "generate",
            "--run-root",
            str(paths.root),
            "--helper-script",
            str(tmp_path / "unused-helper.py"),
        ]
    )

    assert result == 1
    assert "length_category" in capsys.readouterr().err
    assert helper_called is False


def test_inspector_rejects_null_necklace_length(tmp_path: Path) -> None:
    analysis_path = tmp_path / "product_analysis.json"
    write_json(analysis_path, _analysis_with_length(None))
    validate = runpy.run_path(str(ARTIFACT_INSPECTOR))["_validate_product_analysis"]

    errors = validate(analysis_path)

    assert any("length_category" in error and "不能为空" in error for error in errors)


@pytest.mark.parametrize("length_category", ["choker", "collarbone", "upper_chest", "long"])
def test_all_legal_necklace_lengths_are_ready_for_workflow(
    tmp_path: Path,
    length_category: str,
) -> None:
    analysis_path = tmp_path / f"{length_category}.json"
    write_json(analysis_path, _analysis_with_length(length_category))

    product = load_product_analysis(analysis_path)
    snapshot = ProductConfirmationSnapshot.from_analysis(product)
    validate = runpy.run_path(str(ARTIFACT_INSPECTOR))["_validate_product_analysis"]

    assert snapshot.length_category == length_category
    assert not any("length_category" in error for error in validate(analysis_path))


def test_unknown_can_be_corrected_before_scoring_through_formal_cli_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_image = tmp_path / "unknown-product.jpg"
    product_image.write_bytes(b"product")
    analysis_path = tmp_path / "unknown-analysis.json"
    analysis_data = _analysis_with_length(None)
    analysis_data.update(
        {
            "product_type": "疑似项链",
            "detected_product_type": "unknown",
            "confirmed_product_type": "unknown",
            "classification_confidence": "low",
            "classification_evidence": ["颈部可见连续链状结构，但自动品类不确定"],
            "classification_source": "auto_uncertain",
            "uncertain_details": ["需要人工确认品类与长度等级"],
            "layer_count": 1,
        }
    )
    write_json(analysis_path, analysis_data)
    references = _worn_necklace_references(tmp_path)
    monkeypatch.setattr(
        "jewelry_on_hand.cli.sync_and_load_reference_rows",
        lambda _config: references,
    )
    output_root = tmp_path / "runs"
    run_root = output_root / "unknown-corrected"

    try:
        prepare_result = main(
            [
                "prepare-review",
                "--product-image",
                str(product_image),
                "--analysis-json",
                str(analysis_path),
                "--output-root",
                str(output_root),
                "--run-id",
                run_root.name,
                "--confirmed-product-type",
                "necklace",
                "--length-category",
                "collarbone",
                "--output-role",
                "lifestyle",
            ]
        )
    except SystemExit as exc:
        pytest.fail(f"prepare-review 尚未提供评分前人工纠正参数，退出码 {exc.code}")

    assert prepare_result == 0
    final_analysis = json.loads(
        (run_root / "analysis" / "product_analysis.json").read_text(encoding="utf-8")
    )
    assert final_analysis["detected_product_type"] == "unknown"
    assert final_analysis["confirmed_product_type"] == "necklace"
    assert final_analysis["classification_source"] == "manual_override"
    assert final_analysis["length_category"] == "collarbone"
    selected = json.loads(
        (run_root / "analysis" / "selected_references.json").read_text(encoding="utf-8")
    )
    assert selected[0]["metadata"]["applicable_product_types"] == "necklace"
    assert selected[0]["metadata"]["applicable_display_modes"] == "worn"

    assert (
        main(
            [
                "record-decision",
                "--run-root",
                str(run_root),
                "--action",
                "generate_rank_1",
                "--fidelity-confirmed",
                "--output-role",
                "lifestyle",
            ]
        )
        == 0
    )
    helper_calls: list[tuple[Path, dict[int, str]]] = []

    def fake_run_generation(paths, _product_image, prompts_by_rank, _helper_script, wait=True):
        assert wait is True
        helper_calls.append((paths.root, prompts_by_rank))
        return []

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert (
        main(
            [
                "generate",
                "--run-root",
                str(run_root),
                "--helper-script",
                str(tmp_path / "unused-helper.py"),
            ]
        )
        == 0
    )
    assert helper_calls and helper_calls[0][0] == run_root
    assert set(helper_calls[0][1]) == {1}


def test_prepare_review_still_rejects_final_unknown_before_top_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    product_image = tmp_path / "unknown-product.jpg"
    product_image.write_bytes(b"product")
    analysis_path = tmp_path / "unknown-analysis.json"
    analysis_data = _analysis_with_length(None)
    analysis_data.update(
        {
            "product_type": "无法识别",
            "detected_product_type": "unknown",
            "confirmed_product_type": "unknown",
            "classification_confidence": "low",
            "classification_source": "auto_uncertain",
        }
    )
    write_json(analysis_path, analysis_data)
    monkeypatch.setattr(
        "jewelry_on_hand.cli.sync_and_load_reference_rows",
        lambda _config: [_worn_necklace_reference(tmp_path)],
    )
    output_root = tmp_path / "runs"

    result = main(
        [
            "prepare-review",
            "--product-image",
            str(product_image),
            "--analysis-json",
            str(analysis_path),
            "--output-root",
            str(output_root),
            "--run-id",
            "unknown-unresolved",
            "--output-role",
            "lifestyle",
        ]
    )

    assert result == 1
    error = capsys.readouterr().err
    assert "人工纠正" in error or "无法识别" in error
    assert not (
        output_root / "unknown-unresolved" / "analysis" / "selected_references.json"
    ).exists()


def _necklace_reference(
    tmp_path: Path,
    *,
    index: int,
    name: str,
    display_mode: str,
    framing: str,
    multi_layer_space: bool = False,
) -> ReferenceRow:
    reference_path = tmp_path / f"{name}.jpg"
    reference_path.write_bytes(name.encode("utf-8"))
    hand_held = display_mode == "hand_held"
    notes = "无原有首饰，画面空间充足"
    if multi_layer_space:
        notes += "，具有多层垂直空间并能保持层间落差"
    return ReferenceRow(
        index=index,
        file_name=reference_path.name,
        relative_path=reference_path.name,
        absolute_path=reference_path,
        width=1200,
        height=1600,
        size_mb=0.2,
        purpose_category=(
            "手部佩戴图；深色背景；手持展示构图参考"
            if hand_held
            else "生活场景图；深色背景；真人佩戴构图参考"
        ),
        bracelet_applicability="否",
        default_strategy="优先使用",
        style_category="自然精致",
        scene_keywords="自然光",
        jewelry_type="项链",
        recommended_usage=(
            "双手捏持，完整链条自然垂落，具有真实接触"
            if hand_held
            else "颈部至胸前完整佩戴展示"
        ),
        notes=notes,
        confidence="高",
        file_exists=True,
        applicable_product_types="necklace",
        applicable_display_modes=display_mode,
        framing=framing,
        visible_body_regions=(
            "双手、手指、掌心" if hand_held else "颈部、锁骨、胸前"
        ),
        product_visibility="高",
        neck_visibility="低" if hand_held else "高",
        collarbone_visibility="低" if hand_held else "高",
        chest_visibility="高",
        hand_visibility="高" if hand_held else "低",
        collar_type="低领",
        clothing_occlusion_risk="低",
        hair_occlusion_risk="低",
        pose_keywords="双手捏持，链条完整" if hand_held else "正面",
        existing_jewelry="无",
        crop_risk="低",
    )


def _necklace_reference_set(
    tmp_path: Path,
    *,
    start_index: int,
    name: str,
    display_mode: str,
    framing: str,
    multi_layer_space: bool = False,
) -> list[ReferenceRow]:
    return [
        _necklace_reference(
            tmp_path,
            index=start_index + offset,
            name=name if offset == 0 else f"{name}-alt-{offset}",
            display_mode=display_mode,
            framing=framing,
            multi_layer_space=multi_layer_space,
        )
        for offset in range(3)
    ]


def _prepare_necklace_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str,
    display_mode: str = "worn",
    length_category: str = "collarbone",
    layer_count: int = 1,
    references: list[ReferenceRow] | None = None,
    prepare_overrides: list[str] | None = None,
) -> RunPaths:
    product_image = tmp_path / f"{run_id}-product.jpg"
    product_image.write_bytes(b"product")
    analysis_path = tmp_path / f"{run_id}-analysis.json"
    analysis_data = _analysis_with_length(length_category)
    analysis_data.update(
        {
            "display_mode": display_mode,
            "layer_count": layer_count,
            "visible_appearance": "一条连续项链",
            "special_requirements": [],
        }
    )
    write_json(analysis_path, analysis_data)
    if references is None:
        references = _necklace_reference_set(
            tmp_path,
            start_index=1,
            name=f"{run_id}-{display_mode}",
            display_mode=display_mode,
            framing=(
                "双手与胸前近景" if display_mode == "hand_held" else "颈部与锁骨近景"
            ),
            multi_layer_space=layer_count > 1,
        )
    monkeypatch.setattr(
        "jewelry_on_hand.cli.sync_and_load_reference_rows",
        lambda _config: references,
    )
    effective_display_mode = display_mode
    prepare_args = prepare_overrides or []
    for index, value in enumerate(prepare_args[:-1]):
        if value == "--display-mode":
            effective_display_mode = prepare_args[index + 1]
    output_role = "hand_worn" if effective_display_mode == "hand_held" else "lifestyle"
    output_root = tmp_path / "runs"
    argv = [
        "prepare-review",
        "--product-image",
        str(product_image),
        "--analysis-json",
        str(analysis_path),
        "--output-root",
        str(output_root),
        "--run-id",
        run_id,
        "--output-role",
        output_role,
        *prepare_args,
    ]
    try:
        result = main(argv)
    except SystemExit as exc:
        pytest.fail(f"prepare-review 缺少评分前纠正参数，退出码 {exc.code}")
    assert result == 0
    return RunPaths(root=output_root / run_id)


@pytest.mark.parametrize(
    ("initial_mode", "record_overrides"),
    [
        ("worn", ["--display-mode", "hand_held"]),
        ("hand_held", ["--display-mode", "worn"]),
        ("worn", ["--length-category", "long"]),
        ("worn", ["--layer-count", "2"]),
    ],
)
def test_record_decision_rejects_late_reference_affecting_corrections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    initial_mode: str,
    record_overrides: list[str],
) -> None:
    paths = _prepare_necklace_run(
        tmp_path,
        monkeypatch,
        run_id=f"late-{initial_mode}-{record_overrides[-1]}",
        display_mode=initial_mode,
    )
    analysis_before = (paths.analysis_dir / "product_analysis.json").read_bytes()
    selected_before = (paths.analysis_dir / "selected_references.json").read_bytes()
    output_role = json.loads(
        (paths.analysis_dir / "output_role.json").read_text(encoding="utf-8")
    )["output_role"]

    result = main(
        [
            "record-decision",
            "--run-root",
            str(paths.root),
            "--action",
            "generate_rank_1",
            "--fidelity-confirmed",
            "--output-role",
            output_role,
            *record_overrides,
        ]
    )

    assert result == 1
    assert "重新执行 prepare-review" in capsys.readouterr().err
    assert (paths.analysis_dir / "product_analysis.json").read_bytes() == analysis_before
    assert (paths.analysis_dir / "selected_references.json").read_bytes() == selected_before
    assert not (paths.review_dir / "review_decision.json").exists()


@pytest.mark.parametrize(
    ("source_mode", "prepare_overrides", "expected_name", "expected_field", "expected_value"),
    [
        ("worn", ["--display-mode", "hand_held"], "hand-held", "display_mode", "hand_held"),
        ("hand_held", ["--display-mode", "worn"], "worn-close", "display_mode", "worn"),
        ("worn", ["--length-category", "long"], "worn-long", "length_category", "long"),
        ("worn", ["--layer-count", "2"], "worn-multi", "layer_count", 2),
    ],
)
def test_prepare_review_applies_corrections_before_rescoring_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_mode: str,
    prepare_overrides: list[str],
    expected_name: str,
    expected_field: str,
    expected_value: object,
) -> None:
    references = [
        *_necklace_reference_set(
            tmp_path,
            start_index=1,
            name="worn-close",
            display_mode="worn",
            framing="颈部与锁骨特写",
        ),
        *_necklace_reference_set(
            tmp_path,
            start_index=4,
            name="hand-held",
            display_mode="hand_held",
            framing="双手与胸前近景",
        ),
        *_necklace_reference_set(
            tmp_path,
            start_index=7,
            name="worn-long",
            display_mode="worn",
            framing="上半身与胸前完整取景",
        ),
        *_necklace_reference_set(
            tmp_path,
            start_index=10,
            name="worn-multi",
            display_mode="worn",
            framing="上半身与胸前完整取景",
            multi_layer_space=True,
        ),
    ]
    paths = _prepare_necklace_run(
        tmp_path,
        monkeypatch,
        run_id=f"rescore-{expected_name}",
        display_mode=source_mode,
        references=references,
        prepare_overrides=prepare_overrides,
    )

    final_analysis = json.loads(
        (paths.analysis_dir / "product_analysis.json").read_text(encoding="utf-8")
    )
    selected = json.loads(
        (paths.analysis_dir / "selected_references.json").read_text(encoding="utf-8")
    )

    assert final_analysis[expected_field] == expected_value
    assert selected
    assert selected[0]["metadata"]["source_file_name"] == f"{expected_name}.jpg"


def _prepare_and_record_generation_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_id: str,
) -> RunPaths:
    paths = _prepare_necklace_run(
        tmp_path,
        monkeypatch,
        run_id=run_id,
    )
    output_role = json.loads(
        (paths.analysis_dir / "output_role.json").read_text(encoding="utf-8")
    )["output_role"]
    assert (
        main(
            [
                "record-decision",
                "--run-root",
                str(paths.root),
                "--action",
                "generate_rank_1",
                "--fidelity-confirmed",
                "--output-role",
                output_role,
            ]
        )
        == 0
    )
    return paths


@pytest.mark.parametrize(
    ("tamper_kind", "expected_error"),
    [
        ("external_path", "review_dir"),
        ("review_bytes", "SHA-256"),
        ("policy_metadata", "展示模式"),
    ],
)
def test_generate_revalidates_necklace_reference_path_digest_and_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tamper_kind: str,
    expected_error: str,
) -> None:
    paths = _prepare_and_record_generation_run(tmp_path, monkeypatch, f"tamper-{tamper_kind}")
    selected_path = paths.analysis_dir / "selected_references.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    review_copy = Path(selected[0]["selected_reference"])
    if tamper_kind == "external_path":
        external = tmp_path / "external-reference.jpg"
        external.write_bytes(b"external")
        selected[0]["selected_reference"] = str(external)
        write_json(selected_path, selected)
    elif tamper_kind == "review_bytes":
        review_copy.write_bytes(b"tampered")
    else:
        selected[0]["metadata"]["applicable_display_modes"] = "hand_held"
        selected[0]["metadata"]["适用展示模式"] = "hand_held"
        write_json(selected_path, selected)
    helper_called = False

    def fake_run_generation(*_args, **_kwargs):
        nonlocal helper_called
        helper_called = True
        return []

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    result = main(
        [
            "generate",
            "--run-root",
            str(paths.root),
            "--helper-script",
            str(tmp_path / "unused-helper.py"),
        ]
    )

    assert result == 1
    assert expected_error in capsys.readouterr().err
    assert helper_called is False
