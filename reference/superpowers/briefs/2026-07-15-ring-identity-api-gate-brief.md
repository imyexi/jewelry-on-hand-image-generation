# 最终修复：戒指 generation 公共 API 身份源门禁

## 根因

CLI 正常路径固定把 `input/product-on-hand.jpg` 传给 `run_generation()`，但公共 API 当前仅检查调用方传入的 `product_image` 文件存在。直接调用 `run_generation(paths, paths.input_dir / "product-detail.png", ...)` 时，细节图仍会成为 helper 第二图和 `product-identity` 审计副本，绕过“产品上手图是唯一模型身份源”规则。

## 目标

对已确认品类为戒指的 run，在创建 generation 目录、写 prompt/submit 或调用 helper 之前，强制调用参数 `product_image` 的规范化绝对路径等于当前 run 的 `input/product-on-hand.jpg`。不一致时抛出中文 `GenerationError`，不得静默改写、回退或继续生成。非戒指行为不变。

## 文件

- 修改 `tests/test_generation.py`
- 修改 `src/jewelry_on_hand/generation.py`

## TDD

1. 新增测试：使用 `_ready_ring_run()` 创建合法戒指 run，再创建 `input/product-detail.png`，把该细节图作为 `run_generation()` 的 `product_image` 参数。

目标断言：

- 抛出 `GenerationError`，中文错误明确包含 `input/product-on-hand.jpg` 和“唯一产品身份图”语义；
- helper 调用次数为 0；
- generation 目录保持空；
- 不产生 `product-identity.*`、prompt 或 submit。

先运行并确认 RED：当前代码会继续调用 helper，或者不会抛出预期错误。

2. 最小实现：在读取并确认 `ProductAnalysis` 为 `ProductType.RING` 后，比较：

```python
product_path.resolve()
paths.product_image_path.resolve()
```

若项目没有现成 `product_image_path` 属性，则使用 `paths.input_dir / "product-on-hand.jpg"`。预期上手图也必须存在；不得扫描或选择 `product-detail.*`。

3. 运行新增测试、整个 `tests/test_generation.py` 以及 CLI 戒指四阶段 E2E。

## 约束

- 门禁只对已确认戒指生效；非戒指公共 API 行为不变。
- 不改变 helper 两图顺序、Rank/模型切换、Prompt 压缩、审计副本命名或 QC。
- 目标文件已有其他未提交改动，只做局部修改。
- 不执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
