# 产品分析 JSON Schema 说明

产品分析 JSON 是系统根据一张产品上手原图生成的内部结构化产物，不是用户需要额外提供的第二份输入。它同时记录原始可读品类、标准化品类、分类依据、展示模式、输入图类型、项链或吊坠结构，以及无法从图片确认的信息，供后续参考图选择、提示词生成和质检使用。

产品分析 JSON 只负责描述整体可见外观和结构，不能替代 `analysis/product_fidelity_constraints.json`。凡是随形、跑环、双尖、回纹、貔貅、桶珠、雕刻、吊坠、流苏、链坠等会影响货号识别的局部结构，都必须同步写入产品保真约束文件，供 review、prompt 和 QC 使用。

## 第一阶段输入与品类边界

- 用户输入：一张真人佩戴产品原图。
- 可选尺寸：仅作为比例参考，不能覆盖、改写或替代图片中的可见外观。
- 当前可生成品类：手串/手链、普通项链、带链吊坠。
- 可识别但不可生成：无链独立吊坠。系统必须明确拒绝，且禁止自动补链。
- 不可生成：无法识别或其他未支持品类。
- 第一阶段输入图只接受 `worn_source`。`hand_held_source`、`flat_lay_source` 和 `unknown_source` 必须如实记录，但加载阶段会拒绝。
- `display_mode` 描述后续生成展示模式，不等同于 `source_image_type`。普通项链和带链吊坠可以由真人佩戴原图生成手持展示图。
- 每次分析都必须生成 `analysis/product_fidelity_constraints.json`；没有局部关键识别点时也要显式记录 `must_keep: []` 和 `review_status: not_applicable`。

## 当前完整结构

新生成的分析结果必须输出全部字段。以下示例描述一件双层带链吊坠；不适用或无法确认的可选结构字段使用 `null`，列表字段使用空列表。

```json
{
  "product_type": "带链吊坠",
  "detected_product_type": "pendant_necklace",
  "confirmed_product_type": "pendant_necklace",
  "classification_confidence": "high",
  "classification_evidence": ["第二层正面中央存在与链条连接的主吊坠"],
  "classification_source": "auto_confirmed",
  "display_mode": "hand_held",
  "source_image_type": "worn_source",
  "wear_position": "颈部和锁骨",
  "visible_appearance": "两层圆珠链，第二层正面中央连接一枚水滴形透明吊坠",
  "color_family": ["透明", "金色"],
  "style_mood": "轻盈清透",
  "composition": "颈部至胸前近景，正面主体完整",
  "product_dimensions": {
    "length_mm": null,
    "width_mm": null,
    "height_mm": null,
    "bead_diameter_mm": null,
    "dimension_source": null
  },
  "needs_full_front_display": true,
  "special_requirements": ["保留双层顺序和相对落差"],
  "layer_count": 2,
  "length_category": "collarbone",
  "chain_or_strand_type": "beaded",
  "has_pendant": true,
  "pendant_count": 1,
  "pendant_layer": 2,
  "pendant_position": "front_center",
  "pendant_orientation": "front_facing",
  "connection_structure": "metal_bail",
  "symmetry": "approximately_symmetric",
  "occluded_parts": ["后颈扣头"],
  "uncertain_details": ["扣头具体结构"],
  "is_independent_multi_item": false
}
```

## 字段定义与类型

| 字段 | 类型 | 当前含义 |
| --- | --- | --- |
| `product_type` | 非空字符串 | 保留原始、可读的品类描述；历史自由文本如“朱砂手链/手串”继续可读。 |
| `detected_product_type` | 标准品类字符串 | 图片初步识别结果：`bracelet`、`necklace`、`pendant_necklace`、`pendant_only` 或 `unknown`。 |
| `confirmed_product_type` | 标准品类字符串 | 系统保守确认或人工纠正后的结果；后续流程以此字段为准。 |
| `classification_confidence` | 非空字符串 | 分类置信度，例如 `high`、`medium`、`low`。 |
| `classification_evidence` | 字符串列表 | 支持分类的肉眼可见证据，不写材质推断。 |
| `classification_source` | 非空字符串 | 分类来源，例如 `auto_confirmed`、`manual_confirmed`、`legacy_inferred`。 |
| `display_mode` | 枚举字符串 | 后续生成展示模式：`worn` 或 `hand_held`。 |
| `source_image_type` | 枚举字符串 | 输入图类型：`worn_source`、`hand_held_source`、`flat_lay_source` 或 `unknown_source`。 |
| `wear_position` | 非空字符串 | 肉眼可见佩戴位置，例如手腕、颈部、锁骨或胸前。 |
| `visible_appearance` | 非空字符串 | 整体可见外观、排列、透明度、光泽、配件和可见纹理。 |
| `color_family` | 字符串列表 | 主要可见颜色。 |
| `style_mood` | 非空字符串 | 整体可见风格氛围。 |
| `composition` | 非空字符串 | 输入图构图和产品展示方式。 |
| `product_dimensions` | 对象 | 可选尺寸及来源；尺寸值必须为有限正数或 `null`。 |
| `needs_full_front_display` | 布尔值 | 后续结果是否需要完整露出正面主体。 |
| `special_requirements` | 字符串列表 | 整体展示要求，不替代局部保真约束。 |
| `layer_count` | 正整数 | 单件产品自身层数；普通项链和带链吊坠仅支持 1 至 3 层。 |
| `length_category` | 字符串或 `null` | 长度类别，例如 `choker`、`collarbone`、`long`；无法确认时为 `null`。 |
| `chain_or_strand_type` | 字符串或 `null` | 肉眼可见链条或串线类型，例如 `metal_chain`、`beaded`。 |
| `has_pendant` | 布尔值 | 是否肉眼可见吊坠。 |
| `pendant_count` | 非负整数 | 肉眼可见吊坠数量。 |
| `pendant_layer` | 正整数或 `null` | 吊坠所在层；不得大于 `layer_count`。 |
| `pendant_position` | 字符串或 `null` | 吊坠可见位置，例如 `front_center`。 |
| `pendant_orientation` | 字符串或 `null` | 吊坠可见朝向，例如 `front_facing`。 |
| `connection_structure` | 字符串或 `null` | 肉眼可见连接结构；看不清时不得推断。 |
| `symmetry` | 字符串或 `null` | 可见对称关系。 |
| `occluded_parts` | 字符串列表 | 被身体、头发、衣物或画面裁切遮挡的部位。 |
| `uncertain_details` | 字符串列表 | 图片无法确认且禁止臆测的细节。 |
| `is_independent_multi_item` | 布尔值 | 是否为多件独立产品组合叠戴；当前不支持多件独立项链组合生成。 |

