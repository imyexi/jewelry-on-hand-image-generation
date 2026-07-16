# Task 5 解阻：output_role 测试夹具协调

## 背景

产品保真 v2 Task 5 的文档与 portable 验证已经完成，但全量测试被并发 `output_role` 强制契约与旧测试夹具冲突阻断。生产契约要求 `prepare-review`、`record-decision` 与 `generate` 的角色声明一致；本任务只协调测试夹具，不削弱生产 gate。

## RED 基线

运行：

```powershell
uv run pytest tests/test_cli.py::test_record_decision_cli_writes_and_normalizes_generate_rank_1 tests/test_cli.py::test_cli_end_to_end_necklace_worn_with_fidelity_coverage tests/test_cli.py::test_cli_end_to_end_pendant_necklace_hand_held_and_critical_gate tests/test_feishu_enrichment_cli.py::test_prepare_review_no_longer_requires_classification_argument tests/test_final_necklace_important_fixes.py -q
```

当前稳定结果：`19 failed, 69 passed`。

## 允许修改

- `tests/test_cli.py`
- `tests/test_feishu_enrichment_cli.py`
- `tests/test_final_necklace_important_fixes.py`
- `reference/superpowers/briefs/2026-07-14-output-role-fixture-fix-report.md`

不得修改生产代码、SPEC、计划、证据文件或其他测试。不得暂存或提交。

## 实施要求

1. 先逐项读取 19 个失败并对照同文件中已经通过的 `output_role` 用例，列出每项缺少的数据：CLI `--output-role`、`analysis/output_role.json`、decision 中的角色，或与 display mode/runtime checklist 不一致的 fixture。
2. 保持 `output_role=hand_worn|lifestyle` 的强制语义，不修改 `src/jewelry_on_hand/output_roles.py`、CLI gate 或任何生产逻辑。
3. `prepare-review` 用例应显式传入合适角色；`record-decision` 用例应同时准备 run 角色文件并传入相同的 `--output-role`；`generate` 用例应保证 run、decision、命令与展示模式满足既有兼容规则。
4. `tests/test_final_necklace_important_fixes.py::_prepare_necklace_run()` 的公共 argv 可集中补充角色，但必须确认手持/佩戴模式均符合生产契约；直接调用 `prepare-review` / `record-decision` 的用例也要单独修正。
5. `tests/test_cli.py` 的三个失败不能只看首个错误：保持各测试原本验证的 record-decision、端到端项链和关键 QC gate 目的，并修正角色兼容及 runtime checklist fixture，使其命中原目标分支。
6. `tests/test_feishu_enrichment_cli.py` 只补充角色声明，不改变“prepare-review 不再需要 classification 参数”的测试目的。
7. 修改后先重跑 RED 命令，要求全部通过；再运行：

```powershell
uv run pytest tests/test_cli.py tests/test_feishu_enrichment_cli.py tests/test_final_necklace_important_fixes.py tests/test_output_role_compatibility.py tests/test_product_fidelity_v2.py -q
```

8. 自审时确认只改允许文件、没有弱化断言、没有调用 provider、没有覆盖戒指/HERO/v6/飞书实现。

## 报告

把完整报告写入 `reference/superpowers/briefs/2026-07-14-output-role-fixture-fix-report.md`，包含：

- 19 项根因映射；
- RED/GREEN 命令和结果；
- 修改文件；
- 自审结论与关注项。

