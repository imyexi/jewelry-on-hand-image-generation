# 真人参考底图替换 QC

## 总体规则

每个 generation 必须人工对照四栏：参考底图、产品身份图、生成结果、已确认构图快照。`pass` 必须同时覆盖 `reference_preservation`、`fidelity_checks`、`checklist_checks` 三层；任一层缺失、重复、类型错误、与状态冲突或备注不可验证，都拒绝写入。

状态只允许：

- `pass`：三层全部通过，`failed=[]`，不存在 `critical_failures`；
- `rerun`：只有允许纠偏的局部问题，必须记录失败项和下一次动作；
- `reject`：存在严重结构错误、参考画面破坏、产品身份错误或来源污染。

## 第一层：reference_preservation

十项 reference evidence 必须逐项记录 `id`、`question`、`result`、`notes`，不得用一条“人工检查通过”批量代替：

1. `framing_preserved`：景别、镜头、裁切和留白是否保留；
2. `pose_preserved`：身体姿势、手势、手臂角度、掌向和手指关系是否保留；
3. `subject_placement_preserved`：人物/手部位置与画面占比是否保留；
4. `person_preserved`：人物身份、脸、肤色和可见身体区域是否保留；
5. `clothing_preserved`：服装、发型及遮挡关系是否保留；
6. `background_preserved`：背景、道具和环境元素是否保留；
7. `lighting_preserved`：光向、明暗、色温和整体色调是否保留；
8. `source_jewelry_removed`：参考底图原首饰是否全部清除；
9. `replacement_target_preserved`：目标产品是否位于快照确认的同一位置；
10. `single_target_product`：画面是否只有一件目标产品，没有复制或新增同类首饰。

任一 reference evidence 失败都不能 `pass`。景别、姿势、人物、服装、背景、光线、替换位置或目标数量改变属于严重错误并 `reject`；小面积原首饰残留可在首次出现时 `rerun`，再次出现则 `reject`。

## 第二层：fidelity_checks

从 `product-fidelity-constraints.json` 的 canonical `must_keep` 重建完整检查集合；`name` 与 `question` 的组合必须完全一致，不得少项、改题、重复或用自由文本代替。

公共保真项目：品类、数量、颜色、材质、透明度、纹理、尺寸感、排列、连接、方向和核心配件。产品上手图只提供珠宝身份，不得把其中的人物、手腕、手臂、手指、颈胸、服装、头发、脸、皮肤块或背景迁移到结果。

- 手串/手链：珠序、主珠、配珠、隔圈、金属件、环绕和松紧。
- 普通项链：同一产品 1 至 3 层、长度等级和层间落差；`pendant_semantics=absent` 时不得新增吊坠。
- 带链吊坠：恰好一个主吊坠、所属层、方向和连接关系不得改变。
- 戒指：`ring_count=1`、`hand_side`、`finger_position`、`ring_wear_style=finger_base`，戒圈、戒面/主石和镶嵌结构一致；不可见戒圈背面不作推断。

品类错误、核心结构缺失、产品复制、主吊坠结构改变、自动补链、戒指数量/指位/戒面结构错误或产品图人体迁移必须 `reject`。

## 第三层：checklist_checks

依据当前 analysis、角色、展示模式和 canonical 调用 runtime checklist，完整覆盖：

- 参考底图原首饰及其他首饰已按快照清除；
- 新产品只在确认位置替换，接触、遮挡、受力和局部阴影自然；
- `hand_worn` 保持手侧、掌向、手势和景别；
- `lifestyle` 保持人物、服装、道具和生活环境，不收敛成产品特写；
- 项链不穿肤、穿衣、穿发，不虚构扣头或不可见连接；
- 戒指自然环绕目标手指，无手指畸变或产品源手污染；
- 无大面积文字、状态栏、平台 UI、logo 或残余水印；
- 结果完整清晰，输出尺寸与格式符合运行约束。

`checklist_checks` 的稳定 ID 集合必须与 runtime checklist 完全一致。不得用 passed/failed 摘要替代逐项记录。

## critical_failures

参考画面严重代码：

- `reference_framing_changed`
- `reference_pose_changed`
- `reference_person_changed`
- `reference_clothing_changed`
- `reference_background_changed`
- `reference_lighting_changed`
- `reference_jewelry_leakage`
- `replacement_target_changed`
- `target_product_duplicated`

产品与物理代码继续使用：`must_keep_failed`、`category_mismatch`、`core_structure_missing`、`layer_count_mismatch`、`length_category_mismatch`、`pendant_layer_changed`、`multi_layer_restructured`、`auto_chain_added`、`source_person_region_migrated`、`severe_intersection`。

戒指代码为 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。

`critical_failures` 只能包含允许代码、不能重复。任何代码存在时不得 `pass`；参考结构、品类、核心结构、产品复制、自动补链、严重穿模、戒指数量/指位/结构/主石或来源手污染必须 `reject`。

## 重跑路由

| 失败 | 第一次动作 | 再次失败 |
| --- | --- | --- |
| 参考景别/姿势/人物/服装/背景/光线改变 | 固定原 rank，注入对应 reference 纠偏，仅重跑一次 | 停用该参考，重新 `prepare-review` |
| 替换位置改变或产品复制 | `reject` | 新建 run，重新审核快照 |
| 小面积原首饰残留 | 固定原 rank，强化清除范围 | `reject` 并换参考 |
| 边缘、接触或阴影轻微不自然 | 固定原 rank `rerun` | 按产品保真策略切模型或换参考 |
| 产品结构或 canonical 失败 | 按失败项纠偏；不得改快照构图 | 再次失败则 `reject` |
| 五输入、SHA、manifest 或快照缺失 | 不进入 QC，判定 `damaged` | 重新 `prepare-review`，不修补旧 run |

模型切换不能掩盖参考图不适用。参考结构失败优先走参考纠偏/换参考；产品结构失败才走产品保真纠偏或模型策略。

## QC JSON 形状

```json
{
  "status": "rerun",
  "passed": ["已验证项目"],
  "failed": ["lighting_preserved"],
  "notes": "结果主光方向与参考底图不一致；固定同一 rank 纠偏重跑一次。",
  "reference_preservation_checks": [],
  "fidelity_checks": [],
  "checklist_checks": [],
  "critical_failures": ["reference_lighting_changed"]
}
```

所有字段以 UTF-8 写入，`notes` 使用中文且指向可见证据。空 `critical_failures` 按 CLI 约定表达，不得伪造空字符串代码。

## 历史边界

历史 run 只读，可由 inspector 按旧规则审计，但不得追加新的 QC 或 generation。现代三层 QC 只对 `modern_snapshot` 有效；部分现代文件存在时是 `damaged`，不能删除文件降级为历史。需要重做必须新建 run 并重新 `prepare-review`。
