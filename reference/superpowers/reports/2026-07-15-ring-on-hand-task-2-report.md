# 任务 2 报告：CLI 端到端与便携契约同步

## 状态

- 已完成 CLI generation 断言迁移：`generation/01/product-identity.jpg` 必须与原始产品上手图一致，helper 的第二张产品图必须为 `input/product-on-hand.jpg`。
- 已保留 `product-detail.png` 在 fidelity source、run 输入目录与 review HTML 中的既有断言，未弱化其 review、结构分析和 canonical 边界。
- 已完成便携技能精确文本契约迁移：`SKILL.md` 与 `references/workflow.md` 均被要求包含三条新语义。
- 已保留便携 workflow 中“禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。”这一独立安全契约。
- 除本报告外，未修改生产代码、技能文档或其他文档；未执行 Git 暂存、提交、stash、checkout 或 reset。

## 测试命令与关键输出

### CLI 四阶段端到端

```powershell
py -m pytest tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

关键输出：

```text
.                                                                        [100%]
1 passed in 0.28s
```

结论：符合任务 1 已完成后的预期 GREEN。

### 便携技能产品身份输入边界

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

关键输出：

```text
F                                                                        [100%]
assert phrase in text
1 failed in 0.17s
```

结论：符合预期 RED。测试已被 pytest 正常收集和执行，首个失败是当前 `skills/jewelry-on-hand-workflow/SKILL.md` 尚未包含精确文本“产品上手图是生成阶段唯一产品身份图”，不是测试语法、导入或路径错误。当前 `SKILL.md` 仍写明细节图存在时优先作为产品身份输入，`references/workflow.md` 仍把细节图定义为 review、canonical 和生成的产品身份输入；任务 3 需全文修订这两份文档后再转 GREEN。

## 文件变化

- `tests/test_cli.py`：将 generation 身份文件断言从 `product-identity.png == product-detail.png` 迁移为 `product-identity.jpg == product_image`；将 helper 产品输入期望从 `input/product-detail.png` 迁移为 `input/product-on-hand.jpg`。
- `tests/test_skill_portability.py`：要求技能入口和便携 workflow 同时包含“产品上手图是生成阶段唯一产品身份图”“细节图只用于 review、结构分析和 QC”“不得作为第三张模型输入”，并继续精确校验便携 workflow 不得迁移内部图 2 中的人物与场景内容。
- `reference/superpowers/reports/2026-07-15-ring-on-hand-task-2-report.md`：新增本任务执行与验证报告。

## 顾虑

- 便携技能契约测试有意保持 RED，因此在任务 3 修订技能文档前，包含该用例的完整测试套件不会全绿。
- 工作区和两个测试文件在本任务开始前已有大量未提交改动；本任务仅实施上述最小行级迁移，没有回滚、覆盖或顺带整理既有改动。
- 本任务无提交。

## 审查修复记录

审查指出，原用例中的“禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。”是独立安全契约，不属于需删除的旧“细节图优先作为产品身份输入”规则。已在保留两份文档三条新语义循环的同时，针对 `PORTABLE_WORKFLOW` 恢复该精确断言。

修复后重新运行：

```powershell
py -m pytest tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

```text
.                                                                        [100%]
1 passed in 0.19s
```

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

```text
F                                                                        [100%]
assert '产品上手图是生成阶段唯一产品身份图' in text
1 failed in 0.21s
```

复核结论：CLI 仍为 GREEN；便携测试仍在新契约循环中因当前 `SKILL.md` 缺少首条精确语义而 RED，失败未到达已恢复的安全断言，因此预期 RED 原因未发生偏移。
