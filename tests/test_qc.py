import json
import re
from dataclasses import replace

import pytest

import jewelry_on_hand.qc as qc_module
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import MustKeepConstraint, ProductAnalysis
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.product_analysis import product_analysis_to_dict
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.qc import build_qc_checklist, write_qc_result
from jewelry_on_hand.qc_review import (
    REFERENCE_FAILURE_CODES,
    build_reference_preservation_checklist,
)
from jewelry_on_hand.reference_composition import (
    ReferenceCompositionSnapshot,
    ReferencePose,
    ReplacementTarget,
)
from jewelry_on_hand.run_paths import read_json, write_json


def test_write_qc_result_writes_required_fields_to_qc_json(tmp_path):
    path = write_qc_result(
        tmp_path,
        "rerun",
        ["\u65e0\u6c34\u5370"],
        ["\u4e3b\u73e0\u88ab\u88c1\u5207"],
        "\u8c03\u6574\u53c2\u8003\u56fe",
    )

    assert path == tmp_path / "qc.json"
    assert path.exists()
    assert read_json(path) == {
        "status": "rerun",
        "passed": ["\u65e0\u6c34\u5370"],
        "failed": ["\u4e3b\u73e0\u88ab\u88c1\u5207"],
        "notes": "\u8c03\u6574\u53c2\u8003\u56fe",
        "fidelity_checks": [],
    }


def test_write_qc_result_normalizes_string_number_and_none_inputs(tmp_path):
    path = write_qc_result(tmp_path, "rerun", "\u65e0\u6c34\u5370", [404], None)

    assert read_json(path) == {
        "status": "rerun",
        "passed": ["\u65e0\u6c34\u5370"],
        "failed": ["404"],
        "notes": "",
        "fidelity_checks": [],
    }


def test_write_qc_result_rejects_pass_with_any_failed_item(tmp_path):
    with pytest.raises(ValueError, match="failed 必须为空"):
        write_qc_result(
            tmp_path,
            "pass",
            ["产品整体正确"],
            ["产品长度偏差"],
            "",
        )


def test_write_qc_result_normalizes_regular_iterables_item_by_item(tmp_path):
    failed_generator = (item for item in ("\u4e3b\u73e0\u88ab\u88c1\u5207", 2))

    path = write_qc_result(
        tmp_path,
        "rerun",
        ("\u6784\u56fe\u6b63\u786e", 1),
        failed_generator,
        "\u590d\u8dd1",
    )

    data = read_json(path)
    assert data["passed"] == ["\u6784\u56fe\u6b63\u786e", "1"]
    assert data["failed"] == ["\u4e3b\u73e0\u88ab\u88c1\u5207", "2"]


def test_write_qc_result_treats_mapping_and_binary_values_as_single_items(tmp_path):
    path = write_qc_result(
        tmp_path,
        "reject",
        {"a": 1},
        b"\xe6\x97\xa0\xe6\xb0\xb4\xe5\x8d\xb0",
        bytearray(b"note"),
    )

    assert read_json(path) == {
        "status": "reject",
        "passed": ["{'a': 1}"],
        "failed": ["\u65e0\u6c34\u5370"],
        "notes": "bytearray(b'note')",
        "fidelity_checks": [],
    }


def test_write_qc_result_falls_back_to_str_for_invalid_utf8_bytes(tmp_path):
    path = write_qc_result(tmp_path, "reject", b"\xff", bytearray(b"\xff"), "")

    assert read_json(path)["passed"] == ["b'\\xff'"]
    assert read_json(path)["failed"] == ["bytearray(b'\\xff')"]


def test_write_qc_result_rejects_unknown_status(tmp_path):
    with pytest.raises(ValueError, match="status"):
        write_qc_result(tmp_path, "unknown", [], [], "")


def test_write_qc_result_writes_fidelity_checks(tmp_path):
    qc_path = write_qc_result(
        tmp_path,
        "rerun",
        ["构图正确"],
        ["关键识别点失败"],
        "需要重跑",
        fidelity_checks=[
            {
                "name": "白水晶随形",
                "question": "白水晶随形是否仍是不规则透明异形珠",
                "result": "fail",
                "notes": "变成圆珠",
            }
        ],
    )

    data = read_json(qc_path)
    assert data["fidelity_checks"] == [
        {
            "name": "白水晶随形",
            "question": "白水晶随形是否仍是不规则透明异形珠",
            "result": "fail",
            "notes": "变成圆珠",
        }
    ]


def test_write_qc_result_rejects_pass_when_fidelity_check_failed(tmp_path):
    with pytest.raises(ValueError, match="must_keep"):
        write_qc_result(
            tmp_path,
            "pass",
            ["构图正确"],
            [],
            "",
            fidelity_checks=[
                {
                    "name": "白水晶随形",
                    "question": "白水晶随形是否仍是不规则透明异形珠",
                    "result": "fail",
                    "notes": "变成圆珠",
                }
            ],
        )


