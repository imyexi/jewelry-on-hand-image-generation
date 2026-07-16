# Task 1 实施报告：canonical v1/v2 模型与序列化

## 状态

DONE。

提交：无（按计划禁止提交实现改动）。

## 实现内容

- 在 `src/jewelry_on_hand/models.py` 增加 `PendantPresence`、`PendantCreationPolicy` 与冻结数据类 `PendantSemantics`。
- `PendantSemantics` 严格校验 presence、count、layer、creation_policy 及其组合关系：第一阶段只允许 absent/0/null 或 present/1/1..3，并固定禁止自动创建吊坠。
- 将 `ProductFidelityConstraints` 扩展为显式支持 schema v1/v2，并增加可空字段 `pendant_semantics`。
- v1 只接受缺失或 null 的 pendant_semantics，序列化时不写入新键，保持既有 payload 原样 round-trip。
- v2 必须显式提供 pendant_semantics 对象，反序列化为类型对象并在序列化时写回结构化对象；没有 v1 到 v2 的自动推断或升级。
- `schema_version` 在 `from_dict()` 中只接受真实整数 1/2，显式拒绝 bool 和字符串；count 的合法零只接受真实整数零，避免 bool、0.0 或字符串冒充整数。

## RED 证据

### Round-trip RED

命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "round_trip" -v
```

结果：退出码 1，收集 0 项并产生 1 个导入错误。关键失败为：

```text
ImportError: cannot import name 'PendantSemantics' from 'jewelry_on_hand.models'
```

这符合预期：测试先引用规格要求的新公共模型，而生产代码尚未定义它；没有通过临时跳过或弱化 import 绕过 RED。

### 非法输入 RED

命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "require or reject" -v
```

结果：退出码 1，同样在收集阶段因 `PendantSemantics` 尚不存在而失败。由于模块 import 是全部测试的前置条件，非法输入用例尚不能进入函数体；这仍然证明实现前目标模型能力缺失，并按简报要求保留了真实 import。

### 自审边界 RED

首轮 GREEN 后自审发现，若只以 `raw_count == 0` 兼容合法零，Python 会把 `0.0` 等值视为零。先增加 count=0.0 的拒绝用例，再运行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -v
```

结果：退出码 1，`1 failed, 16 passed`；关键失败为该用例 `DID NOT RAISE ValueError`。这证明边界问题真实存在。随后将零值分支收紧为 `int` 且排除 `bool`。

## GREEN 与回归

首次实现后命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_models.py -v
```

结果：退出码 0，`175 passed in 0.13s`。

修复自审边界后 fresh 重跑同一命令：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_models.py -v
```

最终结果：退出码 0，`176 passed in 0.12s`。其中新 v2 测试 17 项，既有模型测试全部通过。

## 改动文件

- `src/jewelry_on_hand/models.py`：增加 v2 吊坠语义模型及 ProductFidelityConstraints 的 v1/v2 解析、校验与序列化分支。
- `tests/test_product_fidelity_v2.py`：新增独立 fixture、v1/v2 round-trip、非法 schema、v1/v2 键组合和吊坠字段组合测试，并补充 count=0.0 严格整数边界。
- `tests/test_models.py`：本 Task 未修改；该文件已有并发工作树改动，完整保留并作为聚焦回归运行。

## 双阶段自审

### 规格审查

- v1 原样：测试确认未提供 pendant_semantics 的 v1 payload 反序列化后字段为 None，序列化结果与输入完全相等。
- v2 必填：缺少 pendant_semantics 明确报 `v2 ... pendant_semantics 必填`；合法 absent/present 两种对象均可 round-trip。
- 严格整数：schema 的 bool/字符串被拒绝；count 的 bool 与 0.0 均被拒绝，真实整数 0/1 按组合规则接受。
- 版本边界：只允许 v1/v2；v1 非 null pendant_semantics 被拒绝，v2 不会从其他字段推断吊坠语义。

### 质量审查

- 实现限定在模型目标段和新增测试，没有格式化、覆盖或回退 `models.py`、`test_models.py` 中既有并发改动。
- `to_dict()` 仅在 v2 写入 pendant_semantics，不污染所有既有 v1 fixture。
- 校验错误包含稳定字段名或组合名，测试覆盖每个规格列出的拒绝分支及自审发现的浮点零边界。
- `git diff --check` 无空白错误；仅报告工作树既有 LF/CRLF 转换提示。
- 未发现残留 Critical/Important 问题。

## 关注项

- 当前共享工作树在 Task 开始前已包含 `models.py` 与 `test_models.py` 的其他并发改动；本 Task 未尝试分离、暂存或提交这些改动。
- 本报告与实现均未执行 `git add`、`git commit` 或切换分支。

## Reviewer finding 修复补充

本节记录 reviewer 返回的 2 个 Important 与 1 个 Minor 的修复结果，并取代前述首轮自审中关于“无残留 Important 问题”和直接构造覆盖度的结论。

### Finding 验证与根因

- 已确认 `ProductFidelityConstraints` 直接构造时，`schema_version=1.0` 会因 Python 的 `1.0 == 1` 穿透集合成员判断并被接受。
- `schema_version=2.0` 会错误进入 v2 分支并报告 pendant_semantics 缺失，而不是拒绝 schema 类型。
- 不可哈希 schema 值会在 `value not in {1, 2}` 处泄漏 `TypeError`，没有形成稳定中文 `ValueError`。
- 直接构造的 v1/v2 pendant_semantics 分支与 `PendantSemantics.layer` 运行时边界此前缺少显式测试；测试文件还存在未使用的 `json` import。

根因是 `ProductFidelityConstraints.__post_init__()` 在确认 schema 是真实整数之前先执行集合成员判断。修复后先拒绝 bool 与所有非 int，再在已知可哈希的整数上判断 1/2。

### 修复 RED

先增加 10 项直接构造测试，覆盖 schema_version=1.0、2.0、True、不可哈希列表，v1 非空语义，v2 缺失语义，v2 raw mapping 自动转换，以及 layer=True、1.0、4。生产实现未修改前运行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "direct" -v
```

