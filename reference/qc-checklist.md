# 多品类 QC 检查清单

本清单适用于手串/手链真人佩戴图、普通项链和带链吊坠的真人佩戴或手持展示图，以及单枚常规指根戒指真人佩戴图。新项链 run 必须使用 `schema_version=2` 和必填 `pendant_semantics`；历史 v1 只读，不自动升级。无链独立吊坠、无法识别品类和不受支持的戒指佩戴方式不得进入生成，也不能通过 QC 补救、自动补链或静默换手换指。

QC 结果只能使用以下状态：

- `pass`：所有通用项、品类项、展示模式项和 `must_keep` 均通过。
- `rerun`：产品身份和核心结构正确，只有可修复的手侧、轻微变形、遮挡或接触问题，整体结构仍可辨认。
- `reject`：品类、数量、目标指位、核心结构、多层关系、来源手迁移或严重物理穿透存在错误，需要回到产品分析、参考图或提示词阶段。

不得使用 `pending`、`ok`、`fail` 等其他整体状态。

## 清单来源与记录方式

运行时清单由四部分合并：通用项、品类策略提供的基础项与展示模式项、`product_fidelity_constraints.json` 中每个 `must_keep[].qc_question`，以及 v2 项链从 `pendant_semantics` 精确生成的主吊坠问题。人工 QC 必须逐项检查，并把结构化结果写入 `checklist_checks`；`passed`、`failed` 是面向人的摘要，不能代替逐项记录。不得用布尔值、数字、空字符串或“未检查”代替结论。

标准 run 的记录路径为 `<run>/generation/<rank>/qc.json`。写入器和便携校验器会从该路径同时反推 `<run>/analysis/product_analysis.json` 与 `<run>/analysis/product_fidelity_constraints.json`，在写 `qc.json` 前交叉校验 analysis、canonical 版本与结构化语义，再调用 `build_qc_checklist()` 重建唯一的 runtime checklist。两个文件都不存在时才允许进入 legacy；只存在其中一个属于损坏的现代 run，必须拒绝。

普通项链 v2 固定为 `presence=absent/count=0/layer=null/creation_policy=forbid`，并逐字增加问题 `主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠`。带链吊坠第一阶段固定为 `presence=present/count=1/layer=实际所属层/creation_policy=forbid`，并逐字增加问题 `现有主吊坠数量是否为 {count}，且仍位于第 {layer} 层并保持原连接关系`。QC 不得从 canonical 自由文本里的“禁止”“没有”等极性猜测 presence。

`checklist_checks` 必须对 runtime checklist 做精确、唯一、完整覆盖，且 `pass`、`rerun`、`reject` 三种整体状态都必须记录全量项目。每项格式为：

```json
{
  "id": "qc-dd906be5587ab5a9",
  "question": "主吊坠是否保持原连接？",
  "result": "pass",
  "notes": "位置、朝向和连接均保持"
}
```

稳定 ID 算法为 `"qc-" + SHA-256(question 的 UTF-8 字节).hexdigest()[:16]`。`question` 必须与 runtime checklist 原文逐字一致；不得自行改写问题、复用 ID、遗漏通过项，或只记录失败项。`result` 只能是 `pass`、`rerun`、`fail`。

每次都要检查以下通用项：

1. 产品颜色、材质、透明度、纹理、反光和比例与产品图一致。
2. 元件数量、排列和关键识别点与产品图一致，没有新增、删除或重组结构。
3. 没有迁移产品图中的人物、皮肤、手腕、手臂、颈部、胸部、服装、头发、脸或背景局部。
4. 参考图原有首饰已移除，没有混入戒指、手串、项链或其他饰品。
5. 人物、皮肤、手指、脸部和服装没有明显畸变。
6. 没有文字、水印、平台标识或无关 logo。
7. 不推断产品图不可见的扣头、背面结构或连接细节。

## 手串/手链真人佩戴

除通用项外，必须检查：

- 珠子、主珠、配珠、隔圈、金属件及排列顺序完整。
- 手串真实环绕并贴合手腕，松紧、遮挡和接触阴影自然。
- 手指、手掌、手腕和皮肤纹理自然，无多指、断指、融指或关节错位。
- 手腕宽度、手臂轮廓、肤色和皮肤纹理来自参考图且连续。
- 没有把产品图中的粗手腕、局部手臂、掌纹、指甲或皮肤块连同手串迁移到结果图。

## 戒指真人佩戴

除通用项外，必须检查：

