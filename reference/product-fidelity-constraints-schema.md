# 产品保真约束 JSON Schema

`<run>/analysis/product_fidelity_constraints.json` 是每个标准 run 的 canonical（规范）产品保真约束。它把肉眼可见、容易被模型泛化的小结构和整件产品禁改项转成可 review、可拼装 Prompt、可逐项 QC 的清单。

该文件不是第二张用户输入图，也不是单个失败 SKU 的临时 Prompt 补丁。`prepare-review` 即使没有局部识别点也会写出该文件；`record-decision` 负责确认或导入约束；`generate` 只接受 canonical 路径；标准 QC 从生成目录自动反推该文件。

## 适用品类

约束结构统一用于 `bracelet`、`necklace` 和 `pendant_necklace`。`pendant_only` 与 `unknown` 可以在产品分析中识别，但不得因为存在约束文件而进入生成；无链独立吊坠禁止自动补链。

项链约束必须基于 `worn_source` 中肉眼可见的同一产品结构，覆盖 1 至 3 层、长度等级、吊坠所属层和可见连接。多件独立叠戴、白底/平铺或手持产品源、自动补链与不可见结构推断不是可“确认”的约束，应由品类/来源 gate 直接拒绝。

## Canonical 路径与导入事务

固定相对路径是：

```text
analysis/product_fidelity_constraints.json
```

`record-decision --fidelity-constraints-path <path>` 中的参数只表示本次约束导入源。命令会先读取和校验导入源，再把内容、可选的最终产品分析和 `review/review_decision.json` 以原子事务提交；成功后的决策始终记录 `analysis/product_fidelity_constraints.json`。

如果导入源状态是 `pending` 且生成决策带 `fidelity_confirmed: true`，提交到 canonical 文件时规范化为 `confirmed`。校验或写入任一步失败时事务回滚，不能留下新 analysis、旧约束与新决策混合的状态。

`generate` 不把 `fidelity_constraints_path` 当作运行时任意路径。历史决策如果仍记录非标准路径，会被明确拒绝并要求重新执行 `record-decision`；直接编辑决策或把外部文件留在原地不能绕过 canonical gate。

## `prepare-review` 自动产物

下面示例是产品描述包含“吊坠”和肉眼可见连接环时，当前 `build_product_fidelity_constraints` 实际生成的 canonical 候选。自动词典只命中标准词 `吊坠`；它不会把词典外的“连接环”写入 `detected_keywords`，也不会自动补造吊坠所属层或层间关系：

