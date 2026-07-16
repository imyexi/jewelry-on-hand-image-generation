from __future__ import annotations

import json
import sys
from pathlib import Path

from generation_contract import GenerationContractError, validate_qc_record


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("用法：validate_qc_record.py <qc.json> <fidelity_constraints.json>", file=sys.stderr)
        return 2
    try:
        qc = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        constraints = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        validate_qc_record(qc, constraints)
    except (OSError, UnicodeError, json.JSONDecodeError, GenerationContractError) as exc:
        print(str(exc) if isinstance(exc, GenerationContractError) else f"无法读取 QC 契约输入：{exc}", file=sys.stderr)
        return 1
    print("qc record OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
