import re
from dataclasses import FrozenInstanceError

import pytest

from jewelry_on_hand.models import (
    ReferencePreservationCheck,
    ReferencePreservationEvidence,
)
from jewelry_on_hand.output_roles import OutputRole
from jewelry_on_hand.qc_review import (
    REFERENCE_PRESERVATION_QUESTIONS,
    build_reference_preservation_checklist,
    write_qc_review_page,
)
from jewelry_on_hand.reference_composition import (
    ReferenceCompositionSnapshot,
    ReferencePose,
    ReplacementTarget,
)
from jewelry_on_hand.run_paths import write_json


REFERENCE_CHECK_NAMES = (
    "framing_preserved",
    "pose_preserved",
    "subject_placement_preserved",
    "person_preserved",
    "clothing_preserved",
    "background_preserved",
    "lighting_preserved",
    "source_jewelry_removed",
    "replacement_target_preserved",
    "single_target_product",
)


def test_reference_preservation_check_is_immutable_and_requires_structured_evidence():
    check = ReferencePreservationCheck(
        name="framing_preserved",
        question=REFERENCE_PRESERVATION_QUESTIONS["framing_preserved"],
        result="pass",
        notes="人工 QC 通过，没有问题",
        evidence=ReferencePreservationEvidence(
            comparison_source="scene_reference",
            region="画面四周裁切边界及腕部主体",
            observation="腕部占画面宽度约三分之一，四边裁切位置与底图一致",
        ),
    )

    with pytest.raises(FrozenInstanceError):
        check.result = "fail"
    payload = check.to_dict()
    assert payload["issue_code"] is None
    assert payload["evidence"]["comparison_source"] == "scene_reference"
    assert ReferencePreservationCheck.from_dict(payload) == check
    with pytest.raises(ValueError, match="evidence.*必填"):
        ReferencePreservationCheck(
            name="framing_preserved",
            question=check.question,
            result="pass",
            notes="人工 QC 通过，没有问题",
        )
    with pytest.raises(ValueError, match="pass/rerun/fail"):
        ReferencePreservationCheck(
            name="framing_preserved",
            question=check.question,
            result="unknown",
            notes="对照参考图确认裁切边界一致",
            evidence=check.evidence,
        )


def test_reference_preservation_evidence_requires_controlled_source_region_and_observation():
    with pytest.raises(ValueError, match="comparison_source"):
        ReferencePreservationEvidence(
            comparison_source="manual_guess",
            region="左手腕",
            observation="位置一致",
        )
    with pytest.raises(ValueError, match="region"):
        ReferencePreservationEvidence(
            comparison_source="scene_reference",
            region="",
            observation="位置一致",
        )
    with pytest.raises(ValueError, match="observation"):
        ReferencePreservationEvidence(
            comparison_source="scene_reference",
            region="左手腕",
            observation="",
        )


def test_reference_check_rejects_wrong_comparison_source_for_check_name():
    with pytest.raises(ValueError, match="comparison_source.*framing_preserved"):
        ReferencePreservationCheck(
            name="framing_preserved",
            question=REFERENCE_PRESERVATION_QUESTIONS["framing_preserved"],
            result="pass",
            notes="补充说明",
            evidence=ReferencePreservationEvidence(
                comparison_source="product_identity",
                region="画面边界",
                observation="四边裁切一致",
            ),
        )


def test_pass_rejects_issue_code_and_source_jewelry_requires_severity_facts():
    evidence = ReferencePreservationEvidence(
        comparison_source="scene_reference",
        region="左手腕原首饰区域",
        observation="未见原首饰主体",
    )
    with pytest.raises(ValueError, match="pass.*issue_code"):
        ReferencePreservationCheck(
            name="source_jewelry_removed",
            question=REFERENCE_PRESERVATION_QUESTIONS["source_jewelry_removed"],
            result="pass",
            issue_code="minor_edge_residue",
            notes="补充说明",
            evidence=evidence,
        )
    with pytest.raises(
        ValueError,
        match="source_jewelry_subject_visible|residual_scope",
    ):
        ReferencePreservationCheck(
            name="source_jewelry_removed",
            question=REFERENCE_PRESERVATION_QUESTIONS["source_jewelry_removed"],
            result="pass",
            notes="补充说明",
            evidence=evidence,
        )


def test_reference_preservation_checklist_has_fixed_order_and_exact_questions():
    snapshot = _snapshot()

    checklist = build_reference_preservation_checklist(snapshot)

    assert tuple(name for name, _question in checklist) == REFERENCE_CHECK_NAMES
    assert checklist == tuple(REFERENCE_PRESERVATION_QUESTIONS.items())


def test_qc_review_page_renders_four_columns_real_relative_paths_and_snapshot(tmp_path):
    generation_dir = _complete_generation_dir(tmp_path)

    page = write_qc_review_page(generation_dir)

    html = page.read_text(encoding="utf-8")
    assert page == generation_dir / "qc-review.html"
    for heading in ("参考底图", "产品身份图", "生成结果", "已确认构图快照"):
        assert heading in html
    for relative_path in (
        "scene-reference.jpg",
        "product-reference.jpg",
        "result.png",
    ):
        assert f'src="{relative_path}"' in html
    assert "手腕近景，保留右侧留白" in html
    assert "深色木纹桌面" in html
    assert not (generation_dir / "qc.json").exists()
    assert len(re.findall(r'class="qc-column', html)) == 4


@pytest.mark.parametrize(
    "missing",
    [
        "scene-reference.jpg",
        "product-reference.jpg",
        "result.png",
        "reference-composition-snapshot.json",
    ],
)
def test_qc_review_page_rejects_any_missing_column_input_without_output(
    tmp_path,
    missing,
):
    generation_dir = _complete_generation_dir(tmp_path)
    (generation_dir / missing).unlink()

    with pytest.raises((FileNotFoundError, ValueError), match="缺少|唯一"):
        write_qc_review_page(generation_dir)

    assert not (generation_dir / "qc-review.html").exists()


def _complete_generation_dir(tmp_path):
    generation_dir = tmp_path / "run" / "generation" / "01"
    generation_dir.mkdir(parents=True)
    (generation_dir / "scene-reference.jpg").write_bytes(b"scene")
    (generation_dir / "product-reference.jpg").write_bytes(b"product")
    (generation_dir / "result.png").write_bytes(b"result")
    write_json(
        generation_dir / "reference-composition-snapshot.json",
        _snapshot().to_dict(),
    )
    return generation_dir


def _snapshot():
    return ReferenceCompositionSnapshot(
        rank=1,
        reference_file="rank-1-scene.jpg",
        reference_sha256="1" * 64,
        output_role=OutputRole.HAND_WORN,
        framing="手腕近景，保留右侧留白",
        camera_angle="轻微俯拍",
        subject_placement="手腕位于画面左下三分之一",
        visible_body_regions=("左手腕", "左前臂"),
        pose=ReferencePose(
            body="身体未入镜",
            arm="前臂斜向右上",
            hand="手背朝向镜头",
            hand_side="左手",
        ),
        clothing="黑色长袖，袖口位于前臂中段",
        background="深色木纹桌面",
        lighting="左上方暖色侧光",
        replacement_target=ReplacementTarget(
            body_region="左手腕",
            source_jewelry="原木珠手串",
            target_product_count=1,
        ),
        other_jewelry_to_remove=("原戒指",),
        text_or_ui_risk="none",
        product_visibility_sufficient=True,
        composition_signature="signature-1",
    )
