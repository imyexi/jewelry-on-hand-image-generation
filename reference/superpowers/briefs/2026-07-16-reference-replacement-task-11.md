# 参考底图替换工作流：任务 11 Skill 与文档全文修订

## 目标

把 `jewelry-on-hand-workflow` 全文收敛为只支持 `hand_worn` 与 `lifestyle` 的真人参考底图首饰替换 Skill：参考底图是人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置的唯一来源；产品上手图只提供目标珠宝身份；模型只能移除参考图原首饰并在同一位置换入一件目标产品，外加必要接触阴影和小面积水印处理。`hero` 必须交给独立主图 Skill；历史 run 只读，不得追加 decision/generation。

## 基线与安全

- 基线主提交：`b013461f0250765199b036bbd46e330047183d38`。
- 主工作区高度脏，所有内容视为用户改动。任务开始前记录下列目标的工作字节 SHA/ABSENT；在 `output/` 下短路径 detached worktree 实现，禁止写主工作区、restore/checkout/reset/merge/rebase。
- 多个目标文档在主工作区含未提交的新项链、戒指、飞书参考源和并发工作内容；隔离 worktree 必须先以主工作区当前目标文件作为用户基线覆盖对应文件，再全文修订，不能从旧 HEAD 整文件覆盖用户版本。
- 禁止网络、飞书写回、AIReiter、生图和付费接口。

## 文件范围

- `skills/jewelry-on-hand-workflow/SKILL.md`
- `skills/jewelry-on-hand-workflow/agents/openai.yaml`
- `skills/jewelry-on-hand-workflow/references/workflow.md`
- `skills/jewelry-on-hand-workflow/references/prompt-contract.md`
- `skills/jewelry-on-hand-workflow/references/reference-composition-contract.md`（新建）
- `skills/jewelry-on-hand-workflow/references/qc-checklist.md`
- `skills/jewelry-on-hand-workflow/references/troubleshooting.md`
- `reference/manual-workflow.md`
- `reference/prompt-template.md`
- `reference/qc-checklist.md`
- `reference/review-decision-schema.md`
- `reference/feishu-reference-source.md`
- `reference/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md`
- `tests/test_skill_portability.py`

提交只允许以上 14 个路径。所有参考/流程 Markdown 保持在 `reference/` 或 Skill `references/`，测试产物放 `output/`。更新文档必须全文修订，删除前后矛盾，不能只在末尾追加补丁说明。

## 已完成的 writing-skills RED

旧 Skill 的三个全新代理原文已保存：

- `output/reference-replacement-workflow/2026-07-14/skill-red/01-reference-priority.md`
- `output/reference-replacement-workflow/2026-07-14/skill-red/02-hero-boundary.md`
- `output/reference-replacement-workflow/2026-07-14/skill-red/03-legacy-run.md`

实际失败分别是：

1. 把参考图描述为姿势/氛围参考，明确允许人物和环境重新生成或适度调整。
2. 明确允许当前 Skill 继续 `hero`，并给出 record/generate 命令。
3. 明确允许缺少 `reference_composition_snapshot.json` 的历史 run 继续 generate。

不得覆盖或伪造这些 RED 输出。

## TDD 文档契约

先在 `tests/test_skill_portability.py` 增加并观察 RED，至少固定：

- Skill 明确“只支持 `hand_worn` 和 `lifestyle`”“参考底图是画面结构唯一来源”“产品上手图只提供珠宝身份”“主图必须交给独立主图 Skill”。
- Skill 不含 `hand-reference`、当前 Skill 生成 hero、深色主图例外或三图同 Skill 编排。
- Skill 直接链接 `references/workflow.md`、`prompt-contract.md`、`reference-composition-contract.md`、`qc-checklist.md`、`troubleshooting.md`。
- 所有操作文档一致描述四阶段 `prepare-review -> record-decision -> generate -> qc`、显式 `--output-role`、飞书图片类型唯一来源、五输入 manifest、三态迁移和三层 QC。
- 文档不得声称参考图仅提供氛围、产品图提供构图、历史 run 可续写、现代 generation 使用 `hand-reference.*`。
- 保留项链 v2、戒指 1200 字预算、产品保真 canonical、飞书 pending/enrichment/CAS 审计等现有正确契约。

