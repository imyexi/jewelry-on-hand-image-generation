# Task 5：全文文档协调与最终验证准备报告

## 状态

Task 5 的 v2 文档契约、schema fenced JSON 测试、十份文档全文协调、portable 验证与 `output_role` 测试夹具协调已完成。后续独立审查依次发现两项 Important：第一项是 portable workflow 在加入 v2 结构化主吊坠文案时，误删了 Prompt 段原有的内部图 2 输入图角色禁令；第二项是 `reference/review-decision-schema.md` 的产品确认快照仍允许“至少一个吊坠”，与同节第一阶段 `present/1/快照 pendant_layer/forbid` 冲突。两项问题均已依严格 TDD 修复，并新增精确文档契约防止回归。

Task 5 两项 Important 以及整项 final-review 五项 Important 修复后，主线程重新运行四组最终验证。`output/final-verification/2026-07-14` 的计划约定目录和 `output/final-verification/2026-07-15` 的实际刷新目录均保存同一份新鲜结果：portable 175 passed、v2 聚焦 701 passed、关键回归 109 passed、全量 1503 passed；四组 exitcode 均为 0、stderr 均为 0 bytes。全量计数包含用户确认保留的最新 HERO、`output_role` 与 reference composition 测试，但这些并发范围仍不计入 I1 关闭范围，也未由本 Task 修改。

Task 5 未修改生产代码，未削弱 `output_role` gate，未修改或回退戒指 Prompt 压缩、HERO、v6 生成/QC、飞书或 provider helper，未调用 provider，未暂存或提交。

## TDD 记录

### Task 5 原始文档契约

先在 `tests/test_skill_portability.py` 增加六份操作者文档参数化契约，以及 schema 文档全部 fenced JSON 的解析/版本测试。

- RED：`uv run pytest tests/test_skill_portability.py -k "v2_and_v1_read_only or schema_json" -v`
- RED 结果：8 selected，7 failed，1 passed，exitcode 1。六份文档缺少 v2/历史 v1 只读边界，schema fenced JSON 只有 v1。
- schema GREEN：`uv run pytest tests/test_skill_portability.py -k "schema_json" -v`
- schema GREEN 结果：2 passed，97 deselected，exitcode 0。
- 当时 portability GREEN：`uv run pytest tests/test_skill_portability.py -q`
- 当时 portable 结果：99 passed in 1.05s，exitcode 0，stderr 0 bytes。

### 第一项 Important：内部图 2 迁移禁令

审查发现 `skills/jewelry-on-hand-workflow/references/workflow.md` 的 Prompt 段仍说明“内部图 2 只提供产品身份”，但删除了更具体、不可替代的完整输入图角色禁令。先在 `tests/test_skill_portability.py` 中新增对下列完整句子的精确断言，再修复文档：

`禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。`

- RED：`uv run pytest tests/test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q`
- RED 结果：1 failed in 0.19s，exitcode 1；失败原因精确为 portable workflow 缺少该句，不是测试装配错误。
- 最小 GREEN：`uv run pytest tests/test_skill_portability.py::test_portable_workflow_keeps_product_identity_input_migration_boundary -q`
- 最小 GREEN 结果：1 passed in 0.12s，exitcode 0。
- portable GREEN：`uv run pytest tests/test_skill_portability.py -q`
- portable GREEN 结果：100 passed in 1.00s，exitcode 0。

最小实现只在 portable workflow Prompt 段恢复完整禁令；现有普通项链 absent 文案、带链吊坠 count/layer 文案、自由文本极性禁止推断以及内部图 1/2 职责句均保留。

### 第二项 Important：主吊坠数量必须恰好为一

审查发现 `reference/review-decision-schema.md` 的产品确认快照段仍写“至少一个吊坠”，允许 `pendant_count>=1`；同节后文却规定第一阶段带链吊坠 canonical 必须为 `present/1/快照 pendant_layer/forbid`。先在 `tests/test_skill_portability.py` 的文档契约区域新增 `test_review_decision_schema_requires_exactly_one_primary_pendant`，要求 schema 不得含现行短语“至少一个吊坠”，并必须同时表达“恰好一个主吊坠”和 `pendant_count=1`，再修订文档。

- RED：`uv run pytest tests/test_skill_portability.py::test_review_decision_schema_requires_exactly_one_primary_pendant -q`
- RED 结果：1 failed in 0.20s，exitcode 1；失败点精确为旧文档仍包含“至少一个吊坠”，不是测试装配、导入或语法错误。
- 最小 GREEN：`uv run pytest tests/test_skill_portability.py::test_review_decision_schema_requires_exactly_one_primary_pendant -q`
- 最小 GREEN 结果：1 passed in 0.11s，exitcode 0。
- portable GREEN：`uv run pytest tests/test_skill_portability.py -q`
- portable GREEN 结果：101 passed in 1.10s，exitcode 0。

最小实现只把冲突句修订为“带链吊坠必须使用 `has_pendant: true`、恰好一个主吊坠（`pendant_count=1`）和有效的 `pendant_layer`”。该句与同节 `present/1/快照 pendant_layer/forbid` 完全一致，没有改变其他品类、运行时逻辑或 provider 行为。

## 文档协调范围

全文修订了计划指定的十份文档，不使用末尾“以本节为准”补丁：

