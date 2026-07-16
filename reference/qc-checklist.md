# 真人参考底图替换 QC 检查清单

## 判定原则

人工审核必须并列查看参考底图、产品身份图、生成结果和已确认构图快照。`pass` 同时要求 `reference_preservation`、`fidelity_checks`、`checklist_checks` 三层完整通过；不能用 passed/failed 摘要或一条“人工检查通过”替代逐项 evidence。

- `pass`：三层全通过，无失败、无 `critical_failures`；
- `rerun`：只有局部可纠偏问题，明确记录失败项、证据和下一动作；
- `reject`：参考结构、替换位置、产品身份或核心物理出现严重错误。

## reference_preservation

十项 reference evidence 必须逐条包含稳定 ID、问题、`pass|rerun|fail` 结果和可验证中文备注：

1. `framing_preserved`：镜头、景别、裁切和留白；
2. `pose_preserved`：身体姿势、手势、手臂、掌向和手指关系；
3. `subject_placement_preserved`：人物/手部位置与画面占比；
4. `person_preserved`：人物身份、脸、肤色和可见身体区域；
5. `clothing_preserved`：服装、发型和遮挡；
6. `background_preserved`：背景、道具和环境；
7. `lighting_preserved`：光向、明暗、色温和整体色调；
8. `source_jewelry_removed`：全部原首饰已清除；
9. `replacement_target_preserved`：目标产品位于确认的同一位置；
10. `single_target_product`：只有一件目标产品。

前七项、替换位置或目标数量失败直接 `reject`。小面积原首饰残留首次可 `rerun`，再次失败则 `reject`。

## fidelity_checks

从 generation 固化的 canonical `must_keep` 重建检查集合，`name` 与 `question` 组合必须完全一致。验证品类、数量、结构、排列、连接、方向、颜色、材质、透明度、纹理、反光、尺寸感和核心配件。

- 手串/手链：珠序、主珠、配珠、隔圈、金属件、环绕和松紧；
- 普通项链：同一产品 1 至 3 层、长度和层间落差；`pendant_semantics=absent` 时不新增吊坠；
- 带链吊坠：恰好一个主吊坠、所属层、方向和连接关系；
- 戒指：`ring_count=1`、`hand_side`、`finger_position`、`ring_wear_style=finger_base`，戒圈、戒面/主石和镶嵌一致。

产品上手图只提供珠宝身份。任何产品图人物、手腕、手臂、手指、颈胸、服装、头发、脸、皮肤块或背景迁移都失败。

## checklist_checks

以 analysis、角色、展示模式与 canonical 生成 runtime checklist，ID 集合必须完全一致：

- 原首饰和需清除的其他首饰均消失；
- 新产品只在确认位置出现一次，接触、遮挡、受力和阴影自然；
- `hand_worn` 保持手侧、掌向、手势和景别；
- `lifestyle` 保持人物、服装、道具和生活环境，不改成局部特写；
- 项链不穿肤、穿衣、穿发，不补不可见连接或链条；
- 戒指自然环绕目标手指，无手指畸变和来源手污染；
- 没有大面积文字、状态栏、平台 UI、logo 或残余水印；
- 结果完整清晰，输出格式有效。

## 严重错误代码

参考保留代码：`reference_framing_changed`、`reference_pose_changed`、`reference_person_changed`、`reference_clothing_changed`、`reference_background_changed`、`reference_lighting_changed`、`reference_jewelry_leakage`、`replacement_target_changed`、`target_product_duplicated`。

产品/物理代码：`must_keep_failed`、`category_mismatch`、`core_structure_missing`、`layer_count_mismatch`、`length_category_mismatch`、`pendant_layer_changed`、`multi_layer_restructured`、`auto_chain_added`、`source_person_region_migrated`、`severe_intersection`。

戒指代码：`ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。

`critical_failures` 只能使用允许值且不能重复。任何关键失败存在时不得 `pass`；参考结构、替换位置、产品复制、品类/核心结构、自动补链、严重穿模、戒指数量/指位/戒面结构或来源手污染必须 `reject`。

## 重跑与返回路径

| 失败 | 第一次 | 再次 |
| --- | --- | --- |
| 参考景别、姿势、人物、服装、背景或光线改变 | 固定原 rank，注入 reference 纠偏，只重跑一次 | 停用参考，重新 `prepare-review` |
| 替换位置改变或产品复制 | `reject` | 新建 run，重新确认快照 |
| 小面积原首饰残留 | 强化清除范围 `rerun` | `reject` 并换参考 |
| 边缘、接触或阴影轻微不自然 | 固定原 rank `rerun` | 按保真策略切模型或换参考 |
| 产品结构/canonical 失败 | 只纠偏产品，不改构图 | 再次失败 `reject` |
| 快照、SHA、五输入或 manifest 缺失 | 判定 `damaged`，不进入视觉 QC | 新建 run 并重新 `prepare-review` |

参考失败优先走参考纠偏；产品失败才走产品保真或模型策略，不能用切模型掩盖参考图不适用。

## 记录形状

```json
{
  "status": "reject",
  "passed": ["product_identity"],
  "failed": ["pose_preserved"],
  "notes": "生成结果改变了参考底图手势。",
  "reference_preservation_checks": [],
  "fidelity_checks": [],
  "checklist_checks": [],
  "critical_failures": ["reference_pose_changed"]
}
```

缺项、重复项、空泛备注、非法结果、状态矛盾或乱码都拒绝。历史 run 只读，不得追加 QC；现代三层检查仅用于 `modern_snapshot`，部分存在为 `damaged`。