def test_build_qc_checklist_includes_policy_worn_necklace_and_must_keep_items():
    must_keep = MustKeepConstraint(
        name="主吊坠",
        source_text="第二层中央水滴吊坠",
        normalized_keyword="水滴吊坠",
        location="第二层中央",
        visual_shape="水滴形",
        relationship="连接第二层链条",
        forbid=("不得换层",),
        qc_question="主吊坠是否仍位于第二层中央并保持水滴形？",
    )

    items = build_qc_checklist(
        ProductType.PENDANT_NECKLACE,
        DisplayMode.WORN,
        (must_keep,),
    )

    assert "项链层数、顺序和相对落差正确" in items
    assert "产品颜色、材质、透明度、纹理、反光和比例与产品图一致" in items
    assert "层数、上下顺序、长度等级和层间落差与产品图一致" in items
    assert "吊坠所属层、位置、朝向和连接关系与产品图一致" in items
    assert "链条没有穿肤、穿衣、穿发、悬空或陷入身体" in items
    assert "多层链没有错误交叉、合并或复制" in items
    assert "没有自动补链、凭空补链或补充不存在的连接结构" in items
    assert "没有迁移产品图中的颈部、胸部、衣服、头发或皮肤块" in items
    assert must_keep.qc_question in items


def test_build_qc_checklist_includes_hand_held_necklace_checks():
    items = build_qc_checklist(
        ProductType.NECKLACE,
        DisplayMode.HAND_HELD,
    )

    assert "产品结构完整且关键结构可辨认" in items
    assert "手部与链条接触真实，链条自然垂落" in items
    assert "手指没有穿透链条或吊坠" in items
    assert "吊坠和关键结构没有被不合理遮挡" in items
    assert "产品比例合理，没有因近景明显放大或缩小" in items
    assert "没有虚构佩戴链路、自动补链或补充不存在的结构" in items


def test_build_qc_checklist_includes_ring_position_structure_and_contact_checks():
    items = build_qc_checklist(ProductType.RING, DisplayMode.WORN)

    assert "画面中只有一枚目标戒指" in items
    assert "戒指位于确认后的左右手和目标手指根部" in items
    assert "戒圈自然环绕手指且前后遮挡、接触和阴影真实" in items


def test_qc_check_id_is_stable_for_normalized_question_text():
    first = qc_module.qc_check_id("  产品结构\n是否完整  ")
    second = qc_module.qc_check_id("产品结构 是否完整")

    assert first == second
    assert re.fullmatch(r"qc-[0-9a-f]{64}", first)
    assert qc_module.qc_check_id("产品结构是否完整") != first


@pytest.mark.parametrize(
    "question",
    [
        "",
        " \t\n",
        " \u200b ",
        "\ufeff",
        "\u200c",
        "\u200d",
        "\u2060",
        "\u00ad",
        None,
        1,
        True,
    ],
)
def test_qc_check_id_rejects_empty_or_non_string_question(question):
    with pytest.raises(ValueError, match="QC 问题必须是非空字符串"):
        qc_module.qc_check_id(question)


def test_qc_check_id_preserves_format_character_inside_normal_text():
    plain = qc_module.qc_check_id("产品结构")
    with_joiner = qc_module.qc_check_id(" 产品\u200b结构 ")

    assert with_joiner == qc_module.qc_check_id("产品\u200b结构")
    assert with_joiner != plain


def test_qc_checklist_deduplicates_by_normalized_question_and_keeps_stable_id():
    first = _qc_must_keep("  主吊坠\u200b是否保留？ ")
    duplicate = _qc_must_keep("主吊坠是否保留?")

    items = build_qc_checklist(
        ProductType.PENDANT_NECKLACE,
        DisplayMode.WORN,
        (first, duplicate),
    )
    expected_id = qc_module.qc_check_id(first.qc_question)
    matching = [item for item in items if item.id == expected_id]

    assert len(matching) == 1
    assert matching[0].question == first.qc_question


def test_qc_checklist_rejects_different_questions_when_ids_collide(monkeypatch):
    monkeypatch.setattr(qc_module, "qc_check_id", lambda _question: "qc-collision")

    with pytest.raises(ValueError, match="不同 QC 问题.*ID.*碰撞"):
        build_qc_checklist(ProductType.BRACELET, DisplayMode.WORN)


