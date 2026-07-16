from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType

if TYPE_CHECKING:
    from jewelry_on_hand.models import ProductAnalysis, ReferenceRow


SHARED_BASIC_QC_ITEMS = ("禁止推断不可见扣头或背面结构",)
_BROAD_NEGATION_PREFIXES = (
    "没有明显",
    "无明显",
    "不存在",
    "不包括",
    "不含",
    "不是",
    "不适合",
    "未见",
    "没有",
    "无",
    "未",
)
_DIRECT_NEGATION_PREFIXES = ("不", "非")
_NEGATION_PREFIXES = _BROAD_NEGATION_PREFIXES + _DIRECT_NEGATION_PREFIXES
_NON_NEGATION_PREFIXES = ("非常", "不错", "不只是", "不仅", "不但", "不单", "不止", "不局限于")
_NEGATION_BOUNDARIES = "，,。；;：:\n\r\t"
_NEGATION_CONTRAST_BOUNDARIES = ("但是", "不过", "然而", "但", "却")
_NEGATION_CONNECTORS = ("或", "和", "及", "与", "/", "、")
_CONTROLLED_NEGATIONS = (
    "不含",
    "不包括",
    "未包含",
    "没有",
    "未见",
    "不可见",
    "看不到",
    "无法",
    "无",
    "未",
    "不",
)
_POSITIVE_VISIBILITY_QUALIFIERS = ("可见", "清晰", "完整", "露出")
_NEGATIVE_VISIBILITY_QUALIFIERS = (
    "不可见",
    "未见",
    "不清晰",
    "不完整",
    "没有露出",
    "未露出",
)
_STRONG_CLAUSE_BOUNDARIES = (
    "。",
    "；",
    ";",
    "！",
    "!",
    "？",
    "?",
    "但是",
    "不过",
    "然而",
    "但",
    "却",
)


class ControlledLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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


@dataclass(frozen=True)
class PromptFragments:
    image_one_role: str
    category_fidelity: str
    display_mode: str
    occlusion_physics: str
    prohibitions: str


PromptFragmentBuilder = Callable[["ProductAnalysis"], PromptFragments]


def contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def is_role_appropriate_priority_strategy(row: "ReferenceRow") -> bool:
    strategy = row.default_strategy
    standard_priority = contains_any(
        strategy,
        ("优先使用", "可优先", "优先"),
    ) and not contains_any(strategy, ("不优先", "不建议", "谨慎使用"))
    lifestyle_non_wrist = (
        row.purpose_category.strip() == "生活场景图"
        and contains_any(strategy, ("非手腕构图，默认不优先", "非手腕构图"))
    )
    return standard_priority or lifestyle_non_wrist


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


def contains_affirmed_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    term_list = sorted(set(terms), key=len, reverse=True)
    for term in term_list:
        lowered_term = term.lower()
        start = 0
        while True:
            index = lowered.find(lowered_term, start)
            if index == -1:
                break
            if any(
                len(other) > len(term) and lowered.startswith(other.lower(), index)
                for other in term_list
            ):
                start = index + len(lowered_term)
                continue
            prefix = _strong_clause_prefix(text, index)
            suffix = text[index + len(term) : index + len(term) + 6]
            explicitly_hidden = suffix.startswith(_NEGATIVE_VISIBILITY_QUALIFIERS)
            explicitly_visible = contains_any(
                suffix, _POSITIVE_VISIBILITY_QUALIFIERS
            ) and not explicitly_hidden
            if not explicitly_hidden and (
                explicitly_visible or not contains_any(prefix, _CONTROLLED_NEGATIONS)
            ):
                return True
            start = index + len(lowered_term)
    return False


def parse_visibility_level(text: str) -> ControlledLevel | None:
    value = _compact_text(text)
    if not value or contains_any(value, ("中低", "中高", "高中", "高低")):
        return None
    if contains_any(
        value,
        (
            "不清晰",
            "不完整",
            "不明显",
            "不可见",
            "看不清",
            "无法辨识",
            "不足",
            "缺失",
            "过小",
            "低",
            "无",
        ),
    ):
        return ControlledLevel.LOW
    if contains_any(value, ("高", "清晰", "完整", "充足", "明显", "可见")):
        return ControlledLevel.HIGH
    if contains_any(value, ("中", "一般", "尚可", "部分", "有限")):
        return ControlledLevel.MEDIUM
    return None


def parse_risk_level(text: str) -> ControlledLevel | None:
    value = _compact_text(text)
    if not value:
        return None
    if contains_affirmed_any(
        value, ("大面积", "完全遮挡", "严重", "明显畸变", "高")
    ):
        return ControlledLevel.HIGH
    if contains_any(
        value,
        (
            "不高",
            "无严重",
            "无明显",
            "没有明显",
            "轻微",
            "较低",
            "低",
            "无",
            "没有",
            "未见",
        ),
    ):
        return ControlledLevel.LOW
    if contains_any(value, ("中", "中等", "一般")):
        return ControlledLevel.MEDIUM
    return None


def parse_confidence_level(text: str) -> ControlledLevel | None:
    value = _compact_text(text)
    if value in {"高", "高置信", "高置信度"}:
        return ControlledLevel.HIGH
    if value in {"中", "中置信", "中置信度"}:
        return ControlledLevel.MEDIUM
    if value in {"低", "低置信", "低置信度"}:
        return ControlledLevel.LOW
    return None


def _compact_text(text: str) -> str:
    return "".join(
        character
        for character in text.strip().lower()
        if not character.isspace()
    )


def _strong_clause_prefix(text: str, term_start: int) -> str:
    prefix = text[:term_start]
    clause_start = 0
    for boundary in _STRONG_CLAUSE_BOUNDARIES:
        index = prefix.rfind(boundary)
        if index >= clause_start:
            clause_start = index + len(boundary)
    return prefix[clause_start:]


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
    mode_qc_items: Mapping[DisplayMode, tuple[str, ...]]
    reference_evaluator: ReferenceEvaluator | None = None
    prompt_fragment_builder: PromptFragmentBuilder | None = None

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
        if self.product_type is ProductType.RING and is_independent_multi_item:
            raise ValueError("当前版本只支持单枚戒指，不支持多件独立组合")

    def evaluate_reference(
        self, product: "ProductAnalysis", row: "ReferenceRow"
    ) -> ReferenceAdaptation:
        if self.reference_evaluator is None:
            return ReferenceAdaptation(
                eligible=False,
                risks=(f"{self.category_name}当前没有可用的参考图适配规则",),
            )
        return self.reference_evaluator(product, row)

    def build_prompt_fragments(self, product: "ProductAnalysis") -> PromptFragments:
        if self.prompt_fragment_builder is None:
            raise ValueError(f"{self.category_name}尚未配置生成 Prompt 策略")
        return self.prompt_fragment_builder(product)

    def qc_items_for_mode(self, display_mode: DisplayMode) -> tuple[str, ...]:
        if not isinstance(display_mode, DisplayMode):
            raise ValueError("展示模式必须使用 DisplayMode 枚举")
        if display_mode not in self.supported_modes:
            raise ValueError(
                f"{self.category_name}不支持 {display_mode.value} 展示模式的 QC"
            )
        mode_items = self.mode_qc_items.get(display_mode)
        if mode_items is None:
            raise ValueError(
                f"{self.category_name}尚未配置 {display_mode.value} 展示模式的 QC 清单"
            )
        return tuple(dict.fromkeys(self.basic_qc_items + mode_items))
