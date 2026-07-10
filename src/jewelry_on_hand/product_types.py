from __future__ import annotations

import re
from enum import Enum


_UNCERTAIN_TEXT_MARKERS = (
    "不是",
    "并非",
    "不属于",
    "疑似",
    "可能",
    "也许",
    "或许",
    "不确定",
    "待确认",
    "无法确认",
    "吗",
    "?",
    "？",
    "或",
    "还是",
)

_UNSUPPORTED_CATEGORY_TERMS = (
    "戒指",
    "耳环",
    "耳饰",
    "耳坠",
    "胸针",
    "脚链",
    "发饰",
)

_UNCERTAIN_ENGLISH_PATTERN = re.compile(r"\b(?:not|or)\b")
_UNSUPPORTED_ENGLISH_CATEGORY_PATTERN = re.compile(r"\b(?:ring|earring|brooch)\b")


class ProductType(str, Enum):
    BRACELET = "bracelet"
    NECKLACE = "necklace"
    PENDANT_NECKLACE = "pendant_necklace"
    PENDANT_ONLY = "pendant_only"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return {
            ProductType.BRACELET: "手串/手链",
            ProductType.NECKLACE: "普通项链",
            ProductType.PENDANT_NECKLACE: "带链吊坠",
            ProductType.PENDANT_ONLY: "无链独立吊坠",
            ProductType.UNKNOWN: "无法识别",
        }[self]


def normalize_product_type(value: str | ProductType | None) -> ProductType:
    if isinstance(value, ProductType):
        return value
    if not isinstance(value, str):
        return ProductType.UNKNOWN

    text = value.strip().lower()
    if not text:
        return ProductType.UNKNOWN

    exact_values = {item.value: item for item in ProductType}
    if text in exact_values:
        return exact_values[text]
    if any(marker in text for marker in _UNCERTAIN_TEXT_MARKERS) or (
        _UNCERTAIN_ENGLISH_PATTERN.search(text)
    ):
        return ProductType.UNKNOWN
    if any(term in text for term in _UNSUPPORTED_CATEGORY_TERMS) or (
        _UNSUPPORTED_ENGLISH_CATEGORY_PATTERN.search(text)
    ):
        return ProductType.UNKNOWN

    matches: set[ProductType] = set()
    remaining = text

    category_terms = (
        (ProductType.PENDANT_ONLY, ("无链独立吊坠", "无链吊坠", "pendant only")),
        (
            ProductType.PENDANT_NECKLACE,
            ("带链吊坠", "吊坠项链", "项链吊坠", "pendant necklace"),
        ),
        (ProductType.BRACELET, ("手链", "手串", "手镯", "bracelet")),
        (ProductType.NECKLACE, ("普通项链", "项链", "珠链", "necklace")),
    )
    for product_type, terms in category_terms:
        matched_terms = tuple(term for term in terms if term in remaining)
        if not matched_terms:
            continue
        matches.add(product_type)
        for term in matched_terms:
            remaining = remaining.replace(term, "")

    if len(matches) == 1:
        return matches.pop()
    return ProductType.UNKNOWN
