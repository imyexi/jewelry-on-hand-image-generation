from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import validate_product_mode
from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.run_paths import read_json


class UnsupportedProductError(ValueError):
    """当前产品品类或输入模式不在自动流程支持范围内。"""


def build_analysis_prompt(product_image: str | Path, dimensions: dict[str, Any] | None = None) -> str:
    dimension_note = "未提供尺寸信息。"
    if dimensions is not None:
        dimension_note = json.dumps(dimensions, ensure_ascii=False, indent=2)

    return f"""你是珠宝产品图分析助手。请分析用户提供的产品上手原图，并只输出严格 JSON。

用户输入图路径：
{Path(product_image)}

重要边界：
- 产品分析 JSON 是系统内部产物，不是用户第二输入；用户只提供产品上手原图。
- 当前自动流程支持手串/手链、普通项链、带链吊坠和戒指；无链独立吊坠只能识别，禁止自动补链或进入生成。
- 第一阶段只接受真人佩戴原图；source_image_type 必须如实描述输入图，白底、平铺、纯手持或未知来源会在加载阶段被拒绝。
- product_type 保留肉眼可见的中文品类描述；detected_product_type 和 confirmed_product_type 使用 bracelet、necklace、pendant_necklace、pendant_only、ring、unknown 之一。
- 分类明确时 confirmed_product_type 与 detected_product_type 一致；证据不足时使用 unknown，并在 classification_evidence 和 uncertain_details 记录原因。
- display_mode 是后续生成展示模式，不等于 source_image_type。手串/手链只允许 worn；普通项链和带链吊坠的默认 display_mode 也是 worn，只有用户在后续人工确认中主动切换，才可改为 hand_held。
- visible_appearance 必须只描述肉眼可见外观，包括形状、颜色、排列、透明度、光泽、配件和可见纹理。
- 必须特别写出局部关键结构，例如随形、跑环、双尖、回纹、貔貅、桶珠、雕刻、吊坠、流苏、链坠。
- 只描述肉眼可见外观，不要根据常识或商品名补充图片中看不到的信息。
- 不要猜测材质名，例如不要写水晶、玛瑙、玉石、翡翠、银、金、珍珠等无法仅凭图片确定的材质。
- 尺寸信息只作为比例参考，不能覆盖、改写或替代可见外观判断。
- 普通项链和带链吊坠的 layer_count 只能为 1 至 3；length_category 只能为 choker、collarbone、upper_chest、long 或 null。
- 带链吊坠必须填写 has_pendant=true、pendant_count 大于等于 1 和有效 pendant_layer；普通项链必须填写 false、0、null。pendant_layer 不得大于 layer_count。
- 无链独立吊坠没有链层，必须填写 has_pendant=true、pendant_count 大于等于 1、pendant_layer=null；系统只解析并在加载阶段明确拒绝，禁止自动补链。
- 多件独立项链组合叠戴必须标记 is_independent_multi_item=true，当前阶段会拒绝生成。
- 戒指只允许 ring_count=1、hand_side 为 left/right、finger_position 为 thumb/index/middle/ring/little、ring_wear_style=finger_base；多枚、叠戴、指关节戒和跨指戒当前会拒绝生成。
- 看不清的扣头、背面和遮挡结构不要臆测，分别写入 occluded_parts 和 uncertain_details。

尺寸信息（仅比例参考）：
{dimension_note}

请输出一个 JSON 对象，字段必须完整且字段名固定：
{{
  "product_type": "肉眼可见的中文品类描述",
  "detected_product_type": "bracelet",
  "confirmed_product_type": "bracelet",
  "classification_confidence": "high",
  "classification_evidence": ["支持分类的肉眼可见证据"],
  "classification_source": "auto_confirmed",
  "display_mode": "worn",
  "source_image_type": "worn_source",
  "wear_position": "佩戴位置，例如手腕、颈部或锁骨",
  "visible_appearance": "只描述肉眼可见外观，不写材质猜测",
  "color_family": ["主要可见颜色"],
  "style_mood": "整体可见风格氛围",
  "composition": "图片构图和产品展示方式",
  "product_dimensions": {{
    "length_mm": null,
    "width_mm": null,
    "height_mm": null,
    "bead_diameter_mm": null,
    "dimension_source": null
  }},
  "needs_full_front_display": true,
  "special_requirements": [],
  "layer_count": 1,
  "length_category": null,
  "chain_or_strand_type": null,
  "has_pendant": false,
  "pendant_count": 0,
  "pendant_layer": null,
  "pendant_position": null,
  "pendant_orientation": null,
  "connection_structure": null,
  "symmetry": null,
  "occluded_parts": [],
  "uncertain_details": [],
  "is_independent_multi_item": false,
  "ring_count": 0,
  "hand_side": "unknown",
  "finger_position": "unknown",
  "ring_wear_style": "unknown"
}}

输出要求：
- 只输出 JSON，不要输出 Markdown、解释或额外文字。
- 不确定的尺寸字段填 null；如果引用了输入尺寸，在 dimension_source 写明“用户提供尺寸信息”。
- 不适用或肉眼无法确认的可选结构字段填 null，不要删除字段。
- 即使识别为无链独立吊坠、其他品类或 unknown，也要如实输出完整 JSON，交由加载阶段明确拒绝。"""


def load_product_analysis(path: str | Path) -> ProductAnalysis:
    analysis = ProductAnalysis.from_dict(read_json(path))
    if not analysis.is_supported_product():
        if analysis.normalized_product_type.value == "pendant_only":
            raise UnsupportedProductError("当前版本不支持无链独立吊坠，且禁止自动补链")
        raise UnsupportedProductError("当前支持手串/手链、普通项链、带链吊坠和戒指；产品品类无法识别或不在当前支持范围内")
    try:
        validate_product_mode(
            analysis.normalized_product_type,
            analysis.display_mode,
            analysis.source_image_type,
        )
        get_category_policy(analysis.normalized_product_type).validate_generation(
            layer_count=analysis.layer_count,
            is_independent_multi_item=analysis.is_independent_multi_item,
        )
    except ValueError as exc:
        raise UnsupportedProductError(str(exc)) from exc
    return analysis