`product_dimensions` 的固定子字段如下：

- `length_mm`、`width_mm`、`height_mm`、`bead_diameter_mm`：有限正数或 `null`。
- `dimension_source`：非空字符串或 `null`；引用用户尺寸时写明“用户提供尺寸信息”。

## 品类、展示模式与输入图兼容矩阵

| `confirmed_product_type` | 可用 `display_mode` | 第一阶段可用 `source_image_type` | 层数 | 结果 |
| --- | --- | --- | --- | --- |
| `bracelet` | `worn` | `worn_source` | 1 层 | 支持 |
| `necklace` | `worn`、`hand_held` | `worn_source` | 1 至 3 层 | 支持 |
| `pendant_necklace` | `worn`、`hand_held` | `worn_source` | 1 至 3 层 | 支持 |
| `pendant_only` | 无 | 无 | 不进入生成 | 明确拒绝，禁止自动补链 |
| `unknown` | 无 | 无 | 不进入生成 | 必须先人工纠正 |

对于前三个支持品类，`flat_lay_source`、`hand_held_source` 和 `unknown_source` 均不满足第一阶段输入边界。普通项链或带链吊坠即使选择 `hand_held` 输出模式，输入仍必须是 `worn_source`。

## 结构校验规则

- `layer_count` 必须为大于等于 1 的整数；普通项链和带链吊坠不得超过 3 层，手串/手链只支持 1 层。
- `pendant_count` 必须为大于等于 0 的整数，不接受布尔值或带小数的数值。
- `pendant_layer` 如果存在，必须为正整数且不得大于 `layer_count`。
- 普通项链和带链吊坠的 `is_independent_multi_item` 必须为 `false`；多件独立项链组合叠戴当前不进入生成。
- 列表字段只能包含字符串；布尔、整数、枚举和可选字符串字段必须符合上表类型。
- `confirmed_product_type` 可以与 `detected_product_type` 不同，用于保存人工纠正；后续支持判断以 `confirmed_product_type` 为准。

## 历史手串 JSON 兼容

历史手串 JSON 可能只有原有基础字段，没有任何分类、模式或结构字段。加载器保留原始 `product_type` 字符串，并按下列默认值补齐，不要求迁移旧文件：

| 缺失字段 | 兼容默认值 |
| --- | --- |
| `detected_product_type` | 从 `product_type` 保守归一化；“朱砂手链/手串”等旧自由文本归一化为 `bracelet`。 |
| `confirmed_product_type` | 等于归一化后的 `detected_product_type`。 |
| `classification_confidence` | `high` |
| `classification_evidence` | `[]` |
| `classification_source` | `legacy_inferred` |
| `display_mode` | `worn` |
| `source_image_type` | `worn_source` |
| `layer_count` | `1` |
| `length_category`、`chain_or_strand_type` | `null` |
| `has_pendant` | `false` |
| `pendant_count` | `0` |
| `pendant_layer`、`pendant_position`、`pendant_orientation`、`connection_structure`、`symmetry` | `null` |
| `occluded_parts`、`uncertain_details` | `[]` |
| `is_independent_multi_item` | `false` |

只有字段缺失或值为 `null` 时才使用品类回退逻辑；显式提供布尔值、列表等非法品类字段类型会抛出中文错误，不会被静默当作历史默认值。

## 外观描述与保真约束分工

- `visible_appearance` 写整体可见外观，例如颜色、透明度、纹理、珠子或链条排列、主珠和配件位置。
- `special_requirements` 写整体展示要求，例如“完整露出正面主体”“保留双层顺序”。
- `product_fidelity_constraints.must_keep` 写不可被模型泛化的局部关键识别点，例如“白水晶随形”“海蓝宝跑环”。
- `product_fidelity_constraints.must_not_change` 写跨整件产品的禁改项，例如“珠子排列顺序”“主珠和配件位置关系”。
- 如果某个结构一旦改错会导致 SKU 识别错误，不要只写在 `visible_appearance` 或 `special_requirements`，必须写入 `must_keep`。

## 外观描述规则

- 只写肉眼可见的形状、颜色、透明度、光泽、排列方式、配件形态和纹理。
- 不要猜测水晶、玛瑙、玉石、翡翠、银、金、珍珠等无法仅凭图片确认的材质。
- 不要把用户提供尺寸当作外观事实；尺寸只能帮助判断比例。
- 对扣头、背面、被头发或衣物遮挡的结构，不得凭常识补全，必须写入 `occluded_parts` 或 `uncertain_details`。
- 对“随行/随形”等同义或错别字，保留原始 `source_text`，同时在保真约束中标准化为 `normalized_keyword`。
