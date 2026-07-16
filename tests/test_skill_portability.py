from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import jewelry_on_hand.reference_composition as reference_composition
from jewelry_on_hand.qc import build_qc_checklist, write_qc_result
from jewelry_on_hand.cli import _build_parser, main as cli_main
from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductConfirmationSnapshot,
    ProductFidelityConstraints,
    ReferenceRow,
    ScoredReference,
)
from jewelry_on_hand.output_roles import OutputRole
from jewelry_on_hand.product_analysis import product_analysis_to_dict
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.prompt_builder import build_generation_prompt
from jewelry_on_hand.qc_review import build_reference_preservation_checklist
from jewelry_on_hand.reference_composition import (
    ReferenceCompositionSnapshot,
    ReferencePose,
    ReplacementTarget,
)
from jewelry_on_hand.run_paths import RunPaths
from jewelry_on_hand.review_decision import ReviewGateError, require_generation_decision


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SKILL = PROJECT_ROOT / "skills" / "jewelry-on-hand-workflow"
INSTALLER = PROJECT_ROOT / "scripts" / "install_codex_skills.py"
ARTIFACT_INSPECTOR = WORKFLOW_SKILL / "scripts" / "inspect_run_artifacts.py"
QC_VALIDATOR = WORKFLOW_SKILL / "scripts" / "validate_qc_record.py"
PROMPT_VALIDATOR = WORKFLOW_SKILL / "scripts" / "validate_prompt_contract.py"
SNAPSHOT_VALIDATOR = WORKFLOW_SKILL / "scripts" / "validate_reference_snapshot.py"
PROJECT_GUIDE = PROJECT_ROOT / "CLAUDE.md"
MANUAL_WORKFLOW = PROJECT_ROOT / "reference" / "manual-workflow.md"
FIDELITY_SCHEMA = PROJECT_ROOT / "reference" / "product-fidelity-constraints-schema.md"
REVIEW_DECISION_SCHEMA = PROJECT_ROOT / "reference" / "review-decision-schema.md"
PORTABLE_WORKFLOW = WORKFLOW_SKILL / "references" / "workflow.md"
TROUBLESHOOTING = WORKFLOW_SKILL / "references" / "troubleshooting.md"
PROMPT_CONTRACT = WORKFLOW_SKILL / "references" / "prompt-contract.md"
REFERENCE_COMPOSITION_CONTRACT = (
    WORKFLOW_SKILL / "references" / "reference-composition-contract.md"
)
PORTABLE_QC = WORKFLOW_SKILL / "references" / "qc-checklist.md"
PROJECT_PROMPT = PROJECT_ROOT / "reference" / "prompt-template.md"
PROJECT_QC = PROJECT_ROOT / "reference" / "qc-checklist.md"
FEISHU_REFERENCE_SOURCE = PROJECT_ROOT / "reference" / "feishu-reference-source.md"
WORKFLOW_DESIGN = (
    PROJECT_ROOT
    / "reference"
    / "superpowers"
    / "specs"
    / "2026-06-12-jewelry-on-hand-generation-workflow-design.md"
)
REFERENCE_REPLACEMENT_DOCUMENTS = (
    WORKFLOW_SKILL / "SKILL.md",
    PORTABLE_WORKFLOW,
    PROMPT_CONTRACT,
    PORTABLE_QC,
    TROUBLESHOOTING,
    MANUAL_WORKFLOW,
    PROJECT_PROMPT,
    PROJECT_QC,
    REVIEW_DECISION_SCHEMA,
    FEISHU_REFERENCE_SOURCE,
    WORKFLOW_DESIGN,
)
CURRENT_DOCUMENTS = (
    PROJECT_GUIDE,
    MANUAL_WORKFLOW,
    WORKFLOW_SKILL / "SKILL.md",
    PORTABLE_WORKFLOW,
    FIDELITY_SCHEMA,
)
MODERN_ATOMIC_CONTRACT = (
    "五个现代分类字段 `detected_product_type`、`confirmed_product_type`、"
    "`classification_confidence`、`classification_evidence`、`classification_source` "
    "是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。"
)
LEGACY_EXPLICIT_CONTRACT = (
    "历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、"
    "`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。"
)


def _document_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_skill_declares_reference_base_replacement_scope_and_progressive_routes() -> None:
    skill_path = WORKFLOW_SKILL / "SKILL.md"
    text = _document_text(skill_path)
    frontmatter = text.split("---", 2)[1]
    keys = [line.split(":", 1)[0] for line in frontmatter.splitlines() if ":" in line]

    assert keys == ["name", "description"]
    assert "只支持 `hand_worn` 和 `lifestyle`" in text
    assert "参考底图是画面结构唯一来源" in text
    assert "产品上手图只提供珠宝身份" in text
    assert "主图必须交给独立主图 Skill" in text
    assert "hand-reference" not in text
    for reference in (
        "references/workflow.md",
        "references/prompt-contract.md",
        "references/reference-composition-contract.md",
        "references/qc-checklist.md",
        "references/troubleshooting.md",
    ):
        assert reference in text
    for forbidden in (
        "三图输出角色",
        "分别创建独立 run",
        "`hero` 为产品主体近景",
        "深色背景主图例外",
    ):
        assert forbidden not in text


@pytest.mark.parametrize("document", [MANUAL_WORKFLOW, PORTABLE_WORKFLOW, WORKFLOW_DESIGN])
def test_operator_workflows_share_reference_replacement_lifecycle(document: Path) -> None:
    text = _document_text(document)

    assert "prepare-review -> record-decision -> generate -> qc" in text
    assert "--output-role" in text
    assert "`图片类型` 字段是角色唯一来源" in text
    assert "五输入" in text and "input-manifest.json" in text
    for input_name in (
        "scene-reference",
        "product-reference",
        "reference-composition-snapshot.json",
        "product-analysis.json",
        "product-fidelity-constraints.json",
    ):
        assert input_name in text
    for state in ("modern_snapshot", "legacy_read_only", "damaged"):
        assert state in text
    for layer in ("reference_preservation", "fidelity_checks", "checklist_checks"):
        assert layer in text


@pytest.mark.parametrize("document", [PROJECT_PROMPT, PROMPT_CONTRACT])
def test_prompt_documents_lock_the_reference_base_and_product_identity_roles(
    document: Path,
) -> None:
    text = _document_text(document)

    assert "以参考底图为底图进行编辑" in text
    assert "参考底图是人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置的唯一来源" in text
    assert "产品上手图只提供目标珠宝身份" in text
    assert "只允许移除参考图原首饰并在同一位置换入一件目标产品" in text
    assert "必要接触阴影" in text
    assert "小面积水印" in text
    assert "1200" in text


@pytest.mark.parametrize("document", [PROJECT_QC, PORTABLE_QC])
def test_qc_documents_require_three_layers_and_reference_evidence(document: Path) -> None:
    text = _document_text(document)

    for layer in ("reference_preservation", "fidelity_checks", "checklist_checks"):
        assert layer in text
    for outcome in ("pass", "rerun", "reject"):
        assert outcome in text
    assert "十项 reference evidence" in text
    assert "critical_failures" in text


def test_reference_replacement_documents_reject_legacy_writes_and_old_claims() -> None:
    forbidden_claims = (
        "参考图只提供氛围",
        "参考图仅提供氛围",
        "产品图提供构图",
        "历史 run 可继续生成",
        "人物和场景可以依据参考图重新生成",
        "新 run 写 `hand-reference",
    )

    for document in REFERENCE_REPLACEMENT_DOCUMENTS:
        text = _document_text(document)
        assert not any(claim in text for claim in forbidden_claims), document

    for document in (MANUAL_WORKFLOW, PORTABLE_WORKFLOW, TROUBLESHOOTING, WORKFLOW_DESIGN):
        text = _document_text(document)
        assert "历史 run" in text
        assert "只读" in text
        assert "不得追加" in text
        assert "重新执行 `prepare-review`" in text


def test_revised_documents_preserve_necklace_ring_fidelity_and_feishu_audit() -> None:
    combined = "\n".join(_document_text(path) for path in REFERENCE_REPLACEMENT_DOCUMENTS)

    for phrase in (
        "schema_version=2",
        "pendant_semantics",
        "ring_count",
        "hand_side",
        "finger_position",
        "ring_wear_style",
        "canonical",
        "pending_enrichment",
        "CAS",
    ):
        assert phrase in combined


@pytest.mark.parametrize("document", [MANUAL_WORKFLOW, PORTABLE_WORKFLOW])
def test_documented_qc_pass_command_omits_empty_critical_failures_flag(
    document: Path,
) -> None:
    text = _document_text(document)
    match = re.search(
        r"```powershell\s*\n(?P<command>jewelry-on-hand qc\b.*?)\n```",
        text,
        flags=re.DOTALL,
    )

    assert match is not None, f"{document} 缺少正式 qc PowerShell 示例"
    command = match.group("command")
    assert "--status pass" in command
    assert "--critical-failures" not in command


def test_qc_pass_argv_keeps_critical_failures_unset() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "qc",
            "--generation-dir",
            "generation/01",
            "--status",
            "pass",
            "--reference-preservation-checks-json",
            "reference.json",
            "--fidelity-checks-json",
            "fidelity.json",
            "--checklist-checks-json",
            "checklist.json",
        ]
    )

    assert args.critical_failures is None


def test_design_spec_scopes_output_role_to_the_commands_that_accept_it() -> None:
    text = _document_text(WORKFLOW_DESIGN)

    assert "所有命令显式使用 `--output-role" not in text
    assert "`prepare-review` 与 `record-decision` 显式传 `--output-role`" in text
    assert "`generate` 与 `qc` 从 run 固化角色读取并复核" in text


def test_skill_structure_and_openai_metadata_are_deterministic() -> None:
    skill_text = _document_text(WORKFLOW_SKILL / "SKILL.md")
    links = re.findall(
        r"\[[^]]+\]\((references/(?:workflow|prompt-contract|"
        r"reference-composition-contract|qc-checklist|troubleshooting)\.md)\)",
        skill_text,
    )

    assert len(skill_text.splitlines()) < 500
    assert links == [
        "references/workflow.md",
        "references/prompt-contract.md",
        "references/reference-composition-contract.md",
        "references/qc-checklist.md",
        "references/troubleshooting.md",
    ]
    assert _document_text(WORKFLOW_SKILL / "agents" / "openai.yaml") == (
        'interface:\n'
        '  display_name: "Jewelry Scene Replacement"\n'
        '  short_description: "严格保留真人参考图构图、人物与光线并仅替换为目标珠宝首饰"\n'
        '  default_prompt: "Use $jewelry-on-hand-workflow to replace jewelry in a '
        'hand-worn or lifestyle reference while preserving the reference composition."\n'
    )


@pytest.mark.parametrize(
    "document",
    [WORKFLOW_SKILL / "SKILL.md", PORTABLE_WORKFLOW, MANUAL_WORKFLOW],
)
def test_operator_documents_assign_real_provider_proof_to_task12(document: Path) -> None:
    text = _document_text(document)

    assert "真实第三方模型 proof 属于 Task 12" in text
    assert "真实第三方模型 proof 属于 Task 11" not in text


def test_base_image_便携提示词校验器公开快照绑定签名() -> None:
    namespace = runpy.run_path(str(PROMPT_VALIDATOR))
    parameters = inspect.signature(namespace["validate_prompt"]).parameters

    assert tuple(parameters) == (
        "prompt_path",
        "snapshot_path",
        "analysis_path",
        "canonical_path",
    )
    assert parameters["prompt_path"].default is inspect.Parameter.empty
    assert all(
        parameters[name].default is None
        for name in ("snapshot_path", "analysis_path", "canonical_path")
    )


