from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from jewelry_on_hand.models import ProductAnalysis, ScoredReference
from jewelry_on_hand.output_roles import OutputRole, require_scene_replacement_role


REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME = (
    "reference_composition_snapshots.json"
)
REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME = "reference_composition_snapshot.json"

TextOrUiRisk = Literal["none", "small_removable", "blocking"]
_TEXT_OR_UI_RISKS = frozenset({"none", "small_removable", "blocking"})


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
        _require_fields(source, ("body", "arm", "hand", "hand_side"), "pose")
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
        _require_fields(
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
        _require_fields(source, fields, "参考构图快照")
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
    body_region = _replacement_body_region(product, hand_side)
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
    if _describes_multiple_same_jewelry(target.source_jewelry) and not (
        _has_unique_target_description(target.body_region)
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


def _require_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是字符串")


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} 必须是字符串列表")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} 只能包含字符串")
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
        for marker in ("不足", "过小", "太小", "低", "不可见", "不完整")
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
    if any(
        marker in text
        for marker in (
            "无文字",
            "没有文字",
            "无ui",
            "无 ui",
            "无界面",
            "无平台界面",
            "none",
        )
    ):
        return "none"
    if any(
        marker in text
        for marker in (
            "小面积文字",
            "少量文字",
            "可移除文字",
            "可移除界面",
            "small_removable",
        )
    ):
        return "small_removable"
    if any(
        marker in text
        for marker in (
            "大面积文字",
            "状态栏",
            "平台 ui",
            "平台ui",
            "平台界面",
            "blocking",
        )
    ):
        return "blocking"
    _prepare_review_error(
        "text_or_ui_risk",
        "无法从 notes 确认文字或 UI 风险",
    )


def _replacement_body_region(
    product: ProductAnalysis,
    hand_side: str,
) -> str:
    parts = [hand_side]
    product_hand_side = getattr(product.hand_side, "value", product.hand_side)
    if product_hand_side and product_hand_side != "unknown":
        parts.append(str(product_hand_side))
    finger_position = getattr(
        product.finger_position,
        "value",
        product.finger_position,
    )
    if finger_position and finger_position != "unknown":
        parts.append(str(finger_position))
    parts.append(_required_review_value(product.wear_position, "wear_position"))
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
    return bool(
        re.search(
            r"(?:多|两|二|双|2|叠戴|双层).{0,4}(?:件|条|枚|层|个|手链|手串|项链|戒指)",
            text,
        )
    )


def _has_unique_target_description(text: str) -> bool:
    return bool(
        re.search(
            r"(?:左|右|内|外|上|下|前|后|近|远|第[一二三四五六七八九\d]+|"
            r"left|right|inner|outer|upper|lower|thumb|index|middle|ring|little)",
            text,
            flags=re.IGNORECASE,
        )
    )


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
    "ReplacementTarget",
    "build_candidate_snapshot",
    "load_reference_composition_snapshot",
    "reference_composition_sha256",
    "validate_snapshot_binding",
]
