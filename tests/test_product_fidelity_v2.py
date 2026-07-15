from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace

import pytest

import jewelry_on_hand.product_analysis as product_analysis_module
from jewelry_on_hand.models import (
    MustKeepConstraint,
    PendantSemantics,
    ProductAnalysis,
    ProductFidelityConstraints,
)
from jewelry_on_hand.product_analysis import product_analysis_to_dict
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    product_analysis_sha256,
    validate_product_fidelity_constraints,
)


PENDANT_TERMS = ("吊坠", "主吊坠", "链坠", "流苏", "坠子")
CONSTRAINT_SEMANTIC_FIELD_PATHS = (
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
SEMANTIC_FIELD_PATHS = (
    *CONSTRAINT_SEMANTIC_FIELD_PATHS,
    "pendant_semantics.position",
    "pendant_semantics.orientation",
    "pendant_semantics.connection",
)
PRESENT_PENDANT_CONFLICT_PHRASES = (
    "无吊坠",
    "未见吊坠",
    "吊坠不存在",
    "吊坠缺失",
    "必须新增第二颗吊坠",
    "要求生成第二颗吊坠",
)


def _absent_semantics() -> PendantSemantics:
    return PendantSemantics(
        presence="absent",
        count=0,
        layer=None,
        creation_policy="forbid",
    )


def _present_semantics(layer: int = 2) -> PendantSemantics:
    position = "第二层中央" if layer == 2 else f"第 {layer} 层中央"
    connection = "吊环连接第二层链条" if layer == 2 else f"吊环连接第 {layer} 层链条"
    return PendantSemantics(
        presence="present",
        count=1,
        layer=layer,
        creation_policy="forbid",
        position=position,
        orientation="正面向前",
        connection=connection,
    )


def _necklace_analysis(
    *,
    pendant: bool = False,
    layer_count: int = 2,
    pendant_count: int | None = None,
    visible_appearance: str | None = None,
) -> ProductAnalysis:
    product_type = "pendant_necklace" if pendant else "necklace"
    return ProductAnalysis.from_dict(
        {
            "product_type": product_type,
            "wear_position": "颈部",
            "visible_appearance": visible_appearance
            or (
                "双层细链，第二层中央有水滴形吊坠"
                if pendant
                else "同一条连续海蓝宝微珠长链绕颈形成上下双圈"
            ),
            "color_family": ["海蓝"],
            "style_mood": "清透",
            "composition": "真人佩戴正面构图",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "detected_product_type": product_type,
            "confirmed_product_type": product_type,
            "classification_confidence": "high",
            "classification_evidence": ["肉眼可见结构"],
            "classification_source": "manual_override",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "layer_count": layer_count,
            "length_category": "long",
            "chain_or_strand_type": "连续微珠链",
            "has_pendant": pendant,
            "pendant_count": (
                1 if pendant else 0
            )
            if pendant_count is None
            else pendant_count,
            "pendant_layer": 2 if pendant else None,
            "pendant_position": "第二层中央" if pendant else None,
            "pendant_orientation": "正面向前" if pendant else None,
            "connection_structure": "吊环连接第二层链条" if pendant else None,
            "symmetry": "沿身体中线对称",
            "is_independent_multi_item": False,
        }
    )


def _bracelet_analysis(*, with_keyword: bool = True) -> ProductAnalysis:
    return ProductAnalysis.from_dict(
        {
            "product_type": "bracelet",
            "detected_product_type": "bracelet",
            "confirmed_product_type": "bracelet",
            "classification_confidence": "high",
            "classification_evidence": ["手腕处可见闭合珠串"],
            "classification_source": "manual_override",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "wear_position": "手腕",
            "visible_appearance": (
                "圆珠手链主珠右侧有一颗透明随形"
                if with_keyword
                else "连续圆珠手链"
            ),
            "color_family": ["海蓝", "透明"],
            "style_mood": "清透",
            "composition": "真人手腕近景",
            "product_dimensions": {"bead_diameter_mm": 8.0},
            "needs_full_front_display": True,
            "special_requirements": ["保持可见珠序"],
            "layer_count": 1,
            "has_pendant": False,
            "pendant_count": 0,
            "pendant_layer": None,
            "is_independent_multi_item": False,
        }
    )


def _ring_analysis() -> ProductAnalysis:
    return ProductAnalysis.from_dict(
        {
            "product_type": "ring",
            "detected_product_type": "ring",
            "confirmed_product_type": "ring",
            "classification_confidence": "high",
            "classification_evidence": ["左手无名指根部可见单枚戒指"],
            "classification_source": "manual_override",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "wear_position": "左手无名指根部",
            "visible_appearance": "单枚银色开口戒指，椭圆戒面中央有透明主石",
            "color_family": ["银色", "透明"],
            "style_mood": "克制",
            "composition": "真人手部近景",
            "product_dimensions": {"width_mm": 9.0},
            "needs_full_front_display": True,
            "special_requirements": ["保持开口端点方向"],
            "layer_count": 1,
            "has_pendant": False,
            "pendant_count": 0,
            "pendant_layer": None,
            "occluded_parts": ["戒圈背面"],
            "uncertain_details": ["镶嵌背面结构"],
            "is_independent_multi_item": False,
            "ring_count": 1,
            "hand_side": "left",
            "finger_position": "ring",
            "ring_wear_style": "finger_base",
        }
    )


def _analysis_for_category(product_type: str) -> ProductAnalysis:
    if product_type == "bracelet":
        return _bracelet_analysis()
    if product_type == "necklace":
        return _necklace_analysis()
    if product_type == "pendant_necklace":
        return _necklace_analysis(pendant=True)
    if product_type == "ring":
        return _ring_analysis()
    raise AssertionError(f"未覆盖测试品类：{product_type}")


def _tampered_copy(
    constraints: ProductFidelityConstraints,
    field_name: str,
    value: object,
) -> ProductFidelityConstraints:
    copied = replace(constraints, source=dict(constraints.source))
    object.__setattr__(copied, field_name, value)
    return copied


def _tampered_pendant_constraints(
    product: ProductAnalysis,
    field_name: str,
    value: object,
) -> ProductFidelityConstraints:
    constraints = build_product_fidelity_constraints(product)
    assert constraints.pendant_semantics is not None
    semantics = replace(constraints.pendant_semantics)
    object.__setattr__(semantics, field_name, value)
    return _tampered_copy(constraints, "pendant_semantics", semantics)


def _safe_item() -> MustKeepConstraint:
    return MustKeepConstraint(
        name="微珠链整体结构",
        source_text="同一条连续微珠链绕颈形成上下双圈",
        normalized_keyword="微珠链",
        location="颈前可见区域",
        visual_shape="连续细密圆珠链",
        relationship="同一条长链形成上下两圈",
        forbid=("改成两件独立首饰",),
        qc_question="同一条连续微珠链是否仍形成上下双圈",
    )


def _inject_semantic_text(
    constraints: ProductFidelityConstraints, field_path: str, text: str
) -> ProductFidelityConstraints:
    if field_path == "detected_keywords[0]":
        return replace(constraints, detected_keywords=(text,))
    if field_path == "must_not_change[0]":
        return replace(constraints, must_not_change=(text,))
    item = _safe_item()
    field_name = field_path.removeprefix("must_keep[0].")
    if field_name == "forbid[0]":
        item = replace(item, forbid=(text,))
    else:
        item = replace(item, **{field_name: text})
    return replace(
        constraints,
        must_keep=(item,),
        review_status="pending",
        needs_user_review=True,
        detail_crop_recommended=True,
    )


def _inject_present_semantic_text(
    constraints: ProductFidelityConstraints, field_path: str, text: str
) -> ProductFidelityConstraints:
    if field_path.startswith("pendant_semantics."):
        assert constraints.pendant_semantics is not None
        field_name = field_path.removeprefix("pendant_semantics.")
        semantics = replace(
            constraints.pendant_semantics,
            **{field_name: text},
        )
        return replace(constraints, pendant_semantics=semantics)
    if field_path == "detected_keywords[0]":
        return replace(constraints, detected_keywords=(text,))
    if field_path == "must_not_change[0]":
        if text != "禁止新增第二颗吊坠":
            return replace(constraints, must_not_change=(text,))
        return replace(
            constraints,
            must_not_change=(*constraints.must_not_change, text),
        )
    item = constraints.must_keep[0]
    field_name = field_path.removeprefix("must_keep[0].")
    if field_name == "forbid[0]":
        item = replace(item, forbid=(text, *item.forbid[1:]))
    else:
        item = replace(item, **{field_name: text})
    return replace(constraints, must_keep=(item, *constraints.must_keep[1:]))


def _constraints_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": 1,
        "source": {
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
            "product_analysis_sha256": "a" * 64,
        },
        "detected_keywords": [],
        "must_keep": [],
        "must_not_change": ["保持整体可见结构"],
        "needs_user_review": False,
        "detail_crop_recommended": False,
        "review_status": "not_applicable",
    }
    data.update(overrides)
    if data["schema_version"] == 2:
        semantics = data.get("pendant_semantics")
        product_type = (
            "pendant_necklace"
            if isinstance(semantics, dict) and semantics.get("presence") == "present"
            else "necklace"
        )
        data["source"] = {
            **data["source"],  # type: ignore[arg-type]
            "product_type": product_type,
        }
    return data


