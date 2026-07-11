# Review 决策与产品确认快照 Schema

`review/review_decision.json` 是提交生成任务前的人工审核凭证。系统在写入决策和读取决策时都会校验动作、产品保真状态，以及项链类或戒指产品确认快照与 `analysis/product_analysis.json` 的一致性。任一校验失败时必须停止，不得调用生成接口。

## 1. 决策文件结构

### 1.1 通用字段

| 字段 | 类型 | 规则 |
|---|---|---|
| `action` | 字符串 | 必填；取值见“动作规则”。 |
| `selected_ranks` | 整数数组 | 只允许 `1..3`，不得重复；写入时规范化。 |
| `manual_reference` | 字符串或缺省 | `manual_reference` 动作必填；该动作不能直接生成。 |
| `fidelity_confirmed` | JSON 布尔值 | 生成类动作必须为真正的 JSON `true`；字符串 `"true"`、`"yes"`、`"1"` 和数字 `1` 均非法。 |
| `fidelity_constraints_path` | 字符串 | 默认 `analysis/product_fidelity_constraints.json`；相对路径以 run 根目录为基准。 |
| `fidelity_notes` | 字符串或缺省 | 仅作说明；关键识别点仍须写入保真约束文件。 |
| `confirmation_snapshot` | 对象或缺省 | 类型安全的产品确认快照；项链和戒指生成类动作必填。 |

### 1.2 动作规则

- `generate_rank_1`：只生成 rank 1。`selected_ranks` 缺省或为空时规范化为 `[1]`，显式提供时只能为 `[1]`。
- `generate_selected`：必须且只能选择一个 Top 3 rank。
- `generate_multiple`：必须选择至少两个 Top 3 rank。
- `rerank`：要求重新匹配参考图，不允许进入生成。
- `manual_reference`：记录人工参考图路径，不允许直接进入生成。

## 2. 产品确认快照

`confirmation_snapshot` 保存审核时已经确认的最终产品结构。基础快照是一个整体：一旦出现，原有项链/吊坠字段必须全部存在；允许为空的字段也必须显式写为 `null`，不能删除。四个戒指字段只在 `confirmed_product_type=ring` 时落盘并全部必填；其他品类在模型内部按 `0/unknown` 处理，但不改变历史快照 JSON 结构。

| 字段 | 类型 | 说明 |
|---|---|---|
| `confirmed_product_type` | 枚举字符串 | `bracelet`、`necklace`、`pendant_necklace`、`pendant_only`、`ring` 或 `unknown`。 |
| `source_image_type` | 枚举字符串 | `worn_source`、`hand_held_source`、`flat_lay_source` 或 `unknown_source`；当前生成阶段只接受 `worn_source`。 |
| `display_mode` | 枚举字符串 | `worn` 或 `hand_held`；手串和戒指只允许 `worn`，项链类两种模式均可。 |
| `layer_count` | JSON 整数 | 项链类只允许 1 至 3 层。 |
| `length_category` | 字符串或 `null` | `choker`、`collarbone`、`upper_chest`、`long` 或 `null`。 |
| `has_pendant` | JSON 布尔值 | 是否存在主吊坠。 |
| `pendant_count` | JSON 整数 | 主吊坠数量，不得小于 0。 |
| `pendant_layer` | JSON 整数或 `null` | 主吊坠所属层，不得大于 `layer_count`。 |
| `pendant_position` | 字符串或 `null` | 主吊坠位置，例如 `front_center`。 |
| `pendant_orientation` | 字符串或 `null` | 主吊坠朝向，例如 `front_facing`。 |
| `connection_structure` | 字符串或 `null` | 吊坠和链条的可见连接方式。 |
| `is_independent_multi_item` | JSON 布尔值 | 是否为多件独立项链组合；当前为 `true` 时禁止生成。 |
| `ring_count` | JSON 整数 | 戒指必须为 `1`；非戒指品类为 `0`。旧项链快照缺失时兼容读取为 `0`。 |
| `hand_side` | 枚举字符串 | `left`、`right`、`unknown`；戒指必须明确，非戒指为 `unknown`。 |
| `finger_position` | 枚举字符串 | `thumb`、`index`、`middle`、`ring`、`little`、`unknown`；戒指必须明确。 |
| `ring_wear_style` | 枚举字符串 | 第一阶段戒指必须为 `finger_base`；`midi`、`cross_finger` 和 `unknown` 不可生成。 |

普通项链必须使用 `has_pendant: false`、`pendant_count: 0`、`pendant_layer: null`。带链吊坠必须使用 `has_pendant: true`、至少一个吊坠和有效的 `pendant_layer`。戒指必须使用单枚、明确左右手、明确目标手指和 `finger_base`，并保持所有项链/吊坠字段为空结构。`pendant_only` 即使结构可解析，也会以“当前版本不支持无链独立吊坠，且禁止自动补链”明确拒绝。

## 3. 自动识别与人工确认

产品分析同时保存自动值和人工确认值：

- `detected_product_type`、`classification_confidence`、`classification_evidence` 保存自动识别结果和原始证据，人工纠正不得覆盖。
- `confirmed_product_type` 保存最终确认品类。
- 任一 CLI 人工纠正发生后，`classification_source` 写为 `manual_override`。
- 纠正参数按字段合并；未提供的参数不覆盖当前分析。
- 合并结果必须重新通过 `ProductAnalysis`、品类与展示模式兼容矩阵、输入图来源和品类策略校验，校验成功后才同时写回 analysis 和决策快照。
- 上述确认后 analysis 校验与 decision action 无关；即使 action 是 `rerank` 或 `manual_reference`，只要提供了人工纠正参数，也不得写入 `unknown`、无链独立吊坠、非法输入来源、非法展示模式、非法层数或不支持的结构。

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
6. 项链、带链吊坠和戒指生成决策包含完整 `confirmation_snapshot`；旧项链快照可以缺少戒指字段并按 `0/unknown` 读取，现代戒指快照不得缺少任一戒指字段。
7. 快照每个字段与最终 `analysis/product_analysis.json` 一致；任何字段不一致都拒绝。

`validate_decision_against_analysis(decision, analysis)` 提供同一套可调用的严格校验，生成入口可在提交外部任务前再次调用。

`validate_confirmed_analysis(analysis)` 提供与 action 无关的确认后 analysis 校验。CLI 只要收到任一人工纠正参数，必须在写文件前调用该接口；没有纠正参数的历史非生成动作保持原行为。

人工纠正成功落盘时，analysis 与 decision 使用同一双文件提交过程：先在各自目标目录完整写入并同步临时 JSON，再以 `os.replace` 替换正式文件。若任一次写入或第二次替换失败，系统会用原文件字节原子恢复已经替换的文件；原文件不存在时移除新文件，并清理临时文件。CLI 返回明确中文错误和非零状态，不保留半更新状态。

## 5. 兼容规则

- 历史手串/手链生成决策可能没有 `confirmation_snapshot`，仍按旧格式读取，并继续执行原有产品保真 Gate。
- 新写入且存在产品分析的决策会保存快照；手串快照存在时也必须与最终 analysis 一致。
- 项链、带链吊坠或戒指的生成类决策不允许缺少快照；戒指快照缺少单枚、左右手、指位或佩戴方式任一字段都会拒绝。
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
