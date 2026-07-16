# Task 5：output_role 测试夹具解阻报告

## 状态

`DONE_WITH_CONCERNS`

指定 RED 集和扩展回归均已通过；未修改生产代码、SPEC、计划或证据文件。非阻断关注项是：飞书用例补入角色后，暴露出两个 mock 仍使用旧函数签名，必须同时接受生产端已有的 `product_image` / `output_role` 关键字参数，才能保持该用例原有测试目的并完成回归。

## 单一根因结论

生产端已经把 `output_role` 纳入 `prepare-review -> analysis/output_role.json -> record-decision -> review_decision.json -> generate` 的强制状态链，并把角色与参考图用途、深色背景信号及项链展示模式一起校验。旧测试夹具只准备了部分链路数据，或仍使用 `hand_worn + worn`、角色与参考图用途标记不一致、旧版 runtime checklist 上下文等组合，导致新增前置 gate 抢先失败，无法命中各测试原本要验证的分支。

修复只协调测试数据：

- `hand_held` 项链使用 `hand_worn`，参考图用途包含“手部佩戴图；深色背景”。
- `worn` 项链使用 `lifestyle`，参考图用途包含“生活场景图；深色背景”。
- `record-decision` 同时具备 run 角色文件和相同的命令角色，decision 由生产代码写入相同角色。
- v2 项链 runtime checklist 同时传入最终 analysis 与 fidelity constraints，覆盖吊坠语义问题。

## 19 项根因映射

1. `test_record_decision_cli_writes_and_normalizes_generate_rank_1`：已有 `analysis/output_role.json=hand_worn`，但命令缺少 `--output-role hand_worn`；生产 gate 在写 decision 前拒绝。
2. `test_cli_end_to_end_necklace_worn_with_fidelity_coverage`：run、decision、命令原先一致为 `hand_worn`，但最终展示模式是 `worn`；生成阶段明确要求项链 `hand_worn` 必须为 `hand_held`。改为 `lifestyle`，并把该 worn 参考图用途标为“生活场景图；深色背景”。
3. `test_cli_end_to_end_pendant_necklace_hand_held_and_critical_gate`：角色链本身已是合法的 `hand_worn + hand_held`；失败来自 `_task9_runtime_checklist()` 仍按旧调用构建 checklist，未传 v2 analysis/canonical，缺少吊坠语义检查项，无法完整覆盖 runtime checklist。
4. `test_prepare_review_no_longer_requires_classification_argument`：命令缺少显式角色；补入 `--output-role hand_worn` 后，又暴露两个 mock 未接受生产函数已有的 `product_image` / `output_role` 关键字参数。仅扩宽 mock 签名，返回值和“不需要 classification”的断言不变。
5. `test_prepare_review_rejects_null_necklace_length_before_top_three`：`prepare-review` 缺少 `--output-role`，角色 gate 抢在 `length_category` 校验前失败；补入 `lifestyle` 后恢复原目标分支。
6. `test_record_decision_rejects_null_necklace_length`：手工 run 同时缺少 `analysis/output_role.json` 和命令 `--output-role`；在 `_write_null_length_run()` 写入 `lifestyle`，命令传相同角色后恢复空长度校验。
7. `test_unknown_can_be_corrected_before_scoring_through_formal_cli_e2e`：`prepare-review` 和 `record-decision` 均缺少角色，且 worn 参考图缺少与 `lifestyle` 对应的用途/深色信号；补齐 run 全链路为 `lifestyle` 后恢复“评分前纠正 unknown”的端到端目标。
8. `test_prepare_review_still_rejects_final_unknown_before_top_three`：`prepare-review` 缺少角色，角色 gate 抢先；补入 `lifestyle` 后恢复最终 unknown 拒绝分支。
9. `test_record_decision_rejects_late_reference_affecting_corrections[worn-record_overrides0]`：公共 helper 未声明角色；worn 初始 run 应为 `lifestyle`，参考图应为生活场景用途，record 命令必须读取并传同一角色，才能命中“晚改为 hand_held 必须重跑 prepare-review”。
10. `test_record_decision_rejects_late_reference_affecting_corrections[hand_held-record_overrides1]`：公共 helper 未声明角色；hand-held 初始 run 应为 `hand_worn`，参考图应为手部佩戴用途，record 命令必须传同一角色，才能命中“晚改为 worn 必须重跑”。
11. `test_record_decision_rejects_late_reference_affecting_corrections[worn-record_overrides2]`：公共 helper 与 record 命令缺少一致的 `lifestyle`，角色 gate 阻断“晚改 length_category”分支。
12. `test_record_decision_rejects_late_reference_affecting_corrections[worn-record_overrides3]`：公共 helper 与 record 命令缺少一致的 `lifestyle`，角色 gate 阻断“晚改 layer_count”分支。
13. `test_prepare_review_applies_corrections_before_rescoring_references[worn-prepare_overrides0-hand-held-display_mode-hand_held]`：公共 helper 未按纠正后的最终 `hand_held` 选择 `hand_worn`，且候选参考图缺少角色用途/深色信号；按最终展示模式计算角色后恢复重评分目标。
14. `test_prepare_review_applies_corrections_before_rescoring_references[hand_held-prepare_overrides1-worn-close-display_mode-worn]`：公共 helper 未按纠正后的最终 `worn` 选择 `lifestyle`，且候选参考图缺少相应用途/深色信号。
15. `test_prepare_review_applies_corrections_before_rescoring_references[worn-prepare_overrides2-worn-long-length_category-long]`：worn run 缺少 `lifestyle` 角色及生活场景参考图标记，导致无法命中长项链重评分分支。
16. `test_prepare_review_applies_corrections_before_rescoring_references[worn-prepare_overrides3-worn-multi-layer_count-2]`：worn run 缺少 `lifestyle` 角色及生活场景参考图标记，导致无法命中多层重评分分支。
17. `test_generate_revalidates_necklace_reference_path_digest_and_policy[external_path-review_dir]`：生成前置 helper 未建立 `lifestyle` run 角色、同角色 decision 及相应用途参考图，尚未进入外部路径篡改校验。
18. `test_generate_revalidates_necklace_reference_path_digest_and_policy[review_bytes-SHA-256]`：同上，角色链不完整阻断 review copy SHA-256 篡改校验。
19. `test_generate_revalidates_necklace_reference_path_digest_and_policy[policy_metadata-展示模式]`：同上，角色链不完整阻断参考图展示模式元数据篡改校验。

