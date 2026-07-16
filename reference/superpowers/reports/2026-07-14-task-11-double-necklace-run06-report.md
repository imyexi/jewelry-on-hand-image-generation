# Task 11 普通项链双圈真人佩戴 run 06 执行报告

## 结论

**DONE_WITH_CONCERNS**

`run-20260714-double-necklace-06` 已按 brief 完成固定输入核验、正式 scorer、六项人工补强 canonical、无 `output_role` 的 decision、submit 前硬门禁和一次留存的正式提交链。`generation/01/model.txt` 独立记录模型为 `gpt_image_2`；`3:4 / 2K` 只由 CLI 默认、Prompt 和提交前 `expected_*` 记录支持。没有留存脱敏出站请求 payload，因此不能把画幅和分辨率表述为已独立证实的平台实际请求参数。所有提交前门禁均通过，留存任务被平台接受后在原 CLI wait 中返回 `failed / TIMEOUT`。平台没有返回 output URL 或 `credits_used`，因此没有原图可下载，也不能执行或伪造三图 QC。

现有证据只有单个 `generate-06.invocation.txt`、单个 `generation/01`、一组 submit/result 和一个事后 terminal checkpoint，留存证据未显示第二次提交或 wait 后额外 query。但不存在 contemporaneous `_audit/submitted-checkpoint-06.json`；该缺口不能补造，也不能用事后文件冒充，所以本文不把“未见第二次提交”扩大为无保留的绝对唯一性证明。brief 明确本会话原生 imagegen 不可用，已记录后停止。历史 run03、run04、run05、生产代码、测试、SPEC、Plan 和并发 HERO 文件均未修改；未暂存、未提交。

## 固定输入与 analysis 门禁

