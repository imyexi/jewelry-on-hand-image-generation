from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


TOP_LEVEL_FIELDS = frozenset(
    {
        "rank",
        "reference_file",
        "reference_sha256",
        "output_role",
        "framing",
        "camera_angle",
        "subject_placement",
        "visible_body_regions",
        "pose",
        "clothing",
        "background",
        "lighting",
        "replacement_target",
        "other_jewelry_to_remove",
        "text_or_ui_risk",
        "product_visibility_sufficient",
        "composition_signature",
    }
)
POSE_FIELDS = frozenset({"body", "arm", "hand", "hand_side"})
TARGET_FIELDS = frozenset({"body_region", "source_jewelry", "target_product_count"})
ALLOWED_ROLES = frozenset({"hand_worn", "lifestyle"})
ALLOWED_UI_RISKS = frozenset({"none", "small_removable", "blocking"})


class SnapshotInputError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotInputError(f"JSON 包含重复字段：{key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SnapshotInputError(f"无法按 UTF-8 读取文件：{path}") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, SnapshotInputError) as exc:
        raise SnapshotInputError(f"文件不是有效 JSON：{path}；{exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SnapshotInputError(f"无法读取参考图：{path}") from exc
    return digest.hexdigest()


def _closed_fields(value: Any, fields: frozenset[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} 必须是 JSON 对象"]
    actual = set(value)
    errors: list[str] = []
    missing = sorted(fields - actual)
    extra = sorted(actual - fields)
    if missing:
        errors.append(f"{label} 缺少字段：{'、'.join(missing)}")
    if extra:
        errors.append(f"{label} 包含未知字段：{'、'.join(extra)}")
    return errors


def _nonempty_string(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} 必须是非空字符串")


def _string_list(value: Any, field: str, errors: list[str], *, allow_empty: bool) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{field} 必须是非空字符串组成的 JSON 列表")
    elif not allow_empty and not value:
        errors.append(f"{field} 不能为空列表")


def _signature(data: dict[str, Any]) -> str:
    projection = {
        "output_role": data.get("output_role"),
        "framing": data.get("framing"),
        "pose": data.get("pose"),
        "background": data.get("background"),
        "lighting": data.get("lighting"),
        "replacement_target": data.get("replacement_target"),
    }
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_reference_snapshot(
    snapshot_path: Path,
    reference_path: Path,
    output_role: str,
) -> list[str]:
    data = _load_json(snapshot_path)
    if not isinstance(data, dict):
        return ["参考构图快照必须是 JSON 对象"]
    errors = _closed_fields(data, TOP_LEVEL_FIELDS, "参考构图快照")
    if errors:
        return errors

    rank = data["rank"]
    if type(rank) is not int or rank < 1:
        errors.append("rank 必须是大于等于 1 的 JSON 整数，不能使用布尔值")
    if output_role not in ALLOWED_ROLES:
        errors.append("output_role 参数只能是 hand_worn 或 lifestyle")
    if data["output_role"] != output_role:
        errors.append("快照 output_role 与请求角色不一致")
    if data["output_role"] not in ALLOWED_ROLES:
        errors.append("快照 output_role 只能是 hand_worn 或 lifestyle，拒绝 hero")

    for field in (
        "reference_file",
        "reference_sha256",
        "framing",
        "camera_angle",
        "subject_placement",
        "clothing",
        "background",
        "lighting",
        "composition_signature",
    ):
        _nonempty_string(data[field], field, errors)
    _string_list(data["visible_body_regions"], "visible_body_regions", errors, allow_empty=False)
    _string_list(data["other_jewelry_to_remove"], "other_jewelry_to_remove", errors, allow_empty=True)

    pose = data["pose"]
    errors.extend(_closed_fields(pose, POSE_FIELDS, "pose"))
    if isinstance(pose, dict) and set(pose) == POSE_FIELDS:
        for field in sorted(POSE_FIELDS):
            _nonempty_string(pose[field], f"pose.{field}", errors)

    target = data["replacement_target"]
    errors.extend(_closed_fields(target, TARGET_FIELDS, "replacement_target"))
    if isinstance(target, dict) and set(target) == TARGET_FIELDS:
        _nonempty_string(target["body_region"], "replacement_target.body_region", errors)
        _nonempty_string(target["source_jewelry"], "replacement_target.source_jewelry", errors)
        if type(target["target_product_count"]) is not int or target["target_product_count"] != 1:
            errors.append("replacement_target.target_product_count 必须是 JSON 整数 1，不能使用布尔值")

    if type(data["product_visibility_sufficient"]) is not bool:
        errors.append("product_visibility_sufficient 必须是 JSON 布尔值")
    elif not data["product_visibility_sufficient"]:
        errors.append("产品预计展示面积不足")
    if data["text_or_ui_risk"] not in ALLOWED_UI_RISKS:
        errors.append("text_or_ui_risk 必须是 none/small_removable/blocking")
    elif data["text_or_ui_risk"] == "blocking":
        errors.append("参考图存在阻断性的文字或 UI")

    if not reference_path.is_file():
        raise SnapshotInputError(f"参考图不存在：{reference_path}")
    if data["reference_file"] != reference_path.name:
        errors.append("reference_file 与实际参考图文件名不一致")
    if data["reference_sha256"] != _sha256(reference_path):
        errors.append("reference_sha256 与实际参考图摘要不一致")
    if data["composition_signature"] != _signature(data):
        errors.append("composition_signature 与固定构图投影不一致")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="离线校验参考构图快照")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output-role", required=True, choices=sorted(ALLOWED_ROLES))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        if not args.snapshot.is_file():
            print(f"快照文件不存在：{args.snapshot}", file=sys.stderr)
            return 2
        errors = validate_reference_snapshot(args.snapshot, args.reference, args.output_role)
    except SnapshotInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("参考构图快照校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