def _direct_constraints(**overrides: object) -> ProductFidelityConstraints:
    return ProductFidelityConstraints(**_constraints_data(**overrides))  # type: ignore[arg-type]


def test_v1_constraints_round_trip_does_not_add_pendant_semantics() -> None:
    payload = _constraints_data()
    constraints = ProductFidelityConstraints.from_dict(payload)

    assert constraints.pendant_semantics is None
    assert constraints.to_dict() == payload


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "presence": "absent",
                "count": 0,
                "layer": None,
                "position": None,
                "orientation": None,
                "connection": None,
                "creation_policy": "forbid",
            },
            _absent_semantics(),
        ),
        (
            {
                "presence": "present",
                "count": 1,
                "layer": 2,
                "position": "第二层中央",
                "orientation": "正面向前",
                "connection": "吊环连接第二层链条",
                "creation_policy": "forbid",
            },
            _present_semantics(),
        ),
    ],
)
def test_v2_constraints_round_trip_structured_pendant_semantics(
    payload: dict[str, object], expected: PendantSemantics
) -> None:
    raw = _constraints_data(schema_version=2, pendant_semantics=payload)
    raw["source"] = {
        **raw["source"],  # type: ignore[arg-type]
        "product_type": (
            "pendant_necklace" if expected.presence == "present" else "necklace"
        ),
    }
    constraints = ProductFidelityConstraints.from_dict(raw)

    assert constraints.pendant_semantics == expected
    assert constraints.to_dict() == raw


