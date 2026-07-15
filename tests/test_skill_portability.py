from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from jewelry_on_hand.qc import build_qc_checklist, write_qc_result
from jewelry_on_hand.cli import _build_parser
from jewelry_on_hand.models import (
    ProductAnalysis,
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
PORTABLE_WORKFLOW = WORKFLOW_SKILL / "references" / "workflow.md"
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


def _document_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


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


def _task9_modern_run(root: Path, *, completed: bool = True) -> tuple[Path, Path]:
    generation = root / "generation" / "01"
    source_dir = root / "sources"
    for directory in (root / "input", root / "analysis", root / "review", generation, source_dir):
        directory.mkdir(parents=True, exist_ok=True)

    product_source = root / "input" / "product-on-hand.jpg"
    scene_source = source_dir / "rank-1-scene.jpg"
    product_source.write_bytes(b"product-identity")
    scene_source.write_bytes(b"scene-reference")
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
                "source_path": str(scene_source.resolve()),
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
    _write_json(root / "review" / "reference_composition_snapshot.json", snapshot_data)
    selected = []
    for rank in (1, 2, 3):
        path = scene_source if rank == 1 else source_dir / f"rank-{rank}-scene.jpg"
        if rank != 1:
            path.write_bytes(f"scene-{rank}".encode("ascii"))
        selected.append({"rank": rank, "selected_reference": str(path), "score": 101 - rank})
    _write_json(root / "analysis" / "selected_references.json", selected)
    _write_json(root / "review" / "review_decision.json", _modern_decision(analysis_data))

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
    _root, generation = _task9_modern_run(tmp_path / "run")
    manifest = json.loads((generation / "input-manifest.json").read_text(encoding="utf-8"))
    reference = manifest["inputs"][0]["source_path"]
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
    _root, generation = _task9_modern_run(tmp_path / mutation)
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
    errors = namespace["validate_reference_snapshot"](
        snapshot_path,
        Path(json.loads((generation / "input-manifest.json").read_text(encoding="utf-8"))["inputs"][0]["source_path"]),
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
    else:
        data = json.loads((run_root / "analysis" / "product_analysis.json").read_text(encoding="utf-8"))
        data["visible_appearance"] = "源文件被替换"
        _write_json(run_root / "analysis" / "product_analysis.json", data)
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
    }[mutation]
    assert any(expected in error for error in errors), errors
    assert after == before


def test_input_manifest_inspector_完整现代run通过且历史run只读(tmp_path: Path) -> None:
    modern_root, _generation = _task9_modern_run(tmp_path / "modern")
    namespace = runpy.run_path(str(ARTIFACT_INSPECTOR))
    assert namespace["inspect_run"](modern_root) == []

    legacy = tmp_path / "legacy"
    generation = legacy / "generation" / "01"
    generation.mkdir(parents=True)
    (generation / "hand-reference.jpg").write_bytes(b"legacy")
    (generation / "prompt.txt").write_text("历史提示词", encoding="utf-8")
    before = {path.relative_to(legacy): path.read_bytes() for path in legacy.rglob("*") if path.is_file()}
    result = namespace["inspect_run_state"](legacy)
    after = {path.relative_to(legacy): path.read_bytes() for path in legacy.rglob("*") if path.is_file()}
    assert result["legacy_read_only"] is True
    assert result["errors"] == []
    assert after == before
