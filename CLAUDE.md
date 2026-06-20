# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

一个 Python 命令行工具（`jewelry-on-hand`），把**一张**产品上手原图转成全新的珠宝上手展示图。系统会从参考图分类表中自动挑选参考图（用于姿势 / 构图 / 光线），由人工在 Top 3 中选定，再把两张图提交给 AIReiter 的 `nano_banana_v2` 图生图模型，配合固定模板 prompt 生成。V1 只支持手串/手链；其他品类刻意不在范围内。

代码注释、CLI 帮助文案和报错信息全部是中文——编辑时请保持一致。权威设计文档是 `docs/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md`；各类 schema 与人工串联流程放在 `reference/`（尤其是 `reference/manual-workflow.md`）。

## 常用命令

```powershell
pip install -e ".[dev]"        # 安装 `jewelry-on-hand` 命令行脚本 + pytest
pytest                         # 运行全部测试（pyproject.toml 已配置 pythonpath=src）
pytest tests/test_scoring.py::test_name   # 单个测试（或用 -k <表达式>）
```

仓库没有 `__main__.py`，所以 `python -m jewelry_on_hand` **不可用**——请用安装后的 `jewelry-on-hand` 命令行脚本，入口是 `jewelry_on_hand.cli:main`。没有配置任何 linter/formatter；pytest 是唯一的检查手段。

## 核心约定：两张内部图

这一条不变式驱动了整个 prompt 模板（`prompt_builder.py`）和 QC。用户只提供一张图，但生成时永远提交**两张**，且顺序固定（`generation.py::_submit_command`）：

- **内部图1 = 自动选出的参考图。** 只提供姿势、手腕角度、构图、背景、光线和镜面关系。图中任何首饰都必须被忽略/移除。
- **内部图2 = 用户产品图。** 产品身份的**唯一**来源（珠子、隔圈、颜色、透明度、纹理、排列）。其皮肤 / 手腕 / 手臂 / 背景**不得**被继承——这些来自内部图1。

改动 prompt 或 QC 时，务必保持这种拆分。模板还内置了 prompt 注入防御（`SAFETY_BOUNDARY_SENTENCE`）：来自分类表/分析结果的动态字段只当作描述数据，绝不当作指令执行。

## 流程与跨模块数据流

四个 CLI 子命令依次执行，中间由一道硬性人工 review gate 隔开。跨文件的数据流（仅看文件清单看不出来）：

1. **`prepare-review`** → 创建 `outputs/auto_reference_runs/<run-id>/`，复制产品图进去，加载并校验产品分析 JSON（`product_analysis.py`），生成 `product_fidelity_constraints.json`（`product_fidelity.py`），读取分类表（`reference_catalog.py`），对参考图打分并做多样性重排（`scoring.py`），**把 Top 3 复制进该 run 自己的 `review/` 目录**，再渲染 `review.html`（`review_package.py`）。它刻意**不**创建决策文件。
2. **`record-decision`** → 写入 `review/review_decision.json`（`review_decision.py`）。这就是 gate。
3. **`generate`** → `require_generation_decision` 强制校验 gate，**重新校验**产品仍为手串/手链，然后为每个选中 rank 拼装 prompt 并调用 AIReiter helper（`generation.py`）。它从 `analysis/selected_references.json` 读取参考图（即 **run 内部的 review 副本**），绝不读外部分类表路径——所以移动/删除分类表原图不会影响已 review 的 run。
4. **`qc`** → 写入 `generation/NN/qc.json`（`qc.py`），含逐项 `must_keep` 保真检查。

`models.py` 持有所有 frozen dataclass；校验逻辑在 `__post_init__` 和 `from_dict` 里，抛出中文报错的 `ValueError`。`ReferenceRow.from_dict` 同时接受英文键和分类表的中文表头（`序号`、`文件名`、`绝对路径`……）。

## 必须保持的不变式

- **没过 gate 就不准生成。** `review_decision.json` 必须存在，`action` 是生成类（`generate_rank_1` / `generate_selected` / `generate_multiple`）**且** `fidelity_confirmed: true`；`rerank` 和 `manual_reference` 在 V1 被拦截。品类会在 generate 阶段重新检查，所以手改 run JSON 也绕不过。
- **`product_fidelity_constraints.json` 永远会写出**，即使没有关键结构——此时 `must_keep: []`、`review_status: "not_applicable"`。状态还是 `pending` 时生成会被拒绝。
- **两个参考图文件含义不同：** `analysis/reference_candidates.json` = 全部候选，按质量分排序；`analysis/selected_references.json` = 多样性重排后的 Top 3，指向 run 内部副本。生成用后者。
- **打分分两层：** 逐级放宽的硬过滤（`scoring.py::_filter_reference_rows`），再做质量打分，再做多样性重排（单 run 内，以及可选的批次级重排——惩罚跨 SKU 复用同一文件/拍摄组/风格）。
- **`generate` 依赖外部 skill + 密钥：** `skills/aireiter-image-generation/scripts/aireiter_image_helper.py`，它需要 `skills/aireiter-image-generation/references/config.json`（API key）——该文件被 gitignore，所以没有它就无法生成。
- **以 Windows 为先：** `run_paths.py` 会按 Windows 保留名清洗 run ID；manual-workflow 里的示例是 PowerShell。

## 仓库约定（来自 AGENTS.md）

- 参考文档和流程中的 `.md` 文件放在 `./reference`。
- 临时 / 测试 run 产物放在 `./output`。注意这与代码默认输出根目录 `outputs/auto_reference_runs`（`cli.py::DEFAULT_OUTPUT_ROOT`）不同；`outputs/` 下还放了 `reference_classification/`（分类表的构建脚本，以及工作流读取的 `分类明细` xlsx）。
