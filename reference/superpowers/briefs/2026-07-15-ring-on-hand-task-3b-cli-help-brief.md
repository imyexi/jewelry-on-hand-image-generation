# 任务 3b：修正戒指细节图 CLI 帮助契约

## 背景

任务 3 完成文档全文修订后，冲突搜索发现 `src/jewelry_on_hand/cli.py` 的 `--product-detail-image` 帮助文本仍写“作为审核和生成的产品身份图”，与已确认的产品上手身份源规则冲突。

## 目标

只修正用户可见帮助契约，不改变参数、prepare-review 数据流或任何生成行为。

## 文件

- 修改 `tests/test_cli.py`
- 修改 `src/jewelry_on_hand/cli.py`

## TDD

1. 在 CLI help 相关测试附近新增测试，调用：

```python
with pytest.raises(SystemExit) as exc_info:
    main(["prepare-review", "--help"])
```

断言退出码为 0，并断言帮助文本包含：

```text
仅用于 review、结构分析、canonical 约束和人工 QC
不进入模型
```

同时断言不包含：

```text
作为审核和生成的产品身份图
```

2. 运行新增测试并确认 RED，失败原因必须是旧帮助文本仍声明细节图用于生成。

3. 最小修改 `--product-detail-image` 的 help 为：

```text
戒指可选：已确认的产品主体细节图，仅用于 review、结构分析、canonical 约束和人工 QC，不进入模型。
```

4. 运行新增测试和 `test_cli_end_to_end_ring_four_stage_workflow`，都必须 GREEN。

5. 运行冲突搜索：

```powershell
rg -n "作为审核和生成的产品身份图" src tests
```

预期无命中。

## 约束

- 不修改实际参数行为、fidelity canonical 输入、generation 或文档。
- 目标文件已有其他未提交改动，只做最小局部变化；不得回滚、格式化或顺带修改。
- 不得执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
