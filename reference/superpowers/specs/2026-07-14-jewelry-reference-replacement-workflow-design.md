# 珠宝真人场景参考底图替换工作流设计

## 1. 背景

现有 `jewelry-on-hand-workflow` 同时承担主图、手部佩戴图和生活场景图生成。产品品类策略会向三个角色共同注入“手腕近景佩戴”等画面指令，导致参考图虽然正确提交给模型，构图和生活场景仍可能被重构成泛化的腕部特写。

QY018 和 QY027 已证明当前流程存在两个系统性问题：

1. 参考图只被当成弱构图或氛围提示，未被定义为必须保留的底图。
2. QC 只检查产品结构、人体质量和佩戴物理，没有检查成图是否保留参考图的画面结构。

本设计将当前 Skill 改造成“真人场景首饰替换工作流”。AI 的职责不是围绕参考图重新创作，而是在参考图中移除原首饰并替换为目标产品。

## 2. 已确认决策

- 主图由新的独立 Skill 负责；当前 Skill 不再生成主图。
- 当前 Skill 只接受 `hand_worn` 和 `lifestyle`，收到 `hero` 时必须拒绝。
- 参考图采用结构级严格保留，不要求非编辑区域像素完全不变。
- 结构级保留覆盖手串/手链、普通项链、带链吊坠和戒指。
- 参考图中的全部原首饰必须移除，最终只保留一件目标产品。
- 产品上手图只提供珠宝身份；参考图决定人物、姿势、构图、背景、服装、光线和产品替换位置。
- 参考图选择遵循“硬 gate -> 质量排序 -> 低重复选择”，不得为了随机多样性牺牲参考图质量。

## 3. 目标与非目标

### 3.1 目标

1. 将参考图从弱提示升级为画面结构唯一来源。
2. 将产品上手图限制为产品身份唯一来源。
3. 保证产品品类规则只控制珠宝结构和佩戴物理，不控制景别、机位或人物构图。
4. 在生成前固化参考构图快照，在生成后逐项审计参考图保留情况。
5. 让 `pass` 同时代表参考图保留、原首饰清除、产品保真和佩戴物理全部通过。
6. 保留历史 run 的读取和审计能力，但禁止旧 run 直接进入新生成流程。

### 3.2 非目标

- 不在本设计中实现新的主图 Skill。
- 不要求遮罩外像素完全一致。
- 不实现通用人物换装、换景、重构姿势或摄影再创作。
- 不允许通过裁切、放大或改变景别来弥补参考图中产品展示面积不足。
- 不重新解释或覆盖现有历史 run 的生成产物与决策记录。

## 4. Skill 边界

### 4.1 支持角色

当前 `jewelry-on-hand-workflow` 只支持：

- `hand_worn`：手腕佩戴、手指佩戴，或按项链策略执行手持展示。
- `lifestyle`：半身、全身或带生活环境的人物场景。

全局 `OutputRole.HERO` 继续保留，供新的主图 Skill 使用。当前 Skill 的入口、`prepare-review`、`record-decision` 和 `generate` 均必须拒绝 `hero`，错误信息应明确指向主图 Skill，而不是静默降级或改成 `hand_worn`。

### 4.2 支持品类

- `bracelet`
- `necklace`
- `pendant_necklace`
- `ring`

品类策略继续负责产品结构、数量、连接关系、目标佩戴部位和接触物理。品类策略不得注入无条件景别，例如“手腕近景”“锁骨近景”或“半身上身图”。

## 5. 双图职责与优先级

### 5.1 参考底图

内部图 1 是画面底图，锁定以下结构：

- 人物身份与可见身体区域；
- 身体姿势、手势、手臂角度、手掌朝向和手指关系；
- 服装、发型和人物在画面中的位置；
- 背景、道具和主要环境元素；
- 镜头角度、景别、裁切边界、主体大小和留白；
- 光线方向、明暗关系、色温和整体色调；
- 目标首饰所在身体部位和空间位置。

### 5.2 产品身份图

内部图 2 是产品上手图，仅提供：

- 产品品类；
- 产品数量；
- 珠子、链条、戒圈、主石、吊坠和金属件结构；
- 排列顺序、连接关系、方向和比例；
- 颜色、材质、透明度、纹理和反光；
- 肉眼可见的产品尺寸感。

