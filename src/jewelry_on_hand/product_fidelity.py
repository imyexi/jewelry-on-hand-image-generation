from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jewelry_on_hand.models import (
    MustKeepConstraint,
    PendantSemantics,
    ProductAnalysis,
    ProductFidelityConstraints,
)
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


CONSTRAINTS_FILE_NAME = "product_fidelity_constraints.json"
CONFIRMED_REVIEW_STATUSES = {"confirmed", "corrected", "not_applicable"}
# 仅供历史 v1 词法兼容逻辑使用；v2 使用完整五词集合。
_V1_PENDANT_CANONICAL_KEYWORDS = frozenset({"吊坠", "主吊坠", "流苏", "链坠"})
_PENDANT_SENSITIVE_TERMS = ("主吊坠", "吊坠", "链坠", "流苏", "坠子")
_PRESENT_PENDANT_CONFLICT_PHRASES = (
    "无吊坠",
    "未见吊坠",
    "吊坠不存在",
    "吊坠缺失",
    "必须新增第二颗吊坠",
    "要求生成第二颗吊坠",
)


@dataclass(frozen=True)
class _KeywordRule:
    normalized: str
    aliases: tuple[str, ...]
    visual_shape: str
    relationship: str
    forbid: tuple[str, ...]
    qc_question: str


KEYWORD_RULES: tuple[_KeywordRule, ...] = (
    _KeywordRule(
        normalized="随形",
        aliases=("随形", "随行"),
        visual_shape="不规则异形或切面结构，非圆珠、非椭圆珠",
        relationship="与相邻珠子或隔件保持输入图中的位置关系",
        forbid=("改成圆珠", "改成椭圆珠", "改成普通隔珠"),
        qc_question="随形结构是否仍是不规则异形或切面结构，而不是圆珠或椭圆珠",
    ),
    _KeywordRule(
        normalized="跑环",
        aliases=("跑环",),
        visual_shape=(
            "由多颗小珠串成的独立闭合小环，保持可见环形轮廓和活动结构；"
            "不是绳结、流苏、单个金属环或主串的一部分"
        ),
        relationship=(
            "保持产品图中的环绕、套接或连接对象，以及与主珠、连接件或相邻结构的关系；"
            "不得并入手串主串或改接到其他对象"
        ),
        forbid=(
            "改成绳结或普通珠结",
            "改成流苏或链坠",
            "改成单个金属环、金属片或连接扣",
            "改成普通圆珠",
            "并入手串主串",
            "改变环绕、套接或连接对象",
        ),
        qc_question=(
            "跑环是否仍由多颗小珠形成独立闭合小环，保持原来的环绕、套接或连接对象，"
            "且没有变成珠结、流苏、金属单环、链坠、普通圆珠或主串的一部分"
        ),
    ),
    _KeywordRule(
        normalized="双尖",
        aliases=("双尖",),
        visual_shape="两端尖锥或双尖柱状结构",
        relationship="保持输入图中的朝向和相邻连接关系",
        forbid=("磨成圆珠", "改成桶珠"),
        qc_question="双尖结构的两端尖形轮廓和方向是否保留",
    ),
    _KeywordRule(
        normalized="回纹",
        aliases=("回纹",),
        visual_shape="表面回纹雕刻或连续纹路",
        relationship="保持在原有珠体或配件表面",
        forbid=("改成光面珠", "抹平纹样"),
        qc_question="回纹纹样和凹凸感是否保留",
    ),
    _KeywordRule(
        normalized="貔貅",
        aliases=("貔貅",),
        visual_shape="动物造型立体配件",
        relationship="保持头部、身体和朝向与输入图一致",
        forbid=("改成普通圆珠", "改成抽象金属件"),
        qc_question="貔貅的动物造型、方向和立体感是否保留",
    ),
    _KeywordRule(
        normalized="桶珠",
        aliases=("桶珠",),
        visual_shape="圆柱或桶形珠，能看到侧面、端面或长度比例",
        relationship="保持在输入图中的相邻珠序位置",
        forbid=("改成圆珠",),
        qc_question="桶珠的圆柱轮廓和长度比例是否保留",
    ),
    _KeywordRule(
        normalized="雕刻",
        aliases=("雕刻", "雕花"),
        visual_shape="表面立体纹样、浅浮雕或镂刻层次",
        relationship="保持在原有珠体或配件表面",
        forbid=("磨平成光面", "删除纹样"),
        qc_question="雕刻或雕花纹样是否保留，而不是变成光面",
    ),
    _KeywordRule(
        normalized="吊坠",
        aliases=("吊坠", "流苏", "链坠"),
        visual_shape="垂坠结构及连接点",
        relationship="保持垂坠方向、连接点和长度关系",
        forbid=("删除垂坠", "并入手串", "变成第二件首饰"),
        qc_question="吊坠、流苏或链坠的垂坠方向、连接点和长度关系是否保留",
    ),
)


