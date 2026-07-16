# Task 11 普通项链双圈真人佩戴 run 07 执行报告

## 结论

**DONE_WITH_CONCERNS**

`run-20260714-double-necklace-07` 完成了对 run06 `TIMEOUT` 的一次且仅一次同输入模型生成验证，但 run07 **规格不完全符合**。run07 最终 analysis、六项 corrected canonical、正式 scorer 的 rank2、最终 Prompt 和模型均与固定要求一致；唯一正式 CLI `generate` 被平台接受并返回 `completed`，同一次 CLI 下载了原始 `result.png`，平台返回 `credits_used=2.5`。但是在模型提交前实际发生了两次本地 `record-decision` 调用，且失败原因不是 brief 唯一允许重试的相对路径解析问题，这一不可逆流程偏差不能改写为 brief 合规。run06 的上游 `TIMEOUT` 没有在 run07 重现，但这不能反向证明 run06 的平台内部根因。

成功生成不等于成功 proof。严格三图 QC 判定 `reject`：前五项结构 fidelity 通过，第六项“浅海蓝微珠颗粒形态与尺度”失败。成图浅海蓝珠虽近圆且半透明，但相对产品源整体显著放大、密度下降、间距扩大，细碎切面反光变成更均一的塑料珠感，命中 brief 的硬拒绝条件；同时白衣颈部近景、无手构图明显更接近产品源，而不是 rank2 的米色针织、长发和胸前手部构图，产品源人物/服装/取景迁移检查失败。没有 rerun、第二次 submit、额外 query、换模型或 imagegen fallback。

## 固定输入

- run：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/run-20260714-double-necklace-07`
- 产品源：`reference/上手参考图/海蓝宝长链-双圈真人佩戴.jpg`
- 产品 SHA-256：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`
- 分类快照：`output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/_inputs/catalog-artifact-tool/validation-catalog-multilayer-audited.xlsx`
- 分类快照 SHA-256：`790909D70B6B6FF3EFE448657B541CE27455C9B7BDDA378BD3B6AD7163BDD281`
- analysis SHA-256：`6E0FDEFA1CDE11954117D182FA6A5B6542B1C29685A4986AFD94665B194FE9C7`
- canonical SHA-256：`0891A8852FE80752CB673A935DD3E6A96BF03362CF43AA50BA6999696BF1634B`
- rank2：`微信图片_20260519175542_452_1.png`，score 228，源/review SHA-256 均为 `99D8B5F7119C2DA519D5488D5293A472408BB4AE8B9A8E5F01B12AF6D664DD7C`
- 正式 Prompt 文件 SHA-256：`04D82EE3B39E19AFBCE1B15B06F04E27E18ABE82A154D17FF5888C6337604D3D`

run07 analysis、canonical 与 run06 对应文件原始字节完全相同。正式 `prompt.txt` 也与 run06 原始字节完全相同，保留了历史审查已知的重复标点；没有清理、缩短或改写 Prompt。

## helper 包装器 TDD 与参数证据

透明包装器和测试只位于 `output/.../necklace-worn-double/_audit/`，没有修改生产 helper、生产代码或生产测试。

TDD 证据如下：

| 阶段 | 结果 | 证据 |
| --- | --- | --- |
| RED | `3 failed`，pytest 退出 1 | 三项测试均因 `run07_helper_wrapper.py` 不存在而按预期失败 |
| GREEN | `3 passed`，pytest 退出 0 | submit 脱敏/原样透传、`--help` 不落参数证据、wait 不覆盖均通过 |
| `py_compile` | 退出 0 | 包装器可编译 |
| 正式 helper `--help` 透传 | 退出 0 | 无网络；前后均未创建参数 JSON |

正式 submit 后，`_audit/run07-helper-submit-parameters.json` 从 `generation.py` 传给包装器的实际 argv 中记录：

| 字段 | 值 |
| --- | --- |
| model | `gpt_image_2` |
| aspect_ratio | `3:4` |
| resolution | `2K` |
| task_id | `run-20260714-double-necklace-07-rank-02-30389700` |
| image_count | `2` |
| Prompt argv UTF-8 SHA-256 | `0C0EE1DD42FEAA1A59AAA27B41AE852E2823E7FA10F57B5DF9E3DAC9966BC5EE` |
| Prompt argv 字符数 | `3310` |
| 正式 helper | `skills/aireiter-image-generation/scripts/aireiter_image_helper.py` |
| 包装器 SHA-256 | `67062D525D27A7408B12A74667EDF97055BAAB854C316CE97652E3787160E3B8` |

