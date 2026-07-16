# Task 11 普通项链双圈真人佩戴 run 05 执行报告

## 结论

**DONE_WITH_CONCERNS**

`run-20260713-double-necklace-05` 按 brief 完成了唯一一次真实 `gpt_image_2 / 3:4 / 2K` 生成，平台终态为 `completed`，原始 2K 图已下载，实际消耗 2.5 credits；流程门禁、任务身份、五项 canonical、无吊坠互斥、无 `output_role`、无第二次提交和三项 validator 均有效。

独立三图审查推翻了原来的无保留 `QC pass`：产品源中的浅海蓝微珠是细小、密集、接近圆形或细小切面的透明微珠，成图却普遍变成更大、更规则的椭圆/桶珠状颗粒，尺度、间距、视觉粗细、纹理及透明反光明显漂移。正式 QC CLI 已把 `qc.json` 重判为 `reject`。五项结构性 fidelity checks 仍全部通过，但 24 项 runtime checklist 中产品外观保真项失败，因此 run05 不能作为成功矩阵 proof。

本任务和本次审查修复均没有第二次 submit/generate，没有 imagegen fallback，没有修改生产代码、测试、SPEC、Plan、run03 或 run04，也没有暂存或提交 Git 变更。

## 固定输入与复制门禁

- run：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/run-20260713-double-necklace-05`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- run05 输入：`_inputs/necklace-worn-double-analysis-rerun-05.json`

run03 `analysis/product_analysis.json` 被逐字复制到 run05 输入；源、复制输入与 run05 最终 analysis 的原始 SHA-256 均为 `6E0FDEFA1CDE11954117D182FA6A5B6542B1C29685A4986AFD94665B194FE9C7`。三者字节和 JSON 内容一致，规范化 `ProductAnalysis` SHA-256 均为 `A3A4DA5C7BF1ED9138AA584372E27606312F1024DEA62FC0FBA2463E64EAB302`。run03 canonical 的绑定摘要与该规范化摘要一致。

## prepare-review 与 decision

正式 `prepare-review` 不带 `output_role`，退出码 0。scorer 重新生成的 Top 3 为：

| rank | 文件 | score |
| ---: | --- | ---: |
| 1 | `微信图片_20260515152026_434_1.jpg` | 228 |
| 2 | `微信图片_20260519175542_452_1.png` | 228 |
| 3 | `微信图片_20260520114417_523_1.jpg` | 223 |

rank2 源图、review 副本及 selected metadata 的 SHA-256 均为 `99D8B5F7119C2DA519D5488D5293A472408BB4AE8B9A8E5F01B12AF6D664DD7C`。rank、分数、图片和 metadata 均由正式 scorer 产生，未手改。

最终 decision 为 `generate_selected`、`selected_ranks=[2]`、`fidelity_confirmed=true`，且没有 `output_role`。前两次调用分别因相对 canonical 路径解析和冗余分析覆盖导致的摘要不一致而在写入前失败；最终最小调用只传 action、rank、fidelity 和 run03 canonical 绝对路径，退出码 0，analysis 未改变，decision 原子写入成功。

confirmation snapshot 为：

`necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`

## canonical 与 submit 前硬门禁

run05 canonical 与 run03 canonical 字节完全一致，SHA-256 均为 `05E219EA32A807E601EF4135A36B823C625E9DC309C65280C49A220B310C6ACC`。`must_keep.name` 精确为以下五项闭集：

1. `同一条连续长链双圈关系`
2. `上短下长层间落差`
3. `红橙色连续渐变区`
4. `唯一大红圆珠串接关系`
5. `不可见扣头不补造`

硬门禁确认：`analysis/output_role.json` 不存在；decision `output_role=None`；canonical analysis 摘要匹配；不存在 `must_keep=吊坠`；Prompt 包含 `主吊坠：无`，不含要求保留吊坠、吊坠所属层或连接关系的互斥 canonical；不含 run04 人体纠偏文案；不含 `输出用途：` 行；`generation/` 在 submit 前为空；没有 submit JSON 或任务 ID。

预构建 Prompt 与 CLI 实际 `generation/01/prompt.txt` SHA-256 均为 `85405018A009DDF178DA6068DE2EA8640E109ACD14FA3D4D5A90BD31DD9E6147`。submit 前即时 `validate_prompt_contract.py` 退出码为 0。

## 唯一真实生成

| 项目 | 值 |
| --- | --- |
| generate 调用次数 | `1` |
| 模型 / 画幅 / 分辨率 | `gpt_image_2 / 3:4 / 2K` |
| out task ID | `run-20260713-double-necklace-05-rank-02-17c34100` |
| 平台 task ID | `order_xJbGPl6Tj1Hb1wse-iRs2` |
| submit | `statusCode=200 / pending / estimated_credits=2.5` |
| terminal | `completed` |
| credits_used | `2.5` |
| 原图 | `1536x2048 / 4,853,302 bytes` |
| 原图 SHA-256 | `A82F55742A3798AE4092832D1B676B78EA3D7D50059FFDB0F8DF3AF54EE55885` |
| 第二次提交 | `否` |

正式 CLI 的 submit/wait 子命令均带 `python -X utf8`，父进程以 bytes 捕获并严格 UTF-8 解码。终态后以同一 out task ID 独立 query；result 与 query 的 out task ID、平台 task ID、`completed`、2.5 credits 和 output URL 一致。

## 原始 2K QC 重判

正式 `qc.json` 当前状态为 `reject`。24 项 runtime checklist 完整保留，其中 23 项 `pass`、1 项 `fail`；5 项结构性 fidelity checks 均为 `pass`，没有伪造或填入不适用的 `critical_failures`。

失败项为 `qc-93ccd7c67a68352a`：“产品颜色、材质、透明度、纹理、反光和比例与产品图一致”。三图证据显示浅海蓝主体微珠由细小、密集、近圆或细切面透明微珠变成更大、更规则的椭圆/桶珠，尺度、间距、视觉粗细、纹理和透明反光漂移，直接违反产品整体微珠尺度与质感不得变化的边界。

仍可确认通过的内容：

- 两圈完整、相互分离，保持上短下长和清楚落差；没有第三圈、重组或自动补链。
- 红橙渐变区连续可见；下层正面偏左仍只有一颗大红圆珠并沿主线路串接。
- 后颈扣头继续不可见，没有补造、推断或特写；未见严重穿肤、穿衣或穿发。
- rank2 原有吊坠、手链、戒指、文字和水印均已移除。
- 未发现可识别的产品源人物、颈部、胸部、皮肤、白色无袖衣物、头发或户外绿色背景局部迁移；整体人物、米色针织服装和手势更接近 rank2。三图目视不能证明每个人物局部“均来自”某一参考。

五项结构性 canonical 可辨认不能抵消主体微珠外观保真失败，因此整体必须保持 `reject`，普通项链双层真人佩戴成功矩阵仍未通过。

## Validators 与审计

QC 重判后新鲜验证结果为：

| 验证器 | 退出码 | stdout | stderr |
| --- | ---: | --- | --- |
| `validate_prompt_contract.py` | 0 | `Prompt 契约校验通过` | 空 |
| `validate_qc_record.py` | 0 | `qc 记录校验通过` | 空 |
| `inspect_run_artifacts.py` | 0 | `run 产物检查通过` | 空 |

validator 0 只证明 Prompt、QC 记录和 run 产物契约完整，不进行像素级语义审查，也不把 `reject` 变成 `pass`。实际带退出码的 CLI、helper 和 validator 步骤均保存了 stdout/stderr/退出码；Git 快照只保存时间、命令和输出，controller-end 文件本身没有 `exit_code` 字段。

原始 start 为 `2026-07-14T00:02:13.4416046+08:00`，pre-submit 为 `2026-07-14T00:11:35.5631647+08:00`。原 controller-end 采集时间为 `2026-07-14T00:33:57.8127471+08:00`，标签明确是原报告完成后的 task-end；它不是生成终态或 validator 完成瞬间，也不是 late-review。独立审查修复后另存带新采集时间的 `_audit/task-end-hash-manifest-05-review-fix.txt`，用于记录新的 QC 和三份报告摘要，不覆盖或冒充 00:33:57 旧快照。

## 历史边界与最终状态

- run03 继续保持 `completed / 2.5 credits / QC reject / source_person_region_migrated`。
- run04 继续保持错误 `must_keep=吊坠`、互斥 Prompt、平台 `CONTENT_POLICY_BLOCKED`、无原图、无 QC。
- run05 继续保持唯一任务 `completed / 2.5 credits`，但 QC 已重判为 `reject`，不能计入成功矩阵。
- 三个 run 均未提供普通项链双层真人佩戴成功 proof；该场景和 Task 11 总矩阵保持 `DONE_WITH_CONCERNS`。
