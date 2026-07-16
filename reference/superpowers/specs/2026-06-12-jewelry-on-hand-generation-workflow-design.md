# 真人参考底图首饰替换工作流设计规格

## 1. 目标

`jewelry-on-hand-workflow` 是真人场景首饰替换流程，不是围绕参考图重新创作画面的生成器。它只支持 `hand_worn` 与 `lifestyle`；`hero` 必须由独立主图 Skill 处理。

参考底图是画面结构唯一来源：人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置全部由它决定。产品上手图只提供目标珠宝身份。模型只能清除参考底图原首饰、在同一位置放入一件目标产品，并重建必要接触、遮挡、受力、局部阴影与小面积水印区域。

非目标：通用换装、换景、换姿势、人物重构、产品摄影再创作、通过裁切放大弥补展示面积不足、覆盖或续写历史 run。

## 2. 支持矩阵

| 产品 | 来源 | 展示 | 结构 |
| --- | --- | --- | --- |
| `bracelet` | `worn_source` | `worn` | 单件单层 |
| `necklace` | `worn_source` | `worn` / `hand_held` | 同一产品 1 至 3 层，无主吊坠 |
| `pendant_necklace` | `worn_source` | `worn` / `hand_held` | 同一产品 1 至 3 层，恰好一个主吊坠 |
| `ring` | `worn_source` | `worn` | 单枚常规指根戒指 |
| `pendant_only` / `unknown` | 可分析 | 不生成 | 停止 |

