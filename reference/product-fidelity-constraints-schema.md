# 产品保真约束 JSON Schema

`<run>/analysis/product_fidelity_constraints.json` 是每个标准 run 的 canonical（规范）产品保真约束。它把肉眼可见、容易被模型泛化的小结构和整件产品禁改项转成可 review、可拼装 Prompt、可逐项 QC 的清单。

该文件不是第二张用户输入图，也不是单个失败 SKU 的临时 Prompt 补丁。`schema_version=2` 是新 run 的必填结构；`prepare-review` 在所有人工纠正完成并重新校验最终 analysis 后构建 v2 canonical，`record-decision` 负责确认或导入，`generate` 只接受已确认的 canonical 路径，标准 QC 从生成目录自动反推该文件。历史 v1 只读，不自动升级，也不能进入新的项链 `record-decision` 或 `generate`；要继续处理，必须新建 run 并重新执行 `prepare-review`。

## 适用品类

约束结构统一用于 `bracelet`、`necklace`、`pendant_necklace` 和 `ring`。`pendant_only` 与 `unknown` 可以在产品分析中识别，但不得因为存在约束文件而进入生成；无链独立吊坠禁止自动补链。

项链约束必须基于 `worn_source` 中肉眼可见的同一产品结构，覆盖 1 至 3 层、长度等级、主吊坠所属层和可见连接。这里的 1 至 3 层只是运行时数据能力，不证明现实存在三圈吊坠商品，也不得据此伪造商品事实。双圈普通项链附件表示同一条连续长链绕颈形成 2 层，`pendant_semantics.presence=absent`，不是两件独立项链，也不是带链吊坠。多件独立叠戴、白底/平铺或手持产品源、自动补链与不可见结构推断不是可“确认”的约束，应由品类/来源 gate 直接拒绝。

