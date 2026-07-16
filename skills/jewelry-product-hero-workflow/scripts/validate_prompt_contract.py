from __future__ import annotations

import json
import sys
from pathlib import Path

from generation_contract import validate_prompt_contract


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("用法：validate_prompt_contract.py <prompt.txt> <input_order.json>", file=sys.stderr)
        return 2
    try:
        prompt = Path(args[0]).read_text(encoding="utf-8")
        input_order = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"无法读取 Prompt 契约输入：{exc}", file=sys.stderr)
        return 1
    errors = validate_prompt_contract(prompt, input_order)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("prompt contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
