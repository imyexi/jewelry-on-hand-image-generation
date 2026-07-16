# 任务 4：定向回归与三款戒指真实重新生成

## 目标

使用修正后的 generation 契约，在全新 run 根目录重新生成 JH025、JH026、JH501 三张戒指上手图。每个模型任务只能接收两张图：选定 Rank 的手部构图参考图 + 产品上手图；细节图仅供 review、结构分析、canonical 和人工 QC。

## 必须先读

- `C:\Users\Administrator\yuan-image\.agents\skills\aireiter-image-generation\SKILL.md`
- `reference/superpowers/plans/2026-07-15-ring-product-on-hand-identity.md`
- `skills/jewelry-on-hand-workflow/references/workflow.md`

## 输入与输出

历史输入 run 只读，不得修改：

```text
output/ring-feishu-test/2026-07-15/runs-local-ref-v2/JH025-hand-worn
output/ring-feishu-test/2026-07-15/runs-local-ref-v2/JH026-hand-worn
output/ring-feishu-test/2026-07-15/runs-local-ref-v2/JH501-hand-worn
```

每个新 run 的 `--product-image` 使用对应历史 run 的 `input/product-on-hand.jpg`；`--product-detail-image` 使用对应 `input/product-detail.jpg`；`--analysis-json` 使用对应历史 run 的 `analysis/product_analysis.json`。

分类表：

```text
output/ring-feishu-test/2026-07-15/ring-test-reference-catalog.xlsx
```

新 run 根目录：

```text
output/ring-feishu-test/2026-07-15/runs-on-hand-identity-v3
```

最终通过图目录：

```text
output/ring-feishu-test/2026-07-15/final-on-hand-identity
```

验证与 QC 临时文件：

```text
output/ring-product-on-hand-identity/2026-07-15
```

不得覆盖上述历史输入 run 或 `output/ring-feishu-test/2026-07-15/final/`。

## 步骤 1：定向回归

```powershell
py -m pytest tests\test_generation.py tests\test_cli.py::test_prepare_review_help_limits_product_detail_image_to_review_context tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

全部通过才能提交真实生成。

## 步骤 2：创建三个新 run

对三个 SKU 分别执行 `prepare-review`，使用上文对应的产品上手图、细节图、分析 JSON、分类表，并固定：

```text
--output-role hand_worn
--output-root output/ring-feishu-test/2026-07-15/runs-on-hand-identity-v3
--run-id <SKU>-hand-worn
```

若新根目录已存在任何内容，立即停止并报告，不得删除或覆盖。

## 步骤 3：记录决策

固定沿用首轮人工选择：

```text
JH025 -> Rank 3
JH026 -> Rank 1
JH501 -> Rank 1
```

对每个 run 执行 `record-decision`：

```text
--action generate_selected
--selected-ranks <rank>
--fidelity-confirmed
--output-role hand_worn
```

可沿用历史 review_decision 的 `fidelity_notes`，但不得复制旧 decision 文件本身。

## 步骤 4：生成前 dry check

逐个证明：

- `input/product-on-hand.jpg` 存在。
- `input/product-detail.jpg` 存在且哈希不同。
- decision Rank 与固定映射一致。
- 当前 generation 代码和回归测试保证 helper 只有两张图，第二张为传入的 `product-on-hand.jpg`，没有第三张细节图。

把 dry check 结果写入：

```text
output/ring-product-on-hand-identity/2026-07-15/preflight.json
```

## 步骤 5：AIReiter 生成

Helper：

```text
skills/aireiter-image-generation/scripts/aireiter_image_helper.py
```

对三个新 run 执行：

```powershell
py -m jewelry_on_hand.cli generate --run-root <run-root> --helper-script skills\aireiter-image-generation\scripts\aireiter_image_helper.py
```

默认使用 `gpt_image_2`、`3:4`、`2K`。记录每个 `out_task_id`、最终状态、模型和积分。等待 `completed` 并确认 `result.png` 存在。

若 AIReiter 明确失败，严格按 AIReiter skill 的一次 imagegen fallback 规则执行；不得反复换通道。若生成成功但 QC 失败，按现有 retry matrix 写入真实 QC 后再调用 CLI `generate`，让系统切换未尝试 Rank/纠偏；不得覆盖旧 generation。

## 步骤 6：身份图审计

每个 generation 必须满足：

- `input/product-on-hand.jpg` SHA-256 等于 `generation/NN/product-identity.jpg`。
- `input/product-detail.jpg` SHA-256 与上述哈希不同。
- `product-identity.jpg` 的文件大小与上手图一致。
- `submit.json` 仅是 provider 响应时，不得伪称它包含输入列表；“细节图未送模”证明应组合使用：任务 1 回归测试、`generation.py` 的第二图路径、生成目录审计副本哈希和不存在第三图的 `_submit_command` 契约。

## 步骤 7：逐图严格视觉 QC

必须使用图像查看工具实际检查每个新 `result.png`，并对照对应：

- `input/product-on-hand.jpg`：唯一模型产品身份源。
- `input/product-detail.jpg`：只用于人工结构/QC 对照。
- `generation/NN/hand-reference.*`：只用于手势与构图。

不得直接复制历史 QC 结论。每个最终通过图都要写完整且针对新结果的：

- 5 条 `fidelity_checks`；
- 18 条 `checklist_checks`；
- 数量、手侧、食指根部、戒指结构、接触/遮挡、手指畸变、产品源手迁移、水印/文字逐项结论。

只有全部 pass、`critical_failures` 为空时，才能通过 CLI `qc --status pass`。若任一关键项无法从图中确认或明显失败，必须如实 reject/rerun，不得为满足三图交付而虚报。

## 步骤 8：验证 Prompt、QC 与 run 完整性

对每个最终 generation 运行：

```powershell
py skills\jewelry-on-hand-workflow\scripts\validate_prompt_contract.py <generation>\prompt.txt
py skills\jewelry-on-hand-workflow\scripts\validate_qc_record.py <generation>\qc.json
py skills\jewelry-on-hand-workflow\scripts\inspect_run_artifacts.py <run-root>
```

还要核对 Prompt 字符数，并记录实际选用 Rank。

## 步骤 9：交付与验证报告

只复制最终 QC 为 `pass` 的三张结果，命名：

```text
JH025-hand-worn.png
JH026-hand-worn.png
JH501-hand-worn.png
```

写入：

```text
output/ring-product-on-hand-identity/2026-07-15/verification.json
```

每个 SKU 必须记录：run、最终 generation、模型、任务 ID、credits_used、参考 Rank、产品上手图 SHA-256、审计身份图 SHA-256、细节图 SHA-256、细节图未送模证明、Prompt 字符数、5/5 fidelity、18/18 checklist、validator/inspector 结果、最终 QC 状态。

同时写执行报告：

```text
reference/superpowers/reports/2026-07-15-ring-on-hand-task-4-report.md
```

## 工作区约束

- 所有测试/生成产物必须在 `output/`；Markdown 报告放 `reference/`。
- 不写回飞书，不修改分类表，不修改历史 run。
- 除新 output 产物和任务报告外，不修改代码、测试、技能或产品文档。
- 不执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
