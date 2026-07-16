# 参考底图替换工作流：任务 9 便携端到端审计

## 目标

提供只依赖 Python 标准库的便携校验器，离线验证 confirmed reference snapshot、四输入 Prompt、三层结构化 QC 和 generation 五输入 manifest；`inspect_run_artifacts.py` 对现代 run 做完整交叉审计，对历史 run 只读识别。

## 范围

- 新建：`skills/jewelry-on-hand-workflow/scripts/validate_reference_snapshot.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- 修改：`tests/test_skill_portability.py`

只允许这五个文件。脚本不得导入 `jewelry_on_hand` 或第三方库，不修改项目生产包、CLI、generation、QC 或文档。

## 统一退出码

- `0`：契约校验通过。
- `1`：文件存在且可解析，但业务契约、交叉绑定、摘要或完整性失败。
- `2`：参数错误、文件缺失/不可读、JSON 语法/编码错误等无法执行校验的输入错误。

所有错误中文、无 traceback；stdout/stderr 约定确定性，帮助文本可用。

## Snapshot validator

`validate_reference_snapshot.py SNAPSHOT --reference FILE --output-role {hand_worn,lifestyle}`：

- 严格校验 Task 2 顶层字段和 `pose`/`replacement_target` 闭集，拒绝额外/缺失字段、bool 伪装整数、blocking UI、展示不足、非单件目标。
- 实际参考文件 SHA-256、文件名、角色一致；仅 hand_worn/lifestyle，拒绝 hero。
- 按 Task 2 固定投影重算 `composition_signature`，未知嵌套字段即使协调重签名也拒绝。
- 成功输出“参考构图快照校验通过”。

## Prompt validator 四输入

现代调用继续为 `prompt + snapshot + analysis + canonical`，legacy 单输入只读：

- 从 generation 固定文件 `prompt.txt`、`reference-composition-snapshot.json`、`product-analysis.json`、`product-fidelity-constraints.json` 校验。
- 两条 canonical JSON 与 analysis/canonical 投影逐字节、类型严格一致；拒绝重复 key、Unicode escape、额外空白、键序/字段变化、`1/1.0/true` 混淆。
- 锁定值与 snapshot 一致；参考底图仍为唯一构图源。
- 仅允许 Task 8 的 `REFERENCE_STRUCTURE_RETRY_SUFFIX` 作为精确单次尾缀；重复、变体或其他尾部文本拒绝。
- legacy 输出 `legacy_read_only=true`，不能作为现代 generation gate。

## QC validator

现代 QC 从 generation 目录固定读取 snapshot、analysis、canonical，并重建三层预期：

- 十项 reference checks 固定、完整、唯一、问题匹配。
- 每项结构化 evidence 的 comparison_source/region/observation、issue_code、残留 facts 与 Task 8 模型契约一致。
- reference fail 与九严重码集合严格映射；pass/rerun/reject 三层状态一致。
- fidelity/checklist 完整、稳定 ID/问题/结果一致；notes 不能替代 evidence。
- 缺项、重复、未知、统一伪证据、明显泄漏伪 rerun 均拒绝。

## Run inspector

对每个现代 generation/NN 要求并交叉校验：

- `scene-reference.*`、`product-reference.*`、`reference-composition-snapshot.json`、`product-analysis.json`、`product-fidelity-constraints.json`、`input-manifest.json`、`prompt.txt`、任务记录；已完成结果还要求 `result.*`、`qc-review.html`、`qc.json`。
- manifest `schema_version=1`、角色、两个有序 image entries，以及 snapshot/analysis/canonical 的 copied_file+SHA；实际副本摘要与源/manifest一致。
- 图片顺序固定 scene_reference 后 product_identity；不接受现代 `hand-reference.*`。
- 调用 snapshot、四输入 Prompt、QC 校验逻辑并汇总中文错误。

历史 run：只读识别 `hand-reference.*`/旧格式，输出 legacy/read-only 状态；不得重命名、补写、迁移或把部分现代文件的 damaged run 误判为 legacy。

## TDD

- 快照：成功、坏JSON=2无traceback、SHA/role/rank/count/嵌套字段/签名错误=1。
- Prompt：固定四输入成功；缺任一输入、摘要/投影/JSON类型篡改；suffix精确一次。
- QC：缺十项、重复/未知、evidence缺失/错源、issue/facts错误、严重码映射、三层状态。
- Inspector：缺manifest、顺序反转、copied_file路径逃逸、摘要错误、输入文件替换、Prompt/QC失败、现代hand-reference拒绝、完整现代通过。
- 历史完整只读通过；部分现代/damaged拒绝且不修改磁盘。

RED/GREEN：

```powershell
python -m pytest tests/test_skill_portability.py `
  -k "reference_snapshot or input_manifest or reference_preservation" -v `
  --basetemp=output/t09-red -o cache_dir=output/cache-t09-red
python -m pytest tests/test_skill_portability.py -v `
  --basetemp=output/t09-green -o cache_dir=output/cache-t09-green
```

随后对四脚本 `py_compile`，并以直接子进程验证退出码/UTF-8。使用短 `output/` 路径。

## 安全

- 从最新 HEAD 新建短路径 detached worktree；主五目标先做 output只读快照/SHA，主树禁止写入/restore/checkout。
- 为每个 dirty 文件选择正确 merge-base，保留 Task 6 四输入、Task 8 evidence 与用户并发便携改动，不整文件覆盖。
- 同类并发持续授权自动重基线；只提交五文件，detached+主index plumbing非amend。
- 集成前后主工作字节/ABSENT状态不变、索引空、tested/detached/main tree一致。
- 报告全文写入 `.superpowers/sdd/reference-replacement-task-9-report.md`。
- 禁止网络、飞书、生图或付费接口。
