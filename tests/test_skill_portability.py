from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from jewelry_on_hand.qc import (
    PENDANT_ABSENT_QC_QUESTION,
    build_qc_checklist,
    qc_check_id,
    write_qc_result,
)
from jewelry_on_hand.cli import _build_parser
from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductFidelityConstraints,
    ReferenceRow,
    ScoredReference,
)
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.prompt_builder import build_generation_prompt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SKILL = PROJECT_ROOT / "skills" / "jewelry-on-hand-workflow"
INSTALLER = PROJECT_ROOT / "scripts" / "install_codex_skills.py"
ARTIFACT_INSPECTOR = WORKFLOW_SKILL / "scripts" / "inspect_run_artifacts.py"
QC_VALIDATOR = WORKFLOW_SKILL / "scripts" / "validate_qc_record.py"
PROMPT_VALIDATOR = WORKFLOW_SKILL / "scripts" / "validate_prompt_contract.py"
PROJECT_GUIDE = PROJECT_ROOT / "CLAUDE.md"
MANUAL_WORKFLOW = PROJECT_ROOT / "reference" / "manual-workflow.md"
PROMPT_TEMPLATE = PROJECT_ROOT / "reference" / "prompt-template.md"
FIDELITY_SCHEMA = PROJECT_ROOT / "reference" / "product-fidelity-constraints-schema.md"
REVIEW_DECISION_SCHEMA = PROJECT_ROOT / "reference" / "review-decision-schema.md"
PORTABLE_WORKFLOW = WORKFLOW_SKILL / "references" / "workflow.md"
PORTABLE_PROMPT_CONTRACT = WORKFLOW_SKILL / "references" / "prompt-contract.md"
TROUBLESHOOTING = WORKFLOW_SKILL / "references" / "troubleshooting.md"
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
TASK11_PROOF_CONTRACT = "真实第三方模型 proof 属于 Task 11，尚未完成。"
PORTABLE_SEMANTIC_FIELD_PATHS = (
    "detected_keywords[0]",
    "must_not_change[0]",
    "must_keep[0].name",
    "must_keep[0].source_text",
    "must_keep[0].normalized_keyword",
    "must_keep[0].location",
    "must_keep[0].visual_shape",
    "must_keep[0].relationship",
    "must_keep[0].forbid[0]",
    "must_keep[0].qc_question",
)
PORTABLE_PRESENT_PENDANT_CONFLICT_PHRASES = (
    "无吊坠",
    "未见吊坠",
    "吊坠不存在",
    "吊坠缺失",
    "必须新增第二颗吊坠",
    "要求生成第二颗吊坠",
)


def _document_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_skill_documents_reference_selection_prompt_without_default_dark_rule() -> None:
    selection_documents = (
        WORKFLOW_SKILL / "SKILL.md",
        PORTABLE_WORKFLOW,
        MANUAL_WORKFLOW,
    )
    for document in selection_documents:
        text = _document_text(document)
        assert "--reference-selection-prompt" in text
        assert "有提示词" in text and "全部条件" in text and "硬约束" in text
        assert "无提示词" in text and "适用品类" in text and "关键词" in text
        assert "少于 3 张" in text and "阻断" in text
        assert "analysis/reference_selection_constraints.json" in text
        assert "reference_selection_constraints_sha256" in text

    for document in selection_documents + (
        PORTABLE_PROMPT_CONTRACT,
        PROMPT_TEMPLATE,
    ):
        text = _document_text(document)
        assert "选图提示词不得写入" in text
        assert "三个角色均须同时通过深色背景 gate" not in text
        assert "三个角色都要求深色背景" not in text
        assert "使用深色背景" not in text
        assert "USER_APPROVED_DARK" not in text
        assert "DARK_BACKGROUND_TEXT_TERMS" not in text


def test_prompt_documents_keep_reference_audit_out_of_model_prompt() -> None:
    documents = (
        WORKFLOW_SKILL / "SKILL.md",
        PORTABLE_PROMPT_CONTRACT,
        PROMPT_TEMPLATE,
    )
    for document in documents:
        text = _document_text(document)
        assert "送模投影" in text
        assert "参考图风格" in text
        assert "参考图场景" in text
        assert "参考图姿势" in text
        assert "审核与 generation metadata" in text

    contradictory = (
        "手串和项链参考区继续保留文件、路径、排名",
        "戒指送模只保留文件名",
    )
    for document in (PORTABLE_PROMPT_CONTRACT, PROMPT_TEMPLATE):
        text = _document_text(document)
        assert all(fragment not in text for fragment in contradictory)