def test_qc_checklist_items_are_immutable_string_compatible_records():
    items = build_qc_checklist(ProductType.BRACELET, DisplayMode.WORN)
    item = items[0]

    assert isinstance(item, str)
    assert isinstance(item, qc_module.QCChecklistItem)
    assert item.question == str(item)
    assert item.id == qc_module.qc_check_id(item.question)
    assert item.startswith("产品")
    assert "产品" in item
    assert item + "。" == f"{item}。"
    assert json.loads(json.dumps(items, ensure_ascii=False))[0] == item.question
    with pytest.raises(AttributeError):
        item.id = "qc-tampered"
    with pytest.raises(AttributeError):
        item.question = "篡改问题"


@pytest.mark.parametrize("must_keep", ["", b"", bytearray(), {}, set(), frozenset()])
def test_legacy_qc_rejects_falsey_or_non_sequence_must_keep(must_keep):
    with pytest.raises(ValueError, match="must_keep.*列表"):
        build_qc_checklist(
            ProductType.BRACELET,
            DisplayMode.WORN,
            must_keep,
        )


def test_legacy_qc_iterables_use_deterministic_full_structure_order():
    morphology_b = replace(
        _qc_must_keep("主吊坠是否保留 B 形态"),
        name="同名要求",
        source_text="同一来源",
        normalized_keyword="同一关键词",
        location="同一位置",
        visual_shape="B 形态",
        relationship="B 邻接",
        forbid=("禁止 B",),
    )
    morphology_a = replace(
        _qc_must_keep("主吊坠是否保留 A 形态"),
        name="同名要求",
        source_text="同一来源",
        normalized_keyword="同一关键词",
        location="同一位置",
        visual_shape="A 形态",
        relationship="A 邻接",
        forbid=("禁止 A",),
    )

    tuple_items = build_qc_checklist(
        ProductType.PENDANT_NECKLACE,
        DisplayMode.WORN,
        (morphology_b, morphology_a),
    )
    generator_items = build_qc_checklist(
        ProductType.PENDANT_NECKLACE,
        DisplayMode.WORN,
        (item for item in (morphology_a, morphology_b)),
    )
    set_iterator_items = build_qc_checklist(
        ProductType.PENDANT_NECKLACE,
        DisplayMode.WORN,
        iter({morphology_b, morphology_a}),
    )

    assert generator_items == tuple_items
    assert set_iterator_items == tuple_items
    assert [item.id for item in generator_items] == [item.id for item in tuple_items]
    assert tuple_items.index(morphology_a.qc_question) < tuple_items.index(
        morphology_b.qc_question
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("name", 1),
        ("source_text", None),
        ("normalized_keyword", True),
        ("location", 1.0),
        ("visual_shape", []),
        ("relationship", {}),
        ("forbid", ("合法", 1)),
        ("qc_question", "问题".encode("utf-8")),
    ],
)
def test_legacy_qc_sort_key_rejects_tampered_field_types(
    field_name,
    invalid_value,
):
    item = _qc_must_keep("主吊坠是否保留")
    object.__setattr__(item, field_name, invalid_value)

    with pytest.raises(ValueError, match=rf"must_keep\.{field_name}"):
        build_qc_checklist(
            ProductType.PENDANT_NECKLACE,
            DisplayMode.WORN,
            (item,),
        )


def test_qc_checklist_rejects_visually_empty_must_keep_question():
    must_keep = _qc_must_keep("\u200b\ufeff")

    with pytest.raises(ValueError, match="QC 问题必须是非空字符串"):
        build_qc_checklist(
            ProductType.PENDANT_NECKLACE,
            DisplayMode.WORN,
            (must_keep,),
        )


@pytest.mark.parametrize(
    "product_type",
    [
        ProductType.BRACELET,
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
        ProductType.RING,
    ],
)
def test_modern_qc_checklist_is_stable_and_covers_canonical_must_keep(product_type):
    analysis = _qc_analysis_for_category(product_type)
    constraints = _confirmed_qc_constraints(analysis)

    first = build_qc_checklist(
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )
    second = build_qc_checklist(
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )

    assert first == second
    assert first
    assert all(isinstance(question, str) and question.strip() for question in first)
    assert set(item.qc_question for item in constraints.must_keep).issubset(first)
    ids = [qc_module.qc_check_id(question) for question in first]
    assert len(ids) == len(set(ids))


def test_modern_pendant_qc_covers_structured_identity_and_forbids_second_pendant():
    analysis = _qc_analysis_for_category(ProductType.PENDANT_NECKLACE)
    constraints = _confirmed_qc_constraints(analysis)

    questions = build_qc_checklist(
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )
    combined = "\n".join(questions)

    assert "1 颗" in combined
    assert "第 2 层" in combined
    assert "第二层中央" in combined
    assert "正面向前" in combined
    assert "吊环连接第二层链条" in combined
    assert "禁止新增第二颗吊坠" in combined


