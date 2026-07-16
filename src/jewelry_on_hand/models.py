from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from jewelry_on_hand.display_modes import DisplayMode, SourceImageType
from jewelry_on_hand.output_roles import OutputRole, normalize_output_role
from jewelry_on_hand.product_types import ProductType, normalize_product_type
from jewelry_on_hand.ring_attributes import FingerPosition, HandSide, RingWearStyle


_DIMENSION_FIELDS = (
    "length_mm",
    "width_mm",
    "height_mm",
    "bead_diameter_mm",
)

_MODERN_CLASSIFICATION_FIELDS = (
    "detected_product_type",
    "confirmed_product_type",
    "classification_confidence",
    "classification_evidence",
    "classification_source",
)

_NECKLACE_LENGTH_CATEGORIES = frozenset(
    {"choker", "collarbone", "upper_chest", "long"}
)


def _ensure_mapping(data: dict[str, Any] | None, model_name: str) -> dict[str, Any]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{model_name} 必须是字典")
    return data


def _positive_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是正数")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} 必须是正数")
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} 必须是正数") from exc
    else:
        raise ValueError(f"{field_name} 必须是正数")
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} 必须大于 0")
    return number


def _required_string(source: dict[str, Any], field_name: str) -> str:
    value = source.get(field_name)
    return _required_string_value(value, field_name)


def _required_string_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _optional_non_empty_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串或 None")
    return value.strip()


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须是字符串列表")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} 只能包含字符串")
    return tuple(value)


def _string_sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} 必须是字符串列表")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} 只能包含字符串")
    return tuple(value)


def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"{field_name} 必须是布尔值或 true/false/1/0/yes/no/y/n 字符串")


def _optional_bool(value: Any, field_name: str, default: bool = False) -> bool:
    if value is None:
        return default
    return _parse_bool(value, field_name)


def _required_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是整数")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} 必须是整数")
    if number < 1:
        raise ValueError(f"{field_name} 必须大于等于 1")
    return number


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是整数或 None")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} 必须是整数或 None") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} 必须是整数或 None")
    if number <= 0:
        raise ValueError(f"{field_name} 必须大于 0")
    return number


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是数字或 None")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是数字或 None") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} 必须是有限非负数")
    return number


def _json_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是 JSON 布尔值")
    return value


