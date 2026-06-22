from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_SKILLS = ("jewelry-on-hand-workflow",)
EXCLUDED_NAMES = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    _prefer_utf8_output()
    args = _parse_args()
    codex_home = Path(args.codex_home or os.environ.get("CODEX_HOME") or _default_codex_home())
    destination_root = codex_home / "skills"
    skills = args.skill or list(DEFAULT_SKILLS)

    for skill in skills:
        source = PROJECT_SKILLS_DIR / skill
        if not source.is_dir():
            raise SystemExit(f"找不到项目内 Skill：{source}")
        _install_skill(source, destination_root / skill, force=args.force, dry_run=args.dry_run)

    print(f"安装完成。请重启 Codex 以加载更新后的 Skill。目标目录：{destination_root}")
    return 0


def _prefer_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把项目内的 Codex Skill 安装到 CODEX_HOME/skills，便于多人/多电脑复用。"
    )
    parser.add_argument(
        "--skill",
        action="append",
        help="要安装的 Skill 名称；可重复。默认只安装 jewelry-on-hand-workflow。",
    )
    parser.add_argument(
        "--codex-home",
        help="Codex home 目录；默认读取 CODEX_HOME，未设置时使用用户目录下的 .codex。",
    )
    parser.add_argument("--force", action="store_true", help="目标已存在时先删除再安装。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要安装的路径，不写入文件。")
    return parser.parse_args()


def _default_codex_home() -> Path:
    return Path.home() / ".codex"


def _install_skill(source: Path, destination: Path, *, force: bool, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] {source} -> {destination}")
        return

    if destination.exists():
        if not force:
            raise SystemExit(f"目标 Skill 已存在：{destination}。如需覆盖，请加 --force。")
        _safe_remove_existing(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=_ignore_skill_files)
    print(f"已安装 {source.name} -> {destination}")


def _safe_remove_existing(destination: Path) -> None:
    resolved = destination.resolve()
    expected_parent = (destination.parent).resolve()
    if resolved.parent != expected_parent or resolved.name in {"", ".", ".."}:
        raise SystemExit(f"拒绝删除异常目标目录：{destination}")
    shutil.rmtree(resolved)


def _ignore_skill_files(directory: str, names: list[str]) -> set[str]:
    root = Path(directory)
    ignored: set[str] = set()
    for name in names:
        candidate = root / name
        if name in EXCLUDED_NAMES or candidate.suffix in EXCLUDED_SUFFIXES:
            ignored.add(name)
            continue
        if root.name == "references" and name == "config.json":
            ignored.add(name)
    return ignored


if __name__ == "__main__":
    raise SystemExit(main())
