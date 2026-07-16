# 多品类 Troubleshooting

所有命令与便携脚本使用 UTF-8 和中文错误文案。先根据错误定位阶段，不要通过直接编辑产物、删除约束或跳过 QC 绕过 gate。新项链 canonical 必须为 `schema_version=2` 且包含 `pendant_semantics`；历史 v1 只读，不自动升级，必须新建 run 并重新执行 `prepare-review` 才能继续。

## 品类、输入或展示模式被拒绝

当前生成白名单为 `bracelet`、`necklace`、`pendant_necklace`、`ring`。`pendant_only` 和 `unknown` 可分析但不得生成；无链独立吊坠禁止自动补链。

四种可生成品类都只接受 `worn_source`。项链目标为 `hand_held` 时，输入仍不能是 `hand_held_source`；`flat_lay_source`、白底/平铺图和 `unknown_source` 也不兼容。不要修改 JSON 假装来源，应该换真人佩戴产品图或停止任务。

项链只支持同一产品自身 1 至 3 层；这是运行时能力，不代表存在三圈吊坠商品。`is_independent_multi_item: true` 表示多件独立叠戴，必须拒绝。双圈附件是同一条连续长链形成 2 层、`presence=absent`，不是两件项链或带链吊坠。扣头、背面或连接被遮挡时写入不可见/不确定字段，不得推断。

## v2 canonical 或主吊坠语义被拒绝

症状：`record-decision`、`generate` 或 inspector 报 `schema_version=2`、`pendant_semantics`、analysis/快照冲突，或普通项链 absent canonical 的自由文本含敏感词。

处理：

1. 不要给历史 v1 补字段或原地改写；历史 v1 只允许 inspector、validator 与 QC 只读，inspector 应显示 `legacy_read_only=true`。
2. 新建 run，在 `prepare-review` 评分前完成最终品类、层数、长度和主吊坠结构纠正，由 builder 重建 v2 canonical。
3. 普通项链应为 `absent/0/null/forbid`；其 `detected_keywords[]`、`must_not_change[]` 及 `must_keep` 的 name/source_text/normalized_keyword/location/visual_shape/relationship/forbid/qc_question 共 10 类路径不得出现 `吊坠`、`主吊坠`、`链坠`、`流苏`、`坠子`。不要在自由文本写“禁止新增吊坠”，禁止创建由 `creation_policy=forbid` 表达。
4. 带链吊坠第一阶段应为 `present/1/实际所属层/forbid`，且只有一项可追溯主吊坠 `must_keep`。
5. `record-decision` 在替换文件前、`generate` 在创建 generation 目录和调用 helper/provider 前完成交叉校验；错误后不应出现半写入文件或 provider 任务。

## 项链缺少完整产品确认快照

症状：`generate` 或 `inspect_run_artifacts.py` 报“项链生成决策缺少完整产品确认快照”，或报告快照字段与最终 analysis 不一致。

处理：

1. 不要手补局部字段、复制旧手串决策或沿用旧 Top 3。
2. 若 analysis 的品类、`source_image_type`、`display_mode`、层数、长度等级、吊坠字段或多件标志需要变化，新建 run，并在 `prepare-review` 评分前传入纠正参数。
3. 重新检查 review 包后再运行不带项链纠正参数的 `record-decision --fidelity-confirmed`。CLI 会从已完成评分的最终 analysis 生成完整快照。

## 项链参考图路径、摘要或最终策略被拒绝

症状：`generate` 报 selected path 不在当前 `review_dir`、review SHA-256 不一致，或参考图与最终品类/展示模式/长度/裁切/手持策略不兼容。

处理：不要改 `selected_references.json`、复制外部图覆盖 rank 或在决策阶段修改 analysis。审核后副本被改动时新建 run 重做 `prepare-review`；analysis 变化时也必须在新 run 的评分前纠正并重选 Top 3。

## 戒指候选或确认快照不完整

症状：`prepare-review` 报合格戒指参考图少于三张或无法形成 Top 3；`generate` 报戒指快照缺少字段或与 analysis 不一致。

