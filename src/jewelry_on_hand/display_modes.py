from __future__ import annotations

from enum import Enum

from jewelry_on_hand.product_types import ProductType


class DisplayMode(str, Enum):
    WORN = "worn"
    HAND_HELD = "hand_held"


class SourceImageType(str, Enum):
    WORN_SOURCE = "worn_source"
    HAND_HELD_SOURCE = "hand_held_source"
    FLAT_LAY_SOURCE = "flat_lay_source"
    UNKNOWN_SOURCE = "unknown_source"


_SUPPORTED_MODES = {
    ProductType.BRACELET: frozenset({DisplayMode.WORN}),
    ProductType.RING: frozenset({DisplayMode.WORN}),
    ProductType.NECKLACE: frozenset({DisplayMode.WORN, DisplayMode.HAND_HELD}),
    ProductType.PENDANT_NECKLACE: frozenset(
        {DisplayMode.WORN, DisplayMode.HAND_HELD}
    ),
}

_DISPLAY_MODE_NAMES = {
    DisplayMode.WORN: "真人佩戴",
    DisplayMode.HAND_HELD: "手持展示",
}


def _require_product_type(product_type: ProductType) -> None:
    if not isinstance(product_type, ProductType):
        raise ValueError("产品品类必须使用 ProductType 枚举")


def default_display_mode(product_type: ProductType) -> DisplayMode:
    _require_product_type(product_type)
    if product_type is ProductType.PENDANT_ONLY:
        raise ValueError("无链独立吊坠当前不支持生成，无法确定默认展示模式")
    if product_type is ProductType.UNKNOWN:
        raise ValueError("产品品类无法识别，无法确定默认展示模式")
    return DisplayMode.WORN


def validate_product_mode(
    product_type: ProductType,
    display_mode: DisplayMode,
    source_image_type: SourceImageType,
) -> None:
    _require_product_type(product_type)
    if not isinstance(display_mode, DisplayMode):
        raise ValueError("展示模式必须使用 DisplayMode 枚举")
    if not isinstance(source_image_type, SourceImageType):
        raise ValueError("输入图类型必须使用 SourceImageType 枚举")

    if product_type is ProductType.UNKNOWN:
        raise ValueError("产品品类无法识别，必须先人工纠正")
    if product_type is ProductType.PENDANT_ONLY:
        raise ValueError("当前版本不支持无链独立吊坠，且禁止自动补链")
    if source_image_type is SourceImageType.FLAT_LAY_SOURCE:
        raise ValueError(
            f"{product_type.display_name}的输入图类型为白底或平铺产品图，不兼容："
            "第一阶段只接受真人佩戴原图"
        )
    if source_image_type is not SourceImageType.WORN_SOURCE:
        raise ValueError(
            f"{product_type.display_name}的输入图类型 {source_image_type.value} 不兼容："
            "第一阶段只接受真人佩戴原图"
        )
    if display_mode not in _SUPPORTED_MODES[product_type]:
        raise ValueError(
            f"{product_type.display_name}与{_DISPLAY_MODE_NAMES[display_mode]}模式不兼容"
        )
