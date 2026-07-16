from pathlib import Path
from runpy import run_path

import pytest

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductConfirmationSnapshot,
    ReferenceRow,
    ReviewDecision,
    ScoredReference,
)
from jewelry_on_hand.output_roles import (
    OutputRole,
    output_role_instruction,
    require_scene_replacement_role,
)
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.prompt_builder import build_prompt
from jewelry_on_hand.review_package import write_review_package
from jewelry_on_hand.run_paths import RunPaths, write_json


PROMPT_VALIDATOR = (
    Path(__file__).parents[1]
    / "skills"
    / "jewelry-on-hand-workflow"
    / "scripts"
    / "validate_prompt_contract.py"
)


@pytest.mark.parametrize("role", [OutputRole.HAND_WORN, "lifestyle"])
def test_scene_replacement_role_accepts_only_supported_roles(role):
    assert require_scene_replacement_role(role, stage="prepare-review") in {
        OutputRole.HAND_WORN,
        OutputRole.LIFESTYLE,
    }


@pytest.mark.parametrize("role", [None, OutputRole.HERO, "hero"])
def test_scene_replacement_role_rejects_missing_or_hero(role):
    with pytest.raises(ValueError, match="主图 Skill|hand_worn|lifestyle"):
        require_scene_replacement_role(role, stage="generate")


@pytest.mark.parametrize("role", [OutputRole.HERO, "hero"])
def test_output_role_instruction_rejects_hero(role):
    with pytest.raises(ValueError, match="主图 Skill"):
        output_role_instruction(
            role,
            ProductType.BRACELET,
            DisplayMode.WORN,
        )


def test_output_role_instruction_has_no_fixed_background_brightness():
    instruction = output_role_instruction(
        OutputRole.HAND_WORN,
        ProductType.BRACELET,
        DisplayMode.WORN,
    )

    assert "使用深色背景" not in instruction
    assert "深色背景" not in instruction
    assert "产品完整清晰" in instruction


def _analysis_payload() -> dict:
    return {
        "product_type": "普通项链",
        "detected_product_type": "necklace",
        "confirmed_product_type": "necklace",
        "classification_confidence": "high",
        "classification_evidence": ["两层完整链条与锁骨佩戴关系清晰"],
        "classification_source": "auto_confirmed",
        "display_mode": "worn",
        "source_image_type": "worn_source",
        "wear_position": "颈部至锁骨",
        "visible_appearance": "浅海蓝微珠双层项链，红橙微珠过渡区位于下层左侧",
        "color_family": ["浅海蓝", "红橙"],
        "style_mood": "自然简洁",
        "composition": "颈部至锁骨完整展示双层落差",
        "product_dimensions": {"length_mm": 900, "dimension_source": "用户录入"},
        "needs_full_front_display": True,
        "special_requirements": ["保持双层顺序与相对落差"],
        "layer_count": 2,
        "length_category": "long",
        "chain_or_strand_type": "微珠链",
        "has_pendant": False,
        "pendant_count": 0,
        "pendant_layer": None,
        "pendant_position": None,
        "pendant_orientation": None,
        "connection_structure": None,
        "symmetry": "沿身体中线自然分布",
        "occluded_parts": ["后颈连接结构"],
        "uncertain_details": [],
        "is_independent_multi_item": False,
    }


def _scored_reference(reference_path: Path) -> ScoredReference:
    row = ReferenceRow(
        index=1,
        file_name=reference_path.name,
        relative_path=reference_path.name,
        absolute_path=reference_path,
        width=1080,
        height=1440,
        size_mb=0.1,
        purpose_category="真人佩戴构图参考",
        bracelet_applicability="",
        default_strategy="常规可优先使用",
        style_category="自然生活感",
        scene_keywords="正面颈胸 浅色背景",
        jewelry_type="普通项链",
        recommended_usage="双层项链真人佩戴",
        notes="颈部、锁骨和胸前区域完整",
        confidence="高",
        file_exists=True,
        applicable_product_types="necklace",
        applicable_display_modes="worn",
        framing="颈部至胸前半身",
        visible_body_regions="颈部、锁骨、胸前",
        product_visibility="高",
        neck_visibility="完整",
        collarbone_visibility="完整",
        chest_visibility="完整",
        collar_type="低领",
        clothing_occlusion_risk="低",
        hair_occlusion_risk="低",
        pose_keywords="多层垂直空间 层间落差空间充足",
        existing_jewelry="无",
        crop_risk="低",
    )
    return ScoredReference(
        row=row,
        score=228,
        rank=1,
        reason=("品类、展示模式与垂直空间匹配",),
        risk=(),
        ignored_reference_jewelry=(),
    )


