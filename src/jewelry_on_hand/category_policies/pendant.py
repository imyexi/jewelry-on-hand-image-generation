from jewelry_on_hand.category_policies.base import CategoryPolicy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType


PENDANT_ONLY_POLICY = CategoryPolicy(
    product_type=ProductType.PENDANT_ONLY,
    supported_modes=frozenset(),
    max_layer_count=1,
    basic_qc_items=(
        "保持无链独立吊坠品类判断",
        "禁止自动补链",
    ),
)
