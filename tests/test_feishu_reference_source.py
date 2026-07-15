from __future__ import annotations

import hashlib
import json
import os
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
    build_reference_source_snapshot,
    import_enrichment_results,
    load_cached_reference_rows,
    sync_and_load_reference_rows,
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
    with pytest.raises(FeishuReferenceError, match="飞书命令执行失败.*权限不足"):
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


@pytest.mark.parametrize(
    "failure",
    [FileNotFoundError("命令不存在"), PermissionError("拒绝执行")],
)
def test_lark_cli_gateway_wraps_subprocess_os_errors_in_actionable_chinese(
    monkeypatch,
    failure,
):
    gateway = LarkCliGateway("lark-cli")
    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(FeishuReferenceError, match="无法启动 lark-cli.*安装路径|执行权限"):
        gateway._run("base", "+table-list")


def test_lark_cli_gateway_wraps_invalid_utf8_output_in_actionable_chinese(
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, stdout=b"\xff\xfe", stderr=b""
        ),
    )

    with pytest.raises(FeishuReferenceError, match="不是有效 UTF-8"):
        gateway._run("base", "+table-list")


def test_lark_cli_gateway_nonzero_plain_text_is_command_failure_not_json_error(
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [],
            7,
            stdout=b"not-json",
            stderr="权限或网络失败".encode("utf-8"),
        ),
    )

    with pytest.raises(FeishuReferenceError, match="执行失败.*退出码 7.*权限或网络失败"):
        gateway._run("base", "+table-list")


def test_lark_cli_gateway_record_upsert_adapter_builds_expected_command(monkeypatch):
    gateway = LarkCliGateway("lark-cli")
    calls = []
    monkeypatch.setattr(
        gateway,
        "_run",
        lambda *args: calls.append(args) or {"ok": True, "data": {}},
    )

    gateway.update_record(
        "base-token",
        "table-id",
        "rec1",
        {"风格分类": "人工风格"},
    )

    assert calls[0][:8] == (
        "base",
        "+record-upsert",
        "--base-token",
        "base-token",
        "--table-id",
        "table-id",
        "--record-id",
        "rec1",
    )
    assert json.loads(calls[0][calls[0].index("--json") + 1]) == {
        "风格分类": "人工风格"
    }


def test_lark_cli_gateway_field_create_adapter_builds_expected_command(monkeypatch):
    gateway = LarkCliGateway("lark-cli")
    calls = []
    monkeypatch.setattr(
        gateway,
        "_run",
        lambda *args: calls.append(args) or {"ok": True, "data": {}},
    )
    definition = {"name": "AI补齐版本", "type": "text"}

    gateway.create_field("base-token", "table-id", definition)

    assert calls[0][:6] == (
        "base",
        "+field-create",
        "--base-token",
        "base-token",
        "--table-id",
        "table-id",
    )
    assert json.loads(calls[0][calls[0].index("--json") + 1]) == definition


def test_lark_cli_gateway_attachment_failure_cleans_temporary_and_preserves_target(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "reference.png"
    destination.write_bytes(b"old")

    def fail_after_partial_download(*args):
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"partial")
        raise FeishuReferenceError("测试附件下载失败")

    monkeypatch.setattr(gateway, "_run", fail_after_partial_download)

    with pytest.raises(FeishuReferenceError, match="测试附件下载失败"):
        gateway.download_attachment(
            "base-token", "table-id", "rec1", "file1", destination
        )

    assert destination.read_bytes() == b"old"
    assert list(tmp_path.glob("*.download.tmp")) == []


def test_lark_cli_gateway_attachment_success_atomically_replaces_target(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "reference.png"
    destination.write_bytes(b"old")

    def complete_download(*args):
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"new")
        return {"ok": True, "data": {}}

    monkeypatch.setattr(gateway, "_run", complete_download)

    gateway.download_attachment(
        "base-token", "table-id", "rec1", "file1", destination
    )

    assert destination.read_bytes() == b"new"
    assert list(tmp_path.glob("*.download.tmp")) == []


