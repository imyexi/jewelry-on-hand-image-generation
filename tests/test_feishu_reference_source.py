from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from jewelry_on_hand.feishu_reference_source import (
    AI_FIELD_NAMES,
    ENRICHMENT_VERSION,
    FeishuReferenceConfig,
    FeishuReferenceError,
    FeishuReferenceSync,
    InvalidEnrichmentError,
    LarkCliGateway,
    OPTIONAL_REFERENCE_FIELD_NAMES,
    PendingEnrichmentError,
    RING_REQUIRED_FIELD_NAMES,
    audit_enrichment_readback,
    import_enrichment_results,
    load_cached_reference_rows,
)


def test_lark_cli_gateway_missing_executable_uses_chinese_error(monkeypatch):
    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.shutil.which", lambda _name: None
    )

    with pytest.raises(FeishuReferenceError, match="未找到 lark-cli"):
        LarkCliGateway()


def test_lark_cli_gateway_invalid_json_and_command_failure_use_chinese_errors(
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout=b"not-json", stderr=b"bad-json"),
            subprocess.CompletedProcess(
                [],
                1,
                stdout=json.dumps(
                    {"ok": False, "error": {"message": "权限不足"}},
                    ensure_ascii=False,
                ).encode("utf-8"),
                stderr=b"",
            ),
        ]
    )
    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(FeishuReferenceError, match="lark-cli 未返回有效 JSON"):
        gateway._run("base", "+table-list")
    with pytest.raises(FeishuReferenceError, match="飞书命令执行失败：权限不足"):
        gateway._run("base", "+table-list")


def test_lark_cli_gateway_get_record_parses_matrix_response(monkeypatch):
    gateway = LarkCliGateway("lark-cli")
    calls = []

    def fake_run(*args):
        calls.append(args)
        return {
            "data": {
                "fields": ["素材编号", "风格分类"],
                "record_id_list": ["rec1"],
                "data": [["RP000001", "人工风格"]],
            }
        }

    monkeypatch.setattr(gateway, "_run", fake_run)

    result = gateway.get_record("base-token", "table-id", "rec1")

    assert result == {
        "record_id": "rec1",
        "fields": {"素材编号": "RP000001", "风格分类": "人工风格"},
    }
    assert calls == [
        (
            "base",
            "+record-get",
            "--base-token",
            "base-token",
            "--table-id",
            "table-id",
            "--record-id",
            "rec1",
            "--format",
            "json",
            "--as",
            "user",
        )
    ]


PNG_3X2 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000030000000208020000001216f14d"
    "0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
)

LEGACY_ENRICHMENT_FIELDS = {
    "默认使用策略": "常规可优先使用",
    "风格分类": "清透自然光",
    "推荐使用方式": "近景佩戴或手持展示",
    "备注": "人物和产品展示区域完整",
    "判断置信度": "高",
}

GENERIC_REFERENCE_FIELDS = {
    "适用产品类型": "necklace,pendant_necklace",
    "适用展示模式": "worn,hand_held",
    "人物取景范围": "胸前半身",
    "可见身体区域": "颈部 锁骨 胸前 手部",
    "产品预计展示面积": "高",
    "颈部可见度": "高",
    "锁骨可见度": "高",
    "胸前可见度": "高",
    "手部可见度": "中",
    "衣领类型": "低领",
    "衣物遮挡风险": "低",
    "头发遮挡风险": "低",
    "姿势关键词": "正面站立 单手持链",
    "镜面关系": "无镜面",
    "原有首饰类型": "细项链",
    "裁切风险": "低",
    "左右手": "left",
    "可见手指": "thumb,index,middle,ring,little",
    "手部朝向": "back",
    "戒面可见度": "高",
    "手指分离度": "高",
    "手指遮挡风险": "低",
}

RING_REFERENCE_FIELDS = {
    "左右手": "left",
    "可见手指": "thumb,index,middle,ring,little",
    "手部朝向": "back",
    "戒面可见度": "高",
    "手指分离度": "高",
    "手指遮挡风险": "低",
}

LEGACY_SOURCE_FIELD_NAMES = (
    "素材编号",
    "素材图片",
    "关键词",
    "图片类型",
    "适用品类",
)


