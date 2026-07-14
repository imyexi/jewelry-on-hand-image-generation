from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductDimensions,
    ReferenceRow,
    ScoredReference,
)
from jewelry_on_hand.output_roles import OutputRole
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME,
    ReferenceCompositionSnapshot,
    build_candidate_snapshot,
    load_reference_composition_snapshot,
    reference_composition_sha256,
    validate_snapshot_binding,
)


@pytest.fixture
def 参考图文件(tmp_path: Path) -> Path:
    path = tmp_path / "参考图.jpg"
    path.write_bytes(b"reference-image")
    return path


@pytest.fixture
def 手链产品() -> ProductAnalysis:
    return ProductAnalysis(
        product_type="手链/手串",
        wear_position="手腕",
        visible_appearance="深红色圆珠单圈手链",
        color_family=("深红",),
        style_mood="暗调闪光",
        composition="手腕近景",
        product_dimensions=ProductDimensions(bead_diameter_mm=10),
        needs_full_front_display=True,
        special_requirements=("保留圆珠排列",),
    )


@pytest.fixture
def 已评分参考图(参考图文件: Path) -> ScoredReference:
    row = ReferenceRow(
        index=1,
        file_name=参考图文件.name,
        relative_path=f"参考图/{参考图文件.name}",
        absolute_path=参考图文件,
        width=1200,
        height=1600,
        size_mb=0.5,
        purpose_category="手部佩戴图",
        bracelet_applicability="适用",
        default_strategy="优先使用",
        style_category="左上侧柔光，高对比暗背景",
        scene_keywords="深色布面，室内",
        jewelry_type="手链",
        recommended_usage="手腕近景",
        notes="正面视角；主体位于画面中下部；无文字或平台界面",
        confidence="高",
        file_exists=True,
        applicable_product_types="手链",
        applicable_display_modes="佩戴",
        framing="手部近景",
        visible_body_regions="左手、手腕、前臂",
        product_visibility="展示面积充足",
        hand_visibility="完整可见",
        collar_type="无可见服装",
        clothing_occlusion_risk="无遮挡",
        hair_occlusion_risk="无遮挡",
        pose_keywords="身体未入镜，前臂斜向右上",
        existing_jewelry="左手腕单条手链",
        crop_risk="无裁切",
        hand_side="左手",
        hand_orientation="掌心朝上",
    )
    return ScoredReference(
        row=row,
        score=100,
        rank=1,
        reason=("替换位置清晰",),
        risk=(),
        ignored_reference_jewelry=("右手食指戒指",),
    )


