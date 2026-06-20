# CLI 手工串联流程

本文说明 `jewelry-on-hand` CLI 的人工 review 与端到端 gate 流程。所有命令建议在仓库根目录执行，并为每次新产品生成使用新的 `--run-id`。

## 1. 准备 Review 包

运行 `prepare-review`：

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\product_analysis.json `
  --classification .\path\to\catalog.xlsx `
  --output-root .\outputs\auto_reference_runs `
  --run-id demo
```

如果有用户提供的尺寸信息，可同时传入 `--dimensions-json`：

```powershell
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\product_analysis.json `
  --dimensions-json .\path\to\product_dimensions.json `
  --classification .\path\to\catalog.xlsx `
  --output-root .\outputs\auto_reference_runs `
  --run-id demo
```

该命令会完成以下动作：

- 写入前检查目标 run 根目录：如果 `output_root/run_id` 已存在且非空，命令返回 1 并拒绝继续，避免沿用旧的 `review/review_decision.json` 绕过人工 review。
- 创建本次运行目录，并把用户产品图复制为 `input/product-on-hand.jpg`。
- 生成产品分析提示词 `analysis/product_analysis_prompt.txt`。
- 如果提供 `--dimensions-json`，写入 `input/product_dimensions.json`，并把尺寸信息放入产品分析提示词。
- 加载并校验传入的产品分析 JSON；第一版只支持手串/手链产品，其他品类会停止。
- 写入 `analysis/product_analysis.json` 作为可追踪产物。
- 生成并写入 `analysis/product_fidelity_constraints.json`，把随形、跑环、双尖、回纹、貔貅、桶珠、雕刻、吊坠、流苏、链坠等关键结构转成 `must_keep`；如果没有局部关键识别点，也必须写入 `must_keep: []` 和 `review_status: not_applicable`。
- 对小尺寸、半透明、低对比或遮挡的关键结构，建议写入 `input/detail-crops/` 局部裁切图，供 review 和 QC 使用。
- 读取分类 workbook（`分类明细` 工作表），筛选并排序自动参考图。
- 基础候选按质量分写入 `analysis/reference_candidates.json`；Top 3 会再经过多样性重排，不是简单取最高分前三张。
- Top 3 应尽量覆盖三种生成方向：安全保真参考、生活方式参考、差异化构图参考。同一风格分类、同一场景簇、同一姿势簇或同一拍摄组会被降权，候选池不足时才允许重复。
- 批量处理多个 SKU 时，还必须执行批次级多样性重排：对本批次已经使用过的同一张参考图施加强惩罚，并对已大量使用的拍摄组、风格簇降权；重排后重新写入各 run 的 `analysis/selected_references.json` 和 `review/rank-N-*`。
- 先把选中的参考图复制到 run 内 `review/rank-N-...`，再写入 `analysis/selected_references.json`；生成阶段只使用这些 run 内副本，不依赖外部原始 catalog 图片路径。
- 写入 `analysis/reference_candidates.json` 记录候选图，候选条目可继续指向原始候选路径以便追踪。
- 生成 `review/review.html`，供用户查看候选参考图和产品关键识别点。
- 此阶段不会创建 `review/review_decision.json`，必须等待用户人工确认。

如果缺少 `--analysis-json`，`prepare-review` 会先创建新的 run、复制产品图、生成 `analysis/product_analysis_prompt.txt`，然后返回 1。这个 prompt-only run 只是临时分析辅助产物，不是后续正式 run。补齐视觉分析 JSON 后请使用新的 `run-id` 重新跑完整流程，或由操作员人工确认临时 run 已不需要后清理该目录；不要复用这个非空 `run-id`。

## 2. 记录 Review 决策

用户在 `review/review.html` 中选择候选图后，还必须确认或修正产品关键识别点。不要把用户补充的结构只留在聊天记录里；需要更新 `analysis/product_fidelity_constraints.json`，并把 `review_status` 置为 `confirmed`、`corrected` 或 `not_applicable`。

随后运行 `record-decision`：

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\demo `
  --action generate_rank_1 `
  --fidelity-confirmed
```

如果只想生成指定的单张非 rank 1 参考图，使用 `generate_selected`，且只传 1 个 rank：

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\demo `
  --action generate_selected `
  --selected-ranks 2 `
  --fidelity-confirmed
```

也可以选择多个排名，使用 `generate_multiple`，且至少传 2 个 rank：

```powershell
jewelry-on-hand record-decision `
  --run-root .\outputs\auto_reference_runs\demo `
  --action generate_multiple `
  --selected-ranks 1,2 `
  --fidelity-confirmed