class FakeGateway:
    def __init__(
        self,
        pages,
        fields=None,
        downloads=None,
        before_get_record=None,
        before_update=None,
        after_update=None,
        update_failures=None,
    ):
        self.pages = list(pages)
        self.fields = fields or []
        self.downloads = downloads or {}
        self.before_get_record = before_get_record
        self.before_update = before_update
        self.after_update = after_update
        self.update_failures = set(update_failures or ())
        self.download_calls = []
        self.get_record_calls = []
        self.updates = []
        self.created_fields = []

    def resolve_source(self, config):
        return config.base_token or "base-token", config.table_id or "table-id"

    def list_fields(self, base_token, table_id):
        return self.fields

    def list_records(self, base_token, table_id, offset, limit):
        index = offset // limit
        return self.pages[index] if index < len(self.pages) else {"records": [], "has_more": False}

    def get_record(self, base_token, table_id, record_id):
        self.get_record_calls.append(record_id)
        if self.before_get_record:
            self.before_get_record(record_id)
        for page in self.pages:
            for item in page.get("records", []):
                if item.get("record_id") == record_id:
                    return item
        raise AssertionError(f"测试网关中不存在记录：{record_id}")

    def download_attachment(self, base_token, table_id, record_id, file_token, destination):
        self.download_calls.append((record_id, file_token))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.downloads[file_token])

    def create_field(self, base_token, table_id, field):
        self.created_fields.append(field)

    def update_record(self, base_token, table_id, record_id, fields):
        args = (base_token, table_id, record_id, fields)
        self.updates.append((args, {}))
        if self.before_update:
            self.before_update(record_id, fields)
        if record_id in self.update_failures:
            raise FeishuReferenceError(f"测试写入失败：{record_id}")
        for page in self.pages:
            for item in page.get("records", []):
                if item.get("record_id") == record_id:
                    item.setdefault("fields", {}).update(fields)
                    if self.after_update:
                        self.after_update(record_id, fields)
                    return
        raise AssertionError(f"测试网关中不存在记录：{record_id}")


def record(record_id="rec1", number="RP000001", token="file1", keywords="浅色 手腕"):
    return {
        "record_id": record_id,
        "fields": {
            "素材编号": number,
            "素材图片": [{"file_token": token, "name": f"{number}.png", "size": len(PNG_3X2)}],
            "关键词": keywords,
            "图片类型": ["手部佩戴图"],
            "适用品类": ["手串", "手链"],
            "默认使用策略": "",
            "风格分类": "",
            "推荐使用方式": "",
            "备注": "",
            "判断置信度": "",
            "AI补齐状态": "",
            "AI补齐版本": "",
        },
    }


def make_config(tmp_path):
    return FeishuReferenceConfig(
        wiki_url="https://my.feishu.cn/wiki/example",
        table_name="素材收录池",
        cache_root=tmp_path / "cache",
        page_size=2,
    )