@pytest.fixture
def 有效快照(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> ReferenceCompositionSnapshot:
    return build_candidate_snapshot(
        手链产品,
        已评分参考图,
        OutputRole.HAND_WORN,
    )


@pytest.fixture
def 有效快照数据(有效快照: ReferenceCompositionSnapshot) -> dict[str, object]:
    return 有效快照.to_dict()


def test_参考构图快照可完整往返并绑定真实文件(
    参考图文件: Path,
    已评分参考图: ScoredReference,
    手链产品: ProductAnalysis,
) -> None:
    snapshot = build_candidate_snapshot(
        手链产品,
        已评分参考图,
        OutputRole.HAND_WORN,
    )

    restored = ReferenceCompositionSnapshot.from_dict(snapshot.to_dict())

    assert restored == snapshot
    assert restored.reference_sha256 == hashlib.sha256(
        参考图文件.read_bytes()
    ).hexdigest()
    assert restored.replacement_target.target_product_count == 1
    assert restored.composition_signature
    assert restored.visible_body_regions == ("左手", "手腕", "前臂")
    assert restored.other_jewelry_to_remove == ("右手食指戒指",)
    assert restored.camera_angle == "正面视角"
    assert restored.subject_placement == "主体位于画面中下部"
    assert restored.pose.body == "身体未入镜"
    assert restored.pose.arm == "前臂斜向右上"
    assert restored.pose.hand == "掌心朝上"


def test_参考构图快照及其嵌套对象均不可修改(
    有效快照: ReferenceCompositionSnapshot,
) -> None:
    with pytest.raises(FrozenInstanceError):
        有效快照.framing = "全身"
    with pytest.raises(FrozenInstanceError):
        有效快照.pose.hand = "手背朝上"
    with pytest.raises(FrozenInstanceError):
        有效快照.replacement_target.body_region = "右手腕"


def test_快照文件名常量固定() -> None:
    assert (
        REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
        == "reference_composition_snapshots.json"
    )
    assert (
        REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
        == "reference_composition_snapshot.json"
    )


def test_可从磁盘加载参考构图快照(
    tmp_path: Path,
    有效快照: ReferenceCompositionSnapshot,
) -> None:
    path = tmp_path / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    path.write_text(
        json.dumps(有效快照.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_reference_composition_snapshot(path) == 有效快照


def test_快照摘要使用固定紧凑格式(
    有效快照: ReferenceCompositionSnapshot,
) -> None:
    payload = json.dumps(
        有效快照.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert reference_composition_sha256(有效快照) == hashlib.sha256(
        payload
    ).hexdigest()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"output_role": "hero"}, "hero"),
        ({"reference_sha256": "0" * 64}, "SHA-256"),
        ({"text_or_ui_risk": "blocking"}, "文字或 UI"),
        ({"product_visibility_sufficient": False}, "展示面积不足"),
    ],
    ids=("主图角色", "文件摘要", "文字界面", "展示面积"),
)
def test_绑定校验拒绝不安全或不匹配的快照(
    有效快照数据: dict[str, object],
    参考图文件: Path,
    mutation: dict[str, object],
    message: str,
) -> None:
    data = 有效快照数据 | mutation
    snapshot = ReferenceCompositionSnapshot.from_dict(data)

    with pytest.raises(ValueError, match=message):
        validate_snapshot_binding(
            snapshot,
            reference_file=参考图文件,
            output_role=OutputRole.HAND_WORN,
            expected_rank=1,
        )


def _修改嵌套字段(
    data: dict[str, object],
    field_name: str,
    value: object,
) -> dict[str, object]:
    changed = data.copy()
    nested_name, child_name = field_name.split(".", maxsplit=1)
    nested_source = changed[nested_name]
    assert isinstance(nested_source, dict)
    nested = nested_source.copy()
    nested[child_name] = value
    changed[nested_name] = nested
    return changed


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("framing", "", "framing"),
        ("camera_angle", "  ", "camera_angle"),
        ("subject_placement", "", "subject_placement"),
        ("clothing", "", "clothing"),
        ("background", "", "background"),
        ("lighting", "", "lighting"),
        ("visible_body_regions", [], "身体区域"),
        ("pose.body", "", "pose.body"),
        ("pose.arm", "", "pose.arm"),
        ("pose.hand", "", "pose.hand"),
        ("pose.hand_side", "", "pose.hand_side"),
        ("replacement_target.body_region", "", "替换部位"),
        ("replacement_target.source_jewelry", "", "原首饰"),
        ("replacement_target.target_product_count", 2, "单件目标"),
    ],
    ids=(
        "空景别",
        "空镜头角度",
        "空主体位置",
        "空服装",
        "空背景",
        "空光线",
        "空身体区域",
        "空身体姿势",
        "空手臂姿势",
        "空手部姿势",
        "空左右手",
        "空替换部位",
        "空原首饰",
        "非单件目标",
    ),
)
def test_绑定校验拒绝不完整的构图字段(
    有效快照数据: dict[str, object],
    参考图文件: Path,
    field_name: str,
    value: object,
    message: str,
) -> None:
    if "." in field_name:
        data = _修改嵌套字段(有效快照数据, field_name, value)
    else:
        data = 有效快照数据 | {field_name: value}
    snapshot = ReferenceCompositionSnapshot.from_dict(data)

    with pytest.raises(ValueError, match=message) as caught:
        validate_snapshot_binding(
            snapshot,
            reference_file=参考图文件,
            output_role=OutputRole.HAND_WORN,
            expected_rank=1,
        )

    assert "prepare-review" in str(caught.value)


