from jewelry_on_hand.category_policies.base import CategoryPolicy
from jewelry_on_hand.category_policies.bracelet import BRACELET_POLICY
from jewelry_on_hand.category_policies.necklace import (
    NECKLACE_POLICY,
    PENDANT_NECKLACE_POLICY,
)
from jewelry_on_hand.category_policies.pendant import PENDANT_ONLY_POLICY
from jewelry_on_hand.product_types import ProductType


_POLICIES = {
    ProductType.BRACELET: BRACELET_POLICY,
    ProductType.NECKLACE: NECKLACE_POLICY,
    ProductType.PENDANT_NECKLACE: PENDANT_NECKLACE_POLICY,
    ProductType.PENDANT_ONLY: PENDANT_ONLY_POLICY,
}


def get_category_policy(product_type: ProductType) -> CategoryPolicy:
    if not isinstance(product_type, ProductType):
        raise ValueError("产品品类必须使用 ProductType 枚举")
    if product_type is ProductType.UNKNOWN:
        raise ValueError("产品品类无法识别，必须先人工纠正")
    return _POLICIES[product_type]


__all__ = ["CategoryPolicy", "get_category_policy"]