def legacy_source_fingerprint(item):
    fields = item["fields"]
    data = {
        "record_id": item["record_id"],
        "fields": {
            name: fields.get(name)
            for name in LEGACY_SOURCE_FIELD_NAMES
            if name != "素材图片"
        },
        "attachment": fields["素材图片"][0],
    }
    encoded = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def rewrite_cache_as_legacy_format(config, item):
    manifest_path = config.cache_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_item = manifest["records"][0]
    fingerprint = legacy_source_fingerprint(item)
    manifest_item["source_fingerprint"] = fingerprint
    manifest_item["source_fields"] = {
        name: item["fields"].get(name) for name in LEGACY_SOURCE_FIELD_NAMES
    }
    manifest_item["resolved_enrichment"] = dict(LEGACY_ENRICHMENT_FIELDS)
    manifest_item["missing_ai_fields"] = []
    manifest_item["pending_enrichment"] = False
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    (config.cache_root / "enrichment.json").write_text(
        json.dumps({item["record_id"]: LEGACY_ENRICHMENT_FIELDS}, ensure_ascii=False),
        encoding="utf-8",
    )
    (config.cache_root / "pending_enrichment.json").write_text(
        json.dumps({"version": "1", "records": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return fingerprint


def test_sync_auto_paginates_and_writes_pending_manifest(tmp_path):
    gateway = FakeGateway(
        pages=[
            {"records": [record("rec1", "RP000001", "file1"), record("rec2", "RP000002", "file2")], "has_more": True},
            {"records": [record("rec3", "RP000003", "file3")], "has_more": False},
        ],
        downloads={"file1": PNG_3X2, "file2": PNG_3X2, "file3": PNG_3X2},
    )

    result = FeishuReferenceSync(make_config(tmp_path), gateway).sync()

    assert result.total_records == 3
    assert result.pending_count == 3
    assert len(gateway.download_calls) == 3
    pending = json.loads(result.pending_path.read_text(encoding="utf-8"))
    assert [item["record_id"] for item in pending["records"]] == ["rec1", "rec2", "rec3"]


def test_sync_is_incremental_and_source_change_marks_record_pending(tmp_path):
    config = make_config(tmp_path)
    first_gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}], downloads={"file1": PNG_3X2}
    )
    FeishuReferenceSync(config, first_gateway).sync()

    enriched = config.cache_root / "enrichment.json"
    enriched.write_text(json.dumps({"rec1": {name: "已填" for name in AI_FIELD_NAMES}}, ensure_ascii=False), encoding="utf-8")
    second_gateway = FakeGateway(pages=[{"records": [record()], "has_more": False}], downloads={})
    unchanged = FeishuReferenceSync(config, second_gateway).sync()
    assert unchanged.pending_count == 0
    assert second_gateway.download_calls == []

    changed_gateway = FakeGateway(
        pages=[{"records": [record(keywords="深色 闪光")], "has_more": False}], downloads={}
    )
    changed = FeishuReferenceSync(config, changed_gateway).sync()
    assert changed.pending_count == 1
    assert changed_gateway.download_calls == []


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ({"AI补齐状态": "需刷新"}, "AI补齐状态=需刷新"),
        ({"AI补齐版本": "2"}, "AI补齐版本不匹配"),
        ({"默认使用策略": ""}, "远端已清空已写回字段：默认使用策略"),
    ],
)
def test_sync_invalidates_local_enrichment_for_remote_refresh_version_or_clear(
    tmp_path,
    mutation,
    expected_reason,
):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(LEGACY_ENRICHMENT_FIELDS)
    item["fields"].update({"AI补齐状态": "已完成", "AI补齐版本": ENRICHMENT_VERSION})
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    item["fields"].update(mutation)

    result = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()

    assert result.pending_count == 1
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest_item = manifest["records"][0]
    assert expected_reason in manifest_item["enrichment_invalidation_reasons"]
    local = json.loads(
        (config.cache_root / "enrichment.json").read_text(encoding="utf-8")
    )
    if "默认使用策略" in mutation:
        assert local["rec1"]["默认使用策略"] == ""


def test_sync_silently_migrates_unchanged_legacy_fingerprint(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update({name: None for name in OPTIONAL_REFERENCE_FIELD_NAMES})
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    legacy_fingerprint = rewrite_cache_as_legacy_format(config, item)

    legacy_manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert set(legacy_manifest["records"][0]["source_fields"]) == set(
        LEGACY_SOURCE_FIELD_NAMES
    )

    first_gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}]
    )
    first = FeishuReferenceSync(config, first_gateway).sync()

    assert first.pending_count == 0
    assert first_gateway.download_calls == []
    rows = load_cached_reference_rows(config.cache_root)
    assert len(rows) == 1
    assert rows[0].default_strategy == LEGACY_ENRICHMENT_FIELDS["默认使用策略"]

    upgraded_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    upgraded_record = upgraded_manifest["records"][0]
    upgraded_fingerprint = upgraded_record["source_fingerprint"]
    assert upgraded_fingerprint != legacy_fingerprint
    assert all(
        name in upgraded_record["source_fields"]
        and upgraded_record["source_fields"][name] is None
        for name in OPTIONAL_REFERENCE_FIELD_NAMES
    )

    second_gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}]
    )
    second = FeishuReferenceSync(config, second_gateway).sync()
    second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))

    assert second.pending_count == 0
    assert second_gateway.download_calls == []
    assert second_manifest["records"][0]["source_fingerprint"] == upgraded_fingerprint


