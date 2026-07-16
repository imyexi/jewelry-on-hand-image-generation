# CLI 手工串联：真人参考底图首饰替换

## 1. 任务边界

当前工作流只支持 `hand_worn` 和 `lifestyle`，不生成 `hero`。主图必须交给独立主图 Skill。参考底图是人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置的唯一来源；产品上手图只提供珠宝身份。结果只能清除原首饰并在同一位置替换一件目标产品，外加必要接触和局部阴影。

支持产品：

- `bracelet`：`worn_source` + `worn`；
- `necklace`、`pendant_necklace`：`worn_source` + `worn|hand_held`，同一产品 1 至 3 层；
- `ring`：`worn_source` + `worn`，单枚常规指根戒指；
- `pendant_only`、`unknown` 只分析不生成。

拒绝 `hand_held_source`、`flat_lay_source`、`unknown_source`、多件独立项链、无链吊坠自动补链和不可见结构推断。严格顺序为 `prepare-review -> record-decision -> generate -> qc`。

## 2. 运行前准备

从包含 `pyproject.toml` 与 `src/jewelry_on_hand/` 的项目根目录运行。设置 UTF-8，并准备：

- 一张产品上手原图，或同一件产品的多张真人产品上手图；
- 产品分析 JSON；
- 戒指可选的产品细节图（只供 review、结构分析和 QC）；
- `hand_worn` 或 `lifestyle` 角色；
- 默认飞书素材表，或显式提供历史兼容 Excel。

产品分析必须明确 `bracelet`、`necklace`、`pendant_necklace`、`ring`、`pendant_only` 或 `unknown`；项链需要 `schema_version=2` canonical 与 `pendant_semantics`；戒指需要 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`。

多张真人产品上手图只有在人工确认属于同一件产品时，才可通过缩放、留白和确定性拼接形成同一件产品的多视角身份图。不得使用 AI 修改产品像素，不得使用白底或平铺图补齐视角。把源附件 token、源 SHA-256、拼接顺序和输出 SHA-256 写入 `output/` 审计；最终只把拼接图作为一张产品身份输入。

## 3. 参考图来源与审计

默认同步飞书。`图片类型` 字段是角色唯一来源：`hand_worn` 只选“手部佩戴图”，`lifestyle` 只选“生活场景图”。关键词、风格、推荐使用方式和视觉判断不能替代图片类型。

任一 `pending_enrichment=true` 默认阻断。用户明确批准临时批次时才可用 `--ignore-pending-enrichment`；命令仍完整分页同步、排除 pending、保存 `analysis/reference_source_snapshot.json`，且不写回飞书。显式传 `--classification <xlsx>` 时，本地 Excel 作为导入源并优先；不得与 ignore pending 混用。

角色匹配后执行深色背景硬 gate；`背景干净` 不能单独放行。`非手腕构图，默认不优先` 在 `lifestyle` 角色下按角色匹配候选处理，保留半身、行走和环境构图。`RP000298` 只豁免深色背景判定，不得绕过 `图片类型` gate 或其他硬 gate。

## 4. `prepare-review`

```powershell
$env:PYTHONUTF8 = '1'
jewelry-on-hand prepare-review `
  --product-image '<产品上手图>' `
  --analysis-json '<产品分析.json>' `
  --output-role hand_worn `
  --output-root 'output/runs'
```

本地 Excel 模式额外传 `--classification '<参考图库.xlsx>'`。戒指细节图用 `--product-detail-image`。自动分类不确定时，必须在候选评分前用 `--confirmed-product-type`、`--source-image-type`、`--display-mode`、`--layer-count`、项链吊坠参数或戒指确认字段纠正，不能在决策阶段改品类或构图。

检查以下输出：

- `analysis/product_analysis.json` 与 `analysis/product_fidelity_constraints.json`；
- `analysis/output_role.json` 与 `analysis/reference_source_snapshot.json`；
- `analysis/selected_references.json` 的 Top 3 和源/review 双 SHA；
- `analysis/reference_composition_snapshots.json` 的三份候选快照；
- `review/review.html` 中产品、参考图和结构字段。

人工确认每个候选的人物、身体区域、姿势、手势、镜头、景别、主体位置、服装、背景、光线、留白、唯一替换位置、原首饰清除范围、展示面积与文字/UI 风险。自动 Top 3 不是用户决策。候选描述错误时修订飞书语义源并重新运行本阶段，不直接改 JSON。

## 5. `record-decision`

一次只选一个 rank：

```powershell
jewelry-on-hand record-decision `
  --run-root '<run目录>' `
  --output-role hand_worn `
  --action generate_rank_1 `
  --selected-ranks 1 `
  --fidelity-confirmed
```

