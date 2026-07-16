# 参考底图替换工作流：任务 7D 模型契约前置固化

## 目标

把主工作区当前 `models.py` 的并发模型扩展安全固化，同时恢复并严格保留 Task 5 的 `ReviewDecision.reference_snapshot_sha256` 决策绑定契约。该提交先于产品保真 v2，使后续 `PendantSemantics` 与 `ProductFidelityConstraints.pendant_semantics` 在纯提交 tree 可用。

## 范围

- 修改并提交：`src/jewelry_on_hand/models.py`
- 修改并提交：`tests/test_models.py`
- 仅在直接验证需要时修改同一模型契约测试；必须在报告中说明。

不得修改或提交 product_fidelity、product_analysis、review_decision、generation、CLI、QC、飞书参考源或主图 Skill。

## 必须同时保留的契约

### Task 5 决策摘要

- `ReviewDecision` 必须保留非空、64 位小写十六进制 `reference_snapshot_sha256`。
- `to_dict()` / `from_dict()` round-trip 必须保留该字段；现代决策缺失、空值、类型错误或格式错误中文 fail-closed。
- 旧历史格式只能按既有只读兼容规则读取，不能由现代 writer 伪造；不得用默认空摘要绕过。
- 决策 action、selected ranks、output role、fidelity digest 等现有校验不得放宽。

### 并发模型扩展

- 保留当前 `PendantSemantics` 的不可变 schema、序列化、解析、枚举/数量/连接关系校验。
- 保留 `ProductFidelityConstraints.pendant_semantics` 及其 round-trip；非吊坠品类不得误带吊坠语义，吊坠项链的必要结构不得静默丢失。
- 保留当前其他用户模型字段和校验，不回退或整文件覆盖。
- 新旧字段的默认/兼容行为必须显式且确定性；禁止 Python 宽松 bool/int 相等绕过。

## TDD 与验证

1. 在最新主 HEAD 的 `output/` detached worktree 中，以 HEAD 模型为共同基线，把主工作区当前模型扩展三方合并，并恢复 Task 5 摘要字段。
2. 先写/运行 RED：当前脏模型删除 snapshot digest 的用例必须失败；再做最小 GREEN。
3. 必测：
   - `ReviewDecision` snapshot digest 有效 round-trip；缺失、空、非字符串、大写、非 hex、长度错误拒绝。
   - 现代 writer 不能创建无摘要决策；历史只读兼容不变。
   - `PendantSemantics` 完整 round-trip、无效数量/层/连接/朝向边界。
   - `ProductFidelityConstraints` 四品类 round-trip；pendant_necklace 语义保留，其他品类无污染。
4. 运行：

```powershell
python -m pytest tests/test_models.py tests/test_review_decision.py `
  tests/test_output_role_compatibility.py -v `
  --basetemp=output/t07d -o cache_dir=output/cache-t07d
```

5. 纯 tree 导入、`py_compile`、`git diff --check`。

所有测试显式设置隔离 `PYTHONPATH`；不得访问外部系统或生图。

## 安全集成

- 用户已持续授权同类 HEAD 前进和目标并发自动重基线；记录主目标 SHA，逐块保留两边语义。
- 只提交获准文件，detached 与主 index plumbing 均非 amend。
- 集成前后主索引为空、主工作区原字节不变，tested/detached/main tree 一致。
- 报告全文写入 `.superpowers/sdd/reference-replacement-task-7d-report.md`，只保留唯一当前状态。
