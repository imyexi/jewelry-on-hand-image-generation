from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from jewelry_on_hand.models import (
    MustKeepConstraint,
    PendantSemantics,
    ProductAnalysis,
    ProductFidelityConstraints,
)
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    product_analysis_sha256,
    validate_product_fidelity_constraints,
)
from jewelry_on_hand.qc import build_qc_checklist


PENDANT_TERMS = ("吊坠", "主吊坠", "链坠", "流苏", "坠子")
SEMANTIC_FIELD_PATHS = (
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
PRESENT_PENDANT_CONFLICT_PHRASES = (
    "无吊坠",
    "未见吊坠",
    "吊坠不存在",
    "吊坠缺失",
    "必须新增第二颗吊坠",
    "要求生成第二颗吊坠",
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
    if field_path == "detected_keywords[0]":
        return replace(constraints, detected_keywords=(text,))
    if field_path == "must_not_change[0]":
        return replace(constraints, must_not_change=(text,))
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
                "creation_policy": "forbid",
            },
            PendantSemantics("absent", 0, None, "forbid"),
        ),
        (
            {
                "presence": "present",
                "count": 1,
                "layer": 2,
                "creation_policy": "forbid",
            },
            PendantSemantics("present", 1, 2, "forbid"),
        ),
    ],
)
def test_v2_constraints_round_trip_structured_pendant_semantics(
    payload: dict[str, object], expected: PendantSemantics
) -> None:
    raw = _constraints_data(schema_version=2, pendant_semantics=payload)
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
        _direct_constraints(
            pendant_semantics=PendantSemantics("absent", 0, None, "forbid")
        )


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
            "creation_policy": "forbid",
        },
    )

    assert constraints.pendant_semantics == PendantSemantics(
        "present", 1, 3, "forbid"
    )


@pytest.mark.parametrize("layer", [True, 1.0, 4])
def test_direct_pendant_semantics_reject_invalid_layer(layer: object) -> None:
    with pytest.raises(ValueError, match="layer"):
        PendantSemantics("present", 1, layer, "forbid")  # type: ignore[arg-type]


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
    assert constraints.pendant_semantics == PendantSemantics(
        "absent", 0, None, "forbid"
    )


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
    assert constraints.pendant_semantics == PendantSemantics("present", 1, 2, "forbid")
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
@pytest.mark.parametrize("field_path", SEMANTIC_FIELD_PATHS)
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
        PendantSemantics("present", 1, 1, "forbid"),
        PendantSemantics("present", 1, 2, "forbid"),
    ],
)
def test_plain_necklace_rejects_present_contract(
    semantics: PendantSemantics,
) -> None:
    product = _necklace_analysis()
    constraints = replace(
        build_product_fidelity_constraints(product), pendant_semantics=semantics
    )
    with pytest.raises(
        ValueError,
        match="analysis=.*necklace.*canonical=.*present.*prepare-review",
    ):
        validate_product_fidelity_constraints(product, constraints)


def test_pendant_necklace_rejects_wrong_layer_contract() -> None:
    product = _necklace_analysis(pendant=True)
    constraints = replace(
        build_product_fidelity_constraints(product),
        pendant_semantics=PendantSemantics("present", 1, 1, "forbid"),
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


def test_qc_checklist_uses_absent_v2_contract_for_double_loop_plain_necklace() -> None:
    product = _necklace_analysis(layer_count=2)
    constraints = build_product_fidelity_constraints(product)

    checklist = build_qc_checklist(
        product.normalized_product_type,
        product.display_mode,
        constraints.must_keep,
        product_analysis=product,
        fidelity_constraints=constraints,
    )

    assert "主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠" in checklist
    assert all("第 3 层吊坠" not in question for question in checklist)


def test_qc_checklist_uses_present_v2_count_and_layer() -> None:
    product = _necklace_analysis(pendant=True, layer_count=2)
    constraints = build_product_fidelity_constraints(product)

    checklist = build_qc_checklist(
        product.normalized_product_type,
        product.display_mode,
        constraints.must_keep,
        product_analysis=product,
        fidelity_constraints=constraints,
    )

    assert "现有主吊坠数量是否为 1，且仍位于第 2 层并保持原连接关系" in checklist