戒指约束同样只记录产品图肉眼可见事实。即使没有命中手串/项链结构词典，戒指也必须生成非空的产品级 `must_keep`：一项直接引用 `visible_appearance` 保存整枚戒指可见结构，一项同时引用 `color_family` 与可见描述保存颜色和材质表现，并把每条 `special_requirements` 分别转成可追溯的产品特定要求。现代分析和确认快照必须另行保存 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`；约束文件不能替代单枚、左右手、目标手指和 `finger_base` gate。不可见戒圈背面、镶嵌背面或连接结构只能进入禁止推断边界，不得写成确定款式事实。

## Canonical 路径与导入事务

固定相对路径是：

```text
analysis/product_fidelity_constraints.json
```

`record-decision --fidelity-constraints-path <path>` 中的参数只表示本次约束导入源。命令会先读取导入源，并结合已经完成参考评分的最终 `ProductAnalysis` 交叉校验 `schema_version=2`、`pendant_semantics`、品类 canonical 不变量与 `source.product_analysis_sha256`，再把内容和 `review/review_decision.json` 以原子事务提交；任何冲突都用中文错误说明修复动作，并在文件替换前停止。成功后的决策始终记录 `analysis/product_fidelity_constraints.json`。摘要对所有品类强制生效，防止把同品类另一 SKU 的约束误导入当前 run。戒指导入还必须在任何文件替换前验证非空 `must_keep`、状态、全部字段（包括 `source_text`）不含手串语义，以及分析字段的可追溯覆盖。

项链 analysis 的品类、来源、展示模式、层数、长度或主吊坠结构一旦变化，旧 Top 3 与旧 canonical 同时失效；`record-decision` 会在事务前拒绝，不能通过导入约束或重绑摘要继续。必须新建 run，在 `prepare-review` 评分前完成最终纠正，并基于最终 analysis 重建 Top 3 与 v2 canonical。戒指等仍允许决策阶段纠正的路径继续使用原子事务；外部文件不自动重绑摘要。

如果导入源状态是 `pending` 且生成决策带 `fidelity_confirmed: true`，提交到 canonical 文件时规范化为 `confirmed`。校验或写入任一步失败时事务回滚，不能留下新 analysis、旧约束与新决策混合的状态。

`generate` 不把 `fidelity_constraints_path` 当作运行时任意路径。在创建 generation 目录或调用 helper/provider 前，它会再次使用磁盘中的最终 `ProductAnalysis` 交叉校验决策快照、canonical 路径、摘要、`schema_version=2` 与 `pendant_semantics`；冲突时输出中文修复动作并停止。历史决策如果仍记录非标准路径，或旧 canonical 缺少/携带错误的 `product_analysis_sha256`，会被明确拒绝并要求重新执行 `prepare-review` / `record-decision`；直接编辑决策或把外部文件留在原地不能绕过 canonical gate。历史戒指文件即使状态已是 `confirmed`，只要为空、使用 `not_applicable`、混入手串语义或缺少任一分析字段的可追溯覆盖，也必须拒绝。

## `prepare-review` 自动产物

`prepare-review` 先合并所有 correction-only 参数并校验最终 analysis，再构建 `schema_version=2` canonical、评分并复制 Top 3。下面是普通双圈项链的完整 v2 示例。它表示同一条连续长链绕颈形成 2 层；结构化主吊坠语义为 absent，不是两件项链，也不是带链吊坠。absent 规则不依赖 `must_not_change` 或 `forbid` 中的自然语言否定句：

```json
{
  "schema_version": 2,
  "source": {
    "product_image": "input/product-on-hand.jpg",
    "product_analysis": "analysis/product_analysis.json",
    "product_analysis_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "detected_keywords": [],
  "must_keep": [
    {
      "name": "双圈连续结构",
      "source_text": "同一条连续海蓝宝微珠长链绕颈形成上下双圈",
      "normalized_keyword": "双圈连续链",
      "location": "颈前上下两层",
      "visual_shape": "两层连续微珠链",
      "relationship": "同一条长链绕颈形成两层，不是两件独立首饰",
      "forbid": ["拆成两件独立首饰", "改成三层"],
      "qc_question": "同一条连续长链是否仍形成上下两层"
    }
  ],
  "must_not_change": [
    "同一条长链形成的双圈结构和上下相对落差",
    "整件产品颜色、透明度、纹理、光泽和反光"
  ],
  "pendant_semantics": {
    "presence": "absent",
    "count": 0,
    "layer": null,
    "creation_policy": "forbid"
  },
  "needs_user_review": true,
  "detail_crop_recommended": true,
  "review_status": "pending"
}
```

示例中的全零摘要仅为 JSON 形态占位，不能用于真实文件。实际值由 builder 对规范化 `ProductAnalysis`（包括 dataclass、枚举与 tuple 的稳定 JSON 表示，key 排序）计算 SHA-256。普通项链的 absent canonical 在下列 10 类自由文本路径中都不得出现五个敏感词 `吊坠`、`主吊坠`、`链坠`、`流苏`、`坠子`：`detected_keywords[]`、`must_not_change[]`、`must_keep[].name`、`must_keep[].source_text`、`must_keep[].normalized_keyword`、`must_keep[].location`、`must_keep[].visual_shape`、`must_keep[].relationship`、`must_keep[].forbid[]`、`must_keep[].qc_question`。禁止创建的机器事实只由 `pendant_semantics.creation_policy=forbid` 表达，canonical 自由文本不得再写“禁止新增吊坠”。

## 人工修订或导入后的产物

下面是带链吊坠经人工确认后的完整 v2 示例。`pendant_semantics` 精确声明 presence/count/layer；对应 `must_keep` 必须有且只有一项可追溯主吊坠，并在 relationship 中包含所属层。人工修订后可通过 `record-decision --fidelity-constraints-path` 导入，但不得改写自动命中来源：

```json
{
  "schema_version": 2,
  "source": {
    "product_image": "input/product-on-hand.jpg",
    "product_analysis": "analysis/product_analysis.json",
    "product_analysis_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
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
  "pendant_semantics": {
    "presence": "present",
    "count": 1,
    "layer": 2,
    "creation_policy": "forbid"
  },
  "needs_user_review": true,
  "detail_crop_recommended": true,
  "review_status": "corrected"
}
```

## 字段要求

v1 顶层字段固定为 `schema_version`、`source`、`detected_keywords`、`must_keep`、`must_not_change`、`needs_user_review`、`detail_crop_recommended`、`review_status`，不得出现 `pendant_semantics`。v2 顶层字段是在同一组字段上增加必填对象 `pendant_semantics`。两个版本均拒绝未知顶层字段；新 run 必须写 `schema_version=2`。

- `schema_version`：必填，只接受整数 `1` 或 `2`，不接受布尔值、字符串或其他数字；v1 仅供历史只读，v2 用于新 run。
- `source.product_id`：可选产品编号。
- `source.product_image`：推荐固定为 `input/product-on-hand.jpg`。
- `source.product_analysis`：必填，固定为 `analysis/product_analysis.json`。
- `source.product_analysis_sha256`：必填，必须等于最终规范化 `ProductAnalysis` 的 SHA-256；不是原始 JSON 文件字节摘要，也不能从另一 SKU 复制。
- `detected_keywords`：自动命中的标准化结构词字符串列表，顺序稳定；戒指产品级 canonical 不是词典命中，因此允许为空。
- `must_keep`：必填数组；非戒指只有确实没有局部关键识别点时才允许为空，戒指必须至少包含整体可见结构和可见颜色/材质表现，并逐条包含产品特定要求。validator 会扫描每项的 name、`source_text`、keyword、位置、形状、关系、全部 forbid 和 QC question；项链不得混入主珠/配珠/手腕环绕等手串结构语义，手串不得混入绕颈/锁骨/后颈/层间落差等项链结构语义。
- `must_keep[].name`：人工可读且能唯一定位的结构名称。
- `must_keep[].source_text`：来自产品可见描述的原始文本，便于追溯。
- `must_keep[].normalized_keyword`：标准化结构词，如 `随形`、`跑环`、`吊坠`、`连接环`。
- `must_keep[].location`：结构在产品或层中的肉眼可见位置。
- `must_keep[].visual_shape`：可见形状、朝向、透明度或纹理，不能只写推测材质。
- `must_keep[].relationship`：与相邻珠子、链条、吊坠或连接件的可见关系。
- `must_keep[].forbid`：该结构禁止发生的变化，至少一项。
- `must_keep[].qc_question`：QC 必须原样对应的问题。
- `must_not_change`：跨整件产品的禁改项，如层间关系、排列和整体外观。
- `pendant_semantics`：v2 必填、v1 禁止；必须严格包含 `presence`、`count`、`layer`、`creation_policy`。
- `pendant_semantics.presence`：只允许 `present` 或 `absent`。
- `pendant_semantics.count`：第一阶段只允许整数 `0` 或 `1`；absent 固定为 `0`，present 固定为 `1`。
- `pendant_semantics.layer`：absent 固定为 `null`；present 必须为整数 `1..3`，并与最终 analysis 的所属层一致。
- `pendant_semantics.creation_policy`：固定为 `forbid`；禁止新增不是 canonical 自由文本极性。
- `needs_user_review`：有 `must_keep` 时通常为 `true`；没有时为 `false`。
- `detail_crop_recommended`：小、透明、低对比或遮挡结构建议为 `true`。
- `review_status`：只能是 `pending`、`confirmed`、`corrected`、`not_applicable`。

字符串字段必须是非空字符串，列表字段必须使用 JSON 数组和正确元素类型。不得使用布尔值、数字或宽松 truthy 值替代状态和文本。

## Review 状态

- `pending`：已发现关键识别点但未人工确认，不允许生成。
- `confirmed`：用户确认自动提取内容无误，允许通过约束状态 gate。
- `corrected`：用户已修订关键识别点，允许通过约束状态 gate。
- `not_applicable`：非戒指产品没有额外局部关键识别点；此时 `must_keep` 必须为空。戒指固定具有产品级关键识别点，不得使用该状态。

生成类决策还必须同时具备 `fidelity_confirmed: true`。普通项链、带链吊坠和戒指还需要完整产品确认快照；约束确认不能替代品类、来源、展示模式、层数、左右手、目标手指与结构确认。新项链的 `record-decision` 和 `generate` 都必须在写文件、创建 generation 目录或调用 helper/provider 前拒绝 v1、缺失 v2 字段或 analysis/canonical/快照冲突，并用中文要求新建 run、纠正 analysis 后重新执行 `prepare-review`。

## 品类侧重点

### bracelet

- `must_not_change` 常包含珠子排列、主珠、配珠、隔圈和金属件位置。
- `must_keep` 常包含随形、跑环、双尖、回纹、貔貅、桶珠或雕刻件。
- 保真约束不替代原图手腕、手臂和皮肤块迁移检查。

### necklace

- 记录同一件产品 1 至 3 层的顺序、长度等级、相对落差和可见交叉关系。
- 不得把多件独立项链组合解释为同一件多层产品。
- 普通项链固定使用 `pendant_semantics={presence: absent, count: 0, layer: null, creation_policy: forbid}`；双圈附件是同一条长链形成 2 层，不是两件项链或带链吊坠。
- 1 至 3 层仅表示解析、校验和渲染能力，不代表存在三圈吊坠商品。
- 被头发、衣服或画面裁切遮挡的扣头、背面和连接细节不得推断。

### pendant_necklace

- 主吊坠、所属层、数量、位置、朝向和可见连接应写入 `must_keep`。
- 固定使用 `pendant_semantics={presence: present, count: 1, layer: ProductAnalysis.pendant_layer, creation_policy: forbid}`；第一阶段不支持多颗主吊坠。
- `forbid` 至少覆盖删除、换层、翻面、复制、移位、脱离连接和自动补链中的适用项。

### ring

- `must_keep` 必须先记录两项产品级 canonical：直接引用 `visible_appearance` 的整枚可见结构，以及结合 `color_family` 与可见描述的颜色/材质表现；每条 `special_requirements` 还必须按原顺序分别形成一项产品特定约束，其 `source_text` 必须等于原要求，`visual_shape`、完整 `forbid` 列表和 `qc_question` 必须按 builder 契约精确引用同一条要求，不能只保留 source 后把执行/QC 字段改成空泛描述。
- 整体结构的 `qc_question` 必须要求逐项对照戒面、主石、戒圈、开口端点和装饰排列等肉眼可见事实的数量、形状、朝向及位置关系，不能只问“结构是否正确”。
- `must_not_change` 应覆盖戒面/主石数量与朝向、戒圈粗细与开口端点、颜色/材质表现和装饰排列，并明确禁止推断不可见戒圈背面、镶嵌背面及连接结构；不得出现“珠子排列顺序”或“主珠”等手串语义。
- `occluded_parts` 与 `uncertain_details` 必须写入禁止推断或禁止确定性补全的禁改边界；整体结构项的 `forbid` 必须精确包含“关闭现有开口或新增开口”和“把不可见戒圈背面、镶嵌背面或连接结构补写为确定结构”，并覆盖改款、复制主石和改变可见镶嵌。
- 自动产物固定为 `review_status=pending`、`needs_user_review=true`、`detail_crop_recommended=true`；只有 `record-decision --fidelity-confirmed` 后才规范化为 `confirmed`。
- `ring_count`、`hand_side`、`finger_position`、`ring_wear_style` 属于分析与快照 gate，不应伪装成自动词典命中。

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
| 戒面 / 主石 / 镶嵌 / 戒圈开口 | 可见数量、形状、朝向、位置和排列 | 改款、复制、闭合开口、补写不可见背面 |

词典只能辅助发现约束，不能覆盖产品图中的肉眼可见事实。

## QC 精确覆盖

标准 `qc.json` 位于 `<run>/generation/NN/qc.json` 时，写入器与便携校验器会自动找到 canonical 约束。每个 `must_keep` 必须有且只有一个 `fidelity_checks` 对象：

- 数量与 `must_keep` 完全一致。
- `name` 与对应 `must_keep[].name` 完全一致。
- `question` 与对应 `must_keep[].qc_question` 完全一致。
- name/question 组合唯一，且对应关系不能交换。
- `result` 只能是 `pass`、`rerun` 或 `fail`。

此外，标准路径会同时读取 `product_analysis.json` 和 canonical，重建完整 runtime checklist；`checklist_checks` 必须按 `qc-` 加 question 的 SHA-256 前 16 位形成稳定 ID，并精确、唯一、完整覆盖所有通用项、品类项、展示模式项和 `must_keep` question。v2 普通项链必须额外逐字记录 `主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠`；v2 带链吊坠必须按实际值记录 `现有主吊坠数量是否为 {count}，且仍位于第 {layer} 层并保持原连接关系`。任何关键检查未通过时整体不得 `pass`。核心结构缺失、层间关系重组或自动补链等严重错误必须 `reject`。标准 run 不能通过删除、漏写或传空任一结构化检查进入宽松 legacy 校验。

Prompt 同样只从已校验 v2 结构化事实渲染。普通项链精确输出 `主吊坠：无。` 和 `禁止新增、补造、复制、悬挂化吊坠，也不得把珠子、跑环或其他元件改成吊坠。`；带链吊坠精确输出 `主吊坠：有；数量：1；所属层：第 N 层。`、`保持肉眼可见的位置、朝向与连接关系；禁止删除、复制、换层或新增第二颗吊坠。`。渲染器不得从自然语言里的“禁止”“没有”等极性猜测 presence。

## Legacy 边界

历史 v1 允许 inspector、validator 和 QC 只读检查，inspector 必须报告 `legacy_read_only=true`；读取不得改写原文件、补写 `pendant_semantics` 或把历史 v1 自动升级为 v2。以下 v1 形态仅表示可解析的历史记录：

```json
{
  "schema_version": 1,
  "source": {
    "product_image": "input/product-on-hand.jpg",
    "product_analysis": "analysis/product_analysis.json",
    "product_analysis_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "detected_keywords": [],
  "must_keep": [],
  "must_not_change": ["保持历史记录中的可见产品结构"],
  "needs_user_review": false,
  "detail_crop_recommended": false,
  "review_status": "not_applicable"
}
```

`product_analysis.json` 与 canonical 同时不存在的历史手串 QC 可以继续按旧字段检查；这不要求批量迁移旧记录。只存在其中一个文件属于损坏的标准 run，不得当作 legacy。历史手串自由文本、旧分析 JSON/run 和缺现代快照的 bracelet 仍兼容，但只要要继续生成，就必须重新建立带摘要的 canonical。历史项链 v1 不允许进入新的 `record-decision` 或 `generate`；必须新建 run，完成最终 analysis 纠正并重新执行 `prepare-review`，由 builder 生成 v2，不能手改或原地迁移。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

普通项链、带链吊坠、戒指、`pendant_only` 和 `unknown` 不适用旧手串默认值。新 run 一旦能从标准路径找到 canonical 文件，就必须执行现代精确覆盖校验。

## 局部裁切图

当 `detail_crop_recommended` 为 `true` 时，可在 run 内保存：

```text
input/detail-crops/
  01-<normalized_keyword>.jpg
  02-<normalized_keyword>.jpg
```

裁切图用于人工 review 与 QC，不改变模型两张内部图的提交顺序，也不能用于推断原图不可见结构。

## 验收边界

本文示例和自动化测试验证的是本地 Schema、模型解析和命令契约。真实第三方模型 proof 属于 Task 11，尚未完成。本次 v2 交付只关闭结构化主吊坠语义 I1；I5 真实双圈成功 proof 与 HERO 仍是开放项，不属于本次实现，也不能因本地测试通过而宣称完成。