Windows 下 `Path.write_text()` 将同一 Prompt 的 77 个 LF 写成 CRLF，因此正式 `prompt.txt` 为 3387 个解码字符、9417 bytes、SHA `04D82E...`，实际 argv 字符串为 3310 字、9340 bytes、SHA `0C0EE1...`。这是同一构建结果的内存字符串与 Windows 落盘换行差异，不是 Prompt 内容变更。参数 JSON 没有保存完整 Prompt、API key、环境变量值、图片路径/base64 或原始 argv。该证据只证明传给正式 helper 子进程的本地实际参数；不把它夸大为平台服务端回显。

## prepare-review、decision 与提交前门禁

正式 `prepare-review` 未传 `output_role`，退出 0。Top 3 仍为 434 rank1/228、452 rank2/228、523 rank3/223。正式 decision 为 `generate_selected`、`selected_ranks=[2]`、`fidelity_confirmed=true`，没有 `output_role`。最终 snapshot 为：

`necklace / worn_source / worn / layer_count=2 / has_pendant=false / is_independent_multi_item=false`

实际共有两次本地 `record-decision` 调用。第一次已经使用 run06 canonical 的**绝对路径**，但额外传入了一组 brief 未授权的 analysis 确认 override；CLI 因而把 `classification_source` 改为 `manual_override`，临时规范化 SHA 变为 `C966BABE152E3EBC41DA0F1956935EB1AE10EB938866EBFC441E4E02CE30AD56`，与 canonical source 不匹配，调用退出 1，事务未写 decision，generation 仍为空。第二次本地调用删除这些 override 后退出 0，并从既有 analysis 生成正确 snapshot。run06/run07 最终 analysis 原始字节和规范化 JSON 一直相同，规范化 SHA 均为 `A3A4DA5C7BF1ED9138AA584372E27606312F1024DEA62FC0FBA2463E64EAB302`；最终 analysis、canonical、Prompt 和图片均未因这两次调用改变，也没有第二次模型 submit。

brief 只授权“相对路径解析失败后将同一 canonical 改为绝对路径”的一次本地重试；run07 首次调用已经使用绝对 canonical，失败来自未授权 override，随后第二次调用因此超出唯一允许的重试边界。这是无法通过报告或最终成功事务消除的不可逆流程偏差，run07 规格结论必须保留为不完全符合。

`_audit/preflight-gate-07.py` 最终 39/39 通过，包括：

- analysis 与 run06 原始字节相同；
- canonical 与 run06 原始字节和全部字段相同，六项 name 顺序精确，`review_status=corrected`，无 `must_keep=吊坠`；
- Prompt 与 run06 原始字节相同，含 `主吊坠：无`、微珠正向和禁止项，无人体纠偏、无 `输出用途：` 行；
- Prompt validator 退出 0；
- generation 为空，无 submit/task ID；
- 包装器 RED/GREEN、`py_compile`、`--help` 门禁通过，参数 JSON 尚不存在。

task-start 与 pre-submit 均使用 `run07-fixed-v1` 固定 72 路径集合，无重复且集合完全一致；37 个 run03-06 历史关键路径和 run06 报告摘要变化为 0。pre-submit manifest check 退出 0。

## 唯一真实生成

| 项目 | 值 |
| --- | --- |
| generate 调用次数 | `1` |
| out task ID | `run-20260714-double-necklace-07-rank-02-30389700` |
| 平台 task ID | `order_gD9rTZuSkhH9XhztLCyHz` |
| submit | `statusCode=200 / pending / estimated_credits=2.5` |
| terminal | `completed` |
| credits_used | `2.5` |
| output URL | `https://static.aireiter.com/upload/image-generator/20260714/mRmLGFiVFLtSCS8b6cNRl-final-0.png` |
| result.png | 同一次 CLI 下载，`5063435` bytes |
| result.png SHA-256 | `68FC20FF97CA54C2B053412A50D233DA043CF2A2C07F0CE4CE99AB8E2A5C66EE` |

