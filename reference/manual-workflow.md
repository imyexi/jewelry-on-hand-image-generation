# CLI 手工串联流程

本文说明 `jewelry-on-hand` 的现行人工操作流程。正式生成严格按 `prepare-review -> record-decision -> generate -> qc` 四阶段执行；每个新产品使用新的 `--run-id`，不要复用非空 run。新 run 的 canonical 必须是 `schema_version=2` 并包含 `pendant_semantics`；历史 v1 只读，不自动升级，也不能进入新的项链决策或生成，必须新建 run 并重新执行 `prepare-review`。

## 1. 能力与输入边界

| 规范品类 | 可生成展示模式 | 输入图类型 | 结构边界 |
| --- | --- | --- | --- |
| `bracelet` | `worn` | `worn_source` | 固定 1 层 |
| `necklace` | `worn`、`hand_held` | `worn_source` | 同一产品 1 至 3 层 |
| `pendant_necklace` | `worn`、`hand_held` | `worn_source` | 同一产品 1 至 3 层，必须有完整主吊坠 |
| `ring` | `worn` | `worn_source` | 单枚常规指根佩戴，必须确认左右手和目标手指 |
| `pendant_only` | 不可生成 | 不进入生成 | 可识别，但禁止自动补链 |
| `unknown` | 不可生成 | 不进入生成 | 必须先人工纠正 |

项链输出可以是手持展示，但输入仍只接受真人佩戴的 `worn_source`。`hand_held_source`、`flat_lay_source`、白底/平铺图和 `unknown_source` 都会被拒绝。普通项链和带链吊坠只支持同一件产品自身 1 至 3 层，不支持多件独立叠戴；1 至 3 层只是运行时能力，不代表存在三圈吊坠商品。双圈附件是同一条连续长链绕颈形成 2 层、无主吊坠，不是两件项链或带链吊坠。只记录肉眼可见结构，不得推断不可见扣头、背面或连接，也不得自动补链。戒指第一版固定 `ring_count=1`、明确 `hand_side`、明确 `finger_position` 和 `ring_wear_style=finger_base`；多枚、叠戴、跨指、指关节戒和不可见戒圈背面补写均拒绝。

## 2. 选择参考图来源

`prepare-review` 同时保留两种参考来源，选择规则固定：

1. 默认未传 `--classification` 时，使用飞书“AI 生图参考图素材库/素材收录池”。
2. 仅在显式传入 `--classification <xlsx>` 时，优先读取历史本地分类 Excel。

二者属于同一个 `prepare-review` 阶段的来源分支，不是两套互斥工作流。

戒指候选必须显式标记 `ring + worn`，并完整填写左右手、可见手指、手部朝向、戒面可见度、手指分离度和手指遮挡风险；少于三张合格候选时停止，不得复制同一图片凑 Top 3。

使用飞书前可先执行：

```powershell
jewelry-on-hand reference-ensure-fields
jewelry-on-hand reference-sync
```

若同步退出码为 2，按 `output/feishu_reference_cache/pending_enrichment.json` 补齐语义字段，再导入：

```powershell
jewelry-on-hand reference-import-enrichment `
  --input-json .\output\feishu_reference_cache\enrichment-results.json
```

导入后必须检查 `output/feishu_reference_cache/enrichment-import-audit.json`。只有 `verified` 记录会提交本地缓存；`failed`、`conflict` 仍保留 pending，可修正后重试。飞书 upsert 不支持 revision/if-match，最后一次写前复读到 upsert 之间仍有残余并发窗口，不能把这套流程称为强 CAS。飞书字段、缓存失效和恢复规则见 `reference/feishu-reference-source.md`。显式本地 Excel 是兼容输入，不需要先同步飞书。

如果历史批次已完成回填、但缺少导入时生成的审计文件，必须先执行只读复读审计，再允许该缓存进入候选库：

```powershell
jewelry-on-hand reference-audit-enrichment
```

该命令逐条比较当前飞书字段与本地缓存并重建同名审计文件；其中 `audit_kind=post_sync_readback` 只证明本次复读时字段一致，不能追溯或替代导入时的写后核验。只要审计中存在非 `verified` 记录，必须先修复并重新同步，禁止进入 `prepare-review`。

## 3. 准备产品分析

`analysis-json` 必须符合 `reference/product-analysis-schema.md`。现代记录明确写出 `detected_product_type`、`confirmed_product_type`、分类证据与来源、`source_image_type`、`display_mode`、层数和适用品类结构字段。

普通项链和带链吊坠的 `length_category` 可以在分析 JSON 中暂存为 `null`，但这只表示 correction-only，不能进入参考评分、Top 3、决策或生成。必须在本轮 `prepare-review` 通过 `--length-category` 纠正为 `choker`、`collarbone`、`upper_chest` 或 `long`。`detected_product_type=unknown` 同样可解析，但必须在评分前用 `--confirmed-product-type` 纠正为合法品类。

戒指现代记录额外必须写出 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`。四个字段在 `record-decision` 后也必须进入确认快照并与最终 analysis 一致。

