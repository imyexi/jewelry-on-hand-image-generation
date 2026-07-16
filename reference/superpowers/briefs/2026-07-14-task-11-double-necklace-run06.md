# Task 11 普通项链双圈真人佩戴 run 06 Brief

## 目标

建立全新 `run-20260714-double-necklace-06`。保持 run 05 已验证有效的人物参考策略、原始产品分析与五项结构 canonical，只新增一个产品保真变量：把浅海蓝主体微珠的颗粒形态、尺度、密度、纹理和透明反光提升为第六个 `must_keep`。全部门禁通过后，只提交一次 `gpt_image_2 / 3:4 / 2K`，下载原图并严格 QC。

历史 run 03、04、05 必须原样保留。run 05 的五项结构关系通过，但因浅海蓝微珠从细小密集近圆/细切面漂移为更大规则椭圆/桶珠而正式 QC `reject`。

## 单变量假设

rank 2 已解决可识别的产品源人物局部迁移，且五项结构关系可辨认；当前唯一决定性缺陷是主体浅海蓝微珠的几何和质感漂移。

run 06 只改变 canonical/Prompt 中这一项产品细节，不新增人体、服装、背景或内容策略相关文案，不改变参考图、产品分析、输出模式或模型。

## 固定输入

- run ID：`run-20260714-double-necklace-06`
- 输出根：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- 产品分析：逐字复制 run 03 `analysis/product_analysis.json`，不得修改任何字段
- 基础 canonical：run 03 的五项 constraints
- 人物参考：只有正式 scorer 的 rank 2 仍为 `微信图片_20260519175542_452_1.png`、score 228 时才继续

## 六项 canonical

从 run 03 canonical 派生一个与同一规范化 analysis SHA-256 绑定的新 constraints 文件，保留原五项并新增：

### `浅海蓝微珠颗粒形态与尺度`

- `source_text`：产品源双圈主体由细小、密集、近圆形或细小切面的浅海蓝半透明微珠连续串成。
- `location`：上下两圈除红橙渐变区和唯一大红圆珠之外的浅海蓝主体线路。
- `visual_shape`：颗粒细小密集，近圆或细小切面，保持半透明与细碎反光；不得变成长椭圆、米珠、桶珠、管珠或粗链节。
- `relationship`：浅海蓝微珠沿双圈主线保持原有相对尺度、密度、间距与统一颗粒感；唯一大红圆珠继续是全链唯一明显大颗粒。
- `forbid` 至少包含：整体放大浅蓝微珠、拉长为椭圆/米珠、改成桶珠/管珠、降低颗粒密度或扩大间距、改成金属链节、把半透明细碎反光改成不透明塑料感。
- `qc_question`：浅海蓝主体微珠是否仍保持细小密集、近圆或细小切面的半透明颗粒形态，而没有放大或变成椭圆、米珠、桶珠、管珠或粗链节

最终 `must_keep.name` 必须精确为原五项加上述第六项；不得出现 `must_keep=吊坠`。`review_status` 应体现这是人工纠正/补强后的 canonical，不得伪称默认自动识别。

## 四阶段流程与 submit 前硬门禁

1. 正式 CLI `prepare-review`，不指定 `output_role`；rank 2 文件、score、源/review 摘要必须正确。
2. `record-decision` 使用 `generate_selected`、只选 rank 2，并通过 `--fidelity-constraints-path` 导入六项 canonical。
3. 最终 snapshot 必须为 `necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`。
4. submit 前脚本必须保存并验证：
   - analysis 原始/规范化摘要与 run 03 相同；
   - canonical 绑定最终 analysis，六项 name 精确匹配；
   - 新增第六项的 location/shape/relationship/forbid/question 全部存在且无吊坠互斥；
   - Prompt 有 `主吊坠：无`，没有要求保留吊坠结构；
   - Prompt 明确“细小密集、近圆或细小切面、半透明”，并明确禁止椭圆/米珠/桶珠/管珠/粗链节；
   - Prompt 没有 run 04 的人体纠偏文案，没有 `输出用途：` 行；
   - `validate_prompt_contract.py` 退出 0；
   - generation 根为空，无 submit/task ID。

## 唯一真实生成与 QC

- 只执行一次正式 CLI `generate`，固定 `gpt_image_2 / 3:4 / 2K`。
- 保存 submit/wait/query、任务 ID、平台 ID、credits、result JSON 和原始图片。
- 平台失败时不重复提交；原生 imagegen 在本会话不可用，记录后停止。
- completed 后必须三图对照产品源、rank2、原始结果，并对六项 fidelity 与完整 runtime checklist 逐项写 QC。
- 浅海蓝微珠只有在细小密集、近圆/细切面、半透明、间距和视觉粗细与产品源一致时才可通过；再次出现椭圆/桶珠化必须 reject。
- 人物来源使用谨慎表述：只判断是否存在可识别的产品源人物局部迁移，以及整体是否更接近 rank2，不宣称每个像素来源。
- 任一产品细节、结构、人物迁移、补链或穿模失败均不得 pass；reject/rerun 后停止，不得第二次提交。

## 审计与报告

在任务开始、submit 前、三份报告完成后分别保存带采集时间的 Git status、diff stat 和同一关键路径集 SHA-256 manifest；结束快照可由控制器采集，但必须准确标注采集者与时点。不得先在报告引用尚不存在的文件。

保存三项 validator 的原始 stdout/stderr/退出码：

- Prompt validator
- QC validator
- run inspector

全文修订：

- `reference/superpowers/reports/2026-07-14-task-11-double-necklace-run06-report.md`
- `.superpowers/sdd/task-11-report.md`
- `.superpowers/sdd/task-11-double-necklace-report.md`

不得修改生产代码、测试、SPEC、Plan 或历史 run；不得处理并发 HERO 文件；不暂存、不提交。

## 返回契约

返回 `DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT` 或 `BLOCKED`，包含 run 路径、唯一 out/platform task ID、credits、QC、六项 canonical gate、三 validator、是否第二次提交、Git/hash 审计和关注项。
