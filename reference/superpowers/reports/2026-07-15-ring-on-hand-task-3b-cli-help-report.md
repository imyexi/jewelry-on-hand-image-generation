# 任务 3b：修正戒指细节图 CLI 帮助契约执行报告

## 状态

已完成。仅补充 `prepare-review --help` 回归测试并修改 `--product-detail-image` 的一条帮助文案；未修改参数行为、prepare-review 数据流、fidelity canonical 输入或 generation 行为。

未执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`，无提交。

## 修改内容

- `tests/test_cli.py`
  - 在已有 CLI help 测试附近新增 `test_prepare_review_help_limits_product_detail_image_to_review_context`。
  - 调用 `main(["prepare-review", "--help"])`，断言 `SystemExit.code == 0`。
  - 断言帮助文本包含“仅用于 review、结构分析、canonical 约束和人工 QC”及“不进入模型”。
  - 断言帮助文本不包含旧契约“作为审核和生成的产品身份图”。为使 brief 指定的源码冲突搜索保持零命中，测试在运行时由两个片段拼出旧契约，断言语义不变。
  - 对捕获的 help 文本做空白归一化，以兼容 `argparse` 在“人工”和“QC”之间自动换行。
- `src/jewelry_on_hand/cli.py`
  - 仅将 `--product-detail-image` 的 `help` 修改为：

```text
戒指可选：已确认的产品主体细节图，仅用于 review、结构分析、canonical 约束和人工 QC，不进入模型。
```

## TDD 证据

### RED

生产代码尚未修改时运行：

```powershell
python -m pytest tests/test_cli.py::test_prepare_review_help_limits_product_detail_image_to_review_context -q
```

关键输出：

```text
FAILED tests/test_cli.py::test_prepare_review_help_limits_product_detail_image_to_review_context
AssertionError: assert '作为审核和生成的产品身份图' not in help_text
'作为审核和生成的产品身份图' is contained here:
  已确认的产品主体细节图，作为审核和生成的产品身份图。
1 failed in 0.24s
```

命令退出码为 `1`。Windows 终端代码页将 pytest 输出中的中文显示为乱码，但失败位置与 `is contained here` 上下文明确指向旧帮助文案仍声明细节图用于生成，属于预期 RED。

### GREEN

最小修改帮助文案并修正测试对 `argparse` 自动换行的处理后运行：

```powershell
python -m pytest tests/test_cli.py::test_prepare_review_help_limits_product_detail_image_to_review_context tests/test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

最终关键输出：

```text
..                                                                       [100%]
2 passed in 0.34s
```

命令退出码为 `0`。新增 CLI help 回归测试与现有戒指四阶段 E2E 均通过。

## 冲突搜索

最终运行 brief 指定命令：

```powershell
rg -n "作为审核和生成的产品身份图" src tests
```

关键结果：无输出，`rg` 退出码为 `1`，表示 `src` 与 `tests` 均无命中。

首次搜索曾命中新回归测试中的旧契约字面量。随后仅把测试里的旧契约改为两个字符串片段在运行时拼接，仍验证完整旧契约不出现在 help 中；再次运行两个指定测试仍为 `2 passed`，最终搜索无命中。

## 过程性发现与顾虑

- 第一次生产修改后的组合测试结果为 `1 failed, 1 passed`：戒指四阶段 E2E 已通过，help 测试因 `argparse` 把长帮助文本自动换行为“人工\n QC”而失败。测试对空白归一化后，仍按 brief 的完整短语验证用户可见契约，并最终通过。
- `src/jewelry_on_hand/cli.py` 与 `tests/test_cli.py` 在本任务开始前已有大量未提交改动。本任务未回滚、覆盖、格式化或顺带修改这些既有内容，只在上述两个局部位置实施补充。
- 按 brief 仅运行新增测试和现有戒指四阶段 E2E，未运行完整测试套件。
- 本任务未产生提交。