@pytest.mark.parametrize(
    "product_type",
    [ProductType.BRACELET, ProductType.NECKLACE, ProductType.RING],
)
def test_non_pendant_modern_qc_has_no_structured_main_pendant_questions(product_type):
    analysis = _qc_analysis_for_category(product_type)
    constraints = _confirmed_qc_constraints(analysis)

    questions = build_qc_checklist(
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )

    assert not any("吊坠" in question for question in questions)


def test_non_pendant_modern_qc_rejects_canonical_pendant_requirement():
    analysis = replace(
        _qc_analysis_for_category(ProductType.RING),
        special_requirements=("禁止新增吊坠",),
    )
    constraints = _confirmed_qc_constraints(analysis)
    assert any("吊坠" in item.qc_question for item in constraints.must_keep)

    with pytest.raises(ValueError, match="产品品类.*吊坠要求冲突"):
        build_qc_checklist(
            product_analysis=analysis,
            fidelity_constraints=constraints,
        )


@pytest.mark.parametrize("term", ["吊坠", "主吊坠", "链坠", "流苏", "坠子"])
@pytest.mark.parametrize("format_character", ["\u200b", "\u200c", "\u2060"])
def test_non_pendant_modern_qc_rejects_format_obfuscated_pendant_requirement(
    term,
    format_character,
):
    obfuscated = term[0] + format_character + term[1:]
    analysis = replace(
        _qc_analysis_for_category(ProductType.RING),
        special_requirements=(f"禁止新增{obfuscated}",),
    )
    constraints = _confirmed_qc_constraints(analysis)

    with pytest.raises(ValueError, match="产品品类.*吊坠要求冲突"):
        build_qc_checklist(
            product_analysis=analysis,
            fidelity_constraints=constraints,
        )


def test_modern_qc_preserves_canonical_must_keep_order():
    analysis = _qc_analysis_for_category(ProductType.RING)
    constraints = _confirmed_qc_constraints(analysis)

    items = build_qc_checklist(
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )
    checklist_questions = [item.question for item in items]
    positions = [
        checklist_questions.index(item.qc_question)
        for item in constraints.must_keep
    ]

    assert positions == sorted(positions)


def test_modern_qc_requires_analysis_and_constraints_together():
    analysis = _qc_analysis_for_category(ProductType.BRACELET)
    constraints = _confirmed_qc_constraints(analysis)

    with pytest.raises(ValueError, match="必须同时提供"):
        build_qc_checklist(product_analysis=analysis)
    with pytest.raises(ValueError, match="必须同时提供"):
        build_qc_checklist(fidelity_constraints=constraints)


def test_modern_qc_rejects_unconfirmed_fidelity_constraints():
    analysis = _qc_analysis_for_category(ProductType.BRACELET)
    constraints = build_product_fidelity_constraints(analysis)
    assert constraints.review_status == "pending"

    with pytest.raises(ValueError, match="review_status.*生成"):
        build_qc_checklist(
            product_analysis=analysis,
            fidelity_constraints=constraints,
        )


def test_modern_qc_rejects_explicit_category_or_must_keep_bypass():
    analysis = _qc_analysis_for_category(ProductType.PENDANT_NECKLACE)
    constraints = _confirmed_qc_constraints(analysis)

    with pytest.raises(ValueError, match="品类不一致"):
        build_qc_checklist(
            ProductType.BRACELET,
            analysis.display_mode,
            constraints.must_keep,
            product_analysis=analysis,
            fidelity_constraints=constraints,
        )
    with pytest.raises(ValueError, match="must_keep.*不一致"):
        build_qc_checklist(
            analysis.normalized_product_type,
            analysis.display_mode,
            (),
            product_analysis=analysis,
            fidelity_constraints=constraints,
        )


def test_modern_qc_rejects_analysis_digest_or_canonical_structure_mismatch():
    analysis = _qc_analysis_for_category(ProductType.PENDANT_NECKLACE)
    constraints = _confirmed_qc_constraints(analysis)

    changed_analysis = replace(analysis, style_mood="已被修改")
    with pytest.raises(ValueError, match="product_analysis_sha256.*不一致"):
        build_qc_checklist(
            product_analysis=changed_analysis,
            fidelity_constraints=constraints,
        )

    changed_constraints = replace(
        constraints,
        must_not_change=(*constraints.must_not_change, "额外结构改写"),
    )
    with pytest.raises(ValueError, match="canonical.must_not_change.*不一致"):
        build_qc_checklist(
            product_analysis=analysis,
            fidelity_constraints=changed_constraints,
        )


@pytest.mark.parametrize(
    "critical_failure",
    [
        "layer_count_mismatch",
        "length_category_mismatch",
        "pendant_layer_changed",
        "auto_chain_added",
        "source_person_region_migrated",
    ],
)
def test_write_qc_result_rejects_pass_when_critical_check_failed(
    tmp_path,
    critical_failure,
):
    with pytest.raises(ValueError, match="不得标记为 pass"):
        write_qc_result(
            tmp_path,
            "pass",
            ["构图正确"],
            [],
            "",
            critical_failures=[critical_failure],
        )