def test_lark_cli_gateway_attachment_wraps_destination_directory_failure(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "nested" / "reference.png"
    real_mkdir = Path.mkdir

    def fail_destination_mkdir(path, *args, **kwargs):
        if path == destination.parent:
            raise OSError("测试目录不可写")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_destination_mkdir)

    with pytest.raises(FeishuReferenceError, match="创建飞书附件目录失败") as exc_info:
        gateway.download_attachment(
            "base-token", "table-id", "rec1", "file1", destination
        )

    assert isinstance(exc_info.value.__cause__, OSError)


def test_lark_cli_gateway_attachment_wraps_initial_temporary_cleanup_failure(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "reference.png"
    temporary = destination.with_name(destination.name + ".download.tmp")
    real_unlink = Path.unlink

    def fail_initial_unlink(path, *, missing_ok=False):
        if path == temporary:
            raise OSError("测试旧临时文件不可删除")
        return real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_initial_unlink)
    monkeypatch.setattr(
        gateway,
        "_run",
        lambda *args: pytest.fail("首次临时文件清理失败后不应开始下载"),
    )

    with pytest.raises(FeishuReferenceError, match="清理旧的飞书附件临时文件失败") as exc_info:
        gateway.download_attachment(
            "base-token", "table-id", "rec1", "file1", destination
        )

    assert isinstance(exc_info.value.__cause__, OSError)


def test_lark_cli_gateway_attachment_preserves_download_error_when_cleanup_fails(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "reference.png"
    destination.write_bytes(b"old")
    temporary = destination.with_name(destination.name + ".download.tmp")
    real_unlink = Path.unlink
    temporary_unlinks = 0

    def fail_final_unlink(path, *, missing_ok=False):
        nonlocal temporary_unlinks
        if path == temporary:
            temporary_unlinks += 1
            if temporary_unlinks == 2:
                raise OSError("测试 finally 清理失败")
        return real_unlink(path, missing_ok=missing_ok)

    def fail_after_partial_download(*args):
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"partial")
        raise FeishuReferenceError("测试附件下载失败")

    monkeypatch.setattr(Path, "unlink", fail_final_unlink)
    monkeypatch.setattr(gateway, "_run", fail_after_partial_download)

    with pytest.raises(FeishuReferenceError, match="测试附件下载失败") as exc_info:
        gateway.download_attachment(
            "base-token", "table-id", "rec1", "file1", destination
        )

    assert destination.read_bytes() == b"old"
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "finally 清理失败" in str(exc_info.value.__cause__)


def test_lark_cli_gateway_attachment_wraps_cleanup_failure_after_success(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "reference.png"
    destination.write_bytes(b"old")
    temporary = destination.with_name(destination.name + ".download.tmp")
    real_unlink = Path.unlink
    temporary_unlinks = 0

    def fail_final_unlink(path, *, missing_ok=False):
        nonlocal temporary_unlinks
        if path == temporary:
            temporary_unlinks += 1
            if temporary_unlinks == 2:
                raise OSError("测试成功后的 finally 清理失败")
        return real_unlink(path, missing_ok=missing_ok)

    def complete_download(*args):
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"new")
        return {"ok": True, "data": {}}

    monkeypatch.setattr(Path, "unlink", fail_final_unlink)
    monkeypatch.setattr(gateway, "_run", complete_download)

    with pytest.raises(FeishuReferenceError, match="清理飞书附件临时文件失败") as exc_info:
        gateway.download_attachment(
            "base-token", "table-id", "rec1", "file1", destination
        )

    assert destination.read_bytes() == b"new"
    assert isinstance(exc_info.value.__cause__, OSError)