canonical 版本边界如下：

- 历史 v1 顶层只有 `schema_version`、`source`、`detected_keywords`、`must_keep`、`must_not_change`、`needs_user_review`、`detail_crop_recommended`、`review_status`，不含 `pendant_semantics`；只允许 inspector、validator 和 QC 只读。
- 新 run 必须使用 `schema_version=2`，并在上述字段外提供 `pendant_semantics={presence, count, layer, creation_policy}`。普通项链固定为 `absent/0/null/forbid`，带链吊坠第一阶段固定为 `present/1/实际所属层/forbid`。
- 普通项链 v2 的 10 类自由文本路径 `detected_keywords[]`、`must_not_change[]`、`must_keep[].name`、`source_text`、`normalized_keyword`、`location`、`visual_shape`、`relationship`、`forbid[]`、`qc_question` 均不得包含 `吊坠`、`主吊坠`、`链坠`、`流苏`、`坠子`；禁止创建只由 `creation_policy=forbid` 表达。

如果暂时没有分析 JSON，可不传 `--analysis-json` 运行一次 `prepare-review`。命令会创建 prompt-only run、写入 `analysis/product_analysis_prompt.txt` 并返回非零；完成分析后必须换新 `run-id` 重跑，不得复用已非空目录。

## 4. `prepare-review`：生成 Review 包

使用飞书来源：

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\product-analysis.json `
  --output-root .\outputs\auto_reference_runs `
  --run-id demo
```

如需人工纠正项链品类、来源、展示模式、层数、长度或吊坠结构，必须在同一次 `prepare-review` 评分前传入。例如：

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\product-analysis.json `
  --output-root .\outputs\auto_reference_runs `
  --run-id necklace-hand-held `
  --confirmed-product-type necklace `
  --source-image-type worn_source `
  --display-mode hand_held `
  --layer-count 1 `
  --length-category collarbone `
  --no-has-pendant `
  --pendant-count 0 `
  --pendant-layer null `
  --no-independent-multi-item
```

显式使用本地 Excel：

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\product-analysis.json `
  --classification .\path\to\catalog.xlsx `
  --output-root .\outputs\auto_reference_runs `
  --run-id demo-local
```

戒指产品主体在原图中占比过低、原图带大面积界面，或需要避免源手迁移时，应先准备经过人工确认的细节图并在新 run 中传入：

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\ring-original.jpg `
  --product-detail-image .\path\to\ring-detail.png `
  --analysis-json .\path\to\ring-analysis.json `
  --output-role hand_worn `
  --output-root .\outputs\auto_reference_runs `
  --run-id ring-detail-demo