结果：退出码 1，`3 failed, 7 passed, 17 deselected`。三个关键失败分别为：

- `schema_version=1.0`：`DID NOT RAISE ValueError`。
- `schema_version=2.0`：实际错误为 v2 pendant_semantics 必填，与预期 schema 中文错误不匹配。
- 不可哈希列表：在集合成员判断处抛 `TypeError: unhashable type: 'list'`。

这三项精确复现 reviewer finding；其余 7 项证明既有直接构造约束行为正确，仅缺少回归保护。

### 修复 GREEN 与回归

最小修复 `ProductFidelityConstraints.__post_init__()` 后重跑直接构造测试：

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "direct" -v
```

结果：退出码 0，`10 passed, 17 deselected in 0.03s`。

删除未使用的 `json` import 后运行完整 Task 1 聚焦回归：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_models.py -q
```

结果：退出码 0，`186 passed in 0.11s`。

### Reviewer 修复改动文件

- `src/jewelry_on_hand/models.py`：将直接构造的 schema 校验拆成“先验证非 bool 的 int，再验证值域 1/2”两步。
- `tests/test_product_fidelity_v2.py`：增加 10 项直接构造覆盖，删除未使用的 `json` import。
- `reference/superpowers/briefs/2026-07-14-v2-task-1-report.md`：追加本次 reviewer 修复证据。

`tests/test_models.py` 仍未由本 Task 修改，只参与回归。

### Reviewer 修复自审

- `schema_version` 直接构造和 `from_dict()` 现在都拒绝 float、bool、字符串及不可哈希非整数，并统一抛含 `schema_version` 的中文 `ValueError`。
- 类型检查先于集合成员判断，不再存在 float 等值穿透或不可哈希异常泄漏。
- v1 非空语义、v2 缺失语义、v2 mapping 转模型的三个 `__post_init__` 分支均有直接构造测试。
- `PendantSemantics.layer` 的 bool、float、越界整数三个直接构造边界均有回归测试。
- 未使用 import 已删除；未修改、暂存或提交范围外文件。
- reviewer 返回的 2 个 Important 与 1 个 Minor 均已修复，未发现新的 Critical/Important 问题。

## Reviewer 语言 Minor 修复补充

- 将 schema_version 直接构造参数化用例的英文 ID `float-v1`、`float-v2`、`bool`、`unhashable` 分别改为中文 `浮点数-v1`、`浮点数-v2`、`布尔值`、`不可哈希列表`。
- 未调整测试逻辑或生产实现。
- 验证命令：`uv run pytest tests/test_product_fidelity_v2.py -q`。
- 验证结果：退出码 0，`27 passed in 0.03s`。
- 未暂存、未提交，也未修改其他文件。