处理：

1. 参考记录必须显式标记 `ring + worn`，并完整填写左右手、可见手指、手部朝向、戒面可见度、手指分离度和手指遮挡风险。
2. 用 `record-decision --ring-count 1 --hand-side <left|right> --finger-position <...> --ring-wear-style finger_base` 重新确认，不能手改 JSON。
3. 三张候选必须是三张真实不同图片，不得复制同图伪造 Top 3。
4. `ring_count`、`hand_side`、`finger_position`、`ring_wear_style` 任一缺失或不一致都会拒绝。

## 戒指指位、结构或来源手错误

- 数量、指位、戒圈/镶嵌结构、戒面/主石或产品图来源手迁移分别记录 `ring_count_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`source_hand_leakage`，整体必须 `reject`。
- 左右手、接触物理或手指畸变分别记录 `hand_side_mismatch`、`ring_contact_error`、`finger_deformation`，至少不得 `pass`；严重穿透同时记录 `severe_intersection` 并 `reject`。
- 不可见戒圈背面不得补写为确定结构；这不是可通过“看起来合理”放行的细节。

## 非标准保真约束路径

症状：历史 `review_decision.json` 的 `fidelity_constraints_path` 指向外部或旧相对路径，`generate` 明确拒绝。

`--fidelity-constraints-path` 只是 `record-decision` 的导入源，不是 generate 的动态配置。重新执行：

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\<run-id> `
  --action generate_rank_1 `
  --fidelity-constraints-path .\path\to\confirmed-constraints.json `
  --fidelity-confirmed
