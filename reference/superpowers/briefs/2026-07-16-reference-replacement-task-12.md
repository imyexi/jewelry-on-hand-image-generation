# 参考底图替换工作流：任务 12 集成回归与不回写验证

本 brief 从权威实施计划逐字提取任务 12；只执行未被外部安全边界阻断的步骤。

### 任务 12：完成集成回归与 QY018/QY027 不回写对照验证

**文件：**
- 创建：`reference/superpowers/reports/2026-07-14-jewelry-reference-replacement-verification.md`
- 创建：`output/reference-replacement-workflow/2026-07-14/pytest-targeted.txt`
- 创建：`output/reference-replacement-workflow/2026-07-14/pytest-full.txt`
- 创建：`output/reference-replacement-workflow/2026-07-14/pytest-comparison.md`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY018-hand_worn/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY018-lifestyle/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY027-hand_worn/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY027-lifestyle/`
- 创建：`output/reference-replacement-workflow/2026-07-14/cross-category/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/manual-qc.json`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/verification-report.json`

**接口：**
- Consumes：任务 1-11 完整实现、当前飞书参考源只读数据、现有 QY018/QY027 产品图和 analysis。
- Produces：无新增生产接口；提供自动化回归证据和 4 个不回写真实 run 的人工 QC 证据。
- 外部边界：本任务可以读取飞书参考源；真正提交 AIReiter 前必须再次向用户确认计费生成，且无论结果如何都不得回写飞书。

- [ ] **步骤 1：运行全部定向测试并保存原始输出**

```powershell
python -m pytest tests/test_output_role_compatibility.py `
  tests/test_reference_composition.py tests/test_scoring.py `
  tests/test_review_package.py tests/test_review_decision.py `
  tests/test_prompt_builder.py tests/test_generation.py tests/test_qc.py `
  tests/test_qc_review.py tests/test_cli.py tests/test_skill_portability.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/final-targeted `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-final-targeted `
  *> output/reference-replacement-workflow/2026-07-14/pytest-targeted.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

预期：退出 0，所有定向测试 PASS。

- [ ] **步骤 2：运行全量测试并对比已知基线**

```powershell
python -m pytest -v `
  --basetemp=output/reference-replacement-workflow/pytest/final-full `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-final-full `
  *> output/reference-replacement-workflow/2026-07-14/pytest-full.txt
```

预期：不得出现 6 个已知项链 v1/v2 兼容失败之外的新失败。如果已知失败已被当前工作区其他改动修复，记录更少失败是允许的；不能为了匹配数字恢复失败。`pytest-comparison.md` 逐项列出基线、最终结果、新增失败数（必须为 0）和 6 个历史测试名称。

- [ ] **步骤 3：为 QY018/QY027 建立四个新 review run，禁止复用旧决策**

```powershell
$proof = 'output/reference-replacement-workflow/2026-07-14/real-proof'
$source = 'output/021-20260717-three-role-type-gated-review-20260714-v6'
foreach ($sku in @('QY018', 'QY027')) {
  foreach ($role in @('hand_worn', 'lifestyle')) {
    python -m jewelry_on_hand.cli prepare-review `
      --product-image "$source/$sku-hand_worn/input/product-on-hand.jpg" `
      --analysis-json "$source/$sku-$role/analysis/product_analysis.json" `
      --output-root $proof `
      --run-id "$sku-$role" `
      --output-role $role `
      --reference-cache-root 'output/feishu_reference_cache'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
}
```

预期：四个 run 各有 Top 3、三份 candidate snapshot 与 review.html；不存在 hero run、review_decision 或 generation 目录内容。人工审核必须分别确认 QY018/QY027 的手部与生活场景构图明显不同，生活场景没有被改成腕部特写。

- [ ] **步骤 4：人工确认单一快照并记录决策**

审核者逐个打开四个 `review/review.html`，确认候选快照描述与参考图一致。任一描述不准确时，保留本轮 run 作为失败审计，停止任务 12 并回到任务 2/3 修正字段映射或硬 gate；不得删除旧 run、直接编辑候选 JSON或带错继续。四个页面都确认准确后执行以下交互式命令，人工输入各 run 唯一选择的 `1`、`2` 或 `3`：

