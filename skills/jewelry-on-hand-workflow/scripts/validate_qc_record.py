from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_STATUS = {"pass", "rerun", "reject"}
SOURCE_WRIST_TERMS = ("原图手腕", "源图手腕", "source wrist", "source-wrist", "粗手腕")
SOURCE_ARM_TERMS = ("原图手臂", "源图手臂", "source-arm", "source arm", "局部手臂")
SOURCE_SKIN_TERMS = ("皮肤块", "局部贴片", "肤色", "皮肤纹理")
NEGATED_CHECK_TERMS = ("没有检查", "未检查", "没检查", "未做检查", "没有做检查", "未明确检查")
PASS_CHECK_TERMS = ("检查通过", "迁移检查通过", "来源一致性通过", "未发现", "未见", "无迁移", "没有迁移", "无源图手臂局部贴片")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def validate_qc(path: Path) -> list[str]:
    data = _load_json(path)
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["qc file must contain a JSON object"]

    status = data.get("status")
    if status not in ALLOWED_STATUS:
        errors.append("status must be pass/rerun/reject")

    for key in ("passed", "failed"):
        if not isinstance(data.get(key), list):
            errors.append(f"{key} must be a list")
    if not isinstance(data.get("notes"), str):
        errors.append("notes must be a string")

    passed = data.get("passed") if isinstance(data.get("passed"), list) else []
    failed = data.get("failed") if isinstance(data.get("failed"), list) else []
    notes = data.get("notes") if isinstance(data.get("notes"), str) else ""
    combined = " ".join(str(item) for item in passed + failed) + " " + notes

    if not _contains_any(combined, SOURCE_WRIST_TERMS):
        errors.append("qc must mention source wrist/original wrist check")
    if not _contains_any(combined, SOURCE_ARM_TERMS):
        errors.append("qc must mention source arm/original arm check")
    if not _contains_any(combined, SOURCE_SKIN_TERMS):
        errors.append("qc must mention source skin patch/skin continuity check")
    if _contains_any(combined, NEGATED_CHECK_TERMS):
        errors.append("qc must not say the source-arm/source-wrist check was not performed")

    if status == "pass":
        if failed:
            errors.append("status pass requires failed to be empty")
        if not _contains_any(combined, PASS_CHECK_TERMS):
            errors.append("status pass must explicitly state the source-arm/source-wrist check passed")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_qc_record.py <qc.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"qc file not found: {path}", file=sys.stderr)
        return 2
    errors = validate_qc(path)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("qc record OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
