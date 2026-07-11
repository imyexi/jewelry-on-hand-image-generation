# Review 决策与产品确认快照 Schema

`review/review_decision.json` 是提交生成任务前的人工审核凭证。系统在写入决策和读取决策时都会校验动作、产品保真状态，以及项链类产品确认快照与 `analysis/product_analysis.json` 的一致性。任一校验失败时必须停止，不得调用生成接口。

## 1. 决策文件结构

### 1.1 通用字段

| 字段 | 类型 | 规则 |
|---|---|---|
| `action` | 字符串 | 必填；取值见“动作规则”。 |
| `selected_ranks` | 整数数组 | 只允许 `1..3`，不得重复；写入时规范化。 |
| `manual_reference` | 字符串或缺省 | `manual_reference` 动作必填；该动作不能直接生成。 |
| `fidelity_confirmed` | 布尔值 | 生成类动作必须为 `true`。 |
| `fidelity_constraints_path` | 字符串 | 默认 `analysis/product_fidelity_constraints.json`；相对路径以 run 根目录为基准。 |
| `fidelity_notes` | 字符串或缺省 | 仅作说明；关键识别点仍须写入保真约束文件。 |
| `confirmation_snapshot` | 对象或缺省 | 类型安全的产品确认快照；项链生成类动作必填。 |

### 1.2 动作规则

- `generate_rank_1`：只生成 rank 1。`selected_ranks` 缺省或为空时规范化为 `[1]`，显式提供时只能为 `[1]`。
- `generate_selected`：必须且只能选择一个 Top 3 rank。
- `generate_multiple`：必须选择至少两个 Top 3 rank。
- `rerank`：要求重新匹配参考图，不允许进入生成。
- `manual_reference`：记录人工参考图路径，不允许直接进入生成。

## 2. 产品确认快照

`confirmation_snapshot` 保存审核时已经确认的最终产品结构。快照是一个整体：一旦出现，以下字段必须全部存在；允许为空的字段也必须显式写为 `null`，不能删除。

| 字段 | 类型 | 说明 |
|---|---|---|
| `confirmed_product_type` | 枚举字符串 | `bracelet`、`necklace`、`pendant_necklace`、`pendant_only` 或 `unknown`。生成只支持前三类。 |
| `source_image_type` | 枚举字符串 | `worn_source`、`hand_held_source`、`flat_lay_source` 或 `unknown_source`；当前生成阶段只接受 `worn_source`。 |
| `display_mode` | 枚举字符串 | `worn` 或 `hand_held`；手串只允许 `worn`，项链类两种模式均可。 |
| `layer_count` | JSON 整数 | 项链类只允许 1 至 3 层。 |
| `length_category` | 字符串或 `null` | `choker`、`collarbone`、`upper_chest`、`long` 或 `null`。 |
| `has_pendant` | JSON 布尔值 | 是否存在主吊坠。 |
| `pendant_count` | JSON 整数 | 主吊坠数量，不得小于 0。 |
| `pendant_layer` | JSON 整数或 `null` | 主吊坠所属层，不得大于 `layer_count`。 |
| `pendant_position` | 字符串或 `null` | 主吊坠位置，例如 `front_center`。 |
| `pendant_orientation` | 字符串或 `null` | 主吊坠朝向，例如 `front_facing`。 |
| `connection_structure` | 字符串或 `null` | 吊坠和链条的可见连接方式。 |
| `is_independent_multi_item` | JSON 布尔值 | 是否为多件独立项链组合；当前为 `true` 时禁止生成。 |

普通项链必须使用 `has_pendant: false`、`pendant_count: 0`、`pendant_layer: null`。带链吊坠必须使用 `has_pendant: true`、至少一个吊坠和有效的 `pendant_layer`。`pendant_only` 即使结构可解析，也会以“当前版本不支持无链独立吊坠，且禁止自动补链”明确拒绝。

## 3. 自动识别与人工确认

产品分析同时保存自动值和人工确认值：

- `detected_product_type`、`classification_confidence`、`classification_evidence` 保存自动识别结果和原始证据，人工纠正不得覆盖。
- `confirmed_product_type` 保存最终确认品类。
- 任一 CLI 人工纠正发生后，`classification_source` 写为 `manual_override`。
- 纠正参数按字段合并；未提供的参数不覆盖当前分析。
- 合并结果必须重新通过 `ProductAnalysis`、品类与展示模式兼容矩阵、输入图来源和品类策略校验，校验成功后才同时写回 analysis 和决策快照。

`record-decision` 可使用以下纠正参数：

- `--confirmed-product-type`
- `--source-image-type`
- `--display-mode`
- `--layer-count`
- `--length-category`
- `--has-pendant` / `--no-has-pendant`
- `--pendant-count`
- `--pendant-layer`
- `--pendant-position`
- `--pendant-orientation`
- `--connection-structure`
- `--independent-multi-item` / `--no-independent-multi-item`

可空字符串和 `pendant_layer` 可用 `none` 或 `null` 显式清空。所有纠正参数默认都是“不覆盖”。

## 4. 写入与读取 Gate

生成类动作必须满足：

1. 决策文件存在且 JSON、动作和 rank 合法。
2. `fidelity_confirmed` 为 `true`。
3. 产品保真约束文件存在、合法，且 `review_status` 为 `confirmed`、`corrected` 或 `not_applicable`。
4. 最终品类可生成；`unknown` 和 `pendant_only` 明确拒绝。
5. 输入图类型、展示模式、层数和多件独立组合标记符合当前策略。
6. 项链和带链吊坠生成决策包含完整 `confirmation_snapshot`。
7. 快照每个字段与最终 `analysis/product_analysis.json` 一致；任何字段不一致都拒绝。

`validate_decision_against_analysis(decision, analysis)` 提供同一套可调用的严格校验，生成入口可在提交外部任务前再次调用。

## 5. 兼容规则

- 历史手串/手链生成决策可能没有 `confirmation_snapshot`，仍按旧格式读取，并继续执行原有产品保真 Gate。
- 新写入且存在产品分析的决策会保存快照；手串快照存在时也必须与最终 analysis 一致。
- 项链或带链吊坠的生成类决策不允许使用历史缺省，缺快照、少字段或值不一致都会拒绝。
- `rerank`、`manual_reference` 等非生成动作不强制快照，仍不能绕过生成 Gate。

## 6. 示例

### 6.1 带链吊坠生成决策

```json
{
  "action": "generate_selected",
  "selected_ranks": [2],
  "fidelity_confirmed": true,
  "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
  "fidelity_notes": "已确认第二层主吊坠和连接结构",
  "confirmation_snapshot": {
    "confirmed_product_type": "pendant_necklace",
    "source_image_type": "worn_source",
    "display_mode": "worn",
    "layer_count": 2,
    "length_category": "collarbone",
    "has_pendant": true,
    "pendant_count": 1,
    "pendant_layer": 2,
    "pendant_position": "front_center",
    "pendant_orientation": "front_facing",
    "connection_structure": "metal_bail",
    "is_independent_multi_item": false
  }
}
```

### 6.2 历史手串兼容决策

以下旧文件仍可读取，但只适用于可确认的历史手串/手链记录：

```json
{
  "action": "generate_rank_1",
  "selected_ranks": [1],
  "fidelity_confirmed": true,
  "fidelity_constraints_path": "analysis/product_fidelity_constraints.json"
}
```

### 6.3 非生成决策

```json
{
  "action": "rerank",
  "selected_ranks": []
}
```
