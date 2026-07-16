import hashlib

import pytest

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import (
    MustKeepConstraint,
    ProductAnalysis,
    ProductFidelityConstraints,
)
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.qc import build_qc_checklist, qc_check_id, write_qc_result
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


@pytest.mark.parametrize("status", ["pass", "rerun", "reject"])
def test_standard_modern_run_requires_complete_runtime_checklist_for_every_status(
    tmp_path,
    status,
):
    generation_dir, _analysis, constraints = _modern_ring_run(tmp_path)
    fidelity_checks = [
        {
            "name": item.name,
            "question": item.qc_question,
            "result": "pass",
            "notes": "已核对",
        }
        for item in constraints.must_keep
    ]

    with pytest.raises(ValueError, match="checklist_checks.*完整覆盖"):
        write_qc_result(
            generation_dir,
            status,
            ["少量自由文本"],
            [] if status == "pass" else ["需要处理"],
            "",
            fidelity_checks=fidelity_checks,
            checklist_checks=[],
        )

    assert not (generation_dir / "qc.json").exists()


def test_standard_modern_run_accepts_exact_unique_runtime_checklist(tmp_path):
    generation_dir, analysis, constraints = _modern_ring_run(tmp_path)
    questions = build_qc_checklist(
        analysis.normalized_product_type,
        analysis.display_mode,
        constraints.must_keep,
    )
    checklist_checks = [
        {
            "id": "qc-" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:16],
            "question": question,
            "result": "pass",
            "notes": "已逐项核对",
        }
        for question in questions
    ]
    fidelity_checks = [
        {
            "name": item.name,
            "question": item.qc_question,
            "result": "pass",
            "notes": "与产品图一致",
        }
        for item in constraints.must_keep
    ]

    qc_path = write_qc_result(
        generation_dir,
        "pass",
        ["兼容摘要，不作为 checklist 证据"],
        [],
        "",
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
    )

    data = read_json(qc_path)
    assert data["checklist_checks"] == checklist_checks
    assert len(data["checklist_checks"]) == len(questions)


def test_standard_modern_run_rejects_conflicting_results_for_same_question(
    tmp_path,
):
    generation_dir, analysis, constraints = _modern_ring_run(tmp_path)
    questions = build_qc_checklist(
        analysis.normalized_product_type,
        analysis.display_mode,
        constraints.must_keep,
    )
    target_question = constraints.must_keep[0].qc_question
    checklist_checks = [
        {
            "id": qc_check_id(question),
            "question": question,
            "result": "rerun" if question == target_question else "pass",
            "notes": "已逐项核对",
        }
        for question in questions
    ]
    fidelity_checks = [
        {
            "name": item.name,
            "question": item.qc_question,
            "result": "pass",
            "notes": "与产品图一致",
        }
        for item in constraints.must_keep
    ]

    with pytest.raises(
        ValueError,
        match="fidelity_checks.*checklist_checks.*同一 question.*result 必须一致",
    ):
        write_qc_result(
            generation_dir,
            "rerun",
            ["其余检查通过"],
            ["需要重跑"],
            "",
            fidelity_checks=fidelity_checks,
            checklist_checks=checklist_checks,
        )

    assert not (generation_dir / "qc.json").exists()


def _modern_ring_run(tmp_path):
    run_root = tmp_path / "run"
    generation_dir = run_root / "generation" / "01"
    analysis_data = {
            "product_type": "戒指",
            "detected_product_type": "ring",
            "confirmed_product_type": "ring",
            "classification_confidence": "high",
            "classification_evidence": ["单枚戒指可见"],
            "classification_source": "auto_confirmed",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "wear_position": "左手无名指根部",
            "visible_appearance": "单枚银色开口戒，中央有透明主石",
            "color_family": ["银色", "透明"],
            "style_mood": "简洁",
            "composition": "手部近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": ["保持主石朝向"],
            "layer_count": 1,
            "length_category": None,
            "chain_or_strand_type": None,
            "has_pendant": False,
            "pendant_count": 0,
            "pendant_layer": None,
            "pendant_position": None,
            "pendant_orientation": None,
            "connection_structure": None,
            "symmetry": None,
            "occluded_parts": ["戒圈背面"],
            "uncertain_details": ["镶嵌背面结构"],
            "is_independent_multi_item": False,
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
        }
    analysis = ProductAnalysis.from_dict(analysis_data)
    constraints = build_product_fidelity_constraints(analysis)
    write_json(run_root / "analysis" / "product_analysis.json", analysis_data)
    payload = constraints.to_dict()
    payload["review_status"] = "confirmed"
    write_json(run_root / "analysis" / "product_fidelity_constraints.json", payload)
    return generation_dir, analysis, constraints


