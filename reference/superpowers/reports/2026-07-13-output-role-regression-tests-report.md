# output_role 无角色路径回归测试报告

## 结论

状态：`DONE_WITH_CONCERNS`

本任务只补充自动化回归测试与本报告，没有修改生产代码、技能脚本、SPEC、Plan、既有测试文件或历史 `output` 产物。新增测试锁定以下既有行为：

1. `build_prompt(..., output_role=None)` 不生成任何以 `输出用途：` 开头的行，并通过便携 Prompt 校验器。
2. CLI 对省略 `analysis/output_role.json`、且决策解析后 `output_role is None` 的 `worn` 双层普通项链 run，只构建无用途行的 Prompt；该 Prompt 通过同一便携校验器，测试不会进入真实 AIReiter 生成边界。

本任务新增测试与技能便携性测试均通过；brief 指定的既有 Prompt/CLI 组合最近一次已执行结果为 `107 passed, 1 failed`。失败来自测试期间落地的外部并发 `scoring.py` 改动，本任务按隔离约束不修改或回退该文件。

## 修改文件与测试意图

- `tests/test_output_role_compatibility.py`
  - `test_build_prompt_without_output_role_omits_role_line_and_passes_validator`：直接调用真实 `build_prompt`，断言不存在 `输出用途：` 行，并调用 `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py` 中的真实 `validate_prompt` 验证结果为空错误列表。
  - `test_cli_generate_without_output_role_validates_prompt_without_provider_call`：构建显式 `display_mode=worn` 的双层普通项链 run，不创建 `analysis/output_role.json`，决策数据不写角色字段并解析为 `None`；monkeypatch `jewelry_on_hand.cli.run_generation` 后仅捕获 `prompts_by_rank`，逐项检查用途行与便携校验结果。
- `reference/superpowers/reports/2026-07-13-output-role-regression-tests-report.md`
  - 记录测试意图、命令、结果、网络隔离证据和任务专属 diff 自审。

没有触碰并发修改中的 `tests/test_prompt_builder.py`、`tests/test_cli.py` 或戒指相关文件。

## TDD 说明

测试添加前行为已由独立取证确认通过，因此不存在合法的生产代码 RED 阶段。本任务是对已落地行为补回归保护；依照 brief 约束，没有为了制造 RED 而回退、临时破坏或修改生产代码。

新增测试第一次执行时，pytest 因指定的 `--basetemp` 父目录尚不存在而在 fixture 初始化阶段报告 `2 errors`，未执行行为断言。创建 `output/pytest-output-role-regression` 后，同一新增测试立即得到 `2 passed`。该错误属于测试环境目录初始化问题，不是功能 RED，也没有触发生产代码修改。

## 验证命令与结果

所有测试临时产物均定向到 `output/pytest-output-role-regression`。

### 新增回归测试

```powershell
python -m pytest tests/test_output_role_compatibility.py -q --basetemp=output/pytest-output-role-regression/new-file-final -o cache_dir=output/pytest-output-role-regression/cache-new-file
```

结果：`2 passed in 0.12s`，退出码 0，无 warning/error。

### 既有 Prompt 与 CLI 测试

```powershell
python -m pytest tests/test_prompt_builder.py tests/test_cli.py -q --basetemp=output/pytest-output-role-regression/prompt-cli -o cache_dir=output/pytest-output-role-regression/cache-prompt-cli
```

最近一次已执行结果：`1 failed, 107 passed in 1.04s`，退出码 1。唯一失败为既有 `tests/test_cli.py::test_prepare_review_cli_persists_requested_output_role`。并发工作树于其后继续更新；按主线程最新隔离指令不再复跑，以免把外部并发范围混入本任务。

### 技能便携性测试

```powershell
python -m pytest tests/test_skill_portability.py -q --basetemp=output/pytest-output-role-regression/skill-portability -o cache_dir=output/pytest-output-role-regression/cache-skill-portability
```

结果：`86 passed in 0.52s`，退出码 0，无 warning/error。

