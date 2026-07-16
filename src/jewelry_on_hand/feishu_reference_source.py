from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jewelry_on_hand.models import ReferenceRow

DEFAULT_WIKI_URL = "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink"
DEFAULT_TABLE_NAME = "素材收录池"
DEFAULT_CACHE_ROOT = Path("output/feishu_reference_cache")
ENRICHMENT_VERSION = "1"
IMPORT_AUDIT_FILENAME = "enrichment-import-audit.json"
IMPORT_RESIDUAL_CAS_RISK = (
    "飞书 record-upsert 不支持 revision、etag 或 if-match；最后一次写前复读后到 "
    "upsert 前仍存在无法消除的并发覆盖窗口，写后核验也无法识别已被本次写入覆盖的值。"
)
READBACK_AUDIT_LIMITATION = (
    "该审计只证明执行时远端字段与当前缓存一致，不能追溯或替代导入时的写后核验。"
)
REQUIRED_AI_FIELD_NAMES = (
    "默认使用策略",
    "风格分类",
    "推荐使用方式",
    "备注",
    "判断置信度",
)
OPTIONAL_REFERENCE_FIELD_NAMES = (
    "适用产品类型",
    "适用展示模式",
    "人物取景范围",
    "可见身体区域",
    "产品预计展示面积",
    "颈部可见度",
    "锁骨可见度",
    "胸前可见度",
    "手部可见度",
    "衣领类型",
    "衣物遮挡风险",
    "头发遮挡风险",
    "姿势关键词",
    "镜面关系",
    "原有首饰类型",
    "裁切风险",
    "左右手",
    "可见手指",
    "手部朝向",
    "戒面可见度",
    "手指分离度",
    "手指遮挡风险",
)
RING_REQUIRED_FIELD_NAMES = (
    "左右手",
    "可见手指",
    "手部朝向",
    "戒面可见度",
    "手指分离度",
    "手指遮挡风险",
)
RING_PRODUCT_TYPE_ALIASES = frozenset({"ring", "戒指", "指环"})
WORN_DISPLAY_MODE_ALIASES = frozenset({"worn", "佩戴", "真人佩戴"})
AI_FIELD_NAMES = REQUIRED_AI_FIELD_NAMES + OPTIONAL_REFERENCE_FIELD_NAMES
TRACKING_FIELD_NAMES = ("AI补齐状态", "AI补齐版本")
LEGACY_SOURCE_FIELD_NAMES = (
    "素材编号",
    "素材图片",
    "关键词",
    "图片类型",
    "适用品类",
)
SOURCE_FIELD_NAMES = LEGACY_SOURCE_FIELD_NAMES + OPTIONAL_REFERENCE_FIELD_NAMES


class FeishuReferenceError(RuntimeError):
    pass


class PendingEnrichmentError(FeishuReferenceError):
    pass


class InvalidEnrichmentError(FeishuReferenceError):
    pass


class FeishuGateway(Protocol):
    def resolve_source(self, config: "FeishuReferenceConfig") -> tuple[str, str]: ...
    def list_fields(self, base_token: str, table_id: str) -> list[dict[str, Any]]: ...
    def list_records(
        self, base_token: str, table_id: str, offset: int, limit: int
    ) -> dict[str, Any]: ...
    def get_record(
        self, base_token: str, table_id: str, record_id: str
    ) -> dict[str, Any]: ...
    def download_attachment(
        self,
        base_token: str,
        table_id: str,
        record_id: str,
        file_token: str,
        destination: Path,
    ) -> None: ...
    def create_field(
        self, base_token: str, table_id: str, field: dict[str, Any]
    ) -> None: ...
    def update_record(
        self, base_token: str, table_id: str, record_id: str, fields: dict[str, Any]
    ) -> None: ...


@dataclass(frozen=True)
class FeishuReferenceConfig:
    wiki_url: str = DEFAULT_WIKI_URL
    table_name: str = DEFAULT_TABLE_NAME
    cache_root: Path = DEFAULT_CACHE_ROOT
    base_token: str | None = None
    table_id: str | None = None
    page_size: int = 200

    @classmethod
    def from_env(
        cls,
        *,
        cache_root: str | Path | None = None,
        wiki_url: str | None = None,
        table_name: str | None = None,
    ) -> "FeishuReferenceConfig":
        return cls(
            wiki_url=wiki_url or os.getenv("JEWELRY_REFERENCE_WIKI_URL") or DEFAULT_WIKI_URL,
            table_name=table_name
            or os.getenv("JEWELRY_REFERENCE_TABLE_NAME")
            or DEFAULT_TABLE_NAME,
            cache_root=Path(
                cache_root
                or os.getenv("JEWELRY_REFERENCE_CACHE_ROOT")
                or DEFAULT_CACHE_ROOT
            ),
            base_token=os.getenv("JEWELRY_REFERENCE_BASE_TOKEN") or None,
            table_id=os.getenv("JEWELRY_REFERENCE_TABLE_ID") or None,
        )