- schema 字段表明确 v1 顶层字段和只读边界、v2 必填 `pendant_semantics`，并提供普通项链 absent、带链吊坠 present 两个可解析 v2 示例和一个不含 `pendant_semantics` 的 v1 示例。
- 普通项链 absent 的 10 类自由文本路径和五个敏感词已完整列明；禁止创建由 `creation_policy=forbid` 表达，不再依赖 canonical 自由文本“禁止新增吊坠”。
- 第一阶段带链吊坠在快照与 canonical 中统一为恰好一个主吊坠：`has_pendant: true`、`pendant_count=1`、有效 `pendant_layer`，对应 `present/1/快照 pendant_layer/forbid`；不再保留允许 `pendant_count>=1` 的现行表述。
- `prepare-review` 在最终纠正并校验 analysis 后构建 v2；`record-decision` 在替换文件前、`generate` 在创建 generation 目录、写提交文件、调用 helper 或 provider 前执行交叉校验并给出中文修复动作。
- Prompt 精确记录普通项链“主吊坠：无”与完整禁止创建句、带链吊坠 count/layer 文案；QC 精确记录 absent/present 两个 runtime question，不从自然语言极性推断。
- portable workflow Prompt 段已恢复内部图 2 完整禁止迁移句，不再以“只提供产品身份”概述替代可执行的输入图角色边界。
- inspector 对历史 v1 的 `legacy_read_only=true` 标记、只读不改写和不自动升级已写入 schema、流程、QC 与排障章节。
- 双圈附件明确为同一条连续长链形成 2 层、无主吊坠，不是两件项链或带链吊坠；1 至 3 层仅是运行时能力，不代表存在三圈吊坠商品。
- I1 是本次 v2 范围；I5 真实双圈成功 proof 与 HERO 仍开放。戒指、HERO、三图输出角色、飞书与 v6 章节均保留。

## `output_role` 夹具协调

先前最终验证被既有测试 helper 未完整声明角色阻断；该阻断只在测试夹具层协调，生产 gate 保持不变：

- `prepare-review` 测试显式传入 `hand_worn` 或 `lifestyle`。
- `record-decision` 测试同时准备 `analysis/output_role.json` 并传入相同 `--output-role`，由生产代码写入一致的 decision 角色。
- 项链 `hand_held` 使用 `hand_worn` 与“手部佩戴图；深色背景”参考用途；项链 `worn` 使用 `lifestyle` 与“生活场景图；深色背景”参考用途。
- v2 runtime checklist 夹具传入最终 analysis 与 fidelity constraints，完整覆盖主吊坠语义问题。
- 飞书 CLI 用例只补齐角色声明并扩宽 mock 对现有 `product_image` / `output_role` 关键字参数的接受能力；返回值、调用次数和“不再需要 classification”的断言未改变。

这些变化只涉及测试数据和 mock 签名，没有删除、放宽或绕过任何生产断言，也没有修改 `src/jewelry_on_hand/output_roles.py`、CLI gate、scoring、Prompt 或 QC 生产逻辑。

## 最终验证证据

计划约定目录：`output/final-verification/2026-07-14`；实际刷新目录：`output/final-verification/2026-07-15`。第二项 Important 修复后，主线程重新运行四组验证并将 stdout/stderr/exitcode 三件套同步到两个目录，结果如下：

| 测试组 | 最终结果 | stderr | exitcode |
| --- | --- | --- | --- |
| portable | 175 passed | 0 bytes | 0 |
| v2 聚焦 | 701 passed | 0 bytes | 0 |
| I2-I4 / `output_role` / helper UTF-8 关键回归 | 109 passed | 0 bytes | 0 |
| 全量 | 1503 passed | 0 bytes | 0 |

四组均为 Task 5 两项 Important、整项 final-review 三项 Important 修复，以及用户确认保留的 HERO、`output_role` 与 reference composition 并发改动之后的新鲜运行。本 Task 没有修改或回退这些并发实现，也不把它们的状态计入 I1 关闭结论。

## 最终核对

- 两项 Important finding 均已由精确 RED 复现并最小修复；两个新增契约都进入 portable 全文件组并保持 GREEN。
- 第一项恢复的句子仅补回内部图 2 输入图角色禁令，未删除或改弱 v2 结构化主吊坠 Prompt 契约。
- 第二项只把快照中的宽松数量表述收紧为“恰好一个主吊坠（`pendant_count=1`）”，与现有 canonical 规则协调一致。
- 十份文档协调、schema fenced JSON 边界和 `output_role` 夹具协调均完整保留；fixture 变化没有削弱生产 gate。
- Task 5 没有提交、查询或轮询任何 provider 任务，也没有暂存或提交。
- 本报告不创建 `output/final-verification/2026-07-14/final-code-review.md`；证据虽已刷新，仍需 Task 5 独立复审和整项最终独立复审。

## 开放项与关闭条件

- I1 尚不得宣布关闭；四组最终证据已经刷新，仍须通过 Task 5 独立复审和整项最终独立复审。
- I5 真实双圈成功 proof 仍开放；当前结构化契约和本地测试不能替代真实生成成功证据。
- HERO 仍开放，不属于本次 I1 关闭范围。用户已确认保留最新 HERO；它没有被本 Task 修改、覆盖、放宽或回退。
