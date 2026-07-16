# 戒指产品上手身份图：任务 1 实施报告

## 状态

`DONE_WITH_CONCERNS`

功能与指定测试均已完成并通过。顾虑仅来自工作区现状：两个目标代码文件在本任务开始前已有大量未提交改动，本任务没有提交、暂存、回滚或覆盖这些既有改动。

## 需求落实

- 戒指 generation 的第一张 `--image` 仍由现有 `_submit_command()` 使用所选 Rank 的手部构图参考图。
- 第二张 `--image` 固定使用调用方传入的产品上手图；CLI 场景对应 `input/product-on-hand.jpg`。
- 戒指每个 generation 目录保存与产品上手图内容完全一致、后缀一致的 `product-identity` 审计图。
- `product-detail.*` 不再参与 generation 的任何 AIReiter `--image` 参数。
- 删除不再使用的 `_product_identity_path()`。
- 未修改 `_submit_command()` 的图像顺序、Rank 重试、Prompt、失败码纠偏、模型切换或非戒指行为。

## TDD 记录

### RED：先修改测试

将原测试 `test_ring_generation_prefers_reviewed_product_detail_and_copies_audit_image` 替换为指定目标行为测试 `test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail`，随后在未修改生产代码时运行：

```powershell
py -m pytest tests\test_generation.py::test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail -q
```

结果：退出码 `1`，`1 failed in 0.14s`。

关键失败：

```text
assert command[second] == str(product)
AssertionError: ...\product-detail.png != ...\product-on-hand.jpg
```

失败原因符合要求：旧实现仍将 `product-detail.png` 作为第二张模型输入，不是测试语法、夹具或环境错误。

### GREEN：最小生产代码修改

仅做以下生产代码变更：

```python
product_identity_path = product_path
```

并将审计图复制条件改为仅当完整产品分析确认类别为戒指时执行：

```python
if product is not None and product.confirmed_product_type is ProductType.RING:
    shutil.copy2(
        product_identity_path,
        generation_dir / f"product-identity{product_identity_path.suffix.lower()}",
    )
```

同时删除不再使用的 `_product_identity_path()`。

目标单测：

```powershell
py -m pytest tests\test_generation.py::test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail -q
```

结果：退出码 `0`，`1 passed in 0.07s`。

完整 generation 测试文件：

```powershell
py -m pytest tests\test_generation.py -q
```

结果：退出码 `0`，`99 passed in 1.27s`。

## 完成前复核

按完成前验证流程重新运行完整测试：

```powershell
py -m pytest tests\test_generation.py -q
```

最新结果：退出码 `0`，`99 passed in 0.61s`。

另外检查：

```powershell
rg -n -C 8 "product_identity_path =|product-identity|def _product_identity_path|product-detail" src/jewelry_on_hand/generation.py tests/test_generation.py
git diff --check -- src/jewelry_on_hand/generation.py tests/test_generation.py
```

核验结论：

- `generation.py` 使用 `product_identity_path = product_path`。
- 审计图复制仅由戒指类别条件触发。
- `generation.py` 中已无 `_product_identity_path()` 和 `product-detail` generation 路径。
- `product-detail.png` 仅存在于回归测试，且测试明确断言它不在 helper 命令中。
- `git diff --check` 未报告空白错误；只出现 Git 对两个既有混合行尾文件的 LF→CRLF 提示。

## 文件变化

- `src/jewelry_on_hand/generation.py`：固定产品身份图为调用方产品图；戒指始终复制该审计图；删除旧细节图选择 helper。
- `tests/test_generation.py`：将旧行为测试替换为指定目标行为回归测试。
- `reference/superpowers/reports/2026-07-15-ring-on-hand-task-1-report.md`：新增本实施报告。

## 提交与工作区保护

- 未执行 `git add`。
- 未执行 `git commit`。
- 未执行 `stash`、`checkout`、`reset` 或任何回滚操作。
- 本任务操作范围仅限获准的两个代码文件及本报告文件。

## 顾虑

- `src/jewelry_on_hand/generation.py` 与 `tests/test_generation.py` 在任务开始前均已存在规模较大的未提交修改；本任务只做上述局部改动，无法用单一 Git 提交边界将其与既有工作完全隔离。
- Git 对这两个文件报告“下次触碰时 LF 将替换为 CRLF”的工作区行尾提示；本任务未进行全文件格式化或行尾归一化，以免扩大改动范围。
- 本任务按简报只运行目标单测及 `tests/test_generation.py`，未运行项目全量测试套件。
