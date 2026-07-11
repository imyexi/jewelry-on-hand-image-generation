from jewelry_on_hand.category_policies.base import (
    CategoryPolicy,
    PromptFragments,
    SHARED_BASIC_QC_ITEMS,
)
from jewelry_on_hand.display_modes import DisplayMode
from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.product_types import ProductType


RING_IMAGE_ONE_ROLE = (
    "内部图1：自动参考图，只提供手部姿势、手模、构图、光线和场景；"
    "内部图1中的戒指必须移除且不提供产品身份。"
)

RING_BASIC_QC_ITEMS = (
    "画面中只有一枚目标戒指",
    "戒指位于确认后的左右手和目标手指根部",
    "戒圈、戒面、主石、镶嵌和装饰排列与产品图可见结构一致",
    "戒圈自然环绕手指且前后遮挡、接触和阴影真实",
    "没有迁移产品图中的手、皮肤、指甲、掌纹或背景局部",
)


def _build_ring_prompt_fragments(product: ProductAnalysis) -> PromptFragments:
    hand_name = product.hand_side.display_name
    finger_name = product.finger_position.display_name
    return PromptFragments(
        image_one_role=RING_IMAGE_ONE_ROLE,
        category_fidelity=(
            "只生成一枚目标戒指；戒圈粗细、开口、戒面、主石、镶嵌、颜色、"
            "朝向和装饰排列必须与内部图2肉眼可见结构一致。"
        ),
        display_mode=(
            f"真人佩戴：戒指必须佩戴在已确认的{hand_name}{finger_name}根部，"
            "不得静默换手、换指或改成指关节/跨指佩戴。"
        ),
        occlusion_physics=(
            "戒圈必须自然环绕手指，前侧可见部分与背侧遮挡关系真实，并具有"
            "合理接触和阴影；不得悬浮、贴片、嵌入皮肤或穿透手指。"
        ),
        prohibitions=(
            "不得迁移内部图2中的手、皮肤、指甲、掌纹或背景局部；"
            "不得把不可见戒圈背面或镶嵌背面补写成确定结构。"
        ),
    )


RING_POLICY = CategoryPolicy(
    product_type=ProductType.RING,
    supported_modes=frozenset({DisplayMode.WORN}),
    max_layer_count=1,
    basic_qc_items=SHARED_BASIC_QC_ITEMS + RING_BASIC_QC_ITEMS,
    mode_qc_items={DisplayMode.WORN: RING_BASIC_QC_ITEMS},
    prompt_fragment_builder=_build_ring_prompt_fragments,
)


__all__ = ["RING_BASIC_QC_ITEMS", "RING_IMAGE_ONE_ROLE", "RING_POLICY"]
