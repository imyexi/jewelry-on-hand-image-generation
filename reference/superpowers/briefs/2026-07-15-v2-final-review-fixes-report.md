# 产品保真 v2 最终审查 Important 修复报告

## 结论

brief 中的 3 个 Important 已按逐项 TDD 完成修复。模型反序列化、核心 validator、artifact inspector 与 portable QC validator 现在对 v2 吊坠语义使用一致的严格边界；两组指定回归最终分别为 `264 passed` 与 `440 passed`。

本次未调用 provider，未暂存、未提交，也未修改 brief 允许范围之外的代码或测试文件。

## Finding 1：v2 JSON 反序列化类型不严格

### 根因

`PendantSemantics.__post_init__()` 本身会拒绝 bool、字符串和浮点数，但 `PendantSemantics.from_dict()` 在构造 dataclass 前使用历史宽松 helper `_required_int()` / `_optional_int()`。这些 helper 会把 `"1"`、`1.0`、`"2"`、`2.0` 转为整数，并把空字符串转为 `None`，导致严格 dataclass 校验无法看到原始 JSON 类型。

### RED

先为真实 `PendantSemantics.from_dict()` 与嵌套的 `ProductFidelityConstraints.from_dict()` 各新增 5 组参数：

- `count="1"`
- `count=1.0`
- `layer="2"`
- `layer=2.0`
- absent canonical 的 `layer=""`

命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -q -k "non_json_integer"
```

结果：`10 failed, 88 deselected`。十个用例全部因当前实现未抛出 `ValueError` 而失败，证明测试准确命中宽松归一化缺陷。

### GREEN

仅修改 `PendantSemantics.from_dict()`：`count` 和 `layer` 改用现有严格 `_json_int()`，不修改 `_required_int()`、`_optional_int()` 或任何其他历史模型的兼容语义。合法的 `count=0/1`、`layer=null/1..3` 仍由 dataclass 组合校验继续约束。

命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -q -k "non_json_integer or round_trip_structured_pendant_semantics or pendant_semantics_reject_invalid_combinations"
```

结果：`20 passed, 78 deselected`。

## Finding 2：present canonical 自由文本冲突未拒绝

### 根因

`_validate_v2_pendant_semantics()` 的 absent 分支会遍历 `_iter_constraint_semantic_fields()`，但 present 分支只检查唯一可追溯吊坠 `must_keep` 和所属层，没有扫描自由文本。因而 present canonical 可以同时携带“无吊坠”或“必须新增第二颗吊坠”等结构矛盾，仍被核心 validator 接受。

### RED

新增 6 个规格明确的冲突短语：

- 缺失声明：`无吊坠`、`未见吊坠`、`吊坠不存在`、`吊坠缺失`
- 创建要求：`必须新增第二颗吊坠`、`要求生成第二颗吊坠`

每个短语覆盖 `_iter_constraint_semantic_fields()` 的全部 10 类字段路径：`detected_keywords`、`must_not_change`，以及 `must_keep` 的 `name/source_text/normalized_keyword/location/visual_shape/relationship/forbid/qc_question`。断言错误同时包含精确字段路径和精确冲突短语。

命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -q -k "present_v2_rejects_structural_conflict or present_v2_accepts_forbid_second_pendant_protection"
```

结果：`60 failed, 1 passed, 98 deselected`。60 个冲突用例全部未被正确拒绝；合法保护句用例在修复前已经通过。

### GREEN

在核心 `_validate_v2_pendant_semantics()` 的 present 分支中，先遍历同一 `_iter_constraint_semantic_fields()`，只匹配 brief 明确给出的 6 个结构冲突短语；不引入通用自然语言极性解析器。冲突错误格式为：

```text
<精确字段路径> 与 present canonical 冲突：<精确冲突短语>
```

命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -q -k "present_v2_rejects_structural_conflict or present_v2_accepts_forbid_second_pendant_protection or present_v2_requires_traceable_pendant_must_keep"
```

结果：`62 passed, 97 deselected`。

### 合法保护句正向证据

`test_present_v2_accepts_forbid_second_pendant_protection` 把 `禁止新增第二颗吊坠` 放入 present canonical 的语义字段，并断言核心 validator 返回原 constraints。该用例在 RED 与 GREEN 两次运行中均通过，证明实现没有用简单 `新增第二颗` 子串误杀保护语句。

核心 validator 仍是现有 record-decision、CLI generate、prompt 与 QC 路径复用的同一入口，因此这些调用链自动 fail closed；未在各调用方复制另一套文本规则。

## Finding 3：portable 未对照 analysis.pendant_count

### 根因