def test_reference_preservation_历史单参数校验只读且不能充当现代门禁(
    tmp_path: Path,
) -> None:
    prompt_path = tmp_path / "legacy-prompt.txt"
    prompt_path.write_text("损坏的历史 Prompt", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(PROMPT_VALIDATOR), str(prompt_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 1
    assert "legacy_read_only=true" in completed.stdout
    assert "不能作为新 generation gate" in completed.stdout


@pytest.mark.parametrize(
    "document",
    [PROJECT_GUIDE, MANUAL_WORKFLOW, WORKFLOW_SKILL / "SKILL.md", PORTABLE_WORKFLOW],
)
def test_current_workflow_documents_describe_multi_category_generation_boundary(
    document: Path,
) -> None:
    text = _document_text(document)

    for product_type in (
        "bracelet",
        "necklace",
        "pendant_necklace",
        "pendant_only",
        "unknown",
    ):
        assert product_type in text, f"{document} 缺少品类边界 {product_type}"
    for display_mode in ("worn", "hand_held"):
        assert display_mode in text, f"{document} 缺少展示模式 {display_mode}"
    assert "worn_source" in text
    assert "1 至 3 层" in text
    assert "多件独立" in text
    assert "自动补链" in text
    assert "不可见" in text and "推断" in text


@pytest.mark.parametrize("document", [MANUAL_WORKFLOW, PORTABLE_WORKFLOW])
def test_operator_workflows_lock_cli_stages_reference_sources_and_canonical_gate(
    document: Path,
) -> None:
    text = _document_text(document)

    for command in ("prepare-review", "record-decision", "generate", "qc"):
        assert command in text, f"{document} 缺少 CLI 阶段 {command}"
    assert "--classification" in text
    assert "显式" in text and "优先" in text
    assert "飞书" in text
    assert "--fidelity-constraints-path" in text
    assert "导入源" in text
    assert "analysis/product_fidelity_constraints.json" in text
    assert "非标准" in text and "拒绝" in text
    assert "完整产品确认快照" in text
    assert "fidelity_confirmed" in text


@pytest.mark.parametrize("document", [MANUAL_WORKFLOW, PORTABLE_WORKFLOW])
def test_operator_workflows_use_the_same_four_stage_order(document: Path) -> None:
    text = _document_text(document)
    positions = [text.index(f"`{command}`") for command in (
        "prepare-review", "record-decision", "generate", "qc"
    )]

    assert positions == sorted(positions)


def test_documented_cli_flags_exist_on_the_real_subcommand_parsers() -> None:
    parser = _build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    expected = {
        "prepare-review": {"--product-image", "--analysis-json", "--classification"},
        "record-decision": {
            "--run-root", "--action", "--fidelity-confirmed", "--fidelity-constraints-path"
        },
        "generate": {"--run-root", "--helper-script"},
        "qc": {"--generation-dir", "--status", "--fidelity-checks-json", "--critical-failures"},
    }

    for command, flags in expected.items():
        real_flags = {
            option
            for action in subparsers.choices[command]._actions
            for option in action.option_strings
        }
        assert flags <= real_flags
        for document in (MANUAL_WORKFLOW, PORTABLE_WORKFLOW):
            text = _document_text(document)
            assert flags <= {flag for flag in flags if flag in text}


@pytest.mark.parametrize("document", CURRENT_DOCUMENTS)
def test_current_documents_share_exact_legacy_contracts(document: Path) -> None:
    text = _document_text(document)

    assert MODERN_ATOMIC_CONTRACT in text
    assert LEGACY_EXPLICIT_CONTRACT in text


def test_current_documents_never_describe_the_whole_system_as_bracelet_only() -> None:
    forbidden = ("系统只支持手串", "系统仅支持手串", "全系统只支持手腕", "全系统仅支持手腕")

    for document in CURRENT_DOCUMENTS + (TROUBLESHOOTING,):
        text = _document_text(document)
        assert not any(fragment in text for fragment in forbidden), document


def test_reachable_source_files_have_no_question_mark_mojibake() -> None:
    source_root = PROJECT_ROOT / "src" / "jewelry_on_hand"

    for path in source_root.rglob("*.py"):
        assert "???" not in path.read_text(encoding="utf-8"), path


def test_fidelity_schema_json_examples_parse_and_keep_auto_manual_sources_separate() -> None:
    text = _document_text(FIDELITY_SCHEMA)
    examples = [
        json.loads(block.split("```", 1)[0])
        for block in text.split("```json\n")[1:]
    ]

    assert len(examples) == 2
    parsed = [ProductFidelityConstraints.from_dict(example) for example in examples]
    automatic, corrected = parsed
    assert automatic.review_status == "pending"
    assert corrected.review_status == "corrected"
    assert automatic.detected_keywords == corrected.detected_keywords == ("吊坠",)
    assert "连接环" not in automatic.must_keep[0].relationship
    assert all("第二层" not in item for item in automatic.must_not_change)
    assert "连接环" in corrected.must_keep[0].relationship
    assert any("层" in item for item in corrected.must_not_change)


def _带链吊坠分析数据() -> dict[str, object]:
    data = _modern_analysis()
    data.update(
        {
            "visible_appearance": "双层项链，正面中心有水滴形吊坠，可见连接环连接第二层链条",
            "special_requirements": [],
            "needs_full_front_display": True,
            "layer_count": 2,
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 2,
            "confirmed_product_type": "pendant_necklace",
            "detected_product_type": "pendant_necklace",
        }
    )
    return data


def test_结构不完整的带链吊坠分析必须明确拒绝() -> None:
    data = _带链吊坠分析数据()

    with pytest.raises(ValueError, match="pendant_semantics.position 必须是非空字符串"):
        build_product_fidelity_constraints(ProductAnalysis.from_dict(data))


def test_完整结构化的带链吊坠分析可以构建保真约束() -> None:
    data = _带链吊坠分析数据()
    data.update(
        {
            "pendant_position": "第二层中央",
            "pendant_orientation": "水滴尖端朝下",
            "connection_structure": "闭口金属吊环连接第二层链条",
        }
    )

    automatic = build_product_fidelity_constraints(ProductAnalysis.from_dict(data))

    assert automatic.detected_keywords == ("吊坠",)
    assert [item.normalized_keyword for item in automatic.must_keep] == ["吊坠"]
    assert automatic.pendant_semantics is not None
    assert automatic.pendant_semantics.position == "第二层中央"
    assert automatic.pendant_semantics.orientation == "水滴尖端朝下"
    assert automatic.pendant_semantics.connection == "闭口金属吊环连接第二层链条"


def test_自由文本中的连接环和第二层不会提升为未确认字段() -> None:
    data = _带链吊坠分析数据()
    data.update(
        {
            "pendant_layer": 1,
            "pendant_position": "胸前中线",
            "pendant_orientation": "水滴尖端朝下",
            "connection_structure": "闭口金属扣连接第一层链条",
        }
    )

    automatic = build_product_fidelity_constraints(ProductAnalysis.from_dict(data))

    assert automatic.pendant_semantics is not None
    assert automatic.pendant_semantics.layer == 1
    assert automatic.pendant_semantics.position == "胸前中线"
    assert automatic.pendant_semantics.orientation == "水滴尖端朝下"
    assert automatic.pendant_semantics.connection == "闭口金属扣连接第一层链条"
    pendant_item = automatic.must_keep[0]
    assert pendant_item.source_text == data["visible_appearance"]
    assert pendant_item.visual_shape == (
        "位置：胸前中线；朝向：水滴尖端朝下；"
        "连接：闭口金属扣连接第一层链条"
    )
    assert "连接环" not in pendant_item.visual_shape
    assert "第二层" not in pendant_item.visual_shape
    assert "连接环" not in pendant_item.relationship
    assert "第二层" not in pendant_item.relationship


@pytest.mark.parametrize(
    "document",
    [MANUAL_WORKFLOW, PORTABLE_WORKFLOW, TROUBLESHOOTING],
)
def test_operator_documents_explain_strict_qc_and_legacy_boundary(document: Path) -> None:
    text = _document_text(document)

    assert "fidelity_checks" in text
    assert "must_keep" in text
    assert "完全一致" in text
    assert "critical_failures" in text
    assert "严重错误" in text and "reject" in text
    assert "历史手串" in text
    assert "显式非法" in text
    assert "中文" in text


def test_fidelity_schema_explains_canonical_record_decision_contract() -> None:
    text = _document_text(FIDELITY_SCHEMA)

    assert "--fidelity-constraints-path" in text
    assert "导入源" in text
    assert "analysis/product_fidelity_constraints.json" in text
    assert "canonical" in text
    assert "record-decision" in text
    assert "generate" in text
    assert "非标准" in text and "拒绝" in text


def test_workflow_skill_is_versioned_with_project_and_has_no_local_absolute_paths() -> None:
    skill_md = WORKFLOW_SKILL / "SKILL.md"

    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")

    forbidden_fragments = (
        "C:\\Users\\Administrator",
        "C:/Users/Administrator",
        "\\Documents\\珠宝上手图片生成",
        ".codex\\skills\\jewelry-on-hand-workflow",
    )
    for fragment in forbidden_fragments:
        assert fragment not in text

    assert "当前工作区" in text
    assert "src/jewelry_on_hand" in text
    assert "skills/aireiter-image-generation" in text


def test_skill_installation_guide_uses_codex_home_and_project_relative_paths() -> None:
    guide = PROJECT_ROOT / "reference" / "codex-skill-installation.md"

    assert guide.exists()
    text = guide.read_text(encoding="utf-8")

    assert "CODEX_HOME" in text
    assert "scripts/install_codex_skills.py" in text
    assert "skills/jewelry-on-hand-workflow" in text
    assert "C:\\Users\\Administrator" not in text


def test_installer_copies_project_skills_to_requested_codex_home(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(tmp_path / "codex-home")
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(INSTALLER),
            "--skill",
            "jewelry-on-hand-workflow",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    installed = Path(env["CODEX_HOME"]) / "skills" / "jewelry-on-hand-workflow"
    assert (installed / "SKILL.md").exists()
    assert (installed / "references" / "workflow.md").exists()
    assert (installed / "scripts" / "validate_prompt_contract.py").exists()


def test_portable_prompt_contract_declares_complete_ring_support() -> None:
    namespace = runpy.run_path(str(PROMPT_VALIDATOR))
    rules = namespace["RING_LAYER_REQUIREMENTS"]

    assert "ring" in namespace["ALLOWED_PRODUCT_CATEGORIES"]
    assert "内部图2是戒指身份唯一来源" in rules["【两图职责】"]
    assert "只生成一枚目标戒指" in rules["【品类保真】"]
    assert "戒圈自然环绕手指" in rules["【遮挡与接触物理】"]
    for document in (
        PROJECT_ROOT / "reference" / "prompt-template.md",
        WORKFLOW_SKILL / "references" / "prompt-contract.md",
    ):
        text = _document_text(document)
        assert "ring" in text
        assert "戒指身份唯一来源" in text
        assert "不可见戒圈背面" in text


def test_artifact_inspector_accepts_legacy_bracelet_and_modern_necklace_json(
    tmp_path: Path,
) -> None:
    legacy_root = _artifact_contract_run(
        tmp_path / "legacy",
        _legacy_bracelet_analysis(),
        {"action": "generate_rank_1", "selected_ranks": [1]},
    )
    modern_analysis = _modern_analysis()
    modern_root = _artifact_contract_run(
        tmp_path / "modern",
        modern_analysis,
        _modern_decision(modern_analysis),
    )

    assert _inspect_run(legacy_root) == ["缺少 generation/NN 目录"]
    assert _inspect_run(modern_root) == ["缺少 generation/NN 目录"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_image_type": "hand_held_source"}, "hand_held_source"),
        ({"display_mode": "hand_held"}, "手持展示"),
    ],
)
def test_artifact_inspector_does_not_let_legacy_bracelet_bypass_explicit_mode_gate(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    analysis = _legacy_bracelet_analysis()
    analysis.update(overrides)
    run_root = _artifact_contract_run(
        tmp_path,
        analysis,
        {"action": "generate_rank_1", "selected_ranks": [1]},
    )

    errors = _inspect_run(run_root)

    assert any(message in error for error in errors), errors


def test_artifact_inspector_rejects_missing_or_mismatched_modern_snapshot(
    tmp_path: Path,
) -> None:
    analysis = _modern_analysis()
    missing_root = _artifact_contract_run(
        tmp_path / "missing-snapshot",
        analysis,
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
        },
    )
    mismatch = _modern_decision(analysis)
    mismatch["confirmation_snapshot"]["display_mode"] = "hand_held"
    mismatch_root = _artifact_contract_run(
        tmp_path / "mismatch-snapshot",
        analysis,
        mismatch,
    )

    missing_errors = _inspect_run(missing_root)
    mismatch_errors = _inspect_run(mismatch_root)

    assert any("缺少完整产品确认快照" in error for error in missing_errors)
    assert any("display_mode" in error and "不一致" in error for error in mismatch_errors)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"classification_source": None}, "现代分类契约"),
        (
            {
                "product_type": "疑似项链",
                "detected_product_type": "unknown",
                "confirmed_product_type": "unknown",
            },
            "必须先人工纠正",
        ),
        (
            {
                "product_type": "无链独立吊坠",
                "detected_product_type": "pendant_only",
                "confirmed_product_type": "pendant_only",
                "length_category": None,
                "has_pendant": True,
                "pendant_count": 1,
                "pendant_layer": None,
            },
            "禁止自动补链",
        ),
        ({"source_image_type": "flat_lay_source"}, "白底或平铺"),
        ({"source_image_type": "hand_held_source"}, "hand_held_source"),
        ({"layer_count": 4}, "1 至 3 层"),
        ({"is_independent_multi_item": True}, "多件独立项链"),
        (
            {
                "product_type": "带链吊坠",
                "detected_product_type": "pendant_necklace",
                "confirmed_product_type": "pendant_necklace",
                "has_pendant": False,
                "pendant_count": 0,
                "pendant_layer": None,
            },
            "完整主吊坠结构",
        ),
    ],
)
def test_artifact_inspector_rejects_invalid_modern_contract(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    analysis = _modern_analysis()
    analysis.update(overrides)
    run_root = _artifact_contract_run(
        tmp_path,
        analysis,
        _modern_decision(analysis),
    )

    errors = _inspect_run(run_root)

    assert any(message in error for error in errors), errors


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("passed", [True], "passed 只能包含非空字符串"),
        ("failed", [1], "failed 只能包含非空字符串"),
        ("critical_failures", True, "critical_failures 必须是列表"),
        ("critical_failures", [], "critical_failures 不能为空列表"),
    ],
)
def test_qc_validator_strictly_validates_json_types(tmp_path, field, value, message):
    qc_path = tmp_path / "qc.json"
    data = {
        "status": "reject",
        "passed": ["无水印"],
        "failed": ["自动补链"],
        "notes": "拒绝",
        "critical_failures": ["auto_chain_added"],
    }
    data[field] = value
    _write_json(qc_path, data)

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any(message in error for error in errors), errors