## RED / GREEN 证据

### RED 基线

命令：

```powershell
uv run pytest tests/test_cli.py::test_record_decision_cli_writes_and_normalizes_generate_rank_1 tests/test_cli.py::test_cli_end_to_end_necklace_worn_with_fidelity_coverage tests/test_cli.py::test_cli_end_to_end_pendant_necklace_hand_held_and_critical_gate tests/test_feishu_enrichment_cli.py::test_prepare_review_no_longer_requires_classification_argument tests/test_final_necklace_important_fixes.py -q
```

结果：退出码 `1`，`19 failed, 69 passed in 0.85s`。

### 调试循环

- 第一轮：`14 failed, 74 passed in 0.73s`。证实 `lifestyle` 不能只改命令角色，参考图还必须含“生活场景图”用途和深色背景信号；飞书 mock 还存在隐藏签名问题。
- 第二轮：`1 failed, 87 passed in 0.66s`。剩余失败仅为飞书 `select_top_references` mock 不接受 `output_role` 关键字。

### GREEN：原 RED 命令

最终新鲜验证结果：退出码 `0`，`88 passed in 0.55s`。

### GREEN：指定扩展回归

命令：

```powershell
uv run pytest tests/test_cli.py tests/test_feishu_enrichment_cli.py tests/test_final_necklace_important_fixes.py tests/test_output_role_compatibility.py tests/test_product_fidelity_v2.py -q
```

最终新鲜验证结果：退出码 `0`，`237 passed in 1.55s`。

## 修改文件

- `tests/test_cli.py`
  - 为独立 `record-decision` 用例补充命令角色。
  - 将 worn 项链端到端用例的 run/decision 角色改为兼容的 `lifestyle`。
  - 按 `hand_held` / `worn` 为 Task 9 参考图夹具设置对应角色用途和深色背景信号。
  - 让 v2 runtime checklist 使用最终 analysis 与 fidelity constraints。
- `tests/test_feishu_enrichment_cli.py`
  - 为 `prepare-review` 补入 `hand_worn`。
  - 仅扩宽两个 mock 的关键字参数兼容性，未改变返回值、调用次数或 classification 断言。
- `tests/test_final_necklace_important_fixes.py`
  - 为直接 `prepare-review` / `record-decision` 用例补齐 run 文件和命令角色。
  - 公共项链 helper 按纠正后的最终展示模式选择角色，并为参考图设置匹配的用途/深色信号。
  - `record-decision` 从 run 角色文件读取并传回相同角色。
- `reference/superpowers/briefs/2026-07-14-output-role-fixture-fix-report.md`
  - 本报告。

## 自审

- 生产契约未削弱：没有修改 `src/jewelry_on_hand/output_roles.py`、CLI gate、scoring、prompt、QC 或其他生产逻辑。
- 断言未弱化：未删除、放宽或替换任何原断言；原 record-decision、端到端项链、关键 QC、评分前纠正和篡改校验目标均继续执行。
- 范围符合：本任务只通过编辑工具修改三个允许的测试文件和本报告；共享工作区中其余大量脏改动均为任务开始前既有状态，未清理、回退、暂存或提交。
- 未调用 provider：仅运行本地 pytest、Python 语法检查、文本/状态检查；生成端到端测试使用测试内本地 helper 或 monkeypatch。
- 未覆盖并发实现：没有编辑戒指、HERO、v6、飞书实现、SPEC、计划或证据文件。
- 并发核验：开始时三个目标测试文件 SHA-256 分别为 `2D350EFC...`、`DBE2E0EB...`、`44EB1B80...`；调查期间未观察到非本任务造成的目标文件变化。修改后哈希分别为 `ACAC721F...`、`8C8EC0A4...`、`2C6DD774...`。
- 格式检查：`git diff --check -- tests/test_cli.py tests/test_feishu_enrichment_cli.py tests/test_final_necklace_important_fixes.py` 未报告空白错误，仅提示共享工作区中 `tests/test_cli.py` 的既有 LF/CRLF 转换警告。

## 关注项

- `tests/test_feishu_enrichment_cli.py` 原需求表述为“只补充角色声明”。角色 gate 解锁后，当前生产调用会向两个 mock 传入既有关键字参数；若不扩宽 mock 签名，指定 GREEN 不可能通过。当前处理只修正夹具接口兼容性，不改变测试目的或行为断言。
- 共享工作区高度脏且持续承载并发任务；本报告的通过结果对应上述测试文件哈希与当次生产工作树状态，合并其他并发改动后应复跑同两条命令。