def test_write_qc_result_persists_critical_failures_for_reject(tmp_path):
    path = write_qc_result(
        tmp_path,
        "reject",
        ["无水印"],
        ["检测到自动补链"],
        "返回产品分析阶段",
        critical_failures=["auto_chain_added"],
    )

    assert read_json(path)["critical_failures"] == ["auto_chain_added"]


def test_modern_qc_pass_requires_complete_three_layer_coverage(tmp_path):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )
    reference_checks = _reference_checks(snapshot)

    for field_name, incomplete in (
        ("reference_preservation_checks", reference_checks[:-1]),
        ("fidelity_checks", fidelity_checks[:-1]),
        ("checklist_checks", checklist_checks[:-1]),
    ):
        arguments = {
            "reference_preservation_checks": reference_checks,
            "fidelity_checks": fidelity_checks,
            "checklist_checks": checklist_checks,
        }
        arguments[field_name] = incomplete
        with pytest.raises(ValueError, match=rf"{field_name}.*完整|{field_name}.*数量"):
            write_qc_result(
                generation_dir,
                "pass",
                ["三层人工检查全部完成"],
                [],
                "逐项人工对照",
                **arguments,
            )
        assert not (generation_dir / "qc.json").exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda checks: checks + [dict(checks[0])], "唯一"),
        (lambda checks: [dict(checks[0], name="unknown")] + checks[1:], "未知|完整"),
        (lambda checks: [dict(checks[0], question="错误问题")] + checks[1:], "question|问题"),
        (lambda checks: [dict(checks[0], evidence=None)] + checks[1:], "evidence.*必填"),
        (
            lambda checks: [
                dict(
                    checks[0],
                    evidence=dict(
                        checks[0]["evidence"],
                        comparison_source="product_identity",
                    ),
                )
            ]
            + checks[1:],
            "comparison_source",
        ),
    ],
)
def test_modern_qc_rejects_invalid_reference_preservation_checks(
    tmp_path,
    mutation,
    message,
):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )

    with pytest.raises(ValueError, match=message):
        write_qc_result(
            generation_dir,
            "pass",
            ["三层人工检查全部完成"],
            [],
            "逐项人工对照",
            reference_preservation_checks=mutation(_reference_checks(snapshot)),
            fidelity_checks=fidelity_checks,
            checklist_checks=checklist_checks,
        )

    assert not (generation_dir / "qc.json").exists()


def test_modern_qc_accepts_complete_three_layer_pass_and_persists_all_layers(tmp_path):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )
    reference_checks = _reference_checks(snapshot)

    path = write_qc_result(
        generation_dir,
        "pass",
        ["三层人工检查全部完成"],
        [],
        "逐项人工对照",
        reference_preservation_checks=reference_checks,
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
    )

    payload = read_json(path)
    assert payload["reference_preservation_checks"] == reference_checks
    assert payload["fidelity_checks"] == fidelity_checks
    assert payload["checklist_checks"] == checklist_checks


@pytest.mark.parametrize(("check_name", "critical_code"), REFERENCE_FAILURE_CODES.items())
def test_reference_fail_requires_exact_mapped_critical_code(
    tmp_path,
    check_name,
    critical_code,
):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )
    checks = _reference_checks(snapshot)
    index = next(i for i, check in enumerate(checks) if check["name"] == check_name)
    checks[index] = dict(
        checks[index],
        result="fail",
        issue_code=critical_code,
        evidence=_reference_evidence(check_name, result="fail"),
    )

    wrong_code = next(
        code for code in set(REFERENCE_FAILURE_CODES.values()) if code != critical_code
    )
    for critical_failures in ([], [wrong_code]):
        with pytest.raises(ValueError, match="critical_failures.*映射|错码|缺少"):
            write_qc_result(
                generation_dir,
                "reject",
                [],
                ["参考结构失败"],
                "人工复核",
                reference_preservation_checks=checks,
                fidelity_checks=fidelity_checks,
                checklist_checks=checklist_checks,
                critical_failures=critical_failures,
            )

    path = write_qc_result(
        generation_dir,
        "reject",
        [],
        ["参考结构失败"],
        "人工复核",
        reference_preservation_checks=checks,
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
        critical_failures=[critical_code],
    )
    assert read_json(path)["critical_failures"] == [critical_code]