def test_sync_does_not_apply_legacy_fingerprint_compatibility_to_new_field_value(
    tmp_path,
):
    config = make_config(tmp_path)
    legacy_item = record()
    legacy_item["fields"].update(
        {name: None for name in OPTIONAL_REFERENCE_FIELD_NAMES}
    )
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [legacy_item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    legacy_fingerprint = rewrite_cache_as_legacy_format(config, legacy_item)
    changed_item = record()
    changed_item["fields"].update(
        {name: None for name in OPTIONAL_REFERENCE_FIELD_NAMES}
    )
    changed_item["fields"]["镜面关系"] = "无镜面"

    result = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [changed_item], "has_more": False}]),
    ).sync()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert result.pending_count == 1
    assert manifest["records"][0]["source_fingerprint"] != legacy_fingerprint
    assert manifest["records"][0]["resolved_enrichment"]["默认使用策略"] == ""


def test_sync_fingerprint_detects_generic_reference_field_change(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(GENERIC_REFERENCE_FIELDS)
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    (config.cache_root / "enrichment.json").write_text(
        json.dumps({"rec1": LEGACY_ENRICHMENT_FIELDS}, ensure_ascii=False),
        encoding="utf-8",
    )

    unchanged = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()
    changed_item = record()
    changed_item["fields"].update(GENERIC_REFERENCE_FIELDS)
    changed_item["fields"]["镜面关系"] = "镜中自拍"
    changed = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [changed_item], "has_more": False}]),
    ).sync()

    assert unchanged.pending_count == 0
    assert changed.pending_count == 1


def test_sync_uses_first_attachment_and_records_multiple_attachment_warning(tmp_path):
    item = record()
    item["fields"]["素材图片"].append({"file_token": "file2", "name": "second.png", "size": 10})
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}], downloads={"file1": PNG_3X2}
    )

    result = FeishuReferenceSync(make_config(tmp_path), gateway).sync()

    assert gateway.download_calls == [("rec1", "file1")]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert "仅使用第一张附件" in manifest["records"][0]["warnings"][0]


