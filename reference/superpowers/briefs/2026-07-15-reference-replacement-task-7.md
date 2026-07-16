# 参考底图替换工作流：任务 7 实施简报

## 目标

把已经人工绑定的参考底图、产品身份图、确认快照、产品分析和 canonical 保真约束固化到每个 generation 目录，并让提交给 helper 的两张图片只来自 generation 内副本，顺序固定为参考底图在前、产品身份图在后。所有新产物必须能由 Task 9 的四输入 validator 离线复核。

## 修改范围

- 修改：`src/jewelry_on_hand/generation.py`
- 修改：`src/jewelry_on_hand/cli.py`
- 修改：`tests/test_generation.py`
- 修改：`tests/test_cli.py`

不得修改 `inspect_run_artifacts.py`，该接入属于 Task 9。不得修改 Prompt 契约、评分、审核选择或 QC 规则；不得生图、调用真实或付费 AIReiter、上传或回写飞书。

## 输入与输出契约

输入只接受：已绑定的 `ReviewDecision`、Task 5 的 `review/reference_composition_snapshot.json`、selected review 参考图副本、产品身份图、已确认的 analysis、已确认的 canonical constraints，以及按唯一 rank 构建的 Prompt。

每个 `generation/NN/` 必须固化：

- `scene-reference.*`
- `product-reference.*`
- `reference-composition-snapshot.json`
- `product-analysis.json`
- `product-fidelity-constraints.json`
- `input-manifest.json`
- 既有 Prompt 与任务审计产物

新 run 不得再写 `hand-reference.*`。helper 的两个 `--image` 参数必须只指向 generation 目录内副本，且依次为 `scene-reference.*`、`product-reference.*`。

## Manifest schema

`input-manifest.json` 使用 `schema_version=1`，至少包含：

- `output_role`
- `reference_snapshot`：`copied_file`、`sha256`
- `product_analysis`：`copied_file`、`sha256`
- `fidelity_constraints`：`copied_file`、`sha256`
- `inputs`：严格两个有序条目

每个 input 条目包含：`order`、`role`、`source_path`、`copied_file`、`sha256`。角色顺序固定为 `scene_reference`、`product_identity`。

analysis、canonical 与 snapshot 的摘要必须按复制后文件的实际字节计算，并同时与源文件摘要一致。manifest 的固定文件名与摘要将作为 Task 9 调用 `validate_prompt(prompt, snapshot, analysis, canonical)` 的唯一定位依据，不允许只记录外部绝对路径而不复制文件。

## 原子预检与失败边界

在创建任何 `generation/NN` 之前完成全部 rank 的预检：

1. 当前 Skill 角色必须是 `hand_worn` 或 `lifestyle`，拒绝 `hero`。
2. decision、decision 中的 snapshot digest、确认快照、输出角色、唯一 selected rank 必须一致。
3. selected review 参考副本的文件名和 SHA-256 必须与快照一致。
4. 产品图、analysis、canonical、所有 Prompt 和所有目标目录必须存在并可读。
5. analysis/canonical 必须是人工确认链使用的原始文件；生成阶段不得重建、猜测或改写其业务内容。
6. 复制计划、文件名冲突、目标目录冲突和第二个 job 的所有输入也必须先预检。

任一预检失败时：不得创建 generation 目录、不得复制文件、不得调用 helper，并返回中文错误，明确要求回到 `prepare-review` 或重新确认。

复制阶段使用 staging：先复制五份输入，逐个重算摘要，写 manifest 和 Prompt，再原子发布 generation 目录。复制、摘要或写入失败时必须删除未发布 staging，不能留下伪完整 generation。若批次含多个 rank，任何 rank 在提交前固化失败，则整个批次不得提交任何 helper job。

## TDD 必测

先写 RED，并保留首次失败证据：

- generation 复制五份可信输入，manifest 两张图片顺序正确；helper 参数为 run 内 scene 后 product。
- scene source 被篡改、snapshot SHA 不一致、decision digest 不一致、角色不一致、产品图缺失时，在任何写入或提交前失败。
- analysis 或 canonical 缺失、摘要不一致、复制后被篡改时 fail-closed。
- manifest 中 snapshot/analysis/canonical 的文件名和 SHA 可用于四输入 validator 固定定位。
- 复制失败、写 manifest 失败、第二个 job 预检失败时不得提交任何 rank，也不得留下已发布的半成品目录。
- 新 run 不产生 `hand-reference.*`。
- 现有三个 Task 7 CLI generate 失败用例通过：CLI 加载 confirmed snapshot、analysis、canonical，传给 Prompt builder，并固化 generation 审计。
- hero、缺快照或历史 run 仍拒绝生成，不得用 legacy Prompt 路径绕过。

聚焦 RED：

```powershell
python -m pytest tests/test_generation.py tests/test_cli.py `
  -k "input_manifest or scene_reference or snapshot_sha or analysis_copy or canonical_copy" -v `
  --basetemp=output/t07-red -o cache_dir=output/cache-t07-red
```

GREEN 后运行：

```powershell
python -m pytest tests/test_reference_composition.py tests/test_generation.py tests/test_cli.py tests/test_prompt_builder.py -v `
  --basetemp=output/t07-green -o cache_dir=output/cache-t07-green
```

所有测试必须显式设置隔离 worktree 的 `PYTHONPATH=<worktree>/src`。若全量或相关回归仍有既有失败，逐项与 Task 6 的 12 个旧文档失败集合比较，不得掩盖新增失败。

## 安全提交与报告

- 从 `7375d543529aac34f0843393c0e05b5097787a80` 创建 `output/` 下的 detached worktree。
- 开始前记录主工作树四个目标文件 SHA-256，并确认主索引为空；发现并发变化立即停止。
- 实现代理遵循 RED -> GREEN、自审、`py_compile`、`git diff --check`，在 detached worktree 非 amend 提交。
- 主工作树只用 index plumbing 集成已测试 blob；提交前后目标文件工作区 SHA 不变、索引为空，tested tree、detached tree 与主 HEAD tree 完全一致。
- 实施报告写入 `.superpowers/sdd/reference-replacement-task-7-report.md`，包含 RED/GREEN、相关回归、产物 schema、提交/tree、安全证据和 concerns。

## 完成定义

- 三个 Task 7 CLI 接缝失败被真实修复，不回退到无快照或 legacy Prompt。
- 每个新 generation 同时固化两张图片、snapshot、analysis、canonical 和 manifest，所有 SHA 可互相追溯。
- helper 只读取 run 内副本且顺序固定。
- 任何预检或固化失败均无外部提交、无已发布半成品。
- Task 9 能仅根据 generation 目录固定文件名和 manifest 调用四输入 validator。
- 独立规格审查和代码质量审查均通过后才可进入 Task 8。