def test_two_reference_failures_sharing_one_code_are_deduplicated(tmp_path):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )
    checks = _reference_checks(snapshot)
    for check_name in (
        "subject_placement_preserved",
        "replacement_target_preserved",
    ):
        index = next(i for i, check in enumerate(checks) if check["name"] == check_name)
        checks[index] = dict(
            checks[index],
            result="fail",
            issue_code="replacement_target_changed",
            evidence=_reference_evidence(check_name, result="fail"),
        )

    path = write_qc_result(
        generation_dir,
        "reject",
        [],
        ["主体位置和替换位置均改变"],
        "人工复核",
        reference_preservation_checks=checks,
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
        critical_failures=["replacement_target_changed"],
    )
    assert read_json(path)["critical_failures"] == ["replacement_target_changed"]


def test_only_source_jewelry_edge_residue_may_use_reference_rerun(tmp_path):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )
    checks = _reference_checks(snapshot)
    checks[-3] = dict(
        checks[-3],
        result="rerun",
        issue_code="minor_edge_residue",
        notes="放大查看原手串位置，仍有两像素灰色边缘需要局部清理",
        evidence={
            "comparison_source": "scene_reference",
            "region": "左手腕原手串接触边缘",
            "observation": "仅见两像素灰色边缘，未见完整珠体或原手串主体",
            "source_jewelry_subject_visible": False,
            "residual_scope": "edge_pixels",
        },
    )

    path = write_qc_result(
        generation_dir,
        "rerun",
        [],
        ["原首饰存在轻微边缘残留"],
        "只允许局部修复",
        reference_preservation_checks=checks,
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
    )
    assert read_json(path)["status"] == "rerun"

    checks[-3] = dict(
        checks[-3],
        evidence={
            "comparison_source": "scene_reference",
            "region": "左手腕原手串区域",
            "observation": "可见完整珠体轮廓",
            "source_jewelry_subject_visible": True,
            "residual_scope": "subject_or_large_area",
        },
    )
    with pytest.raises(ValueError, match="minor_edge_residue|subject_visible|residual_scope"):
        write_qc_result(
            generation_dir,
            "rerun",
            [],
            ["原首饰主体残留"],
            "不能局部修复",
            reference_preservation_checks=checks,
            fidelity_checks=fidelity_checks,
            checklist_checks=checklist_checks,
        )


@pytest.mark.parametrize(
    "issue_code",
    [
        "local_blending_artifact",
        "local_shadow_mismatch",
        "non_core_texture_mismatch",
    ],
)
def test_replacement_target_allows_only_controlled_local_rerun_issues(
    tmp_path,
    issue_code,
):
    generation_dir, snapshot, fidelity_checks, checklist_checks = (
        _modern_qc_generation(tmp_path)
    )
    checks = _reference_checks(snapshot)
    index = next(
        i
        for i, check in enumerate(checks)
        if check["name"] == "replacement_target_preserved"
    )
    checks[index] = dict(
        checks[index],
        result="rerun",
        issue_code=issue_code,
        evidence={
            "comparison_source": "confirmed_snapshot",
            "region": "目标产品与手腕接触边缘",
            "observation": "替换位置不变，仅局部融合细节需要修复",
        },
    )

    path = write_qc_result(
        generation_dir,
        "rerun",
        [],
        ["局部融合需要修复"],
        "人工复核",
        reference_preservation_checks=checks,
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
    )
    assert read_json(path)["reference_preservation_checks"][index]["issue_code"] == issue_code

    checks[0] = dict(
        checks[0],
        result="rerun",
        issue_code="local_blending_artifact",
        notes="对照网格确认主体裁切边界发生变化",
    )
    with pytest.raises(ValueError, match="构图|rerun"):
        write_qc_result(
            generation_dir,
            "rerun",
            [],
            ["景别变化"],
            "不能局部修复",
            reference_preservation_checks=checks,
            fidelity_checks=fidelity_checks,
            checklist_checks=checklist_checks,
        )


def _modern_qc_generation(tmp_path):
    generation_dir = tmp_path / "run" / "generation" / "01"
    generation_dir.mkdir(parents=True)
    analysis = _qc_analysis_for_category(ProductType.BRACELET)
    constraints = _confirmed_qc_constraints(analysis)
    snapshot = ReferenceCompositionSnapshot(
        rank=1,
        reference_file="rank-1-scene.jpg",
        reference_sha256="1" * 64,
        output_role="hand_worn",
        framing="手腕近景",
        camera_angle="平视",
        subject_placement="手腕居中",
        visible_body_regions=("左手腕",),
        pose=ReferencePose("身体未入镜", "前臂横向", "手背朝上", "左手"),
        clothing="黑色袖口",
        background="深色木纹",
        lighting="左侧柔光",
        replacement_target=ReplacementTarget("左手腕", "原手串", 1),
        other_jewelry_to_remove=(),
        text_or_ui_risk="none",
        product_visibility_sufficient=True,
        composition_signature="signature",
    )
    write_json(
        generation_dir / "product-analysis.json",
        product_analysis_to_dict(analysis),
    )
    write_json(
        generation_dir / "product-fidelity-constraints.json",
        constraints.to_dict(),
    )
    write_json(
        generation_dir / "reference-composition-snapshot.json",
        snapshot.to_dict(),
    )
    write_json(
        generation_dir / "input-manifest.json",
        {"schema_version": 1, "output_role": "hand_worn"},
    )
    fidelity_checks = [
        {
            "name": item.name,
            "question": item.qc_question,
            "result": "pass",
            "notes": f"对照产品身份图确认 {item.name} 的位置和外观一致",
        }
        for item in constraints.must_keep
    ]
    checklist_checks = [
        {
            "id": item.id,
            "question": item.question,
            "result": "pass",
            "notes": f"逐项检查确认：{item.question}",
        }
        for item in build_qc_checklist(
            product_analysis=analysis,
            fidelity_constraints=constraints,
        )
    ]
    return generation_dir, snapshot, fidelity_checks, checklist_checks


