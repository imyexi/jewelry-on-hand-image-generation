# Task 3：record-decision 与 generation 生命周期门禁实施报告

## 状态

- 状态：完成。
- 提交：无；未执行 `git add`、`git commit`、切分支或推送。
- 范围：仅修改 Task 3 允许的生产/测试文件，并按要求新增本报告。
- 生产实现结论：Task 2 已经把唯一校验器接入正确生命周期位置；本 Task 没有复制校验规则，只在 generation 入口补充门禁时机注释。

## 需求与实现核对

### record-decision

- `write_review_bundle()` 的现有顺序保持为：解析最终 analysis，校验 decision/confirmation snapshot，读取导入 canonical，调用 `validate_product_fidelity_constraints()` 校验 SHA、v2 结构及自由文本交叉约束，形成 payload，最后进入 `_commit_json_transaction()`。
- 新增 v1 项链测试用已有 analysis、decision、canonical 字节作为哨兵，并 monkeypatch `os.replace`。断言统一错误包含“历史 v1 只读”及 `prepare-review`，`os.replace` 调用数为 0，三个原文件逐字节不变。
- reviewer 复审后新增冲突 v2 项链事务测试：把带链吊坠 canonical 的结构层从第 2 层篡改为第 1 层，断言“吊坠结构冲突”发生在任何 `os.replace` 前，analysis、decision、canonical 三个已有文件仍逐字节不变。
- CLI 新增同类端到端测试：返回非零、stderr 包含“历史 v1 只读”、analysis 字节不变，且不创建 decision/canonical。

### generation

- `require_generation_decision()` 的现有顺序保持为：读取 decision，校验 snapshot，读取 canonical，执行 `require_confirmed_constraints()`，再调用 `validate_product_fidelity_constraints()`，最后才返回 decision。
- `run_generation()` 首句继续调用 `require_generation_decision()`；在 `_prepare_generation_dir()`、任何 generation 子目录/文件写入以及 `_run_helper()` 之前 fail closed。新增一行中文注释固定这一生命周期约束。
- 参数化测试覆盖 v1、普通项链错误 `presence=present`、带链吊坠错误 layer 三种 canonical；reviewer 复审后增加 `_prepare_generation_dir`、`Path.write_text`、`shutil.copy2`、`_run_helper` 四层调用哨兵，三种情况的四类调用均为空，且 generation 根目录为空。
- 合法 v2 使用本地 fake helper，`wait=False`，确认恰好到达 helper 一次；没有调用真实 provider 或网络下载。

### 测试工厂与兼容回归

- `tests/test_review_decision.py::_constraints_data()` 在传入 analysis 时复制 builder 的 `schema_version`，并仅在 builder 为 v2 时复制 `pendant_semantics`；未传 analysis 的历史手串 fixture 仍为 v1。
- `tests/test_cli.py::make_constraints()` 采用同一规则，避免把项链 v2 builder 结果错误包装为 v1。
- 将三个既有 fixture 调整为真正合法的 v2 前置数据后再验证原目标：手串自由文本冲突、同品类人工纠正 must_keep 保留、跨品类 must_keep 语义拒绝。未放宽生产校验。

## TDD 与测试时序证据

1. 新增四组生命周期测试后，首次单独运行收集 6 个 case，结果为 `6 passed`。这说明现有 Task 2 生产顺序已经满足要求；这些测试全部是 characterization，不是真正 RED。
2. 首次运行简报 Step 4 宽筛选：`22 passed, 1 failed`。失败是旧“手串 v1 导入项链”fixture 被新的 v1 优先门禁正确截断，无法到达它原要覆盖的手串自由文本分支；将 fixture 构造成结构合法 v2 后，宽筛选为 `23 passed, 187 deselected`。
3. I2-I4 指定回归：`21 passed, 63 deselected`。覆盖 null length、unknown 正向纠正、prepare 前重评分、晚期参考适配字段拒绝，以及生成前参考图路径/SHA/策略复核。
4. 首次 Task 3 全回归：`292 passed, 2 failed`。两项均为旧 fixture 未满足 v2 前置结构：人工纠正 relationship 缺少精确“第 2 层”，以及跨品类测试覆盖掉唯一吊坠 must_keep。最小修正 fixture 后，三个相关参数化 case 为 `3 passed`。
5. 修正后 Task 3 全回归：`294 passed`。
6. 加强 v1 原字节哨兵断言后，四组新增测试再次运行：`6 passed`。
7. reviewer 指出的 Important 证据缺口修复后，非法 generation 三个参数 case 与冲突 v2 before-replace 事务测试首跑为 `4 passed`；现有生产顺序直接满足，仍属于 characterization。
8. reviewer 修复后的新鲜验证：I2-I4 为 `21 passed, 63 deselected`；Task 3 四套件为 `295 passed`。

## 文件改动

- `src/jewelry_on_hand/generation.py`：增加生命周期门禁必须早于 generation 写入和 helper/provider 调用的注释；执行顺序不变。
- `tests/test_review_decision.py`：升级约束工厂；新增 v1 与冲突 v2 的 before-replace 原字节保护测试；修正三个既有 v2 fixture 的结构合法性。
- `tests/test_generation.py`：新增非法 v1/冲突 v2 的目录准备、文本写入、复制、helper 四层零调用参数化测试，以及合法 v2 到达 fake helper 测试。
- `tests/test_cli.py`：升级约束工厂；新增 CLI v1 项链无写入测试。
- `src/jewelry_on_hand/review_decision.py`、`src/jewelry_on_hand/cli.py`：本 Task 未增加生产逻辑；复核并保留现有唯一 validator 调用与 CLI 二次校验。
- `tests/test_final_necklace_important_fixes.py`：本 Task 未修改，仅作为 I2-I4 回归套件执行。

## 双阶段自审

### 规格审查

- v1/冲突 v2 均在 `os.replace` 前拒绝；两类测试分别直接证明 analysis、decision、canonical 原字节不变。
- generation 非法 canonical 在 generation 目录准备、文本写入、参考图复制和 helper/provider 调用前拒绝；三类非法输入的四层调用均为 0。
- 合法 v2 到达本地 fake helper 一次，不触发真实 provider。
- 历史 v1 复制到新 run 仍由统一错误拒绝，没有自动推断 `pendant_semantics`、schema 改写或摘要重绑。

### 质量审查

- 复用 `validate_product_fidelity_constraints()`，没有新增第二套词法或结构判断。
- `write_review_bundle()` 原子事务仍只在所有前置校验通过后启动，回滚语义未退化。
- 测试 mock 仅隔离事务 `os.replace`、generation 目录准备、文本写入、参考图复制、helper/provider 和下载边界；断言验证真实门禁副作用，不验证 mock 自身。
- reviewer 指出的 1 个 Important 测试证据缺口与 1 个 record-decision 关注项均已补齐；当前未发现剩余 Critical 或 Important 问题。

## 关注项

- 新增测试没有产生真正 RED，因为 Task 2 已提前完成所需生产接线；报告已按要求明确标记为 characterization。
- 工作区存在大量其他并发历史修改；本 Task 未回退、暂存或提交它们。
- pytest 在 Windows 控制台输出的工作区中文根路径显示乱码，但测试名称、退出码与断言执行正常，不影响结果。