```json
{
  "schema_version": 1,
  "source": {
    "product_image": "input/product-on-hand.jpg",
    "product_analysis": "analysis/product_analysis.json"
  },
  "detected_keywords": ["吊坠"],
  "must_keep": [
    {
      "name": "吊坠",
      "source_text": "双层项链，正面中心有水滴形吊坠，可见连接环连接第二层链条",
      "normalized_keyword": "吊坠",
      "location": "正面中心",
      "visual_shape": "垂坠结构及连接点",
      "relationship": "保持垂坠方向、连接点和长度关系",
      "forbid": ["删除垂坠", "并入手串", "变成第二件首饰"],
      "qc_question": "吊坠、流苏或链坠的垂坠方向、连接点和长度关系是否保留"
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

自动产物中的 `source_text` 可以原样保留产品分析里肉眼可见的“连接环”和“第二层”描述，但自动程序不会把这些文本升级为独立命中来源或精确层级约束。人工不得伪造或扩充 `detected_keywords`；该字段只记录实际自动词典命中。

## 人工修订或导入后的产物

用户在 review 中确认吊坠确属第二层且连接环肉眼可见后，可以修订 `must_keep` 和 `must_not_change`，再通过 `record-decision --fidelity-constraints-path` 导入。修订后的 `detected_keywords` 仍保持自动命中结果，不把人工结论伪装成自动来源：

```json
{
  "schema_version": 1,
  "source": {
    "product_image": "input/product-on-hand.jpg",
    "product_analysis": "analysis/product_analysis.json"
  },
  "detected_keywords": ["吊坠"],
  "must_keep": [
    {
      "name": "第二层水滴吊坠",
      "source_text": "双层项链，正面中心有水滴形吊坠，可见连接环连接第二层链条",
      "normalized_keyword": "吊坠",
      "location": "第二层正面中央",
      "visual_shape": "透明水滴形，尖端向下",
      "relationship": "通过肉眼可见的连接环连接第二层链条",
      "forbid": ["换到第一层", "翻面", "复制", "脱离连接", "自动补链"],
      "qc_question": "第二层水滴吊坠是否仍位于第二层中央并保持原连接？"
    }
  ],
  "must_not_change": [
    "双层上下顺序与相对落差",
    "吊坠所属层和可见连接关系",
    "整件产品颜色、透明度、纹理和反光"
  ],
  "needs_user_review": true,
  "detail_crop_recommended": true,
  "review_status": "corrected"
}
```

## 字段要求

- `schema_version`：必填，当前固定为整数 `1`。
- `source.product_id`：可选产品编号。
- `source.product_image`：推荐固定为 `input/product-on-hand.jpg`。
- `source.product_analysis`：推荐固定为 `analysis/product_analysis.json`。
- `detected_keywords`：自动命中的标准化结构词字符串列表，顺序稳定。
- `must_keep`：必填数组；只有确实没有局部关键识别点时才允许为空。
- `must_keep[].name`：人工可读且能唯一定位的结构名称。
- `must_keep[].source_text`：来自产品可见描述的原始文本，便于追溯。
- `must_keep[].normalized_keyword`：标准化结构词，如 `随形`、`跑环`、`吊坠`、`连接环`。
- `must_keep[].location`：结构在产品或层中的肉眼可见位置。
- `must_keep[].visual_shape`：可见形状、朝向、透明度或纹理，不能只写推测材质。
- `must_keep[].relationship`：与相邻珠子、链条、吊坠或连接件的可见关系。
- `must_keep[].forbid`：该结构禁止发生的变化，至少一项。
- `must_keep[].qc_question`：QC 必须原样对应的问题。
- `must_not_change`：跨整件产品的禁改项，如层间关系、排列和整体外观。
- `needs_user_review`：有 `must_keep` 时通常为 `true`；没有时为 `false`。
- `detail_crop_recommended`：小、透明、低对比或遮挡结构建议为 `true`。
- `review_status`：只能是 `pending`、`confirmed`、`corrected`、`not_applicable`。

字符串字段必须是非空字符串，列表字段必须使用 JSON 数组和正确元素类型。不得使用布尔值、数字或宽松 truthy 值替代状态和文本。

## Review 状态

- `pending`：已发现关键识别点但未人工确认，不允许生成。
- `confirmed`：用户确认自动提取内容无误，允许通过约束状态 gate。
- `corrected`：用户已修订关键识别点，允许通过约束状态 gate。
- `not_applicable`：没有额外局部关键识别点；此时 `must_keep` 必须为空。

生成类决策还必须同时具备 `fidelity_confirmed: true`。普通项链和带链吊坠还需要完整产品确认快照；约束确认不能替代品类、来源、展示模式、层数与结构确认。

## 品类侧重点

### bracelet

- `must_not_change` 常包含珠子排列、主珠、配珠、隔圈和金属件位置。
- `must_keep` 常包含随形、跑环、双尖、回纹、貔貅、桶珠或雕刻件。
- 保真约束不替代原图手腕、手臂和皮肤块迁移检查。

### necklace

- 记录同一件产品 1 至 3 层的顺序、长度等级、相对落差和可见交叉关系。
- 不得把多件独立项链组合解释为同一件多层产品。
- 被头发、衣服或画面裁切遮挡的扣头、背面和连接细节不得推断。

### pendant_necklace

- 主吊坠、所属层、数量、位置、朝向和可见连接应写入 `must_keep`。
- `forbid` 至少覆盖删除、换层、翻面、复制、移位、脱离连接和自动补链中的适用项。

## 结构词典

| 结构词 | 必须保留 | 常见错误 |
| --- | --- | --- |
| 随形 / 随行 | 非圆珠的自然不规则轮廓和切面 | 改成圆珠、椭圆珠或普通隔珠 |
| 跑环 | 环形连接、位置关系和活动感 | 简化成链坠、圆珠或金属片 |
| 双尖 | 两端尖形轮廓和方向 | 磨成圆珠或桶珠 |
| 回纹 / 雕刻 | 可见纹样和凹凸层次 | 变成光面件 |
| 貔貅 | 头部、身体和造型方向 | 变成普通圆珠或抽象金属件 |
| 桶珠 | 圆柱侧面、端面和长度比例 | 改成圆珠 |
| 吊坠 / 流苏 / 链坠 | 所属层、方向、连接点和长度关系 | 删除、换层、复制、自动补链 |

词典只能辅助发现约束，不能覆盖产品图中的肉眼可见事实。

## QC 精确覆盖

标准 `qc.json` 位于 `<run>/generation/NN/qc.json` 时，写入器与便携校验器会自动找到 canonical 约束。每个 `must_keep` 必须有且只有一个 `fidelity_checks` 对象：

- 数量与 `must_keep` 完全一致。
- `name` 与对应 `must_keep[].name` 完全一致。
- `question` 与对应 `must_keep[].qc_question` 完全一致。
- name/question 组合唯一，且对应关系不能交换。
- `result` 只能是 `pass`、`rerun` 或 `fail`。

任何关键检查未通过时整体不得 `pass`。核心结构缺失、层间关系重组或自动补链等严重错误必须 `reject`。标准 run 不能通过删除、漏写或传空 `fidelity_checks` 进入宽松 legacy 校验。

## Legacy 边界

缺少 canonical 约束的历史手串 QC 可以继续按旧字段检查；这不要求批量迁移旧记录。历史手串自由文本、旧分析 JSON/run 和缺现代快照的 bracelet 仍兼容。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

普通项链、带链吊坠、`pendant_only` 和 `unknown` 不适用旧手串默认值。新 run 一旦能从标准路径找到 canonical 文件，就必须执行现代精确覆盖校验。

## 局部裁切图

当 `detail_crop_recommended` 为 `true` 时，可在 run 内保存：

```text
input/detail-crops/
  01-<normalized_keyword>.jpg
  02-<normalized_keyword>.jpg
```

裁切图用于人工 review 与 QC，不改变模型两张内部图的提交顺序，也不能用于推断原图不可见结构。

## 验收边界

本文示例和自动化测试验证的是本地 Schema、模型解析和命令契约。真实第三方模型 proof 属于 Task 11，尚未完成。