def build_product_fidelity_constraints(
    product: ProductAnalysis,
    *,
    product_id: str | None = None,
    product_image: str = "input/product-on-hand.jpg",
    product_analysis: str = "analysis/product_analysis.json",
) -> ProductFidelityConstraints:
    source: dict[str, Any] = {
        "product_image": product_image,
        "product_analysis": product_analysis,
        "product_analysis_sha256": product_analysis_sha256(product),
        "product_type": product.normalized_product_type.value,
    }
    if product_id:
        source["product_id"] = product_id
    constraints = _build_product_fidelity_constraints_unvalidated(product, source)
    return validate_product_fidelity_constraints(product, constraints)


def _build_product_fidelity_constraints_unvalidated(
    product: ProductAnalysis,
    source: dict[str, Any],
) -> ProductFidelityConstraints:
    if product.normalized_product_type is ProductType.RING:
        return _build_ring_fidelity_constraints(product, source)
    if product.normalized_product_type in {
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
    }:
        return _build_necklace_v2_fidelity_constraints(product, source)

    text = _constraint_source_text(product)
    must_keep: list[MustKeepConstraint] = []
    detected_keywords: list[str] = []

    for rule in KEYWORD_RULES:
        matched_alias = _first_matching_alias(text, rule.aliases)
        if matched_alias is None:
            continue
        source_text = _source_text_for_alias(product, matched_alias)
        detected_keywords.append(rule.normalized)
        must_keep.append(
            MustKeepConstraint(
                name=_constraint_name(rule.normalized, matched_alias),
                source_text=source_text,
                normalized_keyword=rule.normalized,
                location=_infer_location(source_text, matched_alias),
                visual_shape=rule.visual_shape,
                relationship=rule.relationship,
                forbid=rule.forbid,
                qc_question=rule.qc_question,
            )
        )

    review_status = "pending" if must_keep else "not_applicable"
    return ProductFidelityConstraints(
        schema_version=1,
        source=source,
        detected_keywords=tuple(detected_keywords),
        must_keep=tuple(must_keep),
        must_not_change=_non_ring_must_not_change(product),
        needs_user_review=bool(must_keep),
        detail_crop_recommended=bool(must_keep),
        review_status=review_status,  # type: ignore[arg-type]
    )


def _build_necklace_v2_fidelity_constraints(
    product: ProductAnalysis,
    source: dict[str, Any],
) -> ProductFidelityConstraints:
    has_structured_pendant = (
        product.normalized_product_type is ProductType.PENDANT_NECKLACE
        and product.has_pendant
    )
    if has_structured_pendant and product.pendant_count != 1:
        raise ValueError("第一阶段只支持 1 颗主吊坠")

    semantics = PendantSemantics(
        presence="present" if has_structured_pendant else "absent",
        count=1 if has_structured_pendant else 0,
        layer=product.pendant_layer if has_structured_pendant else None,
        creation_policy="forbid",
        position=product.pendant_position if has_structured_pendant else None,
        orientation=(
            product.pendant_orientation if has_structured_pendant else None
        ),
        connection=(
            product.connection_structure if has_structured_pendant else None
        ),
    )
    must_keep, detected_keywords = _extract_non_pendant_necklace_items(product)
    if has_structured_pendant:
        assert product.pendant_layer is not None
        must_keep.append(
            MustKeepConstraint(
                name="主吊坠可见结构",
                source_text=product.visible_appearance,
                normalized_keyword="吊坠",
                location=product.pendant_position or "产品图中肉眼可见位置",
                visual_shape=product.visible_appearance,
                relationship=(
                    f"保持第 {product.pendant_layer} 层、原朝向和肉眼可见连接关系："
                    f"{product.connection_structure or '只按产品图可见连接'}"
                ),
                forbid=("删除", "复制", "换层", "新增第二颗"),
                qc_question=(
                    f"现有 1 颗主吊坠是否仍位于第 {product.pendant_layer} 层，"
                    "并保持产品图中的位置、朝向和肉眼可见连接关系"
                ),
            )
        )
        detected_keywords.append("吊坠")

    return ProductFidelityConstraints(
        schema_version=2,
        source=source,
        detected_keywords=tuple(detected_keywords),
        must_keep=tuple(must_keep),
        must_not_change=_non_ring_must_not_change(product),
        needs_user_review=bool(must_keep),
        detail_crop_recommended=bool(must_keep),
        review_status="pending" if must_keep else "not_applicable",
        pendant_semantics=semantics,
    )


def _contains_pendant_term(text: str) -> bool:
    return any(term in text for term in _PENDANT_SENSITIVE_TERMS)