使用短路径运行 RED；记录精确失败，不因既有 `pendant_semantics.position` 范围外失败而修改 Task 11 文档契约测试。

## Skill 渐进披露

### `SKILL.md`

- frontmatter 仅 `name` 与 `description`。
- `name: jewelry-on-hand-workflow`。
- description 使用中文触发条件句，说明何时用于真人场景的手部佩戴/生活场景首饰替换及严格保留参考图；不概括内部步骤。
- 正文少于 500 行，只保留：角色边界、核心原则、四阶段强制流程、关键 gate、reference 路由、历史只读与安全边界。
- 不重复粘贴详细 schema；每份详细契约只在对应 reference 中维护。
- 直接链接五份 references；详细用法要求按需读取。

### Skill references

- `workflow.md`：四阶段 CLI、输入输出、人工确认、dry run、现代五输入、历史只读。
- `prompt-contract.md`：底图编辑开头、内部图 1/2 职责、快照优先、允许修改区域、严格保留与冲突停止、1200 字预算。
- `reference-composition-contract.md`：完整 schema、候选与确认差异、SHA/rank/role/source 绑定、不可修改字段、三态和停止条件。
- `qc-checklist.md`：reference/fidelity/checklist 三层检查、十项 reference evidence、pass/rerun/reject、critical code 和重跑路由。
- `troubleshooting.md`：SHA、角色、快照、历史 run、damaged、构图漂移、源图迁移、UTF-8/退出码恢复动作。

### 项目 `reference/`

全文同步最终实现，不得保留：当前 Skill 生成主图、深色背景主图例外、参考图只提供氛围、产品构图字段覆盖参考图、新 run 写 `hand-reference.*`、历史 run 可继续生成。保留并整合新项链、戒指、产品保真与飞书审计内容。

## `agents/openai.yaml`

使用 deterministic generator，不手写：

```powershell
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py `
  skills/jewelry-on-hand-workflow `
  --interface 'display_name=Jewelry Scene Replacement' `
  --interface 'short_description=严格保留真人参考图并替换为目标珠宝' `
  --interface 'default_prompt=Use $jewelry-on-hand-workflow to replace jewelry in a hand-worn or lifestyle reference while preserving the reference composition.'
```

只保留 generator 产生的 `interface` 字段；所有字符串加引号，default prompt 必须显式包含 `$jewelry-on-hand-workflow`。

## GREEN 与验证

1. 运行新增契约和完整 `tests/test_skill_portability.py`；文档相关 baseline 失败应全部清零。若仅剩 `pendant_semantics.position` 的范围外既有失败，明确记录且不得用文档改动掩盖。
2. 运行 `quick_validate.py skills/jewelry-on-hand-workflow`，必须输出 Skill 有效。
3. 检查 `SKILL.md < 500` 行、frontmatter 只有两个字段、五个 direct references、无 README/CHANGELOG/重复 schema。
4. 使用三个新的全新代理原样重跑 RED 的三个 exact prompt，把逐字输出保存到 `output/reference-replacement-workflow/2026-07-14/skill-green/`。不得提供预期答案。GREEN 标准：参考底图锁定且只替换首饰；拒绝 hero 并指向独立主图 Skill；拒绝历史 run 生成并要求重新 `prepare-review`。
5. 运行 `git diff --check`，核对暂存仅 14 个目标路径；创建非 amend 提交。
6. 报告全文写入 `.superpowers/sdd/reference-replacement-task-11-report.md`，不进入 14 文件提交；报告包含 RED/GREEN 代理输出路径、测试计数、quick_validate、行数、generator 命令、范围和 concerns。
