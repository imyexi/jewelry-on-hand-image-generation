# 戒指产品上手身份图实施计划

> **供 agentic worker 使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实施本计划，并用复选框跟踪每一步。

**目标：** 戒指生成时始终把产品上手图作为内部图 2 和 generation 审计身份图，正面/细节图仅保留给分析、结构确认与 QC。

**架构：** `prepare-review` 的细节图接收、review 展示和 canonical 分析证据保持不变；`run_generation()` 不再扫描 `input/product-detail.*`，直接使用调用方传入的 `input/product-on-hand.jpg`。仅戒指 generation 固定复制该上手图为 `product-identity.jpg`，其余品类行为不变。

**技术栈：** Python 3.11+、pytest、现有 AIReiter helper、SHA-256/JSON 审计文件；不新增图片处理依赖。

## 全局约束

- 所有思考、输出和文档使用中文。
- 参考文档和流程 Markdown 放在 `reference/`，测试与真实生成产物放在 `output/`。
- 不删除 `--product-detail-image`；它继续用于 review、分析、canonical 和人工 QC。
- 正面图或细节图不得进入 AIReiter 的任何 `--image` 参数，也不得作为第三张模型输入。
- 不覆盖历史 generation 和 2026-07-15 首轮测试结果；重新生成必须使用新 run 根目录。
- 不改变参考图 Top 3、Prompt、失败码纠偏和模型切换策略。
- 不写回产品货盘或参考素材飞书 Base。

---

### 任务 1：generation 固定使用产品上手图

**文件：**

- 修改：`tests/test_generation.py:64`
- 修改：`src/jewelry_on_hand/generation.py:91`
- 修改：`src/jewelry_on_hand/generation.py:120`
- 删除逻辑：`src/jewelry_on_hand/generation.py:162`

**接口：**

- 消费：`run_generation(paths: RunPaths, product_image: str | Path, prompts_by_rank: Mapping[int | str, str], helper_script: str | Path, wait: bool = True) -> list[Path]`
- 保持：helper 的第一张 `--image` 是选定 Rank 的手部构图参考图。
- 产出：helper 的第二张 `--image` 对戒指固定为 `product_image`，CLI 中即 `input/product-on-hand.jpg`；戒指 generation 写出同内容的 `product-identity.jpg`。

- [ ] **步骤 1：把现有细节图优先测试改成目标行为测试**

将 `test_ring_generation_prefers_reviewed_product_detail_and_copies_audit_image` 改为：

```python
def test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    detail = paths.input_dir / "product-detail.png"
    detail.write_bytes(b"reviewed ring detail")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-on-hand"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generated = run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    command = calls[0]
    first = command.index("--image") + 1
    second = command.index("--image", first) + 1
    assert command[second] == str(product)
    assert str(detail) not in command
    assert (generated[0] / "product-identity.jpg").read_bytes() == product.read_bytes()
```

- [ ] **步骤 2：运行单测并确认 RED**

运行：

```powershell
py -m pytest tests\test_generation.py::test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail -q
```

预期：FAIL；实际第二个 `--image` 仍为 `product-detail.png`，且审计副本不是 `product-identity.jpg`。

- [ ] **步骤 3：实现最小 generation 修改**

在 `run_generation()` 中删除 `_product_identity_path()` 的选择调用，固定：

```python
product_identity_path = product_path
```

将审计复制改为仅对戒指执行且始终复制：

```python
if product is not None and product.confirmed_product_type is ProductType.RING:
    shutil.copy2(
        product_identity_path,
        generation_dir / f"product-identity{product_identity_path.suffix.lower()}",
    )
```

删除不再使用的 `_product_identity_path()`；不要改变 `_submit_command()` 的图像顺序。

- [ ] **步骤 4：运行目标单测并确认 GREEN**

运行：

```powershell
py -m pytest tests\test_generation.py::test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail -q
```

预期：`1 passed`。

- [ ] **步骤 5：运行 generation 戒指回归**

运行：

```powershell
py -m pytest tests\test_generation.py -q
```

预期：该文件全部通过；非戒指 `test_generation_uses_reference_then_product` 继续证明原有第二图行为不变。

- [ ] **步骤 6：提交任务 1**

```powershell
git add src/jewelry_on_hand/generation.py tests/test_generation.py
git commit -m "fix: use ring on-hand image as model identity"
```

### 任务 2：CLI 端到端与便携契约同步

**文件：**

- 修改：`tests/test_cli.py:1870`
- 修改：`tests/test_skill_portability.py:249`

**接口：**

- 消费：任务 1 保证的 `run_generation()` 第二图与审计副本行为。
- 产出：CLI 四阶段测试断言 `product-detail.png` 仍存在并供 review/canonical 使用，但 helper 第二图和 `product-identity.jpg` 均为 `product-on-hand.jpg`。

