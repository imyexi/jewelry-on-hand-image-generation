# 参考底图替换工作流：任务 7D 决策读取与 writer corrective

## 目标

关闭 Task 7D 独立终审剩余的唯一 Important：历史只读解析可以宽松，但任何进入 generation gate 的决策必须具有严格的 `reference_snapshot_sha256`；实际 writer 必须复用模型唯一序列化边界。产品分析、保真与模型前置均已提交。

## 范围

- 修改并提交：`src/jewelry_on_hand/review_decision.py`
- 修改并提交：`tests/test_review_decision.py`

不得修改 models、product_analysis、product_fidelity、generation、CLI、QC 或其他文件。

## 契约

- `ReviewDecision.from_dict()` 默认宽松只供历史审计读取；不得把默认宽松解释为可生成。
- `require_generation_decision()` 必须始终以 `require_reference_snapshot_sha256=True` 解析，并拒绝任何缺失、空、类型/格式错误 digest 的 generation action。
- legacy 历史决策可由专用只读入口读取，但进入 generation gate 必须失败并提示重新 `prepare-review` / 确认快照。
- `generate_selected`、`generate_multiple` 等所有生成 action 使用同一严格路径；非生成 action 不得被误拒。
- 实际 writer 必须复用 `ReviewDecision.to_dict()` 或同一个唯一严格 helper，禁止私有 `_decision_to_dict` 与模型序列化规则漂移。
- `write_review_bundle` 注入正确 digest 后正常落盘；旧 writer 仍不得创建 generation 决策。
- 继续校验 action、selected ranks、output role、fidelity digest、snapshot digest 与四文件事务绑定；不得放宽现有 gate。

## TDD 与验证

- 先在当前主用户版本上复现 RED：无 digest generation 决策被 `require_generation_decision()` 接受；writer 私有路径绕过模型序列化。
- GREEN 覆盖缺失/空/非字符串/大写/non-hex/长度错误、所有 generation action、非生成 action、legacy read-only、现代 bundle round-trip、旧 writer 拒绝。
- 运行：

```powershell
python -m pytest tests/test_review_decision.py tests/test_models.py -v `
  --basetemp=output/t07d-decision -o cache_dir=output/cache-t07d-decision
```

- 纯 tree 导入、`py_compile`、`git diff --check`；不跑全量。

## 安全

- 从最新主 HEAD 创建全新 detached worktree；主两文件先保存 `output/` 只读快照与 SHA，主树禁止 restore/checkout/写入。
- 用户已持续授权同类并发自动重基线；三方保留并重测。
- 仅两文件 detached 非 amend + 主 index plumbing；集成前后工作字节 SHA 不变、索引空、tested/detached/main tree 一致。
- 全文修订 `.superpowers/sdd/reference-replacement-task-7d-report.md`，记录模型侧已完成和本决策侧最终状态。