def test_qc_validator_forbids_pass_with_critical_failure(tmp_path):
    qc_path = tmp_path / "qc.json"
    _write_json(
        qc_path,
        {
            "status": "pass",
            "passed": ["层数正确"],
            "failed": [],
            "notes": "通过",
            "critical_failures": ["layer_count_mismatch"],
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any("严重错误" in error and "pass" in error for error in errors), errors


def test_qc_validator_requires_reject_for_severe_failed_text(tmp_path):
    qc_path = tmp_path / "qc.json"
    _write_json(
        qc_path,
        {
            "status": "rerun",
            "passed": ["没有迁移产品图中的人物局部"],
            "failed": ["检测到自动补链"],
            "notes": "需要处理",
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any("必须标记为 reject" in error for error in errors), errors


def test_qc_validator_reports_broken_json_in_chinese(tmp_path):
    qc_path = tmp_path / "qc.json"
    qc_path.write_text('{"status":', encoding="utf-8")

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert len(errors) == 1
    assert "不是有效 JSON" in errors[0]


@pytest.mark.parametrize(
    ("fidelity_checks", "message"),
    [
        ([], "数量"),
        (
            [
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                },
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                },
            ],
            "唯一",
        ),
        (
            [
                {
                    "name": "错误名称",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                }
            ],
            "name",
        ),
        (
            [
                {
                    "name": "主吊坠",
                    "question": "错误问题",
                    "result": "pass",
                    "notes": "",
                }
            ],
            "question",
        ),
        (
            [
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "unknown",
                    "notes": "",
                }
            ],
            "result",
        ),
    ],
)
def test_qc_validator_requires_complete_unique_must_keep_coverage(
    tmp_path,
    fidelity_checks,
    message,
):
    run_root = tmp_path / "run"
    qc_path = run_root / "generation" / "01" / "qc.json"
    (run_root / "analysis").mkdir(parents=True)
    qc_path.parent.mkdir(parents=True)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        _portable_constraints_with_must_keep(),
    )
    _write_json(
        qc_path,
        {
            "status": "rerun",
            "passed": ["没有迁移产品图中的人物局部"],
            "failed": ["需要复核"],
            "notes": "",
            "fidelity_checks": fidelity_checks,
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any(message in error for error in errors), errors


@pytest.mark.parametrize("field", ["name", "question", "result", "notes"])
@pytest.mark.parametrize("invalid_value", [["数组"], {"对象": True}, True, 1])
def test_qc_validator_fidelity_checks_field_type_errors_do_not_crash(
    tmp_path,
    field,
    invalid_value,
):
    run_root = tmp_path / "run"
    qc_path = run_root / "generation" / "01" / "qc.json"
    (run_root / "analysis").mkdir(parents=True)
    qc_path.parent.mkdir(parents=True)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        _portable_constraints_with_must_keep(),
    )
    check = {
        "name": "主吊坠",
        "question": "主吊坠是否保持原连接？",
        "result": "pass",
        "notes": "",
    }
    check[field] = invalid_value
    _write_json(
        qc_path,
        {
            "status": "rerun",
            "passed": ["没有迁移产品图中的人物局部"],
            "failed": ["需要复核"],
            "notes": "",
            "fidelity_checks": [check],
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any(
        f"fidelity_checks[0].{field} 必须是字符串" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    ("second_name", "second_question"),
    [
        ("主吊坠", "主吊坠是否保持所属层？"),
        ("吊坠连接环", "主吊坠是否保持原连接？"),
    ],
)
def test_qc_validator_allows_unique_name_question_pairs(
    tmp_path,
    second_name,
    second_question,
):
    run_root = tmp_path / "run"
    qc_path = run_root / "generation" / "01" / "qc.json"
    constraints = _portable_constraints_with_must_keep()
    second = dict(constraints["must_keep"][0])
    second["name"] = second_name
    second["qc_question"] = second_question
    constraints["must_keep"].append(second)
    (run_root / "analysis").mkdir(parents=True)
    qc_path.parent.mkdir(parents=True)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        constraints,
    )
    _write_json(
        qc_path,
        {
            "status": "pass",
            "passed": ["没有迁移产品图中的人物局部，迁移检查通过"],
            "failed": [],
            "notes": "",
            "fidelity_checks": [
                {
                    "name": "主吊坠",
                    "question": "主吊坠是否保持原连接？",
                    "result": "pass",
                    "notes": "",
                },
                {
                    "name": second_name,
                    "question": second_question,
                    "result": "pass",
                    "notes": "",
                },
            ],
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert errors == []


def test_qc_writer_output_passes_portable_validator_for_standard_run(tmp_path):
    run_root = tmp_path / "run"
    generation_dir = run_root / "generation" / "01"
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    constraints_path.parent.mkdir(parents=True)
    _write_json(constraints_path, _portable_constraints_with_must_keep())

    qc_path = write_qc_result(
        generation_dir,
        "pass",
        ["没有迁移产品图中的人物局部，迁移检查通过"],
        [],
        "所有检查通过",
        fidelity_checks=[
            {
                "name": "主吊坠",
                "question": "主吊坠是否保持原连接？",
                "result": "pass",
                "notes": "保持原连接",
            }
        ],
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert errors == []


def test_qc_validator_accepts_representative_legacy_bracelet_record(tmp_path):
    qc_path = tmp_path / "legacy" / "qc.json"
    qc_path.parent.mkdir(parents=True)
    _write_json(
        qc_path,
        {
            "status": "pass",
            "passed": [
                "原图手腕检查通过",
                "原图手臂检查通过",
                "皮肤块迁移检查通过",
            ],
            "failed": [],
            "notes": "未发现粗手腕、局部手臂或皮肤块迁移",
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert errors == []


def _portable_constraints_with_must_keep():
    return {
        "schema_version": 1,
        "source": {
            "product_id": "PN-001",
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
        },
        "detected_keywords": ["主吊坠"],
        "must_keep": [
            {
                "name": "主吊坠",
                "source_text": "第二层中央主吊坠",
                "normalized_keyword": "主吊坠",
                "location": "第二层中央",
                "visual_shape": "水滴形",
                "relationship": "连接第二层链条",
                "forbid": ["不得换层"],
                "qc_question": "主吊坠是否保持原连接？",
            }
        ],
        "must_not_change": ["层间关系"],
        "needs_user_review": False,
        "detail_crop_recommended": False,
        "review_status": "confirmed",
    }


def _inspect_run(run_root: Path) -> list[str]:
    namespace = runpy.run_path(str(ARTIFACT_INSPECTOR))
    return namespace["inspect_run"](run_root)


def _artifact_contract_run(
    root: Path,
    analysis: dict[str, object],
    decision: dict[str, object],
) -> Path:
    for relative in ("input", "analysis", "review", "generation"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "input" / "product-on-hand.jpg").write_bytes(b"product")
    _write_json(root / "analysis" / "product_analysis.json", analysis)
    selected = []
    for rank in (1, 2, 3):
        reference = root / f"reference-{rank}.jpg"
        reference.write_bytes(f"reference-{rank}".encode())
        digest = hashlib.sha256(reference.read_bytes()).hexdigest()
        selected.append(
            {
                "rank": rank,
                "selected_reference": str(reference),
                "score": 100 - rank,
                "source_sha256": digest,
                "review_sha256": digest,
                "metadata": {
                    "source_reference": str(reference),
                    "source_sha256": digest,
                    "review_sha256": digest,
                },
            }
        )
    _write_json(root / "analysis" / "selected_references.json", selected)
    _write_json(root / "review" / "review_decision.json", decision)
    return root


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _legacy_bracelet_analysis() -> dict[str, object]:
    return {
        "product_type": "朱砂手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "深红圆珠手串",
        "color_family": ["深红"],
        "style_mood": "自然",
        "composition": "手腕近景",
        "product_dimensions": {"bead_diameter_mm": 10},
    }


def _modern_analysis() -> dict[str, object]:
    return {
        "product_type": "普通项链",
        "detected_product_type": "necklace",
        "confirmed_product_type": "necklace",
        "classification_confidence": "high",
        "classification_evidence": ["肉眼可见完整链条"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "wear_position": "颈部和锁骨",
        "visible_appearance": "完整金色链条",
        "color_family": ["金色"],
        "style_mood": "精致",
        "composition": "胸前近景",
        "product_dimensions": {},
        "layer_count": 1,
        "length_category": "collarbone",
        "chain_or_strand_type": "metal_chain",
        "has_pendant": False,
        "pendant_count": 0,
        "pendant_layer": None,
        "pendant_position": None,
        "pendant_orientation": None,
        "connection_structure": None,
        "is_independent_multi_item": False,
    }


def _modern_decision(analysis: dict[str, object]) -> dict[str, object]:
    snapshot_fields = (
        "confirmed_product_type",
        "source_image_type",
        "display_mode",
        "layer_count",
        "length_category",
        "has_pendant",
        "pendant_count",
        "pendant_layer",
        "pendant_position",
        "pendant_orientation",
        "connection_structure",
        "is_independent_multi_item",
    )
    return {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "confirmation_snapshot": {
            field_name: analysis[field_name] for field_name in snapshot_fields
        },
    }


def _task9_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _task9_signature(snapshot: dict[str, object]) -> str:
    payload = {
        "output_role": snapshot["output_role"],
        "framing": snapshot["framing"],
        "pose": snapshot["pose"],
        "background": snapshot["background"],
        "lighting": snapshot["lighting"],
        "replacement_target": snapshot["replacement_target"],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _task9_snapshot_digest(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _task9_modern_run(root: Path, *, completed: bool = True) -> tuple[Path, Path]:
    generation = root / "generation" / "01"
    source_dir = root / "sources"
    for directory in (root / "input", root / "analysis", root / "review", generation, source_dir):
        directory.mkdir(parents=True, exist_ok=True)

    product_source = root / "input" / "product-on-hand.jpg"
    scene_source = source_dir / "scene.jpg"
    product_source.write_bytes(b"product-identity")
    scene_source.write_bytes(b"scene-reference")
    review_scene = root / "review" / "rank-1-scene.jpg"
    review_scene.write_bytes(scene_source.read_bytes())
    scene_copy = generation / "scene-reference.jpg"
    product_copy = generation / "product-reference.jpg"
    scene_copy.write_bytes(scene_source.read_bytes())
    product_copy.write_bytes(product_source.read_bytes())

    analysis_data = {
        "product_type": "手链/手串",
        "wear_position": "左手腕",
        "visible_appearance": "深红圆珠手串，中央有一颗白水晶随形珠",
        "color_family": ["深红", "透明"],
        "style_mood": "自然",
        "composition": "手腕近景",
        "product_dimensions": {
            "bead_diameter_mm": 10,
            "dimension_source": "用户录入",
        },
        "needs_full_front_display": True,
        "special_requirements": ["保留白水晶随形珠"],
    }
    product = ProductAnalysis.from_dict(analysis_data)
    analysis_data = product_analysis_to_dict(product)
    canonical_data = build_product_fidelity_constraints(product).to_dict()
    canonical_data["review_status"] = "confirmed"
    constraints = ProductFidelityConstraints.from_dict(canonical_data)

    snapshot_data: dict[str, object] = {
        "rank": 1,
        "reference_file": scene_source.name,
        "reference_sha256": _task9_sha256(scene_source),
        "output_role": "hand_worn",
        "framing": "手腕近景",
        "camera_angle": "平视",
        "subject_placement": "人物居中",
        "visible_body_regions": ["左手腕", "左手"],
        "pose": {
            "body": "身体正面",
            "arm": "手臂自然下垂",
            "hand": "左手手背朝上",
            "hand_side": "left",
        },
        "clothing": "黑色圆领上衣",
        "background": "深色木纹背景",
        "lighting": "左侧柔光",
        "replacement_target": {
            "body_region": "左手腕",
            "source_jewelry": "原手串",
            "target_product_count": 1,
        },
        "other_jewelry_to_remove": [],
        "text_or_ui_risk": "none",
        "product_visibility_sufficient": True,
    }
    snapshot_data["composition_signature"] = _task9_signature(snapshot_data)
    snapshot = ReferenceCompositionSnapshot.from_dict(snapshot_data)
    row = ReferenceRow(
        index=1,
        file_name=scene_source.name,
        relative_path=scene_source.name,
        absolute_path=scene_source,
        width=1200,
        height=1600,
        size_mb=0.1,
        purpose_category="手部佩戴图",
        bracelet_applicability="否",
        default_strategy="已确认",
        style_category="暗调",
        scene_keywords="深色木纹",
        jewelry_type="手链/手串",
        recommended_usage="手腕近景",
        notes="人工确认",
        confidence="高",
        file_exists=True,
    )
    reference = ScoredReference(row, 100, 1, ("人工确认",), (), ())
    prompt = build_generation_prompt(
        product,
        reference,
        constraints,
        OutputRole.HAND_WORN,
        snapshot,
    )

    fixed_json = {
        "reference-composition-snapshot.json": snapshot_data,
        "product-analysis.json": analysis_data,
        "product-fidelity-constraints.json": canonical_data,
    }
    for name, value in fixed_json.items():
        _write_json(generation / name, value)
    (generation / "prompt.txt").write_text(prompt, encoding="utf-8")
    (generation / "model.txt").write_text("gpt_image_2", encoding="utf-8")
    (generation / "reference-rank.txt").write_text("1", encoding="utf-8")
    _write_json(generation / "submit.json", {"ok": True, "data": {"out_task_id": "task-1"}})

    manifest = {
        "schema_version": 1,
        "output_role": "hand_worn",
        "reference_snapshot": {
            "copied_file": "reference-composition-snapshot.json",
            "sha256": _task9_sha256(generation / "reference-composition-snapshot.json"),
        },
        "product_analysis": {
            "copied_file": "product-analysis.json",
            "sha256": _task9_sha256(generation / "product-analysis.json"),
        },
        "fidelity_constraints": {
            "copied_file": "product-fidelity-constraints.json",
            "sha256": _task9_sha256(generation / "product-fidelity-constraints.json"),
        },
        "inputs": [
            {
                "order": 1,
                "role": "scene_reference",
                "source_path": str(review_scene.resolve()),
                "copied_file": scene_copy.name,
                "sha256": _task9_sha256(scene_copy),
            },
            {
                "order": 2,
                "role": "product_identity",
                "source_path": str(product_source.resolve()),
                "copied_file": product_copy.name,
                "sha256": _task9_sha256(product_copy),
            },
        ],
    }
    _write_json(generation / "input-manifest.json", manifest)

    _write_json(root / "analysis" / "product_analysis.json", analysis_data)
    _write_json(root / "analysis" / "product_fidelity_constraints.json", canonical_data)
    _write_json(
        root / "analysis" / "reference_composition_snapshots.json",
        [snapshot_data],
    )
    _write_json(root / "review" / "reference_composition_snapshot.json", snapshot_data)
    selected = []
    for rank in (1, 2, 3):
        source = scene_source if rank == 1 else source_dir / f"scene-{rank}.jpg"
        review = review_scene if rank == 1 else root / "review" / f"rank-{rank}-scene-{rank}.jpg"
        if rank != 1:
            source.write_bytes(f"scene-reference-{rank}".encode())
            review.write_bytes(source.read_bytes())
        selected.append(
            {
                "rank": rank,
                "selected_reference": str(review.resolve()),
                "score": 101 - rank,
                "reason": ["人工确认"],
                "risk": [],
                "ignored_reference_jewelry": [],
                "source_sha256": _task9_sha256(source),
                "review_sha256": _task9_sha256(review),
                "metadata": {
                    "source_reference": str(source.resolve()),
                    "source_absolute_path": str(source.resolve()),
                    "absolute_path": str(source.resolve()),
                    "source_relative_path": source.name,
                    "relative_path": source.name,
                    "source_file_name": source.name,
                    "file_name": source.name,
                    "source_sha256": _task9_sha256(source),
                    "review_sha256": _task9_sha256(review),
                    "file_exists": True,
                },
            }
        )
    _write_json(root / "analysis" / "selected_references.json", selected)
    candidate_snapshots = []
    for item in selected:
        candidate = dict(snapshot_data)
        candidate["rank"] = item["rank"]
        candidate["reference_file"] = item["metadata"]["source_file_name"]
        candidate["reference_sha256"] = item["source_sha256"]
        candidate["composition_signature"] = _task9_signature(candidate)
        candidate_snapshots.append(candidate)
    _write_json(
        root / "analysis" / "reference_composition_snapshots.json",
        candidate_snapshots,
    )
    _write_json(root / "analysis" / "output_role.json", {"output_role": "hand_worn"})
    decision = _modern_decision(analysis_data)
    decision["output_role"] = "hand_worn"
    decision["reference_snapshot_sha256"] = _task9_snapshot_digest(snapshot_data)
    _write_json(root / "review" / "review_decision.json", decision)

    reference_checks = []
    comparison_sources = {
        "replacement_target_preserved": "confirmed_snapshot",
        "single_target_product": "product_identity",
    }
    for name, question in build_reference_preservation_checklist(snapshot):
        evidence: dict[str, object] = {
            "comparison_source": comparison_sources.get(name, "scene_reference"),
            "region": f"{name} 对应区域",
            "observation": f"逐项确认 {name} 保持一致",
        }
        if name == "source_jewelry_removed":
            evidence.update(source_jewelry_subject_visible=False, residual_scope="none")
        reference_checks.append(
            {
                "name": name,
                "question": question,
                "result": "pass",
                "issue_code": None,
                "notes": "人工逐项复核通过",
                "evidence": evidence,
            }
        )
    fidelity_checks = [
        {
            "name": item.name,
            "question": item.qc_question,
            "result": "pass",
            "notes": "对照产品身份图通过",
        }
        for item in constraints.must_keep
    ]
    checklist_checks = [
        {
            "id": item.id,
            "question": item.question,
            "result": "pass",
            "notes": "逐项检查通过",
        }
        for item in build_qc_checklist(
            product_analysis=product,
            fidelity_constraints=constraints,
        )
    ]
    _write_json(
        generation / "qc.json",
        {
            "status": "pass",
            "passed": ["全部结构化检查通过"],
            "failed": [],
            "notes": "人工复核通过",
            "fidelity_checks": fidelity_checks,
            "checklist_checks": checklist_checks,
            "reference_preservation_checks": reference_checks,
        },
    )
    if completed:
        _write_json(generation / "result.json", {"ok": True, "data": {"status": "completed"}})
        (generation / "result.png").write_bytes(b"result")
        (generation / "qc-review.html").write_text("<html>四栏 QC</html>", encoding="utf-8")
    return root, generation


def test_reference_snapshot_cli_严格校验成功与输入错误退出码(tmp_path: Path) -> None:
    root, generation = _task9_modern_run(tmp_path / "run")
    selected = json.loads((root / "analysis" / "selected_references.json").read_text(encoding="utf-8"))
    reference = selected[0]["metadata"]["source_reference"]
    command = [
        sys.executable,
        str(SNAPSHOT_VALIDATOR),
        str(generation / "reference-composition-snapshot.json"),
        "--reference",
        reference,
        "--output-role",
        "hand_worn",
    ]
    passed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    assert passed.returncode == 0, passed.stderr
    assert "参考构图快照校验通过" in passed.stdout

    broken = generation / "broken-snapshot.json"
    broken.write_text('{"rank":', encoding="utf-8")
    failed = subprocess.run(
        [*command[:2], str(broken), *command[3:]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert failed.returncode == 2
    assert "Traceback" not in failed.stderr


@pytest.mark.parametrize(
    "mutation",
    ("sha", "role", "rank_bool", "count_bool", "nested_extra", "signature"),
)
def test_reference_snapshot_拒绝摘要角色类型嵌套与签名篡改(tmp_path: Path, mutation: str) -> None:
    root, generation = _task9_modern_run(tmp_path / mutation)
    snapshot_path = generation / "reference-composition-snapshot.json"
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if mutation == "sha":
        data["reference_sha256"] = "0" * 64
    elif mutation == "role":
        data["output_role"] = "lifestyle"
    elif mutation == "rank_bool":
        data["rank"] = True
    elif mutation == "count_bool":
        data["replacement_target"]["target_product_count"] = True
    elif mutation == "nested_extra":
        data["pose"]["camera_hint"] = "俯拍"
        data["composition_signature"] = _task9_signature(data)
    else:
        data["composition_signature"] = "0" * 64
    _write_json(snapshot_path, data)
    namespace = runpy.run_path(str(SNAPSHOT_VALIDATOR))
    selected = json.loads((root / "analysis" / "selected_references.json").read_text(encoding="utf-8"))
    errors = namespace["validate_reference_snapshot"](
        snapshot_path,
        Path(selected[0]["metadata"]["source_reference"]),
        "hand_worn",
    )
    assert errors, mutation


def test_reference_preservation_prompt_四输入与精确单次纠偏尾缀(tmp_path: Path) -> None:
    _root, generation = _task9_modern_run(tmp_path / "prompt")
    namespace = runpy.run_path(str(PROMPT_VALIDATOR))
    arguments = (
        generation / "prompt.txt",
        generation / "reference-composition-snapshot.json",
        generation / "product-analysis.json",
        generation / "product-fidelity-constraints.json",
    )
    assert namespace["validate_prompt"](*arguments) == []
    suffix = namespace["REFERENCE_STRUCTURE_RETRY_SUFFIX"]
    original = arguments[0].read_text(encoding="utf-8")
    arguments[0].write_text(original.rstrip() + "\n\n" + suffix, encoding="utf-8")
    assert namespace["validate_prompt"](*arguments) == []
    arguments[0].write_text(original.rstrip() + "\n\n" + suffix + suffix, encoding="utf-8")
    assert namespace["validate_prompt"](*arguments)


@pytest.mark.parametrize("product_type", ("necklace", "pendant_necklace"))
def test_严格v2项链安全提示与便携校验器保持同态(
    tmp_path: Path,
    product_type: str,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / product_type)
    data = _modern_analysis()
    data["visible_appearance"] = "双层项链，可见连接环连接第二层链条"
    if product_type == "pendant_necklace":
        data.update(
            {
                "product_type": "带链吊坠",
                "detected_product_type": "pendant_necklace",
                "confirmed_product_type": "pendant_necklace",
                "classification_evidence": ["完整链条与中央主吊坠清晰可见"],
                "layer_count": 2,
                "has_pendant": True,
                "pendant_count": 1,
                "pendant_layer": 1,
                "pendant_position": "胸前中线",
                "pendant_orientation": "水滴尖端朝下",
                "connection_structure": "闭口金属扣连接第一层链条",
            }
        )
    product = ProductAnalysis.from_dict(data)
    analysis_data = product_analysis_to_dict(product)
    canonical_data = build_product_fidelity_constraints(product).to_dict()
    canonical_data["review_status"] = "confirmed"
    constraints = ProductFidelityConstraints.from_dict(canonical_data)

    snapshot_path = generation / "reference-composition-snapshot.json"
    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot_data["output_role"] = "lifestyle"
    snapshot_data["visible_body_regions"] = ["颈部", "胸前"]
    snapshot_data["replacement_target"] = {
        "body_region": "颈部与胸前中线",
        "source_jewelry": "原项链",
        "target_product_count": 1,
    }
    snapshot_data["composition_signature"] = _task9_signature(snapshot_data)
    snapshot = ReferenceCompositionSnapshot.from_dict(snapshot_data)
    reference = ScoredReference(
        ReferenceRow(
            index=1,
            file_name=snapshot.reference_file,
            relative_path=snapshot.reference_file,
            absolute_path=generation / "scene-reference.jpg",
            width=1200,
            height=1600,
            size_mb=0.1,
            purpose_category="生活场景图",
            bracelet_applicability="否",
            default_strategy="已确认",
            style_category="暗调",
            scene_keywords="深色木纹",
            jewelry_type="项链",
            recommended_usage="颈部与胸前构图",
            notes="人工确认",
            confidence="高",
            file_exists=True,
        ),
        100,
        1,
        ("人工确认",),
        (),
        (),
    )
    prompt = build_generation_prompt(
        product,
        reference,
        constraints,
        OutputRole.LIFESTYLE,
        snapshot,
    )

    prompt_path = generation / "prompt.txt"
    analysis_path = generation / "product-analysis.json"
    canonical_path = generation / "product-fidelity-constraints.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    _write_json(snapshot_path, snapshot_data)
    _write_json(analysis_path, analysis_data)
    _write_json(canonical_path, canonical_data)
    validate_prompt = runpy.run_path(str(PROMPT_VALIDATOR))["validate_prompt"]
    arguments = (prompt_path, snapshot_path, analysis_path, canonical_path)

    assert validate_prompt(*arguments) == []

    prefix = "产品身份JSON："
    identity_line = next(line for line in prompt.splitlines() if line.startswith(prefix))
    identity = json.loads(identity_line.removeprefix(prefix))
    identity.pop("layer_count")
    tampered_identity = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    prompt_path.write_text(
        prompt.replace(identity_line, prefix + tampered_identity, 1),
        encoding="utf-8",
    )
    assert validate_prompt(*arguments)


@pytest.mark.parametrize("mutation", ("missing", "analysis_type", "canonical_projection"))
def test_reference_preservation_prompt_拒绝缺输入与可信投影篡改(
    tmp_path: Path,
    mutation: str,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / mutation)
    namespace = runpy.run_path(str(PROMPT_VALIDATOR))
    paths: list[Path | None] = [
        generation / "prompt.txt",
        generation / "reference-composition-snapshot.json",
        generation / "product-analysis.json",
        generation / "product-fidelity-constraints.json",
    ]
    if mutation == "missing":
        paths[2] = None
    elif mutation == "analysis_type":
        data = json.loads(paths[2].read_text(encoding="utf-8"))
        data["color_family"] = True
        _write_json(paths[2], data)
    else:
        data = json.loads(paths[3].read_text(encoding="utf-8"))
        data["must_not_change"].append("新增未确认约束")
        _write_json(paths[3], data)
    assert namespace["validate_prompt"](*paths), mutation


@pytest.mark.parametrize(
    ("value", "should_pass"),
    ((10, True), (10.0, True), ("10", False), (True, False), ([], False), ({}, False)),
)
def test_reference_preservation_prompt_尺寸仅接受真实有限正数并规范为浮点(
    tmp_path: Path,
    value: object,
    should_pass: bool,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / str(type(value).__name__))
    analysis_path = generation / "product-analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["product_dimensions"]["bead_diameter_mm"] = value
    _write_json(analysis_path, analysis)
    errors = runpy.run_path(str(PROMPT_VALIDATOR))["validate_prompt"](
        generation / "prompt.txt",
        generation / "reference-composition-snapshot.json",
        analysis_path,
        generation / "product-fidelity-constraints.json",
    )
    assert (errors == []) is should_pass, errors


@pytest.mark.parametrize(
    ("target", "field", "value"),
    (
        ("snapshot", "output_role", []),
        ("snapshot", "text_or_ui_risk", {}),
        ("analysis", "confirmed_product_type", []),
        ("analysis", "display_mode", {}),
        ("canonical", "review_status", []),
        ("manifest", "output_role", []),
    ),
)
def test_reference_preservation_可解析类型错误均返回中文业务错误而非异常(
    tmp_path: Path,
    target: str,
    field: str,
    value: object,
) -> None:
    run_root, generation = _task9_modern_run(tmp_path / f"{target}-{field}")
    file_by_target = {
        "snapshot": generation / "reference-composition-snapshot.json",
        "analysis": generation / "product-analysis.json",
        "canonical": generation / "product-fidelity-constraints.json",
        "manifest": generation / "input-manifest.json",
    }
    path = file_by_target[target]
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    _write_json(path, data)
    if target == "snapshot":
        selected = json.loads((run_root / "analysis" / "selected_references.json").read_text(encoding="utf-8"))
        errors = runpy.run_path(str(SNAPSHOT_VALIDATOR))["validate_reference_snapshot"](
            path,
            Path(selected[0]["metadata"]["source_reference"]),
            "hand_worn",
        )
    elif target in {"analysis", "canonical"}:
        errors = runpy.run_path(str(PROMPT_VALIDATOR))["validate_prompt"](
            generation / "prompt.txt",
            generation / "reference-composition-snapshot.json",
            generation / "product-analysis.json",
            generation / "product-fidelity-constraints.json",
        )
    else:
        errors = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run"](run_root)
    assert errors
    assert all(isinstance(error, str) and error for error in errors)


@pytest.mark.parametrize(
    "mutation",
    ("missing", "duplicate", "wrong_source", "wrong_issue", "uniform_evidence"),
)
def test_reference_preservation_qc_拒绝缺失重复错源错码与统一伪证据(
    tmp_path: Path,
    mutation: str,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / mutation)
    qc_path = generation / "qc.json"
    data = json.loads(qc_path.read_text(encoding="utf-8"))
    checks = data["reference_preservation_checks"]
    if mutation == "missing":
        checks.pop()
    elif mutation == "duplicate":
        checks[-1] = dict(checks[0])
    elif mutation == "wrong_source":
        checks[0]["evidence"]["comparison_source"] = "product_identity"
    elif mutation == "wrong_issue":
        checks[0]["result"] = "fail"
        checks[0]["issue_code"] = "reference_pose_changed"
        data["status"] = "reject"
        data["critical_failures"] = ["reference_pose_changed"]
        data["failed"] = ["参考结构失败"]
    else:
        for check in checks:
            check["evidence"]["region"] = "整个画面"
            check["evidence"]["observation"] = "全部一致"
    _write_json(qc_path, data)
    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)
    assert errors, mutation
    expected = {
        "missing": "完整唯一覆盖",
        "duplicate": "完整唯一覆盖",
        "wrong_source": "comparison_source",
        "wrong_issue": "issue_code",
        "uniform_evidence": "统一伪证据",
    }[mutation]
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize(
    ("target", "value"),
    (("status", []), ("category", []), ("must_keep", {}), ("check_result", [])),
)
def test_reference_preservation_qc_类型错误返回业务错误不抛异常(
    tmp_path: Path,
    target: str,
    value: object,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / target)
    qc_path = generation / "qc.json"
    if target == "category":
        path = generation / "product-analysis.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["confirmed_product_type"] = value
    elif target == "must_keep":
        path = generation / "product-fidelity-constraints.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["must_keep"] = value
    else:
        path = qc_path
        data = json.loads(path.read_text(encoding="utf-8"))
        if target == "status":
            data["status"] = value
        else:
            data["checklist_checks"][0]["result"] = value
    _write_json(path, data)
    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)
    assert errors
    assert all(isinstance(error, str) and error for error in errors)


def _task9_set_matching_check_result(qc: dict[str, object], result: str) -> None:
    fidelity = qc["fidelity_checks"][0]
    fidelity["result"] = result
    question = fidelity["question"]
    checklist = next(item for item in qc["checklist_checks"] if item["question"] == question)
    checklist["result"] = result


def test_reference_preservation_qc_任一保真fail决定整体reject(
    tmp_path: Path,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / "fidelity-fail")
    qc_path = generation / "qc.json"
    data = json.loads(qc_path.read_text(encoding="utf-8"))
    _task9_set_matching_check_result(data, "fail")
    target = next(
        item
        for item in data["reference_preservation_checks"]
        if item["name"] == "replacement_target_preserved"
    )
    target["result"] = "rerun"
    target["issue_code"] = "local_blending_artifact"
    data["status"] = "rerun"
    data["failed"] = ["保真失败"]
    _write_json(qc_path, data)
    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)
    assert any("最高严重度" in error and "reject" in error for error in errors), errors


def test_reference_preservation_qc_仅保真rerun且参考全pass时整体rerun合法(
    tmp_path: Path,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / "fidelity-rerun")
    qc_path = generation / "qc.json"
    data = json.loads(qc_path.read_text(encoding="utf-8"))
    _task9_set_matching_check_result(data, "rerun")
    data["status"] = "rerun"
    data["failed"] = ["保真局部需复核"]
    _write_json(qc_path, data)
    assert runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path) == []


@pytest.mark.parametrize(
    ("target", "value"),
    (
        ("canonical_must_keep", None),
        ("canonical_must_keep", 0),
        ("canonical_must_keep", True),
        ("fidelity_checks", None),
        ("checklist_checks", None),
    ),
)
def test_reference_preservation_qc_容器类型错误返回中文业务错误且不抛异常(
    tmp_path: Path,
    target: str,
    value: object,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / f"{target}-{type(value).__name__}")
    if target == "canonical_must_keep":
        path = generation / "product-fidelity-constraints.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["must_keep"] = value
    else:
        path = generation / "qc.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data[target] = value
    _write_json(path, data)

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](
        generation / "qc.json"
    )

    assert errors
    assert all(isinstance(error, str) and error for error in errors)


@pytest.mark.parametrize("field", ("name", "qc_question"))
@pytest.mark.parametrize("value", ([], {}, None, True, 1))
def test_reference_preservation_qc_must_keep嵌套类型错误为中文exit1且无traceback(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    _root, generation = _task9_modern_run(
        tmp_path / f"{field}-{type(value).__name__}"
    )
    canonical_path = generation / "product-fidelity-constraints.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical["must_keep"][0][field] = value
    _write_json(canonical_path, canonical)
    expected = f"canonical.must_keep[0].{field} 必须是非空字符串"

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](
        generation / "qc.json"
    )
    completed = subprocess.run(
        [sys.executable, str(QC_VALIDATOR), str(generation / "qc.json")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert any(expected in error for error in errors), errors
    assert any("完整唯一覆盖" in error for error in errors), errors
    assert completed.returncode == 1
    assert expected in completed.stderr
    assert "Traceback" not in completed.stderr


def test_reference_preservation_qc_critical与三层结果合并决定overall(
    tmp_path: Path,
) -> None:
    _root, generation = _task9_modern_run(tmp_path / "critical-status")
    qc_path = generation / "qc.json"
    data = json.loads(qc_path.read_text(encoding="utf-8"))
    data["critical_failures"] = ["category_mismatch"]
    _write_json(qc_path, data)

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any("critical" in error or "关键 QC" in error for error in errors), errors
    assert any("reject" in error for error in errors), errors


def test_reference_preservation_qc_critical_code范围镜像生产契约() -> None:
    namespace = runpy.run_path(str(QC_VALIDATOR))
    expected_non_reference = {
        "must_keep_failed",
        "category_mismatch",
        "core_structure_missing",
        "layer_count_mismatch",
        "length_category_mismatch",
        "pendant_layer_changed",
        "multi_layer_restructured",
        "auto_chain_added",
        "source_person_region_migrated",
        "severe_intersection",
        "ring_count_mismatch",
        "hand_side_mismatch",
        "finger_position_mismatch",
        "ring_structure_mismatch",
        "centerpiece_mismatch",
        "ring_contact_error",
        "finger_deformation",
        "source_hand_leakage",
    }
    assert namespace["ALLOWED_CRITICAL_FAILURES"] == expected_non_reference
    assert {
        "ring_count_mismatch",
        "finger_position_mismatch",
        "ring_structure_mismatch",
        "centerpiece_mismatch",
        "source_hand_leakage",
    } <= namespace["REJECT_CRITICAL_FAILURES"]


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("blocked_action", "action"),
        ("fidelity_unconfirmed", "fidelity_confirmed"),
        ("confirmation_mismatch", "确认快照"),
        ("action_rank_mismatch", "generate_rank_1"),
    ),
)
def test_input_manifest_inspector_现代run执行完整review_decision_gate(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / mutation)
    decision_path = run_root / "review" / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if mutation == "blocked_action":
        decision["action"] = "manual_reference"
    elif mutation == "fidelity_unconfirmed":
        decision["fidelity_confirmed"] = False
    elif mutation == "confirmation_mismatch":
        decision["confirmation_snapshot"]["display_mode"] = "hand_held"
    else:
        decision["selected_ranks"] = [2]
    _write_json(decision_path, decision)

    errors = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run"](run_root)

    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_manifest",
        "reverse_order",
        "path_escape",
        "digest",
        "replace_input",
        "hand_reference",
        "prompt_failure",
        "qc_failure",
        "source_digest",
        "scene_rebind",
        "product_rebind",
        "missing_decision",
        "decision_rank",
        "decision_digest",
        "root_role",
        "missing_selected",
        "selected_review_sha",
        "extra_damaged",
        "empty_generation",
        "modern_fragment",
        "selected_rank_true",
        "selected_rank_float",
        "selected_missing_top3",
        "selected_damaged_record",
    ),
)
def test_input_manifest_inspector_拒绝缺失顺序路径摘要替换与旧文件名(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root, generation = _task9_modern_run(tmp_path / mutation)
    manifest_path = generation / "input-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "missing_manifest":
        manifest_path.unlink()
    elif mutation == "reverse_order":
        manifest["inputs"].reverse()
        _write_json(manifest_path, manifest)
    elif mutation == "path_escape":
        manifest["reference_snapshot"]["copied_file"] = "../snapshot.json"
        _write_json(manifest_path, manifest)
    elif mutation == "digest":
        manifest["product_analysis"]["sha256"] = "0" * 64
        _write_json(manifest_path, manifest)
    elif mutation == "replace_input":
        (generation / "scene-reference.jpg").write_bytes(b"tampered")
    elif mutation == "hand_reference":
        (generation / "hand-reference.jpg").write_bytes(b"legacy-name")
    elif mutation == "prompt_failure":
        (generation / "prompt.txt").write_text("擅自重画整个场景", encoding="utf-8")
    elif mutation == "qc_failure":
        data = json.loads((generation / "qc.json").read_text(encoding="utf-8"))
        data["reference_preservation_checks"].pop()
        _write_json(generation / "qc.json", data)
    elif mutation == "source_digest":
        data = json.loads((run_root / "analysis" / "product_analysis.json").read_text(encoding="utf-8"))
        data["visible_appearance"] = "源文件被替换"
        _write_json(run_root / "analysis" / "product_analysis.json", data)
    elif mutation == "scene_rebind":
        alternative = run_root / "review" / "rank-1-alternative.jpg"
        alternative.write_bytes((generation / "scene-reference.jpg").read_bytes())
        manifest["inputs"][0]["source_path"] = str(alternative.resolve())
        _write_json(manifest_path, manifest)
    elif mutation == "product_rebind":
        alternative = run_root / "sources" / "other-product.jpg"
        alternative.write_bytes((generation / "product-reference.jpg").read_bytes())
        manifest["inputs"][1]["source_path"] = str(alternative.resolve())
        _write_json(manifest_path, manifest)
    elif mutation == "missing_decision":
        (run_root / "review" / "review_decision.json").unlink()
    elif mutation == "decision_rank":
        decision = json.loads((run_root / "review" / "review_decision.json").read_text(encoding="utf-8"))
        decision["action"] = "generate_selected"
        decision["selected_ranks"] = [2]
        _write_json(run_root / "review" / "review_decision.json", decision)
    elif mutation == "decision_digest":
        decision = json.loads((run_root / "review" / "review_decision.json").read_text(encoding="utf-8"))
        decision["reference_snapshot_sha256"] = "0" * 64
        _write_json(run_root / "review" / "review_decision.json", decision)
    elif mutation == "root_role":
        _write_json(run_root / "analysis" / "output_role.json", {"output_role": "lifestyle"})
    elif mutation == "missing_selected":
        (run_root / "analysis" / "selected_references.json").unlink()
    elif mutation == "selected_review_sha":
        selected = json.loads((run_root / "analysis" / "selected_references.json").read_text(encoding="utf-8"))
        selected[0]["review_sha256"] = "0" * 64
        selected[0]["metadata"]["review_sha256"] = "0" * 64
        _write_json(run_root / "analysis" / "selected_references.json", selected)
    elif mutation == "extra_damaged":
        damaged = run_root / "generation" / "02"
        damaged.mkdir()
        (damaged / "prompt.txt").write_text("现代残片", encoding="utf-8")
    elif mutation == "empty_generation":
        (run_root / "generation" / "02").mkdir()
    elif mutation in {"selected_rank_true", "selected_rank_float"}:
        selected_path = run_root / "analysis" / "selected_references.json"
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        selected[0]["rank"] = True if mutation == "selected_rank_true" else 1.0
        _write_json(selected_path, selected)
    elif mutation == "selected_missing_top3":
        selected_path = run_root / "analysis" / "selected_references.json"
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        selected.pop()
        _write_json(selected_path, selected)
    elif mutation == "selected_damaged_record":
        selected_path = run_root / "analysis" / "selected_references.json"
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        selected[2] = "damaged"
        _write_json(selected_path, selected)
    else:
        damaged = run_root / "generation" / "02"
        damaged.mkdir()
        (damaged / "product-reference.jpg").write_bytes(b"fragment")
    before = {path.relative_to(run_root): path.read_bytes() for path in run_root.rglob("*") if path.is_file()}
    errors = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run"](run_root)
    after = {path.relative_to(run_root): path.read_bytes() for path in run_root.rglob("*") if path.is_file()}
    assert errors, mutation
    expected = {
        "missing_manifest": "input-manifest",
        "reverse_order": "顺序",
        "path_escape": "路径逃逸",
        "digest": "摘要",
        "replace_input": "摘要",
        "hand_reference": "hand-reference",
        "prompt_failure": "Prompt",
        "qc_failure": "完整唯一覆盖",
        "source_digest": "源文件摘要",
        "scene_rebind": "selected_reference",
        "product_rebind": "产品原图",
        "missing_decision": "review_decision.json",
        "decision_rank": "selected rank",
        "decision_digest": "快照摘要",
        "root_role": "output_role",
        "missing_selected": "selected_references.json",
        "selected_review_sha": "review_sha256",
        "extra_damaged": "damaged",
        "empty_generation": "damaged",
        "modern_fragment": "damaged",
        "selected_rank_true": "rank",
        "selected_rank_float": "rank",
        "selected_missing_top3": "Top 3",
        "selected_damaged_record": "JSON 对象",
    }[mutation]
    assert any(expected in error for error in errors), errors
    assert after == before


def _task9_legacy_run(root: Path) -> tuple[Path, Path]:
    run_root = _artifact_contract_run(
        root,
        _legacy_bracelet_analysis(),
        {"action": "generate_rank_1", "selected_ranks": [1]},
    )
    generation = run_root / "generation" / "01"
    generation.mkdir(parents=True)
    (generation / "hand-reference.jpg").write_bytes(b"legacy-scene")
    (generation / "model.txt").write_text("gpt_image_2", encoding="utf-8")
    (generation / "prompt.txt").write_text("历史提示词", encoding="utf-8")
    _write_json(generation / "submit.json", {"ok": True, "data": {"out_task_id": "legacy-1"}})
    _write_json(generation / "result.json", {"ok": True, "data": {"status": "completed"}})
    (generation / "result.png").write_bytes(b"legacy-result")
    _write_json(
        generation / "qc.json",
        {
            "status": "pass",
            "passed": ["原图手腕检查通过", "原图手臂检查通过", "皮肤块迁移检查通过"],
            "failed": [],
            "notes": "未发现人物局部迁移",
        },
    )
    return run_root, generation


def _task10_modern_identity_run(
    root: Path,
    product_type: str,
) -> Path:
    run_root, _generation = _task9_modern_run(root)
    shutil.rmtree(run_root / "generation")
    data = _modern_analysis()
    if product_type == "pendant_necklace":
        data.update(
            {
                "product_type": "带链吊坠",
                "detected_product_type": "pendant_necklace",
                "confirmed_product_type": "pendant_necklace",
                "classification_evidence": ["完整链条与中央主吊坠清晰可见"],
                "visible_appearance": "完整链条，中央有一枚主吊坠",
                "has_pendant": True,
                "pendant_count": 1,
                "pendant_layer": 1,
                "pendant_position": "front_center",
                "pendant_orientation": "front_facing",
                "connection_structure": "metal_bail",
            }
        )
    elif product_type == "ring":
        data.update(
            {
                "product_type": "戒指",
                "detected_product_type": "ring",
                "confirmed_product_type": "ring",
                "classification_evidence": ["左手无名指根部可见单枚戒指"],
                "wear_position": "左手无名指根部",
                "visible_appearance": "单枚银色戒指",
                "length_category": None,
                "chain_or_strand_type": None,
                "ring_count": 1,
                "hand_side": "left",
                "finger_position": "ring",
                "ring_wear_style": "finger_base",
            }
        )
    product = ProductAnalysis.from_dict(data)
    analysis_data = product_analysis_to_dict(product)
    canonical = build_product_fidelity_constraints(product).to_dict()
    if canonical["review_status"] == "pending":
        canonical["review_status"] = "confirmed"
    _write_json(run_root / "analysis" / "product_analysis.json", analysis_data)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        canonical,
    )
    snapshot = json.loads(
        (run_root / "review" / "reference_composition_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    decision = {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
        "confirmation_snapshot": ProductConfirmationSnapshot.from_analysis(
            product
        ).to_dict(),
        "output_role": "hand_worn",
        "reference_snapshot_sha256": _task9_snapshot_digest(snapshot),
    }
    _write_json(run_root / "review" / "review_decision.json", decision)
    return run_root


def _modern_legacy_analysis(product_type: str) -> dict[str, object]:
    data = _modern_analysis()
    if product_type == "bracelet":
        data.update(
            {
                "product_type": "手链/手串",
                "detected_product_type": "bracelet",
                "confirmed_product_type": "bracelet",
                "classification_evidence": ["佩戴在左手腕的单条手链"],
                "wear_position": "左手腕",
                "visible_appearance": "单条红色圆珠手链",
                "length_category": None,
                "chain_or_strand_type": None,
            }
        )
    elif product_type == "pendant_necklace":
        data.update(
            {
                "product_type": "带链吊坠",
                "detected_product_type": "pendant_necklace",
                "confirmed_product_type": "pendant_necklace",
                "classification_evidence": ["完整链条与中央主吊坠清晰可见"],
                "visible_appearance": "完整链条，中央有一枚主吊坠",
                "has_pendant": True,
                "pendant_count": 1,
                "pendant_layer": 1,
                "pendant_position": "front_center",
                "pendant_orientation": "front_facing",
                "connection_structure": "metal_bail",
            }
        )
    elif product_type == "ring":
        data.update(
            {
                "product_type": "戒指",
                "detected_product_type": "ring",
                "confirmed_product_type": "ring",
                "classification_evidence": ["左手无名指根部可见单枚戒指"],
                "wear_position": "左手无名指根部",
                "visible_appearance": "单枚银色戒指",
                "length_category": None,
                "chain_or_strand_type": None,
                "ring_count": 1,
                "hand_side": "left",
                "finger_position": "ring",
                "ring_wear_style": "finger_base",
            }
        )
    return data


def test_legacy_read_only_modern_bracelet_生成决策无确认快照时库与_inspector_cli_通过(
    tmp_path: Path,
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / "bracelet")
    _write_json(
        run_root / "analysis" / "product_analysis.json",
        _modern_legacy_analysis("bracelet"),
    )
    decision_path = run_root / "review" / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["fidelity_confirmed"] = True
    decision.pop("confirmation_snapshot", None)
    _write_json(decision_path, decision)
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "legacy_read_only"
    )
    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0
    assert "legacy_read_only=true" in completed.stdout
    assert "Traceback" not in completed.stderr
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    "product_type",
    ("necklace", "pendant_necklace", "ring"),
)
def test_damaged_legacy_三类现代分析生成决策仍必须包含确认快照(
    tmp_path: Path,
    product_type: str,
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / product_type)
    _write_json(
        run_root / "analysis" / "product_analysis.json",
        _modern_legacy_analysis(product_type),
    )
    decision_path = run_root / "review" / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["fidelity_confirmed"] = True
    decision.pop("confirmation_snapshot", None)
    _write_json(decision_path, decision)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert any("确认快照" in error for error in state["errors"]), state


@pytest.mark.parametrize("product_type", ("necklace", "pendant_necklace", "ring"))
def test_damaged_modern_三品类生成决策缺确认快照时库与_inspector_同态(
    tmp_path: Path,
    product_type: str,
) -> None:
    run_root = _task10_modern_identity_run(tmp_path / product_type, product_type)
    paths = RunPaths(run_root)
    inspector = runpy.run_path(str(ARTIFACT_INSPECTOR))
    assert reference_composition.classify_reference_run(paths) == "modern_snapshot"
    assert inspector["inspect_run_state"](run_root)["errors"] == []
    decision_path = run_root / "review" / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision.pop("confirmation_snapshot")
    _write_json(decision_path, decision)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    state = inspector["inspect_run_state"](run_root)
    assert state["legacy_read_only"] is False
    assert any("确认快照" in error for error in state["errors"]), state
    with pytest.raises(ReviewGateError, match="确认快照|run 产物不完整/损坏"):
        require_generation_decision(paths)


@pytest.mark.parametrize(
    "mutation",
    ("non_object", "missing_field", "analysis_drift"),
)
def test_damaged_modern_确认快照非对象缺字段或与_analysis_漂移时同态(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root = _task10_modern_identity_run(tmp_path / mutation, "necklace")
    paths = RunPaths(run_root)
    decision_path = run_root / "review" / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if mutation == "non_object":
        decision["confirmation_snapshot"] = []
    elif mutation == "missing_field":
        decision["confirmation_snapshot"].pop("layer_count")
    else:
        decision["confirmation_snapshot"]["display_mode"] = "hand_held"
    _write_json(decision_path, decision)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](run_root)
    assert state["legacy_read_only"] is False
    assert any("确认快照" in error for error in state["errors"]), state
    with pytest.raises(ReviewGateError, match="确认快照|run 产物不完整/损坏"):
        require_generation_decision(paths)


def test_input_manifest_inspector_完整现代run通过且完整历史run只读(tmp_path: Path) -> None:
    modern_root, _generation = _task9_modern_run(tmp_path / "modern")
    namespace = runpy.run_path(str(ARTIFACT_INSPECTOR))
    assert namespace["inspect_run"](modern_root) == []

    legacy, _legacy_generation = _task9_legacy_run(tmp_path / "legacy")
    before = {path.relative_to(legacy): path.read_bytes() for path in legacy.rglob("*") if path.is_file()}
    result = namespace["inspect_run_state"](legacy)
    after = {path.relative_to(legacy): path.read_bytes() for path in legacy.rglob("*") if path.is_file()}
    assert result["legacy_read_only"] is True
    assert result["errors"] == []
    assert after == before


@pytest.mark.parametrize("mutation", ("missing_submit", "extra_empty", "legacy_fragment"))
def test_input_manifest_inspector_损坏历史run只读拒绝且不改磁盘(
    tmp_path: Path,
    mutation: str,
) -> None:
    legacy, generation = _task9_legacy_run(tmp_path / mutation)
    if mutation == "missing_submit":
        (generation / "submit.json").unlink()
    elif mutation == "extra_empty":
        (legacy / "generation" / "02").mkdir()
    else:
        fragment = legacy / "generation" / "02"
        fragment.mkdir()
        (fragment / "result.png").write_bytes(b"fragment")
    before = {path.relative_to(legacy): path.read_bytes() for path in legacy.rglob("*") if path.is_file()}
    result = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](legacy)
    after = {path.relative_to(legacy): path.read_bytes() for path in legacy.rglob("*") if path.is_file()}
    assert result["errors"]
    assert result["legacy_read_only"] is False
    assert any("damaged" in error or "submit.json" in error for error in result["errors"])
    assert after == before


def test_legacy_read_only_历史_selected_无现代摘要字段仍保持可读(
    tmp_path: Path,
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / "legacy-original")
    selected_path = run_root / "analysis" / "selected_references.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    for item in selected:
        item.pop("source_sha256", None)
        item.pop("review_sha256", None)
        item.pop("metadata", None)
    _write_json(selected_path, selected)
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "legacy_read_only"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )

    assert state == {
        "classified": True,
        "legacy_read_only": True,
        "errors": [],
    }
    assert _run_字节与目录快照(run_root) == before


def test_legacy_read_only_历史_selected_保留普通_metadata_仍允许库与_inspector_cli_通过(
    tmp_path: Path,
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / "legacy-metadata")
    selected_path = run_root / "analysis" / "selected_references.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    for item in selected:
        source_reference = item["metadata"]["source_reference"]
        item.pop("source_sha256", None)
        item.pop("review_sha256", None)
        item["metadata"] = {
            "file_name": Path(source_reference).name,
            "label": "历史参考图",
            "width": 100,
            "source_reference": source_reference,
        }
    _write_json(selected_path, selected)
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "legacy_read_only"
    )
    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0
    assert "legacy_read_only=true" in completed.stdout
    assert "Traceback" not in completed.stderr
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    "partial_field",
    ("top_source", "metadata_source", "top_review", "metadata_review"),
)
def test_damaged_legacy_selected_任一现代摘要字段单独出现就启动成组校验(
    tmp_path: Path,
    partial_field: str,
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / partial_field)
    selected_path = run_root / "analysis" / "selected_references.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    for item in selected:
        item.pop("source_sha256", None)
        item.pop("review_sha256", None)
        item["metadata"] = {"label": "历史参考图"}
    target = selected[0]
    if partial_field == "top_source":
        target["source_sha256"] = "0" * 64
    elif partial_field == "metadata_source":
        target["metadata"]["source_sha256"] = "0" * 64
    elif partial_field == "top_review":
        target["review_sha256"] = "0" * 64
    else:
        target["metadata"]["review_sha256"] = "0" * 64
    _write_json(selected_path, selected)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"]


