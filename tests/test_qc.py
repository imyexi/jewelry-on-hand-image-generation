import pytest

from jewelry_on_hand.qc import write_qc_result
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