- 画面中只有一枚目标戒指，数量与确认快照一致。
- 戒指位于确认后的左右手和目标手指根部，没有换指、叠戴、指关节佩戴或跨指佩戴。
- 戒面、主石、镶嵌、戒圈粗细、开口、颜色、朝向和装饰排列与产品图可见结构一致。
- 戒圈自然环绕手指，前后遮挡、接触、阴影和皮肤受力真实；不得悬浮、贴片、嵌入或穿透。
- 手指数目、长度、关节、指甲和分离度自然，没有多指、断指、融指或扭曲。
- 没有把产品图中的手、皮肤、指甲、掌纹或背景局部迁移到结果图。
- 不可见戒圈背面、镶嵌背面和其他遮挡结构没有被确定性补写。

## 项链真人佩戴

普通项链和带链吊坠均必须检查：

- 层数为产品确认的一至三层，同一件多层产品的上下顺序正确，不是多件独立项链叠戴；一至三层是运行时能力，不代表存在三圈吊坠商品。
- 双圈普通项链必须仍是同一条连续长链形成 2 层，主吊坠语义为 absent，不得变成两件项链或带链吊坠。
- 长度等级正确；各层落点和层间相对落差与产品图一致。
- 普通项链检查精确 absent 问题；带链吊坠检查结构化 count/layer 问题，所属层、位置、朝向、数量和连接关系正确，不得换层、翻面、复制、移位或脱离连接。
- 链条真实绕颈并在胸前受重力自然垂落，没有断裂或异常悬空。
- 链条没有穿肤、穿衣、穿发或陷入身体，遮挡和阴影符合真实前后关系。
- 衣领和头发没有不合理遮住吊坠或主要结构。
- 多层链没有错误交叉、合并、复制、重排或自动补链。
- 没有迁移产品图中的颈部、胸部、衣服、头发、脸、皮肤块或背景局部。

## 项链手持展示

普通项链和带链吊坠均必须检查：

- 产品结构完整，链条、吊坠、连接件和关键识别点可辨认。
- 手部与链条存在真实接触点，链条受重力自然垂落。
- 手指没有穿透、切断、粘连或不合理夹住链条和吊坠。
- 吊坠和关键结构没有被手指或画面裁切过度遮挡。
- 产品比例合理，没有因近景明显放大或缩小。
- 没有虚构绕颈佩戴链路，也没有自动补链、补扣头或补充不存在的结构。
- 没有迁移产品图中的人物、颈部、胸部、服装、头发、脸、皮肤块或背景局部。

## `must_keep` 判定

每个 `must_keep` 都必须生成且只能生成一条 `fidelity_checks` 记录。记录数量必须与 `must_keep` 数量相等，`name` 必须匹配 `must_keep[].name`，`question` 必须匹配 `must_keep[].qc_question`，name/question 组合不得重复。`result` 只能是 `pass`、`rerun` 或 `fail`。

`fidelity_checks` 是保真约束的具名审计视图，`checklist_checks` 是整个 runtime checklist 的完整执行记录；两者必须同时保留，不能互相替代。对应 `must_keep` 的 question 在两处必须完全相同，`result` 也必须完全一致，否则 writer 与便携校验器都会拒绝。

- 所有结果均为 `pass` 时，整体才可能为 `pass`。
- 关键结构轻微变形但仍可辨认时，可记为 `rerun`，整体不得为 `pass`。
- 关键结构缺失、改款或泛化成普通珠子、链条、隔片时，应记为 `fail`；核心结构缺失时整体必须为 `reject`。

重点包括异形珠、跑环、双尖、回纹、雕刻、貔貅、桶珠、吊坠、流苏、链坠、戒面、主石、镶嵌、戒圈开口，以及它们的位置、方向和相邻连接关系。

## 严重错误 gate

`critical_failures` 使用稳定错误代码。没有关键或严重错误时省略该字段；一旦出现，该字段必须是非空字符串列表，不能写空列表、布尔值或数字。

以下错误至少禁止整体 `pass`：

- `must_keep_failed`：任一 `must_keep` 未通过。
- `layer_count_mismatch`：层数错误。
- `length_category_mismatch`：长度等级错误。
- `pendant_layer_changed`：吊坠换层。
- `source_person_region_migrated`：迁移产品图人物局部。
- `hand_side_mismatch`：戒指左右手与确认结果不一致，可重跑但不得通过。
- `ring_contact_error`：戒圈接触、遮挡或阴影不真实，可重跑但不得通过。
- `finger_deformation`：目标手指出现畸变，可重跑但不得通过。

以下严重错误必须使用 `reject`，不能降级为 `rerun`：