@pytest.mark.parametrize(
    "mutation",
    (
        "unsupported_model",
        "result_not_completed",
        "invalid_qc",
        "invalid_analysis",
        "invalid_selected_rank",
        "decision_not_bound",
        "selected_digest",
    ),
)
def test_damaged_历史语义损坏时库与_inspector_等价拒绝且只读(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / mutation)
    if mutation == "unsupported_model":
        (generation / "model.txt").write_text("unsupported", encoding="utf-8")
    elif mutation == "result_not_completed":
        _write_json(generation / "result.json", {"data": {"status": "failed"}})
    elif mutation == "invalid_qc":
        _write_json(
            generation / "qc.json",
            {"status": "pass", "passed": [], "failed": ["存在失败项"]},
        )
    elif mutation == "invalid_analysis":
        analysis_path = run_root / "analysis" / "product_analysis.json"
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        analysis["product_type"] = "未知品类"
        _write_json(analysis_path, analysis)
    elif mutation == "invalid_selected_rank":
        selected_path = run_root / "analysis" / "selected_references.json"
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        selected[0]["rank"] = True
        _write_json(selected_path, selected)
    elif mutation == "decision_not_bound":
        decision_path = run_root / "review" / "review_decision.json"
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision["selected_ranks"] = [4]
        _write_json(decision_path, decision)
    else:
        selected_path = run_root / "analysis" / "selected_references.json"
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        selected[0]["source_sha256"] = "0" * 64
        selected[0]["metadata"]["source_sha256"] = "0" * 64
        _write_json(selected_path, selected)
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )

    assert state["legacy_read_only"] is False
    assert state["errors"]
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize("mutation", ("empty_prompt", "non_object_submit"))
def test_legacy_read_only_generation_只要_prompt_submit_文件存在就保持真实历史兼容(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / mutation)
    if mutation == "empty_prompt":
        (generation / "prompt.txt").write_text("", encoding="utf-8")
    else:
        _write_json(generation / "submit.json", [])
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "legacy_read_only"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )

    assert state == {
        "classified": True,
        "legacy_read_only": True,
        "errors": [],
    }
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    ("case", "invalid_bytes"),
    (
        ("single_invalid", b"\xff"),
        ("bad_continuation", b"\xc3\x28"),
        ("surrogate", b"\xed\xa0\x80"),
    ),
)
def test_damaged_legacy_prompt_非法_utf8_时库_inspector_cli_同态拒绝且只读(
    tmp_path: Path,
    case: str,
    invalid_bytes: bytes,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / case)
    (generation / "prompt.txt").write_bytes(invalid_bytes)
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert any("prompt.txt" in error and "UTF-8" in error for error in state["errors"])

    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 1
    assert "prompt.txt" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    "mutation",
    ("missing_notes", "empty_results", "missing_migration_checks", "critical_failure"),
)
def test_damaged_legacy_qc_与_portable_validator_既有业务语义完全同态(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / mutation)
    qc_path = generation / "qc.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    if mutation == "missing_notes":
        qc.pop("notes")
    elif mutation == "empty_results":
        qc["passed"] = []
        qc["failed"] = []
    elif mutation == "missing_migration_checks":
        qc["passed"] = ["人工复核通过"]
        qc["failed"] = []
        qc["notes"] = "已完成普通画面复核"
    else:
        qc["critical_failures"] = ["category_mismatch"]
    _write_json(qc_path, qc)
    before = _run_字节与目录快照(run_root)

    assert reference_composition.classify_reference_run(RunPaths(run_root)) == "damaged"
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )

    assert state["legacy_read_only"] is False
    assert state["errors"]
    assert _run_字节与目录快照(run_root) == before


