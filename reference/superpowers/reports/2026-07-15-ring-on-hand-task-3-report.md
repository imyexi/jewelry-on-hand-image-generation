# 任务 3：戒指产品上手身份图文档修订报告

## 状态

四份指定文档已按统一边界完成全文相关章节修订：经过确认的戒指细节图只作为 review、结构分析、canonical 约束和人工 QC 对照证据；`input/product-on-hand.jpg` 是生成阶段唯一产品身份图和固定内部图 2；细节图不传给 AIReiter，也不作为第三张模型输入；generation 固定保存内容与产品上手图一致的 `product-identity.jpg`。

本任务未修改测试或生产代码，未执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。

## 各文档修订

### `reference/manual-workflow.md`

- 在 `prepare-review` 戒指细节图章节保留 jpg/jpeg/png/webp 格式限制，以及主石、开口端点、戒圈和装饰不得被裁掉的完整性确认规则。
- 将细节图的现行用途修订为 review、结构分析、canonical 约束和人工 QC 对照证据，明确不进入模型。
- 将 `prepare-review` 产物说明修订为：产品上手图保存为 `input/product-on-hand.jpg`，细节图另存为 `input/product-detail.<ext>`，二者职责分离。
- 在 `generate` 章节明确内部图 2 固定使用 `input/product-on-hand.jpg`；即使存在细节图，也不得传给 AIReiter 或作为第三张模型输入。
- 明确戒指 generation 固定保存 `product-identity.jpg`，且审计副本内容与 `product-on-hand.jpg` 一致；保留内部图 2 人物、身体、皮肤、衣服和背景禁止迁移规则。

### `reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md`

- 修订标题、目标和架构，现行架构明确区分分析/QC 证据与送模产品身份图。
- 将演进过程改写为两阶段事实：2026-07-14 初次引入细节图时曾错误扩展到 generation 身份输入，该做法明确标为“已经废止的历史旧行为”；2026-07-15 修正为 generation 固定使用产品上手图。
- 全文修订任务 1、历史 run 兼容边界、任务 3 审计文件和任务 4 文档步骤；现行步骤不再要求细节图送模。
- 明确细节图不传给 AIReiter、不作为第三张模型输入；`product-identity.jpg` 内容与产品上手图一致。

### `skills/jewelry-on-hand-workflow/SKILL.md`

- 在四阶段强制流程的 `prepare-review` 与 `generate` 中写入统一边界：细节图只供分析/QC，内部图 2 固定为产品上手图，审计副本为内容一致的 `product-identity.jpg`。
- 在强制 Gate 中逐字写入三条便携契约：`产品上手图是生成阶段唯一产品身份图`、`细节图只用于 review、结构分析和 QC`、`不得作为第三张模型输入`。
- 清除“细节图存在时优先作为产品身份输入”的现行规则。
- 将所有品类的来源隔离规则明确为：禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。

### `skills/jewelry-on-hand-workflow/references/workflow.md`

- 在 `prepare-review` 章节保留细节图完整性确认，明确其只供 review、结构分析、canonical 约束和人工 QC 对照，不提交模型。
- 在 `generate` 章节逐字写入三条便携契约，并明确内部图 2 固定使用 `input/product-on-hand.jpg`。
- 明确即使存在 `input/product-detail.<ext>`，也不得传给 AIReiter；generation 固定写 `product-identity.jpg`，内容来自产品上手图。
- 保留逐字安全规则：`禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。`

## 验证结果

### 便携契约 RED 基线

修改前执行：

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

结果：退出码 1，`1 failed in 0.16s`。失败点是两份便携技能文档尚未包含新精确文本契约，符合任务 2 留下的预期 RED。

### 便携契约 GREEN

修改后多次执行同一命令，均为退出码 0、`1 passed`；最终新鲜复验耗时在 0.12 至 0.13 秒之间。

额外使用 `rg` 核对后，三条精确文本均同时出现在：

- `skills/jewelry-on-hand-workflow/SKILL.md`
- `skills/jewelry-on-hand-workflow/references/workflow.md`

### CLI 四阶段 E2E

执行：

```powershell
py -m pytest tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

结果：首次与报告完成后的最终新鲜复验均为退出码 0、`1 passed`，耗时 0.19 秒。

### 冲突搜索

执行 brief 指定命令：

```powershell
rg -n "细节图.*优先.*身份|生成的第二张输入使用细节图|内部图 2 使用细节图|作为审核和生成的产品身份图" reference skills\jewelry-on-hand-workflow src tests
```

结果分类：

- 四份本任务目标文档没有命中任何现行冲突规则。
- `reference/superpowers/plans/2026-07-15-ring-product-on-hand-identity.md` 的命中分别是“测试不得再要求旧行为”和冲突搜索命令本身，不是现行送模指令。
- `reference/superpowers/specs/2026-07-15-ring-product-identity-source-design.md` 的命中是要求删除旧规则。
- `reference/superpowers/reports/2026-07-15-ring-on-hand-task-2-report.md` 的命中是任务 2 RED 基线历史记录，以及需要继续保留的内部图 2 安全契约说明。
- 任务 2/3 brief 的命中是删除旧要求的验收文字或冲突搜索命令本身。
- 本报告自身的命中是修订记录、原样保存的检索命令，以及对剩余生产文案冲突的审计引用，不是现行操作指令。
- `src/jewelry_on_hand/cli.py:97` 仍有现行帮助文案：`作为审核和生成的产品身份图`。这是允许修改范围外的生产代码冲突，详见“顾虑”。

对四份目标文档另做扩大关键词复核：命中的细节图/generation 描述均为否定规则，或在旧计划中明确标注“历史阶段”“现已废止”“已经废止的历史旧行为”；没有把旧行为表述为现行指令。

### 差异校验

执行：

```powershell
git diff --check -- reference/manual-workflow.md reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md skills/jewelry-on-hand-workflow/SKILL.md skills/jewelry-on-hand-workflow/references/workflow.md
```

结果：退出码 0，无空白错误。Git 仅提示三个已跟踪文档下次触碰时可能由 LF 转换为 CRLF；这不是 `diff --check` 失败，本任务未做全文件格式化。

## 顾虑

`src/jewelry_on_hand/cli.py:97` 的 `--product-detail-image` 帮助文案仍把细节图描述为“审核和生成的产品身份图”，属于现行冲突。brief 同时规定本任务只能修改四份文档和本报告、不得修改生产代码，因此本任务未越界处理。上级控制器已确认将在任务级复核后按 TDD 单独修订该生产帮助文案；在该项完成前，不能声称仓库范围的冲突搜索已完全清零。
