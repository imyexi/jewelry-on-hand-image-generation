# 产品分析 JSON Schema 说明

产品分析 JSON 是系统内部产物，不是用户第二输入。用户只提供产品上手原图；系统基于原图生成结构化分析结果，供后续参考图选择、生成提示词和质检流程使用。

产品分析 JSON 只负责描述整体可见外观；它不能替代 `analysis/product_fidelity_constraints.json`。凡是随形、跑环、双尖、回纹、貔貅、桶珠、雕刻、吊坠、流苏、链坠等会影响货号识别的局部结构，必须同步写入产品保真约束文件，供 review、prompt 和 QC 使用。

## 输入边界

- 用户输入：一张产品上手原图。
- 可选尺寸：仅作为比例参考，不能覆盖、改写或替代图片中的可见外观。
- 第一版品类 Gate：只允许 `product_type` 包含“手链”或“手串”的分析结果进入后续流程。
- 产品保真约束：每次分析都必须生成 `analysis/product_fidelity_constraints.json`；没有局部关键识别点时也要显式记录 `must_keep: []` 和 `review_status: not_applicable`。

## 字段要求

```json
{
  "product_type": "手串/手链/其他肉眼可见品类",
  "wear_position": "佩戴位置，例如手腕",
  "visible_appearance": "只描述肉眼可见外观，不写材质猜测",
  "color_family": ["主要可见颜色"],
  "style_mood": "整体可见风格氛围",
  "composition": "图片构图和产品展示方式",
  "product_dimensions": {
    "length_mm": null,
    "width_mm": null,
    "height_mm": null,
    "bead_diameter_mm": null,
    "dimension_source": null
  },
  "needs_full_front_display": true,
  "special_requirements": []
}
```

## 与产品保真约束的分工

- `visible_appearance` 写整体可见外观，例如颜色、透明度、纹理、珠子排列、主珠和配件位置。
- `special_requirements` 写整体展示要求，例如“完整露出正面主体”“保留主珠位置”。
- `product_fidelity_constraints.must_keep` 写不可被模型泛化的局部关键识别点，例如“白水晶随形”“海蓝宝跑环”。
- `product_fidelity_constraints.must_not_change` 写跨整件产品的禁改项，例如“珠子排列顺序”“主珠和配件位置关系”。
- 如果某个结构一旦改错会导致 SKU 识别错误，不要只写在 `visible_appearance` 或 `special_requirements`，必须写入 `must_keep`。

## 外观描述规则

- `visible_appearance` 只写肉眼可见外观，例如珠形、颜色、透明度、光泽、排列方式、配件形态、可见纹理。
- 不要猜测材质名，例如水晶、玛瑙、玉石、翡翠、银、金、珍珠等无法仅凭图片确定的材质。
- 不要把用户提供尺寸当作外观事实；尺寸只能帮助判断比例。
- 如果图片不是手串/手链，仍应如实填写可见品类，但后续流程会拒绝该结果。
- 对“随行/随形”等同义或错别字，保留原始 `source_text`，同时在保真约束中标准化为 `normalized_keyword`。