def _prompt_contract_errors(tmp_path: Path, prompt: str) -> list[str]:
    validate_prompt = run_path(str(PROMPT_VALIDATOR))["validate_prompt"]
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    return validate_prompt(prompt_path)


def _output_role_lines(prompt: str) -> list[str]:
    return [line for line in prompt.splitlines() if line.startswith("输出用途：")]


def test_build_prompt_without_output_role_omits_role_line_and_passes_validator(
    tmp_path,
):
    """直接构建的无角色 Prompt 不得注入用途行，并须满足便携契约。"""
    reference_path = tmp_path / "reference.jpg"
    reference_path.write_bytes(b"reference")
    product = ProductAnalysis.from_dict(_analysis_payload())
    prompt = build_prompt(
        product,
        _scored_reference(reference_path),
        build_product_fidelity_constraints(product),
        output_role=None,
    )

    assert _output_role_lines(prompt) == []
    assert _prompt_contract_errors(tmp_path, prompt) == []


def test_build_prompt_keeps_reference_scene_without_fixed_dark_instruction(tmp_path):
    reference_path = tmp_path / "reference.jpg"
    reference_path.write_bytes(b"reference")
    product = ProductAnalysis.from_dict(_analysis_payload())
    prompt = build_prompt(
        product,
        _scored_reference(reference_path),
        build_product_fidelity_constraints(product),
        output_role=OutputRole.LIFESTYLE,
    )

    assert "使用深色背景" not in prompt
    assert "参考图场景：正面颈胸 浅色背景" in prompt
    assert "生活场景图" in prompt


def test_cli_generate_without_output_role_rejects_before_provider_call(
    tmp_path,
    monkeypatch,
    capsys,
):
    """CLI 无角色 run 必须在调用 AIReiter 前失败。"""
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "no-output-role"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    product_path = input_dir / "product-on-hand.jpg"
    product_path.write_bytes(b"product")
    reference_path = tmp_path / "reference.jpg"
    reference_path.write_bytes(b"reference")
    paths = RunPaths(root=run_root)

    analysis_payload = _analysis_payload()
    product = ProductAnalysis.from_dict(analysis_payload)
    constraints = build_product_fidelity_constraints(product)
    decision_payload = {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "confirmation_snapshot": ProductConfirmationSnapshot.from_analysis(
            product
        ).to_dict(),
    }
    write_json(analysis_dir / "product_analysis.json", analysis_payload)
    write_json(analysis_dir / "product_fidelity_constraints.json", constraints.to_dict())
    scored_reference = _scored_reference(reference_path)
    write_review_package(
        paths,
        product_path,
        [scored_reference],
        [scored_reference],
    )
    write_json(review_dir / "review_decision.json", decision_payload)

    captured_prompts = {}

    def capture_prompts(
        _paths,
        _product_image,
        prompts_by_rank,
        _helper_script,
        wait=True,
    ):
        captured_prompts.update(prompts_by_rank)
        return []

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", capture_prompts)

    assert not (analysis_dir / "output_role.json").exists()
    assert ReviewDecision.from_dict(decision_payload).output_role is None
    assert main(
        [
            "generate",
            "--run-root",
            str(run_root),
            "--helper-script",
            str(tmp_path / "unused-helper.py"),
            "--no-wait",
        ]
    ) != 0
    assert "hand_worn" in capsys.readouterr().err
    assert captured_prompts == {}
    assert not (run_root / "generation").exists()
