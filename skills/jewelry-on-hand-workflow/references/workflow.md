# 真人参考底图首饰替换 Workflow

## 范围与不变量

本 Skill 只处理 `hand_worn` 与 `lifestyle`；`hero` 必须交给独立主图 Skill。参考底图是人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置的唯一来源，产品上手图只提供珠宝身份。只允许移除原首饰、在原位置换入一件目标产品，以及重建必要接触和局部阴影。

支持 `bracelet`、`necklace`、`pendant_necklace`、`ring`。`necklace` 与 `pendant_necklace` 可为 `worn` 或 `hand_held`、同一产品 1 至 3 层；`pendant_only`、`unknown` 只分析不生成。输入必须是 `worn_source`；拒绝多件独立项链、无链吊坠自动补链，以及对不可见结构的推断。

四阶段顺序固定为 `prepare-review -> record-decision -> generate -> qc`。

## 参考源

默认同步飞书素材表；`图片类型` 字段是角色唯一来源：

- `hand_worn` 只接收“手部佩戴图”；
- `lifestyle` 只接收“生活场景图”；
- 关键词、风格、推荐使用方式和视觉判断不得替代该字段。

角色匹配后继续执行深色背景硬 gate。明确的深色、黑色、暗色背景/布景、低调暗色背景、黑色支撑面或深色沥青路面可以通过；`背景干净` 不能单独放行。`非手腕构图，默认不优先` 在 `lifestyle` 角色下按角色匹配候选处理，不得把半身、行走或环境生活场景按手串品类误判为不合格。人工确认的 `RP000298` 只豁免深色背景判定，不得绕过 `图片类型` gate 和其他硬 gate。

默认任一 `pending_enrichment=true` 都阻断。用户明确批准临时排除待补全记录时才可传 `--ignore-pending-enrichment`；系统仍完整分页同步并把过滤审计写入 `analysis/reference_source_snapshot.json`，不写回飞书。显式传入 `--classification <xlsx>` 时，本地 Excel 作为历史兼容导入源并优先于飞书；它与 `--ignore-pending-enrichment` 互斥。

## 1. `prepare-review`

先准备产品上手原图和产品分析 JSON；戒指可额外提供细节图，但细节图只用于 review、结构分析和 QC。命令必须显式传入支持角色：

如果飞书为同一件产品提供多张真人产品上手图，先确认它们确属同一件产品，再仅做缩放、留白和确定性拼接，形成同一件产品的多视角身份图。不得使用 AI 修改产品像素，不得使用白底或平铺图补齐视角。审计必须记录源附件 token、源 SHA-256、拼接顺序和输出 SHA-256；拼接图仍作为唯一 `--product-image`，不能拆成多件产品或多张模型输入。

```powershell
jewelry-on-hand prepare-review `
  --product-image <产品上手图> `
  --analysis-json <产品分析.json> `
  --output-role hand_worn `
  --output-root <输出目录>
```

使用本地分类表时额外传 `--classification <参考图库.xlsx>`。需要人工纠正时，在评分前使用 `--confirmed-product-type`、`--source-image-type`、`--display-mode`、`--layer-count` 等参数；项链还可纠正长度和 `pendant_semantics`，戒指分析需确认 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`。

该阶段输出并冻结：

- `input/product-on-hand.*` 与 `analysis/product_analysis.json`；
- `analysis/product_fidelity_constraints.json` canonical；
- `analysis/output_role.json` 与 `analysis/reference_source_snapshot.json`；
- Top 3 的 `analysis/selected_references.json`、run 内 review 副本；
- `analysis/reference_composition_snapshots.json` 候选草稿；
- 展示产品图、候选参考图与结构字段的 `review/review.html`。

人工逐张确认画面结构、唯一替换位置、需移除首饰、目标展示面积和文字/UI 风险。Top 3 只是候选，不能自动成为决策。构图描述错误时必须修复飞书语义源并重新执行本阶段，不能直接编辑候选 JSON。

## 2. `record-decision`

人工只能选择一个 rank。角色必须与 `analysis/output_role.json` 一致，并显式确认保真：

```powershell
jewelry-on-hand record-decision `
  --run-root <run目录> `
  --output-role hand_worn `
  --action generate_rank_1 `
  --selected-ranks 1 `
  --fidelity-confirmed
```

