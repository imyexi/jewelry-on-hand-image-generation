# Workflow

## 适用范围

使用此流程处理手链/手串类产品上手图：从飞书 Base 或本地 SKU 列表读取产品图，选择手部参考图，等待用户确认 rank，再调用 AIReiter 生成并做 QC。

## 完整流程

1. 解析用户输入：飞书 Base URL、日期批次、货盘表名、SKU 列表、是否重跑。模型默认由规则选择，不把 nanobanana 当作首选。
2. 如果用户提供飞书 Base URL，使用 `lark-base` 读取目标表和记录；只读数据，不默认写回。
3. 下载或定位“产品上手图”，保存到项目 `output/`。
4. 为每个 SKU 建立独立 run 目录，并把产品图复制为 `input/product-on-hand.jpg`。
5. 写入或读取 `analysis/product_analysis.json`，确认 `product_type` 是手链/手串。
6. 读取参考图分类表，自动筛选 Top 3，并写入 `analysis/selected_references.json`。
7. 生成 `review/` 包：候选图副本、contact sheet、`review.html` 和候选说明。
8. 停止并请用户为每个 SKU 选择 rank 1、2 或 3；不要自动默认 rank 1。
9. 用户选择后写入 `review/review_decision.json`。
10. 生成前再次校验：产品图存在、参考图存在、决策可生成、所选 rank 在 Top 3 中。
11. 使用项目 `jewelry_on_hand.prompt_builder.build_prompt` 构建 prompt。
12. 使用 `scripts/validate_prompt_contract.py` 检查 prompt。
13. 选择模型：默认使用 `gpt_image_2`；统计同一 run 内 `generation/NN/qc.json` 中 `status != "pass"` 的记录，超过 1 次后下一次生成才使用 `nano_banana_v2` 兜底。
14. 调用 `aireiter-image-generation`，并把实际模型写入 `generation/NN/model.txt`。
15. 保存 `model.txt`、`prompt.txt`、`hand-reference.*`、`submit.json`、`result.json`、`result.png`。
16. 按 `references/qc-checklist.md` 做 QC，并写入 `generation/NN/qc.json`。
17. 如果 QC 为 `rerun` 或 `reject`，同一 run 内下一次生成写入后续 `generation/NN/`，不覆盖旧产物；跨批或重新拉货盘时才创建新的带时间戳 rerun 目录。
18. 最终汇总只收录 QC 为 `pass` 且通过原图手腕/手臂迁移检查的图片。
19. 如生成最终汇总 JSON，使用 `scripts/inspect_run_artifacts.py <run-root> <final-summary.json>` 校验汇总只引用当前 run 内 QC 为 `pass` 的结果图。

## Review Gate

生成前必须存在合法 `review/review_decision.json`。允许进入生成的形式：

```json
{"action":"generate_rank_1","selected_ranks":[1]}
{"action":"generate_selected","selected_ranks":[2]}
{"action":"generate_multiple","selected_ranks":[1,3]}
```

禁止进入生成：

```json
{"action":"rerank","selected_ranks":[]}
{"action":"manual_reference","manual_reference":"..."}
```

`selected_ranks` 必须在 1..3 内、不能重复，并且必须存在于 `analysis/selected_references.json`。

## Prompt Gate

生成前必须重新构建并校验 prompt，不要复用旧 prompt。prompt 必须明确：

- 内部图1是手部参考图。
- 内部图2是产品上手原图。
- 产品身份来自内部图2，但手腕、手臂、皮肤来源必须来自内部图1。
- 禁止把内部图2里的手串和原手腕作为整体贴到内部图1。

## Model Selection Gate

生成前必须先检查当前 run 的 `generation/` 历史：

- 默认模型是 `gpt_image_2`。
- `generation/NN/qc.json` 中 `status != "pass"` 计为一次 QC 未通过，`rerun` 和 `reject` 都计入。
- QC 未通过次数为 0 或 1 时，继续使用 `gpt_image_2`。
- QC 未通过次数超过 1 次时，下一次生成使用 `nano_banana_v2` 兜底。
- 已有非空 `generation/NN/` 如果缺少 `qc.json`，必须停止，不得跳过目录继续生成。
- 每个生成目录必须写入 `model.txt`，内容为本次实际提交的模型名。

## QC Gate

QC 是交付前 gate，不是可选总结。QC 记录必须包含：

- `status`: `pass`、`rerun` 或 `reject`。
- `passed`: 通过项列表。
- `failed`: 失败项列表。
- `notes`: 文字说明。

QC 必须明确写到“原图手腕/手臂/皮肤块是否随手串迁移”。只写“手部自然”不够。

## Final Summary Gate

最终汇总只能引用当前 run 内 `generation/NN/result.png`，并且对应 `generation/NN/qc.json` 的 `status` 必须是 `pass`。不要把 `rerun`、`reject` 或未写 QC 的图片放入最终交付列表。

## 重跑命名

使用新的时间戳目录：

```text
output/auto_reference_runs/feishu-<date>-<SKU>-gpt-image-2-<timestamp>/
output/auto_reference_runs/feishu-<date>-<SKU>-rerun-<timestamp>/
```

不要覆盖已有 `generation/01/result.png`。同一 run 的重跑使用后续 `generation/NN/`；如果发现非空 `generation/NN/` 缺少 `qc.json`，先补 QC 或人工处理，不要跳过。

## Dry Run 规则

dry run 只能检查 gate 和列风险，不调用 AIReiter，不下载新结果，不写回飞书，不伪造 `qc.json` 或 `result.png`。