`submitted-checkpoint-07.json` 在同一个 CLI 的内建 wait 仍运行时采集：generation 目录 1、submit.json 1、result.json 0，参数 JSON 已存在；没有发网络 query。`terminal-checkpoint-07.json` 在该 CLI 退出后采集：generation 目录 1、submit.json 1、result.json 1、generate invocation 1，平台终态 completed。现有 contemporaneous checkpoint、单个 invocation 和最终文件计数共同证明本任务范围内正式 generate/submit 只有一次；没有第二次提交、额外 query 或 fallback。

## 严格三图 QC

三图对照对象为产品源、run07 rank2 review 副本和同一次 CLI 下载的原始 `result.png`。正式 QC CLI 写入 `generation/01/qc.json`，状态 `reject`。

六项 fidelity：

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 同一条连续长链双圈关系 | pass | 两圈共同延伸至不可见后颈，无第三圈、断裂、交叉或主线重组 |
| 上短下长层间落差 | pass | 上圈贴颈且较短，下圈落向锁骨且较长 |
| 红橙色连续渐变区 | pass | 红、橙、浅色仍沿线路形成连续过渡 |
| 唯一大红圆珠串接关系 | pass | 下层偏左仅一颗明显大红圆珠，沿主线串接，无吊环或复制 |
| 不可见扣头不补造 | pass | 后颈连接和扣头继续不可见，未补造或特写 |
| 浅海蓝微珠颗粒形态与尺度 | **fail** | 整体放大、密度下降、间距扩大并呈均一塑料珠感，命中硬拒绝 |

runtime checklist 共 25 项，18 pass、7 fail。除产品材质/比例、元件数量和排列、无新增删除结构、两项产品源人物区域迁移检查及第六项微珠问题外，`qc-05425e8cc30e0d4a` 也为 fail：成图在红珠与微珠主线连接处新增了产品源中不清晰存在的高亮银色间隔/连接元件，属于补充不存在的连接结构。QC 记录 `critical_failures=[must_keep_failed,source_person_region_migrated]`。reject 后没有 rerun。

## Validators 与审计

三项最终 validator 的原始 stdout、stderr 和退出码保存在 run07 `validation-final/`：

| 验证器 | 退出码 | 结果 |
| --- | ---: | --- |
| `validate_prompt_contract.py` | 0 | `Prompt 契约校验通过` |
| `validate_qc_record.py` | 0 | `qc 记录校验通过` |
| `inspect_run_artifacts.py` | 0 | `run 产物检查通过` |

task-start 时间为 `2026-07-14T02:22:08.1236493+08:00`，pre-submit 时间为 `2026-07-14T02:32:47.6294779+08:00`，采集者均为 `task11-run07-executor`。两阶段均保存带命令和退出码的 Git status、diff stat，以及同一 `run07-fixed-v1` 72 项 manifest。按照“报告完成后再采 task-end”的时序，本文和另外两份汇总全文修订完成后才采集 end；本文不预先引用尚未生成的 checkpoint，也不在 end 之后追写造成报告哈希失效。

本任务只创建 run07、output-only 包装器/测试/审计/QC 证据并全文修订三份报告。没有修改生产代码、生产测试、SPEC、Plan、历史 run、并发 HERO/戒指文件、Git index、HEAD 或分支；没有暂存或提交。

## 最终关注项

1. run07 completed 证明相同输入这次可以通过平台生成，但不能解释 run06 上游 TIMEOUT 的内部根因。
2. 第六项微珠仍失败，且出现产品源人物/服装/取景迁移，所以 run07 不能计为普通项链双层真人佩戴成功 proof。
3. 参数证据闭合本地出站侧 `gpt_image_2 / 3:4 / 2K`，但不是平台服务端 payload 回显。
4. 正式任务只有一次，completed/reject 后没有 rerun、额外 query、换模型或 fallback。
5. 双圈场景确认消耗由 5.0 增至 7.5 credits；Task 11 累计确认消耗由 35.0 增至 37.5 credits。
6. 两次本地 `record-decision` 调用超出 brief 唯一授权的重试边界；虽然失败事务未落盘、最终输入/图片未变且模型 submit 只有一次，run07 规格仍不完全符合。