@dataclass(frozen=True)
class ImportResult:
    updated_records: int
    remaining_pending: int


@dataclass(frozen=True)
class ReadbackAuditResult:
    verified_records: int
    failed_records: int


@dataclass(frozen=True)
class SyncResult:
    total_records: int
    usable_records: int
    pending_count: int
    downloaded_count: int
    manifest_path: Path
    pending_path: Path
    issues_path: Path


class LarkCliGateway:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("lark-cli.cmd") or shutil.which("lark-cli")
        if not self.executable:
            raise FeishuReferenceError("未找到 lark-cli，请先安装并完成飞书授权")

    def resolve_source(self, config: FeishuReferenceConfig) -> tuple[str, str]:
        base_token = config.base_token
        if not base_token:
            payload = self._run(
                "base",
                "+url-resolve",
                "--url",
                config.wiki_url,
                "--as",
                "user",
            )
            base_token = _required_text(payload.get("data", {}).get("base_token"), "base_token")
        if config.table_id:
            return base_token, config.table_id
        payload = self._run(
            "base", "+table-list", "--base-token", base_token, "--as", "user"
        )
        tables = payload.get("data", {}).get("tables", [])
        matches = [item for item in tables if item.get("name") == config.table_name]
        if len(matches) != 1:
            raise FeishuReferenceError(
                f"无法唯一定位飞书数据表 {config.table_name!r}，命中 {len(matches)} 个"
            )
        return base_token, _required_text(matches[0].get("id"), "table_id")

    def list_fields(self, base_token: str, table_id: str) -> list[dict[str, Any]]:
        payload = self._run(
            "base",
            "+field-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            "user",
        )
        return list(payload.get("data", {}).get("fields", []))

    def list_records(
        self, base_token: str, table_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        payload = self._run(
            "base",
            "+record-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--offset",
            str(offset),
            "--limit",
            str(limit),
            "--format",
            "json",
            "--as",
            "user",
        )
        data = payload.get("data", {})
        records = _records_from_matrix(data)
        return {"records": records, "has_more": bool(data.get("has_more"))}

    def get_record(
        self, base_token: str, table_id: str, record_id: str
    ) -> dict[str, Any]:
        payload = self._run(
            "base",
            "+record-get",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--format",
            "json",
            "--as",
            "user",
        )
        records = _records_from_matrix(payload.get("data", {}))
        matches = [item for item in records if item.get("record_id") == record_id]
        if len(matches) != 1:
            raise FeishuReferenceError(
                f"无法读取飞书记录 {record_id!r}，命中 {len(matches)} 条"
            )
        return matches[0]

    def download_attachment(
        self,
        base_token: str,
        table_id: str,
        record_id: str,
        file_token: str,
        destination: Path,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            "base",
            "+record-download-attachment",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--file-token",
            file_token,
            "--output",
            str(destination),
            "--overwrite",
            "--as",
            "user",
        )
        if not destination.is_file():
            raise FeishuReferenceError(f"飞书附件下载后文件不存在：{destination}")

    def create_field(
        self, base_token: str, table_id: str, field: dict[str, Any]
    ) -> None:
        self._run(
            "base",
            "+field-create",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(field, ensure_ascii=False, separators=(",", ":")),
            "--as",
            "user",
        )

    def update_record(
        self, base_token: str, table_id: str, record_id: str, fields: dict[str, Any]
    ) -> None:
        self._run(
            "base",
            "+record-upsert",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--json",
            json.dumps(fields, ensure_ascii=False, separators=(",", ":")),
            "--as",
            "user",
        )

    def _run(self, *args: str) -> dict[str, Any]:
        env = os.environ.copy()
        env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
        env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
        completed = subprocess.run(
            [self.executable, *args],
            capture_output=True,
            env=env,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", errors="strict")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise FeishuReferenceError(
                f"lark-cli 未返回有效 JSON：{stderr or stdout}"
            ) from exc
        if completed.returncode != 0 or not payload.get("ok"):
            error = payload.get("error", {})
            message = error.get("message") or stderr or stdout
            raise FeishuReferenceError(f"飞书命令执行失败：{message}")
        return payload


class FeishuReferenceSync:
    def __init__(self, config: FeishuReferenceConfig, gateway: FeishuGateway | None = None) -> None:
        self.config = config
        self.gateway = gateway or LarkCliGateway()

    def sync(self) -> SyncResult:
        cache_root = self.config.cache_root
        images_dir = cache_root / "images"
        cache_root.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        previous_manifest = _read_json(cache_root / "manifest.json", {"records": []})
        previous_by_id = {
            item["record_id"]: item for item in previous_manifest.get("records", [])
        }
        local_enrichment = _read_json(cache_root / "enrichment.json", {})

        base_token, table_id = self.gateway.resolve_source(self.config)
        records = self._read_all_records(base_token, table_id)
        records.sort(key=_record_sort_key)

        manifest_records: list[dict[str, Any]] = []
        pending_records: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        downloaded_count = 0
        usable_records = 0

        for stable_index, source in enumerate(records, start=1):
            item, downloaded = self._sync_record(
                source,
                stable_index,
                base_token,
                table_id,
                images_dir,
                previous_by_id.get(source["record_id"]),
                local_enrichment,
            )
            downloaded_count += int(downloaded)
            manifest_records.append(item)
            if item["usable"]:
                usable_records += 1
            else:
                issues.append(
                    {"record_id": item["record_id"], "reason": item["issue"]}
                )
            if item["pending_enrichment"]:
                pending_records.append(_pending_record(item))

        active_ids = {item["record_id"] for item in manifest_records}
        local_enrichment = {
            record_id: values
            for record_id, values in local_enrichment.items()
            if record_id in active_ids
        }
        manifest = {
            "source": {
                "wiki_url": self.config.wiki_url,
                "table_name": self.config.table_name,
                "base_token": base_token,
                "table_id": table_id,
            },
            "records": manifest_records,
        }
        manifest_path = cache_root / "manifest.json"
        pending_path = cache_root / "pending_enrichment.json"
        issues_path = cache_root / "issues.json"
        _write_json(manifest_path, manifest)
        _write_json(cache_root / "enrichment.json", local_enrichment)
        _write_json(pending_path, {"version": ENRICHMENT_VERSION, "records": pending_records})
        _write_json(issues_path, {"records": issues})
        return SyncResult(
            total_records=len(manifest_records),
            usable_records=usable_records,
            pending_count=len(pending_records),
            downloaded_count=downloaded_count,
            manifest_path=manifest_path,
            pending_path=pending_path,
            issues_path=issues_path,
        )

    def _read_all_records(self, base_token: str, table_id: str) -> list[dict[str, Any]]:
        return _read_all_records(
            self.gateway, base_token, table_id, self.config.page_size
        )

    def _sync_record(
        self,
        source: dict[str, Any],
        stable_index: int,
        base_token: str,
        table_id: str,
        images_dir: Path,
        previous: dict[str, Any] | None,
        local_enrichment: dict[str, dict[str, str]],
    ) -> tuple[dict[str, Any], bool]:
        record_id = _required_text(source.get("record_id"), "record_id")
        fields = dict(source.get("fields") or {})
        attachments = _attachments(fields.get("素材图片"))
        warnings: list[str] = []
        if len(attachments) > 1:
            warnings.append("素材图片包含多张附件，仅使用第一张附件")
        attachment = attachments[0] if attachments else None
        fingerprint = _source_fingerprint(record_id, fields, attachment)
        changed = previous is None or previous.get("source_fingerprint") != fingerprint
        if changed and previous and _matches_legacy_source_fingerprint(
            previous, record_id, fields, attachment
        ):
            changed = False

        remote_enrichment = {
            name: _field_text(fields.get(name)) for name in AI_FIELD_NAMES
        }
        invalidation_reasons: list[str] = []
        tracking_status = _field_text(fields.get("AI补齐状态"))
        tracking_version = _field_text(fields.get("AI补齐版本"))
        if tracking_status == "需刷新":
            invalidation_reasons.append("AI补齐状态=需刷新")
        if tracking_version and tracking_version != ENRICHMENT_VERSION:
            invalidation_reasons.append("AI补齐版本不匹配")
        previous_completed = bool(
            previous
            and tracking_status == "已完成"
            and tracking_version == ENRICHMENT_VERSION
        )
        if previous_completed:
            previous_values = dict(previous.get("resolved_enrichment") or {})
            cleared = [
                name
                for name in AI_FIELD_NAMES
                if _field_text(previous_values.get(name)) and not remote_enrichment[name]
            ]
            invalidation_reasons.extend(
                f"远端已清空已写回字段：{name}" for name in cleared
            )
        invalidated = bool(invalidation_reasons)
        if changed or invalidated:
            local_values = {}
        else:
            local_values = dict(local_enrichment.get(record_id) or {})
        resolved_enrichment = {
            name: remote_enrichment[name] or _field_text(local_values.get(name))
            for name in AI_FIELD_NAMES
        }
        local_enrichment[record_id] = resolved_enrichment

        downloaded = False
        image_path: Path | None = None
        issue = ""
        if attachment is None:
            issue = "素材图片为空，无法作为参考图候选"
        else:
            suffix = Path(_required_text(attachment.get("name"), "附件文件名")).suffix.lower() or ".bin"
            image_path = images_dir / f"{_safe_file_stem(_field_text(fields.get('素材编号')) or record_id)}{suffix}"
            same_attachment = bool(
                previous
                and previous.get("attachment", {}).get("file_token")
                == attachment.get("file_token")
            )
            if not same_attachment or not image_path.is_file():
                self.gateway.download_attachment(
                    base_token,
                    table_id,
                    record_id,
                    _required_text(attachment.get("file_token"), "file_token"),
                    image_path,
                )
                downloaded = True
            if not image_path.is_file():
                issue = "素材图片下载失败或本地缓存缺失"

        missing_ai_fields = _missing_ai_fields(fields, resolved_enrichment)
        pending = bool(
            image_path
            and image_path.is_file()
            and (changed or invalidated or missing_ai_fields)
        )
        width, height = _image_dimensions(image_path) if image_path and image_path.is_file() else (None, None)
        size_mb = round(image_path.stat().st_size / 1024 / 1024, 6) if image_path and image_path.is_file() else None

        item = {
            "record_id": record_id,
            "stable_index": stable_index,
            "source_fingerprint": fingerprint,
            "source_fields": {name: fields.get(name) for name in SOURCE_FIELD_NAMES},
            "attachment": attachment,
            "image_path": str(image_path.resolve()) if image_path else "",
            "width": width,
            "height": height,
            "size_mb": size_mb,
            "resolved_enrichment": resolved_enrichment,
            "missing_ai_fields": missing_ai_fields,
            "pending_enrichment": pending,
            "enrichment_invalidation_reasons": invalidation_reasons,
            "usable": not issue and bool(image_path and image_path.is_file()),
            "issue": issue,
            "warnings": warnings,
        }
        return item, downloaded




def ensure_enrichment_fields(
    config: FeishuReferenceConfig, gateway: FeishuGateway | None = None
) -> list[str]:
    gateway = gateway or LarkCliGateway()
    base_token, table_id = gateway.resolve_source(config)
    existing = {item.get("name") for item in gateway.list_fields(base_token, table_id)}
    definitions = [
        {"name": name, "type": "text"} for name in AI_FIELD_NAMES
    ] + [
        {
            "name": "AI补齐状态",
            "type": "select",
            "multiple": False,
            "options": [{"name": "待补齐"}, {"name": "已完成"}, {"name": "需刷新"}],
        },
        {"name": "AI补齐版本", "type": "text"},
    ]
    created = []
    for definition in definitions:
        if definition["name"] in existing:
            continue
        gateway.create_field(base_token, table_id, definition)
        created.append(definition["name"] )
    return created

def import_enrichment_results(
    config: FeishuReferenceConfig,
    input_path: str | Path,
    gateway: FeishuGateway | None = None,
) -> ImportResult:
    gateway = gateway or LarkCliGateway()
    root = config.cache_root
    manifest = _read_json(root / "manifest.json", None)
    pending_document = _read_json(root / "pending_enrichment.json", None)
    if not manifest or not pending_document:
        raise InvalidEnrichmentError("缺少飞书同步缓存，请先执行 reference-sync")
    pending_by_id = {item["record_id"]: item for item in pending_document.get("records", [])}
    submitted = _read_json(Path(input_path), None)
    if not isinstance(submitted, dict) or not isinstance(submitted.get("records"), list):
        raise InvalidEnrichmentError("补齐结果必须是包含 records 数组的 JSON 对象")

    results_by_id: dict[str, dict[str, str]] = {}
    for item in submitted["records"]:
        if not isinstance(item, dict):
            raise InvalidEnrichmentError("补齐结果 records 中每项必须是对象")
        record_id = _field_text(item.get("record_id"))
        if record_id not in pending_by_id:
            raise InvalidEnrichmentError(f"记录 {record_id!r} 不在待补齐清单")
        fields = item.get("fields")
        if not isinstance(fields, dict):
            raise InvalidEnrichmentError(f"记录 {record_id} 缺少 fields 对象")
        missing = [
            name
            for name in REQUIRED_AI_FIELD_NAMES
            if not _field_text(fields.get(name))
        ]
        if missing:
            raise InvalidEnrichmentError(
                f"记录 {record_id} 缺少必需补齐字段：{'、'.join(missing)}"
            )
        results_by_id[record_id] = {
            name: _field_text(fields.get(name)) for name in AI_FIELD_NAMES
        }

    base_token, table_id = gateway.resolve_source(config)
    current_by_id = {
        item["record_id"]: item
        for item in _read_all_records(
            gateway, base_token, table_id, config.page_size
        )
    }
    manifest_by_id = {item["record_id"]: item for item in manifest.get("records", [])}
    for record_id, generated in results_by_id.items():
        current = current_by_id.get(record_id)
        if current is None:
            raise InvalidEnrichmentError(f"记录 {record_id} 已不在当前飞书数据表中")
        manifest_item = manifest_by_id[record_id]
        current_fields = dict(current.get("fields") or {})
        _validate_source_unchanged(record_id, manifest_item, current_fields)
        remote = {
            name: _field_text(current_fields.get(name)) for name in AI_FIELD_NAMES
        }
        final_values = {
            name: remote[name] or generated[name] for name in AI_FIELD_NAMES
        }
        _validate_ring_required_fields(record_id, current_fields, final_values)

    updated = 0
    audit_records: list[dict[str, Any]] = []
    for record_id, generated in results_by_id.items():
        manifest_item = manifest_by_id[record_id]
        audit_item: dict[str, Any] = {
            "record_id": record_id,
            "status": "failed",
            "patch": {},
            "details": {},
            "error": "",
        }
        try:
            latest = gateway.get_record(base_token, table_id, record_id)
            current_fields = dict(latest.get("fields") or {})
            _validate_source_unchanged(record_id, manifest_item, current_fields)
            remote = {
                name: _field_text(current_fields.get(name))
                for name in AI_FIELD_NAMES
            }
            final_values = {
                name: remote[name] or generated[name] for name in AI_FIELD_NAMES
            }
            _validate_ring_required_fields(
                record_id, current_fields, final_values
            )

            prewrite = gateway.get_record(base_token, table_id, record_id)
            current_fields = dict(prewrite.get("fields") or {})
            _validate_source_unchanged(record_id, manifest_item, current_fields)
            remote = {
                name: _field_text(current_fields.get(name))
                for name in AI_FIELD_NAMES
            }
            final_values = {
                name: remote[name] or generated[name] for name in AI_FIELD_NAMES
            }
            _validate_ring_required_fields(
                record_id, current_fields, final_values
            )
            patch = {
                name: generated[name]
                for name in AI_FIELD_NAMES
                if not remote[name] and generated[name]
            }
            patch["AI补齐状态"] = "已完成"
            patch["AI补齐版本"] = ENRICHMENT_VERSION
            audit_item["patch"] = patch
            gateway.update_record(base_token, table_id, record_id, patch)
            written = gateway.get_record(base_token, table_id, record_id)

            written_fields = dict(written.get("fields") or {})
            mismatches = {
                name: {
                    "expected": _field_text(expected),
                    "actual": _field_text(written_fields.get(name)),
                }
                for name, expected in patch.items()
                if _field_text(written_fields.get(name)) != _field_text(expected)
            }
            if mismatches:
                audit_item["status"] = "conflict"
                audit_item["details"] = mismatches
                audit_records.append(audit_item)
                continue

            verified_values = {
                name: _field_text(written_fields.get(name))
                for name in AI_FIELD_NAMES
            }
            source_fields = {
                name: written_fields.get(name) for name in SOURCE_FIELD_NAMES
            }
            source_fingerprint = _source_fingerprint(
                record_id,
                source_fields,
                manifest_item.get("attachment"),
            )
            missing_ai_fields = _missing_ai_fields(
                written_fields, verified_values
            )
        except Exception as exc:
            audit_item["error"] = str(exc)
            audit_records.append(audit_item)
            continue

        manifest_item["resolved_enrichment"] = verified_values
        manifest_item["source_fields"] = source_fields
        manifest_item["source_fingerprint"] = source_fingerprint
        manifest_item["missing_ai_fields"] = missing_ai_fields
        manifest_item["pending_enrichment"] = False
        audit_item["status"] = "verified"
        audit_records.append(audit_item)
        updated += 1

    remaining = [
        _pending_record(item)
        for item in manifest.get("records", [])
        if item.get("pending_enrichment")
    ]
    local_enrichment = {
        item["record_id"]: item["resolved_enrichment"]
        for item in manifest.get("records", [])
        if item.get("usable")
    }
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "enrichment.json", local_enrichment)
    _write_json(
        root / "pending_enrichment.json",
        {"version": ENRICHMENT_VERSION, "records": remaining},
    )
    _write_json(
        root / IMPORT_AUDIT_FILENAME,
        {
            "version": 1,
            "residual_cas_risk": IMPORT_RESIDUAL_CAS_RISK,
            "records": audit_records,
        },
    )
    return ImportResult(updated_records=updated, remaining_pending=len(remaining))


