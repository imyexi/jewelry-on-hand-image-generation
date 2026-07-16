# 多品类珠宝上手图 Workflow

## 适用范围

本流程覆盖四个可生成规范品类：

| 品类 | 输出模式 | 输入与结构限制 |
| --- | --- | --- |
| `bracelet` | `worn` | 只接受 `worn_source`，固定 1 层 |
| `necklace` | `worn`、`hand_held` | 只接受 `worn_source`，同一产品 1 至 3 层 |
| `pendant_necklace` | `worn`、`hand_held` | 只接受 `worn_source`，同一产品 1 至 3 层且保留完整主吊坠 |
| `ring` | `worn` | 只接受 `worn_source`，单枚常规指根佩戴且确认左右手和目标手指 |

`pendant_only` 和 `unknown` 可以分析识别，但不得生成；禁止自动补链。新项链 canonical 必须为 `schema_version=2` 并包含 `pendant_semantics`；历史 v1 只读，不自动升级。项链拒绝 `hand_held_source`、`flat_lay_source`、白底/平铺输入、`unknown_source`、多件独立叠戴和不可见结构推断。双圈附件是同一条连续长链形成 2 层、主吊坠 absent，不是两件项链或带链吊坠；1 至 3 层仅是运行时能力，不代表存在三圈吊坠商品。戒指拒绝多枚、叠戴、跨指、指关节佩戴和不可见戒圈背面补写。

## 参考源选择

参考源由同一个 `prepare-review` 命令选择：

- 默认未传 `--classification` 时，同步并读取飞书“AI 生图参考图素材库/素材收录池”。
- 仅在显式传 `--classification <xlsx>` 时，本地历史分类 Excel 优先。
- 默认只要同步结果存在 `pending_enrichment=true` 就停止，不允许静默跳过。
- 用户明确批准临时忽略待补全素材时，线上路径可显式传 `--ignore-pending-enrichment`；它与 `--classification` 不能同时使用。

飞书临时忽略模式仍完整分页同步线上 Base，随后只排除 pending 候选，不写回远端；过滤后无候选立即失败。正式 run 会写 `analysis/reference_source_snapshot.json`，固定来源、同步总数、忽略/保留数量、忽略素材编号与 record_id、manifest SHA-256 和分页完成状态。本地 Excel 兼容路径不要求同步飞书，也不生成该线上快照。

戒指候选必须显式标记 `ring + worn`，并完整填写左右手、可见手指、手部朝向、戒面可见度、手指分离度和手指遮挡风险。元数据明确出现水印、logo、平台标识或人物宽场景区域时拒绝；有 `framing` 时必须是手部近景/特写、手指近景/特写或戒指特写。少于三张合格候选时停止，不得复制图片伪造 Top 3，人工仍需视觉检查未被元数据标出的水印。

## 四阶段流程

### 1. `prepare-review`

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\product-analysis.json `
  --output-role lifestyle `
  --output-root .\outputs\auto_reference_runs `
  --run-id demo
```

戒指原图主体过小或携带大量源手时，可额外传 `--product-detail-image .\path\to\ring-detail.png`。细节图必须事先确认未裁掉主石、开口端点、戒圈或装饰；系统将其保存为 `input/product-detail.<ext>`，只作为 review、结构分析、canonical 约束和人工 QC 对照证据，不做不可审计的盲目自动裁切，也不提交模型。

项链若需人工纠正，必须在这条命令中传 `--confirmed-product-type`、`--source-image-type`、`--display-mode`、`--layer-count`、`--length-category` 和适用的吊坠/多件字段；系统先纠正再评分。`detected_product_type=unknown` 与项链 `length_category=null` 只能作为 correction-only，未纠正时不得产生 Top 3。

如需本地 Excel，加 `--classification .\path\to\catalog.xlsx`。若是已获批准的线上临时批次，需要排除待补全素材时改加 `--ignore-pending-enrichment`，不得同时传本地 Excel；默认仍保持 pending 全局阻断。命令会拒绝非空 run，复制产品图，合并全部人工纠正并校验最终分析 JSON，再生成带 `product_analysis_sha256` 的 `schema_version=2` canonical，随后写候选与多样性 Top 3，将参考图复制到 run 的 `review/`，并渲染 `review.html`。普通项链写 `absent/0/null/forbid`，带链吊坠第一阶段写 `present/1/实际所属层/forbid`。此阶段不会创建 `review_decision.json`。