拒绝 `hand_held_source`、`flat_lay_source`、`unknown_source`、多件独立项链、无链吊坠自动补链和不可见结构推断。项链新 canonical 为 `schema_version=2` 并包含 `pendant_semantics`；戒指确认 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`。

## 3. 双图职责

### 3.1 参考底图

内部图 1 锁定：

- 人物身份与可见身体区域；
- 身体姿势、手势、手臂角度、掌向和手指关系；
- 服装、发型和人物位置；
- 背景、道具和主要环境元素；
- 镜头角度、景别、裁切、主体大小和留白；
- 光线方向、明暗、色温和整体色调；
- 原首饰及目标替换位置。

### 3.2 产品身份图

内部图 2 只提供品类、数量、珠子/链条/戒圈/主石/吊坠/金属件、排列、连接、方向、比例、颜色、材质、透明度、纹理、反光和肉眼可见尺寸。其人物、皮肤、手腕、手臂、手指、颈胸、服装、头发、脸和背景均不得迁移。

如果同一件产品有多张真人产品上手图，可在人工确认同一身份后仅做缩放、留白和确定性拼接，形成同一件产品的多视角身份图。不得使用 AI 修改产品像素，不得使用白底或平铺图补齐视角；审计保存源附件 token、源 SHA-256、拼接顺序和输出 SHA-256。多视角不增加目标数量，结果仍只能出现一件产品。

### 3.3 优先级

保留参考画面结构 -> 清除全部原首饰 -> 同一位置替换一件目标产品 -> 保持产品 canonical -> 只做必要融合。产品分析、品类、风格词和推荐方式不能覆盖参考构图。

## 4. 飞书参考源

飞书素材表的 `图片类型` 字段是角色唯一来源：`hand_worn` 只接收“手部佩戴图”，`lifestyle` 只接收“生活场景图”。不得用关键词、视觉推断、风格或推荐方式替代。

选择顺序：硬 gate -> 质量排序 -> 合格池低重复选择。硬 gate 检查角色、适用品类/展示模式、目标位置、展示面积、画面结构、原首饰可清除性和文字/UI 风险。多样性只能在最高合格分减 10 分以内、最多三张的候选中使用 `composition_signature`；不能提升低质量候选。

全部角色执行深色背景硬 gate；`背景干净` 不能单独放行。`RP000298` 只豁免深色背景判定，不得绕过 `图片类型` gate。`非手腕构图，默认不优先` 在 `lifestyle` 角色下按角色匹配候选处理，不能被手串品类策略误扣。`existing_jewelry`（飞书 `原有首饰类型`）是原首饰判断的唯一来源，不得从 `jewelry_type`、适用品类或历史备注推断原首饰。`background` 和 `lighting` 只抽取各自语义片段，不得拼入整段备注；候选签名与最终快照使用同一抽取结果。

飞书默认只读且 `pending_enrichment=true` 阻断。用户批准临时排除模式时仍完整分页同步、排除 pending 并写 run 内来源快照。enrichment 导入采用写前复读、紧邻写前复读、写后复读和逐记录审计；接口无 revision/if-match，不能声称强 CAS。

## 5. 四阶段生命周期

固定为 `prepare-review -> record-decision -> generate -> qc`。`prepare-review` 与 `record-decision` 显式传 `--output-role`；`generate` 与 `qc` 从 run 固化角色读取并复核，不接受命令行重绑角色。

### 5.1 `prepare-review`

输入：产品上手图、产品 analysis、角色、飞书源（或显式 `--classification` Excel）。输出：最终 analysis、canonical、角色/来源审计、Top 3、源/review 双 SHA、三份候选参考构图快照和人工 review 页面。

人工确认参考人物、姿势、手势、镜头、景别、主体位置、服装、背景、光线、留白、唯一替换位置、原首饰清除范围、展示面积和文字/UI 风险。错误描述必须回源修订并重新运行，不直接改 JSON。

### 5.2 `record-decision`

输入：唯一 selected rank、相同角色、`fidelity_confirmed=true`。输出：完整产品确认快照、canonical、`review/review_decision.json` 与单一 `review/reference_composition_snapshot.json` 的原子绑定。

decision 保存确认快照规范化 JSON 的 `reference_snapshot_sha256`。rank、角色、文件名、源/review SHA、analysis、canonical 或快照冲突时不写任何部分文件，重新 `prepare-review`。

### 5.3 `generate`

只接受 `modern_snapshot`。正式发布前以 staging 固化五输入：

1. `scene-reference.*`；
2. `product-reference.*`；
3. `reference-composition-snapshot.json`；
4. `product-analysis.json`；
5. `product-fidelity-constraints.json`。

`input-manifest.json` 使用 schema v1，记录角色、两张有序 image entries、snapshot/analysis/canonical 的 `copied_file` 和 SHA-256。模型图像顺序固定为 scene 后 product。复制、摘要、Prompt 或 manifest 失败时不发布目录、不调用 provider。

### 5.4 `qc`

人工并列查看参考底图、产品身份图、结果和确认快照。三层为 `reference_preservation`、`fidelity_checks`、`checklist_checks`；任一层缺失或失败都不能 `pass`。

## 6. 参考构图快照

候选文件为 `analysis/reference_composition_snapshots.json`，确认文件为 `review/reference_composition_snapshot.json`。每条严格包含：

- `rank`、`reference_file`、`reference_sha256`、`output_role`；
- `framing`、`camera_angle`、`subject_placement`、`visible_body_regions`；
- `pose.body|arm|hand|hand_side`；
- `clothing`、`background`、`lighting`；
- `replacement_target.body_region|source_jewelry|target_product_count`；
- `other_jewelry_to_remove`、`text_or_ui_risk`、`product_visibility_sufficient`、`composition_signature`。

确认后所有字段不可修改。目标数量固定为 1；多件同类原首饰必须有唯一选择器。`text_or_ui_risk=blocking`、展示面积不足、目标不唯一、字段为空、角色/SHA/rank 冲突都停止。

## 7. Prompt 契约

Prompt 首段必须说明“以参考底图为底图进行编辑”。唯一允许修改：清除全部原首饰与直接阴影、原位置放入一件目标产品、重建必要接触/遮挡/受力/局部阴影、处理小面积水印。

确认快照优先于产品规则。产品 analysis 与 canonical 只控制珠宝身份和佩戴物理：手串珠序与环绕；项链层数、长度、主吊坠和重力；戒指数量、手侧、指位、戒圈/戒面和接触。不得注入快照外“手腕近景”“锁骨近景”“半身”等构图。

`hand_worn` 保持手侧、掌向、手臂、手指和景别；`lifestyle` 保持半身/全身/环境景别、人物、服装、道具和生活环境。`hero` 在构建前拒绝。

Prompt 不超过 1200 字；四输入 validator 同时读取 Prompt、确认快照、analysis、canonical。职责反转、无快照构图、宽泛重绘、角色冲突、摘要错误或 UTF-8 损坏均在 provider 前失败。

## 8. 产品保真

产品上手图是唯一身份图；细节图只用于 review、结构分析和 QC，不得作为第三张模型输入。canonical 绑定最终 analysis 摘要，`--fidelity-constraints-path` 只是导入源。

普通项链保持 `pendant_semantics=absent`；带链吊坠保持 `present`、`pendant_count=1`、实际所属层和连接；不得推断不可见扣头或自动补链。戒指固定单枚、已确认手侧/指位、`finger_base`；不可见戒圈背面不推断。

## 9. 三层 QC

### 9.1 reference_preservation

十项 evidence：`framing_preserved`、`pose_preserved`、`subject_placement_preserved`、`person_preserved`、`clothing_preserved`、`background_preserved`、`lighting_preserved`、`source_jewelry_removed`、`replacement_target_preserved`、`single_target_product`。

### 9.2 fidelity_checks

与 canonical `must_keep` 的名称/问题组合完全一致，覆盖产品品类、数量、结构、排列、连接、颜色、材质、透明度、纹理、反光和比例。

### 9.3 checklist_checks

与当前 analysis、角色和展示模式的 runtime checklist 完全一致，覆盖佩戴物理、原首饰清除、来源人物区域隔离、文字/UI 与输出质量。

状态为 `pass`、`rerun`、`reject`。参考景别、姿势、人物、服装、背景、光线、替换位置或目标数量改变必须 `reject`。首次局部构图问题固定原 rank 纠偏一次，再失败停用参考并重新 `prepare-review`。

## 10. 关键错误代码

参考代码：`reference_framing_changed`、`reference_pose_changed`、`reference_person_changed`、`reference_clothing_changed`、`reference_background_changed`、`reference_lighting_changed`、`reference_jewelry_leakage`、`replacement_target_changed`、`target_product_duplicated`。

产品/物理继续使用 `must_keep_failed`、`category_mismatch`、`core_structure_missing`、`layer_count_mismatch`、`length_category_mismatch`、`pendant_layer_changed`、`multi_layer_restructured`、`auto_chain_added`、`source_person_region_migrated`、`severe_intersection`；戒指使用 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。

## 11. 运行目录

```text
run/
├── input/
├── analysis/
│   ├── product_analysis.json
│   ├── product_fidelity_constraints.json
│   ├── output_role.json
│   ├── selected_references.json
│   └── reference_composition_snapshots.json
├── review/
│   ├── review.html
│   ├── review_decision.json
│   └── reference_composition_snapshot.json
└── generation/NN/
    ├── scene-reference.jpg
    ├── product-reference.jpg
    ├── reference-composition-snapshot.json
    ├── product-analysis.json
    ├── product-fidelity-constraints.json
    ├── input-manifest.json
    ├── prompt.txt
    ├── qc-review.html
    └── qc.json