def _legacy_must_keep_constraints(run_root: Path) -> list[dict[str, str]]:
    must_keep = [
        {"name": "主珠形状", "qc_question": "主珠是否保持圆形"},
        {"name": "珠序", "qc_question": "珠子排列顺序是否保持"},
    ]
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        {"must_keep": must_keep},
    )
    return must_keep


def _legacy_fidelity_check(item: dict[str, str]) -> dict[str, str]:
    return {
        "name": item["name"],
        "question": item["qc_question"],
        "result": "pass",
        "notes": "人工逐项确认通过",
    }


@pytest.mark.parametrize(
    ("case", "fidelity_checks"),
    (
        ("container_null", None),
        ("container_dict", {}),
        ("container_bool", True),
        ("container_string", "不是列表"),
        ("item_null", [None]),
        ("item_list", [[]]),
        ("item_bool", [True]),
        ("item_string", ["不是对象"]),
        ("item_dict_missing_fields", [{}]),
        (
            "result_null",
            [{"name": "主珠", "question": "是否保持", "result": None, "notes": ""}],
        ),
        (
            "result_list",
            [{"name": "主珠", "question": "是否保持", "result": [], "notes": ""}],
        ),
        (
            "result_dict",
            [{"name": "主珠", "question": "是否保持", "result": {}, "notes": ""}],
        ),
        (
            "result_bool",
            [{"name": "主珠", "question": "是否保持", "result": True, "notes": ""}],
        ),
        (
            "result_string",
            [{"name": "主珠", "question": "是否保持", "result": "unknown", "notes": ""}],
        ),
    ),
)
def test_damaged_legacy_qc_fidelity_checks_基础类型字段与_result_必须同态拒绝(
    tmp_path: Path,
    case: str,
    fidelity_checks: object,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / case)
    qc_path = generation / "qc.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    qc["fidelity_checks"] = fidelity_checks
    _write_json(qc_path, qc)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"], case