```

该命令会写入 `review/review_decision.json`。`generate_rank_1` 会规范化为 `selected_ranks: [1]`；如果显式传入 `--selected-ranks`，只能传 `1`，不能传 `2` 或 `3`。`generate_selected` 必须且只能选择 1 个 rank；`generate_multiple` 至少选择 2 个 rank。`--selected-ranks` 不能包含重复排名。

决策文件必须记录产品保真约束是否已确认；生成类 action 需要 `--fidelity-confirmed`，写入 `fidelity_confirmed: true`。可选使用 `--fidelity-notes` 记录补充说明，或使用 `--fidelity-constraints-path` 指向非默认约束文件。生成前不能只依赖参考图 rank；必须同时满足产品保真约束已确认。

`manual_reference` 可用于记录人工参考图路径，但第一版不能进入 `generate`。如果需要生成，请改用 `generate_rank_1`、`generate_selected` 或 `generate_multiple` 重新选择已入选 rank；手动参考图生成留待未来版本支持。

## 3. 生成图片

确认 `review/review_decision.json` 存在且是可生成决策后，运行 `generate`：

```powershell
jewelry-on-hand generate `
  --run-root .\outputs\auto_reference_runs\demo
```

`generate` 会先检查 review gate：如果缺少决策文件，或决策为 `rerank` / `manual_reference`，流程会停止。通过 gate 后，命令会重新加载并校验 `analysis/product_analysis.json` 的产品品类；非手串/手链 run 会返回非 0 且不会调用生成。

生成前还必须加载并校验 `analysis/product_fidelity_constraints.json`：文件必须存在、JSON 合法，且 `review_status` 必须为 `confirmed`、`corrected` 或 `not_applicable`。如果 `must_keep` 非空但仍是 `pending`，流程必须停止，等待人工确认或补充。

随后命令读取 `analysis/selected_references.json`，为每个选中排名生成提示词，并调用 AIReiter helper。默认提交模型为 `gpt_image_2`；如果同一 run 里已有超过 1 个 `generation/NN/qc.json` 的 `status` 不是 `pass`，下一次生成会自动改用 `nano_banana_v2` 兜底。

生成目录按“本次生成序号”保存，而不是按参考图 rank 命名：只选择 rank 2 时仍写入 `generation/01/`；选择 rank 2 和 rank 3 时写入 `generation/01/`、`generation/02/`。如果已有带 `qc.json` 的历史生成目录，下一次会写入后续序号；如果已有非空目录但缺少 `qc.json`，系统会停止，避免覆盖或跳过未质检产物。每个目录会写入 `model.txt` 记录实际模型。`wait` 完成后会保存 `result.json` 并下载第一张输出图为 `result.png`；使用 `--no-wait` 时只保存提交阶段产物。

生成阶段使用 `analysis/selected_references.json` 中指向的 run 内 review 副本作为自动参考图，因此外部 catalog 原始图片被移动、删除或改动时，不应影响已完成 review 的 run。`selected_references.json` 的 metadata 会保留原始来源路径与相对路径，用于追踪和提示词判断（例如对镜/镜面构图检测）。

内部提交给 AIReiter 的图片顺序固定为：

1. 自动参考图在前：只用于手部姿势、手模构图、场景氛围、光线和画面比例参考。
2. 用户产品图在后：作为产品款式、颜色、珠子排列、尺寸感和可见细节的唯一保真依据。

默认 helper 脚本为 `skills/aireiter-image-generation/scripts/aireiter_image_helper.py`。如果只想提交不等待结果，可加 `--no-wait`。

Prompt Builder 必须把 `product_fidelity_constraints.must_keep` 写入“本产品必须保留的关键识别点”，并把 `must_not_change` 写入“产品整体禁止变化”。不能只依赖 `visible_appearance` 或临时 prompt 补丁。

## 4. 写入 QC 结果

每个生成目录完成质检后，运行 `qc`：

```powershell
jewelry-on-hand qc `
  --generation-dir .\outputs\auto_reference_runs\demo\generation\01 `
  --status rerun `
  --passed 无水印,构图正确 `
  --failed 主珠被裁切 `
  --notes 需要调整参考图后复跑
```

该命令会写入 `generation/NN/qc.json`。`--status` 只能是以下三种之一：

- `pass`：通过，可交付。
- `rerun`：需要复跑。
- `reject`：拒绝使用。

QC 必须逐项检查 `analysis/product_fidelity_constraints.json` 中的 `must_keep`。任一关键识别点缺失、改款或被泛化时，`--status` 不能使用 `pass`；轻微可修复问题用 `rerun`，严重识别错误用 `reject`。建议在 `qc.json` 中增加 `fidelity_checks`，记录每个 `qc_question` 的结果。

如果已准备好逐项检查 JSON，可用 `--fidelity-checks-json` 写入：

```powershell
jewelry-on-hand qc `
  --generation-dir .\outputs\auto_reference_runs\demo\generation\01 `
  --status rerun `
  --failed 关键识别点失败 `
  --fidelity-checks-json .\path\to\fidelity_checks.json
```

`fidelity_checks.json` 必须是数组；每项包含 `name`、`question`、`result`、`notes`。其中 `result` 只能是 `pass`、`rerun` 或 `fail`。任一关键识别点结果不是 `pass` 时，整体 `--status` 不能使用 `pass`。
