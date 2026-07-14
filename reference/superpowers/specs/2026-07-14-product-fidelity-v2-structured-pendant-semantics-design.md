# 产品保真 v2 结构化吊坠语义设计

**日期：** 2026-07-14  
**状态：** 已批准，待实施  
**适用范围：** 普通项链与带链吊坠的新建 run；历史 v1 canonical 只读兼容

## 1. 背景与问题

普通项链 `has_pendant=false` 必须同时满足两条边界：

1. 不得把“不是吊坠、没有吊坠、禁止新增吊坠”等否定描述提取成需要保留的现有吊坠。
2. 不得允许人工 canonical 在任意自由文本字段中隐藏“必须保留既有吊坠、不得改变主吊坠”等正向保留语义。

现有 `schema_version=1` 依赖中文分句、连接词、否定词和动作词判断自由文本极性。四轮修复已经覆盖字段全集、动作顺序与大量复合句，但独立审查仍能通过新的连接词或否定作用域构造漏判。继续增加同义词和正则不能证明自然语言闭合，也会持续引入误拒。

因此，新 run 不再以自然语言极性推断作为吊坠存在性和创建策略的权威来源。`schema_version=2` 使用结构化吊坠契约；自由文本只描述肉眼可见产品事实，不承担“有无吊坠”和“是否允许新增吊坠”的机器语义。

## 2. 目标

- 为普通项链和带链吊坠提供唯一、可枚举、可交叉校验的吊坠存在性契约。
- 让新项链 run 在 `prepare-review`、`record-decision`、Prompt、generation gate 和 QC 中使用同一结构化事实。
- 对无吊坠普通项链实施确定性规则：所有 canonical 自由文本字段不得出现吊坠敏感词，禁止新增吊坠由结构化契约和品类策略表达。
- 保持历史 v1 JSON、run、Prompt、QC 和哈希原样可读取、可检查、可展示。
- 阻止历史 v1 canonical 被用于新的项链决策、重生成或自动升级。

## 3. 非目标

- 不为任意中文自然语言建立通用语义解析器。
- 不自动把历史 v1 canonical 猜测性迁移为 v2。
- 不修改或重写 run03 至 run07 及其他历史 run。
- 不处理真实双层佩戴成功 proof 缺口。
- 不修改并发 HERO、戒指或飞书功能。
- 不把三层自动化兼容扩展成不存在的三圈带链吊坠真实商品。

## 4. Schema v2

### 4.1 顶层版本

`ProductFidelityConstraints.schema_version` 接受 `1` 或 `2`：

- `1`：历史只读格式。
- `2`：支持结构化吊坠语义的新格式。

普通项链和带链吊坠的新建 run 必须使用 v2。手串、戒指和历史 run 可继续使用 v1；本设计不要求把其他品类批量升级到 v2。

### 4.2 `pendant_semantics`

v2 新增顶层对象：

```json
{
  "pendant_semantics": {
    "presence": "absent",
    "count": 0,
    "layer": null,
    "creation_policy": "forbid"
  }
}
```

字段定义：

- `presence`：`present` 或 `absent`。
- `count`：非负整数；第一阶段只能为 `0` 或 `1`。
- `layer`：`null` 或 `1..3` 的整数。
- `creation_policy`：固定为 `forbid`，表示生成过程不得新增、复制或补造未确认的吊坠。

普通项链必须精确为：

```text
presence=absent / count=0 / layer=null / creation_policy=forbid
```

带链吊坠必须精确为：

```text
presence=present / count=1 / layer=ProductAnalysis.pendant_layer / creation_policy=forbid
```

第一阶段没有多吊坠结构，不允许 `count>1`。`layer` 不能超过 `ProductAnalysis.layer_count`。

### 4.3 自由文本规则

v2 的 canonical 语义字段全集包括：

- `detected_keywords[]`
- `must_not_change[]`
- `must_keep[].name`
- `must_keep[].source_text`
- `must_keep[].normalized_keyword`
- `must_keep[].location`
- `must_keep[].visual_shape`
- `must_keep[].relationship`
- `must_keep[].forbid[]`
- `must_keep[].qc_question`

当 `pendant_semantics.presence=absent` 时，上述所有自由文本字段一律不得出现当前吊坠别名集合，包括 `吊坠`、`主吊坠`、`链坠`、`流苏` 和 `坠子`。该规则不区分肯定、否定、连接词或动作顺序。

因此，下面两类文本在 v2 无吊坠 canonical 中都非法：

```text
必须保留既有吊坠
禁止新增吊坠
```

第二类并不是业务上错误，而是必须改由 `pendant_semantics.creation_policy=forbid` 和品类 Prompt 渲染器表达。这样机器不再从自由文本猜测它是“禁止创造”还是“保护既有结构”。