@pytest.mark.parametrize(
    "case",
    ("absent", "empty", "partial", "duplicate", "mismatch"),
)
def test_damaged_legacy_qc_存在_canonical_must_keep_时必须完整唯一覆盖(
    tmp_path: Path,
    case: str,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / case)
    must_keep = _legacy_must_keep_constraints(run_root)
    checks = [_legacy_fidelity_check(item) for item in must_keep]
    if case == "empty":
        checks = []
    elif case == "partial":
        checks = checks[:1]
    elif case == "duplicate":
        checks = [checks[0], dict(checks[0])]
    elif case == "mismatch":
        checks[1]["question"] = "不匹配的问题"
    qc_path = generation / "qc.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    if case != "absent":
        qc["fidelity_checks"] = checks
    _write_json(qc_path, qc)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"], case


def test_legacy_read_only_qc_完整覆盖_canonical_must_keep_时同态通过(
    tmp_path: Path,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / "complete")
    must_keep = _legacy_must_keep_constraints(run_root)
    qc_path = generation / "qc.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    qc["fidelity_checks"] = [
        _legacy_fidelity_check(item) for item in must_keep
    ]
    _write_json(qc_path, qc)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "legacy_read_only"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state == {
        "classified": True,
        "legacy_read_only": True,
        "errors": [],
    }


