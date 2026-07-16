# Task 2 实施报告：v2 builder、零敏感词与结构交叉校验

## 状态

Task 2 已完成，未提交、未暂存、未切分支。普通项链与带链吊坠现在由独立 v2 builder 生成结构化 `pendant_semantics`；手串与戒指继续生成 v1。

## RED 证据

### Builder RED

先加入两类项链 builder 测试，再运行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "builder" -v
```

结果：退出码 1，收集 31 项、选中 3 项，`3 failed, 28 deselected`。

- 普通项链仍输出 `schema_version=1`，未生成 absent contract。
- 带链吊坠仍输出 `schema_version=1`，未生成 present contract。
- 跑环样例沿用旧规则文本并触发项链/手串语义冲突，证明 builder 尚未隔离项链规则文本。

### 结构门禁 RED

随后加入 10 个自由文本路径 × 5 个敏感词矩阵，以及错层和缺失可追溯项测试，再运行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "absent_v2 or conflict or wrong_layer or traceable" -v
```

结果：退出码 1，收集 85 项、选中 53 项，`53 failed, 32 deselected`。

- 50 个 absent 注入用例均未得到带精确字段路径的拒绝。
- present builder、错层 contract 和缺失 `must_keep` 均因旧 v1/无结构交叉校验失败。
- 测试均先于生产代码修改落盘；未删除既有攻击文本。

## 实现

### 项链 v2 builder

- `build_product_fidelity_constraints()` 将 `necklace`、`pendant_necklace` 分流到 `_build_necklace_v2_fidelity_constraints()`；ring 分支和 bracelet 通用 v1 分支保持原有版本。
- 普通项链只按最终规范化 analysis 输出 `absent/0/null/forbid`；带链吊坠只按规范字段输出 `present/1/pendant_layer/forbid`。
- 带链吊坠第一阶段要求 `pendant_count == 1`，否则明确报错“第一阶段只支持 1 颗主吊坠”。
- present canonical 创建唯一主吊坠 `must_keep`，保留产品图源文本、位置、可见形状、连接关系和 `第 N 层` 追溯信息。
- 非吊坠细节仍可匹配 `KEYWORD_RULES`，但明确跳过吊坠 rule；污染源句退化到安全 alias，规则模板中的五个敏感词统一替换为“垂饰”。跑环规则中的手串专用“主珠”仅在项链专用文本中收敛为“相邻珠体”。

### 统一 v2 校验

- SHA-256 绑定校验后，所有项链统一进入 `_validate_v2_pendant_semantics()`。
- v1 项链 canonical 明确只读并要求新建 run、重新执行 `prepare-review`。
- analysis/canonical 冲突错误同时包含 `analysis`、`canonical` 和 `prepare-review`。
- absent contract 对 `detected_keywords`、`must_not_change` 及 `must_keep` 八类子字段逐项执行纯字符串检查，五个敏感词任一命中即报告精确索引路径。
- present contract 要求有且只有一个敏感关键词归一项，并要求其 `relationship` 包含结构化 `第 N 层`。
- 历史 `_has_positive_pendant_semantics()` 保留但不再参与 v2 项链 correctness gate。

### I1 测试迁移

- run04 与全部复合否定输入现在断言 builder 输出 v2 absent contract，且敏感文本不进入 canonical 自由文本。
- 所有手工写入 absent v2 的吊坠文本，无论否定、禁止创建、禁止保留或破坏语气，均统一拒绝。
- 原负向别名、混合分句、连接词、显式不存在、创建禁止、保留禁止和破坏禁止攻击文本全部保留。
- 附件实物仍按“同一条海蓝宝长链绕颈双圈”的普通项链处理，没有创建两件项链、吊坠或三圈吊坠 proof。

## GREEN 与回归证据

简报指定聚焦 GREEN：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_final_necklace_important_fixes.py -k "pendant or canonical or run04" -v
```

结果：退出码 0，`136 passed, 32 deselected in 0.26s`；没有真实 provider 调用。

完整 Task 2 两文件回归：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_final_necklace_important_fixes.py -v
```