若多个 SKU 的 Top 3 过度重复，可在未决策 run 上使用 `rerank-batch` 联合重排。单 run 保持无风险参考优先；批次重排为降低重复，可选择低复用但带可控“参考首饰/界面需移除”风险的候选。此类候选只提供姿势、构图、背景和光线，生成阶段仍须移除参考首饰、文字和平台元素；重排不得创建决策或绕过人工确认。

缺少 `--analysis-json` 时只生成分析 Prompt 并返回非零；补齐后换新 run-id。`product_analysis.json` 必须明确现代品类、来源、模式和结构字段；旧手串兼容例外见“Legacy 边界”。

戒指分析必须显式包含 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`，第一版只允许 `1`、明确手侧、明确目标手指和 `finger_base`。

### 2. `record-decision`

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\demo `
  --action generate_rank_1 `
  --selected-ranks 1 `
  --fidelity-confirmed
```

允许的生成 action 是 `generate_rank_1`、`generate_selected`、`generate_multiple`。`selected_ranks` 必须在 1..3 内、不能重复并且存在于 Top 3；`rerank` 和 `manual_reference` 不得进入生成。

普通项链、带链吊坠和戒指的生成决策必须包含完整产品确认快照。项链在本阶段只选择按最终 analysis 产生的 rank；系统会在写文件前交叉校验 analysis、快照、`schema_version=2`、`pendant_semantics`、摘要和 canonical 路径。任何冲突都以中文说明修复动作并拒绝，必须新建 run 并重新执行 `prepare-review`。戒指快照逐字段保存 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style`；戒指人工纠正仍使用对应参数并与决策原子提交。

`--fidelity-constraints-path` 只是 `record-decision` 的约束导入源，外部文件摘要必须与已经完成评分的最终 analysis 匹配。项链 analysis 发生变化时，旧 Top 3 与 canonical 同时失效，不得在本阶段重绑或导入后继续；必须重新 prepare。成功后 canonical 内容固定写入 `<run>/analysis/product_fidelity_constraints.json`，决策固定写该路径。

### 3. `generate`

```powershell
jewelry-on-hand generate --run-root .\outputs\auto_reference_runs\demo `
  --helper-script skills/aireiter-image-generation/scripts/aireiter_image_helper.py
```

生成前重新校验；全部 gate 都发生在创建 generation 目录、写 prompt/submit 文件或调用 helper/provider 前：

- 最终品类是 `bracelet`、`necklace`、`pendant_necklace` 或 `ring`。
- 输入为 `worn_source`；输出模式、1 至 3 层项链结构和多件标志合法。
- 决策为生成类，`fidelity_confirmed: true`，项链或戒指有完整产品确认快照且与最终 analysis 完全一致；戒指另需三张双摘要未变化、内容互异的合格 Top 3。
- canonical 约束存在并已确认，`product_analysis_sha256` 匹配最终 analysis；新项链为 `schema_version=2` 且 `pendant_semantics` 与 analysis/快照精确一致；决策不指向非标准路径。
- 所选 rank 仍在 `analysis/selected_references.json` 中；非 HERO 项链 selected 路径仍在当前 run 的 `review/`，副本摘要未变化，并按最终品类、模式、长度、裁切和手持策略复评合格。

产品上手图是生成阶段唯一产品身份图。戒指内部图 2 固定使用 `input/product-on-hand.jpg`，并固定保存内容一致的 `product-identity.jpg` 审计副本。细节图只用于 review、结构分析和 QC，并可用于 canonical 约束和人工 QC 对照；即使存在 `input/product-detail.<ext>`，也不得传给 AIReiter，不得作为第三张模型输入。

Prompt 必须重新构建并通过 `scripts/validate_prompt_contract.py`。普通项链精确输出 `主吊坠：无。` 与 `禁止新增、补造、复制、悬挂化吊坠，也不得把珠子、跑环或其他元件改成吊坠。`；带链吊坠精确输出 `主吊坠：有；数量：1；所属层：第 N 层。` 与固定保持/禁止句。不得从自由文本极性猜测 presence。内部图 1 只提供人物、姿势、构图、背景和光线；内部图 2 只提供产品身份。禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。

默认模型为 `gpt_image_2`。戒指首次使用人工决策 Rank；失败后切换到 Top 3 中尚未尝试的下一张，并按最新 `critical_failures` 注入指位、主石、结构、数量、接触、来源迁移或手指变形纠偏。实际 Rank、失败码和产品上手图审计副本分别写入 `reference-rank.txt`、`retry-failures.json` 和 `product-identity.jpg`。Top 3 用尽后停止。累计超过 1 次 `status != "pass"` 的 QC 后，下一次才用 `nano_banana_v2`。每次生成写入后续 `generation/NN/`，不得覆盖旧结果；非空目录缺少 `qc.json` 时必须停止处理。

### 4. `qc`

```powershell
jewelry-on-hand qc `
  --generation-dir .\outputs\auto_reference_runs\demo\generation\01 `
  --status reject `
  --passed "无水印" `
  --failed "检测到自动补链" `
  --fidelity-checks-json .\path\to\fidelity-checks.json `
  --checklist-checks-json .\path\to\checklist-checks.json `
  --critical-failures auto_chain_added `
  --notes "严重错误，拒绝交付"