@pytest.mark.parametrize(
    ("case", "score"),
    (
        ("null", None),
        ("list", []),
        ("dict", {}),
        ("bool", True),
        ("string", "99"),
        ("float", 99.0),
    ),
)
def test_damaged_legacy_selected_score_必须是排除_bool_的_json_整数且同态(
    tmp_path: Path,
    case: str,
    score: object,
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / case)
    selected_path = run_root / "analysis" / "selected_references.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    selected[0]["score"] = score
    _write_json(selected_path, selected)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"], case


def _run_字节与目录快照(root: Path) -> tuple[set[Path], dict[Path, bytes]]:
    directories = {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_dir()
    }
    files = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    return directories, files


@pytest.mark.parametrize(
    "missing_artifact",
    (
        "candidate",
        "confirmed",
        "decision_digest",
        "manifest",
        "snapshot_copy",
        "analysis_copy",
        "canonical_copy",
    ),
)
def test_damaged_现代链删除任一关键文件不得降级为历史_run(
    tmp_path: Path,
    missing_artifact: str,
) -> None:
    run_root, generation = _task9_modern_run(tmp_path / missing_artifact)
    paths = RunPaths(run_root)
    target = {
        "candidate": run_root / "analysis" / "reference_composition_snapshots.json",
        "confirmed": run_root / "review" / "reference_composition_snapshot.json",
        "manifest": generation / "input-manifest.json",
        "snapshot_copy": generation / "reference-composition-snapshot.json",
        "analysis_copy": generation / "product-analysis.json",
        "canonical_copy": generation / "product-fidelity-constraints.json",
    }.get(missing_artifact)
    if target is not None:
        target.unlink()
    else:
        decision_path = run_root / "review" / "review_decision.json"
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision.pop("reference_snapshot_sha256")
        _write_json(decision_path, decision)
    before = _run_字节与目录快照(run_root)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](run_root)

    assert state["legacy_read_only"] is False
    assert state["errors"]
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    "modern_fragment",
    (
        "candidate",
        "confirmed",
        "decision_digest",
        "manifest",
        "snapshot_copy",
    ),
)
def test_damaged_历史_run_混入任一现代残片必须拒绝且只读(
    tmp_path: Path,
    modern_fragment: str,
) -> None:
    run_root, generation = _task9_legacy_run(tmp_path / modern_fragment)
    if modern_fragment == "candidate":
        _write_json(
            run_root / "analysis" / "reference_composition_snapshots.json",
            [],
        )
    elif modern_fragment == "confirmed":
        _write_json(
            run_root / "review" / "reference_composition_snapshot.json",
            {},
        )
    elif modern_fragment == "decision_digest":
        decision_path = run_root / "review" / "review_decision.json"
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision["reference_snapshot_sha256"] = "0" * 64
        _write_json(decision_path, decision)
    elif modern_fragment == "manifest":
        _write_json(generation / "input-manifest.json", {})
    else:
        _write_json(generation / "reference-composition-snapshot.json", {})
    before = _run_字节与目录快照(run_root)
    namespace = runpy.run_path(str(ARTIFACT_INSPECTOR))

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = namespace["inspect_run_state"](run_root)

    assert state["legacy_read_only"] is False
    assert state["errors"]
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize("source_kind", ("scene", "product"))
def test_damaged_现代_manifest_源路径重绑定不能保留现代状态(
    tmp_path: Path,
    source_kind: str,
) -> None:
    run_root, generation = _task9_modern_run(tmp_path / source_kind)
    manifest_path = generation / "input-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    index = 0 if source_kind == "scene" else 1
    alternative = run_root / "sources" / f"alternative-{source_kind}.jpg"
    alternative.write_bytes(
        (generation / manifest["inputs"][index]["copied_file"]).read_bytes()
    )
    manifest["inputs"][index]["source_path"] = str(alternative.resolve())
    _write_json(manifest_path, manifest)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )


def test_migration_inspector_完整历史_run_cli_只读通过(tmp_path: Path) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / "legacy-cli")
    before = _run_字节与目录快照(run_root)

    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0
    assert "legacy_read_only=true" in completed.stdout
    assert "Traceback" not in completed.stderr
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    ("action", "extra_args"),
    (
        ("rerank", []),
        ("manual_reference", ["--manual-reference", "manual.jpg"]),
        (
            "generate_rank_1",
            ["--fidelity-confirmed", "--selected-ranks", "1"],
        ),
    ),
)
def test_legacy_read_only_record_decision_cli_在写前业务拒绝且不改磁盘(
    tmp_path: Path,
    capsys,
    action: str,
    extra_args: list[str],
) -> None:
    run_root, _generation = _task9_legacy_run(tmp_path / action)
    _write_json(
        run_root / "analysis" / "output_role.json",
        {"output_role": "hand_worn"},
    )
    before = _run_字节与目录快照(run_root)

    exit_code = cli_main(
        [
            "record-decision",
            "--run-root",
            str(run_root),
            "--action",
            action,
            "--output-role",
            "hand_worn",
            *extra_args,
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "历史 run 只读" in captured.err
    assert "Traceback" not in captured.err
    assert _run_字节与目录快照(run_root) == before


def test_damaged_inspector_非对象_decision_cli_返回业务错误无_traceback(
    tmp_path: Path,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / "bad-decision-cli")
    _write_json(run_root / "review" / "review_decision.json", [])
    before = _run_字节与目录快照(run_root)

    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 1
    assert "review_decision.json 必须是 JSON 对象" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    "mutation",
    (
        "empty_object",
        "bad_rank",
        "bad_sha256",
        "missing_field",
        "bad_signature",
        "source_binding",
    ),
)
def test_damaged_inspector_逐项拒绝损坏候选快照且_cli_无_traceback(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / mutation)
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if mutation == "empty_object":
        candidates.append({})
    elif mutation == "bad_rank":
        candidates[1]["rank"] = True
    elif mutation == "bad_sha256":
        candidates[1]["reference_sha256"] = "A" * 64
    elif mutation == "missing_field":
        candidates[1].pop("lighting")
    elif mutation == "bad_signature":
        candidates[1]["composition_signature"] = "0" * 64
    else:
        candidates[1]["reference_file"] = candidates[0]["reference_file"]
        candidates[1]["reference_sha256"] = candidates[0]["reference_sha256"]
    _write_json(candidates_path, candidates)
    before = _run_字节与目录快照(run_root)

    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 1
    assert "候选" in completed.stderr or "快照" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize(
    "mutation",
    (
        "pose_empty_resigned",
        "target_bad_count_resigned",
        "visible_regions_string",
        "visibility_integer",
        "ui_risk_unknown",
        "pose_hand_side_list_resigned",
        "target_body_region_list_resigned",
        "other_jewelry_string",
        "framing_empty",
    ),
)
def test_damaged_inspector_重签名也不能绕过候选快照嵌套_schema_校验(
    tmp_path: Path,
    mutation: str,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / mutation)
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidate = candidates[1]
    if mutation == "pose_empty_resigned":
        candidate["pose"] = {}
    elif mutation == "target_bad_count_resigned":
        candidate["replacement_target"]["target_product_count"] = 2
    elif mutation == "visible_regions_string":
        candidate["visible_body_regions"] = "左手腕"
    elif mutation == "visibility_integer":
        candidate["product_visibility_sufficient"] = 1
    elif mutation == "ui_risk_unknown":
        candidate["text_or_ui_risk"] = "unknown"
    elif mutation == "pose_hand_side_list_resigned":
        candidate["pose"]["hand_side"] = []
    elif mutation == "target_body_region_list_resigned":
        candidate["replacement_target"]["body_region"] = []
    elif mutation == "other_jewelry_string":
        candidate["other_jewelry_to_remove"] = "无"
    else:
        candidate["framing"] = ""
    candidate["composition_signature"] = _task9_signature(candidate)
    _write_json(candidates_path, candidates)
    before = _run_字节与目录快照(run_root)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )

    assert state["legacy_read_only"] is False
    assert state["errors"], mutation
    assert _run_字节与目录快照(run_root) == before


@pytest.mark.parametrize("scope", ("top", "pose", "target"))
def test_damaged_参考构图快照三层未知字段必须被库与_inspector_同态拒绝(
    tmp_path: Path,
    scope: str,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / scope)
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidate = candidates[1]
    if scope == "top":
        candidate["未知顶层字段"] = "不允许"
    elif scope == "pose":
        candidate["pose"]["未知姿态字段"] = "不允许"
    else:
        candidate["replacement_target"]["未知目标字段"] = "不允许"
    candidate["composition_signature"] = _task9_signature(candidate)
    _write_json(candidates_path, candidates)

    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"]

    with pytest.raises(ValueError, match="未知字段"):
        if scope == "top":
            ReferenceCompositionSnapshot.from_dict(candidate)
        elif scope == "pose":
            ReferencePose.from_dict(candidate["pose"])
        else:
            ReplacementTarget.from_dict(candidate["replacement_target"])
    with pytest.raises(ValueError, match="未知字段"):
        ReferenceCompositionSnapshot.from_dict(candidate)
    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )


@pytest.mark.parametrize(
    ("case", "item"),
    (
        ("empty_string", ""),
        ("blank_string", "   "),
        ("null", None),
        ("list", []),
        ("dict", {}),
        ("bool", True),
        ("number", 1),
    ),
)
def test_damaged_other_jewelry_to_remove_元素必须是非空字符串且同态拒绝(
    tmp_path: Path,
    case: str,
    item: object,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / case)
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidate = candidates[1]
    candidate["other_jewelry_to_remove"] = [item]
    candidate["composition_signature"] = _task9_signature(candidate)
    _write_json(candidates_path, candidates)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"], case


@pytest.mark.parametrize(
    "items",
    ([], ["右手腕原手链"]),
)
def test_modern_snapshot_other_jewelry_to_remove_空列表与正常字符串保持合法(
    tmp_path: Path,
    items: list[str],
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / str(len(items)))
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidate = candidates[1]
    candidate["other_jewelry_to_remove"] = items
    candidate["composition_signature"] = _task9_signature(candidate)
    _write_json(candidates_path, candidates)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "modern_snapshot"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["errors"] == []


@pytest.mark.parametrize(
    ("case", "source_jewelry"),
    (
        ("ambiguous_string", "两条手链"),
        ("null", None),
        ("list", []),
        ("dict", {}),
        ("bool", True),
    ),
)
def test_damaged_候选快照多件同类首饰无唯一选择器时库与_inspector_同态拒绝(
    tmp_path: Path,
    case: str,
    source_jewelry: object,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / case)
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidate = candidates[1]
    candidate["replacement_target"]["source_jewelry"] = source_jewelry
    candidate["replacement_target"]["body_region"] = "左手腕"
    candidate["composition_signature"] = _task9_signature(candidate)
    _write_json(candidates_path, candidates)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "damaged"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["legacy_read_only"] is False
    assert state["errors"], case


@pytest.mark.parametrize(
    ("selector", "source_jewelry", "body_region"),
    (
        ("inner", "两条手链中的内侧手链", "左手腕内侧手链位置"),
        ("outer", "两条手链中的外侧手链", "左手腕外侧手链位置"),
        ("upper", "两条手链中的上方手链", "左手腕上方手链位置"),
        ("lower", "两条手链中的下方手链", "左手腕下方手链位置"),
        ("ordinal", "两条手链中的第2条", "左手腕第2条位置"),
    ),
)
def test_modern_snapshot_多件同类首饰显式唯一选择器保持库与_inspector_同态通过(
    tmp_path: Path,
    selector: str,
    source_jewelry: str,
    body_region: str,
) -> None:
    run_root, _generation = _task9_modern_run(tmp_path / selector)
    candidates_path = (
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidate = candidates[1]
    candidate["replacement_target"]["source_jewelry"] = source_jewelry
    candidate["replacement_target"]["body_region"] = body_region
    candidate["composition_signature"] = _task9_signature(candidate)
    _write_json(candidates_path, candidates)

    assert (
        reference_composition.classify_reference_run(RunPaths(run_root))
        == "modern_snapshot"
    )
    state = runpy.run_path(str(ARTIFACT_INSPECTOR))["inspect_run_state"](
        run_root
    )
    assert state["errors"] == []