def _without_pendant_terms(text: str) -> str:
    result = text
    for term in _PENDANT_SENSITIVE_TERMS:
        result = result.replace(term, "垂饰")
    return result


def _necklace_rule_text(text: str) -> str:
    return _without_pendant_terms(text).replace("主珠", "相邻珠体")


def _extract_non_pendant_necklace_items(
    product: ProductAnalysis,
) -> tuple[list[MustKeepConstraint], list[str]]:
    text = _constraint_source_text(product)
    must_keep: list[MustKeepConstraint] = []
    detected_keywords: list[str] = []
    for rule in KEYWORD_RULES:
        if rule.normalized == "吊坠":
            continue
        matched_alias = _first_matching_alias(text, rule.aliases)
        if matched_alias is None:
            continue
        source_text = _source_text_for_alias(product, matched_alias)
        if _contains_pendant_term(source_text):
            source_text = matched_alias
        detected_keywords.append(rule.normalized)
        must_keep.append(
            MustKeepConstraint(
                name=_constraint_name(rule.normalized, matched_alias),
                source_text=source_text,
                normalized_keyword=rule.normalized,
                location=_infer_location(source_text, matched_alias),
                visual_shape=_necklace_rule_text(rule.visual_shape),
                relationship=_necklace_rule_text(rule.relationship),
                forbid=tuple(_necklace_rule_text(text) for text in rule.forbid),
                qc_question=_necklace_rule_text(rule.qc_question),
            )
        )
    return must_keep, detected_keywords


def _build_ring_fidelity_constraints(
    product: ProductAnalysis,
    source: dict[str, Any],
) -> ProductFidelityConstraints:
    visible_appearance = product.visible_appearance
    color_text = "、".join(product.color_family) or "以产品图肉眼可见颜色为准"
    must_keep = [
        MustKeepConstraint(
            name="戒指整体可见结构",
            source_text=visible_appearance,
            normalized_keyword="戒指整体可见结构",
            location="产品图中可见的整枚戒指",
            visual_shape=visible_appearance,
            relationship=(
                "逐项保持戒面、主石、镶嵌、戒圈、开口端点和装饰排列在产品图中"
                "肉眼可见的数量、形状、朝向与位置关系"
            ),
            forbid=(
                "改款或用通用戒指结构替代",
                "新增、删除或复制戒面、主石、开口端点及装饰",
                "改变可见镶嵌、戒圈粗细、开口关系或装饰排列",
                "关闭现有开口或新增开口",
                "把不可见戒圈背面、镶嵌背面或连接结构补写为确定结构",
            ),
            qc_question=(
                "请对照产品图逐项检查戒面、主石、戒圈、开口端点和装饰排列："
                "它们肉眼可见的数量、形状、朝向及位置关系是否分别与原产品一致？"
            ),
        ),
        MustKeepConstraint(
            name="戒指可见颜色与材质表现",
            source_text=f"颜色范围：{color_text}；可见描述：{visible_appearance}",
            normalized_keyword="戒指可见颜色与材质表现",
            location="整枚戒指肉眼可见表面",
            visual_shape=(
                f"颜色范围为{color_text}；材质只按产品图中的光泽、透明度、纹理和反光表现保留"
            ),
            relationship="颜色与可见材质表现必须附着于原有戒面、主石、戒圈和装饰位置",
            forbid=(
                "换色或改变透明度、纹理、光泽与反光",
                "根据材质名称猜测并重设计表面",
                "把不同部位的颜色或材质表现互换",
            ),
            qc_question=(
                f"请对照产品图逐项检查{color_text}及可见材质表现：戒面、主石、戒圈和装饰的"
                "颜色、透明度、纹理、光泽与反光是否分别保持一致，且没有凭空猜测材质？"
            ),
        ),
    ]
    for index, requirement in enumerate(product.special_requirements, start=1):
        must_keep.append(
            MustKeepConstraint(
                name=f"戒指产品特定要求{index}",
                source_text=requirement,
                normalized_keyword="戒指产品特定要求",
                location="该要求涉及的戒指肉眼可见部位",
                visual_shape=_ring_requirement_visual_shape(requirement),
                relationship="保持该要求涉及部位与戒面、主石、戒圈、开口端点或装饰的原有关系",
                forbid=_ring_requirement_forbid(requirement),
                qc_question=_ring_requirement_qc_question(requirement),
            )
        )

    must_not_change = [
        "戒面、主石、镶嵌、戒圈、开口端点和装饰的可见数量、形状、朝向及排列关系",
        "戒圈可见粗细、开口数量与两端点的位置关系",
        "整枚戒指可见颜色、材质表现、透明度、纹理、光泽和反光",
        "不可推断或补写不可见戒圈背面、镶嵌背面及连接结构",
    ]
    must_not_change.extend(
        f"不可推断或补写被遮挡部分：{part}" for part in product.occluded_parts
    )
    must_not_change.extend(
        f"不可把不确定细节写成确定结构或擅自补全：{detail}"
        for detail in product.uncertain_details
    )

    return ProductFidelityConstraints(
        schema_version=1,
        source=source,
        detected_keywords=(),
        must_keep=tuple(must_keep),
        must_not_change=tuple(must_not_change),
        needs_user_review=True,
        detail_crop_recommended=True,
        review_status="pending",
    )