def test_cached_rows_map_existing_fields_and_image_metadata(tmp_path):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}], downloads={"file1": PNG_3X2}
    )
    FeishuReferenceSync(config, gateway).sync()
    (config.cache_root / "enrichment.json").write_text(
        json.dumps(
            {"rec1": {
                "默认使用策略": "常规可优先使用",
                "风格分类": "清透自然光",
                "推荐使用方式": "近景手腕佩戴",
                "备注": "手腕完整",
                "判断置信度": "高",
            }},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    FeishuReferenceSync(config, FakeGateway(pages=[{"records": [record()], "has_more": False}])).sync()

    rows = load_cached_reference_rows(config.cache_root)

    assert len(rows) == 1
    row = rows[0]
    assert row.index == 1
    assert row.width == 3
    assert row.height == 2
    assert row.purpose_category == "手部佩戴图"
    assert row.bracelet_applicability == "是：适用于手串、手链"
    assert row.scene_keywords == "浅色 手腕"
    assert row.jewelry_type == "手串、手链"
    assert row.applicable_product_types == "手串、手链"
    assert row.file_exists is True


def test_cached_rows_map_generic_fields_from_manifest(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(GENERIC_REFERENCE_FIELDS)
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    (config.cache_root / "enrichment.json").write_text(
        json.dumps({"rec1": LEGACY_ENRICHMENT_FIELDS}, ensure_ascii=False),
        encoding="utf-8",
    )
    result = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    source_fields = manifest["records"][0]["source_fields"]
    assert source_fields["人物取景范围"] == "胸前半身"
    assert source_fields["姿势关键词"] == "正面站立 单手持链"
    assert source_fields["镜面关系"] == "无镜面"
    assert source_fields["左右手"] == "left"
    assert source_fields["可见手指"] == "thumb,index,middle,ring,little"

    row = load_cached_reference_rows(config.cache_root)[0]
    assert row.applicable_product_types == "necklace,pendant_necklace"
    assert row.applicable_display_modes == "worn,hand_held"
    assert row.framing == "胸前半身"
    assert row.visible_body_regions == "颈部 锁骨 胸前 手部"
    assert row.product_visibility == "高"
    assert row.neck_visibility == "高"
    assert row.collarbone_visibility == "高"
    assert row.chest_visibility == "高"
    assert row.hand_visibility == "中"
    assert row.collar_type == "低领"
    assert row.clothing_occlusion_risk == "低"
    assert row.hair_occlusion_risk == "低"
    assert row.pose_keywords == "正面站立 单手持链"
    assert row.mirror_relation == "无镜面"
    assert row.existing_jewelry == "细项链"
    assert row.crop_risk == "低"
    assert row.hand_side == "left"
    assert row.visible_fingers == "thumb,index,middle,ring,little"
    assert row.hand_orientation == "back"
    assert row.ring_face_visibility == "高"
    assert row.finger_separation == "高"
    assert row.finger_occlusion_risk == "低"


def test_cached_row_without_product_annotation_does_not_default_to_necklace(tmp_path):
    config = make_config(tmp_path)
    item = record()
    del item["fields"]["适用品类"]
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    (config.cache_root / "enrichment.json").write_text(
        json.dumps({"rec1": LEGACY_ENRICHMENT_FIELDS}, ensure_ascii=False),
        encoding="utf-8",
    )
    FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()

    row = load_cached_reference_rows(config.cache_root)[0]

    assert row.applicable_product_types == ""
    assert row.applicable_display_modes == ""
    assert row.neck_visibility == ""


def test_import_accepts_optional_generic_fields_and_keeps_next_sync_incremental(tmp_path):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "rec1",
                        "fields": LEGACY_ENRICHMENT_FIELDS | GENERIC_REFERENCE_FIELDS,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import_enrichment_results(config, input_path, gateway)

    patch = gateway.updates[0][0][-1]
    assert patch["适用产品类型"] == "necklace,pendant_necklace"
    assert patch["姿势关键词"] == "正面站立 单手持链"
    assert patch["镜面关系"] == "无镜面"
    assert patch["左右手"] == "left"
    assert patch["手指遮挡风险"] == "低"
    row = load_cached_reference_rows(config.cache_root)[0]
    assert row.applicable_product_types == "necklace,pendant_necklace"
    assert row.pose_keywords == "正面站立 单手持链"
    assert row.hand_side == "left"

    updated_item = record()
    updated_item["fields"].update(GENERIC_REFERENCE_FIELDS)
    next_sync = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [updated_item], "has_more": False}]),
    ).sync()
    assert next_sync.pending_count == 0