@pytest.mark.parametrize(
    "document",
    [
        FIDELITY_SCHEMA,
        MANUAL_WORKFLOW,
        REVIEW_DECISION_SCHEMA,
        WORKFLOW_SKILL / "SKILL.md",
        PORTABLE_WORKFLOW,
        TROUBLESHOOTING,
    ],
)
def test_operator_documents_describe_v2_and_v1_read_only_boundary(
    document: Path,
) -> None:
    text = document.read_text(encoding="utf-8")

    assert "schema_version=2" in text
    assert "pendant_semantics" in text
    assert "历史 v1" in text
    assert "只读" in text
    assert "重新执行 `prepare-review`" in text or "重新执行 prepare-review" in text
    assert "历史 v1 会自动升级为 v2" not in text


def test_review_decision_schema_requires_exactly_one_primary_pendant() -> None:
    text = _document_text(REVIEW_DECISION_SCHEMA)

    assert "至少一个吊坠" not in text
    assert "恰好一个主吊坠" in text
    assert "pendant_count=1" in text


def test_fidelity_schema_json_examples_match_v1_v2_contract() -> None:
    blocks = re.findall(
        r"```json\s*\n(.*?)\n```",
        FIDELITY_SCHEMA.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    examples = [json.loads(block) for block in blocks]

    assert examples
    assert {example["schema_version"] for example in examples} == {1, 2}
    for example in examples:
        if example["schema_version"] == 2:
            ProductFidelityConstraints.from_dict(example)
        else:
            assert "pendant_semantics" not in example


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
        "ring",
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


@pytest.mark.parametrize(
    "document",
    [PROJECT_GUIDE, MANUAL_WORKFLOW, WORKFLOW_SKILL / "SKILL.md", PORTABLE_WORKFLOW],
)
def test_current_workflow_documents_describe_ring_analysis_and_source_routing(
    document: Path,
) -> None:
    text = _document_text(document)

    for field_name in (
        "ring_count",
        "hand_side",
        "finger_position",
        "ring_wear_style",
    ):
        assert field_name in text, f"{document} 缺少戒指分析字段 {field_name}"
    assert "飞书" in text and "默认" in text
    assert "--classification" in text and "Excel" in text


@pytest.mark.parametrize(
    "document",
    [MANUAL_WORKFLOW, WORKFLOW_SKILL / "SKILL.md", PORTABLE_WORKFLOW],
)
def test_operator_documents_describe_ring_reference_fields_and_qc_codes(
    document: Path,
) -> None:
    text = _document_text(document)

    for field_name in (
        "左右手",
        "可见手指",
        "手部朝向",
        "戒面可见度",
        "手指分离度",
        "手指遮挡风险",
    ):
        assert field_name in text, f"{document} 缺少戒指参考字段 {field_name}"
    for failure in (
        "ring_count_mismatch",
        "hand_side_mismatch",
        "finger_position_mismatch",
        "ring_structure_mismatch",
        "centerpiece_mismatch",
        "ring_contact_error",
        "finger_deformation",
        "source_hand_leakage",
    ):
        assert failure in text, f"{document} 缺少戒指 QC 代码 {failure}"


def test_fidelity_schema_and_troubleshooting_cover_ring_contract() -> None:
    fidelity_text = _document_text(FIDELITY_SCHEMA)
    troubleshooting_text = _document_text(TROUBLESHOOTING)

    for field_name in (
        "ring_count",
        "hand_side",
        "finger_position",
        "ring_wear_style",
    ):
        assert field_name in fidelity_text
    assert "不可见戒圈背面" in fidelity_text
    assert "少于三张" in troubleshooting_text or "Top 3" in troubleshooting_text
    assert "ring_count_mismatch" in troubleshooting_text
    assert "source_hand_leakage" in troubleshooting_text


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


def test_portable_workflow_keeps_product_identity_input_migration_boundary() -> None:
    required = (
        "产品上手图是生成阶段唯一产品身份图",
        "细节图只用于 review、结构分析和 QC",
        "不得作为第三张模型输入",
    )

    for document in (WORKFLOW_SKILL / "SKILL.md", PORTABLE_WORKFLOW):
        text = _document_text(document)
        for phrase in required:
            assert phrase in text

    portable_text = _document_text(PORTABLE_WORKFLOW)
    assert (
        "禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、"
        "皮肤块或背景。"
    ) in portable_text


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
def test_current_documents_share_exact_legacy_and_task11_contracts(document: Path) -> None:
    text = _document_text(document)

    assert MODERN_ATOMIC_CONTRACT in text
    assert LEGACY_EXPLICIT_CONTRACT in text
    assert TASK11_PROOF_CONTRACT in text


def test_current_documents_never_describe_the_whole_system_as_bracelet_only() -> None:
    forbidden = ("系统只支持手串", "系统仅支持手串", "全系统只支持手腕", "全系统仅支持手腕")

    for document in CURRENT_DOCUMENTS + (TROUBLESHOOTING,):
        text = _document_text(document)
        assert not any(fragment in text for fragment in forbidden), document


def test_reachable_source_files_have_no_question_mark_mojibake() -> None:
    source_root = PROJECT_ROOT / "src" / "jewelry_on_hand"

    for path in source_root.rglob("*.py"):
        assert "???" not in path.read_text(encoding="utf-8"), path


def test_fidelity_schema_json_examples_parse_and_keep_version_boundaries_separate() -> None:
    text = _document_text(FIDELITY_SCHEMA)
    examples = [
        json.loads(block.split("```", 1)[0])
        for block in text.split("```json\n")[1:]
    ]

    assert len(examples) == 3
    parsed = [ProductFidelityConstraints.from_dict(example) for example in examples]
    legacy = [item for item in parsed if item.schema_version == 1]
    modern = [item for item in parsed if item.schema_version == 2]

    assert len(legacy) == 1
    assert legacy[0].pendant_semantics is None
    assert len(modern) == 2
    assert {item.pendant_semantics.presence for item in modern} == {
        "absent",
        "present",
    }


def test_automatic_fidelity_extraction_does_not_fabricate_ring_or_layer_constraints() -> None:
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
    automatic = build_product_fidelity_constraints(ProductAnalysis.from_dict(data))

    assert automatic.detected_keywords == ("吊坠",)
    assert [item.normalized_keyword for item in automatic.must_keep] == ["吊坠"]
    assert "连接环" not in automatic.must_keep[0].relationship
    assert all("第二层" not in item for item in automatic.must_not_change)


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
    assert "最高优先级：只生成一枚目标戒指" in rules["【基础安全边界】"]
    assert "禁止生成手镯、手链、第二枚戒指" in rules["【基础安全边界】"]
    assert "手背朝镜头" in rules["【展示模式】"]
    assert "戒圈自然环绕手指" in rules["【遮挡与接触物理】"]
    for document in (
        PROJECT_ROOT / "reference" / "prompt-template.md",
        WORKFLOW_SKILL / "references" / "prompt-contract.md",
    ):
        text = _document_text(document)
        assert "ring" in text
        assert "戒指身份唯一来源" in text
        assert "不可见戒圈背面" in text


def test_portable_qc_validator_matches_model_ring_failure_sets() -> None:
    import jewelry_on_hand.models as models

    namespace = runpy.run_path(str(QC_VALIDATOR))

    assert namespace["ALLOWED_CRITICAL_FAILURES"] == models._QC_CRITICAL_FAILURES
    assert namespace["REJECT_CRITICAL_FAILURES"] == models._QC_REJECT_FAILURES
    for failure in (
        "ring_count_mismatch",
        "hand_side_mismatch",
        "finger_position_mismatch",
        "ring_structure_mismatch",
        "centerpiece_mismatch",
        "ring_contact_error",
        "finger_deformation",
        "source_hand_leakage",
    ):
        assert failure in namespace["ALLOWED_CRITICAL_FAILURES"]


@pytest.mark.parametrize(
    "missing_field",
    ("ring_count", "hand_side", "finger_position", "ring_wear_style"),
)
def test_artifact_inspector_rejects_ring_analysis_and_snapshot_missing_fields(
    tmp_path, missing_field
) -> None:
    analysis = _modern_ring_analysis()
    decision = _modern_decision(analysis)
    del analysis[missing_field]
    del decision["confirmation_snapshot"][missing_field]
    run_root = _artifact_contract_run(tmp_path, analysis, decision)

    errors = _inspect_run(run_root)

    assert any(missing_field in error for error in errors), errors


def test_artifact_inspector_accepts_valid_ring_contract_before_generation(tmp_path):
    analysis = _modern_ring_analysis()
    run_root = _artifact_contract_run(
        tmp_path,
        analysis,
        _modern_decision(analysis),
    )

    assert _inspect_run(run_root) == ["缺少 generation/NN 目录"]


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


def test_inspector_marks_v1_necklace_read_only_without_rewriting_json(
    tmp_path: Path,
) -> None:
    run_root, _ = _portable_complete_necklace_run(tmp_path / "v1-necklace", schema=1)
    before = {path: path.read_bytes() for path in run_root.rglob("*.json")}

    result = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    after = {path: path.read_bytes() for path in run_root.rglob("*.json")}

    assert result.returncode == 0, result.stderr
    assert "legacy_read_only=true" in result.stdout
    assert after == before


def test_inspector_and_prompt_validator_accept_v2_plain_necklace(
    tmp_path: Path,
) -> None:
    run_root, prompt_path = _portable_complete_necklace_run(
        tmp_path / "v2-necklace",
        schema=2,
    )

    inspected = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    prompt_validated = subprocess.run(
        [sys.executable, str(PROMPT_VALIDATOR), str(prompt_path)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert inspected.returncode == 0, inspected.stderr
    assert "legacy_read_only=false" in inspected.stdout
    assert prompt_validated.returncode == 0, prompt_validated.stderr


def test_inspector_reports_malformed_v2_lists_without_traceback(
    tmp_path: Path,
) -> None:
    run_root, _ = _portable_complete_necklace_run(
        tmp_path / "malformed-v2-necklace",
        schema=2,
    )
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    constraints["detected_keywords"] = None
    _write_json(constraints_path, constraints)

    result = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "v2 canonical 的 detected_keywords 必须是字符串列表" in result.stderr
    assert "Traceback" not in result.stderr


def test_inspector_rejects_v2_pendant_analysis_count_mismatch_without_traceback(
    tmp_path: Path,
) -> None:
    run_root, _ = _portable_complete_necklace_run(
        tmp_path / "v2-pendant-count-mismatch",
        schema=2,
        pendant=True,
    )
    analysis_path = run_root / "analysis" / "product_analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["pendant_count"] = 2
    _write_json(analysis_path, analysis)
    decision_path = run_root / "review" / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["confirmation_snapshot"]["pendant_count"] = 2
    _write_json(decision_path, decision)

    result = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "analysis.pendant_count" in result.stderr
    assert "Traceback" not in result.stderr


def test_portable_qc_validator_rejects_v2_pendant_wrong_layer(
    tmp_path: Path,
) -> None:
    _, _, qc_path = _portable_complete_necklace_run(
        tmp_path / "v2-pendant",
        schema=2,
        pendant=True,
        include_qc_path=True,
    )

    valid = subprocess.run(
        [sys.executable, str(QC_VALIDATOR), str(qc_path)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr

    data = json.loads(qc_path.read_text(encoding="utf-8"))
    for check in data["checklist_checks"]:
        if check["question"] == "现有主吊坠数量是否为 1，且仍位于第 2 层并保持原连接关系":
            check["question"] = "现有主吊坠数量是否为 1，且仍位于第 1 层并保持原连接关系"
            check["id"] = qc_check_id(check["question"])
            break
    _write_json(qc_path, data)

    invalid = subprocess.run(
        [sys.executable, str(QC_VALIDATOR), str(qc_path)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert invalid.returncode != 0


def test_portable_qc_validator_rejects_v2_pendant_analysis_count_mismatch(
    tmp_path: Path,
) -> None:
    run_root, _, qc_path = _portable_complete_necklace_run(
        tmp_path / "v2-pendant-qc-count-mismatch",
        schema=2,
        pendant=True,
        include_qc_path=True,
    )
    analysis_path = run_root / "analysis" / "product_analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["pendant_count"] = 2
    _write_json(analysis_path, analysis)
    before = qc_path.read_bytes()

    result = subprocess.run(
        [sys.executable, str(QC_VALIDATOR), str(qc_path)],
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "analysis.pendant_count" in result.stderr
    assert "Traceback" not in result.stderr
    assert qc_path.read_bytes() == before


@pytest.mark.parametrize("validator", ["inspector", "qc"])
def test_portable_v2_plain_necklace_requires_explicit_null_pendant_layer(
    tmp_path: Path, validator: str
) -> None:
    run_root, _, qc_path = _portable_complete_necklace_run(
        tmp_path / f"v2-plain-necklace-missing-layer-{validator}",
        schema=2,
        include_qc_path=True,
    )
    analysis_path = run_root / "analysis" / "product_analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    del analysis["pendant_layer"]
    _write_json(analysis_path, analysis)
    command = (
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)]
        if validator == "inspector"
        else [sys.executable, str(QC_VALIDATOR), str(qc_path)]
    )

    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "analysis.pendant_layer" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("validator", ["inspector", "qc"])
def test_portable_v2_absent_canonical_rejects_missing_semantics_layer_key(
    tmp_path: Path, validator: str
) -> None:
    run_root, _, qc_path = _portable_complete_necklace_run(
        tmp_path / f"v2-absent-canonical-missing-layer-{validator}",
        schema=2,
        include_qc_path=True,
    )
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    del constraints["pendant_semantics"]["layer"]
    _write_json(constraints_path, constraints)
    before_qc = qc_path.read_bytes()
    command = (
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)]
        if validator == "inspector"
        else [sys.executable, str(QC_VALIDATOR), str(qc_path)]
    )

    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "pendant_semantics.layer" in result.stderr
    assert "Traceback" not in result.stderr
    if validator == "qc":
        assert qc_path.read_bytes() == before_qc


@pytest.mark.parametrize("validator", ["inspector", "qc"])
def test_portable_v2_absent_canonical_accepts_explicit_null_semantics_layer(
    tmp_path: Path, validator: str
) -> None:
    run_root, _, qc_path = _portable_complete_necklace_run(
        tmp_path / f"v2-absent-canonical-null-layer-{validator}",
        schema=2,
        include_qc_path=True,
    )
    command = (
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)]
        if validator == "inspector"
        else [sys.executable, str(QC_VALIDATOR), str(qc_path)]
    )

    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "conflict_phrase", PORTABLE_PRESENT_PENDANT_CONFLICT_PHRASES
)
@pytest.mark.parametrize("field_path", PORTABLE_SEMANTIC_FIELD_PATHS)
def test_portable_shared_helper_rejects_present_conflict_matrix(
    field_path: str, conflict_phrase: str
) -> None:
    constraints = _portable_present_constraints_data()
    _inject_portable_semantic_text(constraints, field_path, conflict_phrase)
    namespace = runpy.run_path(str(QC_VALIDATOR))

    errors = namespace["_validate_present_pendant_semantic_conflicts"](constraints)

    assert errors == [f"{field_path} 与 present canonical 冲突：{conflict_phrase}"]


def test_portable_shared_helper_accepts_forbid_second_pendant_protection() -> None:
    constraints = _portable_present_constraints_data()
    _inject_portable_semantic_text(
        constraints,
        "must_not_change[0]",
        "禁止新增第二颗吊坠",
    )
    namespace = runpy.run_path(str(QC_VALIDATOR))

    assert namespace["_validate_present_pendant_semantic_conflicts"](constraints) == []


@pytest.mark.parametrize("validator", ["inspector", "qc"])
def test_portable_process_rejects_present_semantic_conflict_without_traceback(
    tmp_path: Path, validator: str
) -> None:
    run_root, _, qc_path = _portable_complete_necklace_run(
        tmp_path / f"v2-present-conflict-{validator}",
        schema=2,
        pendant=True,
        include_qc_path=True,
    )
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    _inject_portable_semantic_text(
        constraints,
        "must_not_change[0]",
        "吊坠缺失",
    )
    _write_json(constraints_path, constraints)
    before_qc = qc_path.read_bytes()
    command = (
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)]
        if validator == "inspector"
        else [sys.executable, str(QC_VALIDATOR), str(qc_path)]
    )

    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must_not_change[0] 与 present canonical 冲突：吊坠缺失" in result.stderr
    assert "Traceback" not in result.stderr
    if validator == "qc":
        assert qc_path.read_bytes() == before_qc


