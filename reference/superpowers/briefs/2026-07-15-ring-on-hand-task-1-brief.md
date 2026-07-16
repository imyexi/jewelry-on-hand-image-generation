# 任务 1：generation 固定使用产品上手图

## 目标

戒指生成时，helper 的第一张 `--image` 保持为选定 Rank 的手部构图参考图；第二张 `--image` 固定为调用方传入的产品上手图。CLI 场景中即 `input/product-on-hand.jpg`。戒指 generation 同时保存内容完全一致的 `product-identity.jpg`。

## 文件

- 修改 `tests/test_generation.py`
- 修改 `src/jewelry_on_hand/generation.py`

## TDD 步骤

1. 将现有 `test_ring_generation_prefers_reviewed_product_detail_and_copies_audit_image` 改为以下目标行为测试：

```python
def test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    detail = paths.input_dir / "product-detail.png"
    detail.write_bytes(b"reviewed ring detail")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-on-hand"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generated = run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    command = calls[0]
    first = command.index("--image") + 1
    second = command.index("--image", first) + 1
    assert command[second] == str(product)
    assert str(detail) not in command
    assert (generated[0] / "product-identity.jpg").read_bytes() == product.read_bytes()
```

2. 先运行并确认 RED：

```powershell
py -m pytest tests\test_generation.py::test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail -q
```

失败必须来自旧实现仍把 `product-detail.png` 作为第二张图。

3. 最小实现：

```python
product_identity_path = product_path
```

仅戒指始终复制审计身份图：

```python
if product is not None and product.confirmed_product_type is ProductType.RING:
    shutil.copy2(
        product_identity_path,
        generation_dir / f"product-identity{product_identity_path.suffix.lower()}",
    )
```

删除不再使用的 `_product_identity_path()`，不得改变 `_submit_command()` 的图像顺序、Rank 重试逻辑或非戒指行为。

4. 确认 GREEN，并运行整个 generation 测试文件：

```powershell
py -m pytest tests\test_generation.py::test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail -q
py -m pytest tests\test_generation.py -q
```

## 全局约束

- 细节图继续用于 review、结构分析、canonical 和人工 QC，但不得进入任何 AIReiter `--image` 参数，也不得作为第三张模型输入。
- 不改变参考图 Top 3、Prompt、失败码纠偏和模型切换策略。
- 当前工作区存在大量用户及并发改动，不得回滚、覆盖或顺带修改。只修改本任务指定位置。
- 由于目标文件已有未提交改动，本任务不要执行 `git add` 或 `git commit`，避免把既有修改一并提交。