def validate_product_fidelity_constraints(
    product: ProductAnalysis,
    constraints: ProductFidelityConstraints,
) -> ProductFidelityConstraints:
    """校验 canonical 约束与最终产品分析的一致性。"""
    if not isinstance(product, ProductAnalysis):
        raise ValueError("product 必须是 ProductAnalysis")
    if not isinstance(constraints, ProductFidelityConstraints):
        raise ValueError("constraints 必须是 ProductFidelityConstraints")
    _validate_constraint_runtime_types(constraints)
    product_analysis_path = constraints.source.get("product_analysis")
    if type(product_analysis_path) is not str or not product_analysis_path.strip():
        raise ValueError("产品保真约束 source.product_analysis 必须是非空字符串")
    actual_digest = constraints.source.get("product_analysis_sha256")
    expected_digest = product_analysis_sha256(product)
    if type(actual_digest) is not str or actual_digest != expected_digest:
        raise ValueError(
            "产品保真约束 source.product_analysis_sha256 与最终 ProductAnalysis 不一致"
        )
    actual_product_type = constraints.source.get("product_type")
    expected_product_type = product.normalized_product_type.value
    if (
        type(actual_product_type) is not str
        or actual_product_type != expected_product_type
    ):
        raise ValueError(
            "产品保真约束 source.product_type 与最终 ProductAnalysis 品类不一致"
        )
    if product.normalized_product_type in {
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
    }:
        _validate_v2_pendant_semantics(product, constraints)

    expected = _build_product_fidelity_constraints_unvalidated(
        product,
        dict(constraints.source),
    )
    _validate_canonical_projection(constraints, expected)

    if product.normalized_product_type is not ProductType.RING:
        if product.normalized_product_type in {
            ProductType.NECKLACE,
            ProductType.PENDANT_NECKLACE,
        }:
            semantic_text = _constraints_semantic_text(constraints)
            for forbidden in (
                "珠子排列顺序",
                "主珠",
                "配珠",
                "手腕环绕",
            ):
                if forbidden in semantic_text:
                    raise ValueError(
                        f"项链产品保真约束不得包含手串语义：{forbidden}"
                    )
        elif product.normalized_product_type is ProductType.BRACELET:
            semantic_text = _constraints_semantic_text(constraints)
            for forbidden in (
                "项链",
                "绕颈",
                "锁骨",
                "后颈",
                "层间落差",
                "吊坠所属层",
            ):
                if forbidden in semantic_text:
                    raise ValueError(
                        f"手串产品保真约束不得包含项链语义：{forbidden}"
                    )
        return constraints

    prefix = "戒指产品保真约束"
    if not constraints.must_keep:
        raise ValueError(f"{prefix}的 must_keep 不得为空")
    if constraints.review_status == "not_applicable":
        raise ValueError(f"{prefix}不得使用 not_applicable")
    if not constraints.needs_user_review or not constraints.detail_crop_recommended:
        raise ValueError(
            f"{prefix}必须保持 needs_user_review=true 且 detail_crop_recommended=true"
        )

    semantic_text = _constraints_semantic_text(constraints)
    for forbidden in ("珠子排列顺序", "主珠"):
        if forbidden in semantic_text:
            raise ValueError(f"{prefix}不得包含手串语义：{forbidden}")

    structure_items = _ring_items_by_keyword(constraints, "戒指整体可见结构")
    if len(structure_items) != 1:
        raise ValueError(f"{prefix}必须有且只有一项戒指整体可见结构")
    structure = structure_items[0]
    if structure.source_text != product.visible_appearance:
        raise ValueError(f"{prefix}必须直接引用最终 analysis.visible_appearance")
    required_structure_forbid = {
        "关闭现有开口或新增开口",
        "把不可见戒圈背面、镶嵌背面或连接结构补写为确定结构",
    }
    missing_forbid = required_structure_forbid.difference(structure.forbid)
    if missing_forbid:
        raise ValueError(
            f"{prefix}的整体结构 forbid 缺少：{'、'.join(sorted(missing_forbid))}"
        )

    color_items = _ring_items_by_keyword(constraints, "戒指可见颜色与材质表现")
    if len(color_items) != 1:
        raise ValueError(f"{prefix}必须有且只有一项戒指可见颜色与材质表现")
    color_source = color_items[0].source_text
    if product.visible_appearance not in color_source:
        raise ValueError(f"{prefix}的颜色/材质项必须引用 visible_appearance")
    missing_colors = [color for color in product.color_family if color not in color_source]
    if missing_colors:
        raise ValueError(
            f"{prefix}的颜色/材质项缺少 color_family：{'、'.join(missing_colors)}"
        )

    requirement_items = _ring_items_by_keyword(constraints, "戒指产品特定要求")
    actual_requirements = [item.source_text for item in requirement_items]
    if actual_requirements != list(product.special_requirements):
        raise ValueError(
            f"{prefix}必须与 analysis.special_requirements 按原顺序一一对应"
        )
    for item, requirement in zip(
        requirement_items,
        product.special_requirements,
        strict=True,
    ):
        if item.visual_shape != _ring_requirement_visual_shape(requirement):
            raise ValueError(
                f"{prefix}的产品特定要求 visual_shape 未精确关联：{requirement}"
            )
        if item.forbid != _ring_requirement_forbid(requirement):
            raise ValueError(
                f"{prefix}的产品特定要求 forbid 未精确关联：{requirement}"
            )
        if item.qc_question != _ring_requirement_qc_question(requirement):
            raise ValueError(
                f"{prefix}的产品特定要求 qc_question 未精确关联：{requirement}"
            )

    protection_lines = [
        *constraints.must_not_change,
        *(forbid for item in constraints.must_keep for forbid in item.forbid),
    ]
    for part in product.occluded_parts:
        if not _has_protected_boundary(protection_lines, part):
            raise ValueError(f"{prefix}未禁止推断被遮挡部分：{part}")
    for detail in product.uncertain_details:
        if not _has_protected_boundary(protection_lines, detail):
            raise ValueError(f"{prefix}未禁止确定性补全不确定细节：{detail}")
    return constraints


