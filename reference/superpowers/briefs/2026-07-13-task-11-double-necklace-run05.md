# Task 11 普通项链双圈真人佩戴 run 05 Brief

## 目标

建立全新 `run-20260713-double-necklace-05`，继续使用合法 rank 2 人物参考，但完全撤销 run 04 新增的人体纠偏分析文案。产品分析逐字复用 run 03，显式导入 run 03 已审计的五项 canonical；所有语义门禁通过后，只提交一次 `gpt_image_2 / 3:4 / 2K`，等待终态、下载原图并严格 QC。

历史 run 03 的 QC reject 和 run 04 的 invalid canonical + platform failed 必须原样保留，均不得改写或计为成功。

## 根因与单变量假设

run 04 失败前已经存在两类问题：

1. 新增分析文案反复出现下颌、胸部、皮肤、人物像素等表述，并与 rank 2 低领人物参考组合后被平台 `CONTENT_POLICY_BLOCKED`。平台没有返回更细的 policy 原因，不能断言单一触发词，但下一轮应撤销这些新增文案。
2. 默认 canonical 从产品描述的否定句“不是悬挂吊坠”误识别出 `must_keep=吊坠`，正式 Prompt 同时出现“主吊坠：无”和保留吊坠结构。run 04 因此不是规格有效 proof。

run 05 只测试一个有效假设：在使用 run 03 原始产品分析与五项 canonical 的情况下，rank 2 更明显的人物/服装/背景差异能否避免产品源人物局部迁移。

## 固定输入

- run ID：`run-20260713-double-necklace-05`
- 输出根：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- 产品分析来源：run 03 的 `analysis/product_analysis.json`
- canonical 来源：run 03 的 `analysis/product_fidelity_constraints.json`

将 run 03 产品分析复制到 `_inputs/necklace-worn-double-analysis-rerun-05.json`，复制后必须验证 SHA-256 与 JSON 规范化内容均完全一致。不得修改 `composition`、`special_requirements` 或其他字段。

## 四阶段流程

### 1. prepare-review

- 执行正式 CLI `prepare-review`，不指定 `output_role`。
- scorer 必须重新产生真实 Top 3；只有 rank 2 仍为 `微信图片_20260519175542_452_1.png`、score 228、源图/review 副本摘要一致时才继续。
- 不得手改 rank、分数、参考图或 selected metadata。

### 2. record-decision

- 使用 `generate_selected`，只选择 rank 2。
- 使用 `--fidelity-constraints-path` 显式导入 run 03 canonical，不能确认 prepare 默认生成的 `must_keep=吊坠`。
- 不指定 `output_role`。
- 最终 confirmation snapshot 必须为 `necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`。

最终 canonical 必须且只能包含以下五个 `must_keep.name`：

1. `同一条连续长链双圈关系`
2. `上短下长层间落差`
3. `红橙色连续渐变区`
4. `唯一大红圆珠串接关系`
5. `不可见扣头不补造`

`detected_keywords`、`must_keep` 和 `must_not_change` 中不得出现把产品定义成吊坠的内容。

### 3. generate 前硬门禁

调用模型前必须由脚本逐项检查并保存证据：

- `analysis/output_role.json` 不存在，decision 的 `output_role` 为 `None`。
- canonical 的 analysis SHA-256 与 run 05 最终规范化 analysis 匹配。
- canonical 五项名称精确匹配上面的闭集，数量为 5；不存在 `must_keep=吊坠`。
- Prompt 包含 `主吊坠：无`，不得包含要求保留吊坠、吊坠所属层或吊坠连接关系的互斥 canonical 文本。
- Prompt 不包含 run 04 新增的“最终人物、正面下颌……”和“禁止继承其侧转下颌……”纠偏文案。
- Prompt 不含任何 `输出用途：` 行。
- `validate_prompt_contract.py` 退出码为 0。
- `generation/` 只能是 prepare 创建的空根目录，不得存在非空 `generation/NN`、`submit.json` 或第二个任务 ID。

### 4. 唯一真实生成与 QC

- 只执行一次正式 CLI `generate`，模型固定 `gpt_image_2`、画幅 `3:4`、分辨率 `2K`。
- 使用已修复的 helper UTF-8 路径；submit/wait 子命令必须带 `-X utf8`，父进程 strict UTF-8 解码。
- 保存 submit、wait/query、out task ID、平台 task ID、终态、credits、result JSON 和原图。
- 如果平台失败，不得重复提交；原生 imagegen fallback 在本会话不可用，记录后停止。
- 如果 completed，必须查看原始 2K 图并完成全量 runtime checklist 与五项 fidelity checks。
- 任一产品源人物局部迁移、双圈结构错误、渐变区/大红圆珠错误、自动补链或严重穿模都不得 pass。
- 如 QC 为 reject/rerun，完整保留并停止，不得在本任务内第二次生成。

## 审计与验证

在任务开始时、submit 前、任务结束时分别保存：

- `git status --short`
- `git diff --stat`
- run 03 关键文件与 run 05 输入/decision/canonical/prompt/result/QC 的 SHA-256 manifest

这些快照必须带采集时间，不能用事后 late-review 冒充当时证据。

对 run 05 保存三项验证器原始 stdout/stderr/退出码：

- `validate_prompt_contract.py`
- `validate_qc_record.py`
- `inspect_run_artifacts.py`

更新三份报告时必须全文修订相关结论：

- `reference/superpowers/reports/2026-07-13-task-11-double-necklace-run05-report.md`
- `.superpowers/sdd/task-11-report.md`
- `.superpowers/sdd/task-11-double-necklace-report.md`

不得修改生产代码、测试、SPEC、Plan、run 03 或 run 04。不得处理外部并发 HERO 测试失败。未经控制器指示，不暂存、不提交。

## 返回契约

返回 `DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT` 或 `BLOCKED`，并包含：run 路径、唯一 out task ID、平台 task ID、credits、QC、三项 validator、canonical 五项门禁、是否第二次提交、Git 审计和关注项。
