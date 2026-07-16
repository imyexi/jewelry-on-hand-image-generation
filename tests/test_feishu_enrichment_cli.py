from __future__ import annotations

import json

import pytest

from jewelry_on_hand.cli import main
from jewelry_on_hand.feishu_reference_source import (
    AI_FIELD_NAMES,
    FeishuReferenceConfig,
    FeishuReferenceSync,
    InvalidEnrichmentError,
    ensure_enrichment_fields,
    import_enrichment_results,
)

from test_feishu_reference_source import FakeGateway, PNG_3X2, make_config, record


def valid_result(record_id="rec1", **overrides):
    fields = {
        "默认使用策略": "常规可优先使用",
        "风格分类": "清透自然光",
        "推荐使用方式": "近景手腕佩戴",
        "备注": "手腕完整，无明显裁切",
        "判断置信度": "高",
    }
    fields.update(overrides)
    return {"record_id": record_id, "fields": fields}


def test_import_enrichment_writes_only_empty_remote_fields_and_tracking(tmp_path):
    item = record()
    item["fields"]["风格分类"] = "人工风格"
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}], downloads={"file1": PNG_3X2}
    )
    config = make_config(tmp_path)
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "results.json"
    input_path.write_text(json.dumps({"records": [valid_result()]}, ensure_ascii=False), encoding="utf-8")

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 1
    assert result.remaining_pending == 0
    assert len(gateway.updates) == 1
    patch = gateway.updates[0][0][-1]
    assert "风格分类" not in patch
    assert patch["默认使用策略"] == "常规可优先使用"
    assert patch["AI补齐状态"] == "已完成"
    assert patch["AI补齐版本"] == "1"


def test_import_enrichment_rejects_unknown_record_and_missing_fields(tmp_path):
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}], downloads={"file1": PNG_3X2}
    )
    config = make_config(tmp_path)
    FeishuReferenceSync(config, gateway).sync()

    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({"records": [valid_result("missing")]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InvalidEnrichmentError, match="不在待补齐清单"):
        import_enrichment_results(config, unknown, gateway)

    incomplete = tmp_path / "incomplete.json"
    data = valid_result()
    del data["fields"][AI_FIELD_NAMES[0]]
    incomplete.write_text(json.dumps({"records": [data]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InvalidEnrichmentError, match=AI_FIELD_NAMES[0]):
        import_enrichment_results(config, incomplete, gateway)


def test_prepare_review_no_longer_requires_classification_argument(monkeypatch, tmp_path):
    product = tmp_path / "product.jpg"
    product.write_bytes(b"fake")
    analysis = tmp_path / "analysis.json"
    analysis.write_text("{}", encoding="utf-8")

    calls = []
    monkeypatch.setattr("jewelry_on_hand.cli.sync_and_load_reference_rows", lambda config: calls.append(config) or [])
    monkeypatch.setattr("jewelry_on_hand.cli.load_product_analysis", lambda path: object())
    monkeypatch.setattr("jewelry_on_hand.cli.build_product_fidelity_constraints", lambda product, **_kwargs: type("C", (), {"to_dict": lambda self: {}})())
    monkeypatch.setattr("jewelry_on_hand.cli.select_top_references", lambda product, rows, **_kwargs: ([], []))
    monkeypatch.setattr("jewelry_on_hand.cli.write_review_package", lambda *args: None)

    exit_code = main([
        "prepare-review",
        "--product-image", str(product),
        "--analysis-json", str(analysis),
        "--output-root", str(tmp_path / "runs"),
        "--run-id", "demo",
        "--reference-cache-root", str(tmp_path / "cache"),
        "--output-role", "hand_worn",
    ])

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0].cache_root == tmp_path / "cache"


def test_reference_sync_cli_reports_pending_and_returns_nonzero(monkeypatch, tmp_path, capsys):
    class Result:
        total_records = 3
        usable_records = 3
        pending_count = 2
        downloaded_count = 2
        pending_path = tmp_path / "pending.json"

    monkeypatch.setattr("jewelry_on_hand.cli.FeishuReferenceSync.sync", lambda self: Result())

    exit_code = main(["reference-sync", "--reference-cache-root", str(tmp_path / "cache")])

    assert exit_code == 2
    assert "2 条等待 AI 补齐" in capsys.readouterr().err


def test_ensure_enrichment_fields_creates_only_missing_fields(tmp_path):
    gateway = FakeGateway(
        pages=[],
        fields=[{"name": "默认使用策略"}, {"name": "AI补齐版本"}],
    )

    created = ensure_enrichment_fields(make_config(tmp_path), gateway)

    assert "默认使用策略" not in created
    assert "AI补齐版本" not in created
    assert set(created) == set(AI_FIELD_NAMES[1:]) | {"AI补齐状态"}
    status = next(
        item for item in gateway.created_fields if item["name"] == "AI补齐状态"
    )
    assert [option["name"] for option in status["options"]] == [
        "待补齐",
        "已完成",
        "需刷新",
    ]
