from jewelry_on_hand.category_policies.base import CategoryPolicy
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.product_types import ProductType


NECKLACE_POLICY = CategoryPolicy(
    product_type=ProductType.NECKLACE,
    supported_modes=frozenset({DisplayMode.WORN, DisplayMode.HAND_HELD}),
    max_layer_count=3,
    basic_qc_items=(
        "产品品类与产品图一致",
        "项链层数、顺序和相对落差正确",
        "链条与身体或手部关系自然",
    ),
)

PENDANT_NECKLACE_POLICY = CategoryPolicy(
    product_type=ProductType.PENDANT_NECKLACE,
    supported_modes=frozenset({DisplayMode.WORN, DisplayMode.HAND_HELD}),
    max_layer_count=3,
    basic_qc_items=(
        "产品品类与产品图一致",
        "项链层数、顺序和相对落差正确",
        "吊坠形态、连接关系和所在层正确",
    ),
)
