# Task 11 普通项链双圈真人佩戴 run 07 Brief

## 目标

建立全新 `run-20260714-double-necklace-07`，对 run06 的平台上游 `TIMEOUT` 做一次且仅一次最小重试验证。逐字复用 run06 最终 analysis、六项 canonical、rank2 与最终 Prompt，不改变视觉假设、模型、参考图或产品图。

run07 不是对 run06 的覆盖或继续查询。run06 保持 `failed / TIMEOUT` 原样；run07 必须有新的 run、out task ID、平台 task ID 与独立审计。若 run07 再次失败或成图仍有微珠漂移，保留证据并停止，不继续提交。

## 已知根因边界

先完整阅读：

- `reference/superpowers/reports/2026-07-14-task-11-double-necklace-timeout-analysis.md`
- `.superpowers/sdd/task11-double-necklace-run06-review.md`

run06 的本地门禁、submit、任务 ID 传递、UTF-8 JSON 协议与终态落盘均有效；平台返回 `failed / TIMEOUT`。现有证据不能证明是瞬时平台容量，也不能证明第六项 Prompt 必然导致超时。因此 run07 不修改代码、不缩短 Prompt、不换模型，只用同一输入做单次验证。

## 固定输入

- run ID：`run-20260714-double-necklace-07`
- 输出根：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- 产品分析：逐字复制 run06 `analysis/product_analysis.json`，SHA-256 必须为 `6E0FDEFA1CDE11954117D182FA6A5B6542B1C29685A4986AFD94665B194FE9C7`
- canonical：逐字复制 run06 `analysis/product_fidelity_constraints.json`，SHA-256 必须为 `0891A8852FE80752CB673A935DD3E6A96BF03362CF43AA50BA6999696BF1634B`
- 人物参考：正式 scorer 的 rank2 必须仍为 `微信图片_20260519175542_452_1.png`、score 228
- 最终 Prompt：必须与 run06 `generation/01/prompt.txt` 逐字相同，SHA-256 必须为 `04D82EE3B39E19AFBCE1B15B06F04E27E18ABE82A154D17FF5888C6337604D3D`

不得清理 run06 Prompt 中已审查记录的重复标点，因为这会改变单变量验证。

## 脱敏 helper 参数证据

run06 没有保存脱敏出站请求 payload，无法独立证实平台实际 `3:4 / 2K` 参数。run07 必须在 `output/.../necklace-worn-double/_audit/` 创建一个仅用于本次证据采集的透明 Python helper 包装器，不修改生产 helper：

1. 包装器接收 `generation.py` 传入的完整 helper argv。
2. 仅在子命令为 `submit` 时，从实际 argv 提取并原子写入 `run07-helper-submit-parameters.json`：采集时间、`model`、`aspect_ratio`、`resolution`、`task_id`、图片参数数量、Prompt UTF-8 SHA-256 与字符数、真实 helper 路径和包装器 SHA-256。
3. 不写 API key、环境变量值、完整 Prompt、图片 base64 或其他秘密。
4. 记录完成后，以相同 Python 解释器、`-X utf8`、相同 argv 原样调用 `skills/aireiter-image-generation/scripts/aireiter_image_helper.py`；stdout、stderr 和退出码原样透传。
5. `wait` 也原样透传，但不得覆盖 submit 参数证据。
6. 提交前用 `py_compile` 与无网络的 `--help` 透传验证包装器；`--help` 不得创建 submit 参数文件。
7. 包装器和参数 JSON 都属于测试过程，只能放在 `output/`，不得进入 `src/` 或 `skills/`。

参数 JSON 只证明传给正式 helper 的实际子进程参数；报告不得把它夸大为平台服务端回显。结合生产 helper 的既有参数到 payload 映射，可以闭合本地出站侧证据。

## 四阶段流程与提交前门禁

