# 戒指 generation 公共 API 身份源门禁修复报告

## 结论

已完成戒指 `run_generation()` 公共 API 身份源门禁及审查修复。对最终 `ProductAnalysis.confirmed_product_type` 为 `ring` 的 run，当前 run 的 `input/product-on-hand.jpg` 必须存在，且调用参数 `product_image` 的规范化绝对路径必须等于该文件；缺失或不一致均立即抛出中文 `GenerationError`。门禁不会静默改写或回退到其他图片，非戒指缺失产品图仍由通用检查抛出 `FileNotFoundError`。

## 根因与副作用边界

此前 CLI 正常路径会传入 `input/product-on-hand.jpg`，但 `run_generation()` 只验证调用方传入文件存在，并直接把该参数用于 helper 第二图和 `product-identity.*` 审计副本。公共 API 因此可以传入 `input/product-detail.png`，绕过“上手图是唯一产品身份源”的约束。

首轮门禁加入后，通用 `_ensure_file(product_path, "产品图不存在")` 仍位于读取 `ProductAnalysis` 之前。当戒指调用方传入规范路径但该文件缺失时，流程会提前抛出 `FileNotFoundError`，使要求包含明确身份图语义的中文 `GenerationError` 分支不可达。审查修复将通用产品图存在性检查移到 ProductAnalysis/戒指门禁之后，但仍置于所有生成副作用之前。

修复位于 `ProductAnalysis` 成功读取后、确认品类为戒指的分支内，并早于模型选择、generation job 构建、generation 目录写入、prompt/submit 写入、审计副本复制和 helper/provider 调用：

1. 固定预期路径为当前 run 的 `input/product-on-hand.jpg`，不扫描或选择任何 `product-detail.*`。
2. 预期上手图不存在时抛出中文 `GenerationError`。
3. 比较调用参数与预期路径的 `resolve()` 结果；不相等时抛出包含 `input/product-on-hand.jpg` 和“唯一产品身份图”语义的中文 `GenerationError`。
4. 戒指门禁通过后再执行通用产品图存在性检查；非戒指缺失产品图仍抛出原有 `FileNotFoundError`。
5. 以上检查均早于模型选择、generation history/job 构建、generation 目录与文件写入以及 helper/provider 调用。

## TDD 证据

### 第一轮 RED：拒绝 detail 图身份源

先新增 `test_ring_generation_rejects_detail_image_as_public_api_identity_source`，使用 `_ready_ring_run()` 创建合法戒指 run，再把新建的 `input/product-detail.png` 直接传给 `run_generation()`。测试同时要求：

- 抛出目标 `GenerationError`；
- 错误包含 `input/product-on-hand.jpg` 和“唯一产品身份图”；
- helper 调用次数为 0；
- generation 目录保持空；
- 不产生 `product-identity.*`、`prompt.txt` 或 `submit.json`。

生产代码未修改时执行：

```text
python -m pytest tests/test_generation.py::test_ring_generation_rejects_detail_image_as_public_api_identity_source -q --basetemp output/pytest-ring-identity-api-gate-red
```

退出码为 `1`，结果为 `1 failed`，精确失败原因为 `Failed: DID NOT RAISE GenerationError`。这证明测试命中了公共 API 缺少门禁的既有行为，而不是夹具或语法错误。

### 第一轮 GREEN

加入最小路径门禁后执行：

```text
python -m pytest tests/test_generation.py::test_ring_generation_rejects_detail_image_as_public_api_identity_source -q --basetemp output/pytest-ring-identity-api-gate-green
```

退出码为 `0`，结果为 `1 passed in 0.06s`。测试确认拒绝发生在所有 generation/helper 副作用之前。

### 审查 RED：规范身份图缺失

随后新增 `test_ring_generation_reports_missing_canonical_identity_as_generation_error`：使用 `_ready_ring_run()` 创建合法戒指 run 后删除 `input/product-on-hand.jpg`，仍以该规范路径调用 `run_generation()`，并断言中文 `GenerationError`、helper 零调用、generation 目录为空以及不产生 identity/prompt/submit。

生产检查顺序尚未调整时执行：

```text
python -m pytest tests/test_generation.py::test_ring_generation_reports_missing_canonical_identity_as_generation_error -q --basetemp output/pytest-ring-identity-api-gate-missing-red
```

退出码为 `1`，结果为 `1 failed`。堆栈精确显示 `run_generation()` 在读取 ProductAnalysis 前由 `_ensure_file(product_path, "产品图不存在")` 抛出 `FileNotFoundError`，证明目标中文 `GenerationError` 分支不可达。

### 审查 GREEN

将通用产品图存在性检查移到 ProductAnalysis/戒指身份门禁之后，再同时运行两个门禁测试：

```text
python -m pytest tests/test_generation.py::test_ring_generation_rejects_detail_image_as_public_api_identity_source tests/test_generation.py::test_ring_generation_reports_missing_canonical_identity_as_generation_error -q --basetemp output/pytest-ring-identity-api-gate-two-green
```

退出码为 `0`，结果为 `2 passed in 0.08s`。detail 图与缺失规范上手图都在 helper 和 generation 副作用之前被中文 `GenerationError` 拒绝。

## 回归验证

完整 generation 测试：

```text
python -m pytest tests/test_generation.py -q --basetemp output/pytest-ring-identity-api-gate-generation-review
```

退出码为 `0`，结果为 `106 passed in 0.74s`。

戒指 CLI 四阶段端到端测试：

```text
python -m pytest tests/test_cli.py::test_cli_end_to_end_ring_four_stage_workflow -q --basetemp output/pytest-ring-identity-api-gate-cli-e2e-review
```

退出码为 `0`，结果为 `1 passed in 0.18s`。该 E2E 使用本地假 helper，不提交真实生成任务。

## 修改范围与顾虑

仅局部修改以下目标文件：

- `src/jewelry_on_hand/generation.py`
- `tests/test_generation.py`
- `reference/superpowers/reports/2026-07-15-ring-identity-api-gate-report.md`

未改变 helper 两图顺序、Rank/模型切换、Prompt 压缩、审计副本命名或 QC；未执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。工作区在任务开始前已有大量其他未提交改动，本修复未回滚、格式化或顺带修改这些内容。

当前无已知功能性顾虑。路径门禁按 brief 使用规范化绝对路径比较，因此同一路径的等价表示可通过，而指向 detail 文件的不同路径会被拒绝。