@pytest.mark.parametrize(
    "critical_failure",
    (
        "ring_count_mismatch",
        "finger_position_mismatch",
        "ring_structure_mismatch",
        "centerpiece_mismatch",
        "source_hand_leakage",
        "severe_intersection",
    ),
)
def test_ring_reject_critical_failures_require_reject(tmp_path, critical_failure):
    with pytest.raises(ValueError, match="必须标记为 reject"):
        write_qc_result(
            tmp_path,
            "rerun",
            ["已完成戒指检查"],
            ["戒指关键错误"],
            "需要拒绝",
            critical_failures=[critical_failure],
        )


@pytest.mark.parametrize(
    "critical_failure",
    ("hand_side_mismatch", "ring_contact_error", "finger_deformation"),
)
def test_ring_rerun_critical_failures_allow_rerun_but_not_pass(
    tmp_path, critical_failure
):
    path = write_qc_result(
        tmp_path / critical_failure,
        "rerun",
        ["已完成戒指检查"],
        ["需要重跑"],
        "修正后重跑",
        critical_failures=[critical_failure],
    )
    assert read_json(path)["status"] == "rerun"

    with pytest.raises(ValueError, match="不得标记为 pass"):
        write_qc_result(
            tmp_path / f"{critical_failure}-pass",
            "pass",
            ["检查通过"],
            [],
            "",
            critical_failures=[critical_failure],
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
    write_json(
        tmp_path / "run" / "analysis" / "product_analysis.json",
        _modern_pendant_analysis_data(),
    )

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
    analysis_data = _modern_pendant_analysis_data()
    write_json(
        tmp_path / "run" / "analysis" / "product_analysis.json",
        analysis_data,
    )
    analysis = ProductAnalysis.from_dict(analysis_data)
    parsed_constraints = ProductFidelityConstraints.from_dict(constraints)
    checklist_checks = [
        {
            "id": "qc-" + hashlib.sha256(question.encode("utf-8")).hexdigest()[:16],
            "question": question,
            "result": "pass",
            "notes": "已核对",
        }
        for question in build_qc_checklist(
            analysis.normalized_product_type,
            analysis.display_mode,
            parsed_constraints.must_keep,
        )
    ]

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
        checklist_checks=checklist_checks,
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


def _modern_pendant_analysis_data():
    return {
        "product_type": "带链吊坠",
        "detected_product_type": "pendant_necklace",
        "confirmed_product_type": "pendant_necklace",
        "classification_confidence": "high",
        "classification_evidence": ["完整链条连接主吊坠"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "wear_position": "颈部和锁骨",
        "visible_appearance": "单层链条连接中央主吊坠",
        "color_family": ["银色"],
        "style_mood": "精致",
        "composition": "胸前近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
        "layer_count": 1,
        "length_category": "collarbone",
        "chain_or_strand_type": "metal_chain",
        "has_pendant": True,
        "pendant_count": 1,
        "pendant_layer": 1,
        "pendant_position": "front_center",
        "pendant_orientation": "front_facing",
        "connection_structure": "metal_bail",
        "symmetry": "approximately_symmetric",
        "occluded_parts": ["后颈扣头"],
        "uncertain_details": ["扣头背面"],
        "is_independent_multi_item": False,
    }