`inspect_run_artifacts.py` 与 `validate_qc_record.py` 都根据 `confirmed_product_type` 直接硬编码 canonical 的 expected presence/count，仅从 analysis 读取 `pendant_layer`。两者都没有先严格确认最终 analysis 的 `has_pendant/pendant_count/pendant_layer` 三元组。因此 `pendant_necklace + analysis.pendant_count=2 + canonical.count=1` 会被错误认证，QC 还会接受按 canonical count=1 生成的 checklist。

### RED

新增两个要求中的进程级 portable RED：

1. artifact inspector：把合法 v2 带链吊坠 run 的 analysis 与 confirmation snapshot 一并改为 `pendant_count=2`，确认 inspector 错误返回 0。
2. QC validator：只把最终 analysis 改为 `pendant_count=2`，保留 canonical count=1 及对应 checklist，确认 QC validator 错误返回 0。

命令：

```powershell
uv run pytest tests/test_skill_portability.py -q -k "analysis_count_mismatch"
```

结果：`2 failed, 101 deselected`，两个脚本都错误接受矛盾 run。

自审时又发现普通项链若完全缺少 `pendant_layer` 键，`.get()` 会把“缺失”误当成显式 `null`。为落实“逐字段确认”，补充 inspector/QC 参数化 RED：

```powershell
uv run pytest tests/test_skill_portability.py -q -k "requires_explicit_null_pendant_layer"
```

结果：`2 failed, 103 deselected`。

### GREEN

在 portable 的 `validate_qc_record.py` 中增加纯 Python helper `_validate_v2_necklace_analysis_pendant_fields()`，由 QC validator 直接调用，并由本来就依赖同目录 QC 模块的 inspector 复用。helper 不导入项目 package，严格要求：

- 普通项链：三个字段必须显式存在，且分别为 JSON `false`、JSON 整数 `0`、JSON `null`；
- 带链吊坠：`has_pendant` 必须为 JSON `true`，`pendant_count` 必须为 JSON 整数 `1`，`pendant_layer` 必须为 JSON 整数 `1..3`；
- ring/bracelet：helper 立即返回，不增加项链逐字段规则；其既有合法 semantics 校验保持不变。

随后两脚本仍执行原有 canonical 类型、组合和 analysis/canonical 层级对照。

命令：

```powershell
uv run pytest tests/test_skill_portability.py -q -k "analysis_count_mismatch or requires_explicit_null_pendant_layer or inspector_and_prompt_validator_accept_v2_plain_necklace or portable_v2_non_necklace_qc_does_not_require_pendant_question"
```

结果：`7 passed, 98 deselected`。两个 count=2 用例均以非零退出码拒绝，stderr 包含中文 `analysis.pendant_count` 诊断且无 `Traceback`；QC 文件字节未被改写。普通项链显式 null 与 ring/bracelet 边界一并通过。

## 完整验证

修复及自审补强完成后，重新运行 brief 指定的两组完整命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_skill_portability.py -q
```

结果：`264 passed in 1.41s`。

```powershell
uv run pytest tests/test_models.py tests/test_review_decision.py tests/test_generation.py tests/test_prompt_builder.py tests/test_qc.py -q
```

结果：`440 passed in 1.16s`。

## 修改文件

- `src/jewelry_on_hand/models.py`
- `src/jewelry_on_hand/product_fidelity.py`
- `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_skill_portability.py`
- `reference/superpowers/briefs/2026-07-15-v2-final-review-fixes-report.md`

## 自审

- 范围：仅修改 brief 允许的 6 个代码/测试文件并新增本报告；未触碰戒指实现、HERO、飞书、v6、`output_role` 或 provider helper。
- TDD：每个 finding 均先运行并保存预期 RED，再做最小 GREEN；普通项链显式 null 缺失边界也单独完成 RED/GREEN。
- 模型兼容：没有修改历史 `_required_int()` / `_optional_int()`；严格类型只落在 `PendantSemantics.from_dict()`。
- 文本规则：仅维护 brief 明确的 6 个冲突短语；合法 `禁止新增第二颗吊坠` 有独立正向测试。
- portable：对两个 portable 脚本执行项目 package import 搜索，无匹配；新增 helper 只使用标准库与同目录脚本边界。
- 品类边界：新逐字段 helper 只处理 `necklace` / `pendant_necklace`；ring/bracelet 回归通过。
- 诊断边界：新增 inspector/QC 失败均为中文、非零退出且无 traceback；QC validator 不改写错误 checklist 文件。
- 代码卫生：目标文件 `git diff --check` 无空白错误；仅出现工作树既有的 LF/CRLF 提示。
- 外部行为：未调用任何 provider；未执行 git stage、commit、push 或破坏性命令。