@pytest.mark.parametrize("validator", ["inspector", "qc"])
def test_portable_process_accepts_forbid_second_pendant_protection(
    tmp_path: Path, validator: str
) -> None:
    run_root, _, qc_path = _portable_complete_necklace_run(
        tmp_path / f"v2-present-protection-{validator}",
        schema=2,
        pendant=True,
        include_qc_path=True,
    )
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    _inject_portable_semantic_text(
        constraints,
        "must_not_change[0]",
        "禁止新增第二颗吊坠",
    )
    _write_json(constraints_path, constraints)
    command = (
        [sys.executable, str(ARTIFACT_INSPECTOR), str(run_root)]
        if validator == "inspector"
        else [sys.executable, str(QC_VALIDATOR), str(qc_path)]
    )

    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_portable_present_conflict_gate_does_not_import_project_package() -> None:
    for script in (ARTIFACT_INSPECTOR, QC_VALIDATOR):
        text = script.read_text(encoding="utf-8")
        assert "import jewelry_on_hand" not in text
        assert "from jewelry_on_hand" not in text


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
    analysis_data = _modern_analysis()
    _write_json(run_root / "analysis" / "product_analysis.json", analysis_data)
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
            "checklist_checks": _portable_checklist_checks(
                analysis_data,
                constraints,
            ),
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert errors == []