def test_import_rereads_paginated_remote_records_and_preserves_concurrent_manual_value(
    tmp_path,
):
    config = make_config(tmp_path)
    third = record("rec3", "RP000003", "file3")
    gateway = FakeGateway(
        pages=[
            {
                "records": [
                    record("rec1", "RP000001", "file1"),
                    record("rec2", "RP000002", "file2"),
                ],
                "has_more": True,
            },
            {"records": [third], "has_more": False},
        ],
        downloads={"file1": PNG_3X2, "file2": PNG_3X2, "file3": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    third["fields"]["风格分类"] = "同步后人工风格"
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "rec3",
                        "fields": LEGACY_ENRICHMENT_FIELDS | {"风格分类": "AI 风格"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.remaining_pending == 2
    patch = gateway.updates[0][0][-1]
    assert "风格分类" not in patch
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_item = next(
        item for item in manifest["records"] if item["record_id"] == "rec3"
    )
    assert manifest_item["resolved_enrichment"]["风格分类"] == "同步后人工风格"
    enrichment = json.loads(
        (config.cache_root / "enrichment.json").read_text(encoding="utf-8")
    )
    assert enrichment["rec3"]["风格分类"] == "同步后人工风格"


def test_import_get_record_preserves_manual_value_added_after_full_reread(tmp_path):
    config = make_config(tmp_path)
    item = record()

    def add_manual_value(_record_id):
        item["fields"]["风格分类"] = "写回前人工风格"

    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
        before_get_record=add_manual_value,
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "rec1",
                        "fields": LEGACY_ENRICHMENT_FIELDS | {"风格分类": "AI 风格"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import_enrichment_results(config, input_path, gateway)

    assert gateway.get_record_calls == ["rec1", "rec1", "rec1"]
    patch = gateway.updates[0][0][-1]
    assert "风格分类" not in patch
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert (
        manifest["records"][0]["resolved_enrichment"]["风格分类"]
        == "写回前人工风格"
    )
    enrichment = json.loads(
        (config.cache_root / "enrichment.json").read_text(encoding="utf-8")
    )
    assert enrichment["rec1"]["风格分类"] == "写回前人工风格"


def test_readback_audit_marks_completed_records_verified(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(LEGACY_ENRICHMENT_FIELDS)
    item["fields"]["AI补齐状态"] = "已完成"
    item["fields"]["AI补齐版本"] = ENRICHMENT_VERSION
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}], downloads={"file1": PNG_3X2}
    )
    FeishuReferenceSync(config, gateway).sync()
    FeishuReferenceSync(config, gateway).sync()

    result = audit_enrichment_readback(config, gateway)

    assert result.verified_records == 1
    assert result.failed_records == 0
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["audit_kind"] == "post_sync_readback"
    assert audit["records"] == [
        {
            "record_id": "rec1",
            "status": "verified",
            "patch": {},
            "details": {},
            "error": "",
        }
    ]


def test_import_immediate_prewrite_reread_preserves_manual_value(tmp_path):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def add_manual_value_on_second_get(record_id):
        if gateway.get_record_calls.count(record_id) == 2:
            item["fields"]["风格分类"] = "紧邻写入前人工风格"

    gateway.before_get_record = add_manual_value_on_second_get
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "rec1",
                        "fields": LEGACY_ENRICHMENT_FIELDS | {"风格分类": "AI 风格"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 1
    assert gateway.get_record_calls == ["rec1", "rec1", "rec1"]
    patch = gateway.updates[0][0][-1]
    assert "风格分类" not in patch
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "verified"


def test_import_keeps_failed_record_pending_and_audits_partial_success(tmp_path):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[
            {
                "records": [
                    record("rec1", "RP000001", "file1"),
                    record("rec2", "RP000002", "file2"),
                ],
                "has_more": False,
            }
        ],
        downloads={"file1": PNG_3X2, "file2": PNG_3X2},
        update_failures={"rec2"},
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS},
                    {"record_id": "rec2", "fields": LEGACY_ENRICHMENT_FIELDS},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 1
    assert result.remaining_pending == 1
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    by_id = {item["record_id"]: item for item in manifest["records"]}
    assert by_id["rec1"]["pending_enrichment"] is False
    assert by_id["rec2"]["pending_enrichment"] is True
    local = json.loads(
        (config.cache_root / "enrichment.json").read_text(encoding="utf-8")
    )
    assert local["rec1"]["默认使用策略"] == LEGACY_ENRICHMENT_FIELDS["默认使用策略"]
    assert local["rec2"]["默认使用策略"] == ""
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["status"] for item in audit["records"]] == ["verified", "failed"]
    assert audit["records"][1]["error"] == "测试写入失败：rec2"
    assert "revision" in audit["residual_cas_risk"]


def test_import_keeps_postwrite_mismatch_pending_and_audits_conflict(tmp_path):
    config = make_config(tmp_path)
    item = record()

    def overwrite_after_update(_record_id, _fields):
        item["fields"]["默认使用策略"] = "写后并发值"

    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
        after_update=overwrite_after_update,
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 0
    assert result.remaining_pending == 1
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["records"][0]["pending_enrichment"] is True
    assert manifest["records"][0]["resolved_enrichment"]["默认使用策略"] == ""
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert audit["records"][0]["details"]["默认使用策略"] == {
        "expected": LEGACY_ENRICHMENT_FIELDS["默认使用策略"],
        "actual": "写后并发值",
    }


@pytest.mark.parametrize(
    ("failure_stage", "failure_kind", "expected_error"),
    [
        (1, "read", "测试逐条读取失败"),
        (2, "read", "测试逐条读取失败"),
        (1, "source", "源字段已变化"),
        (2, "ring", "戒指佩戴候选缺少必需字段"),
    ],
)
def test_import_isolates_per_record_read_and_validation_failures_and_continues(
    tmp_path,
    failure_stage,
    failure_kind,
    expected_error,
):
    config = make_config(tmp_path)
    first = record("rec1", "RP000001", "file1")
    second = record("rec2", "RP000002", "file2")
    third = record("rec3", "RP000003", "file3")
    if failure_kind == "ring":
        second["fields"].update(
            LEGACY_ENRICHMENT_FIELDS
            | RING_REFERENCE_FIELDS
            | {"适用产品类型": "ring", "适用展示模式": "worn"}
        )
    gateway = FakeGateway(
        pages=[
            {
                "records": [first, second, third],
                "has_more": False,
            }
        ],
        downloads={"file1": PNG_3X2, "file2": PNG_3X2, "file3": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def fail_second_record(record_id):
        if record_id != "rec2":
            return
        call_number = gateway.get_record_calls.count(record_id)
        if call_number != failure_stage:
            return
        if failure_kind == "read":
            raise FeishuReferenceError("测试逐条读取失败：rec2")
        if failure_kind == "source":
            second["fields"]["关键词"] = "并发修改源字段"
        if failure_kind == "ring":
            second["fields"]["手指遮挡风险"] = ""

    gateway.before_get_record = fail_second_record
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": record_id, "fields": LEGACY_ENRICHMENT_FIELDS}
                    for record_id in ("rec1", "rec2", "rec3")
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 2
    assert result.remaining_pending == 1
    assert gateway.get_record_calls.count("rec3") == 3
    assert first["fields"]["AI补齐状态"] == "已完成"
    assert third["fields"]["AI补齐状态"] == "已完成"
    assert second["fields"]["AI补齐状态"] != "已完成"
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    by_id = {item["record_id"]: item for item in manifest["records"]}
    assert by_id["rec1"]["pending_enrichment"] is False
    assert by_id["rec2"]["pending_enrichment"] is True
    assert by_id["rec3"]["pending_enrichment"] is False
    local = json.loads(
        (config.cache_root / "enrichment.json").read_text(encoding="utf-8")
    )
    assert local["rec1"]["默认使用策略"] == LEGACY_ENRICHMENT_FIELDS["默认使用策略"]
    expected_second_value = (
        LEGACY_ENRICHMENT_FIELDS["默认使用策略"]
        if failure_kind == "ring"
        else ""
    )
    assert local["rec2"]["默认使用策略"] == expected_second_value
    assert local["rec3"]["默认使用策略"] == LEGACY_ENRICHMENT_FIELDS["默认使用策略"]
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["status"] for item in audit["records"]] == [
        "verified",
        "failed",
        "verified",
    ]
    assert expected_error in audit["records"][1]["error"]


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("关键词", "同步后修改的关键词"),
        ("适用品类", ["戒指"]),
        (
            "素材图片",
            [
                {
                    "file_token": "file2",
                    "name": "replacement.png",
                    "size": len(PNG_3X2),
                }
            ],
        ),
    ],
)
def test_import_rejects_stale_non_ai_source_without_writing_or_changing_cache(
    tmp_path,
    field_name,
    changed_value,
):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    manifest_path = config.cache_root / "manifest.json"
    pending_path = config.cache_root / "pending_enrichment.json"
    manifest_before = manifest_path.read_bytes()
    pending_before = pending_path.read_bytes()
    item["fields"][field_name] = changed_value
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(InvalidEnrichmentError, match="源字段已变化"):
        import_enrichment_results(config, input_path, gateway)

    assert gateway.updates == []
    assert manifest_path.read_bytes() == manifest_before
    assert pending_path.read_bytes() == pending_before


