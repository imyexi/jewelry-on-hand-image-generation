# 产品保真 v2 最终审查 Important 修复简报

## 状态

整项最终独立审查发现 3 个 Important。必须由一个 implementer 统一按 TDD 修复，避免模型、核心 validator 与 portable validator 之间再次漂移。不得修改范围外戒指、HERO、飞书、v6、`output_role` 或 provider helper，不得真实调用 provider，不得暂存或提交。

## Finding 1：v2 JSON 反序列化类型不严格

`PendantSemantics.from_dict()` 当前通过 `_required_int()` / `_optional_int()` 宽松转换，错误接受 `count="1"`、`count=1.0`、`layer="2"`、`layer=2.0` 和 absent `layer=""`。

要求：

- v2 JSON 的 `count` 必须是非 bool 的原生整数，且仅为 0/1；
- `layer` 必须是 `null` 或非 bool 的原生整数 1..3；
- 不得把字符串、浮点或空字符串静默规范化；
- 不改变其他历史模型 helper 的兼容语义，只在 `PendantSemantics.from_dict()` 建立严格边界；
- 先添加真实 `ProductFidelityConstraints.from_dict()` / `PendantSemantics.from_dict()` RED，覆盖字符串、整数值浮点和空字符串，再最小修复。

## Finding 2：present canonical 自由文本冲突未拒绝

核心 `validate_product_fidelity_constraints()` 只检查唯一吊坠 `must_keep` 和 layer，没有拒绝 present canonical 在自由文本中声明吊坠缺失或要求生成第二颗。

要求：

- 先写 RED，证明 present canonical 在语义字段中出现“无吊坠”“未见吊坠”“吊坠不存在”“吊坠缺失”等缺失声明，或“必须新增第二颗吊坠”“要求生成第二颗吊坠”等创建要求时被拒绝；
- 覆盖 `_iter_constraint_semantic_fields()` 的适用字段路径，错误应包含精确字段路径和冲突短语；
- 合法保护语句“禁止新增第二颗吊坠”必须继续通过，不能用简单 `新增第二颗` 子串误杀；
- 不建立通用自然语言极性解析器，只维护规格明确的结构冲突短语集合；
- 复用同一核心 validator，使 record-decision / generate 自动 fail closed。

## Finding 3：portable 未对照 analysis.pendant_count

`inspect_run_artifacts.py` 与 `validate_qc_record.py` 对带链吊坠硬编码 expected canonical count=1，却没有先要求最终 analysis 的 `pendant_count=1`。`analysis count=2 + canonical count=1` 可能被 portable 认证。

要求：

- inspector 和 QC validator 都必须在 schema v2 项链对照中逐字段确认 analysis：普通项链 `has_pendant=false/count=0/layer=null`，带链吊坠 `has_pendant=true/count=1/layer=N`；
- 至少新增两个 portable RED：inspector 拒绝 count=2 且中文无 traceback；QC validator 拒绝同类矛盾并不生成/接受错误 checklist；
- portable 脚本不得导入项目 package；保持现有纯 Python 可复制运行边界；
- ring/bracelet v2 仍只做合法 semantics 校验，不追加项链逐字段规则。

## 允许修改

- `src/jewelry_on_hand/models.py`
- `src/jewelry_on_hand/product_fidelity.py`
- `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_skill_portability.py`
- `reference/superpowers/briefs/2026-07-15-v2-final-review-fixes-report.md`

## 验证

先按 finding 分别保存 RED/GREEN，再至少运行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_skill_portability.py -q
uv run pytest tests/test_models.py tests/test_review_decision.py tests/test_generation.py tests/test_prompt_builder.py tests/test_qc.py -q
```

完整报告必须包含每项 RED/GREEN、修改文件、自审，以及合法“禁止新增第二颗吊坠”未被误杀的正向证据。