```

细节图只支持 jpg/jpeg/png/webp，且只允许戒指使用。系统不使用固定中心或颜色阈值盲目裁切；细节图必须在进入流程前确认主石、开口端点、戒圈和装饰均未被裁掉。经过确认的细节图只作为 review、结构分析、canonical 约束和人工 QC 对照证据，不进入模型。

可再传 `--dimensions-json` 写入用户提供尺寸。该阶段会：

- 拒绝非空目标 run，复制产品上手图为 `input/product-on-hand.jpg`；戒指提供细节图时另存为 `input/product-detail.<ext>`，供 review、结构分析、canonical 约束和人工 QC 对照使用，产品上手图继续作为生成阶段唯一产品身份图。
- 以 correction-only 方式解析分析，先合并全部人工纠正并重新校验，再使用最终 analysis 生成 `schema_version=2` 的 `analysis/product_fidelity_constraints.json`；不能先构建 v1 或沿用旧 canonical 后再补字段。
- 写入完整候选 `analysis/reference_candidates.json`。
- 多样性重排 Top 3，复制候选到 run 的 `review/`，再写 `analysis/selected_references.json` 和 `review/review.html`。
- 不创建 `review/review_decision.json`；自动 Top 3 不等于人工选择。

当同一批 SKU 的候选重复过多时，可对尚未创建决策的 run 使用 `rerank-batch` 批次重排。单个 run 仍优先无风险参考；批次重排会平衡已过度复用的无风险图与低复用的可控风险图，风险图只能作为构图参考，生成时仍必须移除参考首饰、文字和平台元素，并保持产品身份隔离。`rerank-batch` 仅更新 review 包，不能替代人工确认或进入 `generate`。

保真约束即使没有局部识别点也必须存在；此时写 `must_keep: []` 和 `review_status: not_applicable`。`source.product_analysis` 固定为 `analysis/product_analysis.json`，`source.product_analysis_sha256` 绑定规范化后的最终分析，所有品类都必须具备。有关键识别点时先人工核对 `must_keep`、`must_not_change` 和 `qc_question`。

项链与戒指 Top 3 的每条 selected metadata 都会记录 `source_sha256` 与 `review_sha256`。项链生成前要求 selected 路径仍位于当前 run 的 `review/`，重算副本摘要，并按最终品类、展示模式、长度、裁切和手持策略复评；外部路径、审核后篡改或不再适配的 metadata 会被拒绝。戒指还会重算源图摘要，并要求三张内容互异。戒指元数据明确标记水印、logo、平台标识、人物半身/全身或脸、头发、胸部等宽场景时直接淘汰；人工 review 仍需查看图片，因为“元数据未标记水印”不等于视觉确认无水印。

## 5. `record-decision`：提交人工确认

选择 rank 1：

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\demo `
  --action generate_rank_1 `
  --selected-ranks 1 `
  --fidelity-confirmed
```

选择单个其他 rank 使用 `generate_selected`；选择至少两个 rank 使用 `generate_multiple`。`selected_ranks` 只能在 1..3 内且不能重复。`rerank` 和 `manual_reference` 可以记录，但不能进入当前 `generate`。

普通项链和带链吊坠在本阶段只选择已经按最终 analysis 产生的 rank，并确认保真约束，不再修改会影响参考适配的分析字段。写入前会交叉校验 analysis、确认快照、`schema_version=2`、`pendant_semantics`、摘要和 canonical 路径。若品类、来源、展示模式、层数、长度或主吊坠结构需要变化，当前 Top 3 和旧决策立即失效；CLI 会用中文说明冲突和修复动作，并在写入任何文件前拒绝。必须新建 run，在 `prepare-review` 评分前传入纠正参数并重新生成 review 包，不能手改 JSON 或沿用旧 Top 3。

生成类决策必须写 `fidelity_confirmed: true`。普通项链和带链吊坠还必须保存完整产品确认快照，包括品类、来源、模式、层数、非空长度等级、吊坠字段和多件标志；快照与最终 analysis 不一致时会被拒绝。CLI 从已经完成评分的最终 analysis 自动构建快照。

戒指人工纠正使用 `--ring-count`、`--hand-side`、`--finger-position`、`--ring-wear-style`。只有单枚、明确左右手、明确目标手指和 `finger_base` 能通过；戒指生成类决策同样强制完整快照。

### 外部保真约束导入

如人工在其他文件中修订约束，可传：

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\demo `
  --action generate_rank_1 `
  --fidelity-constraints-path .\review\confirmed-constraints.json `
  --fidelity-confirmed
```

`--fidelity-constraints-path` 只是 `record-decision` 的导入源。外部文件必须携带与最终规范化 `ProductAnalysis` 完全一致的 `source.product_analysis_sha256`；系统不会替外部文件重绑摘要，因此另一 SKU 的约束会在任何替换前被拒绝。成功后内容写入 canonical 路径 `<run>/analysis/product_fidelity_constraints.json`，`review_decision.json` 也固定记录 `analysis/product_fidelity_constraints.json`。历史决策若仍记录非标准路径或 canonical 缺摘要，`generate` 会拒绝并要求重新执行 `prepare-review` / `record-decision`；生成阶段不会直接读取任意外部约束。

## 6. `generate`：通过 Gate 后生成

```powershell
jewelry-on-hand generate `
  --run-root .\outputs\auto_reference_runs\demo `
  --helper-script skills/aireiter-image-generation/scripts/aireiter_image_helper.py
