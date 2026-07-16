# Task 4：结构化 Prompt、QC 与便携 validator 整合报告

## 结论

Task 4 已完成。普通项链与带链吊坠的 Prompt、QC 和三个便携脚本均以最终 `ProductAnalysis` 与 v2 canonical 为唯一结构化吊坠事实来源；历史 schema v1 由 inspector 标记为只读，检查过程中不改写 JSON。reviewer 指出的非项链 schema v2 QC 漂移也已修复，任务级总回归为 373 项通过。

本报告只描述 Task 4 的项链 v2 工作，同时明确保留工作树中并发完成的戒指契约。未提交、未暂存，也未回退任何并发文件。

## Prompt 阶段（前一实现者完成，本次复核）

### RED 证据

根据交接事实，前一实现者先加入普通项链 absent、带链吊坠 count/layer、缺失 v2 canonical、冲突 canonical 等测试；旧实现因品类策略仍按 analysis-only 渲染且未消费 v2 canonical 而失败。

### GREEN 证据

- 前一阶段交接测试：`tests/test_prompt_builder.py` 为 63 passed。
- `prompt_builder.py` 在项链 Prompt 输出前调用统一 `validate_product_fidelity_constraints()`；普通项链固定渲染“主吊坠：无。”与完整禁止创建句，带链吊坠固定渲染 count=1 和所属层。
- `category_policies/necklace.py` 不再自行根据 `analysis.has_pendant` 渲染吊坠事实，仍负责层数、长度、链型、顺序、展示模式与物理规则。
- `validate_prompt_contract.py` 的便携规则与核心 Prompt 精确一致：普通项链要求 absent 完整句；带链吊坠要求数量 1、所属层 1 至 3，并校验禁止删除、复制、换层或新增第二颗吊坠。
- 本次总回归重新覆盖全部 Prompt 测试，包含普通双圈项链 `layer_count=2 + pendant absent`，未引入三圈吊坠商品或 proof 断言。

## QC 阶段

### RED