需要导入人工纠正的保真约束时加 `--fidelity-constraints-path '<约束.json>'`。它只是导入源；系统验证 `product_analysis_sha256` 后，标准 canonical 仍写入 `analysis/product_fidelity_constraints.json`。非标准路径、晚期重绑或摘要不一致应拒绝。

写入 gate 同时验证：

- 角色与 `analysis/output_role.json` 和飞书图片类型一致；
- 单一 selected rank 存在；
- 源图、review 副本、rank 与 SHA 绑定未变；
- 完整产品确认快照、analysis 和 canonical 完全一致；
- 候选快照已人工确认，唯一位置与目标数量合法；
- decision 包含 `fidelity_confirmed=true` 并绑定 `reference_snapshot_sha256`。

成功后得到 `review/review_decision.json` 与 `review/reference_composition_snapshot.json`。任一冲突都不写部分文件，并要求重新 `prepare-review`。

## 6. `generate`

```powershell
jewelry-on-hand generate `
  --run-root '<run目录>' `
  --helper-script 'skills/aireiter-image-generation/scripts/aireiter_image_helper.py'
```

只允许 `modern_snapshot`。提交前再次验证 decision、确认快照、源/review SHA、角色、产品分析和 canonical，并以 staging 固化五输入：

1. `scene-reference.*`；
2. `product-reference.*`；
3. `reference-composition-snapshot.json`；
4. `product-analysis.json`；
5. `product-fidelity-constraints.json`。

`input-manifest.json` 记录角色、两张有序 image entries、其余三份 `copied_file` 与全部 SHA-256。模型输入顺序固定为 scene 后 product。复制、摘要、Prompt 或 manifest 任一步失败都不发布 generation，也不提交任何 helper job。

Prompt 必须以“参考底图编辑任务”开头，只允许清除原首饰、原位置替换一件产品和必要融合。产品规则只控制珠宝结构与佩戴物理，不得改变参考构图。

## 7. `qc`

先查看 generation 中的四栏审核页，再准备三份逐项 JSON：

```powershell
jewelry-on-hand qc `
  --generation-dir '<run目录>/generation/01' `
  --status pass `
  --reference-preservation-checks-json '<reference.json>' `
  --fidelity-checks-json '<fidelity.json>' `
  --checklist-checks-json '<checklist.json>'
```

存在严重参考姿势错误时，`reject` 示例必须传实际错误码：

```powershell
jewelry-on-hand qc `
  --generation-dir '<run目录>/generation/01' `
  --status reject `
  --reference-preservation-checks-json '<reference.json>' `
  --fidelity-checks-json '<fidelity.json>' `
  --checklist-checks-json '<checklist.json>' `
  --critical-failures reference_pose_changed
```

三层要求：

- `reference_preservation`：十项 evidence，覆盖景别、姿势、主体位置、人物、服装、背景、光线、原首饰清除、替换位置和单件目标；
- `fidelity_checks`：与 canonical `must_keep` 完全一致；
- `checklist_checks`：与当前角色、品类和展示模式的 runtime checklist 完全一致。

参考景别、姿势、人物、服装、背景、光线、位置或数量改变，产品身份/核心结构错误，或来源人体区域迁移都是严重错误并 `reject`。只有小范围边缘、接触或阴影问题可 `rerun`。参考构图第一次失败固定同一 rank 纠偏一次，再失败停用参考并重新 `prepare-review`。错误说明使用中文，`critical_failures` 必须合法且不重复。

戒指人工 QC 还要检查参考字段：左右手、可见手指、手部朝向、戒面可见度、手指分离度、手指遮挡风险。使用 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage` 路由。

## 8. Dry run

不真实生成时，只执行 `prepare-review` 并人工检查 Top 3、候选快照和 review 页面；可运行便携 validator 与 inspector，但不要执行 provider、不要伪造 decision/generation/QC。dry run 只证明离线 gate 可执行。

## 9. 三态与历史

- `modern_snapshot`：候选快照、确认快照、decision digest 完整；已有 generation 还需五输入与 manifest 完整。
- `legacy_read_only`：现代链全部不存在的完整历史 run，仅可读取、检查和审计。
- `damaged`：部分现代文件存在、摘要冲突、路径逃逸或固化不完整，必须停止。

历史 run 只读且不得追加 decision、generation 或 QC。历史手串也只能检查和审计；旧 SKU 要重做时，新建 run 并重新执行 `prepare-review`。历史 v1 canonical 不补写 `pendant_semantics`，不自动升级。

五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

## 10. 最终交付

只交付当前 run 中三层 QC 均完整且 `status=pass` 的结果。不得把本地测试、mock、命令成功或 provider 任务完成写成视觉验收。真实第三方模型 proof 属于 Task 12，尚未完成。