- run：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/run-20260714-double-necklace-06`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- 分类快照 SHA-256：`790909D70B6B6FF3EFE448657B541CE27455C9B7BDDA378BD3B6AD7163BDD281`
- run06 analysis 输入：`_inputs/necklace-worn-double-analysis-rerun-06.json`

run03 `analysis/product_analysis.json` 被逐字复制为 run06 输入。run03 原文件、run06 输入和 run06 最终 analysis 的原始 SHA-256 均为 `6E0FDEFA1CDE11954117D182FA6A5B6542B1C29685A4986AFD94665B194FE9C7`；规范化 `ProductAnalysis` SHA-256 均为 `A3A4DA5C7BF1ED9138AA584372E27606312F1024DEA62FC0FBA2463E64EAB302`。没有修改任何 analysis 字段。

## prepare-review 与 decision

正式 `prepare-review` 未传 `output_role`，退出码 0。scorer 结果为：

| rank | 文件 | score |
| ---: | --- | ---: |
| 1 | `微信图片_20260515152026_434_1.jpg` | 228 |
| 2 | `微信图片_20260519175542_452_1.png` | 228 |
| 3 | `微信图片_20260520114417_523_1.jpg` | 223 |

rank2 的源图、review 副本和最终 `hand-reference.png` SHA-256 均为 `99D8B5F7119C2DA519D5488D5293A472408BB4AE8B9A8E5F01B12AF6D664DD7C`。正式 decision 为 `generate_selected`、`selected_ranks=[2]`、`fidelity_confirmed=true`，没有 `output_role`。

首次 `record-decision` 因把工作区相对 canonical 路径按 run 根再次拼接而退出 1，且未写入 decision。根因由 `_resolve_constraints_path()` 的相对路径规则确认；随后仅把同一 canonical 改为绝对路径做最小重试，退出码 0。没有改变 canonical 内容或产品假设。

最终 confirmation snapshot 为：

`necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`

## 六项人工补强 canonical

run06 canonical 绑定最终规范化 analysis，`review_status=corrected`，原始 SHA-256 为 `0891A8852FE80752CB673A935DD3E6A96BF03362CF43AA50BA6999696BF1634B`。原五项与 run03 逐字段相同，最终 `must_keep.name` 顺序精确为：

1. `同一条连续长链双圈关系`
2. `上短下长层间落差`
3. `红橙色连续渐变区`
4. `唯一大红圆珠串接关系`
5. `不可见扣头不补造`
6. `浅海蓝微珠颗粒形态与尺度`

第六项完整记录 brief 指定的 `source_text`、`location`、`visual_shape`、`relationship`、6 条 `forbid` 和 `qc_question`：浅海蓝主体微珠必须细小密集、近圆或细小切面、半透明并保留细碎反光，禁止整体放大、椭圆/米珠化、桶珠/管珠化、降低密度或扩大间距、改为金属粗链节或不透明塑料感。不存在 `must_keep=吊坠`。

## submit 前硬门禁

`_audit/preflight-gate-06.py` 对 canonical/Prompt 缺失、六项字段不精确、吊坠互斥、人体纠偏文案、`输出用途：`、Prompt validator 非 0、generation 非空或已有 task ID 均执行硬拒绝。首次和 submit 前即时最终运行均退出 0，31 项检查全部为 true：

- analysis 原始字节与 run03 完全一致，规范化摘要一致；
- canonical 绑定最终 analysis，原五项与 run03 相同，第六项字段精确，六项 name 顺序精确；
- Prompt 含 `主吊坠：无`，不存在要求保留吊坠结构、所属层或连接关系的正向互斥文案；
- Prompt 明确“细小密集”“近圆或细小切面”“半透明”，并明确禁止长椭圆、米珠、桶珠、管珠和粗链节；
- Prompt 不含 run04 的人体纠偏文案，不含 `输出用途：` 行；
- `validate_prompt_contract.py` 退出 0；
- generation 根为空，无 submit JSON 或 task ID。

预构建 Prompt 与正式 `generation/01/prompt.txt` SHA-256 均为 `04D82EE3B39E19AFBCE1B15B06F04E27E18ABE82A154D17FF5888C6337604D3D`。

## 单个留存任务终态

| 项目 | 值 |
| --- | --- |
| generate 调用次数 | `1` |
| 模型文件 | `generation/01/model.txt` 记录 `gpt_image_2` |
| 画幅 / 分辨率证据边界 | CLI 默认、Prompt 和 expected 记录为 `3:4 / 2K`；无脱敏出站 payload，平台实际请求参数未获独立证实 |
| out task ID | `run-20260714-double-necklace-06-rank-02-3454e1e5` |
| 平台 task ID | `order_zOJpoWtoYnpTQN0D7-eKv` |
| submit | `statusCode=200 / pending / estimated_credits=2.5` |
| terminal | `failed / TIMEOUT` |
| 平台错误 | `Upstream service timed out. Please try again later.(上游服务响应超时，请稍后重试。)` |
| credits_used | 未返回 |
| output URL / result.png | 无 / 无 |
| 第二次提交 | 留存证据未显示；缺少 contemporaneous post-submit checkpoint，不能作绝对证明 |
| wait 后额外 query | `否` |

`generation/01/result.json` 是留存 CLI generate 内建 wait 的终态 query 响应；其精确副本保存为 `_audit/query-terminal-06.json`，留存证据未显示额外网络 query。`submit.json` SHA-256 为 `6282E0E45B6E99A502B02F771C72F5EDE41C5AB9B0B3D781DA5CA69AFC7D2086`，`result.json` SHA-256 为 `27FA152E6E3A0231EC4FBCDF1D2AB601D8EDFBCACC10D5991B577209F63920E2`。

`submit.json` 保存平台接受结果和 out task ID，但不包含出站请求 payload、画幅或分辨率字段。`submit-authorization-06.json` 与 `generate-06.invocation.txt` 中对应字段均明确标为 `expected_*`；它们证明提交前目标，不是平台实际请求参数的独立回执。提交后也没有 contemporaneous `submitted-checkpoint-06.json`，现有 `terminal-checkpoint-06.json` 是事后终态记录。

## 三图 QC 与 validators

平台未返回 output URL，也没有 `result.png`。因此无法把产品源、rank2 和原始结果做三图对照，六项 fidelity 与 runtime checklist 均不能作视觉判定。本轮没有调用 `qc` CLI，没有创建 `qc.json`，QC 状态是“未执行”，不是 `pass`、`rerun` 或 `reject`。尤其第六项微珠是否仍为细小密集、近圆/细切面且半透明无法判断；不得用 Prompt 门禁通过代替图像 QC。

新鲜 validator 原始 stdout、stderr 和退出码保存在 `validation-final/`：

| 验证器 | 退出码 | 结果 |
| --- | ---: | --- |
| `validate_prompt_contract.py` | 0 | `Prompt 契约校验通过` |
| `validate_qc_record.py` | 2 | 找不到 `generation/01/qc.json` |
| `inspect_run_artifacts.py` | 1 | 缺 result.png、qc.json，result status 非 completed |

非零结果准确反映平台失败后的不完整 run，不能通过伪造原图、QC 或 completed 状态消除。

## Git/hash 审计与范围

- task-start：`2026-07-14T01:15:37.3159325+08:00`，执行者 `task11-run06-executor`。
- pre-submit：`2026-07-14T01:23:03.4043187+08:00`，执行者 `task11-run06-executor`。
- 两阶段均保存带时间、命令和退出码的 Git status、diff stat，以及同一 `run06-fixed-v1` 关键路径集的 43 项 SHA-256 manifest。
- start 与 pre-submit 的 Git status 主体和 diff stat 主体一致；manifest 路径集合完全一致。历史 run03/04/05 关键文件摘要未发生变化。
- 原三份报告完成后，控制器曾于 `2026-07-14T01:42:27.3420838+08:00` 采集原 controller-end；本次独立审查修订发生在该快照之后。修订完成后的新 end manifest 尚未采集，本文不预先引用或补造，应由控制器在全部五份 Markdown 修订后重新采集并标注采集者与时点。

本轮只新增 run06、run06 输入/审计/validator 证据并修订三份报告；没有修改生产代码、测试、SPEC、Plan、历史 run 或并发 HERO 文件，没有暂存或提交。

## 最终关注项

1. 六项 canonical 和 submit 前 Prompt 均通过门禁，但平台上游 TIMEOUT 导致没有成图，不能完成第六项视觉假设验证。
2. 平台只返回 `estimated_credits=2.5`，没有返回 `credits_used`，本轮不计入确认消耗。
3. 留存证据未显示第二次 submit/generate、额外 query 或 imagegen fallback；但缺少 contemporaneous post-submit checkpoint，不作超出留存证据的绝对唯一性断言。
4. 模型文件实证 `gpt_image_2`；`3:4 / 2K` 仅是 CLI 默认、Prompt 和 expected 记录，未留存脱敏出站 payload。
5. 普通项链双层真人佩戴成功矩阵仍未通过：run03 人物迁移 reject、run04 invalid canonical 且平台失败、run05 微珠漂移 reject、run06 平台 TIMEOUT 且无 QC。