def test_lark_cli_gateway_attachment_unexpected_download_error_still_cleans_temporary(
    tmp_path,
    monkeypatch,
):
    gateway = LarkCliGateway("lark-cli")
    destination = tmp_path / "reference.png"
    temporary = destination.with_name(destination.name + ".download.tmp")

    def fail_unexpectedly_after_partial_download(*args):
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"partial")
        raise RuntimeError("测试意外下载异常")

    monkeypatch.setattr(gateway, "_run", fail_unexpectedly_after_partial_download)

    with pytest.raises(RuntimeError, match="测试意外下载异常"):
        gateway.download_attachment(
            "base-token", "table-id", "rec1", "file1", destination
        )

    assert not temporary.exists()


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
        self.atomic_attempts = []
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

    def update_record_if_fields_empty(
        self,
        base_token,
        table_id,
        record_id,
        fields,
        required_empty_fields,
        expected_fields=None,
    ):
        expected_fields = dict(expected_fields or {})
        self.atomic_attempts.append(
            (
                base_token,
                table_id,
                record_id,
                dict(fields),
                tuple(required_empty_fields),
                expected_fields,
            )
        )
        if self.before_update:
            self.before_update(record_id, fields)
        if record_id in self.update_failures:
            raise FeishuReferenceError(f"测试写入失败：{record_id}")
        for page in self.pages:
            for item in page.get("records", []):
                if item.get("record_id") != record_id:
                    continue
                current_fields = item.setdefault("fields", {})
                conflicts = {
                    name: str(current_fields.get(name) or "").strip()
                    for name in required_empty_fields
                    if str(current_fields.get(name) or "").strip()
                }
                conflicts.update(
                    {
                        name: current_fields.get(name)
                        for name, expected in expected_fields.items()
                        if current_fields.get(name) != expected
                    }
                )
                if conflicts:
                    return {
                        "updated": False,
                        "record": item,
                        "conflicts": conflicts,
                    }
                current_fields.update(fields)
                self.updates.append(
                    ((base_token, table_id, record_id, dict(fields)), {})
                )
                if self.after_update:
                    self.after_update(record_id, fields)
                return {"updated": True, "record": item, "conflicts": {}}
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


