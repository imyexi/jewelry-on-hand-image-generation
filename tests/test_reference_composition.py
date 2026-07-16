from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from jewelry_on_hand import reference_composition as reference_composition_module
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
def 戒指产品() -> ProductAnalysis:
    return ProductAnalysis.from_dict(
        {
            "product_type": "戒指",
            "detected_product_type": "ring",
            "confirmed_product_type": "ring",
            "classification_confidence": "high",
            "classification_evidence": ["肉眼可见单枚戒指"],
            "classification_source": "auto_confirmed",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "wear_position": "左手无名指根部",
            "visible_appearance": "单枚银色开口戒",
            "color_family": ["银色"],
            "style_mood": "暗调闪光",
            "composition": "手部近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "layer_count": 1,
            "has_pendant": False,
            "pendant_count": 0,
            "is_independent_multi_item": False,
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
        }
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


def test_背景与光线只提取备注中的画面片段而排除分类元数据(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    row = replace(
        已评分参考图.row,
        purpose_category="生活场景图",
        style_category="户外自然光",
        scene_keywords=(
            "户外行走，手腕完整露出，细手链，适合戒指构图，"
            "深色沥青路面为背景"
        ),
        notes=(
            "素材编号：RP000081；图片类型：手部佩戴图；"
            "正面视角；主体位于画面左中部；"
            "深色沥青路面为背景；柔和侧光；"
            "包袋有小面积文字，可移除文字"
        ),
    )

    snapshot = build_candidate_snapshot(
        手链产品,
        replace(已评分参考图, row=row),
        OutputRole.LIFESTYLE,
    )

    assert "深色沥青路面为背景" in snapshot.background
    assert "柔和侧光" in snapshot.lighting
    assert "细手链" not in snapshot.background
    assert "戒指" not in snapshot.background
    for metadata in ("素材编号", "图片类型", "适用品类", "小面积文字"):
        assert metadata not in snapshot.background
        assert metadata not in snapshot.lighting


def test_候选快照就绪检查复用构建器并保留结构化排除原因(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    source_row = 已评分参考图.row
    incomplete_row = replace(source_row, collar_type="")

    readiness = reference_composition_module.assess_candidate_snapshot_readiness(
        手链产品,
        incomplete_row,
        OutputRole.HAND_WORN,
    )

    assert readiness.ready is False
    assert readiness.field_name == "clothing"
    assert "同步字段为空" in readiness.reason
    assert incomplete_row.collar_type == ""
    assert source_row.collar_type == "无可见服装"


def test_候选快照就绪检查不吞掉非候选数据错误(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    with pytest.raises(ValueError, match="hero"):
        reference_composition_module.assess_candidate_snapshot_readiness(
            手链产品,
            已评分参考图.row,
            OutputRole.HERO,
        )


def test_候选草稿接受明确否定的文字界面风险(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    row = replace(
        已评分参考图.row,
        notes=(
            "正面视角；主体位于画面中下部；"
            "无大面积文字，不含 blocking 风险；无文字或平台界面"
        ),
    )

    snapshot = build_candidate_snapshot(
        手链产品,
        replace(已评分参考图, row=row),
        OutputRole.HAND_WORN,
    )

    assert snapshot.text_or_ui_risk == "none"


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
        "左手腕",
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
        ({}, OutputRole.HAND_WORN, 1, "同内容但改名.jpg", "文件名"),
        (
            {"reference_file": "子目录/参考图.jpg"},
            OutputRole.HAND_WORN,
            1,
            None,
            "文件名",
        ),
    ],
    ids=(
        "角色不一致",
        "排序不一致",
        "快照文件名不一致",
        "实际文件改名",
        "快照文件名含路径",
    ),
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
    "notes",
    (
        "正面视角；主体位于画面中下部；无文字；存在平台界面",
        "正面视角；主体位于画面中下部；无文字；手机状态栏明显",
    ),
    ids=("平台界面冲突", "状态栏冲突"),
)
def test_候选草稿拒绝文字界面风险冲突(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
    notes: str,
) -> None:
    row = replace(已评分参考图.row, notes=notes)
    reference = replace(已评分参考图, row=row)

    with pytest.raises(ValueError, match="文字或 UI.*prepare-review"):
        build_candidate_snapshot(
            手链产品,
            reference,
            OutputRole.HAND_WORN,
        )


@pytest.mark.parametrize(
    "product_visibility",
    ("展示面积不大", "产品不够清晰"),
    ids=("面积不大", "产品不清晰"),
)
def test_候选草稿将否定展示描述标记为不足(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
    参考图文件: Path,
    product_visibility: str,
) -> None:
    row = replace(
        已评分参考图.row,
        product_visibility=product_visibility,
    )
    reference = replace(已评分参考图, row=row)

    snapshot = build_candidate_snapshot(
        手链产品,
        reference,
        OutputRole.HAND_WORN,
    )

    assert snapshot.product_visibility_sufficient is False
    with pytest.raises(ValueError, match="展示面积不足.*prepare-review"):
        validate_snapshot_binding(
            snapshot,
            reference_file=参考图文件,
            output_role=OutputRole.HAND_WORN,
            expected_rank=1,
        )


def test_候选草稿拒绝无法确定的展示面积描述(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    row = replace(已评分参考图.row, product_visibility="展示面积一般")
    reference = replace(已评分参考图, row=row)

    with pytest.raises(ValueError, match="product_visibility.*prepare-review"):
        build_candidate_snapshot(
            手链产品,
            reference,
            OutputRole.HAND_WORN,
        )


def test_候选草稿拒绝只有手侧定位的多件同类首饰(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
) -> None:
    row = replace(
        已评分参考图.row,
        existing_jewelry="左手腕两条同类手链叠戴",
    )
    reference = replace(已评分参考图, row=row)

    with pytest.raises(ValueError, match="唯一目标.*prepare-review"):
        build_candidate_snapshot(
            手链产品,
            reference,
            OutputRole.HAND_WORN,
        )


def test_绑定校验拒绝用整组裸方位冒充单件选择器(
    有效快照数据: dict[str, object],
    参考图文件: Path,
) -> None:
    data = _修改嵌套字段(
        有效快照数据,
        "replacement_target.source_jewelry",
        "左手腕上方两条同类手链",
    )
    data = _修改嵌套字段(
        data,
        "replacement_target.body_region",
        "左手腕；上方",
    )
    snapshot = ReferenceCompositionSnapshot.from_dict(data)

    with pytest.raises(ValueError, match="唯一目标.*prepare-review"):
        validate_snapshot_binding(
            snapshot,
            reference_file=参考图文件,
            output_role=OutputRole.HAND_WORN,
            expected_rank=1,
        )


@pytest.mark.parametrize(
    "existing_jewelry",
    (
        "左手腕三条同类手链",
        "左手腕3条同类手链",
        "四枚同类戒指",
        "左手腕十一条同类手链",
        "左手腕上方两条同类手链",
    ),
    ids=(
        "三条手链",
        "数字三条手链",
        "四枚戒指",
        "十一条手链",
        "整组上方位置",
    ),
)
def test_候选草稿拒绝未绑定具体单件的多件同类首饰(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
    existing_jewelry: str,
) -> None:
    row = replace(
        已评分参考图.row,
        existing_jewelry=existing_jewelry,
    )
    reference = replace(已评分参考图, row=row)

    with pytest.raises(ValueError, match="唯一目标.*prepare-review"):
        build_candidate_snapshot(
            手链产品,
            reference,
            OutputRole.HAND_WORN,
        )


@pytest.mark.parametrize(
    ("existing_jewelry", "selector"),
    (
        ("左手腕两条同类手链中的第 2 条", "第 2 条"),
        ("左手腕两条同类手链中外侧那条", "外侧那条"),
        ("左手腕第 2 条手链", "第 2 条"),
    ),
    ids=("序号绑定单条", "方位绑定单条", "单独序号不是数量"),
)
def test_候选草稿接受绑定到具体单件的手链选择器(
    手链产品: ProductAnalysis,
    已评分参考图: ScoredReference,
    参考图文件: Path,
    existing_jewelry: str,
    selector: str,
) -> None:
    row = replace(
        已评分参考图.row,
        existing_jewelry=existing_jewelry,
    )
    reference = replace(已评分参考图, row=row)

    snapshot = build_candidate_snapshot(
        手链产品,
        reference,
        OutputRole.HAND_WORN,
    )

    assert selector in snapshot.replacement_target.body_region
    validate_snapshot_binding(
        snapshot,
        reference_file=参考图文件,
        output_role=OutputRole.HAND_WORN,
        expected_rank=1,
    )


def test_候选草稿接受具体手指绑定的单枚戒指选择器(
    戒指产品: ProductAnalysis,
    已评分参考图: ScoredReference,
    参考图文件: Path,
) -> None:
    row = replace(
        已评分参考图.row,
        jewelry_type="戒指",
        existing_jewelry="四枚同类戒指中食指戒指",
        visible_body_regions="左手、手指",
        visible_fingers="食指、中指、无名指、小指",
    )
    reference = replace(已评分参考图, row=row)

    snapshot = build_candidate_snapshot(
        戒指产品,
        reference,
        OutputRole.HAND_WORN,
    )

    assert "食指戒指" in snapshot.replacement_target.body_region
    validate_snapshot_binding(
        snapshot,
        reference_file=参考图文件,
        output_role=OutputRole.HAND_WORN,
        expected_rank=1,
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