def test_pendant_semantics_from_dict_rejects_absent_v2_without_layer_key() -> None:
    with pytest.raises(ValueError, match="pendant_semantics.layer.*必填"):
        PendantSemantics.from_dict(
            {
                "presence": "absent",
                "count": 0,
                "creation_policy": "forbid",
            }
        )


def test_v2_constraints_from_dict_rejects_absent_semantics_without_layer_key() -> None:
    with pytest.raises(ValueError, match="pendant_semantics.layer.*必填"):
        ProductFidelityConstraints.from_dict(
            _constraints_data(
                schema_version=2,
                pendant_semantics={
                    "presence": "absent",
                    "count": 0,
                    "creation_policy": "forbid",
                },
            )
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("count", "1"),
        ("count", 1.0),
        ("layer", "2"),
        ("layer", 2.0),
        ("layer", ""),
    ],
    ids=["count-字符串", "count-浮点数", "layer-字符串", "layer-浮点数", "layer-空字符串"],
)
def test_pendant_semantics_from_dict_rejects_non_json_integer_types(
    field_name: str, invalid_value: object
) -> None:
    payload: dict[str, object] = {
        "presence": "present",
        "count": 1,
        "layer": 2,
        "creation_policy": "forbid",
    }
    if field_name == "layer" and invalid_value == "":
        payload.update(presence="absent", count=0, layer=None)
    payload[field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        PendantSemantics.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("count", "1"),
        ("count", 1.0),
        ("layer", "2"),
        ("layer", 2.0),
        ("layer", ""),
    ],
    ids=["count-字符串", "count-浮点数", "layer-字符串", "layer-浮点数", "layer-空字符串"],
)
def test_v2_constraints_from_dict_rejects_non_json_integer_semantics(
    field_name: str, invalid_value: object
) -> None:
    semantics: dict[str, object] = {
        "presence": "present",
        "count": 1,
        "layer": 2,
        "creation_policy": "forbid",
    }
    if field_name == "layer" and invalid_value == "":
        semantics.update(presence="absent", count=0, layer=None)
    semantics[field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        ProductFidelityConstraints.from_dict(
            _constraints_data(schema_version=2, pendant_semantics=semantics)
        )


@pytest.mark.parametrize("schema_version", [0, 3, True, "2"])
def test_constraints_reject_unsupported_schema_versions(
    schema_version: object,
) -> None:
    with pytest.raises(ValueError, match="schema_version"):
        ProductFidelityConstraints.from_dict(
            _constraints_data(schema_version=schema_version)
        )


def test_v2_constraints_require_pendant_semantics_object() -> None:
    with pytest.raises(ValueError, match="v2.*pendant_semantics 必填"):
        ProductFidelityConstraints.from_dict(_constraints_data(schema_version=2))


def test_v1_constraints_reject_non_null_pendant_semantics() -> None:
    with pytest.raises(ValueError, match="v1.*pendant_semantics"):
        ProductFidelityConstraints.from_dict(
            _constraints_data(
                pendant_semantics={
                    "presence": "absent",
                    "count": 0,
                    "layer": None,
                    "creation_policy": "forbid",
                }
            )
        )


@pytest.mark.parametrize(
    "schema_version",
    [1.0, 2.0, True, []],
    ids=["浮点数-v1", "浮点数-v2", "布尔值", "不可哈希列表"],
)
def test_direct_constraints_reject_non_integer_schema_versions(
    schema_version: object,
) -> None:
    with pytest.raises(ValueError, match="schema_version.*1 或 2"):
        _direct_constraints(schema_version=schema_version)


def test_direct_v1_constraints_reject_non_null_pendant_semantics() -> None:
    with pytest.raises(ValueError, match="v1.*pendant_semantics"):
        _direct_constraints(pendant_semantics=_absent_semantics())


def test_direct_v2_constraints_require_pendant_semantics() -> None:
    with pytest.raises(ValueError, match="v2.*pendant_semantics 必填"):
        _direct_constraints(schema_version=2)


def test_direct_v2_constraints_convert_raw_pendant_semantics_mapping() -> None:
    constraints = _direct_constraints(
        schema_version=2,
        pendant_semantics={
            "presence": "present",
            "count": 1,
            "layer": 3,
            "position": "第 3 层中央",
            "orientation": "正面向前",
            "connection": "吊环连接第 3 层链条",
            "creation_policy": "forbid",
        },
    )

    assert constraints.pendant_semantics == _present_semantics(3)


@pytest.mark.parametrize("layer", [True, 1.0, 4])
def test_direct_pendant_semantics_reject_invalid_layer(layer: object) -> None:
    with pytest.raises(ValueError, match="layer"):
        PendantSemantics(
            presence="present",
            count=1,
            layer=layer,  # type: ignore[arg-type]
            creation_policy="forbid",
            position="中央",
            orientation="正面向前",
            connection="吊环连接链条",
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "presence": "unknown",
                "count": 0,
                "layer": None,
                "creation_policy": "forbid",
            },
            "presence",
        ),
        (
            {
                "presence": "absent",
                "count": True,
                "layer": None,
                "creation_policy": "forbid",
            },
            "count",
        ),
        (
            {
                "presence": "absent",
                "count": 0.0,
                "layer": None,
                "creation_policy": "forbid",
            },
            "count",
        ),
        (
            {
                "presence": "absent",
                "count": 1,
                "layer": None,
                "creation_policy": "forbid",
            },
            "absent",
        ),
        (
            {
                "presence": "present",
                "count": 0,
                "layer": 1,
                "creation_policy": "forbid",
            },
            "present",
        ),
        (
            {
                "presence": "present",
                "count": 1,
                "layer": None,
                "creation_policy": "forbid",
            },
            "layer",
        ),
        (
            {
                "presence": "present",
                "count": 1,
                "layer": 4,
                "creation_policy": "forbid",
            },
            "layer",
        ),
        (
            {
                "presence": "absent",
                "count": 0,
                "layer": None,
                "creation_policy": "allow",
            },
            "creation_policy",
        ),
    ],
)
def test_pendant_semantics_reject_invalid_combinations(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProductFidelityConstraints.from_dict(
            _constraints_data(schema_version=2, pendant_semantics=payload)
        )


def test_plain_necklace_builder_emits_v2_absent_contract() -> None:
    constraints = build_product_fidelity_constraints(_necklace_analysis())

    assert constraints.schema_version == 2
    assert constraints.pendant_semantics == _absent_semantics()


def test_plain_necklace_builder_sanitizes_non_pendant_rule_text() -> None:
    product = _necklace_analysis(
        visible_appearance="双圈微珠链中央有一个活动跑环，没有任何垂饰"
    )
    constraints = build_product_fidelity_constraints(product)
    semantic_text = json.dumps(constraints.to_dict(), ensure_ascii=False)

    assert "跑环" in semantic_text
    assert all(term not in semantic_text for term in PENDANT_TERMS)


def test_pendant_necklace_builder_emits_v2_present_contract_and_traceable_item() -> None:
    constraints = build_product_fidelity_constraints(_necklace_analysis(pendant=True))

    assert constraints.schema_version == 2
    assert constraints.pendant_semantics == _present_semantics()
    pendant_items = [
        item for item in constraints.must_keep if item.normalized_keyword == "吊坠"
    ]
    assert len(pendant_items) == 1
    assert "第 2 层" in pendant_items[0].relationship


def test_pendant_necklace_v2_rejects_multiple_pendants_in_first_phase() -> None:
    with pytest.raises(ValueError, match="第一阶段.*1 颗主吊坠"):
        build_product_fidelity_constraints(
            _necklace_analysis(pendant=True, pendant_count=2)
        )


def test_v2_validator_rejects_multiple_pendants_when_builder_is_bypassed() -> None:
    legal_product = _necklace_analysis(pendant=True)
    multiple_pendant_product = _necklace_analysis(pendant=True, pendant_count=2)
    legal_constraints = build_product_fidelity_constraints(legal_product)
    rebound_constraints = replace(
        legal_constraints,
        source={
            **legal_constraints.source,
            "product_analysis_sha256": product_analysis_sha256(
                multiple_pendant_product
            ),
        },
    )

    with pytest.raises(
        ValueError,
        match="analysis=.*count=2.*canonical=.*count.*1.*prepare-review",
    ):
        validate_product_fidelity_constraints(
            multiple_pendant_product,
            rebound_constraints,
        )


@pytest.mark.parametrize("term", PENDANT_TERMS)
@pytest.mark.parametrize("field_path", CONSTRAINT_SEMANTIC_FIELD_PATHS)
def test_absent_v2_rejects_pendant_term_in_every_free_text_field(
    term: str, field_path: str
) -> None:
    product = _necklace_analysis()
    constraints = _inject_semantic_text(
        build_product_fidelity_constraints(product), field_path, f"禁止新增{term}"
    )

    with pytest.raises(ValueError, match=re.escape(field_path)):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize(
    "semantics",
    [
        _present_semantics(1),
        _present_semantics(2),
    ],
)
def test_plain_necklace_rejects_present_contract(
    semantics: PendantSemantics,
) -> None:
    product = _necklace_analysis()
    constraints = build_product_fidelity_constraints(product)
    object.__setattr__(constraints, "pendant_semantics", semantics)
    with pytest.raises(
        ValueError,
        match="analysis=.*necklace.*canonical=.*present.*prepare-review",
    ):
        validate_product_fidelity_constraints(product, constraints)


def test_pendant_necklace_rejects_wrong_layer_contract() -> None:
    product = _necklace_analysis(pendant=True)
    constraints = replace(
        build_product_fidelity_constraints(product),
        pendant_semantics=_present_semantics(1),
    )
    with pytest.raises(
        ValueError,
        match="analysis=.*2.*canonical=.*1.*prepare-review",
    ):
        validate_product_fidelity_constraints(product, constraints)


def test_present_v2_requires_traceable_pendant_must_keep() -> None:
    product = _necklace_analysis(pendant=True)
    constraints = replace(build_product_fidelity_constraints(product), must_keep=())
    with pytest.raises(ValueError, match="可追溯.*must_keep"):
        validate_product_fidelity_constraints(product, constraints)


@pytest.mark.parametrize("conflict_phrase", PRESENT_PENDANT_CONFLICT_PHRASES)
@pytest.mark.parametrize("field_path", SEMANTIC_FIELD_PATHS)
def test_present_v2_rejects_structural_conflict_in_every_semantic_field(
    field_path: str, conflict_phrase: str
) -> None:
    product = _necklace_analysis(pendant=True)
    constraints = _inject_present_semantic_text(
        build_product_fidelity_constraints(product), field_path, conflict_phrase
    )

    with pytest.raises(
        ValueError,
        match=re.escape(f"{field_path} 与 present canonical 冲突：{conflict_phrase}"),
    ):
        validate_product_fidelity_constraints(product, constraints)


def test_present_v2_accepts_forbid_second_pendant_protection() -> None:
    product = _necklace_analysis(pendant=True)
    constraints = _inject_present_semantic_text(
        build_product_fidelity_constraints(product),
        "must_not_change[0]",
        "禁止新增第二颗吊坠",
    )

    assert validate_product_fidelity_constraints(product, constraints) is constraints


@pytest.mark.parametrize(
    ("has_pendant", "field_name", "invalid_value"),
    [
        (True, "presence", True),
        (True, "presence", " present "),
        (True, "count", True),
        (True, "count", 1.0),
        (True, "count", 0),
        (True, "layer", True),
        (True, "layer", 2.0),
        (True, "layer", None),
        (True, "creation_policy", True),
        (True, "creation_policy", "allow"),
        (True, "creation_policy", " forbid "),
        (True, "position", 1),
        (True, "position", ""),
        (True, "orientation", False),
        (True, "orientation", "   "),
        (True, "connection", 1.0),
        (True, "connection", "\t"),
        (False, "count", 1),
        (False, "layer", 1),
        (False, "position", "中央"),
        (False, "orientation", "正面向前"),
        (False, "connection", "吊环连接"),
    ],
)
def test_validator_strictly_rejects_tampered_pendant_runtime_fields(
    has_pendant: bool,
    field_name: str,
    invalid_value: object,
) -> None:
    product = _necklace_analysis(pendant=has_pendant)
    constraints = _tampered_pendant_constraints(
        product,
        field_name,
        invalid_value,
    )

    with pytest.raises(ValueError, match=f"pendant_semantics.{field_name}"):
        validate_product_fidelity_constraints(product, constraints)


def test_product_analysis_sha256_uses_canonical_product_analysis_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = _bracelet_analysis()
    canonical = {"规范化字段": ["中文", 1, None, False]}
    monkeypatch.setattr(
        product_analysis_module,
        "product_analysis_to_dict",
        lambda value: canonical if value is product else {},
    )
    expected = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert product_analysis_sha256(product) == expected


def test_product_analysis_sha256_is_stable_for_equivalent_inputs() -> None:
    first = _bracelet_analysis()
    second = ProductAnalysis.from_dict(product_analysis_to_dict(first))

    assert first is not second
    assert product_analysis_sha256(first) == product_analysis_sha256(second)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("visible_appearance", "圆珠手链中央有透明随形"),
        ("style_mood", "明亮通透"),
        ("composition", "真人手腕侧面近景"),
    ],
)
def test_product_analysis_sha256_changes_for_business_field_change(
    field_name: str,
    replacement: object,
) -> None:
    product = _bracelet_analysis()
    changed = replace(product, **{field_name: replacement})

    assert product_analysis_sha256(product) != product_analysis_sha256(changed)