def test_qc_writer_output_passes_portable_validator_for_standard_run(tmp_path):
    run_root = tmp_path / "run"
    generation_dir = run_root / "generation" / "01"
    constraints_path = run_root / "analysis" / "product_fidelity_constraints.json"
    constraints_path.parent.mkdir(parents=True)
    constraints_data = _portable_constraints_with_must_keep()
    analysis_data = _modern_analysis()
    _write_json(constraints_path, constraints_data)
    _write_json(run_root / "analysis" / "product_analysis.json", analysis_data)

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
        checklist_checks=_portable_checklist_checks(
            analysis_data,
            constraints_data,
        ),
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert errors == []


def test_portable_qc_validator_rejects_conflicting_results_for_same_question(
    tmp_path,
):
    run_root = tmp_path / "run"
    qc_path = run_root / "generation" / "01" / "qc.json"
    constraints_data = _portable_constraints_with_must_keep()
    analysis_data = _modern_analysis()
    (run_root / "analysis").mkdir(parents=True)
    qc_path.parent.mkdir(parents=True)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        constraints_data,
    )
    _write_json(run_root / "analysis" / "product_analysis.json", analysis_data)
    checklist_checks = _portable_checklist_checks(
        analysis_data,
        constraints_data,
    )
    target_question = constraints_data["must_keep"][0]["qc_question"]
    next(
        item for item in checklist_checks if item["question"] == target_question
    )["result"] = "rerun"
    _write_json(
        qc_path,
        {
            "status": "rerun",
            "passed": ["其余检查通过"],
            "failed": ["需要重跑"],
            "notes": "",
            "fidelity_checks": [
                {
                    "name": "主吊坠",
                    "question": target_question,
                    "result": "pass",
                    "notes": "保持原连接",
                }
            ],
            "checklist_checks": checklist_checks,
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert (
        "fidelity_checks 与 checklist_checks 对同一 question 的 result 必须一致："
        + target_question
    ) in errors


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


def test_portable_qc_validator_requires_exact_runtime_checklist_for_modern_run(
    tmp_path,
):
    run_root = tmp_path / "modern-ring"
    qc_path = run_root / "generation" / "01" / "qc.json"
    analysis_data = _modern_ring_analysis() | {
        "needs_full_front_display": True,
        "special_requirements": [],
        "occluded_parts": ["戒圈背面"],
        "uncertain_details": ["镶嵌背面结构"],
    }
    analysis = ProductAnalysis.from_dict(analysis_data)
    constraints = build_product_fidelity_constraints(analysis)
    constraints_data = constraints.to_dict()
    constraints_data["review_status"] = "confirmed"
    (run_root / "analysis").mkdir(parents=True)
    qc_path.parent.mkdir(parents=True)
    _write_json(run_root / "analysis" / "product_analysis.json", analysis_data)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        constraints_data,
    )
    _write_json(
        qc_path,
        {
            "status": "pass",
            "passed": ["没有迁移产品图中的手部，迁移检查通过"],
            "failed": [],
            "notes": "",
            "fidelity_checks": [
                {
                    "name": item.name,
                    "question": item.qc_question,
                    "result": "pass",
                    "notes": "已核对",
                }
                for item in constraints.must_keep
            ],
        },
    )

    errors = runpy.run_path(str(QC_VALIDATOR))["validate_qc"](qc_path)

    assert any("checklist_checks" in error and "完整覆盖" in error for error in errors)


@pytest.mark.parametrize("product_type", ["ring", "bracelet"])
def test_portable_v2_non_necklace_qc_does_not_require_pendant_question(
    tmp_path: Path,
    product_type: str,
) -> None:
    analysis_data = (
        _modern_ring_analysis()
        if product_type == "ring"
        else _modern_bracelet_analysis()
    )
    analysis = ProductAnalysis.from_dict(analysis_data)
    constraints_data = build_product_fidelity_constraints(analysis).to_dict()
    constraints_data.update(
        {
            "schema_version": 2,
            "pendant_semantics": {
                "presence": "absent",
                "count": 0,
                "layer": None,
                "creation_policy": "forbid",
            },
            "review_status": "confirmed",
        }
    )
    constraints = ProductFidelityConstraints.from_dict(constraints_data)
    expected_questions = build_qc_checklist(
        analysis.normalized_product_type,
        analysis.display_mode,
        constraints.must_keep,
        product_analysis=analysis,
        fidelity_constraints=constraints,
    )
    assert PENDANT_ABSENT_QC_QUESTION not in expected_questions

    run_root = tmp_path / product_type
    qc_path = run_root / "generation" / "01" / "qc.json"
    (run_root / "analysis").mkdir(parents=True)
    qc_path.parent.mkdir(parents=True)
    _write_json(run_root / "analysis" / "product_analysis.json", analysis_data)
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        constraints_data,
    )
    _write_json(
        qc_path,
        {
            "status": "pass",
            "passed": ["产品结构与人物局部迁移检查通过"],
            "failed": [],
            "notes": "",
            "fidelity_checks": [
                {
                    "name": item.name,
                    "question": item.qc_question,
                    "result": "pass",
                    "notes": "已核对",
                }
                for item in constraints.must_keep
            ],
            "checklist_checks": [
                {
                    "id": qc_check_id(question),
                    "question": question,
                    "result": "pass",
                    "notes": "已核对",
                }
                for question in expected_questions
            ],
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


def _portable_checklist_checks(analysis_data, constraints_data):
    analysis = ProductAnalysis.from_dict(analysis_data)
    constraints = ProductFidelityConstraints.from_dict(constraints_data)
    return [
        {
            "id": qc_check_id(question),
            "question": question,
            "result": "pass",
            "notes": "已核对",
        }
        for question in build_qc_checklist(
            analysis.normalized_product_type,
            analysis.display_mode,
            constraints.must_keep,
        )
    ]


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
        selected.append(
            {
                "rank": rank,
                "selected_reference": str(reference),
                "score": 100 - rank,
            }
        )
    _write_json(root / "analysis" / "selected_references.json", selected)
    _write_json(root / "review" / "review_decision.json", decision)
    return root


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _portable_present_constraints_data() -> dict[str, object]:
    analysis_data = _modern_analysis()
    analysis_data.update(
        {
            "product_type": "带链吊坠",
            "detected_product_type": "pendant_necklace",
            "confirmed_product_type": "pendant_necklace",
            "visible_appearance": "双层细链，第二层中央有一颗水滴形主吊坠",
            "layer_count": 2,
            "has_pendant": True,
            "pendant_count": 1,
            "pendant_layer": 2,
            "pendant_position": "第二层中央",
            "pendant_orientation": "正面朝向镜头",
            "connection_structure": "吊环连接第二层链条",
        }
    )
    return build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis_data)
    ).to_dict()


