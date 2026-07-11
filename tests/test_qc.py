import pytest

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import MustKeepConstraint
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.qc import build_qc_checklist, write_qc_result
from jewelry_on_hand.run_paths import read_json


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
    path = write_qc_result(tmp_path, "pass", "\u65e0\u6c34\u5370", [404], None)

    assert read_json(path) == {
        "status": "pass",
        "passed": ["\u65e0\u6c34\u5370"],
        "failed": ["404"],
        "notes": "",
        "fidelity_checks": [],
    }


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
    assert "层数、上下顺序、长度等级和层间落差与产品图一致" in items
    assert "吊坠所属层、位置、朝向和连接关系与产品图一致" in items
    assert "链条没有穿肤、穿衣、穿发、悬空或陷入身体" in items
    assert "多层链没有错误交叉、合并或复制" in items
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
