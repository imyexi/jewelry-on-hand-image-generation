from __future__ import annotations

from enum import Enum


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