外部约束只能通过 `--fidelity-constraints-path <文件>` 作为导入源。系统必须校验其 analysis 摘要，再把标准 canonical 固化到 `analysis/product_fidelity_constraints.json`；非标准路径、晚期重绑或摘要不一致一律拒绝。

写入前交叉校验最终 analysis、完整产品确认快照、canonical、单一 selected rank、源/review 双 SHA、角色与候选参考快照。成功后原子写入 `review/review_decision.json` 和 `review/reference_composition_snapshot.json`，decision 绑定确认快照摘要并记录 `fidelity_confirmed=true`。失败时不得留下部分决策。

## 3. `generate`

```powershell
jewelry-on-hand generate `
  --run-root <run目录> `
  --helper-script skills/aireiter-image-generation/scripts/aireiter_image_helper.py
```

在创建 generation、写 submit 或调用 provider 前再次验证角色、rank、确认快照、参考文件 SHA、analysis 与 canonical。每个现代 generation 采用五输入固化：

1. `scene-reference.*`：参考底图；
2. `product-reference.*`：产品身份图；
3. `reference-composition-snapshot.json`：已确认参考结构；
4. `product-analysis.json`：已确认产品分析；
5. `product-fidelity-constraints.json`：canonical 产品保真约束。

`input-manifest.json` 使用 `schema_version=1`，记录 `output_role`、两张有序图片及 snapshot/analysis/canonical 的 `copied_file` 与 SHA-256。实际副本、源文件和 manifest 摘要必须一致；模型输入顺序只能是 scene 后 product。任何固化失败都不得发布半成品目录或提交任一 job。

Prompt 必须以参考底图编辑声明开头；产品分析只能约束珠宝结构和佩戴物理，不能覆盖已确认构图。详细规则见 `prompt-contract.md`。

## 4. `qc`

先人工查看四栏页面：参考底图、产品身份图、结果、已确认构图快照。逐项填写三层 JSON：

```powershell
jewelry-on-hand qc `
  --generation-dir <generation/NN> `
  --status pass `
  --reference-preservation-checks-json <reference.json> `
  --fidelity-checks-json <fidelity.json> `
  --checklist-checks-json <checklist.json>
```

存在严重参考姿势错误时，`reject` 示例必须传实际错误码：

```powershell
jewelry-on-hand qc `
  --generation-dir <generation/NN> `
  --status reject `
  --reference-preservation-checks-json <reference.json> `
  --fidelity-checks-json <fidelity.json> `
  --checklist-checks-json <checklist.json> `
  --critical-failures reference_pose_changed
```

- `reference_preservation`：十项参考画面证据；
- `fidelity_checks`：canonical `must_keep` 与产品身份；
- `checklist_checks`：runtime 品类、佩戴物理和通用质量清单。

三层必须完全覆盖、备注可验证且与 `critical_failures` 一致。参考结构改变、原首饰泄漏、替换位置改变或目标产品复制直接 `reject`。只有局部融合或阴影问题可 `rerun`；参考构图问题固定纠偏重跑一次，再次失败则停用该参考并重新 `prepare-review`。

## Dry run

不调用 provider 的 dry run 只执行 `prepare-review`，人工审阅 Top 3 与候选快照，然后运行便携快照/Prompt/产物检查器。不要执行 `generate`，也不要伪造 decision、manifest 或 QC。dry run 用于验证路由、数据和 gate，不等于真实生成。

## 三态迁移

- `modern_snapshot`：候选快照、确认快照、decision digest 完整；若已有 generation，还要求 manifest 与五份固化副本完整。只有此态可生成。
- `legacy_read_only`：上述现代快照链全部不存在的历史 run。允许读取、检查和审计，不得追加 decision、generation 或 QC。
- `damaged`：现代链部分存在、摘要不一致或 generation 固化不完整。停止并报告损坏，不得删除单个文件伪装成历史。

历史 run 只读且不得追加。历史手串也只能检查和审计；需要重做时，新建 run 并重新执行 `prepare-review`，不能续写原目录。历史 v1 canonical 只读，不得补写 `pendant_semantics` 或自动升级。

五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

## 验收边界

最终只汇总当前 run 内 `qc.json` 为 `pass` 的结果。严格 QC 必须让 `fidelity_checks` 与 `must_keep` 完全一致，`critical_failures` 采用合法非空代码；严重错误必须 `reject` 并以中文说明。真实第三方模型 proof 属于 Task 12，尚未完成。