- [ ] **步骤 1：修改 CLI 端到端断言**

保留以下 prepare-review 断言：

```python
assert constraints["source"]["product_image"] == "input/product-detail.png"
assert (run_root / "input" / "product-detail.png").read_bytes() == product_detail.read_bytes()
assert "product-detail.png" in (run_root / "review" / "review.html").read_text(encoding="utf-8")
```

将 generation 断言改为：

```python
assert (generation_dir / "product-identity.jpg").read_bytes() == product_image.read_bytes()
_assert_task9_submit_call(
    helper_log,
    run_root,
    selected_reference,
    generation_dir,
    expected_product=run_root / "input" / "product-on-hand.jpg",
)
```

- [ ] **步骤 2：运行 CLI 戒指 E2E 并确认旧实现下 RED 或任务 1 后 GREEN**

运行：

```powershell
py -m pytest tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q
```

预期：任务 1 已完成时 `1 passed`；若在任务 1 前单独执行，本测试必须因身份图仍为细节图而失败。

- [ ] **步骤 3：修订便携技能契约测试的精确文本**

让 `test_portable_workflow_keeps_product_identity_input_migration_boundary` 要求 `SKILL.md` 和 `references/workflow.md` 同时包含以下语义：

```python
required = (
    "产品上手图是生成阶段唯一产品身份图",
    "细节图只用于 review、结构分析和 QC",
    "不得作为第三张模型输入",
)
```

测试不得再要求“细节图存在时优先作为产品身份输入”。

- [ ] **步骤 4：运行便携契约测试并确认 RED**

运行：

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

预期：FAIL；现有技能文档仍声明细节图优先送模。

- [ ] **步骤 5：提交任务 2 的测试变更**

先不提交失败状态；任务 3 文档 GREEN 后与文档一起提交。

### 任务 3：全文修订操作文档与技能工作流

**文件：**

- 修改：`reference/manual-workflow.md:110-130`
- 修改：`reference/manual-workflow.md:185-195`
- 修改：`skills/jewelry-on-hand-workflow/SKILL.md:50-65`
- 修改：`skills/jewelry-on-hand-workflow/references/workflow.md:30-45`
- 修改：`skills/jewelry-on-hand-workflow/references/workflow.md:75-90`
- 修改：`reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md:6-24`

**接口：**

- 消费：任务 1 的真实代码行为与任务 2 的便携契约测试。
- 产出：所有现行操作文档一致区分“分析证据图”和“送模身份图”。

- [ ] **步骤 1：修订 manual workflow 的 prepare-review 章节**

明确写入：

```text
戒指可提供经过确认的 product-detail 作为 review、结构分析、canonical 约束和人工 QC 对照证据；它不进入模型。产品上手图 input/product-on-hand.jpg 是生成阶段唯一产品身份图。
```

删除任何“review 和 canonical 改用该细节身份图”中把细节图称为生成身份图的表述；canonical 可以继续记录细节图作为分析证据。

- [ ] **步骤 2：修订 manual workflow 的 generate 章节**

明确写入：

```text
内部图 2 固定使用 input/product-on-hand.jpg。即使存在 input/product-detail.*，也不得把细节图传给 AIReiter 或作为第三张输入。戒指 generation 固定保存 product-identity.jpg，其内容与 product-on-hand.jpg 一致。
```

- [ ] **步骤 3：修订便携 SKILL 与 workflow 副本**

在 `SKILL.md` 的强制 Gate 和 `references/workflow.md` 四阶段流程中使用与主文档一致的规则；同时保留：

```text
细节图必须事先确认未裁掉主石、开口端点、戒圈或装饰。
```

该句只约束分析/QC 证据，不再暗示细节图送模。

- [ ] **步骤 4：全文修订旧实施计划的目标和任务 1**

把已完成历史任务改写为两阶段事实：最初引入细节分析图，2026-07-15 再修正为“生成固定使用上手图”。不得只在文末追加覆盖说明。

- [ ] **步骤 5：运行便携契约测试并确认 GREEN**

运行：