最近一轮三个验证命令共执行 196 项测试：195 项通过，1 项既有 CLI 测试失败。

### 并发失败时间线与根因取证

1. 新增测试完成后，目标组合第一次运行得到 `108 passed in 0.82s`；最终自审前第二次运行得到 `108 passed in 0.97s`。
2. 首次触发失败时，`src/jewelry_on_hand/scoring.py` 的工作树修改时间变为 `2026-07-13 22:21:32 +08:00`；随后该并发范围继续更新并于 `22:23:36` 稳定。`tests/test_cli.py` 的修改时间仍为 `2026-07-13 21:06:38 +08:00`，本任务文件未触碰二者。
3. 并发改动后的目标组合变为 `107 passed, 1 failed`，单独复现同一既有测试也稳定失败。
4. 只读取证显示新的 `_filter_output_role_rows` 对 `OutputRole.HERO` 只接受 `purpose_category` 包含“主图”的行；既有失败测试把“主图”放在 `recommended_usage="产品主图特写"`，而 `purpose_category="上手姿势/手模构图参考"`，因此候选被过滤为空并由 CLI 返回 1。
5. 主线程确认稳定后的 `scoring.py` 仍是并发任务有意收紧 HERO `purpose_category` 的版本，而既有 CLI 测试尚未同步。该失败不经过本任务新增的无角色 CLI `generate` 测试路径，也不由 `tests/test_output_role_compatibility.py` 引入。依照并发隔离要求，本任务不修改、回退或覆盖 `scoring.py` 与既有脏测试，也不继续复跑。

## 未触发网络或 AIReiter 的证明

- CLI 测试在调用 `main(["generate", ...])` 之前，用 pytest `monkeypatch` 将 `jewelry_on_hand.cli.run_generation` 替换为本地 `capture_prompts`。
- `capture_prompts` 只把 `prompts_by_rank` 复制到内存字典并返回空列表；不调用 helper、不提交任务、不轮询网络，也不写生成结果。
- CLI 参数使用不存在的 `unused-helper.py` 路径仍能完成，证明真实 helper 未被执行。
- 测试断言 `run_root/generation` 不存在，因此没有创建 `submit.json`、`result.json`、`qc.json`、计费记录或伪造生成产物。
- 测试只在 pytest 的 `tmp_path` 下写入最小输入、分析、参考与决策夹具；便携 validator 只读取测试生成的 `prompt.txt`。

## 任务专属 diff 自审

由于两个任务文件都是新建且未跟踪，普通 `git diff -- <path>` 不会显示其正文；为保持“不暂存”约束，使用以下只读、仅针对本任务文件的等价自审命令：

```powershell
git diff --no-index -- NUL tests/test_output_role_compatibility.py
git diff --no-index -- NUL reference/superpowers/reports/2026-07-13-output-role-regression-tests-report.md
git status --short -- tests/test_output_role_compatibility.py reference/superpowers/reports/2026-07-13-output-role-regression-tests-report.md
```

自审结论：

- 变更范围仅为一个独立测试文件与本报告。
- 测试使用真实 `build_prompt`、真实 CLI 解析/门禁和真实便携 validator，没有复制生产 Prompt 逻辑。
- 无角色路径通过“省略 `output_role.json` + 决策解析为 `None`”表达；没有把 `worn` 当成 output role。
- 没有新增“未指定”“佩戴展示图”或其他角色白名单。
- 没有执行 `git add`、`git commit`、提交网络任务或改写历史产物。

## 关注项

存在一项外部并发关注：brief 指定的既有 Prompt/CLI 组合最近一次执行有 1 项 output-role 参考筛选测试失败，稳定后的并发 HERO 筛选契约与既有测试尚未同步，具体时间线和根因见上文；本任务新增的两项无角色回归测试均通过。另有一个过程性说明：新增测试首次运行前需要先存在 `--basetemp` 的父目录，该目录初始化后新增测试稳定通过。
