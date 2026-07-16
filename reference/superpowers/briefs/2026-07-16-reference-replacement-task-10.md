# 参考底图替换工作流：任务 10 历史 run 只读迁移门禁

## 目标

把参考替换 run 明确分为 `modern_snapshot`、`legacy_read_only`、`damaged` 三态。历史 run 可以由便携 inspector 只读审计，但 `record-decision` 与 `generate` 必须拒绝追加写入，并提示重新执行 `prepare-review`；任何新旧快照链部分混合均为 damaged，不得通过删除单个文件降级成 legacy。

## 范围

- 修改：`src/jewelry_on_hand/reference_composition.py`
- 修改：`src/jewelry_on_hand/review_decision.py`
- 修改：`src/jewelry_on_hand/generation.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- 修改：`tests/test_generation.py`
- 修改：`tests/test_review_decision.py`
- 修改：`tests/test_skill_portability.py`

只允许以上七个文件。所有代码注释、错误文案和测试名称使用中文；测试产物放 `output/`。禁止网络、飞书、生图、AIReiter 和付费接口。

## 前置状态

- 基线主提交：`df5edbb7a339a779d23278aee8aa008029c24006`。
- Task 9 已批准并绑定现代 run 的产品原图、唯一 selected rank、完整 decision、确认快照、原始参考图、review 副本、generation 副本和 manifest SHA。
- 便携 inspector 已把每个 `generation/NN` 分类为 modern、legacy 或 damaged，并对完整 legacy 输出 `legacy_read_only=true`。
- 当前实现仍可能允许历史 run 进入写入口；Task 10 只收紧迁移边界，不修改现代生成语义。

## 接口与三态判定

在 `reference_composition.py` 提供：

```python
ReferenceRunState = Literal["modern_snapshot", "legacy_read_only", "damaged"]

def classify_reference_run(paths: RunPaths) -> ReferenceRunState: ...

def require_modern_reference_run(paths: RunPaths) -> ReferenceCompositionSnapshot: ...
```

判定至少绑定以下根产物：

- `analysis/reference_composition_snapshots.json`
- `review/reference_composition_snapshot.json`
- `review/review_decision.json` 中合法的 `reference_snapshot_sha256`
- 已存在 generation 时的现代 `input-manifest.json` 与现代固化副本

完整现代链为 `modern_snapshot`；现代标记全部不存在且历史根/历史 generation 完整时为 `legacy_read_only`；任何部分存在、摘要错误、混合 modern/legacy、现代残片或缺关键文件均为 `damaged`。不得只按一个文件存在与否判断。

`require_modern_reference_run` 仅对完整现代链加载并返回确认快照；legacy 抛出含“历史 run 只读、重新执行 prepare-review”的中文错误，damaged 抛出含“run 产物不完整/损坏、重新执行 prepare-review”的中文错误。

## 写入口

- `review_decision.require_generation_decision` 返回前调用现代 run gate。
- `generation.run_generation` 在任何新 generation 目录、提交记录或外部 helper 调用前再次调用现代 run gate，并使用其返回的 confirmed snapshot，防止绕过 CLI 或直接函数调用。
- 只读 inspector 使用等价的标准库独立三态语义；不得导入 `jewelry_on_hand`。
- inspector 对完整 legacy 返回 0，并输出 `legacy_read_only=true`；damaged 返回 1；语法/缺失输入仍遵守 Task 9 的退出码 2 契约。
- 检查和失败路径不得修改历史 JSON、补文件、迁移、重命名或创建 generation 目录。

## TDD

先写并观察 RED：

1. 完整 legacy run 被分类为 `legacy_read_only`，inspector 只读通过，但 `require_generation_decision` 和 `run_generation` 均拒绝。
2. 完整现代 run 为 `modern_snapshot`，既有现代 decision/generation 正常通过。
3. 候选快照、确认快照、decision digest、generation manifest/固化副本的每种部分存在组合均为 `damaged`。
4. 删除现代链中的单个文件不能降级为 legacy；modern/legacy 混合必须 damaged。
5. legacy/damaged 拒绝前后目录字节与文件清单完全不变，helper 未被调用、未创建新 generation 目录。
6. 非对象 decision、坏 digest 类型/长度/大小写、快照摘要不一致返回中文业务错误，不 traceback。

聚焦 RED/GREEN：

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
$env:PYTHONUTF8='1'
python -m pytest tests/test_generation.py tests/test_review_decision.py `
  tests/test_skill_portability.py -k "legacy_read_only or damaged or migration" -v `
  --basetemp=output/t10-red -o cache_dir=output/cache-t10-red
```

随后运行三个完整目标测试文件，并运行 generation/decision/reference composition/CLI 相关回归。使用短 ASCII basetemp；所有测试显式设置隔离 worktree 的 `PYTHONPATH`。

## 安全与提交

- 从 `df5edbb` 创建 `output/` 下短路径 detached worktree，不写主工作区。
- 先记录主七目标工作字节 SHA/ABSENT；主 HEAD、索引或目标文件发生并发变化时按用户持续授权重新基线，但不得覆盖用户内容。
- 严格 TDD；提交前核对 `git diff --cached --name-only` 仅含七个目标文件。
- 创建非 amend 提交；报告全文写入 `.superpowers/sdd/reference-replacement-task-10-report.md`，报告不进入七文件提交。
- 提交后提供 worktree、base、commit、tree、RED/GREEN、完整回归、`py_compile`/`git diff --check` 和 concerns。
