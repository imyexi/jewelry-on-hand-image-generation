from jewelry_on_hand.category_policies.base import CategoryPolicy, SHARED_BASIC_QC_ITEMS
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType


BRACELET_POLICY = CategoryPolicy(
    product_type=ProductType.BRACELET,
    supported_modes=frozenset({DisplayMode.WORN}),
    max_layer_count=1,
    basic_qc_items=SHARED_BASIC_QC_ITEMS
    + (
        "产品品类与产品图一致",
        "产品关键结构完整",
        "手腕佩戴关系自然",
    ),
)