def _inject_portable_semantic_text(
    constraints: dict[str, object], field_path: str, text: str
) -> None:
    if field_path == "detected_keywords[0]":
        constraints["detected_keywords"] = [text]
        return
    if field_path == "must_not_change[0]":
        constraints["must_not_change"] = [text]
        return
    must_keep = constraints["must_keep"]
    assert isinstance(must_keep, list) and isinstance(must_keep[0], dict)
    field_name = field_path.removeprefix("must_keep[0].")
    if field_name == "forbid[0]":
        must_keep[0]["forbid"] = [text]
    else:
        must_keep[0][field_name] = text


def _portable_complete_necklace_run(
    root: Path,
    *,
    schema: int,
    pendant: bool = False,
    include_qc_path: bool = False,
):
    analysis_data = _modern_analysis()
    if pendant:
        analysis_data.update(
            {
                "product_type": "带链吊坠",
                "detected_product_type": "pendant_necklace",
                "confirmed_product_type": "pendant_necklace",
                "visible_appearance": "双层细链，第二层中央有一颗水滴形主吊坠",
                "layer_count": 2,
                "has_pendant": True,
                "pendant_count": 1,
                "pendant_layer": 2,
                "pendant_position": "第二层中央",
                "pendant_orientation": "正面朝向镜头",
                "connection_structure": "吊环连接第二层链条",
            }
        )
    analysis = ProductAnalysis.from_dict(analysis_data)
    v2_constraints = build_product_fidelity_constraints(analysis)
    constraints_data = v2_constraints.to_dict()
    if schema == 1:
        constraints_data = {
            "schema_version": 1,
            "source": {
                "product_id": "PN-LEGACY",
                "product_image": "input/product-on-hand.jpg",
                "product_analysis": "analysis/product_analysis.json",
            },
            "detected_keywords": [],
            "must_keep": [],
            "must_not_change": ["层间关系"],
            "needs_user_review": False,
            "detail_crop_recommended": False,
            "review_status": "confirmed",
        }
    constraints = ProductFidelityConstraints.from_dict(constraints_data)
    run_root = _artifact_contract_run(root, analysis_data, _modern_decision(analysis_data))
    _write_json(
        run_root / "analysis" / "product_fidelity_constraints.json",
        constraints_data,
    )

    reference_path = run_root / "reference-1.jpg"
    row = ReferenceRow(
        index=1,
        file_name=reference_path.name,
        relative_path=reference_path.name,
        absolute_path=reference_path,
        width=100,
        height=200,
        size_mb=0.1,
        purpose_category="上手姿势参考",
        bracelet_applicability="是",
        default_strategy="常规可用",
        style_category="自然",
        scene_keywords="室内",
        jewelry_type="项链",
        recommended_usage="胸前近景",
        notes="",
        confidence="高",
        file_exists=True,
    )
    scored = ScoredReference(
        row=row,
        score=100,
        rank=1,
        reason=("构图匹配",),
        risk=(),
        ignored_reference_jewelry=(),
    )
    prompt = build_generation_prompt(analysis, scored, v2_constraints)
    generation_dir = run_root / "generation" / "01"
    generation_dir.mkdir(parents=True)
    (generation_dir / "model.txt").write_text("nano_banana_v2", encoding="utf-8")
    prompt_path = generation_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    (generation_dir / "hand-reference.jpg").write_bytes(b"reference")
    _write_json(generation_dir / "submit.json", {"ok": True})
    _write_json(generation_dir / "result.json", {"data": {"status": "completed"}})
    (generation_dir / "result.png").write_bytes(b"result")

    checklist_context = (
        {"product_analysis": analysis, "fidelity_constraints": constraints}
        if schema == 2
        else {}
    )
    checklist = build_qc_checklist(
        analysis.normalized_product_type,
        analysis.display_mode,
        constraints.must_keep,
        **checklist_context,
    )
    qc_path = generation_dir / "qc.json"
    _write_json(
        qc_path,
        {
            "status": "pass",
            "passed": ["没有迁移产品图中的人物局部，迁移检查通过"],
            "failed": [],
            "notes": "",
            "fidelity_checks": [
                {
                    "name": item.name,
                    "question": item.qc_question,
                    "result": "pass",
                    "notes": "已核对",
                }
                for item in constraints.must_keep
            ],
            "checklist_checks": [
                {
                    "id": qc_check_id(question),
                    "question": question,
                    "result": "pass",
                    "notes": "已核对",
                }
                for question in checklist
            ],
        },
    )
    if include_qc_path:
        return run_root, prompt_path, qc_path
    return run_root, prompt_path


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


