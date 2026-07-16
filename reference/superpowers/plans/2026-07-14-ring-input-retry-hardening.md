# 戒指分析证据边界与失败驱动重试实施计划

> **供 agentic worker 使用：** 使用 `superpowers:executing-plans` 原地实施，严格测试先行，不触碰并发的产品主图工作流文件。

**目标：** 支持经过确认的戒指细节分析图，明确区分分析/QC 证据与送模产品身份图，阻止已标记的低质参考图，并让重试根据 QC 失败码切换 Rank 和纠偏 Prompt。

**架构：** CLI 在 `prepare-review` 阶段接收可选细节图，仅供 review、结构分析、canonical 约束和人工 QC 对照；`generation` 固定以 `input/product-on-hand.jpg` 作为内部图 2，且只将该图传给 AIReiter，并保存内容一致的 `product-identity.jpg` 审计副本。戒指策略增加元数据质量门槛；generation history 记录实际 Rank 和最新失败码，构建下一次 Rank 与纠偏段。

**两阶段事实：** 2026-07-14 最初引入可选细节图时，曾把它的范围错误扩展到 generation 产品身份输入；这是已经废止的历史旧行为。2026-07-15 起，现行规则修正为细节图不进入模型，产品上手图是生成阶段唯一产品身份图。

**技术栈：** Python 3.11+、pytest、现有 JSON/文件哈希和 AIReiter helper；不新增图像处理依赖。

## 全局约束

- 所有文档和输出使用中文；测试产物放 `output/`。
- 保留当前脏工作区和并发产品主图工作流改动。
- 不静默裁切或截断产品图和 Prompt。
- 历史 run 无细节图、无 Rank 审计文件时保持兼容；历史 run 即使保留细节图，也不得沿用已废止的送模行为。

### 任务 1：细节分析证据与生成身份边界

- [x] 先新增 RunPaths、CLI 和 generation 失败测试。
- [x] 实现 `--product-detail-image` 复制与格式校验。
- [x] 2026-07-14 历史阶段：戒指 review/canonical 使用细节图；当时 generation 也选择细节图的做法现已废止。
- [x] 2026-07-15 修正阶段：细节图仅供 review、结构分析、canonical 约束和人工 QC 对照，不传给 AIReiter，也不作为第三张模型输入。
- [x] 2026-07-15 修正阶段：戒指 generation 的内部图 2 固定为 `input/product-on-hand.jpg`，并保存内容一致的 `product-identity.jpg` 审计副本。
- [x] 非戒指传入细节图时明确拒绝。

### 任务 2：参考图质量门槛

- [x] 先新增水印、logo、宽场景和有效手部近景测试。
- [x] 在戒指策略中实现未否定风险词和取景范围检查。
- [x] 运行品类策略和评分测试。

### 任务 3：失败驱动 Rank 与纠偏 Prompt

- [x] 先新增 Rank 1/2/3 顺序、第三次模型切换和 Top 3 耗尽测试。
- [x] 新增各戒指失败码纠偏测试。
- [x] 记录 `reference-rank.txt`、`retry-failures.json` 和内容与产品上手图一致的 `product-identity.jpg`。
- [x] CLI 为戒指构建 Top 3 Prompt，generation 选择实际 Rank 并注入纠偏。

### 任务 4：文档与验证

- [x] 全文修订操作文档和技能工作流相关章节，清除现行细节图送模要求并保留分析/QC 用途。
- [x] 运行戒指定向测试、真实 run dry-run 和完整测试集。
- [x] 输出验证报告并区分并发/既有无关失败。