```

生成前会重新检查；全部 gate 都发生在创建新的 `generation/NN/`、写 prompt/submit 文件或调用 helper/provider 之前：

- 决策是生成类 action，rank 合法，`fidelity_confirmed` 为 true。
- canonical 约束存在且状态为 `confirmed`、`corrected` 或 `not_applicable`；新项链必须为 `schema_version=2`，并具有与最终 analysis 精确一致的 `pendant_semantics`。历史 v1 会以中文错误拒绝，要求新建 run 并重新执行 `prepare-review`。
- canonical 的 `product_analysis_sha256` 与磁盘最终规范化 analysis 完全一致。
- 最终品类是 `bracelet`、`necklace`、`pendant_necklace` 或 `ring`。
- 输入是 `worn_source`，展示模式、层数、吊坠结构和多件标志合法。
- 项链或戒指具有完整产品确认快照，且与最终 analysis 完全一致；项链长度等级非空，selected 路径位于当前 run 的 `review/`，审核摘要未变化并通过最终参考策略复评；戒指另需三张合格且源图/review 双摘要未变化、内容互异的 Top 3 参考图。
- 决策中的约束路径是 canonical 相对路径。

生成只读取 `analysis/selected_references.json` 指向的 run 内 review 副本，外部 Excel 或飞书附件后续移动不会影响已 review 的 run。每条 selected metadata 必须完整保留可重建 `ReferenceRow` 的字段，包括源图路径与文件名、尺寸、`file_exists`、用途、手串适用性、默认策略、置信度及全部品类适配字段；生成前会从 metadata 重建记录并按最终品类策略复评，不能依赖测试或人工临时补字段。戒指内部图 2 固定使用 `input/product-on-hand.jpg`，generation 固定保存 `product-identity.jpg`，且审计副本内容与 `product-on-hand.jpg` 一致。即使存在 `input/product-detail.<ext>`，也不得把细节图传给 AIReiter 或作为第三张模型输入。内部图 2 只提供产品身份；不得迁移其中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。

v2 项链 Prompt 只从结构化事实渲染。普通项链逐字输出 `主吊坠：无。` 与 `禁止新增、补造、复制、悬挂化吊坠，也不得把珠子、跑环或其他元件改成吊坠。`；带链吊坠逐字输出 `主吊坠：有；数量：1；所属层：第 N 层。` 与 `保持肉眼可见的位置、朝向与连接关系；禁止删除、复制、换层或新增第二颗吊坠。`。不得从 canonical 自由文本中的否定词猜测 presence。

每次输出写到新的 `generation/NN/`，不按 rank 命名，也不覆盖旧结果。戒指单图决策首次使用人工选择 Rank；最新 QC 非 pass 后按尚未尝试的 Top 3 顺序切换参考图，并根据 `critical_failures` 在 Prompt 末尾写 `【本轮纠偏】`。实际 Rank 写入 `reference-rank.txt`，失败码写入 `retry-failures.json`；历史目录没有 Rank 文件时用手部参考图 SHA-256 反查。Top 3 全部尝试后停止，不再重复 Rank 1。默认模型为 `gpt_image_2`；同一 run 中已有超过 1 次非 `pass` QC 后，下一次才使用 `nano_banana_v2`。发现非空生成目录缺少 `qc.json` 时必须先处理，不能跳过。

### 三图输出角色

批量交付主图、手部佩戴图和生活场景图时，每个 SKU 分别为 `hero`、`hand_worn`、`lifestyle` 建立独立 run，并在 `prepare-review` 与 `record-decision` 两个命令中传入同名 `--output-role`。每个角色的参考图类型必须直接取自飞书素材表 `图片类型` 字段（本地缓存字段为 `purpose_category`），不得依关键词、风格、推荐使用方式或视觉内容自行判断：`hero` 必须为“主图”，`hand_worn` 必须为“手部佩戴图”，`lifestyle` 必须为“生活场景图”。三个角色均在该类型 gate 后再选深色背景候选；图片类型不符时不得作为候选或以人工例外放行。深色文本 gate 接受“深色/黑色/暗色背景或布景”、低调暗色背景、暗黑背景，以及明确的黑色支撑面：黑色托盘、石材、岩石、石板、底座和黑绒/黑色绒布；“背景干净”不能单独视为深色背景。经人工视觉确认的例外按角色受控：主图为 `RP000137`、`RP000144`，生活场景图为 `RP000298`，且仅放宽对应角色的深色背景判断。生成提示词固定要求深色背景、产品完整清晰和无文字。

`hero` 使用产品主体近景，`lifestyle` 保留日常氛围且不遮挡主体。手链和戒指的 `hand_worn` 使用自然佩戴；项链的 `hand_worn` 必须在 `prepare-review` 评分前把产品分析纠正为 `hand_held`，以手指轻持链条自然垂落展示，不能伪造为手腕佩戴。`analysis/output_role.json`、`review_decision.json` 与生成时的角色不一致会被拒绝。

## 7. `qc`：严格写入质检结果

标准路径 `<run>/generation/NN/qc.json` 会同时反推 `<run>/analysis/product_analysis.json` 与 `<run>/analysis/product_fidelity_constraints.json`，重建完整 runtime checklist。每个 `must_keep` 必须有且只有一条 `fidelity_checks`，数量、`name`、`question` 及 name/question 对应关系必须与约束完全一致；此外 `checklist_checks` 必须完整记录所有通用、品类、展示模式和 `must_keep` 问题。v2 普通项链精确增加 `主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠`；v2 带链吊坠按结构化值增加 `现有主吊坠数量是否为 {count}，且仍位于第 {layer} 层并保持原连接关系`。

```powershell
jewelry-on-hand qc `
  --generation-dir .\outputs\auto_reference_runs\demo\generation\01 `
  --status pass `
  --passed "产品结构正确,没有迁移产品图中的人物局部，迁移检查通过" `
  --fidelity-checks-json .\path\to\fidelity-checks.json `
  --checklist-checks-json .\path\to\checklist-checks.json `
  --notes "所有检查通过"