```powershell
$proof = 'output/reference-replacement-workflow/2026-07-14/real-proof'
foreach ($name in @(
  'QY018-hand_worn',
  'QY018-lifestyle',
  'QY027-hand_worn',
  'QY027-lifestyle'
)) {
  $role = if ($name.EndsWith('-hand_worn')) { 'hand_worn' } else { 'lifestyle' }
  $rank = [int](Read-Host "$name 选择唯一 rank（1/2/3）")
  if ($rank -notin @(1, 2, 3)) { throw "$name 的 rank 必须是 1、2 或 3" }
  python -m jewelry_on_hand.cli record-decision `
    --run-root "$proof/$name" `
    --action generate_selected `
    --selected-ranks $rank `
    --output-role $role `
    --fidelity-confirmed `
    --reference-snapshot-confirmed
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

预期：decision、canonical、confirmed snapshot 的摘要一致；任何字段不一致都在写文件前失败。把选择 rank、参考编号、composition signature、确认人和确认时间写入 `verification-report.json`。

- [ ] **步骤 5：在获得用户计费确认后生成，未确认则停在可审计 review 状态**

确认后逐个运行：

```powershell
$proof = 'output/reference-replacement-workflow/2026-07-14/real-proof'
foreach ($name in @(
  'QY018-hand_worn',
  'QY018-lifestyle',
  'QY027-hand_worn',
  'QY027-lifestyle'
)) {
  python -m jewelry_on_hand.cli generate `
    --run-root "$proof/$name" `
    --helper-script skills/aireiter-image-generation/scripts/aireiter_image_helper.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

预期：每个 run 只有一个新 generation 目录，包含两张输入副本、快照、manifest、Prompt、模型任务记录、结果和四栏 QC 页面。此步骤不调用水印 Skill、不上传飞书、不删除旧附件。

- [ ] **步骤 6：逐项人工 QC 并写验证报告**

每张结果必须逐项填写 10 条 reference preservation、全部 must_keep 和 runtime checklist。`manual-qc.json` 至少记录：

```json
{
  "sku": "QY027",
  "output_role": "lifestyle",
  "reference_file": "RP000000.jpg",
  "reference_preservation": {
    "framing_preserved": true,
    "pose_preserved": true,
    "subject_placement_preserved": true,
    "person_preserved": true,
    "clothing_preserved": true,
    "background_preserved": true,
    "lighting_preserved": true,
    "source_jewelry_removed": true,
    "replacement_target_preserved": true,
    "single_target_product": true
  },
  "feishu_writeback": false
}
```

验收要求：QY018、QY027 的 4 张结果都保留各自参考构图；手部与生活图不收敛到同一种腕部特写；原首饰全部移除；目标产品只出现一次且结构保真。任一项失败时按 QC 路由记录 reject/rerun，不得把失败结果计入通过率。

- [ ] **步骤 7：在 QY 对照通过后做四品类第二批 review-only 验证**

QY018/QY027 的 4 张结果全部通过后，再用现有真实素材建立 6 个非手串 review-only run；加上 QY018/QY027，覆盖 `bracelet`、`necklace`、`pendant_necklace`、`ring` 各 2 个产品。执行：

```powershell
$root = 'output/reference-replacement-workflow/2026-07-14/cross-category'
$cases = @(
  @{
    Name='necklace-worn'; Role='lifestyle';
    Source='output/multi-category-validation/2026-07-11/real-proof/necklace-worn-single/run-20260711-222800'
  },
  @{
    Name='necklace-handheld'; Role='hand_worn';
    Source='output/multi-category-validation/2026-07-11/real-proof/necklace-handheld-single/run-20260712-final-handheld-01'
  },
  @{
    Name='pendant-worn'; Role='lifestyle';
    Source='output/multi-category-validation/2026-07-11/real-proof/pendant-worn-single/run-20260711-203407'
  },
  @{
    Name='pendant-handheld'; Role='hand_worn';
    Source='output/multi-category-validation/2026-07-11/real-proof/pendant-handheld-double/run-20260712-review-fix-01'
  },
  @{
    Name='ring-open'; Role='hand_worn';
    Source='output/ring-category-validation/2026-07-11/real-proof/open-ring/run-v2'
  },
  @{
    Name='ring-plain-band'; Role='hand_worn';
    Source='output/ring-category-validation/2026-07-11/real-proof/plain-band/run-v2'
  }
)
foreach ($case in $cases) {
  python -m jewelry_on_hand.cli prepare-review `
    --product-image "$($case.Source)/input/product-on-hand.jpg" `
    --analysis-json "$($case.Source)/analysis/product_analysis.json" `
    --output-root $root `
    --run-id $case.Name `
    --output-role $case.Role `
    --reference-cache-root 'output/feishu_reference_cache'
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

预期：6 个 run 都产生类型正确、硬 gate 合格且有三份快照的 Top 3；项链手持参考保留手指接触和垂落位置，项链/吊坠佩戴参考保留原景别，戒指参考目标手与指位一致。第二批只做 review、snapshot 和便携快照校验；四品类 Prompt 由任务 6 的真实 analysis/canonical 参数化测试覆盖。若要提交 6 张额外计费生成，必须取得单独授权，仍不得回写飞书。

- [ ] **步骤 8：运行最终产物检查与 diff 检查**

```powershell
Get-ChildItem 'output/reference-replacement-workflow/2026-07-14/real-proof' -Directory | `
  Where-Object { $_.Name -match '^QY0(18|27)-(hand_worn|lifestyle)$' } | `
  ForEach-Object {
    python skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py $_.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
git diff --check
git status --short
```

预期：所有已实际生成并 QC 的 run 检查通过；未获计费确认而没有 generation 的 run 在报告中标记 `review_only`，不伪报完成；`git diff --check` 退出 0；没有飞书写回产物。

- [ ] **步骤 9：写验证报告并提交（不提交大图与临时日志）**

在 `reference/superpowers/reports/2026-07-14-jewelry-reference-replacement-verification.md` 记录：定向测试命令与结果、全量基线/最终差异、四个 proof run 的 run-id/rank/参考编号/AIReiter 任务号、10 条参考保留检查结果、产品保真结论、失败与重跑记录、`feishu_writeback=false`。原始 pytest 输出、Prompt、manifest、QC JSON 和图片只保留在 `output/`，不要用 `git add -f` 提交。

```powershell
git add reference/superpowers/reports/2026-07-14-jewelry-reference-replacement-verification.md
git diff --cached --name-only
git commit -m "test: verify reference preserving jewelry workflow"
```

如果集成验证暴露实现缺陷，先回到对应任务补 RED/GREEN 和独立修复提交，再重新执行任务 12；不得把未解释的生产修复混入验证报告提交。

