from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.product_fidelity import build_product_fidelity_constraints
from jewelry_on_hand.run_paths import read_json


class UnsupportedProductError(ValueError):
    """当前产品品类不在第一版自动流程支持范围内。"""


def build_analysis_prompt(product_image: str | Path, dimensions: dict[str, Any] | None = None) -> str:
    dimension_note = "未提供尺寸信息。"
    if dimensions is not None:
        dimension_note = json.dumps(dimensions, ensure_ascii=False, indent=2)

    return f"""你是珠宝产品图分析助手。请分析用户提供的产品上手原图，并只输出严格 JSON。

用户输入图路径：
{Path(product_image)}

重要边界：
- 产品分析 JSON 是系统内部产物，不是用户第二输入；用户只提供产品上手原图。
- 第一版只支持手串/手链产品图；如果不是手串/手链，也仍按可见内容填写 product_type。
- visible_appearance 必须只描述肉眼可见外观，包括形状、颜色、排列、透明度、光泽、配件和可见纹理。
- 必须特别写出局部关键结构，例如随形、跑环、双尖、回纹、貔貅、桶珠、雕刻、吊坠、流苏、链坠。
- 只描述肉眼可见外观，不要根据常识或商品名补充图片中看不到的信息。
- 不要猜测材质名，例如不要写水晶、玛瑙、玉石、翡翠、银、金、珍珠等无法仅凭图片确定的材质。
- 尺寸信息只作为比例参考，不能覆盖、改写或替代可见外观判断。

尺寸信息（仅比例参考）：
{dimension_note}

请输出一个 JSON 对象，字段必须完整且字段名固定：
{{
  "product_type": "手串/手链/其他肉眼可见品类",
  "wear_position": "佩戴位置，例如手腕",
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
  "special_requirements": []
}}

输出要求：
- 只输出 JSON，不要输出 Markdown、解释或额外文字。
- 不确定的尺寸字段填 null；如果引用了输入尺寸，在 dimension_source 写明“用户提供尺寸信息”。
- product_type 第一版只有包含“手链”或“手串”时才会进入后续流程。"""


def load_product_analysis(path: str | Path) -> ProductAnalysis:
    analysis = ProductAnalysis.from_dict(read_json(path))
    if not analysis.is_supported_product():
        raise UnsupportedProductError("当前版本只支持手串/手链产品图")
    return analysis
