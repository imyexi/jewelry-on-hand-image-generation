# 吊坠语义基线失败修复 brief

## 目标

清零 Task 12 定向测试中的唯一真实失败：

`tests/test_skill_portability.py::test_automatic_fidelity_extraction_does_not_fabricate_ring_or_layer_constraints`

当前调用链在 `build_product_fidelity_constraints()` 中为 `pendant_necklace` 构造 `PendantSemantics(presence="present")`，但输入 analysis 缺少 `pendant_position`、`pendant_orientation` 与 `connection_structure`，因此严格模型以 `pendant_semantics.position 必须是非空字符串` 拒绝。

## 绑定契约

- 新项链 canonical 使用 `schema_version=2`；有主吊坠时，`pendant_semantics.position`、`orientation`、`connection` 必须是有证据的非空字符串。
- 不得从 `visible_appearance` 自由文本自动提升或编造结构化位置、朝向、连接和层级约束。
- 结构不完整或未人工确认时必须停止，不得用通用占位文本绕过严格 canonical。
- 历史 v1 只读；不得为了测试通过放宽 `PendantSemantics` 或现代 generation gate。
- 所有错误文案、测试名、注释与报告使用中文。
- 主工作区高度脏；只允许在独立 worktree 修改本 brief 明确列出的文件。

## 调试与 TDD 要求

1. 使用 `superpowers:systematic-debugging` 完成根因、数据流和相邻工作示例对比；先在干净基线稳定复现。
2. 判断失败是生产缺陷还是旧测试与严格 v2 契约冲突。不得预设必须修改生产代码。
3. 若严格契约要求拒绝不完整 analysis，更新/拆分测试以明确断言拒绝，并保留一个完整结构化 analysis 的正例，证明 builder 不会从自由文本提升“连接环/第二层”等未确认细节。
4. 若证据证明生产代码应支持该输入，先写能精确表达非编造边界的失败测试，再做最小生产修复；不得使用“待确认”“肉眼可见位置”等占位语义绕过非空校验。
5. 运行聚焦 RED/GREEN、`tests/test_product_fidelity_v2.py`、`tests/test_skill_portability.py` 以及与修改路径直接相关的回归。

## 允许路径

- `tests/test_skill_portability.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_prompt_builder.py`（端到端 Prompt 冲突回归）
- `src/jewelry_on_hand/product_fidelity.py`（仅当根因证明确需生产修复）
- `src/jewelry_on_hand/models.py`（仅当根因证明确需生产修复）
- `src/jewelry_on_hand/prompt_builder.py`（仅用于隔离未确认自由文本与现代生成 Prompt）
- `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`（保持便携校验器与现代 Prompt 投影同态）

提交前核对暂存仅包含必要允许路径，创建非 amend 提交。完整报告写入 `.superpowers/sdd/pendant-semantics-baseline-fix-report.md`，不提交报告。