内部图 2 中的人物、皮肤、手腕、手臂、手、手指、颈部、胸部、服装、头发、脸和背景均不得迁移。

### 5.3 固定优先级

1. 保留参考图画面结构。
2. 移除参考图中的全部原首饰。
3. 在确认的唯一目标位置放入一件目标产品。
4. 保持目标产品与产品上手图一致。
5. 只为真实接触、遮挡、受力和局部阴影做必要重绘。

低优先级规则不得覆盖高优先级规则。产品品类、风格词、推荐使用方式和产品分析不得改变参考图的构图。

## 6. 参考构图快照

### 6.1 候选快照

`prepare-review` 为每张 Top 3 候选生成结构化快照，统一保存到：

```text
analysis/reference_composition_snapshots.json
```

每条快照至少包含：

```json
{
  "rank": 1,
  "reference_file": "RP000000.jpg",
  "reference_sha256": "...",
  "output_role": "hand_worn",
  "framing": "hand_closeup",
  "camera_angle": "front",
  "subject_placement": "手和前臂位于画面中下部",
  "visible_body_regions": ["hand", "wrist", "forearm"],
  "pose": {
    "body": "无躯干",
    "arm": "前臂斜向右上",
    "hand": "掌心朝上",
    "hand_side": "left"
  },
  "clothing": "无可见服装",
  "background": "深色布面",
  "lighting": "左上侧柔光，高对比暗背景",
  "replacement_target": {
    "body_region": "left_wrist",
    "source_jewelry": "single_bracelet",
    "target_product_count": 1
  },
  "other_jewelry_to_remove": ["ring"],
  "text_or_ui_risk": "none"
}
```

### 6.2 人工确认

审核页必须并列展示参考图、产品图和快照。人工选择参考图时同时确认：

- 目标替换位置；
- 原首饰清除范围；
- 人物与身体部位；
- 景别、姿势、背景、服装和光线描述；
- 产品在该参考图中的预计可见面积是否足够。

确认后的单一快照写入：

```text
review/reference_composition_snapshot.json
```

该文件与参考图 SHA-256、输出角色和 `review_decision.json` 绑定。任何一项变化都必须重新执行 `prepare-review`，不得在生成阶段晚绑定或静默修正。

### 6.3 强制停止条件

以下情况不得生成：

- 缺少参考构图快照；
- 快照与参考图 SHA-256 不匹配；
- 快照角色与飞书“图片类型”或 run 角色不一致；
- 无法确认唯一替换位置；
- 多件同类首饰且无法区分目标位置；
- 产品预计展示面积不足；
- 目标部位被严重遮挡；
- 参考图包含大面积文字、手机状态栏或平台 UI；
- 参考图画面结构与角色语义冲突。

## 7. 参考图选择与多样性

### 7.1 唯一角色来源

飞书素材表的“图片类型”字段仍是角色分类唯一来源：

- `hand_worn` 只能使用“手部佩戴图”；
- `lifestyle` 只能使用“生活场景图”；
- 不得用关键词、视觉推测、推荐方式或风格分类替代图片类型。

### 7.2 选择顺序

参考图选择固定分三层：

1. 硬性资格 gate；
2. 质量排序；
3. 合格候选内的低重复选择。

硬 gate 至少检查：

- 角色、品类和替换位置适用；
- 目标位置清晰；
- 展示面积足够；
- 人物、姿势、背景和光线完整；
- 没有大面积文字或 UI；
- 原首饰能够完整识别并清除。

质量排序优先考虑替换可行性、构图完整度和画面质量。产品颜色、材质和风格匹配只作为次要加分。标记“不优先”“复杂叠戴干扰”“目标位置过小”的参考图不得因多样性需求被提升。

### 7.3 低重复算法

为每张合格参考图生成：

```text
composition_signature =
  output_role + framing + pose + background + lighting + replacement_target
```

通过硬 gate 后，以同一 SKU、同一角色的最高合格分为基准。只有 `score >= max_eligible_score - 10` 的候选才能进入多样性池，且多样性池最多保留 3 张。先选择当前批次使用次数较少的 signature，再在使用次数与 score 均相同的候选之间按审计种子随机。多样性优化不得绕过任何硬 gate，也不得选择低于该阈值的参考图。

## 8. Prompt 契约

### 8.1 固定编辑声明

Prompt 必须以以下语义开头：