- `category_mismatch`：产品品类错误。
- `core_structure_missing`：核心结构缺失。
- `multi_layer_restructured`：多层关系被重组、合并或复制。
- `auto_chain_added`：自动补链或虚构连接结构。
- `severe_intersection`：链条、吊坠或手部发生严重穿模。
- `ring_count_mismatch`：戒指数量不是确认后的单枚。
- `finger_position_mismatch`：戒指佩戴在错误手指或错误指位。
- `ring_structure_mismatch`：戒圈、开口、镶嵌或装饰排列错误。
- `centerpiece_mismatch`：戒面或主石数量、形状、颜色、朝向错误。
- `source_hand_leakage`：产品图中的手、皮肤、指甲或掌纹迁移到结果图。

局部轻微变形且产品结构仍可辨认时使用 `rerun`；不要为轻微问题误填严重错误代码。

## QC JSON

下列 JSON 为字段结构示例。为控制篇幅，`checklist_checks` 仅展示与错误直接相关的项目；实际写入标准 run 时仍必须包含该 runtime checklist 的全部项目。

带严重错误的记录示例：

```json
{
  "status": "reject",
  "passed": ["无文字、水印或无关 logo"],
  "failed": ["目标戒指从无名指换到中指，且戒面主石形状错误"],
  "fidelity_checks": [
    {
      "name": "圆形主石戒面",
      "question": "主石形状、数量和朝向是否与产品图一致？",
      "result": "fail",
      "notes": "主石被改成方形且佩戴手指错误"
    }
  ],
  "checklist_checks": [
    {
      "id": "qc-3547adf3f38d87b8",
      "question": "主石形状、数量和朝向是否与产品图一致？",
      "result": "fail",
      "notes": "主石被改成方形且佩戴手指错误"
    }
  ],
  "critical_failures": [
    "finger_position_mismatch",
    "centerpiece_mismatch"
  ],
  "notes": "戒指指位和核心结构错误，返回产品分析和提示词阶段"
}
```

通过记录中的 `failed` 必须为空，`fidelity_checks` 中所有结果必须为 `pass`，并省略 `critical_failures`：

```json
{
  "status": "pass",
  "passed": [
    "产品结构、层数和长度等级正确",
    "没有迁移产品图中的人物局部，迁移检查通过"
  ],
  "failed": [],
  "fidelity_checks": [
    {
      "name": "主吊坠",
      "question": "主吊坠是否保持原连接？",
      "result": "pass",
      "notes": "位置、朝向和连接均保持"
    }
  ],
  "checklist_checks": [
    {
      "id": "qc-dd906be5587ab5a9",
      "question": "主吊坠是否保持原连接？",
      "result": "pass",
      "notes": "位置、朝向和连接均保持"
    }
  ],
  "notes": "所有适用品类和展示模式必检项均已通过"
}
```

`status`、`notes` 和列表元素必须使用正确 JSON 类型。`passed` 与 `failed` 不能同时为空；`fidelity_checks` 和 `checklist_checks` 必须是对象列表，各字段类型严格正确。整体 `pass` 要求 `failed` 为空、全部 `fidelity_checks` 为 `pass`、全部 `checklist_checks` 为 `pass`，且没有 `critical_failures`。

## 历史手串兼容与模型兜底

只有 `analysis/product_analysis.json` 与 `analysis/product_fidelity_constraints.json` 同时不存在时，才进入明确的 legacy 兼容分支。历史手串 `qc.json` 不要求批量增加 `fidelity_checks`、`checklist_checks` 或 `critical_failures`；便携校验仍接受旧字段结构，但继续要求明确记录原图手腕、手臂和皮肤块迁移检查。历史 v1 canonical 只允许 inspector、validator 和 QC 只读，inspector 标记 `legacy_read_only=true`，不得改写文件或补写 `pendant_semantics`；历史项链 v1 要继续处理，必须新建 run 并重新执行 `prepare-review`。标准 run 不得通过删除单个分析文件、漏写或传空结构化检查绕过 gate，新记录也不得用宽松 truthy 值绕过类型或状态 gate。

`pass` 不计入 QC 失败次数；`rerun` 和 `reject` 均计入。当前 run 的未通过次数为零或一次时继续使用默认 `gpt_image_2`，超过一次后下一次使用 `nano_banana_v2` 兜底。不得删除或跳过已有非空 `generation/NN/`；缺少 `qc.json` 的目录必须先处理。本次 v2 仅关闭结构化主吊坠语义 I1；I5 真实双圈成功 proof 与 HERO 仍为开放项，不属于本次 QC 契约交付。
