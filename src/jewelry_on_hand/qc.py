from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jewelry_on_hand.models import QcResult
from jewelry_on_hand.run_paths import write_json


_ALLOWED_STATUS = {"pass", "rerun", "reject"}


def write_qc_result(
    generation_dir: str | Path,
    status: str,
    passed: Any,
    failed: Any,
    notes: Any,
    fidelity_checks: Any = None,
) -> Path:
    if status not in _ALLOWED_STATUS:
        raise ValueError("status 必须是 pass/rerun/reject")

    result = QcResult(
        status=status,
        passed=tuple(_normalize_string_list(passed)),
        failed=tuple(_normalize_string_list(failed)),
        notes="" if notes is None else str(notes),
        fidelity_checks=tuple(_normalize_fidelity_checks(fidelity_checks)),
    )
    qc_path = Path(generation_dir) / "qc.json"
    write_json(
        qc_path,
        {
            "status": result.status,
            "passed": list(result.passed),
            "failed": list(result.failed),
            "notes": result.notes,
            "fidelity_checks": [check.to_dict() for check in result.fidelity_checks],
        },
    )
    return qc_path


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return [_to_readable_string(value)]
    if isinstance(value, Iterable):
        return [_to_readable_string(item) for item in value]
    return [_to_readable_string(value)]


def _to_readable_string(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return str(value)
    return str(value)


def _normalize_fidelity_checks(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("fidelity_checks 必须是列表")
    return value
