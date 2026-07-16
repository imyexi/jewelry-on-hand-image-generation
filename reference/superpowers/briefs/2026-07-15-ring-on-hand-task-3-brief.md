# 任务 3：全文修订操作文档与技能工作流

## 目标

全文修订现行操作文档和便携技能，使其一致区分“分析/QC 证据图”和“送模产品身份图”，清除所有细节图优先送模的冲突规则。

## 文件

- 修改 `reference/manual-workflow.md`
- 修改 `reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md`
- 修改 `skills/jewelry-on-hand-workflow/SKILL.md`
- 修改 `skills/jewelry-on-hand-workflow/references/workflow.md`

任务 2 已修改但本任务不应再修改的验证文件：

- `tests/test_skill_portability.py`
- `tests/test_cli.py`

## 必须统一的规则

1. 戒指可提供经过确认的 `product-detail`，仅作为 review、结构分析、canonical 约束和人工 QC 对照证据；它不进入模型。
2. `input/product-on-hand.jpg` 是生成阶段唯一产品身份图。
3. 内部图 2 固定使用 `input/product-on-hand.jpg`。
4. 即使存在 `input/product-detail.*`，也不得把细节图传给 AIReiter 或作为第三张模型输入。
5. 戒指 generation 固定保存 `product-identity.jpg`，其内容与 `product-on-hand.jpg` 一致。
6. 继续保留并澄清：细节图必须事先确认未裁掉主石、开口端点、戒圈或装饰。这只约束分析/QC 证据完整性，不暗示送模。
7. 继续保留“禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。”安全规则。

## 精确文本契约

`skills/jewelry-on-hand-workflow/SKILL.md` 和 `skills/jewelry-on-hand-workflow/references/workflow.md` 必须同时逐字包含：

```text
产品上手图是生成阶段唯一产品身份图
细节图只用于 review、结构分析和 QC
不得作为第三张模型输入
```

可在同一句周围补充 canonical/人工 QC 语义，但不得破坏以上连续精确文本。

## 各文件要求

### `reference/manual-workflow.md`

- 在 prepare-review 相关章节明确细节图只作为 review、结构分析、canonical 和人工 QC 证据，不进入模型。
- 在 generate 相关章节明确内部图 2 固定为 `input/product-on-hand.jpg`；细节图不得传给 AIReiter、不得成为第三张输入；戒指审计副本内容与上手图一致。
- 删除将细节图称为生成身份图或表示细节图优先送模的表述。

### `skills/jewelry-on-hand-workflow/SKILL.md`

- 在强制 Gate/执行规则中采用统一边界。
- 包含三条精确文本契约。
- 保留人物/场景禁止迁移规则。

### `skills/jewelry-on-hand-workflow/references/workflow.md`

- 在四阶段流程的 prepare-review 和 generate 中采用统一边界。
- 包含三条精确文本契约。
- 保留细节图完整性确认规则和人物/场景禁止迁移规则。

### `reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md`

- 全文修订目标、架构、任务 1 及所有相关步骤，改写成两阶段事实：最初引入细节分析图，2026-07-15 再修正为 generation 固定使用产品上手图。
- 不能只在文末追加覆盖说明；全文不得保留任何现行“细节图优先作为生成身份输入”的要求。
- 历史描述若必须保留，要明确标为历史旧行为，而不能作为现行规则。

## 验证

先运行便携契约并确认从任务 2 的 RED 转为 GREEN：

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

再运行 CLI 四阶段测试，确保文档修订未破坏已有契约：

```powershell
py -m pytest tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

搜索冲突旧规则：

```powershell
rg -n "细节图.*优先.*身份|生成的第二张输入使用细节图|内部图 2 使用细节图|作为审核和生成的产品身份图" reference skills\jewelry-on-hand-workflow src tests
```

预期：现行文档和测试无冲突要求。若命中旧计划的历史描述，必须清晰标明其为已废止历史事实，且不能表述成现行指令。

最后运行：

```powershell
git diff --check -- reference/manual-workflow.md reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md skills/jewelry-on-hand-workflow/SKILL.md skills/jewelry-on-hand-workflow/references/workflow.md
```

## 工作区保护

当前四份目标文档都混有本任务前的未提交工作。必须理解上下文后修订相关章节，不得覆盖、回滚或删除无关内容，不得全文件格式化。不得修改测试或生产代码，不得执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
