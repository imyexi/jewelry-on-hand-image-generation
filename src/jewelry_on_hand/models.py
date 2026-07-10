from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from jewelry_on_hand.display_modes import DisplayMode, SourceImageType
from jewelry_on_hand.product_types import ProductType, normalize_product_type


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
        if not self.has_pendant:
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
            product_type=_required_string(source, "product_type"),
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
        )

    @property
    def normalized_product_type(self) -> ProductType:
        return self.confirmed_product_type

    def is_supported_product(self) -> bool:
        return self.normalized_product_type in {
            ProductType.BRACELET,
            ProductType.NECKLACE,
            ProductType.PENDANT_NECKLACE,
        }


FidelityReviewStatus = Literal["pending", "confirmed", "corrected", "not_applicable"]


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

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schema_version 必须为 1")
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
            raise ValueError("schema_version 必须为 1")
        return cls(
            schema_version=_required_int(source.get("schema_version"), "schema_version"),
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
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": dict(self.source),
            "detected_keywords": list(self.detected_keywords),
            "must_keep": [item.to_dict() for item in self.must_keep],
            "must_not_change": list(self.must_not_change),
            "needs_user_review": self.needs_user_review,
            "detail_crop_recommended": self.detail_crop_recommended,
            "review_status": self.review_status,
        }

    def is_confirmed_for_generation(self) -> bool:
        return self.review_status in {"confirmed", "corrected", "not_applicable"}


def _ensure_constraint_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("must_keep 必须是列表")
    return value


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
        )
        return " ".join(str(part) for part in parts if part)

    def metadata_dict(self) -> dict[str, Any]:
        return {
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
            "用途分类": self.purpose_category,
            "风格分类": self.style_category,
            "场景关键词": self.scene_keywords,
            "饰品类型": self.jewelry_type,
            "推荐使用方式": self.recommended_usage,
            "备注": self.notes,
            "判断置信度": self.confidence,
        }


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
class ReviewDecision:
    action: ReviewAction
    selected_ranks: list[int]
    manual_reference: str | None = None
    fidelity_confirmed: bool = False
    fidelity_notes: str | None = None
    fidelity_constraints_path: str = "analysis/product_fidelity_constraints.json"

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
        fidelity_confirmed = _optional_bool(
            source.get("fidelity_confirmed"), "fidelity_confirmed"
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

        return cls(
            action=action,  # type: ignore[arg-type]
            selected_ranks=selected_ranks,
            manual_reference=manual_reference,
            fidelity_confirmed=fidelity_confirmed,
            fidelity_notes=fidelity_notes,
            fidelity_constraints_path=fidelity_constraints_path,
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


@dataclass(frozen=True)
class QcResult:
    status: Literal["pass", "rerun", "reject"]
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    notes: str
    fidelity_checks: tuple["FidelityCheck", ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in {"pass", "rerun", "reject"}:
            raise ValueError("status 必须是 pass/rerun/reject")
        object.__setattr__(self, "passed", _string_sequence(self.passed, "passed"))
        object.__setattr__(self, "failed", _string_sequence(self.failed, "failed"))
        if not isinstance(self.notes, str):
            raise ValueError("notes 必须是字符串")
        checks = _parse_fidelity_checks(self.fidelity_checks)
        if self.status == "pass" and any(check.result != "pass" for check in checks):
            raise ValueError("must_keep 关键识别点失败时不得标记为 pass")
        object.__setattr__(self, "fidelity_checks", checks)


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
        return cls(
            name=_required_string(source, "name"),
            question=_required_string(source, "question"),
            result=_required_string(source, "result"),  # type: ignore[arg-type]
            notes="" if source.get("notes") is None else str(source.get("notes")),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
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