执行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "qc_checklist_uses" -v
```

结果：2 failed。两个新增用例均因 `build_qc_checklist()` 不接受 `product_analysis` 关键字参数而按预期失败，证明测试覆盖的是缺失的新接口。

### GREEN

- `build_qc_checklist()` 新增 keyword-only `product_analysis` 与 `fidelity_constraints`，项链标准 v2 context 必须成对提供并先调用统一 validator。
- absent 仅追加一次“主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠”；present 仅追加一次“现有主吊坠数量是否为 1，且仍位于第 N 层并保持原连接关系”。
- 核心与便携 QC 使用同名 `PENDANT_ABSENT_QC_QUESTION`、`PENDANT_PRESENT_QC_QUESTION` 常量，避免文案漂移。
- `write_qc_result()` 对标准 schema v2 runtime 传入 analysis/canonical；schema v1 与无标准 runtime context 的旧调用继续沿用宽松 checklist，不伪造结构化事实。

验证：

```text
uv run pytest tests/test_product_fidelity_v2.py tests/test_qc.py -q
127 passed
```

## Portable 阶段

### RED

首轮先落盘并运行三个要求用例及一个畸形输入用例；reviewer 复审后再补一组非项链参数化用例：

1. 完整 v1 项链 run：inspector 退出 0，但 stdout 缺少 `legacy_read_only=true`。
2. 合法 v2 普通项链 run：portable QC 尚未重建 absent 精确问题，inspector 因 runtime checklist 不一致失败。
3. 合法 v2 带链吊坠 QC：正确 count=1/layer=2 记录在修复前即失败，无法进入错误 layer=1 的预期拒绝阶段。
4. 畸形 v2 `detected_keywords=null`：inspector 抛出 `TypeError` traceback，而非返回中文校验错误。
5. 合法 schema v2 ring/bracelet：核心 expected checklist 不含吊坠问题，但 portable 错误地无条件追加 absent 吊坠问题，两项均因 runtime checklist 不一致而失败。

### GREEN

- `inspect_run_artifacts.py` 新增独立 `_validate_fidelity_constraints_data()`：schema v1 返回只读标记；schema v2 严格检查结构化字段类型、presence/count/layer/policy、最终 analysis 对照、absent 敏感词字段路径以及 present 主吊坠 must_keep 可追溯层。脚本不导入项目 package。
- inspector 成功输出 `legacy_read_only=true|false`；v1 用例比较执行前后全部 JSON 原始字节，确认完全不变。
- `validate_qc_record.py` 对 schema v1 保持历史 checklist；对所有 schema v2 都强制要求并校验 `pendant_semantics` 的基本类型与 presence/count/layer/policy 组合。只有 `necklace`、`pendant_necklace` 会进一步对照最终 analysis 并追加与核心 QC 完全相同的唯一吊坠问题；正确 layer=2 通过，伪造 layer=1 非零退出。
- `validate_prompt_contract.py` 的项链 v2 规则已与核心 Prompt 对齐，并继续保持纯标准库/同目录脚本依赖。
- 畸形 v2 现在返回明确中文错误且无 traceback。
- reviewer 的 Important 已用 ring、bracelet 参数化测试复现：两类合法 schema v2 canonical 都保留必填的 absent/0/null/forbid 对象，但核心 expected checklist 不含吊坠问题；修复前 portable 错误追加吊坠问题，修复后两类均通过。非项链缺失 `pendant_semantics` 仍不合法。

验证：

```text
portable 新四测：4 passed
reviewer 非项链 v2 回归：2 passed
tests/test_skill_portability.py：92 passed
```

## 用户要求保留的并发戒指契约

- 未回退或搬移任何戒指生产语义。
- `validate_prompt_contract.py` 继续校验戒指 Prompt 前 300 字核心约束。
- “最高优先级：只生成一枚目标戒指”继续归属 `【基础安全边界】`；portable 旧断言已协调到该层，而不是把生产字符串移回 `【品类保真】`。
- 手背朝向、单枚戒指、额外首饰禁令及现有 ring 专属逻辑均保留；Task 4 新增的项链分支未覆盖 ring 分支。

## 文件

Task 4 允许范围内的实现与测试文件：

- `src/jewelry_on_hand/prompt_builder.py`
- `src/jewelry_on_hand/category_policies/necklace.py`
- `src/jewelry_on_hand/qc.py`
- `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- `tests/test_prompt_builder.py`
- `tests/test_qc.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_skill_portability.py`
- `tests/test_final_necklace_important_fixes.py`

本报告按要求写入 `reference/superpowers/briefs/2026-07-14-v2-task-4-report.md`。

## 最终验证与自审

```powershell
uv run pytest tests/test_prompt_builder.py tests/test_qc.py tests/test_product_fidelity_v2.py tests/test_skill_portability.py tests/test_final_necklace_important_fixes.py -v
```

结果：373 passed，0 failed，耗时 2.61 秒。

附加检查：四个核心/便携脚本 `py_compile` 通过；Task 4 文件定向 `git diff --check` 通过。检查仅出现工作树既有的 LF/CRLF 转换提示，没有空白错误。

自审确认：

- Prompt 与 QC 的项链吊坠事实只来自已校验 v2 canonical + 最终 analysis。
- 普通双圈项链仍是同一条项链形成两圈，canonical 为 pendant absent。
- v1 inspector 仅读取且不改写；v2 inspector 明确输出非 legacy。
- 三个便携脚本无项目 package 依赖、无网络依赖。
- bracelet/ring 的 schema v2 QC 继续要求合法 `pendant_semantics`，但不追加项链专属吊坠问题；旧 Prompt/QC 与并发戒指契约由总回归覆盖并按用户要求保留。

## 关注项

- 工作树包含多任务并发改动，Task 4 文件的 Git diff 会同时显示既有戒指等改动；整合时应按本报告区分项链 v2 与并发戒指契约，不要以整文件回退。
- 仓库对部分文件提示未来 Git 操作可能将 LF 转为 CRLF；本次没有执行格式化、暂存或提交，也未改变该策略。
