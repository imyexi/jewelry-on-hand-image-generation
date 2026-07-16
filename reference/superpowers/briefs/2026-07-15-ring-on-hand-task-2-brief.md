# 任务 2：CLI 端到端与便携契约同步

## 目标

同步测试，使其准确表达两类图片的边界：`product-detail.png` 继续保存并供 review、结构分析和 canonical 使用；helper 的第二张图与 generation 的 `product-identity.jpg` 必须来自 `input/product-on-hand.jpg`。

## 文件

- 修改 `tests/test_cli.py`
- 修改 `tests/test_skill_portability.py`

## 实施步骤

1. 在 `test_cli_end_to_end_ring_four_stage_workflow` 中保留以下 prepare-review 语义：

```python
assert constraints["source"]["product_image"] == "input/product-detail.png"
assert (run_root / "input" / "product-detail.png").read_bytes() == product_detail.read_bytes()
assert "product-detail.png" in (run_root / "review" / "review.html").read_text(encoding="utf-8")
```

把 generation 断言改为：

```python
assert (generation_dir / "product-identity.jpg").read_bytes() == product_image.read_bytes()
_assert_task9_submit_call(
    helper_log,
    run_root,
    selected_reference,
    generation_dir,
    expected_product=run_root / "input" / "product-on-hand.jpg",
)
```

运行：

```powershell
py -m pytest tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

任务 1 已完成，因此预期 `1 passed`。

2. 修改 `test_portable_workflow_keeps_product_identity_input_migration_boundary`，要求 `skills/jewelry-on-hand-workflow/SKILL.md` 和 `skills/jewelry-on-hand-workflow/references/workflow.md` 同时包含以下精确语义：

```python
required = (
    "产品上手图是生成阶段唯一产品身份图",
    "细节图只用于 review、结构分析和 QC",
    "不得作为第三张模型输入",
)
```

删除对“细节图存在时优先作为产品身份输入”的旧要求。

运行并确认预期 RED：

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

失败必须来自当前技能文档尚未包含新契约，而非测试错误。任务 3 将全文修订文档并使该测试转 GREEN。

## 约束

- 不修改生产代码和文档；本任务只迁移测试。
- 不删除或弱化细节图在 review/canonical 中的现有断言。
- 不改变四阶段流程的其他测试语义。
- 当前工作区很脏，目标文件已有其他未提交改动。不得回滚、覆盖或顺带修改；不得执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