def audit_enrichment_readback(
    config: FeishuReferenceConfig, gateway: FeishuGateway | None = None
) -> ReadbackAuditResult:
    """复读远端补齐字段，为缺失的历史导入审计提供当前状态证据。"""
    gateway = gateway or LarkCliGateway()
    root = config.cache_root
    manifest = _read_json(root / "manifest.json", None)
    if not manifest:
        raise InvalidEnrichmentError("缺少飞书同步缓存，请先执行 reference-sync")

    base_token, table_id = gateway.resolve_source(config)
    current_by_id = {
        item["record_id"]: item
        for item in _read_all_records(gateway, base_token, table_id, config.page_size)
    }
    audit_records: list[dict[str, Any]] = []
    for manifest_item in manifest.get("records", []):
        record_id = _field_text(manifest_item.get("record_id"))
        audit_item: dict[str, Any] = {
            "record_id": record_id,
            "status": "failed",
            "patch": {},
            "details": {},
            "error": "",
        }
        try:
            current = current_by_id.get(record_id)
            if current is None:
                raise FeishuReferenceError(f"远端不存在记录 {record_id}")
            current_fields = dict(current.get("fields") or {})
            _validate_source_unchanged(record_id, manifest_item, current_fields)
            expected_values = {
                name: _field_text(
                    (manifest_item.get("resolved_enrichment") or {}).get(name)
                )
                for name in AI_FIELD_NAMES
            }
            actual_values = {
                name: _field_text(current_fields.get(name)) for name in AI_FIELD_NAMES
            }
            missing = _missing_ai_fields(current_fields, actual_values)
            mismatches = {
                name: {"expected": expected, "actual": actual_values[name]}
                for name, expected in expected_values.items()
                if expected != actual_values[name]
            }
            if missing:
                audit_item["details"]["missing_ai_fields"] = missing
            if mismatches:
                audit_item["details"]["mismatches"] = mismatches
            if manifest_item.get("pending_enrichment"):
                audit_item["details"]["pending_enrichment"] = True
            if audit_item["details"]:
                audit_records.append(audit_item)
                continue
        except Exception as exc:
            audit_item["error"] = str(exc)
            audit_records.append(audit_item)
            continue
        audit_item["status"] = "verified"
        audit_records.append(audit_item)

    _write_json(
        root / IMPORT_AUDIT_FILENAME,
        {
            "version": 1,
            "audit_kind": "post_sync_readback",
            "limitation": READBACK_AUDIT_LIMITATION,
            "records": audit_records,
        },
    )
    verified = sum(item["status"] == "verified" for item in audit_records)
    return ReadbackAuditResult(
        verified_records=verified,
        failed_records=len(audit_records) - verified,
    )