def _validate_constraint_runtime_types(
    constraints: ProductFidelityConstraints,
) -> None:
    if type(constraints.schema_version) is not int:
        raise ValueError("canonical schema_version 必须是整数")
    if type(constraints.source) is not dict:
        raise ValueError("canonical source 必须是对象")
    for field_name in ("detected_keywords", "must_keep", "must_not_change"):
        if type(getattr(constraints, field_name)) is not tuple:
            raise ValueError(f"canonical {field_name} 必须是 tuple")
    if any(type(item) is not str for item in constraints.detected_keywords):
        raise ValueError("canonical detected_keywords 必须只含字符串")
    if any(
        not isinstance(item, MustKeepConstraint) for item in constraints.must_keep
    ):
        raise ValueError("canonical must_keep 必须只含 MustKeepConstraint")
    if any(type(item) is not str for item in constraints.must_not_change):
        raise ValueError("canonical must_not_change 必须只含字符串")
    for field_name in ("needs_user_review", "detail_crop_recommended"):
        if type(getattr(constraints, field_name)) is not bool:
            raise ValueError(f"canonical {field_name} 必须是布尔值")
    if type(constraints.review_status) is not str:
        raise ValueError("canonical review_status 必须是字符串")
    if constraints.review_status not in {
        "pending",
        "confirmed",
        "corrected",
        "not_applicable",
    }:
        raise ValueError(
            "canonical review_status 必须是 pending/confirmed/corrected/not_applicable"
        )
    if constraints.schema_version == 1:
        if constraints.pendant_semantics is not None:
            raise ValueError("canonical v1 pendant_semantics 必须为空")
    elif constraints.schema_version == 2:
        if not isinstance(constraints.pendant_semantics, PendantSemantics):
            raise ValueError("canonical v2 pendant_semantics 必须是 PendantSemantics")


def _validate_canonical_projection(
    constraints: ProductFidelityConstraints,
    expected: ProductFidelityConstraints,
) -> None:
    for field_name in (
        "schema_version",
        "detected_keywords",
        "must_keep",
        "needs_user_review",
        "detail_crop_recommended",
        "pendant_semantics",
    ):
        if getattr(constraints, field_name) != getattr(expected, field_name):
            raise ValueError(
                f"产品保真约束 canonical.{field_name} 与最终 ProductAnalysis 不一致"
            )

    allowed_additions = (
        ("禁止新增第二颗吊坠",)
        if expected.pendant_semantics is not None
        and expected.pendant_semantics.presence == "present"
        else ()
    )
    if constraints.must_not_change not in {
        expected.must_not_change,
        (*expected.must_not_change, *allowed_additions),
    }:
        raise ValueError(
            "产品保真约束 canonical.must_not_change 与最终 ProductAnalysis 不一致"
        )

    if expected.review_status == "not_applicable":
        allowed_statuses = {"not_applicable"}
    else:
        allowed_statuses = {"pending", "confirmed", "corrected"}
    if constraints.review_status not in allowed_statuses:
        raise ValueError(
            "产品保真约束 canonical.review_status 与 must_keep 确认边界不一致"
        )


