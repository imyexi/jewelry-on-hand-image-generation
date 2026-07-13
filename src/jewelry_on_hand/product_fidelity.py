from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jewelry_on_hand.models import (
    MustKeepConstraint,
    ProductAnalysis,
    ProductFidelityConstraints,
)
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


CONSTRAINTS_FILE_NAME = "product_fidelity_constraints.json"
CONFIRMED_REVIEW_STATUSES = {"confirmed", "corrected", "not_applicable"}


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
    text = _constraint_source_text(product)
    must_keep: list[MustKeepConstraint] = []
    detected_keywords: list[str] = []

    for rule in KEYWORD_RULES:
        matched_alias = _first_matching_alias(text, rule.aliases)
        if matched_alias is None:
            continue
        detected_keywords.append(rule.normalized)
        must_keep.append(
            MustKeepConstraint(
                name=_constraint_name(rule.normalized, matched_alias),
                source_text=_source_text_for_alias(product, matched_alias),
                normalized_keyword=rule.normalized,
                location=_infer_location(text, matched_alias),
                visual_shape=rule.visual_shape,
                relationship=rule.relationship,
                forbid=rule.forbid,
                qc_question=rule.qc_question,
            )
        )

    review_status = "pending" if must_keep else "not_applicable"
    source: dict[str, Any] = {
        "product_image": product_image,
        "product_analysis": product_analysis,
    }
    if product_id:
        source["product_id"] = product_id

    return ProductFidelityConstraints(
        schema_version=1,
        source=source,
        detected_keywords=tuple(detected_keywords),
        must_keep=tuple(must_keep),
        must_not_change=(
            "珠子排列顺序",
            "主珠和配件位置关系",
            "产品整体颜色、透明度、纹理和反光",
        ),
        needs_user_review=bool(must_keep),
        detail_crop_recommended=bool(must_keep),
        review_status=review_status,  # type: ignore[arg-type]
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
        if alias in text:
            return alias
    return None


def _constraint_name(normalized: str, matched_alias: str) -> str:
    if normalized == matched_alias:
        return normalized
    return f"{matched_alias}（标准化为{normalized}）"


def _source_text_for_alias(product: ProductAnalysis, alias: str) -> str:
    for item in (product.visible_appearance, *product.special_requirements):
        if alias in item:
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
    "require_confirmed_constraints",
    "write_product_fidelity_constraints",
]