def sync_and_load_reference_rows(
    config: FeishuReferenceConfig,
    gateway: FeishuGateway | None = None,
    *,
    ignore_pending_enrichment: bool = False,
) -> list[ReferenceRow]:
    FeishuReferenceSync(config, gateway).sync()
    return load_cached_reference_rows(
        config.cache_root,
        ignore_pending_enrichment=ignore_pending_enrichment,
    )


def build_reference_source_snapshot(
    cache_root: str | Path,
    *,
    ignore_pending_enrichment: bool,
) -> dict[str, Any]:
    root = Path(cache_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FeishuReferenceError(f"飞书参考图库缓存不存在：{manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuReferenceError(f"飞书参考图库缓存不是有效 UTF-8 JSON：{manifest_path}") from exc

    records = list(manifest.get("records", []))
    ignored = (
        [item for item in records if item.get("pending_enrichment")]
        if ignore_pending_enrichment
        else []
    )
    ignored.sort(key=lambda item: int(item.get("stable_index") or 0))
    retained = [
        item
        for item in records
        if item.get("usable")
        and not (ignore_pending_enrichment and item.get("pending_enrichment"))
    ]
    return {
        "schema_version": 1,
        "source": dict(manifest.get("source") or {}),
        "pagination_complete": True,
        "synced_total_count": len(records),
        "ignored_pending_count": len(ignored),
        "retained_usable_count": len(retained),
        "ignored_pending_records": [
            {
                "record_id": _field_text(item.get("record_id")),
                "material_number": _field_text(
                    (item.get("source_fields") or {}).get("素材编号")
                ),
            }
            for item in ignored
        ],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def load_cached_reference_rows(
    cache_root: str | Path,
    *,
    ignore_pending_enrichment: bool = False,
) -> list[ReferenceRow]:
    root = Path(cache_root)
    manifest = _read_json(root / "manifest.json", None)
    if not manifest:
        raise FeishuReferenceError(f"飞书参考图库缓存不存在：{root / 'manifest.json'}")
    pending = [
        item for item in manifest.get("records", []) if item.get("pending_enrichment")
    ]
    if pending and not ignore_pending_enrichment:
        raise PendingEnrichmentError(
            f"{len(pending)} 条素材等待 AI 补齐；请处理 {root / 'pending_enrichment.json'}"
        )
    rows: list[ReferenceRow] = []
    for item in manifest.get("records", []):
        if ignore_pending_enrichment and item.get("pending_enrichment"):
            continue
        if not item.get("usable"):
            continue
        source = item.get("source_fields", {})
        enrichment = item.get("resolved_enrichment", {})
        image_path = Path(item["image_path"])
        number = _field_text(source.get("素材编号"))
        image_type = _join_field(source.get("图片类型"))
        categories = _field_values(source.get("适用品类"))
        keywords = _field_text(source.get("关键词"))
        applicable_product_types = _reference_field_text(
            source, enrichment, "适用产品类型", "适用品类"
        )
        rows.append(
            ReferenceRow(
                index=int(item["stable_index"]),
                file_name=image_path.name,
                relative_path=image_path.relative_to(root.resolve()).as_posix()
                if image_path.is_relative_to(root.resolve())
                else image_path.name,
                absolute_path=image_path,
                width=item.get("width"),
                height=item.get("height"),
                size_mb=item.get("size_mb"),
                purpose_category=image_type or "未分类",
                bracelet_applicability=_bracelet_applicability(categories),
                default_strategy=_field_text(enrichment.get("默认使用策略")),
                style_category=_field_text(enrichment.get("风格分类")),
                scene_keywords=keywords,
                jewelry_type="、".join(categories) or applicable_product_types or "通用",
                recommended_usage=_field_text(enrichment.get("推荐使用方式")),
                notes=_merge_notes(number, _field_text(enrichment.get("备注"))),
                confidence=_field_text(enrichment.get("判断置信度")),
                file_exists=image_path.is_file(),
                applicable_product_types=applicable_product_types,
                applicable_display_modes=_reference_field_text(
                    source, enrichment, "适用展示模式"
                ),
                framing=_reference_field_text(
                    source, enrichment, "人物取景范围"
                ),
                visible_body_regions=_reference_field_text(
                    source, enrichment, "可见身体区域"
                ),
                product_visibility=_reference_field_text(
                    source, enrichment, "产品预计展示面积"
                ),
                neck_visibility=_reference_field_text(
                    source, enrichment, "颈部可见度"
                ),
                collarbone_visibility=_reference_field_text(
                    source, enrichment, "锁骨可见度"
                ),
                chest_visibility=_reference_field_text(
                    source, enrichment, "胸前可见度"
                ),
                hand_visibility=_reference_field_text(
                    source, enrichment, "手部可见度"
                ),
                collar_type=_reference_field_text(source, enrichment, "衣领类型"),
                clothing_occlusion_risk=_reference_field_text(
                    source, enrichment, "衣物遮挡风险"
                ),
                hair_occlusion_risk=_reference_field_text(
                    source, enrichment, "头发遮挡风险"
                ),
                pose_keywords=_reference_field_text(
                    source, enrichment, "姿势关键词"
                ),
                mirror_relation=_reference_field_text(
                    source, enrichment, "镜面关系"
                ),
                existing_jewelry=_reference_field_text(
                    source, enrichment, "原有首饰类型"
                ),
                crop_risk=_reference_field_text(source, enrichment, "裁切风险"),
                hand_side=_reference_field_text(source, enrichment, "左右手"),
                visible_fingers=_reference_field_text(
                    source, enrichment, "可见手指"
                ),
                hand_orientation=_reference_field_text(
                    source, enrichment, "手部朝向"
                ),
                ring_face_visibility=_reference_field_text(
                    source, enrichment, "戒面可见度"
                ),
                finger_separation=_reference_field_text(
                    source, enrichment, "手指分离度"
                ),
                finger_occlusion_risk=_reference_field_text(
                    source, enrichment, "手指遮挡风险"
                ),
            )
        )
    if ignore_pending_enrichment and not rows:
        raise FeishuReferenceError("排除待补全素材后没有可用参考图")
    return rows


def _records_from_matrix(data: dict[str, Any]) -> list[dict[str, Any]]:
    field_names = data.get("fields", [])
    record_ids = data.get("record_id_list", [])
    rows = data.get("data", [])
    records = []
    for record_id, values in zip(record_ids, rows, strict=True):
        records.append(
            {
                "record_id": record_id,
                "fields": {
                    name: values[index] if index < len(values) else None
                    for index, name in enumerate(field_names)
                },
            }
        )
    return records


def _read_all_records(
    gateway: FeishuGateway,
    base_token: str,
    table_id: str,
    page_size: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = gateway.list_records(base_token, table_id, offset, page_size)
        page_records = list(page.get("records", []))
        records.extend(page_records)
        if not page.get("has_more"):
            return records
        if not page_records:
            raise FeishuReferenceError("飞书分页返回 has_more=true 但当前页无记录")
        offset += len(page_records)


def _missing_ai_fields(
    source_fields: dict[str, Any], resolved_enrichment: dict[str, str]
) -> list[str]:
    missing = [
        name
        for name in REQUIRED_AI_FIELD_NAMES
        if not resolved_enrichment.get(name)
    ]
    if _is_ring_worn_candidate(source_fields, resolved_enrichment):
        missing.extend(
            name
            for name in RING_REQUIRED_FIELD_NAMES
            if not resolved_enrichment.get(name)
        )
    return missing


def _validate_source_unchanged(
    record_id: str,
    manifest_item: dict[str, Any],
    current_fields: dict[str, Any],
) -> None:
    previous_fields = manifest_item.get("source_fields") or {}
    changed_fields = []
    for name in LEGACY_SOURCE_FIELD_NAMES:
        if name == "素材图片":
            previous_value = _attachment_identities(previous_fields.get(name))
            current_value = _attachment_identities(current_fields.get(name))
        else:
            previous_value = previous_fields.get(name)
            current_value = current_fields.get(name)
        if previous_value != current_value:
            changed_fields.append(name)

    previous_attachment = _attachment_identity(manifest_item.get("attachment"))
    current_attachments = _attachments(current_fields.get("素材图片"))
    current_attachment = _attachment_identity(
        current_attachments[0] if current_attachments else None
    )
    if previous_attachment != current_attachment and "素材图片" not in changed_fields:
        changed_fields.append("素材图片")
    if changed_fields:
        raise InvalidEnrichmentError(
            f"记录 {record_id} 的源字段已变化：{'、'.join(changed_fields)}；"
            "请重新执行 reference-sync 后再导入"
        )


def _attachment_identities(value: Any) -> tuple[tuple[str, str], ...]:
    return tuple(_attachment_identity(item) for item in _attachments(value))


def _attachment_identity(attachment: dict[str, Any] | None) -> tuple[str, str]:
    if not attachment:
        return ("", "")
    return (
        _field_text(attachment.get("file_token")),
        _field_text(attachment.get("name")),
    )


def _validate_ring_required_fields(
    record_id: str,
    source_fields: dict[str, Any],
    final_values: dict[str, str],
) -> None:
    if not _is_ring_worn_candidate(source_fields, final_values):
        return
    missing = [name for name in RING_REQUIRED_FIELD_NAMES if not final_values[name]]
    if missing:
        raise InvalidEnrichmentError(
            f"记录 {record_id} 的戒指佩戴候选缺少必需字段：{'、'.join(missing)}"
        )


def _is_ring_worn_candidate(
    source_fields: dict[str, Any], resolved_enrichment: dict[str, str]
) -> bool:
    product_types = _reference_field_text(
        source_fields, resolved_enrichment, "适用产品类型", "适用品类"
    )
    display_modes = _reference_field_text(
        source_fields, resolved_enrichment, "适用展示模式"
    )
    return _contains_annotation(
        product_types, RING_PRODUCT_TYPE_ALIASES
    ) and _contains_annotation(
        display_modes, WORN_DISPLAY_MODE_ALIASES
    )


def _contains_annotation(value: str, aliases: frozenset[str]) -> bool:
    tokens = {
        item.strip().lower()
        for item in re.split(r"[,，、;/|\s]+", value)
        if item.strip()
    }
    return bool(tokens & aliases)


def _pending_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": item["record_id"],
        "素材编号": _field_text(item["source_fields"].get("素材编号")),
        "image_path": item["image_path"],
        "source_fields": item["source_fields"],
        "required_fields": list(REQUIRED_AI_FIELD_NAMES),
        "optional_fields": list(OPTIONAL_REFERENCE_FIELD_NAMES),
        "missing_fields": item["missing_ai_fields"],
    }


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    fields = record.get("fields") or {}
    return (_field_text(fields.get("素材编号")), str(record.get("record_id") or ""))


def _source_fingerprint(
    record_id: str,
    fields: dict[str, Any],
    attachment: dict[str, Any] | None,
    source_field_names: tuple[str, ...] = SOURCE_FIELD_NAMES,
) -> str:
    data = {
        "record_id": record_id,
        "fields": {
            name: fields.get(name)
            for name in source_field_names
            if name != "素材图片"
        },
        "attachment": attachment,
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _matches_legacy_source_fingerprint(
    previous: dict[str, Any],
    record_id: str,
    fields: dict[str, Any],
    attachment: dict[str, Any] | None,
) -> bool:
    previous_fields = previous.get("source_fields")
    if not isinstance(previous_fields, dict):
        return False
    if any(name in previous_fields for name in OPTIONAL_REFERENCE_FIELD_NAMES):
        return False
    if any(_field_text(fields.get(name)) for name in OPTIONAL_REFERENCE_FIELD_NAMES):
        return False
    return previous.get("source_fingerprint") == _source_fingerprint(
        record_id, fields, attachment, LEGACY_SOURCE_FIELD_NAMES
    )


def _attachments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and item.get("file_token")]


def _field_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("name") or item.get("text") or ""
            else:
                text = item
            text = str(text).strip()
            if text:
                result.append(text)
        return result
    text = str(value).strip()
    return [text] if text else []


def _field_text(value: Any) -> str:
    return "、".join(_field_values(value))


def _reference_field_text(
    source: dict[str, Any],
    enrichment: dict[str, Any],
    *field_names: str,
) -> str:
    for field_name in field_names:
        value = _field_text(enrichment.get(field_name)) or _field_text(
            source.get(field_name)
        )
        if value:
            return value
    return ""


def _join_field(value: Any) -> str:
    return "、".join(_field_values(value))


def _bracelet_applicability(categories: list[str]) -> str:
    target = [item for item in categories if item in {"手串", "手链", "手镯", "通用"}]
    if not target:
        return "否：未标记手链手串适用"
    return f"是：适用于{'、'.join(target)}"


def _merge_notes(number: str, notes: str) -> str:
    return f"素材编号：{number}；{notes}" if number else notes


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    data = path.read_bytes()[:32]
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:3] == b"GIF" and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(path)
    return None, None


def _jpeg_dimensions(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        handle.read(2)
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_raw = handle.read(2)
            if len(length_raw) != 2:
                break
            length = struct.unpack(">H", length_raw)[0]
            if marker and marker[0] in range(0xC0, 0xC4):
                payload = handle.read(5)
                if len(payload) == 5:
                    height, width = struct.unpack(">HH", payload[1:5])
                    return width, height
                break
            handle.seek(max(length - 2, 0), 1)
    return None, None


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise FeishuReferenceError(f"缺少必需值：{name}")
    return text


def _safe_file_stem(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "-" for character in value)
    return safe.strip("-_") or "reference"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeishuReferenceError(f"无法读取缓存 JSON：{path}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


