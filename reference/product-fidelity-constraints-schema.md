# 产品保真约束 JSON Schema 说明

`analysis/product_fidelity_constraints.json` 是产品分析阶段必须生成的结构化中间产物，用于把“肉眼可见但容易被模型泛化的小结构”转成可 review、可拼装 prompt、可逐项 QC 的约束清单。

它不是用户第二输入，也不是为某个 SKU 临时补的一句 prompt。每个 run 进入 Review Gate 前都必须存在该文件；如果没有局部关键识别点，也必须显式写出 `must_keep: []` 和 `review_status: not_applicable`。

## 目标

- 从产品可见外观和特殊要求中提取关键识别点，例如随形、跑环、双尖、回纹、貔貅、桶珠、雕刻、吊坠、流苏、链坠。
- 明确每个关键识别点的位置、形态、相邻关系、禁止变化和 QC 问题。
- 让 Prompt Builder 必须消费 `must_keep` 和 `must_not_change`。
- 让 QC 必须逐项回答 `must_keep[].qc_question`。
- 避免只修单个失败 SKU，而是让所有产品都经过“发现约束 -> 人工确认 -> 生成约束 -> 逐项质检”的闭环。

## JSON 结构

```json
{
  "schema_version": 1,
  "source": {
    "product_id": "JH016",
    "product_image": "input/product-on-hand.jpg",
    "product_analysis": "analysis/product_analysis.json"
  },
  "detected_keywords": ["随形"],
  "must_keep": [
    {
      "name": "白水晶随形",
      "source_text": "白水晶随形",
      "normalized_keyword": "随形",
      "location": "手串正面中心附近",
      "visual_shape": "透明、不规则随形、非圆珠、偏扁切面",
      "relationship": "位于相邻圆珠之间，是产品识别点",
      "forbid": ["改成圆珠", "改成椭圆珠", "改成普通隔珠"],
      "qc_question": "白水晶随形是否仍是不规则透明异形珠"
    }
  ],
  "must_not_change": [
    "珠子排列顺序",
    "主珠和配件位置关系",
    "产品整体颜色、透明度、纹理和反光"
  ],
  "needs_user_review": true,
  "detail_crop_recommended": true,
  "review_status": "pending"
}
```

## 字段要求

- `schema_version`：必填，当前固定为 `1`。
- `source.product_id`：可选，来自货号或本地任务编号。
- `source.product_image`：推荐填写，默认 `input/product-on-hand.jpg`。
- `source.product_analysis`：推荐填写，默认 `analysis/product_analysis.json`。
- `detected_keywords`：自动命中的标准化结构词列表，顺序应稳定，便于 review。
- `must_keep`：必填数组；允许为空，但只有在确实没有局部关键识别点时才应为空。
- `must_keep[].name`：人工可读名称，例如“白水晶随形”“海蓝宝跑环”。
- `must_keep[].source_text`：原始来源文本，保留“随行/随形”等原词，便于追溯。
- `must_keep[].normalized_keyword`：标准化结构词，例如 `随形`、`跑环`、`双尖`。
- `must_keep[].location`：该结构在产品中的位置，例如“主珠右侧”“垂坠连接处”。
- `must_keep[].visual_shape`：必须描述可见形态，不只写材质名。
- `must_keep[].relationship`：该结构与相邻珠子、隔圈、吊坠、链条或主珠的连接关系。
- `must_keep[].forbid`：该结构生成时禁止变成什么，至少包含一项。
- `must_keep[].qc_question`：QC 时必须逐项回答的问题。
- `must_not_change`：整件产品的保真禁改项。
- `needs_user_review`：有 `must_keep` 时通常为 `true`；无局部关键识别点时为 `false`。
- `detail_crop_recommended`：小结构、半透明结构、低对比结构、遮挡结构建议为 `true`。
- `review_status`：只能是 `pending`、`confirmed`、`corrected`、`not_applicable`。

## Review 状态规则

- `pending`：系统已发现关键识别点，但尚未人工确认；不允许进入生成。
- `confirmed`：用户已确认关键识别点无误；允许进入生成。
- `corrected`：用户已补充或修正关键识别点；允许进入生成。
- `not_applicable`：没有额外局部关键识别点，且 `must_keep` 必须为空；允许进入生成。

生成前 gate 必须同时满足：

- `review/review_decision.json` 的 `fidelity_confirmed` 为 `true`。
- `analysis/product_fidelity_constraints.json` 存在且 JSON 合法。
- `review_status` 为 `confirmed`、`corrected` 或 `not_applicable`。

## 局部结构词典

| 结构词 | 识别含义 | 必须保留 | 常见错误 |
|---|---|---|---|
| 随形 / 随行 | 不规则异形珠或切面件，可能透明或有色 | 非圆珠、非椭圆珠、自然不规则轮廓和切面 | 被改成圆珠、椭圆珠、普通隔珠 |
| 跑环 | 环状连接结构或活动环，常连接主珠、吊坠或垂坠 | 环形连接、位置关系、活动感 | 被简化成普通链坠、圆珠、金属片 |
| 双尖 | 两端尖锥或双尖柱状结构 | 两端尖形轮廓和方向 | 被磨成圆珠或桶珠 |
| 回纹 | 表面回纹雕刻或连续纹路 | 表面纹样和凹凸感 | 被生成光面珠 |
| 貔貅 | 动物造型配件 | 头部、身体、立体造型方向 | 被变成普通圆珠或抽象金属件 |
| 桶珠 | 圆柱或桶形珠 | 圆柱侧面、端面和长度比例 | 被改成圆珠 |
| 雕刻 / 雕花 | 表面立体纹样 | 纹样、浅浮雕或镂刻层次 | 被磨平成光面 |
| 吊坠 / 流苏 / 链坠 | 垂坠结构及连接点 | 垂坠方向、连接点、长度关系 | 被删掉、并入手串、变成第二件首饰 |

词典只用于提醒和生成约束，不允许覆盖图片中肉眼可见事实。如果词典含义与产品图冲突，以产品图为准。

## 局部裁切图

当 `detail_crop_recommended = true` 时，建议在 run 内保存局部裁切图：

```text
input/detail-crops/
  01-<normalized_keyword>.jpg
  02-<normalized_keyword>.jpg
```

局部裁切图用于人工 review 和 QC，不改变模型内部图片顺序。当前模型提交仍固定为两张图：内部图1为自动参考图，内部图2为用户产品上手原图。