当 `presence=present` 时可以在自由文本中描述吊坠，但必须满足：

- `detected_keywords` 或至少一项 `must_keep[].normalized_keyword` 明确指向吊坠。
- 吊坠 `must_keep` 的位置、所属层、可见形状、连接关系和 QC question 非空。
- 不得在自由文本中声明吊坠缺失或要求生成第二颗吊坠。

## 5. 与 ProductAnalysis 的一致性

v2 校验必须把 `pendant_semantics` 与最终 `ProductAnalysis` 逐字段比较：

| ProductAnalysis | pendant_semantics |
| --- | --- |
| `product_type=necklace` | `presence=absent` |
| `has_pendant=false` | `count=0`、`layer=null` |
| `product_type=pendant_necklace` | `presence=present` |
| `has_pendant=true` | `count=1` |
| `pendant_layer=N` | `layer=N` |

任何不一致都必须在文件替换、决策写入和 provider 调用之前拒绝。错误信息必须同时指出 analysis 值、canonical 值和需要重新执行 `prepare-review` 的动作。

## 6. 生命周期

### 6.1 `prepare-review`

- 最终品类和结构纠正完成后再构建 canonical。
- 普通项链构建 v2 `pendant_semantics=absent/0/null/forbid`。
- 带链吊坠构建 v2 `present/1/pendant_layer/forbid`。
- v2 builder 只从规范化 `ProductAnalysis.product_type/has_pendant/pendant_layer` 确定吊坠结构；不得调用 `_first_matching_alias()` 或其他自由文本词法结果决定 `pendant_semantics`。
- v2 builder 不把“禁止新增吊坠”等品类禁止项写入 canonical 自由文本。
- 自动生成的 v2 必须立即通过结构一致性和自由文本敏感词校验。

### 6.2 人工 review 与 `record-decision`

- 人工可修订视觉事实，但不能删除或绕过 `pendant_semantics`。
- 对现代普通项链/带链吊坠，导入 `schema_version=1` 时拒绝并提示：历史 v1 只读，请重新执行 `prepare-review` 生成 v2。
- 导入 v2 时先校验 analysis SHA-256，再校验 `pendant_semantics` 和全部自由文本字段，全部通过后才进入现有原子事务。
- 不提供自动 v1→v2 升级命令；避免迁移过程重新猜测自然语言。

### 6.3 Prompt

v2 Prompt 的吊坠段只从 `pendant_semantics` 与最终 `ProductAnalysis` 渲染：

普通项链：

```text
主吊坠：无。
禁止新增、补造、复制、悬挂化吊坠，也不得把珠子、跑环或其他元件改成吊坠。
```

带链吊坠：

```text
主吊坠：有；数量：1；所属层：第 N 层。
保持肉眼可见的位置、朝向与连接关系；禁止删除、复制、换层或新增第二颗吊坠。
```

v2 Prompt 不调用自然语言吊坠极性判断。`must_keep` 仍用于产品视觉细节，但无吊坠 v2 已通过零敏感词门禁，因此不会重新引入互斥吊坠要求。

### 6.4 Generation gate

现代 `necklace/pendant_necklace` 生成前必须再次验证：

- `schema_version=2`
- analysis SHA-256 绑定
- `pendant_semantics` 与最终 analysis 一致
- 自由文本规则通过
- review decision snapshot 与最终 analysis 一致

任一失败时 helper 调用次数必须为 0，generation 目录不得出现 submit/result。

### 6.5 QC 与 inspector

- v2 runtime checklist 根据结构化语义生成“无吊坠不得新增”或“现有吊坠数量/所属层/连接关系”检查项。
- `validate_qc_record.py` 和 `inspect_run_artifacts.py` 同时接受历史 v1 与 v2。
- 历史 v1 run 继续按其原始 Prompt、canonical 和 QC 检查，不修改文件。
- inspector 遇到 v1 只报告 `legacy_read_only=true`；不得把它升级、重写或用于新 generation gate。

## 7. v1 兼容边界

### 7.1 允许

- `ProductFidelityConstraints.from_dict()` 读取 v1。
- review HTML、报告、历史 inspector 和 QC validator 读取 v1。
- 历史 run 的原文件、摘要和状态保持不变。

### 7.2 禁止

- v1 普通项链或带链吊坠写入新的 `record-decision`。
- v1 普通项链或带链吊坠调用 `generate`。
- 自动从自由文本推断 `pendant_semantics` 并升级为 v2。
- 通过复制历史 v1 文件到新 run 绕过 v2 门禁。

### 7.3 重新生成路径