def _validate_v2_pendant_semantics(
    product: ProductAnalysis,
    constraints: ProductFidelityConstraints,
) -> None:
    if constraints.schema_version != 2 or constraints.pendant_semantics is None:
        raise ValueError(
            "历史 v1 只读，不得用于新的项链决策或生成；"
            "请新建 run 并重新执行 prepare-review"
        )
    if (
        product.normalized_product_type is ProductType.PENDANT_NECKLACE
        and product.pendant_count != 1
    ):
        raise ValueError(
            "吊坠结构冲突："
            f"analysis={product.normalized_product_type.value}/"
            f"has_pendant={product.has_pendant}/count={product.pendant_count}/"
            f"layer={product.pendant_layer}，"
            f"canonical={constraints.pendant_semantics.to_dict()}；"
            "请新建 run 并重新执行 prepare-review"
        )
    expected = (
        PendantSemantics(
            presence="present",
            count=1,
            layer=product.pendant_layer,
            creation_policy="forbid",
            position=product.pendant_position,
            orientation=product.pendant_orientation,
            connection=product.connection_structure,
        )
        if product.normalized_product_type is ProductType.PENDANT_NECKLACE
        else PendantSemantics(
            presence="absent",
            count=0,
            layer=None,
            creation_policy="forbid",
        )
    )
    if constraints.pendant_semantics != expected:
        raise ValueError(
            "吊坠结构冲突："
            f"analysis={product.normalized_product_type.value}/"
            f"has_pendant={product.has_pendant}/count={product.pendant_count}/"
            f"layer={product.pendant_layer}，"
            f"canonical={constraints.pendant_semantics.to_dict()}；"
            "请新建 run 并重新执行 prepare-review"
        )

    if constraints.pendant_semantics.presence == "absent":
        for field_path, text in _iter_constraint_semantic_fields(constraints):
            for term in ("吊坠", "主吊坠", "链坠", "流苏", "坠子"):
                if term in text:
                    raise ValueError(
                        f"v2 无吊坠 canonical 的 {field_path} "
                        f"不得包含敏感词：{term}"
                    )
        return

    for field_path, text in _iter_constraint_semantic_fields(constraints):
        for phrase in _PRESENT_PENDANT_CONFLICT_PHRASES:
            if phrase in text:
                raise ValueError(
                    f"{field_path} 与 present canonical 冲突：{phrase}"
                )

    pendant_items = [
        item
        for item in constraints.must_keep
        if item.normalized_keyword in _PENDANT_SENSITIVE_TERMS
    ]
    if len(pendant_items) != 1:
        raise ValueError("v2 有吊坠 canonical 必须有且只有一项可追溯主吊坠 must_keep")
    expected_layer = f"第 {constraints.pendant_semantics.layer} 层"
    if expected_layer not in pendant_items[0].relationship:
        raise ValueError(
            "v2 有吊坠 canonical 的可追溯主吊坠 must_keep.relationship "
            f"必须包含 {expected_layer}"
        )


def _constraints_semantic_text(
    constraints: ProductFidelityConstraints,
) -> str:
    return "；".join(
        text for _field_name, text in _iter_constraint_semantic_fields(constraints)
    )


def _iter_constraint_semantic_fields(
    constraints: ProductFidelityConstraints,
) -> Iterator[tuple[str, str]]:
    for index, keyword in enumerate(constraints.detected_keywords):
        yield f"detected_keywords[{index}]", keyword
    for index, text in enumerate(constraints.must_not_change):
        yield f"must_not_change[{index}]", text
    for item_index, item in enumerate(constraints.must_keep):
        prefix = f"must_keep[{item_index}]"
        yield f"{prefix}.name", item.name
        yield f"{prefix}.source_text", item.source_text
        yield f"{prefix}.normalized_keyword", item.normalized_keyword
        yield f"{prefix}.location", item.location
        yield f"{prefix}.visual_shape", item.visual_shape
        yield f"{prefix}.relationship", item.relationship
        for forbid_index, text in enumerate(item.forbid):
            yield f"{prefix}.forbid[{forbid_index}]", text
        yield f"{prefix}.qc_question", item.qc_question


