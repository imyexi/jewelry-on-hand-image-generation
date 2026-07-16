# Task 11 普通项链双圈真人佩戴第二轮复跑报告

## 最终状态

**DONE_WITH_CONCERNS**

新 run `run-20260713-double-necklace-04` 已按 `prepare-review -> record-decision -> generate` 执行，并且只提交了一次真实 `gpt_image_2 / 3:4 / 2K` 任务。事后独立审查确认，该 run 在提交前已经存在阻断性规格缺陷：自动 canonical 把产品描述中的否定句“不是悬挂吊坠”误识别成必须保留的“吊坠”，正式 Prompt 同时要求“主吊坠：无”与保留吊坠结构。故 run 04 不是一轮规格有效的 rank 2 产品保真假设验证。平台随后又以 `CONTENT_POLICY_BLOCKED` 拒绝任务，没有输出 URL、原始 2K 图片或 `credits_used`，因此无法进入基于原图的人工 QC，也没有调用 `qc` CLI。普通项链双层真人佩戴仍不计入成功矩阵。

历史 `run-20260713-double-necklace-03` 的当前内容仍显示：任务为 `completed`，五项产品结构通过，但因 `source_person_region_migrated` 被严格 QC `reject`。任务执行时缺少 brief 要求的结束 Git 快照和 run 03 前后 hash manifest，因此“本轮未修改历史产物”只能由现有旁证与事后摘要支持，不能作完整 contemporaneous 审计证明。

## 输入与边界

- 输出根：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/`
- 新 run：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/run-20260713-double-necklace-04`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品源 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- 新分析输入：`_inputs/necklace-worn-double-analysis-rerun-04.json`
- 新分析输入 SHA-256：`594F4C91D99F3A9398E5D6CE5E898D6C044DBEE8D2FD87DAA14D63E153E79AA1`

新分析输入从 run 03 最终 `product_analysis.json` 复制。自动比较确认属性集合一致，除 `composition` 与 `special_requirements` 外没有字段变化；analysis 仍明确 `necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`。但是后续 canonical 构建错误地从否定句识别出吊坠，因此“输入身份未变”不等于 run 04 的约束和 Prompt 仍保持五项结构。

## 四阶段执行

### 1. prepare-review

正式命令使用产品源、新分析输入、固定 run ID 和 output-only 分类快照，退出码为 `0`。scorer 重新生成的合法 Top 3 为：

| rank | 文件 | score | SHA-256 |
| ---: | --- | ---: | --- |
| 1 | `微信图片_20260515152026_434_1.jpg` | 228 | `C00439B84C878F1585FABC7697B2DE9F44E9B8F42B3295D166C0B5E00FECAC4D` |
| 2 | `微信图片_20260519175542_452_1.png` | 228 | `99D8B5F7119C2DA519D5488D5293A472408BB4AE8B9A8E5F01B12AF6D664DD7C` |
| 3 | `微信图片_20260520114417_523_1.jpg` | 223 | `DA380D577ED169B9685A1BFEFCF0FF0F6FB47DC3891858D73E4E76CFAE6976A3` |

rank 2 仍精确对应 452 图，源图与 run 内 review 副本摘要一致，满足继续条件。run 内没有 `analysis/output_role.json`。

### 2. record-decision

正式决策退出码为 `0`，内容为：

- `action=generate_selected`
- `selected_ranks=[2]`
- `fidelity_confirmed=true`
- 未指定、未追加 `output_role`
- confirmation snapshot 的结构化产品字段与最终 analysis 一致，但这不证明错误 canonical 有效

confirmation snapshot 与 analysis 的结构化字段一致，但实际 `product_fidelity_constraints.json` 没有保持 brief 的五项 canonical。它的 `detected_keywords=["吊坠"]`、唯一 `must_keep.name="吊坠"`，来源正是“不是悬挂吊坠”的否定句；文件同时被标记为 `needs_user_review=true`、`review_status=confirmed`。这是一份被错误确认的 canonical，不能作为有效保真约束。

### 3. generate

生成前使用 CLI 生成阶段相同代码路径重建 Prompt。第一次审计命令因 PowerShell 剥离 `python -c` 内部引号失败；第二次构建成功但 PowerShell `>` 将 stdout 编码为 UTF-16，validator 无法按 UTF-8 读取。定位根因后没有修改生产代码或 validator，而是在 `output/` 中使用只读预构建脚本和原生进程重定向生成 UTF-8 Prompt。

最终生成前机械证据：

- Prompt SHA-256：`E9C5BF10AB57F2895058A380B5C9891F4A5890AB3C17A3170F1413D5F6D0568E`
- `输出用途：` 行计数：`0`
- 预生成 `validate_prompt_contract.py`：退出码 `0`，但校验器没有识别下述产品语义冲突
- CLI 实际写入的 `generation/01/prompt.txt` 摘要与预构建 Prompt 完全一致
- `generation/01/model.txt`：`gpt_image_2`

同一正式 Prompt 第 34 行写“主吊坠：无；不得凭空添加吊坠或吊坠连接结构”，第 36 行却要求保留“吊坠结构”且禁止删除垂坠，第 39 行又要求保持“吊坠所属层、位置、朝向和肉眼可见连接关系”。这些指令与 `has_pendant=false` 直接冲突。validator `0` 只能证明八层格式和现有机械规则通过，不能证明 Prompt 符合 Task 11 canonical。按照 brief 的“发现代码问题即停止”，正确行为应是在 submit 前停止；实际提交不构成干净、规格有效的 rank 2 proof。

