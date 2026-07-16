# 参考构图快照完整性硬 Gate 修复 brief

## 目标

修复 `prepare-review` 先选入 Top 3、再因候选缺 `clothing` 等同步字段而在 `build_candidate_snapshot()` 崩溃的问题。任何无法生成完整 `ReferenceCompositionSnapshot` 的行必须在打分、质量窗口和低重复选择前排除；合格候选不足 3 张时，命令必须用中文明确列出数量与主要排除原因，不得写半成品 review/decision/generation。

## 绑定契约

- 当前 Skill 只支持 `hand_worn` 与 `lifestyle`；图片类型仍严格来自飞书 `图片类型` / 本地 `purpose_category`，不得视觉改判。
- 完整快照要求与 `build_candidate_snapshot()` 单一来源同态：真实文件、framing、visible body regions、pose、hand side/orientation、clothing、background、lighting、文字/UI 风险、唯一替换目标和产品展示面积全部可确认。
- 快照不完整是候选硬 gate，不是生成阶段补值点；不得使用“未标注”、默认衣服、默认姿势或其他占位绕过。
- gate 只排除不合格候选，不修改来源 `ReferenceRow`，并保留可审计的排除原因。
- `prepare-review` 需要恰好 3 个可审核候选；不足 3 个时在任何 review 产物写入前失败。
- 所有错误文案、测试名、注释与报告使用中文。
- 主工作区高度脏；只在独立 worktree 修改允许路径。

## TDD 与调试要求

1. 使用 `superpowers:systematic-debugging` 复现：Top 3 行通过既有品类/角色 gate，但至少一行缺 `collar_type` 或其他快照必填字段，当前选择成功而快照构建失败。
2. 先写 RED 覆盖：不完整行不进入 candidates/selected；三个完整行仍按质量窗口与低重复规则选择；完整行少于 3 时抛出包含角色、合格数和排除字段的中文错误；CLI 不写半成品 review。
3. 提取/复用一个与 `build_candidate_snapshot()` 同源的只读 readiness 校验，不要在 `scoring.py` 复制一套字段清单。若直接调用快照构建做 gate，避免吞掉非候选数据错误，并保证排除原因可审计。
4. 最小实现后运行 scoring、reference composition、review package、CLI、Task 12 定向矩阵与全量测试。

## 允许路径

- `src/jewelry_on_hand/reference_composition.py`
- `src/jewelry_on_hand/scoring.py`
- `src/jewelry_on_hand/cli.py`（仅用于错误传播或写前顺序）
- `tests/test_reference_composition.py`
- `tests/test_scoring.py`
- `tests/test_cli.py`

提交前只暂存必要允许路径，创建非 amend 提交。完整报告写入 `.superpowers/sdd/reference-snapshot-readiness-gate-fix-report.md`，不提交报告。
