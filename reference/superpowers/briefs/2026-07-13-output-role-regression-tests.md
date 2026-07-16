# output_role 无角色路径回归测试 Brief

## 背景

历史 `run-20260713-double-necklace-03` 在并发改动的短暂不一致窗口中生成了非法行 `输出用途：未指定`，随后被闭集校验器正确拒绝。当前代码已经把 `output_role=None` 处理为空字符串，当前无角色 Prompt 能通过校验器，但独立审查指出缺少自动化回归保护。

审查文件：`.superpowers/sdd/task-11-double-necklace-review.md`。

## 目标

只增加最小自动化测试，锁定以下两个行为：

1. `build_prompt(..., output_role=None)` 不生成任何以 `输出用途：` 开头的行，并通过便携 Prompt 校验器。
2. CLI 无角色 run 在生成阶段构建的 Prompt 同样没有 `输出用途：` 行，并能通过便携 Prompt 校验器；不得调用真实 AIReiter。

## 约束

- 不修改生产代码、技能脚本、文档、SPEC、Plan 或 output 历史产物。
- 优先复用 `tests/test_prompt_builder.py` 与 `tests/test_cli.py` 的既有 helper，最小化新增代码；若必须新增测试文件，避免复制大段生产逻辑。
- 当前这两个测试是对已经落地行为的回归保护，不得为了制造 RED 而回退或临时破坏生产代码。需要在报告中明确“测试添加前行为已由独立取证确认通过，因此不存在合法的生产代码 RED 阶段”。
- CLI 测试必须 monkeypatch 真实生成边界，只捕获 `prompts_by_rank` 并运行便携 validator；不能提交网络任务、创建计费或伪造 result/QC。
- 无角色意味着省略 `analysis/output_role.json`，决策中的 `output_role` 也为 `None`；不得把 `worn` 当成 output role，也不得新增“未指定”或“佩戴展示图”白名单。
- 所有新增测试名称和断言使用清晰英文标识符，测试说明和报告使用中文。
- 已有工作树包含并发戒指改动；只对测试所需位置做最小补丁，不覆盖、不格式化、不暂存其他文件。

## 验证

至少运行并记录：

```powershell
python -m pytest tests/test_prompt_builder.py tests/test_cli.py -q
python -m pytest tests/test_skill_portability.py -q
```

如果新增独立测试文件，也要显式运行该文件。测试必须全部通过，输出无新的 warning/error。

## 报告与返回

把完整报告写入 `reference/superpowers/reports/2026-07-13-output-role-regression-tests-report.md`，包括：

- 修改文件和测试意图；
- 运行的精确命令、测试数量和结果；
- 未触发网络/AIReiter 的证明；
- `git diff --` 仅针对本任务文件的自审；
- 是否存在关注项。

不要提交或暂存。返回 `DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT` 或 `BLOCKED`，并给出修改文件、测试结果和关注项。