def _json_int(value: Any, field_name: str, *, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        suffix = "或 null" if allow_none else ""
        raise ValueError(f"{field_name} 必须是 JSON 整数{suffix}")
    return value


def _normalize_product_type_field(
    value: ProductType | str | None,
    fallback: ProductType | str,
    field_name: str,
) -> ProductType:
    if value is None:
        return normalize_product_type(fallback)
    if not isinstance(value, (ProductType, str)):
        raise ValueError(f"{field_name} 必须是 ProductType、字符串或 None")
    return normalize_product_type(value)


@dataclass(frozen=True)
class ProductDimensions:
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    bead_diameter_mm: float | None = None
    dimension_source: str | None = None

    def __post_init__(self) -> None:
        for field_name in _DIMENSION_FIELDS:
            object.__setattr__(
                self,
                field_name,
                _positive_float(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "dimension_source",
            _optional_non_empty_string(self.dimension_source, "dimension_source"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProductDimensions":
        source = _ensure_mapping(data, "ProductDimensions")
        return cls(
            length_mm=_positive_float(source.get("length_mm"), "length_mm"),
            width_mm=_positive_float(source.get("width_mm"), "width_mm"),
            height_mm=_positive_float(source.get("height_mm"), "height_mm"),
            bead_diameter_mm=_positive_float(source.get("bead_diameter_mm"), "bead_diameter_mm"),
            dimension_source=_optional_non_empty_string(
                source.get("dimension_source"), "dimension_source"
            ),
        )


@dataclass(frozen=True)
class ProductAnalysis:
    product_type: str
    wear_position: str
    visible_appearance: str
    color_family: tuple[str, ...]
    style_mood: str
    composition: str
    product_dimensions: ProductDimensions
    needs_full_front_display: bool
    special_requirements: tuple[str, ...] = field(default_factory=tuple)
    detected_product_type: ProductType | str | None = None
    confirmed_product_type: ProductType | str | None = None
    classification_confidence: str = "high"
    classification_evidence: tuple[str, ...] = field(default_factory=tuple)
    classification_source: str = "legacy_inferred"
    display_mode: DisplayMode | str = DisplayMode.WORN
    source_image_type: SourceImageType | str = SourceImageType.WORN_SOURCE
    layer_count: int = 1
    length_category: str | None = None
    chain_or_strand_type: str | None = None
    has_pendant: bool = False
    pendant_count: int = 0
    pendant_layer: int | None = None
    pendant_position: str | None = None
    pendant_orientation: str | None = None
    connection_structure: str | None = None
    symmetry: str | None = None
    occluded_parts: tuple[str, ...] = field(default_factory=tuple)
    uncertain_details: tuple[str, ...] = field(default_factory=tuple)
    is_independent_multi_item: bool = False
    ring_count: int = 0
    hand_side: HandSide | str = HandSide.UNKNOWN
    finger_position: FingerPosition | str = FingerPosition.UNKNOWN
    ring_wear_style: RingWearStyle | str = RingWearStyle.UNKNOWN

    def __post_init__(self) -> None:
        for field_name in (
            "product_type",
            "wear_position",
            "visible_appearance",
            "style_mood",
            "composition",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_string_value(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "color_family",
            _string_sequence(self.color_family, "color_family"),
        )
        object.__setattr__(
            self,
            "special_requirements",
            _string_sequence(self.special_requirements, "special_requirements"),
        )
        object.__setattr__(
            self,
            "needs_full_front_display",
            _parse_bool(self.needs_full_front_display, "needs_full_front_display"),
        )
        if not isinstance(self.product_dimensions, ProductDimensions):
            raise ValueError("product_dimensions 必须是 ProductDimensions")

        detected = _normalize_product_type_field(
            self.detected_product_type,
            self.product_type,
            "detected_product_type",
        )
        confirmed = _normalize_product_type_field(
            self.confirmed_product_type,
            detected,
            "confirmed_product_type",
        )
        object.__setattr__(self, "detected_product_type", detected)
        object.__setattr__(self, "confirmed_product_type", confirmed)
        object.__setattr__(
            self,
            "classification_evidence",
            _string_sequence(self.classification_evidence, "classification_evidence"),
        )
        for field_name in ("classification_confidence", "classification_source"):
            object.__setattr__(
                self,
                field_name,
                _required_string_value(getattr(self, field_name), field_name),
            )
        try:
            object.__setattr__(self, "display_mode", DisplayMode(self.display_mode))
        except ValueError as exc:
            raise ValueError("display_mode 必须是 worn/hand_held") from exc
        try:
            object.__setattr__(self, "source_image_type", SourceImageType(self.source_image_type))
        except ValueError as exc:
            raise ValueError(
                "source_image_type 必须是 worn_source/hand_held_source/flat_lay_source/unknown_source"
            ) from exc

        object.__setattr__(self, "layer_count", _required_int(self.layer_count, "layer_count"))
        object.__setattr__(self, "has_pendant", _parse_bool(self.has_pendant, "has_pendant"))
        object.__setattr__(
            self,
            "is_independent_multi_item",
            _parse_bool(self.is_independent_multi_item, "is_independent_multi_item"),
        )
        ring_count = _json_int(self.ring_count, "ring_count")
        if ring_count is None or ring_count < 0:
            raise ValueError("ring_count 必须是大于等于 0 的 JSON 整数")
        object.__setattr__(self, "ring_count", ring_count)
        try:
            object.__setattr__(self, "hand_side", HandSide(self.hand_side))
        except (TypeError, ValueError) as exc:
            raise ValueError("hand_side 必须是 left/right/unknown") from exc
        try:
            object.__setattr__(
                self,
                "finger_position",
                FingerPosition(self.finger_position),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "finger_position 必须是 thumb/index/middle/ring/little/unknown"
            ) from exc
        try:
            object.__setattr__(
                self,
                "ring_wear_style",
                RingWearStyle(self.ring_wear_style),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ring_wear_style 必须是 finger_base/midi/cross_finger/unknown"
            ) from exc
        if isinstance(self.pendant_count, bool):
            raise ValueError("pendant_count 必须是大于等于 0 的整数")
        try:
            pendant_count = int(self.pendant_count)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("pendant_count 必须是大于等于 0 的整数") from exc
        if isinstance(self.pendant_count, float) and not self.pendant_count.is_integer():
            raise ValueError("pendant_count 必须是大于等于 0 的整数")
        if pendant_count < 0:
            raise ValueError("pendant_count 必须大于等于 0")
        object.__setattr__(self, "pendant_count", pendant_count)
        object.__setattr__(self, "pendant_layer", _optional_int(self.pendant_layer, "pendant_layer"))
        for field_name in (
            "length_category",
            "chain_or_strand_type",
            "pendant_position",
            "pendant_orientation",
            "connection_structure",
            "symmetry",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_non_empty_string(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "occluded_parts",
            _string_sequence(self.occluded_parts, "occluded_parts"),
        )
        object.__setattr__(
            self,
            "uncertain_details",
            _string_sequence(self.uncertain_details, "uncertain_details"),
        )

        if (
            confirmed in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}
            and self.length_category is not None
            and self.length_category not in _NECKLACE_LENGTH_CATEGORIES
        ):
            raise ValueError(
                "length_category 必须是 choker、collarbone、upper_chest、long 或 None"
            )
        if confirmed is ProductType.RING:
            if self.ring_count != 1:
                raise ValueError("当前版本只支持单枚戒指")
            if self.hand_side is HandSide.UNKNOWN:
                raise ValueError("戒指生成前必须确认左右手")
            if self.finger_position is FingerPosition.UNKNOWN:
                raise ValueError("戒指生成前必须确认佩戴手指")
            if self.ring_wear_style is not RingWearStyle.FINGER_BASE:
                raise ValueError("当前版本只支持常规指根佩戴戒指")
            if (
                self.layer_count != 1
                or self.has_pendant
                or self.pendant_count != 0
                or self.pendant_layer is not None
                or self.is_independent_multi_item
            ):
                raise ValueError("戒指不得声明项链层数或吊坠结构")
        elif (
            self.ring_count != 0
            or self.hand_side is not HandSide.UNKNOWN
            or self.finger_position is not FingerPosition.UNKNOWN
            or self.ring_wear_style is not RingWearStyle.UNKNOWN
        ):
            raise ValueError("非戒指品类不得声明戒指结构")

        if confirmed is ProductType.PENDANT_NECKLACE and (
            not self.has_pendant
            or self.pendant_count < 1
            or self.pendant_layer is None
        ):
            raise ValueError(
                "带链吊坠必须声明完整主吊坠结构："
                "has_pendant=true、pendant_count 大于等于 1 且 pendant_layer 有效"
            )
        if confirmed is ProductType.NECKLACE and (
            self.has_pendant
            or self.pendant_count != 0
            or self.pendant_layer is not None
        ):
            raise ValueError(
                "普通项链不得声明主吊坠："
                "has_pendant=false、pendant_count=0 且 pendant_layer 为空"
            )
        if confirmed is ProductType.PENDANT_ONLY:
            if (
                not self.has_pendant
                or self.pendant_count < 1
                or self.pendant_layer is not None
            ):
                raise ValueError(
                    "无链独立吊坠必须声明 has_pendant=true、"
                    "pendant_count 大于等于 1 且 pendant_layer 为空"
                )
        elif not self.has_pendant:
            if self.pendant_count != 0:
                raise ValueError("has_pendant=false 时 pendant_count 必须为 0")
            if self.pendant_layer is not None:
                raise ValueError("has_pendant=false 时不得填写 pendant_layer")
        else:
            if self.pendant_count < 1:
                raise ValueError("has_pendant=true 时 pendant_count 必须大于等于 1")
            if self.pendant_layer is None:
                raise ValueError("has_pendant=true 时必须填写 pendant_layer")

        if confirmed in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}:
            if not 1 <= self.layer_count <= 3:
                raise ValueError("项链产品只支持 1 至 3 层")
            if self.is_independent_multi_item:
                raise ValueError("当前版本不支持多件独立项链组合叠戴")
        if self.pendant_layer is not None and self.pendant_layer > self.layer_count:
            raise ValueError("pendant_layer 不能大于 layer_count")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProductAnalysis":
        source = _ensure_mapping(data, "ProductAnalysis")
        raw_product_type = _required_string(source, "product_type")
        if "color_family" not in source:
            raise ValueError("color_family 必须是字符串列表")
        present_classification_fields = {
            field_name
            for field_name in _MODERN_CLASSIFICATION_FIELDS
            if field_name in source
        }
        if present_classification_fields and len(present_classification_fields) != len(
            _MODERN_CLASSIFICATION_FIELDS
        ):
            missing_fields = [
                field_name
                for field_name in _MODERN_CLASSIFICATION_FIELDS
                if field_name not in source
            ]
            raise ValueError(
                "现代分类契约不完整，缺少字段：" + "、".join(missing_fields)
            )
        is_modern_classification = bool(present_classification_fields)
        if is_modern_classification:
            for field_name in ("detected_product_type", "confirmed_product_type"):
                value = source[field_name]
                if not isinstance(value, (ProductType, str)) or not value.strip():
                    raise ValueError(f"{field_name} 必须是非空品类字符串")
            if "source_image_type" not in source:
                raise ValueError(
                    "现代分类记录的 source_image_type 必须显式提供，不得使用历史默认"
                )
            if normalize_product_type(source["confirmed_product_type"]) is ProductType.RING:
                missing_ring_fields = [
                    field_name
                    for field_name in (
                        "ring_count",
                        "hand_side",
                        "finger_position",
                        "ring_wear_style",
                    )
                    if field_name not in source
                ]
                if missing_ring_fields:
                    raise ValueError(
                        "戒指分析契约不完整，缺少字段："
                        + "、".join(missing_ring_fields)
                    )
        elif normalize_product_type(raw_product_type) is not ProductType.BRACELET:
            raise ValueError(
                "只有可确认的旧手串/手链记录可以使用历史默认；"
                "其他品类必须提供完整现代分类契约"
            )
        special_requirements = (
            _string_list(source["special_requirements"], "special_requirements")
            if "special_requirements" in source
            else ()
        )
        needs_full_front_display = (
            _parse_bool(source["needs_full_front_display"], "needs_full_front_display")
            if "needs_full_front_display" in source
            else True
        )
        return cls(
            product_type=raw_product_type,
            wear_position=_required_string(source, "wear_position"),
            visible_appearance=_required_string(source, "visible_appearance"),
            color_family=_string_list(source["color_family"], "color_family"),
            style_mood=_required_string(source, "style_mood"),
            composition=_required_string(source, "composition"),
            product_dimensions=ProductDimensions.from_dict(source.get("product_dimensions")),
            needs_full_front_display=needs_full_front_display,
            special_requirements=special_requirements,
            detected_product_type=(
                source["detected_product_type"] if is_modern_classification else None
            ),
            confirmed_product_type=(
                source["confirmed_product_type"] if is_modern_classification else None
            ),
            classification_confidence=(
                source["classification_confidence"]
                if is_modern_classification
                else "high"
            ),
            classification_evidence=(
                _string_list(
                    source["classification_evidence"], "classification_evidence"
                )
                if is_modern_classification
                else ()
            ),
            classification_source=(
                source["classification_source"]
                if is_modern_classification
                else "legacy_inferred"
            ),
            display_mode=source.get("display_mode", DisplayMode.WORN.value),
            source_image_type=source.get("source_image_type", SourceImageType.WORN_SOURCE.value),
            layer_count=(
                _json_int(source["layer_count"], "layer_count")
                if "layer_count" in source
                else 1
            ),
            length_category=source.get("length_category"),
            chain_or_strand_type=source.get("chain_or_strand_type"),
            has_pendant=(
                _json_bool(source["has_pendant"], "has_pendant")
                if "has_pendant" in source
                else False
            ),
            pendant_count=(
                _json_int(source["pendant_count"], "pendant_count")
                if "pendant_count" in source
                else 0
            ),
            pendant_layer=(
                _json_int(
                    source["pendant_layer"],
                    "pendant_layer",
                    allow_none=True,
                )
                if "pendant_layer" in source
                else None
            ),
            pendant_position=source.get("pendant_position"),
            pendant_orientation=source.get("pendant_orientation"),
            connection_structure=source.get("connection_structure"),
            symmetry=source.get("symmetry"),
            occluded_parts=_string_list(source.get("occluded_parts", []), "occluded_parts"),
            uncertain_details=_string_list(
                source.get("uncertain_details", []), "uncertain_details"
            ),
            is_independent_multi_item=(
                _json_bool(
                    source["is_independent_multi_item"],
                    "is_independent_multi_item",
                )
                if "is_independent_multi_item" in source
                else False
            ),
            ring_count=(
                _json_int(source["ring_count"], "ring_count")
                if "ring_count" in source
                else 0
            ),
            hand_side=source.get("hand_side", HandSide.UNKNOWN.value),
            finger_position=source.get(
                "finger_position", FingerPosition.UNKNOWN.value
            ),
            ring_wear_style=source.get(
                "ring_wear_style", RingWearStyle.UNKNOWN.value
            ),
        )

    @property
    def normalized_product_type(self) -> ProductType:
        return self.confirmed_product_type

    def is_supported_product(self) -> bool:
        return self.normalized_product_type in {
            ProductType.BRACELET,
            ProductType.NECKLACE,
            ProductType.PENDANT_NECKLACE,
            ProductType.RING,
        }


FidelityReviewStatus = Literal["pending", "confirmed", "corrected", "not_applicable"]
PendantPresence = Literal["present", "absent"]
PendantCreationPolicy = Literal["forbid"]


@dataclass(frozen=True)
class PendantSemantics:
    presence: PendantPresence
    count: int
    layer: int | None
    creation_policy: PendantCreationPolicy

    def __post_init__(self) -> None:
        if self.presence not in {"present", "absent"}:
            raise ValueError("pendant_semantics.presence 必须是 present/absent")
        if isinstance(self.count, bool) or not isinstance(self.count, int):
            raise ValueError("pendant_semantics.count 必须是整数 0 或 1")
        if self.count not in {0, 1}:
            raise ValueError("pendant_semantics.count 第一阶段只能是 0 或 1")
        if self.layer is not None and (
            isinstance(self.layer, bool)
            or not isinstance(self.layer, int)
            or not 1 <= self.layer <= 3
        ):
            raise ValueError("pendant_semantics.layer 必须是 null 或 1 至 3")
        if self.creation_policy != "forbid":
            raise ValueError("pendant_semantics.creation_policy 必须为 forbid")
        if self.presence == "absent" and (
            self.count != 0 or self.layer is not None
        ):
            raise ValueError("presence=absent 时 count 必须为 0 且 layer 必须为 null")
        if self.presence == "present" and (
            self.count != 1 or self.layer is None
        ):
            raise ValueError("presence=present 时 count 必须为 1 且 layer 必须为 1 至 3")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PendantSemantics":
        source = _ensure_mapping(data, "pendant_semantics")
        if "layer" not in source:
            raise ValueError("pendant_semantics.layer 必填；absent 时必须显式为 null")
        return cls(
            presence=_required_string(source, "presence"),  # type: ignore[arg-type]
            count=_json_int(source.get("count"), "count"),  # type: ignore[arg-type]
            layer=_json_int(source["layer"], "layer", allow_none=True),
            creation_policy=_required_string(  # type: ignore[arg-type]
                source, "creation_policy"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "presence": self.presence,
            "count": self.count,
            "layer": self.layer,
            "creation_policy": self.creation_policy,
        }


@dataclass(frozen=True)
class MustKeepConstraint:
    name: str
    source_text: str
    normalized_keyword: str
    location: str
    visual_shape: str
    relationship: str
    forbid: tuple[str, ...]
    qc_question: str

    def __post_init__(self) -> None:
        for field_name in (
            "name",
            "source_text",
            "normalized_keyword",
            "location",
            "visual_shape",
            "relationship",
            "qc_question",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_string_value(getattr(self, field_name), field_name),
            )
        forbid = _string_sequence(self.forbid, "forbid")
        if not forbid:
            raise ValueError("forbid 必须至少包含一个禁止变化项")
        object.__setattr__(self, "forbid", forbid)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MustKeepConstraint":
        source = _ensure_mapping(data, "MustKeepConstraint")
        return cls(
            name=_required_string(source, "name"),
            source_text=_required_string(source, "source_text"),
            normalized_keyword=_required_string(source, "normalized_keyword"),
            location=_required_string(source, "location"),
            visual_shape=_required_string(source, "visual_shape"),
            relationship=_required_string(source, "relationship"),
            forbid=_string_list(source.get("forbid"), "forbid"),
            qc_question=_required_string(source, "qc_question"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_text": self.source_text,
            "normalized_keyword": self.normalized_keyword,
            "location": self.location,
            "visual_shape": self.visual_shape,
            "relationship": self.relationship,
            "forbid": list(self.forbid),
            "qc_question": self.qc_question,
        }


@dataclass(frozen=True)
class ProductFidelityConstraints:
    schema_version: int
    source: dict[str, Any]
    detected_keywords: tuple[str, ...]
    must_keep: tuple[MustKeepConstraint, ...]
    must_not_change: tuple[str, ...]
    needs_user_review: bool
    detail_crop_recommended: bool
    review_status: FidelityReviewStatus
    pendant_semantics: PendantSemantics | None = None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise ValueError("schema_version 必须为 1 或 2")
        if self.schema_version not in {1, 2}:
            raise ValueError("schema_version 必须为 1 或 2")
        if self.schema_version == 1:
            if self.pendant_semantics is not None:
                raise ValueError("v1 的 pendant_semantics 必须为 null 或缺失")
        else:
            if self.pendant_semantics is None:
                raise ValueError("v2 的 pendant_semantics 必填")
            if not isinstance(self.pendant_semantics, PendantSemantics):
                object.__setattr__(
                    self,
                    "pendant_semantics",
                    PendantSemantics.from_dict(self.pendant_semantics),
                )
        source = _ensure_mapping(self.source, "source")
        object.__setattr__(self, "source", dict(source))
        object.__setattr__(
            self,
            "detected_keywords",
            _string_sequence(self.detected_keywords, "detected_keywords"),
        )
        must_keep_items: list[MustKeepConstraint] = []
        if not isinstance(self.must_keep, (list, tuple)):
            raise ValueError("must_keep 必须是列表")
        for item in self.must_keep:
            if isinstance(item, MustKeepConstraint):
                must_keep_items.append(item)
            else:
                must_keep_items.append(MustKeepConstraint.from_dict(item))
        object.__setattr__(self, "must_keep", tuple(must_keep_items))
        object.__setattr__(
            self,
            "must_not_change",
            _string_sequence(self.must_not_change, "must_not_change"),
        )
        object.__setattr__(
            self,
            "needs_user_review",
            _parse_bool(self.needs_user_review, "needs_user_review"),
        )
        object.__setattr__(
            self,
            "detail_crop_recommended",
            _parse_bool(self.detail_crop_recommended, "detail_crop_recommended"),
        )
        if self.review_status not in {
            "pending",
            "confirmed",
            "corrected",
            "not_applicable",
        }:
            raise ValueError("review_status 必须是 pending/confirmed/corrected/not_applicable")
        if self.review_status == "not_applicable" and must_keep_items:
            raise ValueError("review_status 为 not_applicable 时 must_keep 必须为空")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProductFidelityConstraints":
        source = _ensure_mapping(data, "ProductFidelityConstraints")
        if "schema_version" not in source:
            raise ValueError("schema_version 必须为 1 或 2")
        raw_schema_version = source.get("schema_version")
        if (
            isinstance(raw_schema_version, bool)
            or not isinstance(raw_schema_version, int)
            or raw_schema_version not in {1, 2}
        ):
            raise ValueError("schema_version 必须为 1 或 2")
        schema_version = _required_int(raw_schema_version, "schema_version")
        if schema_version == 1 and source.get("pendant_semantics") is not None:
            raise ValueError("v1 的 pendant_semantics 必须为 null 或缺失")
        if schema_version == 2 and "pendant_semantics" not in source:
            raise ValueError("v2 的 pendant_semantics 必填")
        pendant_semantics = (
            PendantSemantics.from_dict(source.get("pendant_semantics"))
            if schema_version == 2
            else None
        )
        return cls(
            schema_version=schema_version,
            source=_ensure_mapping(source.get("source"), "source"),
            detected_keywords=_string_list(source.get("detected_keywords"), "detected_keywords"),
            must_keep=tuple(
                MustKeepConstraint.from_dict(item)
                for item in _ensure_constraint_list(source.get("must_keep"))
            ),
            must_not_change=_string_list(source.get("must_not_change"), "must_not_change"),
            needs_user_review=_parse_bool(source.get("needs_user_review"), "needs_user_review"),
            detail_crop_recommended=_parse_bool(
                source.get("detail_crop_recommended"), "detail_crop_recommended"
            ),
            review_status=_required_string(source, "review_status"),  # type: ignore[arg-type]
            pendant_semantics=pendant_semantics,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": dict(self.source),
            "detected_keywords": list(self.detected_keywords),
            "must_keep": [item.to_dict() for item in self.must_keep],
            "must_not_change": list(self.must_not_change),
            "needs_user_review": self.needs_user_review,
            "detail_crop_recommended": self.detail_crop_recommended,
            "review_status": self.review_status,
        }
        if self.schema_version == 2:
            assert self.pendant_semantics is not None
            payload["pendant_semantics"] = self.pendant_semantics.to_dict()
        return payload

    def is_confirmed_for_generation(self) -> bool:
        return self.review_status in {"confirmed", "corrected", "not_applicable"}


def _ensure_constraint_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("must_keep 必须是列表")
    return value


def _reference_field_value(source: dict[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        value = source.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        return value
    return ""


@dataclass(frozen=True)
class ReferenceRow:
    index: int
    file_name: str
    relative_path: str
    absolute_path: Path
    width: int | None
    height: int | None
    size_mb: float | None
    purpose_category: str
    bracelet_applicability: str
    default_strategy: str
    style_category: str
    scene_keywords: str
    jewelry_type: str
    recommended_usage: str
    notes: str
    confidence: str
    file_exists: bool
    applicable_product_types: str = ""
    applicable_display_modes: str = ""
    framing: str = ""
    visible_body_regions: str = ""
    product_visibility: str = ""
    neck_visibility: str = ""
    collarbone_visibility: str = ""
    chest_visibility: str = ""
    hand_visibility: str = ""
    collar_type: str = ""
    clothing_occlusion_risk: str = ""
    hair_occlusion_risk: str = ""
    pose_keywords: str = ""
    mirror_relation: str = ""
    existing_jewelry: str = ""
    crop_risk: str = ""
    hand_side: str = ""
    visible_fingers: str = ""
    hand_orientation: str = ""
    ring_face_visibility: str = ""
    finger_separation: str = ""
    finger_occlusion_risk: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", _required_int(self.index, "index"))
        if not isinstance(self.absolute_path, (str, Path)):
            raise ValueError("absolute_path 必须是路径字符串或 Path")
        object.__setattr__(self, "absolute_path", Path(self.absolute_path))
        object.__setattr__(self, "width", _optional_int(self.width, "width"))
        object.__setattr__(self, "height", _optional_int(self.height, "height"))
        object.__setattr__(self, "size_mb", _optional_float(self.size_mb, "size_mb"))
        object.__setattr__(self, "file_exists", _parse_bool(self.file_exists, "file_exists"))
        for field_name in (
            "file_name",
            "relative_path",
            "purpose_category",
            "bracelet_applicability",
            "default_strategy",
            "style_category",
            "scene_keywords",
            "jewelry_type",
            "recommended_usage",
            "notes",
            "confidence",
            "applicable_product_types",
            "applicable_display_modes",
            "framing",
            "visible_body_regions",
            "product_visibility",
            "neck_visibility",
            "collarbone_visibility",
            "chest_visibility",
            "hand_visibility",
            "collar_type",
            "clothing_occlusion_risk",
            "hair_occlusion_risk",
            "pose_keywords",
            "mirror_relation",
            "existing_jewelry",
            "crop_risk",
            "hand_side",
            "visible_fingers",
            "hand_orientation",
            "ring_face_visibility",
            "finger_separation",
            "finger_occlusion_risk",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise ValueError(f"{field_name} 必须是字符串")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReferenceRow":
        source = _ensure_mapping(data, "ReferenceRow")
        return cls(
            index=source.get("index", source.get("序号")),
            file_name=source.get("file_name", source.get("文件名")),
            relative_path=source.get("relative_path", source.get("相对路径", "")),
            absolute_path=Path(source.get("absolute_path", source.get("绝对路径", ""))),
            width=source.get("width", source.get("宽度")),
            height=source.get("height", source.get("高度")),
            size_mb=source.get("size_mb", source.get("大小MB")),
            purpose_category=source.get("purpose_category", source.get("用途分类", "")),
            bracelet_applicability=source.get(
                "bracelet_applicability",
                source.get("手链手串适用性", source.get("手串适用性", "")),
            ),
            default_strategy=source.get(
                "default_strategy",
                source.get("默认使用策略", source.get("默认策略", "")),
            ),
            style_category=source.get("style_category", source.get("风格分类", "")),
            scene_keywords=source.get("scene_keywords", source.get("场景关键词", "")),
            jewelry_type=source.get("jewelry_type", source.get("饰品类型", "")),
            recommended_usage=source.get(
                "recommended_usage", source.get("推荐使用方式", "")
            ),
            notes=source.get("notes", source.get("备注", "")),
            confidence=source.get("confidence", source.get("判断置信度", "")),
            file_exists=source.get("file_exists", source.get("文件存在", False)),
            applicable_product_types=_reference_field_value(
                source,
                "applicable_product_types",
                "适用产品类型",
                "适用品类",
            ),
            applicable_display_modes=_reference_field_value(
                source, "applicable_display_modes", "适用展示模式"
            ),
            framing=_reference_field_value(
                source, "framing", "人物取景范围", "取景范围"
            ),
            visible_body_regions=_reference_field_value(
                source, "visible_body_regions", "可见身体区域"
            ),
            product_visibility=_reference_field_value(
                source,
                "product_visibility",
                "产品预计展示面积",
                "预计展示面积",
            ),
            neck_visibility=_reference_field_value(
                source, "neck_visibility", "颈部可见度"
            ),
            collarbone_visibility=_reference_field_value(
                source, "collarbone_visibility", "锁骨可见度"
            ),
            chest_visibility=_reference_field_value(
                source, "chest_visibility", "胸前可见度"
            ),
            hand_visibility=_reference_field_value(
                source, "hand_visibility", "手部可见度"
            ),
            collar_type=_reference_field_value(source, "collar_type", "衣领类型"),
            clothing_occlusion_risk=_reference_field_value(
                source, "clothing_occlusion_risk", "衣物遮挡风险"
            ),
            hair_occlusion_risk=_reference_field_value(
                source, "hair_occlusion_risk", "头发遮挡风险"
            ),
            pose_keywords=_reference_field_value(
                source, "pose_keywords", "姿势关键词"
            ),
            mirror_relation=_reference_field_value(
                source, "mirror_relation", "镜面关系"
            ),
            existing_jewelry=_reference_field_value(
                source, "existing_jewelry", "原有首饰类型", "原有首饰"
            ),
            crop_risk=_reference_field_value(source, "crop_risk", "裁切风险"),
            hand_side=_reference_field_value(source, "hand_side", "左右手"),
            visible_fingers=_reference_field_value(
                source, "visible_fingers", "可见手指"
            ),
            hand_orientation=_reference_field_value(
                source, "hand_orientation", "手部朝向"
            ),
            ring_face_visibility=_reference_field_value(
                source, "ring_face_visibility", "戒面可见度"
            ),
            finger_separation=_reference_field_value(
                source, "finger_separation", "手指分离度"
            ),
            finger_occlusion_risk=_reference_field_value(
                source, "finger_occlusion_risk", "手指遮挡风险"
            ),
        )

    def combined_text(self) -> str:
        parts = (
            self.purpose_category,
            self.bracelet_applicability,
            self.default_strategy,
            self.style_category,
            self.scene_keywords,
            self.jewelry_type,
            self.recommended_usage,
            self.notes,
            self.confidence,
            self.applicable_product_types,
            self.applicable_display_modes,
            self.framing,
            self.visible_body_regions,
            self.product_visibility,
            self.neck_visibility,
            self.collarbone_visibility,
            self.chest_visibility,
            self.hand_visibility,
            self.collar_type,
            self.clothing_occlusion_risk,
            self.hair_occlusion_risk,
            self.pose_keywords,
            self.mirror_relation,
            self.existing_jewelry,
            self.crop_risk,
            self.hand_side,
            self.visible_fingers,
            self.hand_orientation,
            self.ring_face_visibility,
            self.finger_separation,
            self.finger_occlusion_risk,
        )
        return " ".join(str(part) for part in parts if part)

    def metadata_dict(self) -> dict[str, Any]:
        metadata = {
            "index": self.index,
            "序号": self.index,
            "file_name": self.file_name,
            "文件名": self.file_name,
            "relative_path": self.relative_path,
            "相对路径": self.relative_path,
            "absolute_path": str(self.absolute_path),
            "绝对路径": str(self.absolute_path),
            "source_reference": str(self.absolute_path),
            "source_absolute_path": str(self.absolute_path),
            "source_relative_path": self.relative_path,
            "source_file_name": self.file_name,
            "width": self.width,
            "宽度": self.width,
            "height": self.height,
            "高度": self.height,
            "size_mb": self.size_mb,
            "大小MB": self.size_mb,
            "purpose_category": self.purpose_category,
            "用途分类": self.purpose_category,
            "bracelet_applicability": self.bracelet_applicability,
            "手链手串适用性": self.bracelet_applicability,
            "default_strategy": self.default_strategy,
            "默认使用策略": self.default_strategy,
            "style_category": self.style_category,
            "风格分类": self.style_category,
            "scene_keywords": self.scene_keywords,
            "场景关键词": self.scene_keywords,
            "jewelry_type": self.jewelry_type,
            "饰品类型": self.jewelry_type,
            "recommended_usage": self.recommended_usage,
            "推荐使用方式": self.recommended_usage,
            "notes": self.notes,
            "备注": self.notes,
            "confidence": self.confidence,
            "判断置信度": self.confidence,
            "file_exists": self.file_exists,
            "文件存在": self.file_exists,
        }
        generic_values = (
            self.applicable_product_types,
            self.applicable_display_modes,
            self.framing,
            self.visible_body_regions,
            self.product_visibility,
            self.neck_visibility,
            self.collarbone_visibility,
            self.chest_visibility,
            self.hand_visibility,
            self.collar_type,
            self.clothing_occlusion_risk,
            self.hair_occlusion_risk,
            self.pose_keywords,
            self.mirror_relation,
            self.existing_jewelry,
            self.crop_risk,
            self.hand_side,
            self.visible_fingers,
            self.hand_orientation,
            self.ring_face_visibility,
            self.finger_separation,
            self.finger_occlusion_risk,
        )
        if any(generic_values):
            metadata.update(
                {
                    "applicable_product_types": self.applicable_product_types,
                    "适用产品类型": self.applicable_product_types,
                    "applicable_display_modes": self.applicable_display_modes,
                    "适用展示模式": self.applicable_display_modes,
                    "framing": self.framing,
                    "人物取景范围": self.framing,
                    "visible_body_regions": self.visible_body_regions,
                    "可见身体区域": self.visible_body_regions,
                    "product_visibility": self.product_visibility,
                    "产品预计展示面积": self.product_visibility,
                    "neck_visibility": self.neck_visibility,
                    "颈部可见度": self.neck_visibility,
                    "collarbone_visibility": self.collarbone_visibility,
                    "锁骨可见度": self.collarbone_visibility,
                    "chest_visibility": self.chest_visibility,
                    "胸前可见度": self.chest_visibility,
                    "hand_visibility": self.hand_visibility,
                    "手部可见度": self.hand_visibility,
                    "collar_type": self.collar_type,
                    "衣领类型": self.collar_type,
                    "clothing_occlusion_risk": self.clothing_occlusion_risk,
                    "衣物遮挡风险": self.clothing_occlusion_risk,
                    "hair_occlusion_risk": self.hair_occlusion_risk,
                    "头发遮挡风险": self.hair_occlusion_risk,
                    "pose_keywords": self.pose_keywords,
                    "姿势关键词": self.pose_keywords,
                    "mirror_relation": self.mirror_relation,
                    "镜面关系": self.mirror_relation,
                    "existing_jewelry": self.existing_jewelry,
                    "原有首饰类型": self.existing_jewelry,
                    "crop_risk": self.crop_risk,
                    "裁切风险": self.crop_risk,
                    "hand_side": self.hand_side,
                    "左右手": self.hand_side,
                    "visible_fingers": self.visible_fingers,
                    "可见手指": self.visible_fingers,
                    "hand_orientation": self.hand_orientation,
                    "手部朝向": self.hand_orientation,
                    "ring_face_visibility": self.ring_face_visibility,
                    "戒面可见度": self.ring_face_visibility,
                    "finger_separation": self.finger_separation,
                    "手指分离度": self.finger_separation,
                    "finger_occlusion_risk": self.finger_occlusion_risk,
                    "手指遮挡风险": self.finger_occlusion_risk,
                }
            )
        return metadata


@dataclass(frozen=True)
class ScoredReference:
    row: ReferenceRow
    score: int
    rank: int
    reason: tuple[str, ...]
    risk: tuple[str, ...]
    ignored_reference_jewelry: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.row, ReferenceRow):
            raise ValueError("row 必须是 ReferenceRow")
        if isinstance(self.score, bool) or not isinstance(self.score, int):
            raise ValueError("score 必须是整数")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise ValueError("rank 必须是整数")
        if self.rank < 1:
            raise ValueError("rank 必须是大于等于 1 的整数")
        object.__setattr__(self, "reason", _string_sequence(self.reason, "reason"))
        object.__setattr__(self, "risk", _string_sequence(self.risk, "risk"))
        object.__setattr__(
            self,
            "ignored_reference_jewelry",
            _string_sequence(
                self.ignored_reference_jewelry, "ignored_reference_jewelry"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_reference": str(self.row.absolute_path),
            "score": self.score,
            "rank": self.rank,
            "reason": list(self.reason),
            "risk": list(self.risk),
            "ignored_reference_jewelry": list(self.ignored_reference_jewelry),
            "metadata": self.row.metadata_dict(),
        }


ReviewAction = Literal[
    "generate_rank_1",
    "generate_selected",
    "generate_multiple",
    "rerank",
    "manual_reference",
]


class _FrozenList(list[int]):
    def _readonly(self, *args: Any, **kwargs: Any) -> None:
        raise AttributeError("selected_ranks 不可修改")

    append = _readonly
    extend = _readonly
    insert = _readonly
    remove = _readonly
    pop = _readonly
    clear = _readonly
    sort = _readonly
    reverse = _readonly
    __setitem__ = _readonly
    __delitem__ = _readonly
    __iadd__ = _readonly
    __imul__ = _readonly


@dataclass(frozen=True)
class ProductConfirmationSnapshot:
    confirmed_product_type: ProductType | str
    source_image_type: SourceImageType | str
    display_mode: DisplayMode | str
    layer_count: int
    length_category: str | None
    has_pendant: bool
    pendant_count: int
    pendant_layer: int | None
    pendant_position: str | None
    pendant_orientation: str | None
    connection_structure: str | None
    is_independent_multi_item: bool
    ring_count: int = 0
    hand_side: HandSide | str = HandSide.UNKNOWN
    finger_position: FingerPosition | str = FingerPosition.UNKNOWN
    ring_wear_style: RingWearStyle | str = RingWearStyle.UNKNOWN

    def __post_init__(self) -> None:
        product_type = normalize_product_type(self.confirmed_product_type)
        is_explicit_unknown = (
            self.confirmed_product_type is ProductType.UNKNOWN
            or self.confirmed_product_type == ProductType.UNKNOWN.value
        )
        if product_type is ProductType.UNKNOWN and not is_explicit_unknown:
            raise ValueError("confirmed_product_type 必须是规范品类")
        object.__setattr__(self, "confirmed_product_type", product_type)
        try:
            object.__setattr__(self, "source_image_type", SourceImageType(self.source_image_type))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "source_image_type 必须是 worn_source/hand_held_source/flat_lay_source/unknown_source"
            ) from exc
        try:
            object.__setattr__(self, "display_mode", DisplayMode(self.display_mode))
        except (TypeError, ValueError) as exc:
            raise ValueError("display_mode 必须是 worn/hand_held") from exc

        layer_count = _json_int(self.layer_count, "layer_count")
        if layer_count is None or layer_count < 1:
            raise ValueError("layer_count 必须是大于等于 1 的 JSON 整数")
        pendant_count = _json_int(self.pendant_count, "pendant_count")
        if pendant_count is None or pendant_count < 0:
            raise ValueError("pendant_count 必须是大于等于 0 的 JSON 整数")
        pendant_layer = _json_int(self.pendant_layer, "pendant_layer", allow_none=True)
        if pendant_layer is not None and pendant_layer < 1:
            raise ValueError("pendant_layer 必须大于等于 1 或为 null")
        object.__setattr__(self, "layer_count", layer_count)
        object.__setattr__(self, "pendant_count", pendant_count)
        object.__setattr__(self, "pendant_layer", pendant_layer)
        object.__setattr__(self, "has_pendant", _json_bool(self.has_pendant, "has_pendant"))
        object.__setattr__(
            self,
            "is_independent_multi_item",
            _json_bool(self.is_independent_multi_item, "is_independent_multi_item"),
        )
        ring_count = _json_int(self.ring_count, "ring_count")
        if ring_count is None or ring_count < 0:
            raise ValueError("ring_count 必须是大于等于 0 的 JSON 整数")
        object.__setattr__(self, "ring_count", ring_count)
        try:
            object.__setattr__(self, "hand_side", HandSide(self.hand_side))
        except (TypeError, ValueError) as exc:
            raise ValueError("hand_side 必须是 left/right/unknown") from exc
        try:
            object.__setattr__(
                self,
                "finger_position",
                FingerPosition(self.finger_position),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "finger_position 必须是 thumb/index/middle/ring/little/unknown"
            ) from exc
        try:
            object.__setattr__(
                self,
                "ring_wear_style",
                RingWearStyle(self.ring_wear_style),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ring_wear_style 必须是 finger_base/midi/cross_finger/unknown"
            ) from exc
        for field_name in (
            "length_category",
            "pendant_position",
            "pendant_orientation",
            "connection_structure",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_non_empty_string(getattr(self, field_name), field_name),
            )

        if product_type in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}:
            if not 1 <= layer_count <= 3:
                raise ValueError("项链产品只支持 1 至 3 层")
            if self.is_independent_multi_item:
                raise ValueError("当前版本不支持多件独立项链组合叠戴")
            if (
                self.length_category is not None
                and self.length_category not in _NECKLACE_LENGTH_CATEGORIES
            ):
                raise ValueError(
                    "项链确认快照的 length_category 必须是 choker、collarbone、upper_chest、long 或 null"
                )
        if product_type is ProductType.PENDANT_NECKLACE and (
            not self.has_pendant or pendant_count < 1 or pendant_layer is None
        ):
            raise ValueError("带链吊坠确认快照必须包含完整吊坠结构")
        if product_type is ProductType.RING:
            if ring_count != 1:
                raise ValueError("戒指确认快照只支持单枚戒指")
            if self.hand_side is HandSide.UNKNOWN:
                raise ValueError("戒指确认快照必须确认左右手")
            if self.finger_position is FingerPosition.UNKNOWN:
                raise ValueError("戒指确认快照必须确认佩戴手指")
            if self.ring_wear_style is not RingWearStyle.FINGER_BASE:
                raise ValueError("戒指确认快照只支持常规指根佩戴")
            if (
                layer_count != 1
                or self.has_pendant
                or pendant_count != 0
                or pendant_layer is not None
                or self.is_independent_multi_item
            ):
                raise ValueError("戒指确认快照不得声明项链层数或吊坠结构")
        elif (
            ring_count != 0
            or self.hand_side is not HandSide.UNKNOWN
            or self.finger_position is not FingerPosition.UNKNOWN
            or self.ring_wear_style is not RingWearStyle.UNKNOWN
        ):
            raise ValueError("非戒指确认快照不得声明戒指结构")
        if product_type is ProductType.NECKLACE and (
            self.has_pendant or pendant_count != 0 or pendant_layer is not None
        ):
            raise ValueError("普通项链确认快照不得声明主吊坠")
        if pendant_layer is not None and pendant_layer > layer_count:
            raise ValueError("pendant_layer 不能大于 layer_count")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProductConfirmationSnapshot":
        source = _ensure_mapping(data, "ProductConfirmationSnapshot")
        required_fields = (
            "confirmed_product_type",
            "source_image_type",
            "display_mode",
            "layer_count",
            "length_category",
            "has_pendant",
            "pendant_count",
            "pendant_layer",
            "pendant_position",
            "pendant_orientation",
            "connection_structure",
            "is_independent_multi_item",
        )
        missing = [field_name for field_name in required_fields if field_name not in source]
        if missing:
            raise ValueError("确认快照不完整，缺少字段：" + "、".join(missing))
        product_type = normalize_product_type(source["confirmed_product_type"])
        ring_fields = (
            "ring_count",
            "hand_side",
            "finger_position",
            "ring_wear_style",
        )
        if product_type is ProductType.RING:
            missing_ring_fields = [
                field_name for field_name in ring_fields if field_name not in source
            ]
            if missing_ring_fields:
                raise ValueError(
                    "戒指确认快照不完整，缺少字段："
                    + "、".join(missing_ring_fields)
                )
        values = {field_name: source[field_name] for field_name in required_fields}
        values.update(
            {
                "ring_count": source.get("ring_count", 0),
                "hand_side": source.get("hand_side", HandSide.UNKNOWN.value),
                "finger_position": source.get(
                    "finger_position", FingerPosition.UNKNOWN.value
                ),
                "ring_wear_style": source.get(
                    "ring_wear_style", RingWearStyle.UNKNOWN.value
                ),
            }
        )
        return cls(**values)

    @classmethod
    def from_analysis(cls, analysis: ProductAnalysis) -> "ProductConfirmationSnapshot":
        if not isinstance(analysis, ProductAnalysis):
            raise ValueError("analysis 必须是 ProductAnalysis")
        return cls(
            confirmed_product_type=analysis.confirmed_product_type,
            source_image_type=analysis.source_image_type,
            display_mode=analysis.display_mode,
            layer_count=analysis.layer_count,
            length_category=analysis.length_category,
            has_pendant=analysis.has_pendant,
            pendant_count=analysis.pendant_count,
            pendant_layer=analysis.pendant_layer,
            pendant_position=analysis.pendant_position,
            pendant_orientation=analysis.pendant_orientation,
            connection_structure=analysis.connection_structure,
            is_independent_multi_item=analysis.is_independent_multi_item,
            ring_count=analysis.ring_count,
            hand_side=analysis.hand_side,
            finger_position=analysis.finger_position,
            ring_wear_style=analysis.ring_wear_style,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "confirmed_product_type": self.confirmed_product_type.value,
            "source_image_type": self.source_image_type.value,
            "display_mode": self.display_mode.value,
            "layer_count": self.layer_count,
            "length_category": self.length_category,
            "has_pendant": self.has_pendant,
            "pendant_count": self.pendant_count,
            "pendant_layer": self.pendant_layer,
            "pendant_position": self.pendant_position,
            "pendant_orientation": self.pendant_orientation,
            "connection_structure": self.connection_structure,
            "is_independent_multi_item": self.is_independent_multi_item,
        }
        if self.confirmed_product_type is ProductType.RING:
            data.update(
                {
                    "ring_count": self.ring_count,
                    "hand_side": self.hand_side.value,
                    "finger_position": self.finger_position.value,
                    "ring_wear_style": self.ring_wear_style.value,
                }
            )
        return data


@dataclass(frozen=True)
class ReviewDecision:
    action: ReviewAction
    selected_ranks: list[int]
    manual_reference: str | None = None
    fidelity_confirmed: bool = False
    fidelity_notes: str | None = None
    fidelity_constraints_path: str = "analysis/product_fidelity_constraints.json"
    confirmation_snapshot: ProductConfirmationSnapshot | None = None
    output_role: OutputRole | str | None = None
    reference_selection_constraints_path: str = (
        "analysis/reference_selection_constraints.json"
    )
    reference_selection_constraints_sha256: str | None = None

    def __post_init__(self) -> None:
        supported_actions = {
            "generate_rank_1",
            "generate_selected",
            "generate_multiple",
            "rerank",
            "manual_reference",
        }
        if self.action not in supported_actions:
            raise ValueError(f"不支持的 action: {self.action}")
        selected_ranks = self._parse_ranks(self.selected_ranks)
        if self.action == "generate_rank_1":
            if not selected_ranks:
                selected_ranks = _FrozenList([1])
            elif list(selected_ranks) != [1]:
                raise ValueError("generate_rank_1 只能使用 selected_ranks [1]")
        if self.action == "generate_selected" and len(selected_ranks) != 1:
            raise ValueError("generate_selected 只能使用一个 selected_ranks")
        if self.action == "generate_multiple" and len(selected_ranks) < 2:
            raise ValueError("generate_multiple 至少需要两个 selected_ranks")
        if self.action == "manual_reference":
            manual_reference = _required_string_value(
                self.manual_reference, "manual_reference"
            )
        else:
            manual_reference = _optional_non_empty_string(
                self.manual_reference, "manual_reference"
            )
        object.__setattr__(self, "selected_ranks", selected_ranks)
        object.__setattr__(self, "manual_reference", manual_reference)
        object.__setattr__(
            self,
            "fidelity_confirmed",
            _parse_bool(self.fidelity_confirmed, "fidelity_confirmed"),
        )
        object.__setattr__(
            self,
            "fidelity_notes",
            _optional_non_empty_string(self.fidelity_notes, "fidelity_notes"),
        )
        object.__setattr__(
            self,
            "fidelity_constraints_path",
            _required_string_value(
                self.fidelity_constraints_path, "fidelity_constraints_path"
            ),
        )
        snapshot = self.confirmation_snapshot
        if isinstance(snapshot, dict):
            snapshot = ProductConfirmationSnapshot.from_dict(snapshot)
        elif snapshot is not None and not isinstance(snapshot, ProductConfirmationSnapshot):
            raise ValueError("confirmation_snapshot 必须是产品确认快照或 null")
        object.__setattr__(self, "confirmation_snapshot", snapshot)
        object.__setattr__(self, "output_role", normalize_output_role(self.output_role))
        object.__setattr__(
            self,
            "reference_selection_constraints_path",
            _required_string_value(
                self.reference_selection_constraints_path,
                "reference_selection_constraints_path",
            ),
        )
        selection_sha256 = _optional_non_empty_string(
            self.reference_selection_constraints_sha256,
            "reference_selection_constraints_sha256",
        )
        if selection_sha256 is not None and (
            len(selection_sha256) != 64
            or any(character not in "0123456789abcdef" for character in selection_sha256)
        ):
            raise ValueError(
                "reference_selection_constraints_sha256 必须是 64 位小写十六进制摘要"
            )
        object.__setattr__(
            self,
            "reference_selection_constraints_sha256",
            selection_sha256,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReviewDecision":
        source = _ensure_mapping(data, "ReviewDecision")
        action = _required_string(source, "action")
        supported_actions = {
            "generate_rank_1",
            "generate_selected",
            "generate_multiple",
            "rerank",
            "manual_reference",
        }
        if action not in supported_actions:
            raise ValueError(f"不支持的 action: {action}")

        selected_ranks = cls._parse_ranks(source.get("selected_ranks"))
        if action == "generate_rank_1":
            if not selected_ranks:
                selected_ranks = _FrozenList([1])
            elif list(selected_ranks) != [1]:
                raise ValueError("generate_rank_1 只能使用 selected_ranks [1]")

        if action == "generate_selected" and len(selected_ranks) != 1:
            raise ValueError("generate_selected 只能使用一个 selected_ranks")
        if action == "generate_multiple" and len(selected_ranks) < 2:
            raise ValueError("generate_multiple 至少需要两个 selected_ranks")

        if action == "manual_reference":
            manual_reference = _required_string(source, "manual_reference")
        else:
            manual_reference = _optional_non_empty_string(
                source.get("manual_reference"), "manual_reference"
            )
        is_generation_action = action in {
            "generate_rank_1",
            "generate_selected",
            "generate_multiple",
        }
        fidelity_confirmed = (
            _json_bool(source["fidelity_confirmed"], "fidelity_confirmed")
            if "fidelity_confirmed" in source
            else False
        )
        if is_generation_action and not fidelity_confirmed:
            raise ValueError("fidelity_confirmed 必须为 true")
        fidelity_notes = _optional_non_empty_string(
            source.get("fidelity_notes"), "fidelity_notes"
        )
        fidelity_constraints_path = _optional_non_empty_string(
            source.get("fidelity_constraints_path"),
            "fidelity_constraints_path",
        ) or "analysis/product_fidelity_constraints.json"
        confirmation_snapshot = (
            ProductConfirmationSnapshot.from_dict(source["confirmation_snapshot"])
            if source.get("confirmation_snapshot") is not None
            else None
        )

        return cls(
            action=action,  # type: ignore[arg-type]
            selected_ranks=selected_ranks,
            manual_reference=manual_reference,
            fidelity_confirmed=fidelity_confirmed,
            fidelity_notes=fidelity_notes,
            fidelity_constraints_path=fidelity_constraints_path,
            confirmation_snapshot=confirmation_snapshot,
            output_role=source.get("output_role"),
            reference_selection_constraints_path=source.get(
                "reference_selection_constraints_path",
                "analysis/reference_selection_constraints.json",
            ),
            reference_selection_constraints_sha256=source.get(
                "reference_selection_constraints_sha256"
            ),
        )

    @staticmethod
    def _parse_ranks(value: Any) -> _FrozenList:
        if value is None:
            return _FrozenList()
        if not isinstance(value, (list, tuple)):
            raise ValueError("selected_ranks 必须是列表")
        ranks: list[int] = []
        for rank in value:
            if isinstance(rank, bool) or not isinstance(rank, int):
                raise ValueError("selected_ranks 必须包含整数")
            if rank < 1 or rank > 3:
                raise ValueError("selected_ranks 必须在 1..3 范围内")
            if rank in ranks:
                raise ValueError("selected_ranks 不能重复")
            ranks.append(rank)
        return _FrozenList(ranks)


QcCriticalFailure = Literal[
    "must_keep_failed",
    "category_mismatch",
    "core_structure_missing",
    "layer_count_mismatch",
    "length_category_mismatch",
    "pendant_layer_changed",
    "multi_layer_restructured",
    "auto_chain_added",
    "source_person_region_migrated",
    "severe_intersection",
    "ring_count_mismatch",
    "hand_side_mismatch",
    "finger_position_mismatch",
    "ring_structure_mismatch",
    "centerpiece_mismatch",
    "ring_contact_error",
    "finger_deformation",
    "source_hand_leakage",
]

_QC_CRITICAL_FAILURES = {
    "must_keep_failed",
    "category_mismatch",
    "core_structure_missing",
    "layer_count_mismatch",
    "length_category_mismatch",
    "pendant_layer_changed",
    "multi_layer_restructured",
    "auto_chain_added",
    "source_person_region_migrated",
    "severe_intersection",
    "ring_count_mismatch",
    "hand_side_mismatch",
    "finger_position_mismatch",
    "ring_structure_mismatch",
    "centerpiece_mismatch",
    "ring_contact_error",
    "finger_deformation",
    "source_hand_leakage",
}

_QC_REJECT_FAILURES = {
    "category_mismatch",
    "core_structure_missing",
    "multi_layer_restructured",
    "auto_chain_added",
    "severe_intersection",
    "ring_count_mismatch",
    "finger_position_mismatch",
    "ring_structure_mismatch",
    "centerpiece_mismatch",
    "source_hand_leakage",
}

_QC_REJECT_FAILURE_TERMS = (
    "品类错误",
    "品类不一致",
    "核心结构缺失",
    "核心配件缺失",
    "多层关系重组",
    "层间关系重组",
    "自动补链",
    "凭空补链",
    "严重穿模",
    "严重穿透",
    "戒指数量错误",
    "佩戴手指错误",
    "戒指结构错误",
    "戒面错误",
    "主石错误",
    "产品图手部迁移",
)


@dataclass(frozen=True)
class QcResult:
    status: Literal["pass", "rerun", "reject"]
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    notes: str
    fidelity_checks: tuple["FidelityCheck", ...] = field(default_factory=tuple)
    checklist_checks: tuple["QcChecklistCheck", ...] = field(default_factory=tuple)
    critical_failures: tuple[QcCriticalFailure, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in {"pass", "rerun", "reject"}:
            raise ValueError("status 必须是 pass/rerun/reject")
        object.__setattr__(self, "passed", _string_sequence(self.passed, "passed"))
        object.__setattr__(self, "failed", _string_sequence(self.failed, "failed"))
        if not isinstance(self.notes, str):
            raise ValueError("notes 必须是字符串")
        if self.status == "pass" and self.failed:
            raise ValueError("status 为 pass 时 failed 必须为空")
        failure_text = " ".join(self.failed)
        checks = _parse_fidelity_checks(self.fidelity_checks)
        if self.status == "pass" and any(check.result != "pass" for check in checks):
            raise ValueError("must_keep 关键识别点失败时不得标记为 pass")
        checklist_checks = _parse_qc_checklist_checks(self.checklist_checks)
        if self.status == "pass" and any(
            check.result != "pass" for check in checklist_checks
        ):
            raise ValueError("checklist_checks 存在未通过项时不得标记为 pass")
        critical_failures = _parse_qc_critical_failures(self.critical_failures)
        if self.status == "pass" and critical_failures:
            raise ValueError("存在关键 QC 失败时不得标记为 pass")
        if self.status != "reject" and (
            any(failure in _QC_REJECT_FAILURES for failure in critical_failures)
            or _contains_any_text(failure_text, _QC_REJECT_FAILURE_TERMS)
        ):
            raise ValueError("品类、结构、自动补链或严重穿模错误必须标记为 reject")
        object.__setattr__(self, "fidelity_checks", checks)
        object.__setattr__(self, "checklist_checks", checklist_checks)
        object.__setattr__(self, "critical_failures", critical_failures)


FidelityCheckResult = Literal["pass", "rerun", "fail"]


@dataclass(frozen=True)
class FidelityCheck:
    name: str
    question: str
    result: FidelityCheckResult
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_string_value(self.name, "name"))
        object.__setattr__(
            self,
            "question",
            _required_string_value(self.question, "question"),
        )
        if self.result not in {"pass", "rerun", "fail"}:
            raise ValueError("fidelity_checks.result 必须是 pass/rerun/fail")
        if not isinstance(self.notes, str):
            raise ValueError("fidelity_checks.notes 必须是字符串")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FidelityCheck":
        source = _ensure_mapping(data, "FidelityCheck")
        notes = source.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError("fidelity_checks.notes 必须是字符串或 null")
        return cls(
            name=_required_string(source, "name"),
            question=_required_string(source, "question"),
            result=_required_string(source, "result"),  # type: ignore[arg-type]
            notes="" if notes is None else notes,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "question": self.question,
            "result": self.result,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class QcChecklistCheck:
    id: str
    question: str
    result: FidelityCheckResult
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_string_value(self.id, "id"))
        object.__setattr__(
            self,
            "question",
            _required_string_value(self.question, "question"),
        )
        if self.result not in {"pass", "rerun", "fail"}:
            raise ValueError("checklist_checks.result 必须是 pass/rerun/fail")
        if not isinstance(self.notes, str):
            raise ValueError("checklist_checks.notes 必须是字符串")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "QcChecklistCheck":
        source = _ensure_mapping(data, "QcChecklistCheck")
        notes = source.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError("checklist_checks.notes 必须是字符串或 null")
        return cls(
            id=_required_string(source, "id"),
            question=_required_string(source, "question"),
            result=_required_string(source, "result"),  # type: ignore[arg-type]
            notes="" if notes is None else notes,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "question": self.question,
            "result": self.result,
            "notes": self.notes,
        }


def _parse_fidelity_checks(value: Any) -> tuple[FidelityCheck, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("fidelity_checks 必须是列表")
    checks: list[FidelityCheck] = []
    for item in value:
        if isinstance(item, FidelityCheck):
            checks.append(item)
        else:
            checks.append(FidelityCheck.from_dict(item))
    return tuple(checks)


def _parse_qc_checklist_checks(value: Any) -> tuple[QcChecklistCheck, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("checklist_checks 必须是列表")
    checks: list[QcChecklistCheck] = []
    for item in value:
        if isinstance(item, QcChecklistCheck):
            checks.append(item)
        else:
            checks.append(QcChecklistCheck.from_dict(item))
    return tuple(checks)


def _parse_qc_critical_failures(value: Any) -> tuple[QcCriticalFailure, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("critical_failures 必须是列表")
    failures: list[QcCriticalFailure] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("critical_failures 只能包含非空字符串")
        normalized = item.strip()
        if normalized not in _QC_CRITICAL_FAILURES:
            raise ValueError(f"critical_failures 包含未知错误代码：{normalized}")
        if normalized in failures:
            raise ValueError("critical_failures 不能包含重复错误代码")
        failures.append(normalized)  # type: ignore[arg-type]
    return tuple(failures)


def _contains_any_text(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)