def _reference_checks(snapshot):
    return [
        {
            "name": name,
            "question": question,
            "result": "pass",
            "issue_code": None,
            "notes": f"对照参考底图网格逐项确认 {name} 保持一致",
            "evidence": _reference_evidence(name, result="pass"),
        }
        for name, question in build_reference_preservation_checklist(snapshot)
    ]


def _reference_evidence(name, *, result):
    comparison_sources = {
        "replacement_target_preserved": "confirmed_snapshot",
        "single_target_product": "product_identity",
    }
    evidence = {
        "comparison_source": comparison_sources.get(name, "scene_reference"),
        "region": f"{name} 对应画面区域",
        "observation": f"逐项对照确认 {name} 的可见事实",
    }
    if name == "source_jewelry_removed":
        if result == "pass":
            evidence.update(
                source_jewelry_subject_visible=False,
                residual_scope="none",
            )
        elif result == "rerun":
            evidence.update(
                source_jewelry_subject_visible=False,
                residual_scope="edge_pixels",
            )
        else:
            evidence.update(
                source_jewelry_subject_visible=True,
                residual_scope="subject_or_large_area",
            )
    return evidence


@pytest.mark.parametrize(
    ("fidelity_checks", "message"),
    [
        ([], "数量"),
        (
            [
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                },
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                },
            ],
            "唯一",
        ),
        (
            [
                {
                    "name": "错误名称",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                }
            ],
            "name",
        ),
        (
            [
                {
                    "name": "主吊坠",
                    "question": "错误问题",
                    "result": "pass",
                    "notes": "",
                }
            ],
            "question",
        ),
        (
            [
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "unknown",
                    "notes": "",
                }
            ],
            "result",
        ),
    ],
)
def test_write_qc_result_requires_complete_unique_must_keep_coverage(
    tmp_path,
    fidelity_checks,
    message,
):
    generation_dir = tmp_path / "run" / "generation" / "01"
    constraints_path = tmp_path / "run" / "analysis" / "product_fidelity_constraints.json"
    write_json(constraints_path, _constraints_with_must_keep())

    with pytest.raises(ValueError, match=message):
        write_qc_result(
            generation_dir,
            "rerun",
            ["构图正确"],
            ["需要复核"],
            "",
            fidelity_checks=fidelity_checks,
        )

    assert not (generation_dir / "qc.json").exists()


@pytest.mark.parametrize(
    ("second_name", "second_question"),
    [
        ("主吊坠", "主吊坠是否保持所属层？"),
        ("吊坠连接环", "主吊坠是否保持原连接？"),
    ],
)
def test_write_qc_result_allows_unique_name_question_pairs(
    tmp_path,
    second_name,
    second_question,
):
    generation_dir = tmp_path / "run" / "generation" / "01"
    constraints_path = tmp_path / "run" / "analysis" / "product_fidelity_constraints.json"
    constraints = _constraints_with_must_keep()
    second = dict(constraints["must_keep"][0])
    second["name"] = second_name
    second["qc_question"] = second_question
    constraints["must_keep"].append(second)
    write_json(constraints_path, constraints)

    path = write_qc_result(
        generation_dir,
        "pass",
        ["没有迁移产品图中的人物局部，迁移检查通过"],
        [],
        "",
        fidelity_checks=[
            {
                "name": "主吊坠",
                "question": "主吊坠是否保持原连接？",
                "result": "pass",
                "notes": "",
            },
            {
                "name": second_name,
                "question": second_question,
                "result": "pass",
                "notes": "",
            },
        ],
    )

    assert path.is_file()