```text
这是参考底图编辑任务，不是重新设计或重新生成场景。

内部图1是画面底图。锁定内部图1的人物身份、身体姿势、手势、
服装、背景、道具、镜头角度、景别、主体位置、光线方向、色调和留白。

唯一允许修改：
1. 移除内部图1中的全部原首饰及其直接接触阴影；
2. 在确认的目标位置放入内部图2中的一件目标产品；
3. 为新产品重建必要的接触、遮挡、受力和局部阴影；
4. 清除小面积水印或平台标识。

禁止重新生成、裁切、放大、缩小、换景、换姿势、换衣服、
改变人物位置或把生活场景改成产品特写。
```

### 8.2 角色规则

`hand_worn`：

- 产品只能替换到快照指定的手腕、手指或项链手持位置；
- 手侧、手掌朝向、手臂角度、手指姿势和景别必须保留；
- 不得为了展示产品而推进镜头或改变手势。

`lifestyle`：

- 必须保留参考图原有半身、全身或环境景别；
- 人物位置、服装、环境道具和生活氛围必须保留；
- 产品即使在画面中较小，也不得裁成局部特写；
- 展示面积不足时返回参考图选择阶段。

### 8.3 品类规则

品类 Prompt 只描述产品身份和佩戴物理：

- 手串/手链：珠序、主珠、配件、环绕和接触关系；
- 项链/带链吊坠：层数、长度、吊坠所属层、连接和重力关系；
- 戒指：数量、手侧、指位、戒面、戒圈和接触关系。

品类 Prompt 不得无条件包含“手腕近景”“锁骨近景”“半身”“全身”“小红书自然上手图”等构图指令。只有参考构图快照中明确存在的画面属性才能进入 Prompt。

## 9. 生成输入与运行产物

提交模型时固定顺序：

1. 参考底图；
2. 产品身份图。

每个生成目录保存完整输入快照：

```text
generation/NN/
├── scene-reference.jpg
├── product-reference.jpg
├── reference-composition-snapshot.json
├── input-manifest.json
├── model.txt
├── prompt.txt
├── submit.json
├── result.json
├── result.png
└── qc.json
```

`input-manifest.json` 记录两张输入图的原路径、文件名、SHA-256、角色和顺序。现有 `hand-reference.*` 命名停止用于新 run，避免把生活场景或其他参考图误称为手部参考。

## 10. QC 契约

### 10.1 三层检查

整体 `pass` 必须同时满足：

1. `reference_preservation_checks`：参考图画面结构保留；
2. `fidelity_checks`：产品身份和 `must_keep` 保真；
3. `checklist_checks`：品类、佩戴物理、原首饰清除和通用质量检查。

### 10.2 参考保留检查

`reference_preservation_checks` 至少包含：

- `framing_preserved`
- `pose_preserved`
- `subject_placement_preserved`
- `person_preserved`
- `clothing_preserved`
- `background_preserved`
- `lighting_preserved`
- `source_jewelry_removed`
- `replacement_target_preserved`
- `single_target_product`

人工 QC 页面必须同时展示：

```text
参考底图 | 产品身份图 | 生成结果 | 已确认构图快照
```

审核人逐项填写检查结果和可验证备注。不得用统一的“人工 QC 通过”批量填充全部项目。

### 10.3 严重错误

新增错误代码：

- `reference_framing_changed`
- `reference_pose_changed`
- `reference_person_changed`
- `reference_clothing_changed`
- `reference_background_changed`
- `reference_lighting_changed`
- `reference_jewelry_leakage`
- `replacement_target_changed`
- `target_product_duplicated`

以上错误必须 `reject`，不得因产品结构正确降级为 `rerun`。

### 10.4 可重跑问题

仅以下局部问题可使用 `rerun`：

- 产品边缘融合轻微不自然；
- 接触阴影轻微不真实；
- 小面积原首饰残留；
- 产品局部纹理轻微失真但核心结构仍正确。

若参考构图改变，先强化编辑约束重跑一次；再次改变时停止使用该参考图并返回 `prepare-review`。产品结构错误可按现有产品保真策略重跑或切换模型。模型切换不得仅由总失败次数机械决定。

## 11. 校验器与错误恢复

### 11.1 Prompt 校验

校验器必须拒绝：