def write_enrichment_input(tmp_path, records):
    input_path = tmp_path / "enrichment-results.json"
    input_path.write_text(
        json.dumps({"records": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return input_path


def make_import_transaction_fixture(config):
    root = config.cache_root
    transaction_dir = root / ".enrichment-import-transaction"
    transaction_dir.mkdir(parents=True, exist_ok=True)
    targets = (
        "manifest.json",
        "enrichment.json",
        "pending_enrichment.json",
        "enrichment-import-audit.json",
    )
    documents = {
        name: (root / name).read_bytes()
        if (root / name).is_file()
        else json.dumps(
            {
                "version": 1,
                "atomic_write_contract": "测试原子条件写",
                "records": [],
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        for name in targets
    }
    entries = []
    for name in targets:
        staged = transaction_dir / f"{name}.new"
        staged.write_bytes(documents[name])
        entries.append(
            {
                "target": name,
                "staged": staged.name,
                "sha256": hashlib.sha256(documents[name]).hexdigest(),
            }
        )
    journal = {"version": 1, "phase": "prepared", "files": entries}
    return transaction_dir, root / ".enrichment-import-transaction.json", journal


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


def test_sync_attachment_cache_name_uses_record_and_token_digest_to_avoid_collisions(
    tmp_path,
):
    config = make_config(tmp_path)
    first = record("rec1", "A/B", "token-one")
    second = record("rec2", "A?B", "token-two")
    gateway = FakeGateway(
        pages=[{"records": [first, second], "has_more": False}],
        downloads={"token-one": PNG_3X2, "token-two": PNG_3X2},
    )

    FeishuReferenceSync(config, gateway).sync()

    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    paths = [Path(item["image_path"]) for item in manifest["records"]]
    assert paths[0] != paths[1]
    assert all(path.is_file() for path in paths)
    for path, record_id, token in zip(
        paths,
        ("rec1", "rec2"),
        ("token-one", "token-two"),
        strict=True,
    ):
        expected_digest = hashlib.sha256(
            f"{record_id}\0{token}".encode("utf-8")
        ).hexdigest()[:12]
        assert expected_digest in path.stem


@pytest.mark.parametrize(
    "reserved_name",
    ["CON", "prn", "AUX", "nul", "COM1", "com9", "LPT1", "lpt9"],
)
def test_sync_attachment_cache_name_avoids_windows_reserved_names(
    tmp_path,
    reserved_name,
):
    config = make_config(tmp_path)
    item = record("rec1", reserved_name, "file1")
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )

    FeishuReferenceSync(config, gateway).sync()

    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    image_path = Path(manifest["records"][0]["image_path"])
    assert image_path.is_file()
    assert image_path.stem.upper() not in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    expected_digest = hashlib.sha256(b"rec1\0file1").hexdigest()[:12]
    assert expected_digest in image_path.stem


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


def test_import_uses_atomic_empty_field_update_without_overwriting_racing_manual_value(
    tmp_path,
):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def add_manual_value_inside_atomic_write(_record_id, _fields):
        item["fields"]["风格分类"] = "竞态人工风格"

    gateway.before_update = add_manual_value_inside_atomic_write
    input_path = write_enrichment_input(
        tmp_path,
        [
            {
                "record_id": "rec1",
                "fields": LEGACY_ENRICHMENT_FIELDS | {"风格分类": "AI 风格"},
            }
        ],
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 0
    assert result.remaining_pending == 1
    assert item["fields"]["风格分类"] == "竞态人工风格"
    assert len(gateway.atomic_attempts) == 1
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert audit["records"][0]["details"]["风格分类"]["actual"] == "竞态人工风格"


def test_import_atomic_predicate_rejects_nonpatch_ai_field_cleared_in_write_window(
    tmp_path,
):
    config = make_config(tmp_path)
    item = record()
    item["fields"]["风格分类"] = "预读人工风格"
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def clear_nonpatch_ai_field(_record_id, _fields):
        item["fields"]["风格分类"] = ""

    gateway.before_update = clear_nonpatch_ai_field
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 0
    assert result.remaining_pending == 1
    assert gateway.updates == []
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert "风格分类" in audit["records"][0]["details"]


@pytest.mark.parametrize("changed_dependency", ["关键词", "素材图片"])
def test_import_atomic_predicate_rejects_source_change_in_write_window(
    tmp_path,
    changed_dependency,
):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def change_source(_record_id, _fields):
        if changed_dependency == "关键词":
            item["fields"]["关键词"] = "原子窗口并发关键词"
        else:
            item["fields"]["素材图片"] = [
                {
                    "file_token": "replacement-token",
                    "name": "replacement.png",
                    "size": len(PNG_3X2),
                }
            ]

    gateway.before_update = change_source
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 0
    assert result.remaining_pending == 1
    assert gateway.updates == []
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert changed_dependency in audit["records"][0]["details"]


@pytest.mark.parametrize("tracking_field", ["AI补齐状态", "AI补齐版本"])
def test_import_atomic_predicate_rejects_tracking_raw_value_change_in_write_window(
    tmp_path,
    tracking_field,
):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def change_tracking_representation(_record_id, _fields):
        item["fields"][tracking_field] = []

    gateway.before_update = change_tracking_representation
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 0
    assert result.remaining_pending == 1
    assert gateway.updates == []
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert tracking_field in audit["records"][0]["details"]


def test_import_write_readback_missing_ai_fields_stays_pending_and_conflict(
    tmp_path,
):
    config = make_config(tmp_path)
    item = record()

    def clear_required_field_after_write(_record_id, _fields):
        item["fields"]["备注"] = ""

    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
        after_update=clear_required_field_after_write,
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 0
    assert result.remaining_pending == 1
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["records"][0]["pending_enrichment"] is True
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert "备注" in audit["records"][0]["details"]["missing_ai_fields"]


def test_import_with_lark_cli_gateway_fails_closed_before_record_upsert_and_audits(
    tmp_path,
    monkeypatch,
):
    config = make_config(tmp_path)
    item = record()
    FeishuReferenceSync(
        config,
        FakeGateway(
            pages=[{"records": [item], "has_more": False}],
            downloads={"file1": PNG_3X2},
        ),
    ).sync()
    gateway = LarkCliGateway("lark-cli")
    monkeypatch.setattr(gateway, "resolve_source", lambda _config: ("base-token", "table-id"))
    monkeypatch.setattr(
        gateway,
        "list_records",
        lambda _base, _table, _offset, _limit: {
            "records": [item],
            "has_more": False,
        },
    )
    monkeypatch.setattr(gateway, "get_record", lambda _base, _table, _record: item)
    commands = []
    monkeypatch.setattr(
        gateway,
        "_run",
        lambda *args: commands.append(args) or {"ok": True, "data": {}},
    )
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    with pytest.raises(FeishuReferenceError, match="原子条件写|字段仍为空"):
        import_enrichment_results(config, input_path, gateway)

    assert not any("+record-upsert" in command for command in commands)
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "failed"
    assert "原子条件写" in audit["records"][0]["error"]


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

    assert gateway.get_record_calls == ["rec1"]
    assert len(gateway.atomic_attempts) == 1
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


def test_readback_audit_marks_expected_actual_mismatch_as_conflict(tmp_path):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(LEGACY_ENRICHMENT_FIELDS)
    item["fields"].update(
        {"AI补齐状态": "已完成", "AI补齐版本": ENRICHMENT_VERSION}
    )
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    FeishuReferenceSync(config, gateway).sync()
    item["fields"]["风格分类"] = "远端并发风格"

    result = audit_enrichment_readback(config, gateway)

    assert result.verified_records == 0
    assert result.failed_records == 1
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert audit["records"][0]["details"]["mismatches"]["风格分类"] == {
        "expected": LEGACY_ENRICHMENT_FIELDS["风格分类"],
        "actual": "远端并发风格",
    }


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [("AI补齐状态", ""), ("AI补齐版本", "2")],
)
def test_readback_audit_requires_completed_tracking_state_and_version(
    tmp_path,
    field_name,
    changed_value,
):
    config = make_config(tmp_path)
    item = record()
    item["fields"].update(LEGACY_ENRICHMENT_FIELDS)
    item["fields"].update(
        {"AI补齐状态": "已完成", "AI补齐版本": ENRICHMENT_VERSION}
    )
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    FeishuReferenceSync(config, gateway).sync()
    item["fields"][field_name] = changed_value

    result = audit_enrichment_readback(config, gateway)

    assert result.verified_records == 0
    assert result.failed_records == 1
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"
    assert field_name in audit["records"][0]["details"]["tracking_mismatches"]


def test_import_atomic_write_checks_manual_value_after_single_reread(tmp_path):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    def add_manual_value_inside_atomic_write(_record_id, _fields):
        item["fields"]["风格分类"] = "原子写入窗口人工风格"

    gateway.before_update = add_manual_value_inside_atomic_write
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

    assert result.updated_records == 0
    assert gateway.get_record_calls == ["rec1"]
    assert item["fields"]["风格分类"] == "原子写入窗口人工风格"
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "conflict"


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
    assert "residual_cas_risk" not in audit
    assert "原子条件写" in audit["atomic_write_contract"]


def test_import_fsyncs_pending_audit_before_remote_atomic_write(
    tmp_path,
    monkeypatch,
):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    fsync_calls = []
    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.os.fsync",
        lambda file_descriptor: fsync_calls.append(file_descriptor),
    )

    def assert_pending_audit_is_durable(_record_id, _fields):
        audit_path = config.cache_root / "enrichment-import-audit.json"
        assert audit_path.is_file()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit["records"][0]["status"] == "pending"
        assert fsync_calls

    gateway.before_update = assert_pending_audit_is_durable
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    result = import_enrichment_results(config, input_path, gateway)

    assert result.updated_records == 1
    assert fsync_calls


@pytest.mark.parametrize(
    "failed_target",
    [
        "manifest.json",
        "enrichment.json",
        "pending_enrichment.json",
        "enrichment-import-audit.json",
    ],
)
def test_import_recovers_four_file_transaction_after_replace_failure(
    tmp_path,
    monkeypatch,
    failed_target,
):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )
    real_replace = os.replace
    failed_once = False

    def fail_target_replace_once(source, destination):
        nonlocal failed_once
        destination_path = Path(destination)
        journal = config.cache_root / ".enrichment-import-transaction.json"
        if (
            not failed_once
            and journal.is_file()
            and destination_path.name == failed_target
        ):
            failed_once = True
            raise OSError("测试事务 replace 失败")
        return real_replace(source, destination)

    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.os.replace",
        fail_target_replace_once,
    )

    with pytest.raises(FeishuReferenceError, match="本地缓存事务发布失败"):
        import_enrichment_results(config, input_path, gateway)

    journal = config.cache_root / ".enrichment-import-transaction.json"
    assert journal.is_file()
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] in {"pending", "verified"}

    monkeypatch.setattr(
        "jewelry_on_hand.feishu_reference_source.os.replace",
        real_replace,
    )
    rows = load_cached_reference_rows(config.cache_root)

    assert len(rows) == 1
    assert not journal.exists()
    manifest = json.loads(
        (config.cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["records"][0]["pending_enrichment"] is False
    pending = json.loads(
        (config.cache_root / "pending_enrichment.json").read_text(encoding="utf-8")
    )
    assert pending["records"] == []
    final_audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert final_audit["records"][0]["status"] == "verified"


@pytest.mark.parametrize(
    "mutation",
    [
        "version_bool",
        "phase",
        "schema_extra",
        "target",
        "staged_name",
        "entry_extra",
        "sha_uppercase",
        "staged_missing",
        "digest_mismatch",
        "absolute_escape",
        "parent_escape",
    ],
)
def test_transaction_recovery_rejects_invalid_journal_before_any_publish(
    tmp_path,
    mutation,
):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    manifest_path = config.cache_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    transaction_dir, journal_path, journal = make_import_transaction_fixture(config)
    external = tmp_path / "external-stage.json"
    external.write_text('{"source": {}, "records": []}', encoding="utf-8")
    external_before = external.read_bytes()

    if mutation == "version_bool":
        journal["version"] = True
    elif mutation == "phase":
        journal["phase"] = "publishing"
    elif mutation == "schema_extra":
        journal["unexpected"] = True
    elif mutation == "target":
        journal["files"][0]["target"] = "other.json"
    elif mutation == "staged_name":
        alternate = transaction_dir / "alternate.new"
        alternate.write_bytes((transaction_dir / "manifest.json.new").read_bytes())
        journal["files"][0]["staged"] = alternate.name
    elif mutation == "entry_extra":
        journal["files"][0]["unexpected"] = True
    elif mutation == "sha_uppercase":
        journal["files"][0]["sha256"] = journal["files"][0]["sha256"].upper()
    elif mutation == "staged_missing":
        (transaction_dir / "manifest.json.new").unlink()
    elif mutation == "digest_mismatch":
        journal["files"][0]["sha256"] = "0" * 64
    elif mutation == "absolute_escape":
        journal["files"][0]["staged"] = str(external.resolve())
        journal["files"][0]["sha256"] = hashlib.sha256(external_before).hexdigest()
    elif mutation == "parent_escape":
        escaped = config.cache_root / "escape-stage.json"
        escaped.write_bytes(external_before)
        journal["files"][0]["staged"] = "../escape-stage.json"
        journal["files"][0]["sha256"] = hashlib.sha256(external_before).hexdigest()

    journal_path.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(FeishuReferenceError, match="damaged"):
        load_cached_reference_rows(config.cache_root)

    assert manifest_path.read_bytes() == manifest_before
    assert external.read_bytes() == external_before
    assert journal_path.is_file()


@pytest.mark.parametrize(
    "entry_name",
    [
        "sync",
        "import",
        "audit",
        "snapshot",
        "load",
        "sync_and_load",
    ],
)
def test_public_entry_recovers_valid_import_transaction_first(tmp_path, entry_name):
    config = make_config(tmp_path)
    item = record()
    if entry_name in {"load", "sync_and_load"}:
        item["fields"].update(LEGACY_ENRICHMENT_FIELDS)
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    if entry_name == "load":
        rewrite_cache_as_legacy_format(config, item)
    transaction_dir, journal_path, journal = make_import_transaction_fixture(config)
    journal_path.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if entry_name == "sync":
        FeishuReferenceSync(config, gateway).sync()
    elif entry_name == "import":
        input_path = write_enrichment_input(
            tmp_path,
            [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
        )
        import_enrichment_results(config, input_path, gateway)
    elif entry_name == "audit":
        audit_enrichment_readback(config, gateway)
    elif entry_name == "snapshot":
        build_reference_source_snapshot(
            config.cache_root,
            ignore_pending_enrichment=True,
        )
    elif entry_name == "load":
        load_cached_reference_rows(
            config.cache_root,
            ignore_pending_enrichment=True,
        )
    else:
        sync_and_load_reference_rows(
            config,
            gateway,
            ignore_pending_enrichment=True,
        )

    assert not journal_path.exists()
    assert not transaction_dir.exists()


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
    ("failure_kind", "expected_error"),
    [
        ("read", "测试逐条读取失败"),
        ("source", "源字段已变化"),
        ("ring", "戒指佩戴候选缺少必需字段"),
        ("atomic", "测试写入失败"),
    ],
)
def test_import_isolates_per_record_read_and_validation_failures_and_continues(
    tmp_path,
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
        update_failures={"rec2"} if failure_kind == "atomic" else None,
    )
    FeishuReferenceSync(config, gateway).sync()

    def fail_second_record(record_id):
        if record_id != "rec2":
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
    assert gateway.get_record_calls.count("rec3") == 1
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
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "failed"
    assert "源字段已变化" in audit["records"][0]["error"]


def test_import_audits_remote_record_disappearance_before_raising(tmp_path):
    config = make_config(tmp_path)
    item = record()
    gateway = FakeGateway(
        pages=[{"records": [item], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    gateway.pages = [{"records": [], "has_more": False}]
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": LEGACY_ENRICHMENT_FIELDS}],
    )

    with pytest.raises(InvalidEnrichmentError, match="已不在当前飞书数据表"):
        import_enrichment_results(config, input_path, gateway)

    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "failed"
    assert "已不在当前飞书数据表" in audit["records"][0]["error"]


@pytest.mark.parametrize(
    ("submitted_fields", "expected_error"),
    [
        ("不是对象", "缺少 fields 对象"),
        (
            {name: value for name, value in LEGACY_ENRICHMENT_FIELDS.items() if name != "备注"},
            "缺少必需补齐字段：备注",
        ),
    ],
)
def test_import_input_preflight_failure_is_persisted_after_record_id_is_known(
    tmp_path,
    submitted_fields,
    expected_error,
):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    input_path = write_enrichment_input(
        tmp_path,
        [{"record_id": "rec1", "fields": submitted_fields}],
    )

    with pytest.raises(InvalidEnrichmentError, match=expected_error):
        import_enrichment_results(config, input_path, gateway)

    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["record_id"] == "rec1"
    assert audit["records"][0]["status"] == "failed"
    assert expected_error in audit["records"][0]["error"]


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
    audit = json.loads(
        (config.cache_root / "enrichment-import-audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["records"][0]["status"] == "failed"
    assert "戒指佩戴候选缺少必需字段" in audit["records"][0]["error"]


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


def test_loading_cache_can_explicitly_ignore_pending_enrichment(tmp_path):
    config = make_config(tmp_path)
    completed = record("rec1", "RP000001", "file1")
    completed["fields"].update(LEGACY_ENRICHMENT_FIELDS | GENERIC_REFERENCE_FIELDS)
    pending = record("rec2", "RP000308", "file2")
    gateway = FakeGateway(
        pages=[{"records": [completed, pending], "has_more": False}],
        downloads={"file1": PNG_3X2, "file2": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()
    FeishuReferenceSync(
        config,
        FakeGateway(pages=[{"records": [completed, pending], "has_more": False}]),
    ).sync()

    rows = load_cached_reference_rows(
        config.cache_root,
        ignore_pending_enrichment=True,
    )

    assert len(rows) == 1
    assert rows[0].file_name.startswith("RP000001")
    assert "RP000308" not in rows[0].notes


def test_loading_cache_rejects_when_ignoring_pending_leaves_no_usable_rows(
    tmp_path,
):
    config = make_config(tmp_path)
    gateway = FakeGateway(
        pages=[{"records": [record()], "has_more": False}],
        downloads={"file1": PNG_3X2},
    )
    FeishuReferenceSync(config, gateway).sync()

    with pytest.raises(
        FeishuReferenceError,
        match="排除待补全素材后没有可用参考图",
    ):
        load_cached_reference_rows(
            config.cache_root,
            ignore_pending_enrichment=True,
        )