```

成功后 canonical 文件固定为 `<run>/analysis/product_fidelity_constraints.json`，决策固定记录该路径。外部约束还必须携带与最终规范化 analysis 一致的 `product_analysis_sha256`；缺摘要或另一 SKU 的摘要会在写入前拒绝。不要直接改历史决策路径，也不要让 generate 读取外部文件。

## bracelet：原图手腕或手臂随产品迁移

这是手串/手链专属高频故障，不是系统只支持手腕场景的说明。

原因：内部图 2 是完整产品佩戴图，模型把手串与原手腕当成一个主体；或 Prompt 只强调尺寸和贴合，没有切断皮肤来源。

处理：

- 确认 Prompt 明确内部图 2 只提供珠子、隔圈、金属件、颜色、纹理和排列。
- 强调手腕宽度、手臂轮廓、皮肤连续性和肤色来自内部图 1。
- 换手腕露出完整、背景简单的参考图；必要时提供清晰的产品细节 crop。
- QC 分别写明原图手腕、手臂和皮肤块迁移检查，只写“手部自然”不够。

## 项链：产品图人物局部随产品迁移

症状：结果带入产品图中的颈部、胸部、衣领、头发、脸、皮肤块或背景贴片。

处理：

- 确认内部图 2 只提供链条、层数、吊坠、颜色、纹理和肉眼可见连接。
- `worn` 模式的人物、颈部、胸部、服装和头发均来自内部图 1。
- `hand_held` 模式的手和场景来自内部图 1，不得虚构绕颈佩戴链路。
- QC 明确写“没有迁移产品图中的人物局部，迁移检查通过”；严重人物贴片可记录 `source_person_region_migrated`，整体不能 `pass`。

## 项链层数、吊坠或连接漂移

常见症状包括层数变多/变少、上下层交换、吊坠换层/翻面/复制、链条合并、多件独立项链被当成一件、凭空补链或推断不可见扣头。

处理：

- 回查最终 `product_analysis.json` 的 `layer_count`、`length_category`、`pendant_layer`、`connection_structure` 和 `is_independent_multi_item`。
- 把关键吊坠与连接写入 `must_keep`，把层间关系写入 `must_not_change`，不要只在 Prompt 尾部临时补一句。
- 核心结构缺失、多层关系重组、自动补链或严重穿模是严重错误，必须 `reject`，不能标为 `rerun`。

## 参考图首饰混入

原因：参考图本来有戒指、手串、项链或其他饰品，或 `ignored_reference_jewelry` 未进入 Prompt。

处理：换更干净的 rank，并确认 Prompt 明确“不要把内部图 1 的原有首饰迁移到新图”。产品身份只能来自内部图 2。

## QC 报 `fidelity_checks` 或 `checklist_checks` 不完整

标准路径 `<run>/generation/NN/qc.json` 会自动反推 `<run>/analysis/product_fidelity_constraints.json`。每个 `must_keep` 必须对应且只能对应一条 `fidelity_checks`：

- 数量必须与 `must_keep` 完全一致。
- `name` 与 `must_keep[].name` 完全一致。
- `question` 与 `must_keep[].qc_question` 完全一致。
- name/question 组合唯一且对应关系不变。
- `result` 只能是 `pass`、`rerun` 或 `fail`；整体 `pass` 时每项都必须是 `pass`。

不要通过删除 canonical 约束、漏写检查或传空数组降级验证。

标准路径还会同时读取 `product_analysis.json` 并重建 runtime checklist。`checklist_checks` 必须包含全部问题；每项 `id` 为 `qc-` 加精确 question UTF-8 SHA-256 的前 16 位，question 不得改写，ID/question 组合不得重复。`pass`、`rerun`、`reject` 都要全量记录，不是只记录失败项。只存在 analysis 或 canonical 其中一个时是损坏 run，不会进入 legacy。

## `critical_failures` 或状态错误

`--critical-failures` 可重复使用或用逗号分隔。空参数、空分段、未知代码、重复代码、布尔值或数字都会收到中文错误。没有关键失败时省略字段，不要写空列表。

任何 `critical_failures` 都禁止 `pass`。品类错误、核心结构缺失、多层关系重组、自动补链、严重穿模，以及戒指数量/指位/核心结构/戒面主石/来源手迁移必须 `reject`；轻微且结构仍可辨认的问题才使用 `rerun`。

## Legacy 记录为什么仍被拒绝

历史手串自由文本、旧 JSON/run、缺现代快照的 bracelet，以及 analysis 与 canonical 同时不存在的旧 QC 可以兼容。历史 v1 canonical 只允许 inspector、validator 和 QC 只读，inspector 标记 `legacy_read_only=true`；不得改写或补写 `pendant_semantics`，历史项链 v1 不得进入新的决策/生成。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。

历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。普通项链、带链吊坠、戒指、`pendant_only` 和 `unknown` 也不使用旧手串默认值。标准 run 只要能定位 canonical 约束，就必须执行现代 `must_keep` 校验。

## Prompt 编码损坏

症状：Prompt 出现问号占位、`锟` 或替换字符，`validate_prompt_contract.py` 返回中文错误。

处理：用 UTF-8 重写 Prompt，重新从最终分析和约束构建，不要把乱码提交给 AIReiter。v2 普通项链必须精确出现 `主吊坠：无。` 和完整禁止创建句；带链吊坠必须精确出现 `主吊坠：有；数量：1；所属层：第 N 层。`。Prompt 只能从 `pendant_semantics` 渲染，不从自然语言极性推断。

## 模型切换与未完成生成目录

- 默认和第一次 QC 未通过后的重跑仍使用 `gpt_image_2`。
- 同一 run 内非 `pass` QC 次数超过 1 次后，下一次才使用 `nano_banana_v2`。
- 非空 `generation/NN/` 缺 `qc.json` 时先完成人工处理，不得跳过或覆盖。

## AIReiter 轮询失败与验收边界

先读取 `submit.json` 中的 `out_task_id` 并继续查询；不能确认提交失败时不要重复提交。当前本地自动化测试验证的是命令和产物契约。本次 v2 只关闭结构化主吊坠语义 I1；I5 真实双圈成功 proof 与 HERO 仍为开放项。没有真实调用证据时不得声称普通项链、带链吊坠或戒指已经完成真实模型验收。