```

标准 QC 路径会同时反推 analysis 与 canonical 并重建 runtime checklist。普通项链精确增加 `主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠`；带链吊坠按结构化 count/layer 精确增加 `现有主吊坠数量是否为 {count}，且仍位于第 {layer} 层并保持原连接关系`。`checklist_checks` 必须完整覆盖全部项目；每个 `must_keep` 另有且只有一条 `fidelity_checks`，对应关系必须与约束完全一致。

`--critical-failures` 可重复或逗号分隔，写入 JSON 字段 `critical_failures`；不能是空参数、空分段、未知代码或重复代码。存在任一关键失败不能 `pass`；品类错误、核心结构缺失、多层关系重组、自动补链或严重穿模属于严重错误，必须 `reject`。

所有品类必须明确记录产品原图人物局部迁移检查。bracelet 还要分别记录原图手腕、手臂和皮肤块；项链佩戴要检查颈部、胸部、衣服和头发，项链手持要检查手部接触、重力垂落且不虚构绕颈链路。

## 三图角色批量交付

当一个 SKU 需要主图、手部佩戴图和生活场景图时，必须建立三个独立 run：`hero`、`hand_worn`、`lifestyle`。调用 `prepare-review` 时，先以飞书素材表的 `图片类型` 字段（缓存中的 `purpose_category`）做严格槽位过滤，且不得以关键词、风格分类、推荐使用方式或视觉识别结果自行推断：`hero` 只接受含“主图”的记录，`hand_worn` 只接受含“手部佩戴图”的记录，`lifestyle` 只接受含“生活场景图”的记录。各自通过类型 gate 后，才应用深色背景、品类、展示模式和保真 gate；深色背景还包括低调暗色背景、暗黑背景，以及黑色托盘、石材、岩石、石板、底座和黑绒/黑色绒布等明确支撑面，但不能把“背景干净”放宽为深色。人工视觉确认的例外按角色匹配受控素材编号：主图为 `RP000137`、`RP000144`，生活场景图为 `RP000298`；例外仅可放行对应角色的深色背景，绝不放宽图片类型。将角色写入 `analysis/output_role.json`。

后续 `record-decision` 必须传入同名 `--output-role`；缺失、修改或与 run 不一致都会被拒绝。三个角色均使用深色背景、产品完整清晰和无文字约束。手链或戒指的 `hand_worn` 为自然佩戴；项链的 `hand_worn` 必须单独使用 `hand_held` 模式，手指轻持链条自然垂落，不能将项链伪造为手腕佩戴。

戒指代码为 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。数量、指位、结构、戒面/主石和来源手迁移必须 `reject`；手侧、接触和手指畸变至少不得 `pass`。

## Final Summary Gate

最终汇总只能引用当前 run 内 `generation/NN/result.png`，对应 `qc.json` 的 `status` 必须为 `pass`。运行：

```powershell
python skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py `
  .\outputs\auto_reference_runs\demo `
  .\outputs\auto_reference_runs\demo\final-summary.json
```

## Legacy 边界

历史手串自由文本、旧 JSON/run、缺现代快照的 bracelet，以及 analysis 与 canonical 同时不存在的旧 `qc.json` 继续兼容。历史 v1 canonical 只允许 inspector、validator 和 QC 只读，inspector 标记 `legacy_read_only=true`，不得改写文件或补写 `pendant_semantics`；历史项链 v1 禁止进入新决策/生成，必须新建 run 并重新执行 `prepare-review`。只存在其中一个文件属于损坏的现代 run。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

校验脚本和 CLI 使用中文错误文案。发现编码损坏、乱码或字段类型错误时先停止，不提交生成。

## Dry Run 与验收边界

dry run 只检查 gate 和列风险，不调用 AIReiter、不下载结果、不写回飞书，也不伪造 `qc.json` 或 `result.png`。当前自动化验证覆盖本地 CLI 契约。真实第三方模型 proof 属于 Task 11，尚未完成。本次 v2 只关闭结构化主吊坠语义 I1；I5 真实双圈成功 proof 与 HERO 仍为开放项。未取得真实产物前不得声称已经完成真实模型验收。