一次本地保护检查因 `prepare-review` 预建空 `generation/` 根目录而在 CLI 启动前停止。检查确认目录项、`submit.json` 和 `model.txt` 均为 0，因此不构成 generate 或平台提交。

唯一一次正式 generate 的真实提交结果如下；它保留任务追踪价值，但因提交前 Prompt 已失效，不能作为产品保真假设的有效检验：

| 项目 | 值 |
| --- | --- |
| out task ID | `run-20260713-double-necklace-04-rank-02-167d574c` |
| 平台 task ID | `order_mHCf3a1mSOO0Sr4REDlBK` |
| 模型 | `gpt_image_2` |
| 画幅 / 分辨率 | `3:4 / 2K` |
| submit | `statusCode=200`, `status=pending` |
| estimated credits | `2.5` |
| terminal status | `failed` |
| terminal error | `CONTENT_POLICY_BLOCKED` |
| credits_used | 平台未返回 |
| output URL | 无 |

CLI 在 wait 阶段先出现本地 UTF-8 解码故障：`generation.py` 的父进程按系统 GBK 解码 helper 的 UTF-8 stdout，触发 `UnicodeDecodeError`，正式 generate 退出码为 `1`。根据 troubleshooting，没有重新提交，而是从已保存的 `submit.json` 使用同一 out task ID 直接 query。恢复查询退出码为 `0`，取得上述真实 terminal JSON；该 JSON 原样保存为 `generation/01/result.json` 与 `generation/01/query-terminal.json`，三份文件 SHA-256 均为 `96322ABE1C7473540A59475849A67AE1817ABDC9ADF1ED99756DDCEB6BA5968E`。

### 4. qc

平台 failed 且没有 `data.output[].url`，所以不存在可下载的 `result.png`。严格人工 QC 必须查看下载后的原始 2K 图片，本轮没有该前提，故 QC 状态为“未执行”，而不是 `pass`、`rerun` 或 `reject`；没有伪造 `qc.json`，也没有调用 `qc` CLI。

AIReiter 技能要求的 imagegen fallback 已由控制器核验：本会话没有可调用的原生 `image_gen`，只有与任务无关的 Canva 图转设计能力。按技能失败规则立即停止兜底，没有使用其他 CLI/API 替代。

## 最终验证器

三项命令均对 run 04 新鲜执行并保存 stdout、stderr 和退出码。Prompt validator 的 `0` 仅是机械契约结果，不抵消 canonical/Prompt 自相矛盾：

| 验证器 | 退出码 | 原始结论 |
| --- | ---: | --- |
| `validate_prompt_contract.py` | `0` | 原始输出为“Prompt 契约校验通过”，仅代表机械规则；未识别无吊坠/保留吊坠冲突 |
| `validate_qc_record.py` | `2` | 找不到 `generation/01/qc.json` |
| `inspect_run_artifacts.py` | `1` | 缺少 `result.png`、缺少 `qc.json`、`result.json` status 不是 completed |

非零退出是平台失败后的真实不完整状态，不得通过伪造原图或 QC 记录消除；Prompt validator 为 0 也不得被解释为规格符合。

## Credits 与矩阵

submit 只返回 `estimated_credits=2.5`，terminal JSON 没有 `credits_used`。本报告不把估算值当成已确认消耗，也不增加 Task 11 的累计确认 credits。

普通项链双层真人佩戴当前有两份互相独立且都保留的真实证据：

1. run 03：`completed / 2.5 credits / QC reject(source_person_region_migrated)`。
2. run 04：提交前 canonical/Prompt 已自相矛盾，随后 `failed(CONTENT_POLICY_BLOCKED) / credits_used 未返回 / QC 未执行`。

两次都不计成功，矩阵仍未通过。

## Git 与并发边界

- 起始 `git status --short` 与 `git diff --stat` 已保存到 `_audit/git-start-status-04.txt` 和 `_audit/git-start-diff-stat-04.txt`。
- 当时没有保存 brief 要求的结束 Git 快照，也没有在任务开始/结束分别保存 run 03/run 04 同一套关键文件 hash manifest；这一历史缺口不能补造。
- 审查阶段于 `2026-07-13T23:48:00+08:00` 新增 `_audit/late-review-git-status-04.txt`、`_audit/late-review-git-diff-stat-04.txt` 和 `_audit/late-review-run-hash-manifest-04.txt`。三者明确标注 `late-review`，只证明采集时当前状态，不能替代 contemporaneous end snapshot 或前后摘要。
- 当前旁证支持没有覆盖 run 03、生产代码、测试、操作手册、SPEC 或 Plan，但受上述审计缺口限制，不能表述为完整可复核证明。
- 没有处理、暂存或提交并发 HERO 107/108 戒指失败文件。
- 没有暂存、提交、推送或创建 PR。

## 返回契约

- 状态：`DONE_WITH_CONCERNS`
- 新 run：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/run-20260713-double-necklace-04`
- 唯一 out task ID：`run-20260713-double-necklace-04-rank-02-167d574c`
- 平台 task ID：`order_mHCf3a1mSOO0Sr4REDlBK`
- credits：`estimated_credits=2.5`；`credits_used` 未返回、不计入累计
- QC：未执行，原因是平台 failed 且无原图
- 验证器：`0 / 2 / 1`
- 第二次生成：否
- Prompt gate：无 `output_role`、`输出用途：` 行计数为 0、机械 validator 为 0；但 canonical/Prompt 吊坠冲突使规格 gate 实际失败
- 关注项：run 04 proof 在 submit 前已失效；平台内容审核失败；CLI wait 存在 GBK/UTF-8 解码故障；原生 imagegen fallback 不可用；缺少 contemporaneous 结束 Git 快照；矩阵仍未通过
