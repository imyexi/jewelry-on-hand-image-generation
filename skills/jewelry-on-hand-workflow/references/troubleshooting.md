# 多品类 Troubleshooting

所有命令与便携脚本使用 UTF-8 和中文错误文案。先根据错误定位阶段，不要通过直接编辑产物、删除约束或跳过 QC 绕过 gate。

## 品类、输入或展示模式被拒绝

当前生成白名单只有 `bracelet`、`necklace`、`pendant_necklace`。`pendant_only` 和 `unknown` 可分析但不得生成；无链独立吊坠禁止自动补链。

三种可生成品类都只接受 `worn_source`。项链目标为 `hand_held` 时，输入仍不能是 `hand_held_source`；`flat_lay_source`、白底/平铺图和 `unknown_source` 也不兼容。不要修改 JSON 假装来源，应该换真人佩戴产品图或停止任务。

项链只支持同一产品自身 1 至 3 层。`is_independent_multi_item: true` 表示多件独立叠戴，必须拒绝。扣头、背面或连接被遮挡时写入不可见/不确定字段，不得推断。

## 项链缺少完整产品确认快照

症状：`generate` 或 `inspect_run_artifacts.py` 报“项链生成决策缺少完整产品确认快照”，或报告快照字段与最终 analysis 不一致。

处理：

1. 不要手补局部字段或复制旧手串决策。
2. 用 `record-decision` 重新确认品类、`source_image_type`、`display_mode`、层数、长度等级、吊坠字段和多件标志。
3. 同时传 `--fidelity-confirmed`。CLI 会从最终 analysis 生成完整快照，并将人工修正与决策原子提交。

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

成功后 canonical 文件固定为 `<run>/analysis/product_fidelity_constraints.json`，决策固定记录 `analysis/product_fidelity_constraints.json`。不要直接改历史决策路径，也不要让 generate 读取外部文件。

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

## QC 报 `fidelity_checks` 不完整

标准路径 `<run>/generation/NN/qc.json` 会自动反推 `<run>/analysis/product_fidelity_constraints.json`。每个 `must_keep` 必须对应且只能对应一条 `fidelity_checks`：

- 数量必须与 `must_keep` 完全一致。
- `name` 与 `must_keep[].name` 完全一致。
- `question` 与 `must_keep[].qc_question` 完全一致。
- name/question 组合唯一且对应关系不变。
- `result` 只能是 `pass`、`rerun` 或 `fail`；整体 `pass` 时每项都必须是 `pass`。

不要通过删除 canonical 约束、漏写检查或传空数组降级验证。

## `critical_failures` 或状态错误

`--critical-failures` 可重复使用或用逗号分隔。空参数、空分段、未知代码、重复代码、布尔值或数字都会收到中文错误。没有关键失败时省略字段，不要写空列表。

任何 `critical_failures` 都禁止 `pass`。品类错误、核心结构缺失、多层关系重组、自动补链和严重穿模必须 `reject`；轻微且结构仍可辨认的问题才使用 `rerun`。

## Legacy 记录为什么仍被拒绝

历史手串自由文本、旧 JSON/run、缺现代快照的 bracelet 和无 canonical 约束的旧 QC 可以兼容。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。

历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。普通项链、带链吊坠、`pendant_only` 和 `unknown` 也不使用旧手串默认值。标准 run 只要能定位 canonical 约束，就必须执行现代 `must_keep` 校验。

## Prompt 编码损坏

症状：Prompt 出现问号占位、`锟` 或替换字符，`validate_prompt_contract.py` 返回中文错误。

处理：用 UTF-8 重写 Prompt，重新从最终分析和约束构建，不要把乱码提交给 AIReiter。

## 模型切换与未完成生成目录

- 默认和第一次 QC 未通过后的重跑仍使用 `gpt_image_2`。
- 同一 run 内非 `pass` QC 次数超过 1 次后，下一次才使用 `nano_banana_v2`。
- 非空 `generation/NN/` 缺 `qc.json` 时先完成人工处理，不得跳过或覆盖。

## AIReiter 轮询失败与验收边界

先读取 `submit.json` 中的 `out_task_id` 并继续查询；不能确认提交失败时不要重复提交。当前本地自动化测试验证的是命令和产物契约。真实第三方模型 proof 属于 Task 11，尚未完成。没有真实调用证据时不得声称普通项链或带链吊坠已经完成真实模型验收。
