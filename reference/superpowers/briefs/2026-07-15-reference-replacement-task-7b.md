# 参考底图替换工作流：任务 7B 产品保真摘要前置固化

## 目标

把主工作区当前 `product_fidelity.py` 中 Task 7 所需的 canonical 校验与 `product_analysis_sha256` 契约固化为独立、纯提交 tree 可用的前置提交，同时保留用户已有的产品保真 v2 扩展。该任务只稳定产品分析到保真约束的确定性绑定，不修改 generation、CLI、QC 或模型决策语义。

## 预期范围

- 修改并提交：`src/jewelry_on_hand/product_fidelity.py`
- 新建并提交：`tests/test_product_fidelity_v2.py`
- 仅当纯 tree 证明直接必要，才可增加产品保真现有直接测试文件；必须在报告中逐项说明。

不得提交 `generation.py`、`cli.py`、`qc.py`、`models.py`、飞书参考源或主图 Skill 文件。若当前产品保真实现依赖尚未提交的 `product_analysis.py` 或其他模块，先返回最小依赖清单；不要用主脏树镜像替代纯 tree 验证，也不要擅自扩大提交。

## 必须提供的契约

- `product_analysis_sha256(product)` 对规范化 `ProductAnalysis.to_dict()` 的 UTF-8、`ensure_ascii=False`、`sort_keys=True`、紧凑 JSON 计算稳定 SHA-256；等价输入稳定，不同业务字段变化必须改变摘要。
- `build_product_fidelity_constraints()` 写入 `source.product_analysis_sha256`，绑定最终规范化产品分析。
- `validate_product_fidelity_constraints(product, constraints)` 必须校验：状态、品类、摘要、`must_keep`、`must_not_change` 和各品类结构字段；摘要缺失、不匹配、类型错误或 canonical 被篡改均中文 fail-closed。
- 兼容 Task 6 四品类 Prompt 所需的数据投影；不得把 `composition`、`style_mood`、人物、背景或构图字段重新作为生成指令。
- v2 扩展不得删除或放宽 Task 5 的确认链约束。
- 序列化、错误顺序和输出必须确定性；布尔、整数、浮点的类型边界不得依赖 Python 宽松相等。

## TDD 与验证

1. 在最新主 HEAD 的 `output/` detached worktree 中重建当前用户文件，先记录主工作区 SHA。
2. 使用现有 `tests/test_product_fidelity_v2.py` 建立 RED/GREEN；不得删除用户断言换取通过。
3. 必测：摘要稳定性、任一业务字段变化、`source` 缺失/篡改、canonical 类型严格性、四品类约束验证、pending/corrected/not_applicable 状态边界。
4. 至少运行：

```powershell
python -m pytest tests/test_product_fidelity_v2.py tests/test_product_analysis.py `
  tests/test_review_decision.py tests/test_prompt_builder.py -v `
  --basetemp=output/t07b -o cache_dir=output/cache-t07b
```

5. 若纯 tree 收集失败，区分本任务缺口与未提交依赖，不得用主运行态覆盖结论。
6. 运行纯 tree 导入、`py_compile`、`git diff --check`。

所有测试显式设置隔离 worktree `PYTHONPATH=<worktree>/src`。不得调用外部接口、生图或飞书。

## 安全集成

- 用户已持续授权同类 docs-only HEAD 前进和目标文件并发自动重基线；保留所有用户改动，三方合并后重测。
- detached 提交与主 index plumbing 提交只含获准文件；非 amend。
- 集成前后主索引为空、主工作区原字节 SHA 不变，tested/detached/main tree 一致。
- 报告全文写入 `.superpowers/sdd/reference-replacement-task-7b-report.md`，只保留唯一当前状态。
