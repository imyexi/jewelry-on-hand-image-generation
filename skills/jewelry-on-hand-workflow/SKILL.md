---
name: jewelry-on-hand-workflow
description: "Use when running the jewelry on-hand image workflow for bracelet/hand-string SKUs from Feishu/Lark Base, local product images, reference review, AIReiter generation, QC, reruns, or final packaging."
---

# Jewelry On-Hand Workflow

编排当前工作区中的珠宝上手图项目流程。运行前先确认当前工作区或用户指定目录包含 `pyproject.toml`、`src/jewelry_on_hand/`、`reference/` 和 `skills/aireiter-image-generation/`；不要依赖某台电脑上的固定绝对路径。这个 Skill 固定流程与 gate，不替代人工参考图选择和结果 QC。

## 协作 Skill

- 飞书 Base 链接、货盘表、多维表格记录：使用 `lark-base`。
- 图片生成、重跑、查询结果：使用 `aireiter-image-generation`。
- 生成失败、手部异常、原图手腕迁移：使用 `superpowers:systematic-debugging`。
- 对外报告完成前：使用 `superpowers:verification-before-completion`。

## 先读哪份参考

- 完整跑批或 dry run：读 `references/workflow.md`。
- 构建、检查或修补 prompt：读 `references/prompt-contract.md`。
- 判定结果可用、重跑或拒绝：读 `references/qc-checklist.md`。
- 分析失败、决定重跑策略：读 `references/troubleshooting.md`。

## 项目定位

- 优先使用 Codex 当前打开的工作区作为项目根目录。
- 如果当前目录不是项目根目录，向上查找同时包含 `pyproject.toml` 和 `src/jewelry_on_hand/` 的目录。
- 如果用户显式给出项目路径，以用户路径为准，但仍需验证上面的项目标记。
- Skill 安装位置只用于读取本 Skill 的 `references/` 和 `scripts/`；业务代码、参考图、运行产物都来自项目根目录。
- 多人/多电脑复用时，先从项目仓库运行 `scripts/install_codex_skills.py` 安装 Skill，再重启 Codex。

## 强制 Gate

不要跳过这些 gate：

1. 产品记录与产品图已保存到项目 `output/`。
2. `input/product-on-hand.jpg` 已存在。
3. `analysis/product_analysis.json` 已存在，且产品类型确认是手链/手串。
4. `analysis/selected_references.json` 已生成 Top 3 候选。
5. `review/` 下已有 review 包，用户已选择 rank。
6. `review/review_decision.json` 已存在且是可生成决策。
7. prompt 通过 `scripts/validate_prompt_contract.py`。
8. 模型选择遵循默认 `gpt_image_2`；同一 run 内 QC 未通过次数超过 1 次后，下一次生成才改用 `nano_banana_v2` 兜底。
9. 生成产物保存 `model.txt`、`prompt.txt`、`hand-reference.*`、`submit.json`、`result.json`、`result.png`。
10. QC 写入 `qc.json`，并明确检查原图手腕/手臂/皮肤块是否随饰品迁移。
11. 最终汇总只包含 QC 为 `pass` 的图片。

## 禁止行为

- 没有 `review_decision.json` 时不要生成。
- `review_decision.json` 为 `rerank` 或 `manual_reference` 时不要生成。
- 不要把自动 Top 3 当作用户确认。
- 不要覆盖已有 `result.png`；同一 run 重跑必须写入后续 `generation/NN/`，跨批重跑才新建带时间戳目录。
- 不要写回飞书，除非用户明确要求。
- 不要提交包含 `???`、`锟` 或 `�` 的乱码 prompt。
- 不要在缺少“原图手腕/手臂迁移检查”的情况下宣称图片可用。
- 不要在 0 或 1 次 QC 未通过时直接切到 `nano_banana_v2`；默认和首次重跑仍用 `gpt_image_2`。
- 不要跳过缺少 `qc.json` 的非空 `generation/NN/`，这表示未完成或未质检产物。

## 输出规则

- 测试过程和运行产物放在项目 `output/` 下。
- 参考流程文档仍放在项目 `reference/` 下；Skill 自身参考文档放在本 Skill 的 `references/` 下。
- 向用户展示本地图片时使用绝对路径。