如果历史项链需要重新生成，必须建立新 run，并从原产品分析和人工确认事实重新执行 `prepare-review`。新 run 生成独立 v2 canonical、决策、task ID、原图和 QC；历史 run 不覆盖。

## 8. 错误处理

错误信息必须是中文并包含可执行修复动作：

- `schema_version=1`：说明“历史 v1 只读，不得用于新的项链决策或生成，请新建 run 并重新执行 prepare-review”。
- 缺少 `pendant_semantics`：指出 v2 必填对象。
- presence/count/layer 冲突：同时显示 analysis 与 canonical 值。
- 无吊坠自由文本出现敏感词：显示精确字段路径，例如 `must_keep[2].forbid[0]`。
- 带链吊坠缺少可追溯 must_keep：指出缺少的吊坠结构项。

所有错误必须发生在任何原子替换或 provider 调用之前。

## 9. 测试设计

### 9.1 模型与序列化

- v1 JSON 读取与原样导出兼容。
- v2 普通项链和带链吊坠 round-trip。
- v2 缺字段、非法 presence/count/layer/creation_policy 拒绝。
- 手串/戒指 v1 行为不变。

### 9.2 Builder 与结构校验

- 普通项链 builder 输出 v2 absent/0/null/forbid。
- 带链吊坠 builder 输出 v2 present/1/layer/forbid。
- v2 无吊坠自由文本字段矩阵对全部敏感词逐项拒绝。
- v2 带链吊坠必须有吊坠 must_keep，并与 layer 一致。
- analysis/canonical 冲突全部在写入前拒绝。

### 9.3 生命周期

- `prepare-review` 的 unknown 人工纠正后生成正确 v2。
- `record-decision` 拒绝现代项链 v1，且 analysis/decision/canonical 均不改写。
- `generate` 拒绝 v1 或冲突 v2，helper 调用为 0。
- 合法 v2 通过到本地 fake helper，不调用真实 provider。
- 展示模式/长度纠正和参考图复核现有 I2-I4 行为保持。

### 9.4 Prompt、QC 与便携技能

- 普通项链 v2 Prompt 只输出结构化“主吊坠：无/禁止新增”。
- 带链吊坠 v2 Prompt 输出数量和所属层。
- Prompt 不包含 canonical 自由文本中的吊坠敏感词，因为无吊坠 v2 在上游已拒绝。
- QC runtime checklist 与 structured presence/count/layer 一致。
- inspector/QC validator 对历史 v1 正向兼容，对新 v2 正向兼容。

### 9.5 全量门禁

- I1 结构化 v2 聚焦测试全部通过。
- I2-I4 回归全部通过。
- output_role、Windows helper UTF-8、手串、戒指和飞书现有测试不回退。
- `uv run pytest -v` 全量退出 0，stderr 为空。
- 最终独立代码审查确认 I1 关闭；I5 与 HERO 仍单列，不得误报完成。

## 10. 文件职责

预计修改：

- `src/jewelry_on_hand/models.py`：v1/v2 模型、`PendantSemantics` 和 round-trip。
- `src/jewelry_on_hand/product_fidelity.py`：v2 builder、结构一致性、自由文本零敏感词门禁。
- `src/jewelry_on_hand/review_decision.py`：新项链决策强制 v2。
- `src/jewelry_on_hand/generation.py`：新项链生成强制 v2 与重复校验。
- `src/jewelry_on_hand/prompt_builder.py`：从 v2 结构字段渲染吊坠段。
- `src/jewelry_on_hand/qc.py`：从 v2 结构字段生成 runtime checklist。
- `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`：v1 只读与 v2 校验。
- `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`：v2 Prompt 契约。
- `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`：v1/v2 QC 兼容。
- `reference/product-fidelity-constraints-schema.md`、人工流程和技能文档：全文协调 v1/v2 生命周期。

不修改历史 `output/` run，不修改 HERO、戒指或飞书业务逻辑。

## 11. 验收标准

I1 只有在以下条件全部满足时关闭：

1. 新项链 run 使用 schema v2，吊坠语义来自结构字段。
2. 无吊坠 v2 的全部自由文本字段执行零敏感词规则。
3. v1 可读取和检查，但不能用于新的项链决策或生成。
4. v2 Prompt/QC 与 presence/count/layer 精确一致。
5. 所有错误发生在文件替换和 provider 调用之前。
6. 聚焦、便携和全量测试通过。
7. 独立审查确认不再依赖自然语言吊坠极性闭合。

本设计关闭 I1 后，整体规格仍不能宣布完成，直到 I5 真实双层真人佩戴取得原始成图并通过正式 QC；并发 HERO 集成问题继续按独立范围处理。