@pytest.mark.parametrize(
    "product_type",
    ["bracelet", "necklace", "pendant_necklace", "ring"],
)
def test_four_category_builders_bind_canonical_source_and_validate(
    product_type: str,
) -> None:
    product = _analysis_for_category(product_type)
    constraints = build_product_fidelity_constraints(product)

    assert constraints.source["product_type"] == product_type
    assert constraints.source["product_analysis_sha256"] == (
        product_analysis_sha256(product)
    )
    assert validate_product_fidelity_constraints(product, constraints) is constraints


def test_builder_preserves_custom_product_analysis_path() -> None:
    product = _bracelet_analysis()
    constraints = build_product_fidelity_constraints(
        product,
        product_analysis="analysis/final_product_analysis.json",
    )

    assert constraints.source["product_analysis"] == (
        "analysis/final_product_analysis.json"
    )
    assert validate_product_fidelity_constraints(product, constraints) is constraints


@pytest.mark.parametrize(
    "source_change",
    [
        {"product_analysis_sha256": None},
        {"product_analysis_sha256": 1},
        {"product_analysis_sha256": 1.0},
        {"product_analysis_sha256": "0" * 64},
        {"product_type": True},
        {"product_type": "ring"},
    ],
)
def test_validator_rejects_missing_tampered_or_wrongly_typed_source(
    source_change: dict[str, object],
) -> None:
    product = _bracelet_analysis()
    constraints = build_product_fidelity_constraints(product)
    source = dict(constraints.source)
    source.update(source_change)
    tampered = _tampered_copy(constraints, "source", source)

    with pytest.raises(ValueError, match="source"):
        validate_product_fidelity_constraints(product, tampered)