def test_import_rejects_ring_worn_candidate_missing_six_required_fields(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(
        {"适用品类": ["戒指"], "适用展示模式": "worn"}
    )
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(InvalidEnrichmentError, match="戒指佩戴候选缺少必需字段"):
        import_enrichment_results(config, input_path, gateway)

    assert gateway.updates == []


def test_import_accepts_ring_fields_merged_from_remote_and_submission(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(
        {
            "适用产品类型": "ring",
            "左右手": "left",
            "可见手指": "thumb,index,middle,ring,little",
        }
    )
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    submitted_ring_fields = {
        "适用展示模式": "worn",
        "手部朝向": "back",
        "戒面可见度": "高",
        "手指分离度": "高",
        "手指遮挡风险": "低",
    }
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "rec1",
                        "fields": LEGACY_ENRICHMENT_FIELDS | submitted_ring_fields,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.remaining_pending == 0
    patch = gateway.updates[0][0][-1]
    assert "左右手" not in patch
    assert "可见手指" not in patch
    assert patch["适用展示模式"] == "worn"
    enrichment = json.loads(
        (config.cache_root / "enrichment.json").read_text(encoding="utf-8")
    )
    assert enrichment["rec1"]["左右手"] == "left"
    assert enrichment["rec1"]["手部朝向"] == "back"


def test_import_get_record_keeps_ring_worn_pending_when_it_becomes_incomplete(
    tmp_path,
):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(
        LEGACY_ENRICHMENT_FIELDS
        | RING_REFERENCE_FIELDS
        | {"适用产品类型": "ring", "适用展示模式": "worn"}
    )

    def remove_required_field(_record_id):
        item["fields"]["手指遮挡风险"] = ""

    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
        before_get_record=remove_required_field,
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert gateway.get_record_calls == ["rec1"]
    assert gateway.updates == []
    assert result.updated_records == 0
    assert result.remaining_pending == 1
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "failed"
    assert "戒指佩戴候选缺少必需字段" in audit["records"][0]["error"]


def test_sync_keeps_ring_worn_candidate_pending_until_six_fields_are_complete(
    tmp_path,
):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(
        LEGACY_ENRICHMENT_FIELDS
        | {"适用产品类型": "ring", "适用展示模式": "worn"}
    )
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()

    result = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()

    assert result.pending_count == 1
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["records"][0]["missing_ai_fields"] == list(
        RING_REQUIRED_FIELD_NAMES
    )


def test_sync_legacy_ring_label_without_worn_does_not_require_six_fields(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(LEGACY_ENRICHMENT_FIELDS | {"适用品类": ["戒指"]})
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()

    result = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()

    assert result.pending_count == 0
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["records"][0]["missing_ai_fields"] == []


@pytest.mark.parametrize(
    ("product_types", "display_modes", "expected_pending"),
    [
        ("非戒指", "worn", 0),
        ("ring", "不适合佩戴", 0),
        ("指环", "真人佩戴", 1),
    ],
)
def test_sync_ring_worn_candidate_uses_exact_controlled_aliases(
    tmp_path,
    product_types,
    display_modes,
    expected_pending,
):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(
        LEGACY_ENRICHMENT_FIELDS
        | {
            "适用产品类型": product_types,
            "适用展示模式": display_modes,
        }
    )
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()

    result = FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [item], "has_more": False}]),
    ).sync()

    assert result.pending_count == expected_pending


def test_missing_attachment_is_not_a_candidate_and_is_reported(tmp_path):
    item = record()
    item["fields"]["素材图片"] = []
    gateway = FakeGateway(pages=[{"records": [item], "has_more": False}])

    result = FeishuReferenceSync(make_config(tmp_path), gateway).sync()

    assert result.usable_records == 0
    issues = json.loads(result.issues_path.read_text(encoding="utf-8"))
    assert issues["records"][0]["record_id"] == "rec1"
    assert "素材图片" in issues["records"][0]["reason"]


def test_loading_cache_blocks_when_pending_records_exist(tmp_path):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}], downloads={"file1": PNG_3X2}
    )
    FeishuReferenceSync(config, gateway).sync()

    with pytest.raises(PendingEnrichmentError, match="1 条素材等待 AI 补齐"):
        load_cached_reference_rows(config.cache_root)