- 缺少底图锁定声明；
- 缺少唯一允许修改区域；
- 出现与快照冲突的景别、姿势、背景或服装指令；
- 无快照依据的“手腕近景”“半身”“全身”等构图要求；
- `hero` 进入当前 Skill；
- 内部图 1 与内部图 2 职责反转。

### 11.2 快照校验

新增 `validate_reference_snapshot.py`，检查：

- schema 和字段类型；
- SHA-256 与参考图一致；
- 输出角色一致；
- 唯一目标位置存在；
- 目标产品数量为 1；
- 原首饰清除清单合法；
- 快照满足对应角色和品类的最低字段要求。

### 11.3 QC 校验

`validate_qc_record.py` 必须重建当前 run 的参考保留检查、产品保真检查和 runtime checklist。任一检查缺失、重复、结果类型错误或与整体状态不一致时拒绝记录。任何严重错误存在时不得 `pass`。

## 12. Skill 文件结构

```text
skills/jewelry-on-hand-workflow/
├── SKILL.md
├── references/
│   ├── workflow.md
│   ├── prompt-contract.md
│   ├── reference-composition-contract.md
│   ├── qc-checklist.md
│   └── troubleshooting.md
└── scripts/
    ├── validate_prompt_contract.py
    ├── validate_reference_snapshot.py
    ├── validate_qc_record.py
    └── inspect_run_artifacts.py
```

`SKILL.md` 只保留触发范围、强制流程、角色边界和需要读取哪份 reference。详细 schema、Prompt 和 QC 契约放在对应 reference 文件，避免重复和上下文膨胀。

## 13. 迁移与兼容

- 新 schema 只适用于重新执行 `prepare-review` 的 run。
- 历史 run 可以读取、查看和审计，不得直接追加新一轮生成。
- 需要重做的历史 SKU 必须重新执行 `prepare-review -> 人工确认 -> record-decision -> generate -> QC`。
- 不删除或覆盖历史生成目录、决策和 QC。
- 全局保留 `OutputRole.HERO`；当前 Skill 在自身入口拒绝，不影响未来主图 Skill 共用枚举。
- 文档全文修订，不能只在末尾追加与旧规则矛盾的补丁段落。

## 14. 测试范围

### 14.1 单元测试

- 当前 Skill 拒绝 `hero`；
- `hand_worn`、`lifestyle` 覆盖所有支持品类；
- Prompt 包含底图锁定和唯一允许修改区域；
- Prompt 不包含无快照依据的构图指令；
- 产品分析不能覆盖参考构图；
- 快照 SHA-256、角色和目标位置校验；
- 随机多样性只能在合格质量池内执行；
- 低质量候选不能因使用次数少被选中；
- 生成目录保存两张输入图和快照；
- 任何参考保留检查失败时禁止 `pass`；
- 原首饰残留、替换位置变化或产品复制必须 `reject`。

### 14.2 CLI 测试

- `prepare-review` 生成三份候选快照；
- `record-decision` 固化选中快照；
- `generate` 校验参考图与产品图 SHA-256 后提交；
- `qc` 强制完整写入三层检查；
- 历史 run 在缺少新快照时停止生成并给出迁移提示。

### 14.3 真实样例

第一批不回写飞书：

- QY018：验证静物主图不再由当前 Skill 接收；验证手部与生活场景严格保留参考构图。
- QY027：验证手部和生活场景不再收敛为同一种腕部特写。

第二批覆盖手串、项链、带链吊坠和戒指各 2 个 SKU。确认参考构图保留率与产品保真率后，才允许批量生成和飞书回写。

## 15. 验收标准

1. 当前 Skill 对 `hero` 的所有入口均明确拒绝。
2. 每个新 run 都有参考构图候选快照、人工确认快照和生成输入副本。
3. 成图的人物、姿势、景别、服装、背景、光线和目标位置与参考图结构一致。
4. 参考图中的全部原首饰已移除，最终只有一件目标产品。
5. 目标产品结构、颜色、材质、比例和连接关系与产品图一致。
6. 任一参考结构变化、原首饰泄漏、位置变化或产品复制都会被 QC 拒绝。
7. 生活场景图不会为突出产品而自动裁成局部特写。
8. 多样性选择只发生在完整通过硬 gate 且达到质量阈值的候选池内。
9. QY018、QY027 对照实验通过人工逐项审核后，才进入更大批次。