```powershell
py -m pytest tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

预期：`1 passed`。

- [ ] **步骤 6：搜索冲突旧规则**

运行：

```powershell
rg -n "细节图.*优先.*身份|生成的第二张输入使用细节图|内部图 2 使用细节图|作为审核和生成的产品身份图" reference skills\jewelry-on-hand-workflow src tests
```

预期：没有现行文档或测试继续要求细节图送模；历史验证报告若保留旧事实，必须明确标注为历史 run。

- [ ] **步骤 7：提交任务 2 和任务 3**

```powershell
git add tests/test_cli.py tests/test_skill_portability.py reference/manual-workflow.md reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md skills/jewelry-on-hand-workflow/SKILL.md skills/jewelry-on-hand-workflow/references/workflow.md
git commit -m "docs: separate ring detail evidence from model identity"
```

### 任务 4：定向回归与真实三图重新生成

**文件：**

- 创建：`output/ring-product-on-hand-identity/2026-07-15/verification.json`
- 创建：`output/ring-feishu-test/2026-07-15/runs-on-hand-identity-v3/`
- 创建：`output/ring-feishu-test/2026-07-15/final-on-hand-identity/`

**接口：**

- 消费：任务 1 至 3 的 generation 行为、CLI 契约和文档规则。
- 产出：三个新 run、三张只以上手图作为内部图 2 的 QC 通过结果，以及可追溯验证报告。

- [ ] **步骤 1：运行戒指定向回归**

运行：

```powershell
py -m pytest tests\test_generation.py tests\test_cli.py::test_cli_end_to_end_ring_four_stage_workflow tests\test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q
```

预期：全部通过。

- [ ] **步骤 2：创建三个新 run**

对 JH025、JH026、JH501 分别执行 `prepare-review`，输出根目录固定为：

```text
output/ring-feishu-test/2026-07-15/runs-on-hand-identity-v3
```

继续传入 `--product-detail-image` 供 review/canonical/QC，继续使用已审核的 `ring-test-reference-catalog.xlsx` 和 `--output-role hand_worn`。不得复用或修改 `runs-local-ref-v2`。

- [ ] **步骤 3：记录与首轮一致的参考决策**

固定选择：

```text
JH025 -> Rank 3
JH026 -> Rank 1
JH501 -> Rank 1
```

执行 `record-decision --action generate_selected --selected-ranks <rank> --fidelity-confirmed --output-role hand_worn`。

- [ ] **步骤 4：生成前执行身份图 dry check**

先使用测试或命令检查每个 run：

```text
input/product-on-hand.jpg 存在
input/product-detail.* 存在但不会进入 helper command
新 generation 将使用 product-on-hand.jpg 作为第二图
```

- [ ] **步骤 5：提交三项 AIReiter 生成**

对三个新 run 执行：

```powershell
py -m jewelry_on_hand.cli generate --run-root <run-root> --helper-script skills\aireiter-image-generation\scripts\aireiter_image_helper.py
```

等待每个任务达到 `completed` 并下载 `result.png`；失败时保留任务 ID，按 AIReiter 技能的单次 imagegen 兜底规则处理。

- [ ] **步骤 6：验证送模身份审计副本**

对每个 run 比较：

```powershell
Get-FileHash <run>\input\product-on-hand.jpg
Get-FileHash <run>\generation\01\product-identity.jpg
```

预期：SHA-256 完全一致；`product-detail.*` 的 SHA-256 与审计身份图不同且未出现在 `submit.json` 的输入列表中。

- [ ] **步骤 7：逐图执行严格 QC**

每个结果必须完整写入 5 条 `fidelity_checks` 和 18 条 `checklist_checks`；数量、手侧、食指根部、结构、接触、手指畸变、来源手迁移和水印均通过才能标记 `pass`。任何 `critical_failures` 必须按现有重试矩阵处理，不得直接交付。

- [ ] **步骤 8：验证 Prompt、QC 与 run 完整性**

对每个 run 运行：

```powershell
py skills\jewelry-on-hand-workflow\scripts\validate_prompt_contract.py <run>\generation\01\prompt.txt
py skills\jewelry-on-hand-workflow\scripts\validate_qc_record.py <run>\generation\01\qc.json
py skills\jewelry-on-hand-workflow\scripts\inspect_run_artifacts.py <run>
```

预期：三类检查均通过。

- [ ] **步骤 9：整理最终交付和验证报告**

只把 QC 为 `pass` 的结果复制到：

```text
output/ring-feishu-test/2026-07-15/final-on-hand-identity/
```

`verification.json` 必须记录 SKU、run、模型、任务 ID、参考 Rank、产品上手图 SHA-256、审计身份图 SHA-256、细节图未送模证明、Prompt 字数和 QC 结果。

- [ ] **步骤 10：运行最终 scoped 检查并提交代码/文档**

运行：

```powershell
git diff --check -- src/jewelry_on_hand/generation.py tests/test_generation.py tests/test_cli.py tests/test_skill_portability.py reference/manual-workflow.md reference/superpowers/plans/2026-07-14-ring-input-retry-hardening.md skills/jewelry-on-hand-workflow/SKILL.md skills/jewelry-on-hand-workflow/references/workflow.md
```

预期：退出码 0。若任务 1 和任务 3 已分别提交，本步骤不重复提交；只提交仍未提交的本计划或验证文档，不提交 `output/` 测试产物。