def product_analysis_sha256(product: ProductAnalysis) -> str:
    if not isinstance(product, ProductAnalysis):
        raise ValueError("product 必须是 ProductAnalysis")
    # 局部导入避免 product_analysis -> product_fidelity 的模块初始化环。
    from jewelry_on_hand.product_analysis import product_analysis_to_dict

    payload = json.dumps(
        product_analysis_to_dict(product),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _non_ring_must_not_change(product: ProductAnalysis) -> tuple[str, ...]:
    if product.normalized_product_type in {
        ProductType.NECKLACE,
        ProductType.PENDANT_NECKLACE,
    }:
        constraints = [
            "项链层数、上下顺序、相对落差和链条完整性",
            "产品整体颜色、透明度、纹理和反光",
            "不可推断或补写不可见扣头、链条背面或连接结构",
        ]
        if product.has_pendant:
            constraints.insert(1, "吊坠所属层、位置、朝向和肉眼可见连接关系")
        return tuple(constraints)
    return (
        "珠子排列顺序",
        "主珠和配件位置关系",
        "产品整体颜色、透明度、纹理和反光",
    )


def _ring_items_by_keyword(
    constraints: ProductFidelityConstraints,
    normalized_keyword: str,
) -> list[MustKeepConstraint]:
    return [
        item
        for item in constraints.must_keep
        if item.normalized_keyword == normalized_keyword
    ]


def _ring_requirement_visual_shape(requirement: str) -> str:
    return f"按产品图肉眼可见事实核对：{requirement}"


def _ring_requirement_forbid(requirement: str) -> tuple[str, ...]:
    return (
        f"忽略或改变产品特定要求：{requirement}",
        "用通用戒指款式替代该产品特定要求",
    )


def _ring_requirement_qc_question(requirement: str) -> str:
    return (
        f"请对照产品图逐项检查产品特定要求“{requirement}”：涉及的主石、戒面、戒圈、"
        "开口端点或装饰排列是否保持原有可见形状、朝向、数量和位置关系？"
    )


def _has_protected_boundary(lines: list[str], detail: str) -> bool:
    boundary_terms = ("不可推断", "不可补写", "禁止推断", "禁止补写", "不得推断", "不得补写", "不确定", "确定结构", "擅自补全")
    return any(
        detail in line and any(term in line for term in boundary_terms)
        for line in lines
    )


def write_product_fidelity_constraints(
    paths: RunPaths,
    product: ProductAnalysis,
    *,
    product_id: str | None = None,
) -> Path:
    constraints = build_product_fidelity_constraints(product, product_id=product_id)
    constraints_path = paths.analysis_dir / CONSTRAINTS_FILE_NAME
    write_json(constraints_path, constraints.to_dict())
    return constraints_path


def load_product_fidelity_constraints(path: str | Path) -> ProductFidelityConstraints:
    return ProductFidelityConstraints.from_dict(read_json(path))


def require_confirmed_constraints(path: str | Path) -> ProductFidelityConstraints:
    constraints = load_product_fidelity_constraints(path)
    if constraints.review_status not in CONFIRMED_REVIEW_STATUSES:
        raise ValueError(
            f"{path} 的 review_status={constraints.review_status}，必须为 confirmed/corrected/not_applicable"
        )
    return constraints


def default_constraints_path(paths: RunPaths) -> Path:
    return paths.analysis_dir / CONSTRAINTS_FILE_NAME


def _constraint_source_text(product: ProductAnalysis) -> str:
    return "；".join(
        [product.visible_appearance, *product.special_requirements]
    )


def _first_matching_alias(text: str, aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if _text_has_positive_alias(text, alias):
            return alias
    return None


def _text_has_positive_alias(text: str, alias: str) -> bool:
    fragments = re.split(
        r"[，,。；;！？!?\n]+|(?:但(?:是)?|而是|不过|然而|却)",
        text,
    )
    for fragment in fragments:
        start = 0
        while True:
            index = fragment.find(alias, start)
            if index < 0:
                break
            before = fragment[:index]
            if not _is_negated_alias_mention(before):
                return True
            start = index + len(alias)
    return False


def _is_negated_alias_mention(before: str) -> bool:
    if re.search(r"(?:内部图\s*1|参考图|参考素材)[^，,。；;！？!?\n]{0,30}$", before):
        return True
    if re.search(
        r"(?:不是|没有|并非|未见|不含|不带|不存在|未包含|未佩戴|无)"
        r"[^，,。；;！？!?\n]{0,24}$",
        before,
    ):
        return True
    return bool(
        re.search(
            r"(?:禁止|不得|不可|不能|避免)[^，,。；;！？!?\n]{0,30}"
            r"(?:改成|变成|转成|新增|增加|添加|补充|补写|补造|悬挂化)"
            r"[^，,。；;！？!?\n]{0,12}$",
            before,
        )
    )


def _has_positive_pendant_semantics(
    constraints: ProductFidelityConstraints,
) -> bool:
    if any(
        keyword.strip() in _V1_PENDANT_CANONICAL_KEYWORDS
        for keyword in constraints.detected_keywords
    ):
        return True
    if any(
        item.normalized_keyword.strip() in _V1_PENDANT_CANONICAL_KEYWORDS
        for item in constraints.must_keep
    ):
        return True
    return any(
        _line_has_positive_pendant_semantics(
            text,
            field_name=field_name,
        )
        for field_name, text in _iter_constraint_semantic_fields(constraints)
    )


def _line_has_positive_pendant_semantics(
    line: str,
    *,
    field_name: str,
) -> bool:
    pendant_terms = r"(?:主吊坠|吊坠|流苏|链坠)"
    preservation_actions = r"(?:保持|保留|维持|保有|保全|保存|维护|延续)"
    destructive_actions = (
        r"(?:改变(?!为|成)|变更|更改|改动|删除|移除|丢失|遗失|破坏|取消|"
        r"替换(?!为)|换掉)"
    )
    creation_actions = (
        r"(?:新增|增加|添加|补充|补写|补造|悬挂化|改成|改为|改变为|改变成|"
        r"变成|转成|转换为|替换为)"
    )
    clauses = _split_pendant_semantic_clauses(line)
    for clause in clauses:
        if not re.search(pendant_terms, clause):
            continue
        has_preservation = bool(re.search(preservation_actions, clause))
        has_destruction = bool(re.search(destructive_actions, clause))
        has_creation = bool(re.search(creation_actions, clause))
        if (
            _has_explicit_pendant_absence(clause, pendant_terms)
            and not has_preservation
            and not has_destruction
        ):
            continue
        if has_destruction:
            return True
        if has_preservation and not _actions_are_locally_negated(
            clause,
            preservation_actions,
            implicit_prohibition=field_name == "forbid",
            blocking_action_patterns=(creation_actions, destructive_actions),
        ):
            return True
        if has_creation and not _actions_are_locally_negated(
            clause,
            creation_actions,
            implicit_prohibition=field_name in {"forbid", "must_not_change"},
            blocking_action_patterns=(preservation_actions, destructive_actions),
        ):
            return True
        if not has_preservation and not has_creation:
            return True
    return False


def _split_pendant_semantic_clauses(text: str) -> list[str]:
    return re.split(
        r"[，,。；;！？!?\n]+|"
        r"(?:但是|并且|同时|而且|以及|不过|然而|而是|但|又|且|并(?!非|不)|却)",
        text,
    )


def _actions_are_locally_negated(
    text: str,
    action_pattern: str,
    *,
    implicit_prohibition: bool,
    blocking_action_patterns: tuple[str, ...],
) -> bool:
    action_matches = tuple(re.finditer(action_pattern, text))
    if not action_matches:
        return False
    if implicit_prohibition:
        return True
    blocking_matches = tuple(
        match
        for pattern in blocking_action_patterns
        for match in re.finditer(pattern, text)
    )
    negation = (
        r"(?:禁止|严禁|不得|不可|不能|不允许|避免|不必|无需|无须|不用|"
        r"不要|不需要|不应|不)"
    )
    for action in action_matches:
        scope_start = max(
            (
                blocker.end()
                for blocker in blocking_matches
                if blocker.end() <= action.start()
            ),
            default=0,
        )
        prefix = text[scope_start : action.start()]
        if not re.search(
            rf"{negation}[^，,。；;！？!?]{{0,24}}$",
            prefix,
        ):
            return False
    return True


def _has_explicit_pendant_absence(
    text: str,
    pendant_pattern: str,
) -> bool:
    return bool(
        re.search(
            rf"(?:没有|不是|并非|未见|不含|不带|不存在|未包含|未佩戴|无)"
            rf"[^，,。；;！？!?]{{0,24}}{pendant_pattern}",
            text,
        )
        or re.search(
            rf"{pendant_pattern}[^，,。；;！？!?]{{0,24}}"
            rf"(?:不存在|未见|缺失|没有)",
            text,
        )
    )


def _constraint_name(normalized: str, matched_alias: str) -> str:
    if normalized == matched_alias:
        return normalized
    return f"{matched_alias}（标准化为{normalized}）"


def _source_text_for_alias(product: ProductAnalysis, alias: str) -> str:
    for item in (product.visible_appearance, *product.special_requirements):
        if _text_has_positive_alias(item, alias):
            return item
    return alias


def _infer_location(text: str, alias: str) -> str:
    markers = ("主珠右侧", "主珠左侧", "正面中心", "中心附近", "垂坠处", "连接处")
    for marker in markers:
        if marker in text:
            return marker
    return f"产品可见区域中的{alias}结构，review 时确认具体位置"


__all__ = [
    "CONSTRAINTS_FILE_NAME",
    "CONFIRMED_REVIEW_STATUSES",
    "KEYWORD_RULES",
    "build_product_fidelity_constraints",
    "default_constraints_path",
    "load_product_fidelity_constraints",
    "product_analysis_sha256",
    "require_confirmed_constraints",
    "validate_product_fidelity_constraints",
    "write_product_fidelity_constraints",
]