def _constraints_with_must_keep():
    return {
        "schema_version": 1,
        "source": {
            "product_id": "PN-001",
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
        },
        "detected_keywords": ["主吊坠"],
        "must_keep": [
            {
                "name": "主吊坠",
                "source_text": "第二层中央主吊坠",
                "normalized_keyword": "主吊坠",
                "location": "第二层中央",
                "visual_shape": "水滴形",
                "relationship": "连接第二层链条",
                "forbid": ["不得换层"],
                "qc_question": "主吊坠是否保持原连接？",
            }
        ],
        "must_not_change": ["层间关系"],
        "needs_user_review": False,
        "detail_crop_recommended": False,
        "review_status": "confirmed",
    }


def _confirmed_qc_constraints(analysis):
    constraints = build_product_fidelity_constraints(analysis)
    if constraints.review_status == "pending":
        return replace(constraints, review_status="confirmed")
    return constraints


def _qc_must_keep(question):
    return MustKeepConstraint(
        name="主吊坠",
        source_text="第二层中央主吊坠",
        normalized_keyword="主吊坠",
        location="第二层中央",
        visual_shape="水滴形",
        relationship="连接第二层链条",
        forbid=("不得换层",),
        qc_question=question,
    )


def _qc_analysis_for_category(product_type):
    if product_type in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}:
        has_pendant = product_type is ProductType.PENDANT_NECKLACE
        return ProductAnalysis.from_dict(
            {
                "product_type": product_type.value,
                "detected_product_type": product_type.value,
                "confirmed_product_type": product_type.value,
                "classification_confidence": "high",
                "classification_evidence": ["肉眼可见结构"],
                "classification_source": "manual_override",
                "display_mode": "worn",
                "source_image_type": "worn_source",
                "wear_position": "颈部",
                "visible_appearance": (
                    "双层细链，第二层中央有水滴形吊坠"
                    if has_pendant
                    else "同一条连续海蓝宝微珠长链绕颈形成上下双圈"
                ),
                "color_family": ["海蓝"],
                "style_mood": "清透",
                "composition": "真人佩戴正面构图",
                "product_dimensions": {},
                "needs_full_front_display": True,
                "special_requirements": [],
                "layer_count": 2,
                "length_category": "long",
                "chain_or_strand_type": "连续微珠链",
                "has_pendant": has_pendant,
                "pendant_count": 1 if has_pendant else 0,
                "pendant_layer": 2 if has_pendant else None,
                "pendant_position": "第二层中央" if has_pendant else None,
                "pendant_orientation": "正面向前" if has_pendant else None,
                "connection_structure": (
                    "吊环连接第二层链条" if has_pendant else None
                ),
                "symmetry": "沿身体中线对称",
                "is_independent_multi_item": False,
            }
        )
    if product_type is ProductType.BRACELET:
        return ProductAnalysis.from_dict(
            {
                "product_type": "bracelet",
                "detected_product_type": "bracelet",
                "confirmed_product_type": "bracelet",
                "classification_confidence": "high",
                "classification_evidence": ["手腕处可见闭合珠串"],
                "classification_source": "manual_override",
                "display_mode": "worn",
                "source_image_type": "worn_source",
                "wear_position": "手腕",
                "visible_appearance": "圆珠手链主珠右侧有一颗透明随形",
                "color_family": ["海蓝", "透明"],
                "style_mood": "清透",
                "composition": "真人手腕近景",
                "product_dimensions": {"bead_diameter_mm": 8.0},
                "needs_full_front_display": True,
                "special_requirements": ["保持可见珠序"],
                "layer_count": 1,
                "has_pendant": False,
                "pendant_count": 0,
                "pendant_layer": None,
                "is_independent_multi_item": False,
            }
        )
    if product_type is ProductType.RING:
        return ProductAnalysis.from_dict(
            {
                "product_type": "ring",
                "detected_product_type": "ring",
                "confirmed_product_type": "ring",
                "classification_confidence": "high",
                "classification_evidence": ["左手无名指根部可见单枚戒指"],
                "classification_source": "manual_override",
                "display_mode": "worn",
                "source_image_type": "worn_source",
                "wear_position": "左手无名指根部",
                "visible_appearance": "单枚银色开口戒指，椭圆戒面中央有透明主石",
                "color_family": ["银色", "透明"],
                "style_mood": "克制",
                "composition": "真人手部近景",
                "product_dimensions": {"width_mm": 9.0},
                "needs_full_front_display": True,
                "special_requirements": ["保持开口端点方向"],
                "layer_count": 1,
                "has_pendant": False,
                "pendant_count": 0,
                "pendant_layer": None,
                "occluded_parts": ["戒圈背面"],
                "uncertain_details": ["镶嵌背面结构"],
                "is_independent_multi_item": False,
                "ring_count": 1,
                "hand_side": "left",
                "finger_position": "ring",
                "ring_wear_style": "finger_base",
            }
        )
    raise AssertionError(f"未覆盖 QC 测试品类：{product_type}")