```

`pass` 时不要传空的 `--failed`；由未传参数形成空列表。`fidelity-checks.json` 是对象数组，每项严格包含字符串 `name`、`question`、`result`、`notes`。`checklist-checks.json` 也是对象数组，每项包含 `id`、`question`、`result`、`notes`；ID 固定为 `qc-` 加 question UTF-8 SHA-256 的前 16 位。三种整体状态都必须全量记录，不能只写失败项；两类逐项结果都只能是 `pass`、`rerun` 或 `fail`。

`--critical-failures` 可重复传入，也可用逗号分隔，例如：

```powershell
jewelry-on-hand qc `
  --generation-dir .\outputs\auto_reference_runs\demo\generation\01 `
  --status reject `
  --passed "无水印" `
  --failed "检测到自动补链" `
  --critical-failures auto_chain_added,core_structure_missing `
  --notes "严重错误，拒绝交付"
```

空参数、空的逗号分段、未知代码、重复代码和错误 JSON 类型都会得到中文错误。存在任一 `critical_failures` 时不能 `pass`；品类错误、核心结构缺失、多层关系重组、自动补链或严重穿模必须 `reject`，不能使用 `rerun`。所有品类都要记录产品原图人物局部迁移检查；bracelet 还要明确记录原图手腕、手臂和皮肤块检查。

戒指代码为 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。数量、指位、戒指结构、戒面/主石或来源手迁移必须 `reject`；手侧、接触或手指畸变至少不得 `pass`。

最终汇总只能引用当前 run 内 QC 为 `pass` 的 `generation/NN/result.png`。

## 8. Legacy 兼容边界

历史手串自由文本、旧 JSON/run、缺现代确认快照的历史 bracelet，以及 analysis 与 canonical 同时不存在的旧 QC 记录继续可读。历史 v1 canonical 只允许 inspector、validator 和 QC 只读，inspector 标记 `legacy_read_only=true`，不改写文件、不补写 `pendant_semantics`、不自动升级。只存在其中一个标准分析文件属于损坏 run，不进入 legacy；旧 canonical 缺摘要时也不能继续生成。历史项链 v1 不能进入新的 `record-decision` 或 `generate`，必须新建 run 并重新执行 `prepare-review`。兼容分支不为普通项链、带链吊坠、戒指、`pendant_only` 或 `unknown` 补造现代字段。

五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。标准新 run 也不能通过删除单个分析文件、漏写 `fidelity_checks` 或 `checklist_checks` 降级到 legacy。

## 9. 便携校验

```powershell
python skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py `
  .\outputs\auto_reference_runs\demo\generation\01\prompt.txt

python skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py `
  .\outputs\auto_reference_runs\demo\generation\01\qc.json

python skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py `
  .\outputs\auto_reference_runs\demo
```

校验器使用中文文案报告品类、模式、快照、canonical 约束、QC 类型与产物缺失问题。

## 10. 验收状态

本文描述的是已经由本地自动化测试验证的 CLI 契约。真实第三方模型 proof 属于 Task 11，尚未完成。本次 v2 只关闭结构化主吊坠语义 I1；I5 真实双圈成功 proof 与 HERO 仍为开放项，不属于本次交付。在拿到对应真实调用和产物证据前，不得把命令可运行或 mock/e2e 通过写成真实模型验收完成。
