---
name: jewelry-on-hand-workflow
description: "用于需要在真人手部佩戴图或生活场景参考底图中替换首饰，并严格保留原人物、姿势、构图、服装、背景与光线时。"
---

# 真人参考底图首饰替换

## 角色边界

- 只支持 `hand_worn` 和 `lifestyle`。收到 `hero` 时立即拒绝；主图必须交给独立主图 Skill，不得静默降级角色。
- 参考底图是画面结构唯一来源。锁定人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置。
- 产品上手图只提供珠宝身份。不得迁移其中的人物、皮肤、手腕、手臂、手指、颈部、胸部、服装、头发、脸或背景。
- 只移除参考底图中的原首饰，在同一位置放入一件目标产品；只允许补充必要接触、遮挡、受力、局部阴影和小面积水印处理。

在当前工作区运行 `jewelry-on-hand`。向上定位同时包含 `pyproject.toml` 与 `src/jewelry_on_hand/` 的项目根目录；`skills/aireiter-image-generation/` 只在真正生成且已通过所有 gate 时使用。不要依赖机器绝对路径。

## 支持的产品

- `bracelet`：`worn_source`，`display_mode=worn`，单件单层。
- `necklace`：`worn_source`，`worn` 或 `hand_held`，同一产品 1 至 3 层。
- `pendant_necklace`：与项链相同，但必须保留 `schema_version=2` 的 `pendant_semantics` 与恰好一个主吊坠。
- `ring`：`worn_source`，`worn`，单枚常规指根戒指；确认 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`。
- `pendant_only`、`unknown` 只允许分析，不得生成；无链吊坠不得自动补链。

拒绝 `hand_held_source`、`flat_lay_source`、`unknown_source`、多件独立项链、不可见结构推断或来源图冲突。品类规则只控制珠宝结构和佩戴物理，不能改变参考底图的景别、人物或构图。

## 核心原则

优先级固定：保留参考画面结构 -> 清除全部原首饰 -> 在确认位置替换一件目标产品 -> 保持产品 canonical 保真 -> 仅做必要融合。任何低优先级指令与已确认参考快照冲突时停止，不猜测、不折中。

飞书素材表的 `图片类型` 字段是角色唯一来源：`hand_worn` 仅接收“手部佩戴图”，`lifestyle` 仅接收“生活场景图”。不得用关键词、视觉推断、推荐使用方式或风格字段替代。默认飞书同步只读；只有显式传入 `--classification` 时才优先使用本地 Excel。

## 四阶段强制流程

严格按 `prepare-review -> record-decision -> generate -> qc` 执行，不得跳步、补写或倒序。

1. `prepare-review`：显式传 `--output-role hand_worn|lifestyle`，完成产品分析、canonical、飞书候选硬 gate、Top 3、候选参考构图快照和人工 review 包。不得自动生成决策。
2. `record-decision`：人工只能选择一个 rank；同时确认产品保真和参考构图快照。角色、rank、源图/review 双 SHA、analysis、canonical 或快照冲突时停止并重新执行 `prepare-review`。
3. `generate`：只接受完整的 `modern_snapshot`。提交前固化五输入：`scene-reference.*`、`product-reference.*`、`reference-composition-snapshot.json`、`product-analysis.json`、`product-fidelity-constraints.json`，并写 `input-manifest.json`；模型图像顺序固定为参考底图、产品身份图。
4. `qc`：同时完成 `reference_preservation`、`fidelity_checks`、`checklist_checks` 三层检查。参考结构改变、原首饰泄漏、替换位置改变或产品复制均是严重错误并 `reject`。

## 强制 Gate

- 产品分析五个现代分类字段完整；最终品类、来源、展示模式、层数和结构合法。
- 新项链 canonical 为 `schema_version=2`，包含 `pendant_semantics`；分析、完整产品确认快照与 canonical 完全一致。
- 戒指参考审核覆盖左右手、可见手指、手部朝向、戒面可见度、手指分离度、手指遮挡风险；关键失败包括 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。
- 产品上手图是生成阶段唯一产品身份图；细节图只用于 review、结构分析和 QC，不得作为第三张模型输入。
- `--fidelity-constraints-path` 只作为 `record-decision` 的导入源；canonical 必须落在 `analysis/product_fidelity_constraints.json`，非标准路径或摘要不匹配时拒绝。
- 生成决策必须绑定单一 rank、`fidelity_confirmed=true`、确认快照摘要和不变的源/review 文件 SHA。
- Prompt 必须从确认快照取构图，只能修改允许区域；任何五输入或 manifest 摘要不一致都在 provider 调用前停止。
- 只有三层 QC 全部覆盖且 `critical_failures` 合法时才可 `pass`；严重错误必须 `reject`，错误用中文报告。

## 按需读取

- 完整 CLI、输入输出、人工确认和 dry run：读 [工作流](references/workflow.md)。
- Prompt 层序、双图职责和冲突停止：读 [Prompt 契约](references/prompt-contract.md)。
- 快照 schema、绑定、不可编辑字段和三态迁移：读 [参考构图契约](references/reference-composition-contract.md)。
- 三层 QC、十项证据、状态和错误码：读 [QC 清单](references/qc-checklist.md)。
- SHA、角色、快照、历史、构图漂移和退出码恢复：读 [故障排查](references/troubleshooting.md)。

详细 schema 只在对应 reference 维护；不要在此复制或另建 README/CHANGELOG。

## 历史与安全边界

`modern_snapshot` 表示候选快照、确认快照、decision digest 与 generation 固化链完整；全部新参考文件缺失的旧 run 是 `legacy_read_only`；部分存在或不一致是 `damaged`。历史 run 只读，可检查和审计但不得追加 decision、generation 或 QC。要重做旧 SKU，必须新建 run 并重新执行 `prepare-review`。

历史 v1 canonical 只读，不得补写 `pendant_semantics` 或自动升级。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

默认不写回飞书，不联网补数据，不覆盖历史产物，不把 dry run、mock 或本地测试称为真实生成验收。真实第三方模型 proof 属于 Task 12，尚未完成。