def test_绑定校验拒绝多件同类首饰却没有唯一目标描述(
    有效快照数据: dict[str, object],
    参考图文件: Path,
) -> None:
    data = _修改嵌套字段(
        有效快照数据,
        "replacement_target.source_jewelry",
        "两条同类手链叠戴",
    )
    data = _修改嵌套字段(
        data,
        "replacement_target.body_region",
        "手腕",
    )
    snapshot = ReferenceCompositionSnapshot.from_dict(data)

    with pytest.raises(ValueError, match="唯一目标"):
        validate_snapshot_binding(
            snapshot,
            reference_file=参考图文件,
            output_role=OutputRole.HAND_WORN,
            expected_rank=1,
        )


@pytest.mark.parametrize(
    ("mutation", "output_role", "expected_rank", "reference_name", "message"),
    [
        ({"output_role": "lifestyle"}, OutputRole.HAND_WORN, 1, None, "角色"),
        ({"rank": 2}, OutputRole.HAND_WORN, 1, None, "rank"),
        ({"reference_file": "别的图片.jpg"}, OutputRole.HAND_WORN, 1, None, "文件名"),
    ],
    ids=("角色不一致", "排序不一致", "文件名不一致"),
)
def test_绑定校验拒绝角色排序或文件名不一致(
    tmp_path: Path,
    有效快照数据: dict[str, object],
    参考图文件: Path,
    mutation: dict[str, object],
    output_role: OutputRole,
    expected_rank: int,
    reference_name: str | None,
    message: str,
) -> None:
    actual_reference = 参考图文件
    if reference_name is not None:
        actual_reference = tmp_path / reference_name
        actual_reference.write_bytes(参考图文件.read_bytes())
    snapshot = ReferenceCompositionSnapshot.from_dict(有效快照数据 | mutation)

    with pytest.raises(ValueError, match=message):
        validate_snapshot_binding(
            snapshot,
            reference_file=actual_reference,
            output_role=output_role,
            expected_rank=expected_rank,
        )


def test_候选草稿拒绝主图角色(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    with pytest.raises(ValueError, match="hero"):
        build_candidate_snapshot(
            手链产品,
            已评分参考图,
            OutputRole.HERO,
        )


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("framing", "framing"),
        ("visible_body_regions", "visible_body_regions"),
        ("pose_keywords", "pose_keywords"),
        ("hand_side", "hand_side"),
        ("hand_orientation", "hand_orientation"),
        ("collar_type", "clothing"),
        ("scene_keywords", "background"),
        ("style_category", "lighting"),
        ("existing_jewelry", "existing_jewelry"),
        ("product_visibility", "product_visibility"),
        ("notes", "文字或 UI"),
    ],
    ids=(
        "缺少景别",
        "缺少身体区域",
        "缺少姿势",
        "缺少左右手",
        "缺少手部朝向",
        "缺少服装",
        "缺少背景",
        "缺少光线",
        "缺少原首饰",
        "缺少展示面积",
        "缺少文字界面判断",
    ),
)
def test_候选草稿拒绝无法确认的同步字段(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
    field_name: str,
    message: str,
) -> None:
    changed_row = replace(已评分参考图.row, **{field_name: ""})
    changed = ScoredReference(
        changed_row,
        已评分参考图.score,
        已评分参考图.rank,
        已评分参考图.reason,
        已评分参考图.risk,
        已评分参考图.ignored_reference_jewelry,
    )

    with pytest.raises(ValueError, match=message) as caught:
        build_candidate_snapshot(
            手链产品,
            changed,
            OutputRole.HAND_WORN,
        )

    assert "prepare-review" in str(caught.value)