def test_validator_rejects_missing_product_analysis_digest_key() -> None:
    product = _bracelet_analysis()
    constraints = build_product_fidelity_constraints(product)
    source = dict(constraints.source)
    source.pop("product_analysis_sha256")
    tampered = _tampered_copy(constraints, "source", source)

    with pytest.raises(ValueError, match="source.product_analysis_sha256"):
        validate_product_fidelity_constraints(product, tampered)


@pytest.mark.parametrize(
    "product_type",
    ["bracelet", "necklace", "pendant_necklace", "ring"],
)
@pytest.mark.parametrize("field_name", ["must_keep", "must_not_change"])
def test_four_category_validator_rejects_canonical_collection_tampering(
    product_type: str,
    field_name: str,
) -> None:
    product = _analysis_for_category(product_type)
    constraints = build_product_fidelity_constraints(product)
    current = getattr(constraints, field_name)
    replacement = current[1:] if current else (_safe_item(),)
    tampered = _tampered_copy(constraints, field_name, replacement)

    with pytest.raises(ValueError, match=field_name):
        validate_product_fidelity_constraints(product, tampered)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("schema_version", True),
        ("must_keep", []),
        ("must_not_change", []),
        ("needs_user_review", 1),
        ("detail_crop_recommended", 0.0),
    ],
)
def test_validator_rejects_canonical_runtime_type_tampering(
    field_name: str,
    invalid_value: object,
) -> None:
    product = _bracelet_analysis()
    constraints = build_product_fidelity_constraints(product)
    tampered = _tampered_copy(constraints, field_name, invalid_value)

    with pytest.raises(ValueError, match=field_name):
        validate_product_fidelity_constraints(product, tampered)