def _modern_bracelet_analysis() -> dict[str, object]:
    return {
        "product_type": "手链/手串",
        "detected_product_type": "bracelet",
        "confirmed_product_type": "bracelet",
        "classification_confidence": "high",
        "classification_evidence": ["手腕处可见单圈圆珠手串"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "wear_position": "手腕",
        "visible_appearance": "深红圆珠单圈手串",
        "color_family": ["深红"],
        "style_mood": "自然",
        "composition": "手腕近景",
        "product_dimensions": {},
        "layer_count": 1,
        "length_category": None,
        "chain_or_strand_type": None,
        "has_pendant": False,
        "pendant_count": 0,
        "pendant_layer": None,
        "pendant_position": None,
        "pendant_orientation": None,
        "connection_structure": None,
        "is_independent_multi_item": False,
    }


def _modern_ring_analysis() -> dict[str, object]:
    return {
        "product_type": "戒指",
        "detected_product_type": "ring",
        "confirmed_product_type": "ring",
        "classification_confidence": "high",
        "classification_evidence": ["左手无名指根部可见单枚戒指"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "wear_position": "左手无名指根部",
        "visible_appearance": "单枚银色戒指",
        "color_family": ["银色"],
        "style_mood": "自然",
        "composition": "手部近景",
        "product_dimensions": {},
        "layer_count": 1,
        "length_category": None,
        "chain_or_strand_type": None,
        "has_pendant": False,
        "pendant_count": 0,
        "pendant_layer": None,
        "pendant_position": None,
        "pendant_orientation": None,
        "connection_structure": None,
        "is_independent_multi_item": False,
        "ring_count": 1,
        "hand_side": "left",
        "finger_position": "ring",
        "ring_wear_style": "finger_base",
    }


def _modern_decision(analysis: dict[str, object]) -> dict[str, object]:
    snapshot_fields = [
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
    ]
    if analysis["confirmed_product_type"] == "ring":
        snapshot_fields.extend(
            ("ring_count", "hand_side", "finger_position", "ring_wear_style")
        )
    return {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "confirmation_snapshot": {
            field_name: analysis[field_name] for field_name in snapshot_fields
        },
    }