结果：退出码 0，`168 passed in 0.45s`。

Task 1 模型接口回归：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_models.py -q
```

结果：退出码 0，`244 passed in 0.16s`。

bracelet/ring 与 prompt 兼容回归：

```powershell
uv run pytest tests/test_product_analysis.py tests/test_prompt_builder.py -q
```

结果：退出码 0，`77 passed in 0.18s`。

## 改动文件

- `src/jewelry_on_hand/product_fidelity.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_final_necklace_important_fixes.py`
- `reference/superpowers/briefs/2026-07-14-v2-task-2-report.md`

## 双阶段自审

### 规格审查

- contract 决策只读取最终规范化 `ProductAnalysis` 字段；alias/NLP 仅用于提取非吊坠细节，不决定 presence。
- absent 10 个自由文本路径 × 5 个敏感词全部覆盖，并验证精确字段路径。
- present 主吊坠项唯一、可追溯且与 `pendant_layer` 一致。
- 冲突错误包含 analysis、canonical 和 `prepare-review`。
- run04 普通双圈长链保持单件、无吊坠语义。

### 质量审查

- v2 gate 不再调用旧词法极性判断。
- bracelet/ring v1 分支没有改为 v2，相关测试保持通过。
- `git diff --check` 无空白错误，仅有仓库既有的 Windows 行尾提示。
- 首轮自审未发现 Critical/Important；后续独立 reviewer 发现的 1 个 Important 已按下节 TDD 证据修复。

## 关注项

- 当前环境没有安装 `ruff`，`uv run ruff check ...` 返回 `program not found`；本任务没有安装依赖，改以 pytest、`git diff --check` 和逐项源码审查完成验证。
- 工作树原本包含 Task 1 及其他并发/历史改动；本任务未回退、暂存或提交这些改动。

## Reviewer 修复：绕过 builder 的多吊坠交叉校验

### 审查结论

- Important 成立：builder 会拒绝 `pendant_count=2`，但统一 validator 原先只按品类构造 count=1 的 expected contract；手工重绑 SHA 后，count=2 analysis 可以绕过 builder 并被直接校验放行。
- Minor 成立：旧四词词法常量名称没有显式说明只服务 v1，容易与 v2 五词门禁混淆。

### RED

先构造 count=2 的最终 analysis，再从合法 count=1 builder 取得 v2 constraints，并只把 `source.product_analysis_sha256` 重绑到 count=2 analysis；直接调用 validator：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "builder_is_bypassed" -v
```

结果：退出码 1，`1 failed, 85 deselected in 0.06s`；失败为 `DID NOT RAISE ValueError`，证明绕过路径真实存在。

### 最小修复与聚焦 GREEN

- `_validate_v2_pendant_semantics()` 现在直接要求带链吊坠 analysis 的 `pendant_count == 1`，不依赖 builder。
- count 冲突错误包含带标签的 `analysis ... count=2`、`canonical ... count=1` 和 `prepare-review`。
- `_PENDANT_CANONICAL_KEYWORDS` 改名为 `_V1_PENDANT_CANONICAL_KEYWORDS`，并用中文注释说明 v2 使用完整五词集合；全部旧词法引用已同步。

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "builder_is_bypassed or wrong_layer or plain_necklace_rejects_present_contract" -v
```

结果：退出码 0，`4 passed, 82 deselected in 0.04s`。

### 双圈附件事实补证

新增 run04 明确断言：`layer_count=2`、`is_independent_multi_item=false`、canonical 为 `absent/0/null/forbid`，并且不出现“三圈”“第三圈”“第 3 层”或五类吊坠敏感词。该测试只读取既有 analysis，不创建或提交真实 proof。

### Reviewer 修复回归

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_final_necklace_important_fixes.py -q
```

结果：退出码 0，`170 passed in 0.45s`。

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_models.py -q
```

结果：退出码 0，`245 passed in 0.16s`。