def test_corrected_status_keeps_canonical_validation_strict() -> None:
    product = _bracelet_analysis()
    constraints = replace(
        build_product_fidelity_constraints(product),
        review_status="corrected",
    )

    assert validate_product_fidelity_constraints(product, constraints) is constraints
    tampered = _tampered_copy(constraints, "must_not_change", ("任意文本",))
    with pytest.raises(ValueError, match="must_not_change"):
        validate_product_fidelity_constraints(product, tampered)


def test_not_applicable_status_is_only_valid_for_empty_canonical_review() -> None:
    product = _bracelet_analysis(with_keyword=False)
    constraints = build_product_fidelity_constraints(product)

    assert constraints.review_status == "not_applicable"
    assert validate_product_fidelity_constraints(product, constraints) is constraints

    pending = _tampered_copy(constraints, "review_status", "pending")
    with pytest.raises(ValueError, match="review_status"):
        validate_product_fidelity_constraints(product, pending)


def test_pending_canonical_cannot_be_changed_to_not_applicable() -> None:
    product = _bracelet_analysis()
    constraints = build_product_fidelity_constraints(product)

    assert constraints.review_status == "pending"
    not_applicable = _tampered_copy(
        constraints,
        "review_status",
        "not_applicable",
    )
    with pytest.raises(ValueError, match="review_status"):
        validate_product_fidelity_constraints(product, not_applicable)
