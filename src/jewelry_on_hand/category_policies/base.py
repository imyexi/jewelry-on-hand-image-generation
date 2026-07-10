from __future__ import annotations

from dataclasses import dataclass

from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType


SHARED_BASIC_QC_ITEMS = ("禁止推断不可见扣头或背面结构",)


@dataclass(frozen=True)
class CategoryPolicy:
    product_type: ProductType
    supported_modes: frozenset[DisplayMode]
    max_layer_count: int
    basic_qc_items: tuple[str, ...]

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
