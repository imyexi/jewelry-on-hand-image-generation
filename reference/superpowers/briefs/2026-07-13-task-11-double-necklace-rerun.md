# Task 11 普通项链双圈真人佩戴复跑 Brief

## 目标

在不修改或覆盖历史 `run-20260713-double-necklace-03` 的前提下，新建一个正式 run，使用真实 rank 2 人物参考完成一次 `gpt_image_2 / 2K` 生成、下载和严格人工 QC。只有成图与完整 QC 都通过，才能把普通项链双层真人佩戴计入成功矩阵。

## 已确认事实

- 产品源为 `reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`，SHA-256 为 `D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`。
- 产品身份为 `necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`。
- 这是同一条连续长微珠链绕颈双圈，不是两件独立项链，也不是带链吊坠。
- 历史 `run-20260713-double-necklace-03` 的五项产品结构均通过，但因迁移产品源人物局部而 `reject`；其 Prompt、结果、QC 和验证器证据必须原样保留。
- 历史 Prompt 在 21:17 生成，`output_roles.py` 与 Prompt 校验器在 21:22 完成并发改动。当前代码用相同分析和 rank 1 重建的无角色 Prompt 不含 `输出用途：` 行，校验器退出码为 0；证据位于 `output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/_audit/output-role-current-code/validation-result.json`。不得放宽校验器，也不得修改历史 Prompt。

## 新 run

- run ID 固定为 `run-20260713-double-necklace-04`。
- 输出根目录为 `output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/`。
- 分类表使用已经由 `@oai/artifact-tool` 验证的 output-only 快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`。
- 从 run 03 的最终产品分析复制一份新的输入 JSON 到 `_inputs/`，不得修改 run 03 文件。新 JSON 只允许补充与本次人物来源纠偏直接相关、且不改变产品身份或结构的 `composition` / `special_requirements`：
  - 最终人物、正面下颌、颈部、锁骨、胸部、头发分布、米色低领针织上衣、胸前手部/前臂姿势和明亮室内自然光背景均以内部图 1 为准。
  - 内部图 2 只提供微珠长链、双圈关系、颜色、渐变区、大红圆珠和可见结构；禁止继承其侧转下颌、右侧黑发轮廓、白色无袖上衣、深绿色暗背景或任何皮肤/人物像素。
- 执行正式四阶段流程：`prepare-review -> record-decision -> generate -> qc`。不得直接拼装通过产物。
- `prepare-review` 必须重新产生真实候选和 scorer 排名。只有 rank 2 仍为 `微信图片_20260519175542_452_1.png` 且属于合法 Top 3 时才继续；否则停止并报告，不得改 rank 或分数。
- 人工决策使用 `generate_selected` 且只选择 rank 2；不指定 `output_role`。
- canonical 继续锁定五项：同一条连续长链双圈、上短下长落差、红橙连续渐变区、下层偏左唯一大红圆珠串在线路中、不可见后颈扣头不补造。

## 单次生成假设

本轮只测试一个假设：使用视觉差异更大的 rank 2，并明确人物来源边界，可以避免历史 run 的产品源人物区域迁移。

- 内部图 1 应提供正面颈胸、米色针织低领上衣、胸前手部/前臂和明亮室内自然光。
- 内部图 1 原有吊坠项链、手链、戒指和文字水印必须全部移除。
- 内部图 2 只能提供目标双圈项链；不得带入其侧转下颌、右侧黑发、白色无袖上衣或深绿背景。
- 模型固定为 `gpt_image_2`，画幅 `3:4`，分辨率 `2K`。
- 只允许一次真实 `generate`。必须保存提交响应、`out_task_id`、平台 task ID、轮询终态、credits、原始结果 JSON 和下载后的原图。
- 如果提交失败，按 AIReiter 技能的失败规则处理；不得把“已提交”或 `pending` 写成成功。
- 如果成图为 `rerun` 或 `reject`，完整保留证据并停止，不得在本任务内第二次生成。

## 严格人工 QC

查看下载后的原始 2K 图片后，逐项执行 runtime checklist 和五项 fidelity checks。以下条件必须全部成立才可 `pass`：

1. 同一条连续长链形成且只形成上下双圈，不断裂、不合并、不交叉、不复制，也不是两件独立项链。
2. 上层较短、下层较长，落点和层间落差与产品源一致。
3. 蓝色半透明微珠为主，红橙连续渐变区的相对位置保持。
4. 下层偏左只有一颗明显更大的半透明红色圆珠，且直接串在主线路中，不复制、不悬挂化、不改成吊坠。
5. 不补造、推断或特写不可见后颈扣头和连接结构。
6. 最终人物构图明显采用 rank 2 的正面颈胸、米色针织、胸前手部/前臂和明亮室内光；没有迁移产品源的侧转下颌、白色无袖上衣、深绿背景、皮肤块或人物局部。
7. rank 2 的原吊坠项链、手链、戒指和文字水印全部移除。
8. 项链不穿肤、穿衣、穿发，人物、手部、皮肤、衣服和头发无明显畸变。

任一产品源人物局部迁移必须记录 `source_person_region_migrated`，整体不得 `pass`。层数错误、结构重组、自动补链、核心结构缺失或严重穿模按正式严重错误 gate 处理。

## 验证与报告

- 对新 run 运行并保存 `validate_prompt_contract.py`、`validate_qc_record.py`、`inspect_run_artifacts.py` 的原始输出和退出码。
- Prompt 生成前后确认未指定角色时不存在 `输出用途：未指定`；不得通过添加非法白名单绕过。
- 保存开始/结束 `git status --short`、`git diff --stat`、关键输入和结果 SHA-256，证明没有覆盖并发戒指改动。
- 更新 `.superpowers/sdd/task-11-report.md` 与 `.superpowers/sdd/task-11-double-necklace-report.md` 时修订全文相关结论，不得只在末尾追加与旧结论冲突的说明。
- 新增执行报告 `reference/superpowers/reports/2026-07-13-task-11-double-necklace-rerun-report.md`，记录命令、任务 ID、credits、QC、验证器和最终矩阵状态。
- 不修改生产代码、测试、操作手册、SPEC 或 Plan；若发现代码问题，停止并向控制器报告。
- 不提交或暂存并发戒指文件；未经控制器指示不要创建提交。

## 返回契约

返回 `DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT` 或 `BLOCKED`，并包含：新 run 路径、唯一 out task ID、平台 task ID、credits、QC 状态、三项验证器退出码、是否调用第二次生成、Git 边界和关注项。