```

## 12. 三态迁移与历史安全

- `modern_snapshot`：候选、确认、decision digest 完整；已有 generation 时还要求 manifest 和五输入副本完整。只有此态可生成。
- `legacy_read_only`：现代链全部不存在的完整历史 run，只允许读取、检查和审计。
- `damaged`：部分现代文件存在、摘要/路径/固化冲突，必须停止。

历史 run 只读且不得追加 decision、generation 或 QC。要重做历史 SKU，必须新建 run 并重新执行 `prepare-review`。历史 v1 canonical 不补写 `pendant_semantics`、不自动升级；删除现代文件不能把 `damaged` 降级为 legacy。

## 13. 验收

1. 当前 Skill 所有入口拒绝 `hero` 并指向独立主图 Skill。
2. `hand_worn` 与 `lifestyle` 角色只由飞书图片类型决定。
3. 每个现代 run 有候选快照、确认快照、单 rank decision 与五输入 manifest。
4. Prompt 以底图编辑开头，不包含快照外构图。
5. 成图保留人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置。
6. 原首饰全部清除，画面只有一件目标产品，产品 canonical 保真。
7. 三层 QC 完整，严重错误不能 `pass`。
8. 飞书 pending、enrichment 与 CAS 审计可追溯，默认不写回。
9. 历史 run 可审计但不能续写。

测试过程只用离线夹具，产物放 `output/`；不得真实生图、调用付费接口或写回飞书。