1. 在 run07 创建前保存 task-start Git status、diff stat 和固定路径集 `run07-fixed-v1` SHA-256 manifest；路径集要覆盖产品/分类、run03-06 历史关键文件、run06 报告、run07 输入/关键产物、透明包装器、参数 JSON 和三份将修订的报告。
2. 正式 CLI `prepare-review` 不指定 `output_role`，使用逐字复制的 run06 analysis；rank2 文件、score、源/review 摘要必须正确。
3. `record-decision` 使用 `generate_selected`、只选 rank2，并导入逐字复制的 run06 六项 canonical。相对路径若按现有规则解析失败，只可改用同一文件的绝对路径做一次最小本地重试；这不属于模型 submit。
4. 最终 snapshot 必须为 `necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`，decision 不得有 `output_role`。
5. submit 前保存并验证：
   - analysis 与 run06 原始/规范化摘要一致；
   - canonical 与 run06 字节级相同，六项 name 和所有字段一致，`review_status=corrected`，无 `must_keep=吊坠`；
   - Prompt 与 run06 正式 Prompt 字节级相同；
   - Prompt 有 `主吊坠：无`、微珠正向和禁止项，无人体纠偏、无 `输出用途：` 行；
   - `validate_prompt_contract.py` 退出 0；
   - generation 根为空，无 submit/task ID；
   - helper 包装器 `py_compile`、`--help` 通过，参数 JSON 尚不存在；
   - task-start 与 pre-submit 使用同一 `run07-fixed-v1` 路径集合，历史 run03-06 摘要未变。

所有门禁通过前不得 submit。

## 唯一真实生成

- 只执行一次正式 CLI `generate`，把透明包装器作为 `--helper-script`；模型目标为 `gpt_image_2`，实际 helper argv 必须记录 `gpt_image_2 / 3:4 / 2K`。
- 正式 generate 调用前保存带时间的 invocation 与 submit authorization；调用后不得再次 generate/submit。
- 保存 submit、内建 wait 的终态、out task ID、平台 task ID、`credits_used`、output URL、原始图片和包装器参数证据。
- 若平台失败：不重复 submit，不额外 query，不切换模型，不使用 imagegen fallback；保存失败证据和三项 validator 后停止。
- 若 completed：必须由同一次 CLI 下载原始 `result.png`，不得截图或转码替代。

## completed 后严格 QC

只有 completed 且存在原始 `result.png` 时才执行三图对照：

1. 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
2. 人物参考：run07 rank2 review 副本
3. 原始成图：run07 `generation/01/result.png`

QC 必须逐项写完整 runtime checklist 与六项 fidelity：

1. 同一条连续长链双圈关系
2. 上短下长层间落差
3. 红橙色连续渐变区
4. 唯一大红圆珠串接关系
5. 不可见扣头不补造
6. 浅海蓝微珠颗粒形态与尺度

第六项只有在细小密集、近圆或细小切面、半透明、细碎反光、相对尺度/密度/间距与产品源一致时才通过。再次出现长椭圆、米珠、桶珠、管珠、粗链节、整体放大、密度下降或塑料感，必须 `reject`。人物来源只谨慎判断是否存在可识别的产品源人物局部迁移，以及整体是否更接近 rank2。

任何产品细节、结构、人物迁移、补链或穿模失败均不得 `pass`。`reject` 或 `rerun` 后也停止，不得第二次提交。

## validators、审计与报告

保存三项 validator 的原始 stdout、stderr 和退出码：

- Prompt validator
- QC validator
- run inspector

报告完成后保存 task-end Git status、diff stat 和同一 `run07-fixed-v1` manifest，准确标注采集者与时间；不得引用不存在的 contemporaneous checkpoint。若来不及在 submit 后立即采集 checkpoint，报告只能说“留存证据未显示第二次提交”，不能绝对断言。

全文修订：

- `reference/superpowers/reports/2026-07-14-task-11-double-necklace-run07-report.md`
- `.superpowers/sdd/task-11-report.md`
- `.superpowers/sdd/task-11-double-necklace-report.md`

不得修改生产代码、测试、SPEC、Plan、历史 run 或并发 HERO/戒指文件；不得暂存或提交。

## 返回契约

返回 `DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT` 或 `BLOCKED`，包含 run 路径、唯一 out/platform task ID、credits、QC、六项 fidelity、三 validator、包装器参数证据、是否存在第二次提交、Git/hash 审计和所有关注项。
