from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
SKILL = PROJECT_ROOT / "skills" / "jewelry-product-hero-workflow"
SKILL_MD = SKILL / "SKILL.md"
OPENAI_YAML = SKILL / "agents" / "openai.yaml"
PROJECT_REFERENCE = PROJECT_ROOT / "reference" / "product-hero-workflow.md"
INSTALLER = PROJECT_ROOT / "scripts" / "install_codex_skills.py"


def test_product_hero_skill_metadata_and_package_shape() -> None:
    assert SKILL_MD.is_file()
    text = SKILL_MD.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1].strip().splitlines()
    assert len(frontmatter) == 2
    assert frontmatter[0] == "name: jewelry-product-hero-workflow"
    assert frontmatter[1].startswith("description: Use when ")
    for keyword in ("主图", "正面图", "侧视图", "细节图", "飞书", "Top 3", "QC"):
        assert keyword in frontmatter[1]

    forbidden = (
        "C:\\Users\\Administrator",
        "C:/Users/Administrator",
        "\\Documents\\珠宝上手图片生成",
    )
    assert all(fragment not in text for fragment in forbidden)
    assert sorted(path.relative_to(SKILL).as_posix() for path in SKILL.rglob("*.md")) == [
        "SKILL.md"
    ]


def test_product_hero_skill_ui_metadata_matches_contract() -> None:
    assert OPENAI_YAML.is_file()
    text = OPENAI_YAML.read_text(encoding="utf-8")
    assert 'display_name: "珠宝产品主图工作流"' in text
    assert 'short_description: "从多视角商品照和飞书参考图生成高保真珠宝产品主图流程"' in text
    assert (
        'default_prompt: "使用 $jewelry-product-hero-workflow，根据产品正面图、侧视图和细节图，'
        '从飞书主图库选择参考并生成一张通过 QC 的主图。"'
    ) in text


def test_product_hero_skill_encodes_non_negotiable_gates_and_scripts() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    required = (
        "禁止使用通用素材补位",
        "禁止自动选择",
        "显式选择 rank",
        "不得把深色背景作为硬 gate",
        "少于 3 张",
        "四个硬 gate",
        "一个商品单元",
        "成对耳饰",
        "两次非 pass",
        "Nano Banana V2",
        "最多 4 个",
        "只有 pass",
        "默认只读飞书",
        "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink",
        "lark-wiki",
        "lark-base",
        "lark-drive",
        "out_task_id",
        "用户选择证据",
        "实体总数",
        "参考图原商品的数量",
        "遮挡只改变可见数量",
        "component_count_checks",
        "component_count_mismatch",
        "任意本地 PNG",
        "product_hero_workflow.py",
        "reference_review.py",
        "generation_contract.py",
        "validate_prompt_contract.py",
        "validate_qc_record.py",
        "reference/product-hero-workflow.md",
    )
    for fragment in required:
        assert fragment in text


def test_project_reference_is_complete_and_kept_outside_skill() -> None:
    assert PROJECT_REFERENCE.is_file()
    text = PROJECT_REFERENCE.read_text(encoding="utf-8")
    required = (
        "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink",
        "AI生图参考图素材库",
        "素材收录池",
        "图片类型",
        "主图",
        "适用品类",
        "正面图",
        "侧视图",
        "1–4 张细节图",
        "禁止使用通用素材补位",
        "Top 3",
        "显式选择",
        "GPT Image 2",
        "Nano Banana V2",
        "AIReiter",
        "pass",
        "rerun",
        "reject",
        "final/result.png",
        "pagination_complete",
        "request_contract",
        "selected_output_url",
        "user_selection_evidence",
        "component_counts",
        "visible_count",
        "occluded_count",
    )
    for fragment in required:
        assert fragment in text


def test_default_installer_copies_workflows_and_aireiter_without_caches(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(tmp_path / "codex-home")
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(INSTALLER), "--force"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    installed_root = Path(env["CODEX_HOME"]) / "skills"
    for name in (
        "jewelry-on-hand-workflow",
        "jewelry-product-hero-workflow",
        "aireiter-image-generation",
    ):
        installed = installed_root / name
        assert (installed / "SKILL.md").is_file()
        assert not list(installed.rglob("__pycache__"))
        assert not list(installed.rglob("*.pyc"))

    hero_scripts = installed_root / "jewelry-product-hero-workflow" / "scripts"
    installed_hero_text = (
        installed_root / "jewelry-product-hero-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert (
        "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink"
        in installed_hero_text
    )
    aireiter = installed_root / "aireiter-image-generation"
    assert (aireiter / "scripts" / "aireiter_image_helper.py").is_file()
    assert not (aireiter / "references" / "config.json").exists()
    import_check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(hero_scripts)!r}); "
                "import product_hero_workflow, reference_review, generation_contract"
            ),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert import_check.returncode == 0, import_check.stderr
