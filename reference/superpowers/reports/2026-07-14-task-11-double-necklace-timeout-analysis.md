# Task 11 双圈项链 run06 TIMEOUT 分析

## 结论

run06 的单个留存任务已被 AIReiter 接受，并由留存 CLI 调用中的 `wait` 返回平台终态 `failed / TIMEOUT`。现有证据把故障边界定位在平台上游生成阶段，而不是本地 Prompt 校验、UTF-8 协议解码、任务 ID 传递、轮询终态识别或结果落盘阶段。

平台没有返回 `credits_used`、output URL 或原始图片，因此 run06 不计入确认消耗，不能执行 QC，也不能作为普通项链双层真人佩戴成功证据。该结论不推断平台内部根因；单次 TIMEOUT 既不足以证明瞬时容量问题，也不足以证明新增微珠约束必然导致超时。

审计边界同时保留：`model.txt` 独立记录 `gpt_image_2`，但 `3:4 / 2K` 只见于 CLI 默认、Prompt 与 `expected_*` 记录；submit/result 未留存脱敏出站请求 payload，不能独立断言平台实际收到的画幅和分辨率参数。另不存在 contemporaneous `_audit/submitted-checkpoint-06.json`；单个 invocation、单个 `generation/01`、一组 submit/result 和事后 terminal checkpoint 仅支持“留存证据未显示第二次提交”，不能构成无保留的绝对唯一性证明。

## Phase 1：根因边界

### 原始错误

- submit：HTTP/API `statusCode=200`、`status=pending`，out task ID 为 `run-20260714-double-necklace-06-rank-02-3454e1e5`。
- wait：平台 task ID 为 `order_zOJpoWtoYnpTQN0D7-eKv`，终态为 `failed`。
- 平台错误：`TIMEOUT / Upstream service timed out. Please try again later.(上游服务响应超时，请稍后重试。)`。
- helper 退出码：1；这是 helper 对平台 `failed` 终态的既定映射，不是 JSON 解码异常。
- 本地 CLI 已先把合法 UTF-8 JSON 写入 `generation/01/result.json`，再因 helper 非零退出抛出错误；因此失败状态完整保留。

### 组件边界

| 边界 | 证据 | 判断 |
| --- | --- | --- |
| Prompt/结构门禁 | 31/31，Prompt validator 退出 0 | 提交前契约通过 |
| CLI 到 helper submit | submit JSON 为 200/pending | 请求被接受 |
| out task ID 到平台任务 | wait 返回平台 task ID | ID 传递有效 |
| helper 轮询 | 返回结构化终态 JSON | 轮询与 UTF-8 协议有效 |
| 平台生成 | `failed / TIMEOUT` | 故障发生在该边界内或其上游 |
| 下载/QC | 无 URL、无 result.png | 未进入，不能判定视觉质量 |

本地 helper 默认等待上限为 300 秒；若仅是本地等待耗尽，helper 会输出最后一次非终态结果并在 stderr 报 `Timed out waiting for task ...`。run06 实际收到平台明确的 `status=failed` 与 `error.code=TIMEOUT`，所以不能把这次终态误记为本地轮询超时。

### 可复现性限制

run06 brief 禁止同一 run 第二次 submit，也禁止终态后额外 query。当前留存证据只观察到一次平台 TIMEOUT；在不创建新任务的前提下无法复现。本分析不通过重复提交来“试试看”。由于 contemporaneous post-submit checkpoint 缺失，本文只陈述留存证据未显示第二次提交，不补造历史闭环。

## Phase 2：工作样例对比

run05 与 run06 使用相同客户端，`model.txt` 均记录 `gpt_image_2`，本地 CLI 默认、Prompt/expected 目标均为 `3:4 / 2K`，rank2 图片和产品图也相同；run05 平台在 83 秒内返回 `completed`，随后成功下载原图。但两轮都未留存脱敏出站请求 payload，因此这一对比不能把 `3:4 / 2K` 写成已独立证实的平台实际请求参数。run06 的两张输入图片 SHA-256 与 run05 完全相同：

- rank2：`99D8B5F7119C2DA519D5488D5293A472408BB4AE8B9A8E5F01B12AF6D664DD7C`
- 产品图：`D6ED7C4841CBFA9C537F84C91985EF4CB761FCE76C383951ACC651EDD65A25D0`

两轮可见差异是 run06 新增微珠几何/尺度 canonical，Prompt 从 3162 字、8754 bytes 增至 3387 字、9417 bytes。平台接受了该 Prompt，但没有提供足以区分“瞬时上游故障”和“该任务持续触发上游超时”的内部诊断。

## Phase 3：单一假设与最小验证

当前最小假设是：本地数据流有效，run06 在平台上游生成阶段遇到一次可重试的外部 TIMEOUT。最小验证不是修改代码、缩短 Prompt 或切换模型，而是在独立 run 中逐字复用 run06 的最终 analysis、六项 canonical、rank2 和 Prompt，只执行一次同模型 submit。

验证规则：

1. 先完成 run06 独立审查，确认失败证据，并显式保留缺少 contemporaneous post-submit checkpoint 的审计缺口，不把事后文件冒充该检查点。
2. 新 run 必须有新 run ID、新 out task ID 和独立 start/pre-submit/end 审计，不覆盖 run06。
3. 只允许一次正式 submit；不得在同一 run 内重试。
4. 若 completed，下载原图并按六项 fidelity 与完整 runtime checklist 严格 QC。
5. 若再次 `TIMEOUT` 或其他平台失败，保留证据并停止，不继续堆叠重试，也不通过修改 Prompt 混淆单变量假设。

## Phase 4：本地处置

当前不实施生产代码修复。客户端已经正确保存平台失败 JSON、返回非零并阻止下载/QC；修改 helper 超时、吞掉失败或自动重试都会改变现有留存提交链的审计语义，且没有证据表明能修复平台终态 `TIMEOUT`。未来 run 应额外保存脱敏出站请求参数和 contemporaneous post-submit checkpoint，避免再次出现相同证据边界。

只有后续证据表明本地轮询错误、终态解析错误或重复发生同类平台超时时，才重新进入根因分析并决定是否需要 TDD 代码变更。
