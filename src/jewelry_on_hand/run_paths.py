from __future__ import annotations

import json
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def create_run_id(prefix: str = "auto-reference") -> str:
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]+", "-", prefix).strip("-_")
    if not safe_prefix:
        safe_prefix = "auto-reference"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    suffix = secrets.token_hex(8)
    return f"{safe_prefix}-{timestamp}-{suffix}"


@dataclass(frozen=True)
class RunPaths:
    root: Path

    @classmethod
    def create(cls, output_root: str | Path, run_id: str) -> "RunPaths":
        if not _is_safe_run_id(run_id):
            raise ValueError(f"不安全的 run_id: {run_id!r}")
        root = Path(output_root) / run_id
        paths = cls(root=root)
        for directory in (
            paths.input_dir,
            paths.analysis_dir,
            paths.review_dir,
            paths.generation_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def analysis_dir(self) -> Path:
        return self.root / "analysis"

    @property
    def review_dir(self) -> Path:
        return self.root / "review"

    @property
    def generation_dir(self) -> Path:
        return self.root / "generation"

    def copy_product_image(self, source: str | Path) -> Path:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        destination = self.input_dir / "product-on-hand.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return destination


def _is_safe_run_id(run_id: str) -> bool:
    if not run_id:
        return False
    if "/" in run_id or "\\" in run_id:
        return False
    if run_id in {".", ".."} or Path(run_id).is_absolute():
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        return False
    if run_id.endswith(".") or set(run_id) == {"."}:
        return False
    base_name = run_id.split(".", 1)[0].upper()
    return base_name not in _WINDOWS_RESERVED_NAMES


def write_json(path: str | Path, data: Any) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
