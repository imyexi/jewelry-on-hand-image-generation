from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductConfirmationSnapshot,
    ProductFidelityConstraints,
    ReviewDecision,
    ScoredReference,
)
from jewelry_on_hand.output_roles import (
    OutputRole,
    normalize_output_role,
    require_scene_replacement_role,
)
from jewelry_on_hand.product_analysis import (
    validate_analysis_ready_for_reference_selection,
)
from jewelry_on_hand.product_fidelity import (
    validate_product_fidelity_constraints,
)
from jewelry_on_hand.run_paths import RunPaths


REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME = (
    "reference_composition_snapshots.json"
)
REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME = "reference_composition_snapshot.json"

TextOrUiRisk = Literal["none", "small_removable", "blocking"]
ReferenceRunState = Literal["modern_snapshot", "legacy_read_only", "damaged"]
_TEXT_OR_UI_RISKS = frozenset({"none", "small_removable", "blocking"})
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_LEGACY_GENERATION_FILES = frozenset(
    {"model.txt", "prompt.txt", "submit.json", "result.json", "result.png", "qc.json"}
)
_MODERN_GENERATION_MARKERS = frozenset(
    {
        "input-manifest.json",
        "reference-composition-snapshot.json",
        "product-analysis.json",
        "product-fidelity-constraints.json",
        "reference-rank.txt",
        "qc-review.html",
    }
)
_LEGACY_ALLOWED_CRITICAL_FAILURES = frozenset(
    {
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
)
_LEGACY_REJECT_CRITICAL_FAILURES = frozenset(
    {
        "category_mismatch",
        "core_structure_missing",
        "multi_layer_restructured",
        "auto_chain_added",
        "severe_intersection",
        "ring_count_mismatch",
        "finger_position_mismatch",
        "ring_structure_mismatch",
        "centerpiece_mismatch",
        "source_hand_leakage",
    }
)
_LEGACY_SOURCE_WRIST_TERMS = (
    "原图手腕",
    "源图手腕",
    "source wrist",
    "source-wrist",
    "粗手腕",
)
_LEGACY_SOURCE_ARM_TERMS = (
    "原图手臂",
    "源图手臂",
    "source-arm",
    "source arm",
    "局部手臂",
)
_LEGACY_SOURCE_SKIN_TERMS = ("皮肤块", "局部贴片", "肤色", "皮肤纹理")
_LEGACY_SOURCE_PERSON_TERMS = (
    "产品图中的人物",
    "产品图人物局部",
    "产品原图的人物",
    "产品图中的颈部",
    "产品图中的胸部",
    "产品图中的衣服",
    "产品图中的头发",
    "产品图中的皮肤块",
)
_LEGACY_NEGATED_CHECK_TERMS = (
    "没有检查",
    "未检查",
    "没检查",
    "未做检查",
    "没有做检查",
    "未明确检查",
)
_LEGACY_PASS_CHECK_TERMS = (
    "检查通过",
    "迁移检查通过",
    "来源一致性通过",
    "未发现",
    "未见",
    "无迁移",
    "没有迁移",
    "未迁移",
    "无源图手臂局部贴片",
)
_LEGACY_REJECT_FAILURE_TERMS = (
    "品类错误",
    "品类不一致",
    "核心结构缺失",
    "核心配件缺失",
    "多层关系重组",
    "层间关系重组",
    "自动补链",
    "凭空补链",
    "严重穿模",
    "严重穿透",
)


@dataclass(frozen=True)
class ReferencePose:
    body: str
    arm: str
    hand: str
    hand_side: str

    def __post_init__(self) -> None:
        for field_name in ("body", "arm", "hand", "hand_side"):
            _require_string(getattr(self, field_name), f"pose.{field_name}")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ReferencePose":
        source = _require_mapping(data, "pose")
        _require_exact_fields(
            source,
            ("body", "arm", "hand", "hand_side"),
            "pose",
        )
        return cls(
            body=source["body"],
            arm=source["arm"],
            hand=source["hand"],
            hand_side=source["hand_side"],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "body": self.body,
            "arm": self.arm,
            "hand": self.hand,
            "hand_side": self.hand_side,
        }


@dataclass(frozen=True)
class ReplacementTarget:
    body_region: str
    source_jewelry: str
    target_product_count: int

    def __post_init__(self) -> None:
        _require_string(self.body_region, "replacement_target.body_region")
        _require_string(self.source_jewelry, "replacement_target.source_jewelry")
        if isinstance(self.target_product_count, bool) or not isinstance(
            self.target_product_count, int
        ):
            raise ValueError(
                "replacement_target.target_product_count 必须是整数"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ReplacementTarget":
        source = _require_mapping(data, "replacement_target")
        _require_exact_fields(
            source,
            ("body_region", "source_jewelry", "target_product_count"),
            "replacement_target",
        )
        return cls(
            body_region=source["body_region"],
            source_jewelry=source["source_jewelry"],
            target_product_count=source["target_product_count"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_region": self.body_region,
            "source_jewelry": self.source_jewelry,
            "target_product_count": self.target_product_count,
        }


@dataclass(frozen=True)
class ReferenceCompositionSnapshot:
    rank: int
    reference_file: str
    reference_sha256: str
    output_role: OutputRole
    framing: str
    camera_angle: str
    subject_placement: str
    visible_body_regions: tuple[str, ...]
    pose: ReferencePose
    clothing: str
    background: str
    lighting: str
    replacement_target: ReplacementTarget
    other_jewelry_to_remove: tuple[str, ...]
    text_or_ui_risk: TextOrUiRisk
    product_visibility_sufficient: bool
    composition_signature: str

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise ValueError("rank 必须是整数")
        if self.rank < 1:
            raise ValueError("rank 必须大于等于 1")
        for field_name in (
            "reference_file",
            "reference_sha256",
            "framing",
            "camera_angle",
            "subject_placement",
            "clothing",
            "background",
            "lighting",
            "composition_signature",
        ):
            _require_string(getattr(self, field_name), field_name)
        try:
            role = OutputRole(self.output_role)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "output_role 必须是 hero、hand_worn 或 lifestyle"
            ) from exc
        object.__setattr__(self, "output_role", role)
        if not isinstance(self.pose, ReferencePose):
            raise ValueError("pose 必须是 ReferencePose")
        if not isinstance(self.replacement_target, ReplacementTarget):
            raise ValueError("replacement_target 必须是 ReplacementTarget")
        object.__setattr__(
            self,
            "visible_body_regions",
            _string_tuple(self.visible_body_regions, "visible_body_regions"),
        )
        object.__setattr__(
            self,
            "other_jewelry_to_remove",
            _string_tuple(
                self.other_jewelry_to_remove,
                "other_jewelry_to_remove",
            ),
        )
        if self.text_or_ui_risk not in _TEXT_OR_UI_RISKS:
            raise ValueError(
                "text_or_ui_risk 必须是 none、small_removable 或 blocking"
            )
        if not isinstance(self.product_visibility_sufficient, bool):
            raise ValueError("product_visibility_sufficient 必须是布尔值")

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any] | None,
    ) -> "ReferenceCompositionSnapshot":
        source = _require_mapping(data, "参考构图快照")
        fields = (
            "rank",
            "reference_file",
            "reference_sha256",
            "output_role",
            "framing",
            "camera_angle",
            "subject_placement",
            "visible_body_regions",
            "pose",
            "clothing",
            "background",
            "lighting",
            "replacement_target",
            "other_jewelry_to_remove",
            "text_or_ui_risk",
            "product_visibility_sufficient",
            "composition_signature",
        )
        _require_exact_fields(source, fields, "参考构图快照")
        return cls(
            rank=source["rank"],
            reference_file=source["reference_file"],
            reference_sha256=source["reference_sha256"],
            output_role=source["output_role"],
            framing=source["framing"],
            camera_angle=source["camera_angle"],
            subject_placement=source["subject_placement"],
            visible_body_regions=source["visible_body_regions"],
            pose=ReferencePose.from_dict(source["pose"]),
            clothing=source["clothing"],
            background=source["background"],
            lighting=source["lighting"],
            replacement_target=ReplacementTarget.from_dict(
                source["replacement_target"]
            ),
            other_jewelry_to_remove=source["other_jewelry_to_remove"],
            text_or_ui_risk=source["text_or_ui_risk"],
            product_visibility_sufficient=source[
                "product_visibility_sufficient"
            ],
            composition_signature=source["composition_signature"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "reference_file": self.reference_file,
            "reference_sha256": self.reference_sha256,
            "output_role": self.output_role.value,
            "framing": self.framing,
            "camera_angle": self.camera_angle,
            "subject_placement": self.subject_placement,
            "visible_body_regions": list(self.visible_body_regions),
            "pose": self.pose.to_dict(),
            "clothing": self.clothing,
            "background": self.background,
            "lighting": self.lighting,
            "replacement_target": self.replacement_target.to_dict(),
            "other_jewelry_to_remove": list(self.other_jewelry_to_remove),
            "text_or_ui_risk": self.text_or_ui_risk,
            "product_visibility_sufficient": (
                self.product_visibility_sufficient
            ),
            "composition_signature": self.composition_signature,
        }


def build_candidate_snapshot(
    product: ProductAnalysis,
    reference: ScoredReference,
    output_role: OutputRole | str,
) -> ReferenceCompositionSnapshot:
    if not isinstance(product, ProductAnalysis):
        raise ValueError("product 必须是 ProductAnalysis")
    if not isinstance(reference, ScoredReference):
        raise ValueError("reference 必须是 ScoredReference")
    role = require_scene_replacement_role(
        output_role,
        stage="参考构图快照候选",
    )
    row = reference.row
    reference_path = Path(row.absolute_path)
    if not reference_path.is_file():
        _prepare_review_error("reference_file", "参考图真实文件不存在")

    framing = _required_review_value(row.framing, "framing")
    visible_body_regions = _split_review_values(
        row.visible_body_regions,
        "visible_body_regions",
    )
    pose_keywords = _required_review_value(row.pose_keywords, "pose_keywords")
    hand_side = _required_review_value(row.hand_side, "hand_side")
    hand_orientation = _required_review_value(
        row.hand_orientation,
        "hand_orientation",
    )
    collar_type = _required_review_value(row.collar_type, "clothing")
    clothing_occlusion = _required_review_value(
        row.clothing_occlusion_risk,
        "clothing_occlusion_risk",
    )
    scene_keywords = _required_review_value(row.scene_keywords, "background")
    style_category = _required_review_value(row.style_category, "lighting")
    if not row.notes.strip():
        _prepare_review_error(
            "text_or_ui_risk",
            "无法从 notes 确认文字或 UI 风险",
        )
    notes = row.notes.strip()
    source_jewelry = _required_review_value(
        row.existing_jewelry,
        "existing_jewelry",
    )
    product_visibility_sufficient = _parse_product_visibility(
        row.product_visibility
    )
    text_or_ui_risk = _parse_text_or_ui_risk(notes)
    unique_selector = _unique_target_selector(source_jewelry)
    if not _has_confirmed_unique_target(source_jewelry):
        _prepare_review_error(
            "replacement_target.body_region",
            "多件同类首饰缺少内外、上下或次序选择器，无法确认唯一目标",
        )
    body_region = _replacement_body_region(
        hand_side,
        visible_body_regions,
        unique_selector,
    )
    body_pose = _extract_review_segment(
        pose_keywords,
        ("身体", "躯干", "上半身", "全身", "半身", "未入镜"),
        "pose.body",
    )
    arm_pose = _extract_review_segment(
        pose_keywords,
        ("手臂", "前臂", "臂", "胳膊"),
        "pose.arm",
    )
    camera_angle = _extract_review_segment(
        notes,
        ("视角", "镜头", "俯拍", "仰拍", "正面", "侧面"),
        "camera_angle",
    )
    subject_placement = _extract_review_segment(
        notes,
        ("主体", "位于画面", "居中", "中上部", "中下部", "左侧", "右侧"),
        "subject_placement",
    )

    pose = ReferencePose(
        body=body_pose,
        arm=arm_pose,
        hand=hand_orientation,
        hand_side=hand_side,
    )
    target = ReplacementTarget(
        body_region=body_region,
        source_jewelry=source_jewelry,
        target_product_count=1,
    )
    clothing = _join_review_values(collar_type, clothing_occlusion)
    background = _join_review_values(scene_keywords, notes)
    lighting = _join_review_values(style_category, notes)
    signature = _composition_signature(
        output_role=role,
        framing=framing,
        pose=pose,
        background=background,
        lighting=lighting,
        replacement_target=target,
    )

    return ReferenceCompositionSnapshot(
        rank=reference.rank,
        reference_file=row.file_name,
        reference_sha256=_file_sha256(reference_path),
        output_role=role,
        framing=framing,
        camera_angle=camera_angle,
        subject_placement=subject_placement,
        visible_body_regions=visible_body_regions,
        pose=pose,
        clothing=clothing,
        background=background,
        lighting=lighting,
        replacement_target=target,
        other_jewelry_to_remove=reference.ignored_reference_jewelry,
        text_or_ui_risk=text_or_ui_risk,
        product_visibility_sufficient=product_visibility_sufficient,
        composition_signature=signature,
    )


def load_reference_composition_snapshot(
    path: str | Path,
) -> ReferenceCompositionSnapshot:
    snapshot_path = Path(path)
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"无法读取参考构图快照：{snapshot_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"参考构图快照不是有效 JSON：{snapshot_path}") from exc
    return ReferenceCompositionSnapshot.from_dict(data)


def validate_snapshot_binding(
    snapshot: ReferenceCompositionSnapshot,
    *,
    reference_file: str | Path,
    output_role: OutputRole | str,
    expected_rank: int,
) -> None:
    if not isinstance(snapshot, ReferenceCompositionSnapshot):
        raise ValueError("snapshot 必须是 ReferenceCompositionSnapshot")
    role = require_scene_replacement_role(
        output_role,
        stage="参考构图快照绑定",
    )
    if snapshot.output_role is not role:
        _binding_error(
            "output_role",
            f"快照角色 {snapshot.output_role.value} 与运行角色 {role.value} 不一致",
        )
    if isinstance(expected_rank, bool) or not isinstance(expected_rank, int):
        raise ValueError("expected_rank 必须是整数")
    if snapshot.rank != expected_rank:
        _binding_error(
            "rank",
            f"快照值 {snapshot.rank} 与预期值 {expected_rank} 不一致",
        )

    reference_path = Path(reference_file)
    if not reference_path.is_file():
        _binding_error("reference_file", "参考图真实文件不存在")
    if (
        Path(snapshot.reference_file).name != snapshot.reference_file
        or snapshot.reference_file != reference_path.name
    ):
        _binding_error(
            "reference_file",
            "快照文件名与实际参考图文件名不一致",
        )
    actual_sha256 = _file_sha256(reference_path)
    if snapshot.reference_sha256 != actual_sha256:
        _binding_error(
            "reference_sha256",
            "参考图 SHA-256 与快照不一致",
        )

    for field_name in (
        "framing",
        "camera_angle",
        "subject_placement",
        "clothing",
        "background",
        "lighting",
    ):
        if not getattr(snapshot, field_name).strip():
            _binding_error(field_name, "不能为空")
    if not snapshot.visible_body_regions or any(
        not item.strip() for item in snapshot.visible_body_regions
    ):
        _binding_error("visible_body_regions", "身体区域不能为空")
    for field_name in ("body", "arm", "hand", "hand_side"):
        if not getattr(snapshot.pose, field_name).strip():
            _binding_error(f"pose.{field_name}", "不能为空")

    target = snapshot.replacement_target
    if not target.body_region.strip():
        _binding_error("replacement_target.body_region", "替换部位不能为空")
    if not target.source_jewelry.strip():
        _binding_error("replacement_target.source_jewelry", "原首饰不能为空")
    if target.target_product_count != 1:
        _binding_error(
            "replacement_target.target_product_count",
            "必须是单件目标，值只能为 1",
        )
    if not _has_confirmed_unique_target(
        target.source_jewelry,
        target.body_region,
    ):
        _binding_error(
            "replacement_target.body_region",
            "多件同类首饰必须提供唯一目标描述",
        )
    if not snapshot.product_visibility_sufficient:
        _binding_error(
            "product_visibility_sufficient",
            "产品预计展示面积不足",
        )
    if snapshot.text_or_ui_risk == "blocking":
        _binding_error(
            "text_or_ui_risk",
            "参考图存在阻断性的文字或 UI",
        )
    if not snapshot.composition_signature.strip():
        _binding_error("composition_signature", "不能为空")

    expected_signature = _composition_signature(
        output_role=snapshot.output_role,
        framing=snapshot.framing,
        pose=snapshot.pose,
        background=snapshot.background,
        lighting=snapshot.lighting,
        replacement_target=snapshot.replacement_target,
    )
    if snapshot.composition_signature != expected_signature:
        _binding_error("composition_signature", "与快照构图字段不一致")


def reference_composition_sha256(
    snapshot: ReferenceCompositionSnapshot,
) -> str:
    if not isinstance(snapshot, ReferenceCompositionSnapshot):
        raise ValueError("snapshot 必须是 ReferenceCompositionSnapshot")
    payload = json.dumps(
        snapshot.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def classify_reference_run(paths: RunPaths) -> ReferenceRunState:
    if not isinstance(paths, RunPaths):
        raise ValueError("paths 必须是 RunPaths")
    generation_dirs = _generation_directories(paths)
    root_has_modern_marker = _root_has_modern_marker(paths)
    generation_has_modern_marker = any(
        _generation_has_modern_marker(directory)
        for directory in generation_dirs
    )
    if root_has_modern_marker or generation_has_modern_marker:
        snapshot = _load_complete_modern_root(paths)
        if snapshot is None:
            return "damaged"
        if any(
            not _is_complete_modern_generation(directory, paths, snapshot)
            for directory in generation_dirs
        ):
            return "damaged"
        return "modern_snapshot"
    if not generation_dirs or not _is_complete_legacy_root(paths):
        return "damaged"
    if any(not _is_complete_legacy_generation(directory) for directory in generation_dirs):
        return "damaged"
    return "legacy_read_only"


def require_modern_reference_run(
    paths: RunPaths,
) -> ReferenceCompositionSnapshot:
    state = classify_reference_run(paths)
    if state == "legacy_read_only":
        raise ValueError("历史 run 只读，请重新执行 prepare-review")
    if state == "damaged":
        try:
            _load_prepared_artifacts(paths)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"run 产物不完整/损坏，请重新执行 prepare-review；{exc}"
            ) from exc
        raise ValueError("run 产物不完整/损坏，请重新执行 prepare-review")
    try:
        return load_reference_composition_snapshot(
            paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(
            "run 产物不完整/损坏，请重新执行 prepare-review"
        ) from exc


def require_reference_review_ready(paths: RunPaths) -> None:
    """在任何 Review 写入前确认 run 为现代可写态。"""
    state = classify_reference_run(paths)
    if state == "modern_snapshot":
        return
    if state == "legacy_read_only":
        raise ValueError("历史 run 只读，请重新执行 prepare-review")
    candidates_path = paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    confirmed_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    if candidates_path.is_file() and not confirmed_path.exists() and not _generation_directories(paths):
        try:
            prepared = _load_prepare_review_root(paths)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if "composition_signature" in str(exc):
                raise ValueError(
                    "候选参考构图快照不可直接编辑；"
                    "请修订语义源并重新执行 prepare-review"
                ) from exc
            raise ValueError(
                f"run 产物不完整/损坏，请重新执行 prepare-review；{exc}"
            ) from exc
        if prepared is not None:
            return
    raise ValueError("run 产物不完整/损坏，请重新执行 prepare-review")


def _generation_directories(paths: RunPaths) -> list[Path]:
    if not paths.generation_dir.is_dir():
        return []
    return sorted(
        path
        for path in paths.generation_dir.iterdir()
        if path.is_dir()
    )


def _root_has_modern_marker(paths: RunPaths) -> bool:
    if (
        paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    ).exists() or (
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    ).exists():
        return True
    decision_path = paths.review_dir / "review_decision.json"
    if not decision_path.is_file():
        return False
    try:
        decision = _read_json_artifact(decision_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(decision, Mapping) and "reference_snapshot_sha256" in decision


def _generation_has_modern_marker(directory: Path) -> bool:
    try:
        names = {path.name for path in directory.iterdir() if path.is_file()}
    except OSError:
        return True
    return bool(names.intersection(_MODERN_GENERATION_MARKERS)) or any(
        name.startswith(("scene-reference.", "product-reference."))
        for name in names
    )


def _load_prepare_review_root(
    paths: RunPaths,
) -> tuple[ProductAnalysis, list[ReferenceCompositionSnapshot]] | None:
    """读取尚未固化人工决定的现代 prepare-review 根产物。"""
    if _generation_directories(paths):
        return None
    confirmed_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    if confirmed_path.exists():
        return None
    decision_path = paths.review_dir / "review_decision.json"
    if decision_path.is_file():
        decision_data = _read_json_artifact(decision_path)
        decision = ReviewDecision.from_dict(decision_data)
        if (
            decision.action in {
                "generate_rank_1",
                "generate_selected",
                "generate_multiple",
            }
            or decision.reference_snapshot_sha256 is not None
        ):
            return None
    analysis, candidates = _load_prepared_artifacts(paths)
    return analysis, candidates


def _load_prepared_artifacts(
    paths: RunPaths,
) -> tuple[ProductAnalysis, list[ReferenceCompositionSnapshot]]:
    product_path = paths.input_dir / "product-on-hand.jpg"
    analysis_path = paths.analysis_dir / "product_analysis.json"
    constraints_path = paths.analysis_dir / "product_fidelity_constraints.json"
    candidates_path = paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    selected_path = paths.analysis_dir / "selected_references.json"
    role_path = paths.analysis_dir / "output_role.json"
    required = (
        product_path,
        analysis_path,
        constraints_path,
        candidates_path,
        selected_path,
        role_path,
    )
    missing = [path.relative_to(paths.root).as_posix() for path in required if not path.is_file()]
    if missing:
        raise ValueError("prepare-review 根产物缺少：" + "、".join(missing))

    analysis_data = _read_json_artifact(analysis_path)
    analysis = ProductAnalysis.from_dict(analysis_data)
    validate_analysis_ready_for_reference_selection(analysis)
    constraints_data = _read_json_artifact(constraints_path)
    constraints = ProductFidelityConstraints.from_dict(constraints_data)
    validate_product_fidelity_constraints(analysis, constraints)

    role_data = _read_json_artifact(role_path)
    if not isinstance(role_data, Mapping) or set(role_data) != {"output_role"}:
        raise ValueError("analysis/output_role.json 必须只包含 output_role")
    role = require_scene_replacement_role(
        normalize_output_role(role_data.get("output_role")),
        stage="prepare-review run",
    )

    candidate_data = _read_json_artifact(candidates_path)
    if not isinstance(candidate_data, list) or not candidate_data:
        raise ValueError("候选参考构图快照必须是非空列表")
    candidates = [
        ReferenceCompositionSnapshot.from_dict(item)
        for item in candidate_data
    ]
    ranks = [item.rank for item in candidates]
    if len(ranks) != len(set(ranks)):
        raise ValueError("候选参考构图快照 rank 不得重复")
    if any(item.output_role is not role for item in candidates):
        raise ValueError("候选参考构图快照 output_role 角色与当前 run 不一致")
    _validate_selected_candidate_closure(paths, candidates, role)
    return analysis, candidates


def _validate_selected_candidate_closure(
    paths: RunPaths,
    candidates: Sequence[ReferenceCompositionSnapshot],
    role: OutputRole,
) -> None:
    selected_path = paths.analysis_dir / "selected_references.json"
    selected_data = _read_json_artifact(selected_path)
    if not isinstance(selected_data, list) or not selected_data:
        raise ValueError("analysis/selected_references.json 必须是非空列表")
    candidates_by_rank = {item.rank: item for item in candidates}
    selected_ranks: set[int] = set()
    review_root = paths.review_dir.resolve()
    for index, selected in enumerate(selected_data, start=1):
        if not isinstance(selected, Mapping):
            raise ValueError(f"selected_references[{index}] 必须是 JSON 对象")
        rank = selected.get("rank")
        if type(rank) is not int or not 1 <= rank <= 3 or rank in selected_ranks:
            raise ValueError(f"selected_references[{index}].rank 无效或重复")
        selected_ranks.add(rank)
        if type(selected.get("score")) is not int:
            raise ValueError(f"selected_references[{index}].score 必须是整数")
        metadata = selected.get("metadata")
        if not isinstance(metadata, Mapping):
            raise ValueError(f"selected rank {rank} 的 metadata 必须是 JSON 对象")
        review_path = _resolve_recorded_path(
            selected.get("selected_reference"),
            paths,
            selected_path.parent,
        )
        source_value = (
            metadata.get("source_reference")
            or metadata.get("source_absolute_path")
            or metadata.get("absolute_path")
        )
        source_path = _resolve_recorded_path(source_value, paths, selected_path.parent)
        try:
            review_path.relative_to(review_root)
        except ValueError as exc:
            raise ValueError(f"selected rank {rank} 的 review 副本必须位于当前 run") from exc
        if not review_path.is_file() or not source_path.is_file():
            raise ValueError(f"selected rank {rank} 的参考图源图或 review 副本不存在")
        source_digest = _file_sha256(source_path)
        review_digest = _file_sha256(review_path)
        for field_name, expected in (
            ("source_sha256", source_digest),
            ("review_sha256", review_digest),
        ):
            top_value = selected.get(field_name, metadata.get(field_name))
            metadata_value = metadata.get(field_name)
            if (
                not _is_sha256(top_value)
                or top_value != metadata_value
                or top_value != expected
            ):
                raise ValueError(f"selected rank {rank} 的参考图 {field_name} 绑定无效")
        if source_digest != review_digest:
            raise ValueError(f"selected rank {rank} 的源图与 review 副本不一致")
        snapshot = candidates_by_rank.get(rank)
        if snapshot is None:
            raise ValueError(f"selected rank {rank} 缺少候选参考构图快照")
        validate_snapshot_binding(
            snapshot,
            reference_file=source_path,
            output_role=role,
            expected_rank=rank,
        )
    if selected_ranks != set(candidates_by_rank):
        raise ValueError("候选参考构图快照 rank 集合必须与 selected 完全一致")


def _resolve_recorded_path(
    value: Any,
    paths: RunPaths,
    base_dir: Path,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("产物路径必须是非空字符串")
    recorded = Path(value.strip())
    if recorded.is_absolute():
        return recorded.resolve()
    run_relative = (paths.root / recorded).resolve()
    if run_relative.is_file():
        return run_relative
    return (base_dir / recorded).resolve()


def _load_complete_modern_root(
    paths: RunPaths,
) -> ReferenceCompositionSnapshot | None:
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    decision_path = paths.review_dir / "review_decision.json"
    if not snapshot_path.is_file() or not decision_path.is_file():
        return None
    try:
        analysis, candidates = _load_prepared_artifacts(paths)
        snapshot = load_reference_composition_snapshot(snapshot_path)
        decision_data = _read_json_artifact(decision_path)
        decision = ReviewDecision.from_dict(
            decision_data,
            require_reference_snapshot_sha256=True,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not _is_sha256(snapshot.reference_sha256):
        return None
    if any(not _is_sha256(item.reference_sha256) for item in candidates):
        return None
    if sum(item == snapshot for item in candidates) != 1:
        return None
    digest = decision.reference_snapshot_sha256
    if digest != reference_composition_sha256(snapshot):
        return None
    if list(decision.selected_ranks) != [snapshot.rank]:
        return None
    if decision.action not in {"generate_rank_1", "generate_selected"}:
        return None
    if decision.output_role is not snapshot.output_role:
        return None
    if decision.fidelity_constraints_path != "analysis/product_fidelity_constraints.json":
        return None
    expected_confirmation = ProductConfirmationSnapshot.from_analysis(analysis)
    requires_confirmation = analysis.confirmed_product_type.value in {
        "necklace",
        "pendant_necklace",
        "ring",
    }
    if requires_confirmation and decision.confirmation_snapshot is None:
        return None
    if (
        decision.confirmation_snapshot is not None
        and decision.confirmation_snapshot != expected_confirmation
    ):
        return None
    return snapshot


def _is_complete_modern_generation(
    directory: Path,
    paths: RunPaths,
    snapshot: ReferenceCompositionSnapshot,
) -> bool:
    if any(directory.glob("hand-reference.*")):
        return False
    manifest_path = directory / "input-manifest.json"
    try:
        manifest = _read_json_artifact(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "schema_version",
        "output_role",
        "reference_snapshot",
        "product_analysis",
        "fidelity_constraints",
        "inputs",
    }:
        return False
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        return False
    if manifest.get("output_role") != snapshot.output_role.value:
        return False
    fixed_sources = {
        "reference_snapshot": (
            "reference-composition-snapshot.json",
            paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
        ),
        "product_analysis": (
            "product-analysis.json",
            paths.analysis_dir / "product_analysis.json",
        ),
        "fidelity_constraints": (
            "product-fidelity-constraints.json",
            paths.analysis_dir / "product_fidelity_constraints.json",
        ),
    }
    for key, (copied_name, source_path) in fixed_sources.items():
        if not _valid_manifest_file(
            directory,
            manifest.get(key),
            copied_name=copied_name,
            source_path=source_path,
        ):
            return False
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != 2:
        return False
    expected_inputs = (
        (
            1,
            "scene_reference",
            "scene-reference.",
            _selected_review_path(paths, snapshot.rank),
            snapshot.reference_sha256,
        ),
        (
            2,
            "product_identity",
            "product-reference.",
            paths.input_dir / "product-on-hand.jpg",
            None,
        ),
    )
    for item, (order, role, prefix, expected_source, expected_digest) in zip(
        inputs,
        expected_inputs,
    ):
        if not _valid_manifest_input(
            directory,
            item,
            order,
            role,
            prefix,
            expected_source,
            expected_digest,
        ):
            return False
    for name in ("model.txt", "prompt.txt", "reference-rank.txt", "submit.json"):
        if not (directory / name).is_file():
            return False
    try:
        rank = int((directory / "reference-rank.txt").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    return rank == snapshot.rank


def _valid_manifest_file(
    directory: Path,
    value: Any,
    *,
    copied_name: str,
    source_path: Path,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"copied_file", "sha256"}:
        return False
    if value.get("copied_file") != copied_name or not _is_sha256(value.get("sha256")):
        return False
    copied_path = directory / copied_name
    if not copied_path.is_file() or not source_path.is_file():
        return False
    digest = value["sha256"]
    return _file_sha256(copied_path) == digest == _file_sha256(source_path)


def _valid_manifest_input(
    directory: Path,
    value: Any,
    order: int,
    role: str,
    prefix: str,
    expected_source: Path | None,
    expected_digest: str | None,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "order",
        "role",
        "source_path",
        "copied_file",
        "sha256",
    }:
        return False
    copied_name = value.get("copied_file")
    source_value = value.get("source_path")
    digest = value.get("sha256")
    if (
        type(value.get("order")) is not int
        or value.get("order") != order
        or value.get("role") != role
        or not isinstance(copied_name, str)
        or Path(copied_name).name != copied_name
        or not copied_name.startswith(prefix)
        or not isinstance(source_value, str)
        or not source_value.strip()
        or not _is_sha256(digest)
    ):
        return False
    copied_path = directory / copied_name
    source_path = Path(source_value)
    if (
        expected_source is None
        or not copied_path.is_file()
        or not source_path.is_file()
        or not expected_source.is_file()
    ):
        return False
    try:
        if source_path.resolve() != expected_source.resolve():
            return False
    except OSError:
        return False
    if expected_digest is not None and digest != expected_digest:
        return False
    return _file_sha256(copied_path) == digest == _file_sha256(source_path)


def _selected_review_path(paths: RunPaths, rank: int) -> Path | None:
    selected_path = paths.analysis_dir / "selected_references.json"
    try:
        selected = _read_json_artifact(selected_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(selected, list):
        return None
    matches = [
        item
        for item in selected
        if isinstance(item, Mapping)
        and type(item.get("rank")) is int
        and item.get("rank") == rank
    ]
    if len(matches) != 1:
        return None
    value = matches[0].get("selected_reference")
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)


def _is_complete_legacy_root(paths: RunPaths) -> bool:
    required = (
        paths.input_dir / "product-on-hand.jpg",
        paths.analysis_dir / "product_analysis.json",
        paths.analysis_dir / "selected_references.json",
        paths.review_dir / "review_decision.json",
    )
    if not all(path.is_file() for path in required):
        return False
    try:
        analysis_data = _read_json_artifact(required[1])
        selected = _read_json_artifact(required[2])
        decision_data = _read_json_artifact(required[3])
        analysis = ProductAnalysis.from_dict(analysis_data)
        validate_analysis_ready_for_reference_selection(analysis)
        selected_ranks = _validate_legacy_selected(paths, selected)
        decision_ranks = _validate_legacy_decision(decision_data, analysis)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return set(decision_ranks).issubset(selected_ranks)


def _validate_legacy_decision(data: Any, analysis: ProductAnalysis) -> list[int]:
    if not isinstance(data, Mapping) or "reference_snapshot_sha256" in data:
        raise ValueError("历史 ReviewDecision 必须是无快照摘要的 JSON 对象")
    action = data.get("action")
    if action not in {"generate_rank_1", "generate_selected", "generate_multiple"}:
        raise ValueError("历史 ReviewDecision action 无效")
    ranks = data.get("selected_ranks")
    if action == "generate_rank_1" and ranks in (None, []):
        ranks = [1]
    if (
        not isinstance(ranks, list)
        or not ranks
        or any(type(rank) is not int or not 1 <= rank <= 3 for rank in ranks)
        or len(ranks) != len(set(ranks))
    ):
        raise ValueError("历史 ReviewDecision selected_ranks 无效")
    if action == "generate_rank_1" and ranks != [1]:
        raise ValueError("generate_rank_1 只能选择 rank 1")
    if action == "generate_selected" and len(ranks) != 1:
        raise ValueError("generate_selected 必须只选择一个 rank")
    if action == "generate_multiple" and len(ranks) < 2:
        raise ValueError("generate_multiple 至少选择两个 rank")
    if analysis.classification_source != "legacy_inferred":
        decision = ReviewDecision.from_dict(data)
        expected = ProductConfirmationSnapshot.from_analysis(analysis)
        requires_confirmation = analysis.confirmed_product_type.value in {
            "necklace",
            "pendant_necklace",
            "ring",
        }
        if requires_confirmation and decision.confirmation_snapshot is None:
            raise ValueError("现代分析的历史决策缺少产品确认快照")
        if (
            decision.confirmation_snapshot is not None
            and decision.confirmation_snapshot != expected
        ):
            raise ValueError("现代分析的历史决策确认快照与 analysis 不一致")
    return list(ranks)


def _validate_legacy_selected(paths: RunPaths, data: Any) -> set[int]:
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("历史 selected_references 必须包含 Top 3")
    ranks: set[int] = set()
    selected_path = paths.analysis_dir / "selected_references.json"
    for index, item in enumerate(data, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"selected_references[{index}] 必须是 JSON 对象")
        rank = item.get("rank")
        if type(rank) is not int or not 1 <= rank <= 3 or rank in ranks:
            raise ValueError(f"selected_references[{index}].rank 无效或重复")
        if type(item.get("score")) is not int:
            raise ValueError(f"selected_references[{index}].score 必须是整数")
        ranks.add(rank)
        review_path = _resolve_recorded_path(
            item.get("selected_reference"),
            paths,
            selected_path.parent,
        )
        if not review_path.is_file():
            raise ValueError(f"selected rank {rank} 的参考图不存在")
        metadata = item.get("metadata")
        metadata_integrity_fields = (
            isinstance(metadata, Mapping)
            and any(
                field_name in metadata
                for field_name in ("source_sha256", "review_sha256")
            )
        )
        has_integrity_fields = metadata_integrity_fields or any(
            field_name in item for field_name in ("source_sha256", "review_sha256")
        )
        if not has_integrity_fields:
            continue
        if not isinstance(metadata, Mapping):
            raise ValueError(f"selected rank {rank} 完整性字段不完整")
        source_path = _resolve_recorded_path(
            metadata.get("source_reference"),
            paths,
            selected_path.parent,
        )
        if not source_path.is_file():
            raise ValueError(f"selected rank {rank} 的源参考图不存在")
        source_digest = _file_sha256(source_path)
        review_digest = _file_sha256(review_path)
        if source_digest != review_digest:
            raise ValueError(f"selected rank {rank} 的源图与审核图不一致")
        for field_name, expected in (
            ("source_sha256", source_digest),
            ("review_sha256", review_digest),
        ):
            if (
                item.get(field_name) != expected
                or metadata.get(field_name) != expected
            ):
                raise ValueError(f"selected rank {rank} 的 {field_name} 绑定无效")
    if ranks != {1, 2, 3}:
        raise ValueError("历史 selected_references 必须包含 rank 1、2、3")
    return ranks


def _is_complete_legacy_generation(directory: Path) -> bool:
    try:
        names = {path.name for path in directory.iterdir() if path.is_file()}
    except OSError:
        return False
    if not _LEGACY_GENERATION_FILES.issubset(names):
        return False
    hand_references = [
        name for name in names if name.startswith("hand-reference.")
    ]
    if len(hand_references) != 1 or _generation_has_modern_marker(directory):
        return False
    try:
        model = (directory / "model.txt").read_text(encoding="utf-8").strip()
        (directory / "prompt.txt").read_text(encoding="utf-8")
        _read_json_artifact(directory / "submit.json")
        result = _read_json_artifact(directory / "result.json")
        qc = _read_json_artifact(directory / "qc.json")
        expected_must_keep = _legacy_expected_must_keep(directory)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False
    if model not in {"gpt_image_2", "nano_banana_v2"}:
        return False
    if (
        not isinstance(result, Mapping)
        or not isinstance(result.get("data"), Mapping)
        or result["data"].get("status") != "completed"
    ):
        return False
    return _is_valid_legacy_qc(qc, expected_must_keep)


def _is_valid_legacy_qc(
    data: Any,
    expected_must_keep: list[tuple[str, str]] | None = None,
) -> bool:
    if not isinstance(data, Mapping):
        return False
    status = data.get("status")
    passed = data.get("passed")
    failed = data.get("failed")
    notes = data.get("notes")
    if not isinstance(status, str) or status not in {"pass", "rerun", "reject"}:
        return False
    if not _is_non_empty_string_list(passed):
        return False
    if not _is_non_empty_string_list(failed):
        return False
    if not isinstance(notes, str):
        return False
    if not passed and not failed:
        return False

    critical_failures = data.get("critical_failures", None)
    if "critical_failures" in data:
        if not _is_non_empty_string_list(critical_failures) or not critical_failures:
            return False
        normalized_critical = [item.strip() for item in critical_failures]
        if len(set(normalized_critical)) != len(normalized_critical):
            return False
        if any(
            item not in _LEGACY_ALLOWED_CRITICAL_FAILURES
            for item in normalized_critical
        ):
            return False
    else:
        normalized_critical = []

    combined = " ".join(
        [item.strip() for item in passed + failed] + [notes]
    )
    has_person_check = _contains_any(combined, _LEGACY_SOURCE_PERSON_TERMS)
    if not has_person_check and not all(
        _contains_any(combined, terms)
        for terms in (
            _LEGACY_SOURCE_WRIST_TERMS,
            _LEGACY_SOURCE_ARM_TERMS,
            _LEGACY_SOURCE_SKIN_TERMS,
        )
    ):
        return False
    if _contains_any(combined, _LEGACY_NEGATED_CHECK_TERMS):
        return False

    if status == "pass" and (
        failed
        or normalized_critical
        or not _contains_any(combined, _LEGACY_PASS_CHECK_TERMS)
    ):
        return False
    if status != "reject" and (
        any(
            item in _LEGACY_REJECT_CRITICAL_FAILURES
            for item in normalized_critical
        )
        or _contains_any(" ".join(failed), _LEGACY_REJECT_FAILURE_TERMS)
    ):
        return False
    return _is_valid_legacy_fidelity_checks(
        data,
        status,
        expected_must_keep,
    )


def _legacy_expected_must_keep(
    generation_directory: Path,
) -> list[tuple[str, str]] | None:
    constraints_path = (
        generation_directory.parent.parent
        / "analysis"
        / "product_fidelity_constraints.json"
    )
    if not constraints_path.is_file():
        return None
    constraints = _read_json_artifact(constraints_path)
    if not isinstance(constraints, Mapping):
        raise ValueError("产品保真约束必须是 JSON 对象")
    must_keep = constraints.get("must_keep")
    if not isinstance(must_keep, list):
        raise ValueError("产品保真约束 must_keep 必须是列表")
    expected: list[tuple[str, str]] = []
    for item in must_keep:
        if not isinstance(item, Mapping):
            raise ValueError("must_keep 项必须是 JSON 对象")
        name = item.get("name")
        question = item.get("qc_question")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("must_keep.name 必须是非空字符串")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("must_keep.qc_question 必须是非空字符串")
        expected.append((name.strip(), question.strip()))
    if len(set(expected)) != len(expected):
        raise ValueError("must_keep 的 name/qc_question 组合必须唯一")
    return expected


def _is_valid_legacy_fidelity_checks(
    data: Mapping[str, Any],
    status: str,
    expected_must_keep: list[tuple[str, str]] | None,
) -> bool:
    if "fidelity_checks" not in data:
        return not expected_must_keep
    checks = data.get("fidelity_checks")
    if not isinstance(checks, list):
        return False
    valid_checks: list[Mapping[str, Any]] = []
    for check in checks:
        if not isinstance(check, Mapping):
            return False
        for field_name in ("name", "question", "result", "notes"):
            value = check.get(field_name)
            if not isinstance(value, str):
                return False
            if field_name != "notes" and not value.strip():
                return False
        result = check.get("result")
        if result not in {"pass", "rerun", "fail"}:
            return False
        if status == "pass" and result != "pass":
            return False
        valid_checks.append(check)
    if expected_must_keep is None:
        return True

    actual_pairs = [
        (check["name"].strip(), check["question"].strip())
        for check in valid_checks
    ]
    if len(set(actual_pairs)) != len(actual_pairs):
        return False
    if len(actual_pairs) != len(expected_must_keep):
        return False
    actual_names = Counter(name for name, _question in actual_pairs)
    expected_names = Counter(name for name, _question in expected_must_keep)
    if actual_names != expected_names:
        return False
    actual_questions = Counter(question for _name, question in actual_pairs)
    expected_questions = Counter(
        question for _name, question in expected_must_keep
    )
    if actual_questions != expected_questions:
        return False
    return set(actual_pairs) == set(expected_must_keep)


def _is_non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _read_json_artifact(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _require_mapping(
    data: Mapping[str, Any] | None,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return data


def _require_fields(
    source: Mapping[str, Any],
    fields: Sequence[str],
    label: str,
) -> None:
    missing = [field_name for field_name in fields if field_name not in source]
    if missing:
        raise ValueError(f"{label} 缺少字段：{'、'.join(missing)}")


def _require_exact_fields(
    source: Mapping[str, Any],
    fields: Sequence[str],
    label: str,
) -> None:
    _require_fields(source, fields, label)
    expected = set(fields)
    unknown = [str(field_name) for field_name in source if field_name not in expected]
    if unknown:
        raise ValueError(f"{label} 包含未知字段：{'、'.join(unknown)}")


def _require_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是字符串")


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} 必须是字符串列表")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field_name} 只能包含非空字符串")
    return tuple(value)


def _required_review_value(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _prepare_review_error(field_name, "同步字段为空或无法确认")
    return value.strip()


def _split_review_values(value: str, field_name: str) -> tuple[str, ...]:
    text = _required_review_value(value, field_name)
    items = tuple(
        item.strip()
        for item in re.split(r"[、,，;；|/]+", text)
        if item.strip()
    )
    if not items:
        _prepare_review_error(field_name, "无法形成可确认的身体区域")
    return items


def _join_review_values(*values: str) -> str:
    return "；".join(value.strip() for value in values if value.strip())


def _extract_review_segment(
    value: str,
    markers: Sequence[str],
    field_name: str,
) -> str:
    segments = (
        segment.strip()
        for segment in re.split(r"[，,;；。]+", value)
        if segment.strip()
    )
    for segment in segments:
        if any(marker in segment for marker in markers):
            return segment
    _prepare_review_error(field_name, "同步描述中没有可确认的信息")


def _parse_product_visibility(value: str) -> bool:
    text = _required_review_value(value, "product_visibility")
    if any(
        marker in text
        for marker in (
            "不足",
            "过小",
            "太小",
            "低",
            "不可见",
            "不完整",
            "不够",
            "不清晰",
        )
    ) or re.search(
        r"(?:不|未|无|欠|难以).{0,2}(?:大|高|清晰|完整|充分|充足|足够)",
        text,
    ):
        return False
    if any(
        marker in text
        for marker in ("充足", "足够", "充分", "高", "完整", "清晰", "大")
    ):
        return True
    _prepare_review_error(
        "product_visibility",
        "无法确认产品预计展示面积是否充足",
    )


def _parse_text_or_ui_risk(notes: str) -> TextOrUiRisk:
    text = notes.lower()
    safe_markers = (
        "无文字或平台界面",
        "无文字和平台界面",
        "无文字或平台 ui",
        "无文字和平台 ui",
        "无文字",
        "没有文字",
        "无ui",
        "无 ui",
        "无界面",
        "无平台界面",
        "none",
    )
    risk_text = text
    safe_found = False
    for marker in safe_markers:
        if marker in risk_text:
            safe_found = True
            risk_text = risk_text.replace(marker, "")
    small_found = any(
        marker in risk_text
        for marker in (
            "小面积文字",
            "少量文字",
            "可移除文字",
            "可移除界面",
            "small_removable",
        )
    )
    blocking_found = any(
        marker in risk_text
        for marker in (
            "大面积文字",
            "状态栏",
            "平台 ui",
            "平台ui",
            "平台界面",
            "blocking",
        )
    )
    if safe_found and (small_found or blocking_found):
        _prepare_review_error(
            "text_or_ui_risk",
            "文字或 UI 风险描述互相冲突",
        )
    if blocking_found:
        return "blocking"
    if small_found:
        return "small_removable"
    if safe_found:
        return "none"
    _prepare_review_error(
        "text_or_ui_risk",
        "无法从 notes 确认文字或 UI 风险",
    )


def _replacement_body_region(
    hand_side: str,
    visible_body_regions: Sequence[str],
    unique_selector: str | None,
) -> str:
    parts = [hand_side, *visible_body_regions]
    if unique_selector is not None:
        parts.append(unique_selector)
    return _join_review_values(*parts)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _composition_signature(
    *,
    output_role: OutputRole,
    framing: str,
    pose: ReferencePose,
    background: str,
    lighting: str,
    replacement_target: ReplacementTarget,
) -> str:
    data = {
        "output_role": output_role.value,
        "framing": framing,
        "pose": pose.to_dict(),
        "background": background,
        "lighting": lighting,
        "replacement_target": replacement_target.to_dict(),
    }
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _describes_multiple_same_jewelry(text: str) -> bool:
    if re.search(
        r"(?:多\s*(?:件|条|枚|层|个|只|组)|双(?:层|条|枚|件|只)?|叠戴)",
        text,
    ):
        return True
    count_pattern = re.compile(
        r"(?P<number>\d+|[一二两三四五六七八九十百]+)\s*"
        r"(?P<unit>件|条|枚|层|个|只|组)"
    )
    for match in count_pattern.finditer(text):
        if re.search(r"第\s*$", text[: match.start()]):
            continue
        number = match.group("number")
        if number.isdigit() and int(number) < 2:
            continue
        if number == "一":
            continue
        return True
    return False


def _has_confirmed_unique_target(
    source_jewelry: str,
    body_region: str | None = None,
) -> bool:
    if not _describes_multiple_same_jewelry(source_jewelry):
        return True
    selector = _unique_target_selector(source_jewelry)
    if selector is None:
        return False
    return body_region is None or selector in body_region


def _unique_target_selector(text: str) -> str | None:
    selector_patterns = (
        r"第\s*(?:[1-9]\d*|[一二两三四五六七八九十百]+)\s*"
        r"(?:条|件|枚|层|个|只)",
        r"(?:内侧|外侧|内圈|外圈|上方|下方|最上|最下|"
        r"靠近?(?:手掌|手臂|前臂)|远离(?:手掌|手臂|前臂))"
        r"(?:的)?(?:那(?:条|件|枚|个|只)|一(?:条|件|枚|个|只)|"
        r"手链|手串|项链|戒指)",
        r"(?:拇指|食指|中指|无名指|小指)(?:上?的?)?戒指",
    )
    for pattern in selector_patterns:
        match = re.search(pattern, text)
        if match is not None:
            return match.group(0)
    return None


def _prepare_review_error(field_name: str, detail: str) -> None:
    raise ValueError(
        f"无法构建参考构图快照：{field_name} {detail}；"
        "请补全同步字段并重新运行 prepare-review"
    )


def _binding_error(field_name: str, detail: str) -> None:
    raise ValueError(
        f"参考构图快照绑定失败：{field_name} {detail}；"
        "请重新运行 prepare-review"
    )


__all__ = [
    "REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME",
    "REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME",
    "ReferenceCompositionSnapshot",
    "ReferencePose",
    "ReferenceRunState",
    "ReplacementTarget",
    "build_candidate_snapshot",
    "classify_reference_run",
    "load_reference_composition_snapshot",
    "reference_composition_sha256",
    "require_modern_reference_run",
    "validate_snapshot_binding",
]
