# 商品主图数量与遮挡保真实施计划

> **执行要求：** 使用测试先行方式逐项实施；本次在当前会话内执行，不启用子代理。

**目标：** 让商品主图工作流冻结目标产品的精确重复部件数量，在参考图存在遮挡时仍保持实体总数，并重新生成 QY048。

**架构：** 在产品分析和保真约束中绑定 `component_counts`，由生成契约自动写入数量与遮挡 Prompt，再由 `component_count_checks` 定量判定结果。原参考选择和 AIReiter 回执绑定机制保持不变。

**技术栈：** Python 3.13、pytest、JSON 契约、AIReiter GPT Image 2。

## 全局约束

- 所有参考和流程 Markdown 位于 `reference/`。
- 所有测试运行与真实重跑产物位于 `output/`。
- 不覆盖原 QY048 真实测试产物。
- 不写回飞书，不提交 Git。

### 任务一：数量事实契约

**文件：**

- 修改：`tests/test_product_hero_workflow.py`
- 修改：`skills/jewelry-product-hero-workflow/scripts/product_hero_workflow.py`

- [ ] 先增加用例：手串缺少精确数量、数量来源含 reference、已确认珠数却声明珠数未知时失败。
- [ ] 运行定向用例，确认因功能缺失而失败。
- [ ] 实现 `component_counts` 规范化与手串门禁。
- [ ] 重跑定向用例，确认通过。

### 任务二：Prompt 与保真约束

**文件：**

- 修改：`tests/test_product_hero_generation_contract.py`
- 修改：`skills/jewelry-product-hero-workflow/scripts/generation_contract.py`

- [ ] 先增加用例：保真约束必须镜像数量事实，Prompt 必须包含精确数量、参考数量隔离和遮挡优先级。
- [ ] 运行定向用例，确认因功能缺失而失败。
- [ ] 实现约束校验和 Prompt 生成。
- [ ] 重跑定向用例，确认通过。

### 任务三：遮挡感知数量 QC

**文件：**

- 修改：`tests/test_product_hero_generation_contract.py`
- 修改：`skills/jewelry-product-hero-workflow/scripts/generation_contract.py`

- [ ] 先增加用例：可见数与遮挡数合计必须等于实体总数，遮挡必须有证据，数量失败必须进入 rerun。
- [ ] 运行定向用例，确认因功能缺失而失败。
- [ ] 实现固定检查项、失败码与 `component_count_checks` 校验。
- [ ] 重跑定向用例，确认通过。

### 任务四：Skill 与项目参考文档

**文件：**

- 修改：`skills/jewelry-product-hero-workflow/SKILL.md`
- 修改：`reference/product-hero-workflow.md`
- 修改：`tests/test_product_hero_skill_portability.py`

- [ ] 增加 Skill 文案契约测试。
- [ ] 修订全文中的输入、Prompt、QC 和失败处理说明，避免与旧规则矛盾。
- [ ] 运行可移植性测试和 Skill 校验。

### 任务五：QY048 真实重跑

**文件：**

- 创建：`output/skill-evals/product-hero/qy048-count-occlusion-20260715/`

- [ ] 从原冻结 run 复制产品输入和用户已选参考，创建独立重跑 run。
- [ ] 冻结 13 颗数量事实，生成并预检新 Prompt。
- [ ] 使用 AIReiter 提交、轮询、下载并记录回执。
- [ ] 逐颗视觉计数并写入结构化 QC；不满足数量则按 rerun 规则重试。
- [ ] 仅在数量、产品保真和场景检查全部通过后创建 final。

### 任务六：最终验证

- [ ] 运行定向测试。
- [ ] 运行全量 pytest。
- [ ] 运行 Skill `quick_validate.py`。
- [ ] 核对 Git diff 只包含本次相关改动，不处理其他已有改动。
