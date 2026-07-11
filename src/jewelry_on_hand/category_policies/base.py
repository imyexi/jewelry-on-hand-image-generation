from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType

if TYPE_CHECKING:
    from jewelry_on_hand.models import ProductAnalysis, ReferenceRow


SHARED_BASIC_QC_ITEMS = ("禁止推断不可见扣头或背面结构",)
_BROAD_NEGATION_PREFIXES = ("没有明显", "无明显", "不是", "不适合", "未见", "没有", "无", "未")
_DIRECT_NEGATION_PREFIXES = ("不", "非")
_NEGATION_PREFIXES = _BROAD_NEGATION_PREFIXES + _DIRECT_NEGATION_PREFIXES
_NON_NEGATION_PREFIXES = ("非常", "不错", "不只是", "不仅", "不但", "不单", "不止", "不局限于")
_NEGATION_BOUNDARIES = " 　，,。；;：:\n\r\t"
_NEGATION_CONTRAST_BOUNDARIES = ("但是", "不过", "然而", "但", "却")
_NEGATION_CONNECTORS = ("或", "和", "及", "与", "/", "、")


@dataclass(frozen=True)
class ReferenceAdaptation:
    eligible: bool
    score_adjustment: int = 0
    reasons: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    ignored_reference_jewelry: tuple[str, ...] = ()
    selection_tier: int = 0
    diversity_candidate: bool = False


ReferenceEvaluator = Callable[["ProductAnalysis", "ReferenceRow"], ReferenceAdaptation]


def contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def contains_unnegated_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    term_list = tuple(terms)
    for term in term_list:
        lowered_term = term.lower()
        start = 0
        while True:
            index = lowered.find(lowered_term, start)
            if index == -1:
                break
            if not _has_negation_prefix(text, index, term_list):
                return True
            start = index + len(lowered_term)
    return False


def _has_negation_prefix(text: str, term_start: int, terms: tuple[str, ...]) -> bool:
    prefix = _same_clause_prefix(text, term_start)
    compact_prefix = "".join(char for char in prefix if not char.isspace())
    negation = _nearest_valid_negation(compact_prefix)
    if negation is None:
        return False
    negation_index, negation_text = negation
    tail = compact_prefix[negation_index + len(negation_text) :]
    if negation_text in _DIRECT_NEGATION_PREFIXES:
        return tail == "" or _contains_only_terms_and_connectors(tail, terms)
    return len(tail) <= 6


def _contains_only_terms_and_connectors(text: str, terms: tuple[str, ...]) -> bool:
    remaining = text
    sorted_terms = sorted(terms, key=len, reverse=True)
    while remaining:
        for connector in _NEGATION_CONNECTORS:
            if remaining.startswith(connector):
                remaining = remaining[len(connector) :]
                break
        else:
            for term in sorted_terms:
                if remaining.startswith(term):
                    remaining = remaining[len(term) :]
                    break
            else:
                return False
    return True


def _nearest_valid_negation(compact_prefix: str) -> tuple[int, str] | None:
    candidates: list[tuple[int, str]] = []
    for negation in _NEGATION_PREFIXES:
        start = 0
        while True:
            index = compact_prefix.find(negation, start)
            if index == -1:
                break
            if not any(
                compact_prefix.startswith(phrase, index)
                for phrase in _NON_NEGATION_PREFIXES
            ):
                candidates.append((index, negation))
            start = index + len(negation)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], len(item[1])))


def _same_clause_prefix(text: str, term_start: int) -> str:
    prefix = text[:term_start]
    clause_start = 0
    for boundary in _NEGATION_BOUNDARIES:
        index = prefix.rfind(boundary)
        if index >= clause_start:
            clause_start = index + len(boundary)
    for boundary in _NEGATION_CONTRAST_BOUNDARIES:
        index = prefix.rfind(boundary)
        if index >= clause_start:
            clause_start = index + len(boundary)
    return prefix[clause_start:]


@dataclass(frozen=True)
class CategoryPolicy:
    product_type: ProductType
    supported_modes: frozenset[DisplayMode]
    max_layer_count: int
    basic_qc_items: tuple[str, ...]
    reference_evaluator: ReferenceEvaluator | None = None

    @property
    def category_name(self) -> str:
        return self.product_type.display_name

    def validate_generation(self, layer_count: int, is_independent_multi_item: bool) -> None:
        if self.product_type is ProductType.PENDANT_ONLY:
            raise ValueError("当前版本不支持无链独立吊坠，且禁止自动补链")
        if not 1 <= layer_count <= self.max_layer_count:
            supported_layers = (
                "1 层"
                if self.max_layer_count == 1
                else f"1 至 {self.max_layer_count} 层"
            )
            raise ValueError(f"{self.category_name}只支持 {supported_layers}")
        if (
            self.product_type
            in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}
            and is_independent_multi_item
        ):
            raise ValueError("当前版本不支持多件独立项链组合叠戴")

    def evaluate_reference(
        self, product: "ProductAnalysis", row: "ReferenceRow"
    ) -> ReferenceAdaptation:
        if self.reference_evaluator is None:
            return ReferenceAdaptation(
                eligible=False,
                risks=(f"{self.category_name}当前没有可用的参考图适配规则",),
            )
        return self.reference_evaluator(product, row)
