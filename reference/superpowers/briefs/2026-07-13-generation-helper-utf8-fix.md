# generation helper UTF-8 解码修复 Brief

## 背景与根因

`run-20260713-double-necklace-04` 的唯一 AIReiter submit 已被平台接受，但 CLI 在 wait 阶段退出 1。Windows 父进程抛出 `UnicodeDecodeError`，随后把 helper 输出误报为非 JSON。

证据链：

- `src/jewelry_on_hand/generation.py::_run_helper()` 使用 `subprocess.run(..., capture_output=True, text=True)`，没有指定编码；Windows 因而使用系统默认 GBK 解码管道。
- `skills/aireiter-image-generation/scripts/aireiter_image_helper.py` 使用 `print(json.dumps(..., ensure_ascii=False, indent=2))` 输出包含中文的 JSON，输出编码为 UTF-8。
- helper 的 UTF-8 字节在父进程 GBK 文本解码线程中触发 `UnicodeDecodeError`；这发生在 JSON 解析前。
- 已提交任务没有被重复提交，随后按相同 `out_task_id` 查询得到真实终态；本修复不得重提该任务。

## 目标

让 `_run_helper()` 跨 Windows/POSIX 均以 UTF-8 可靠读取 helper 的 stdout/stderr，并保持现有测试 monkeypatch 兼容。修复必须针对字节/文本边界，不能放宽 JSON 校验，也不能吞掉 helper 错误。

## TDD 要求

1. 先新增最小失败测试，模拟 helper 返回包含中文字符的 UTF-8 `bytes` stdout；确认当前 `_run_helper()` 因把 bytes 转成 `"b'...'"` 或无法解析而失败。
2. 测试必须断言 subprocess 以二进制模式调用，或等价地证明父进程不再依赖系统默认文本编码。
3. 再做最小生产修复：优先把 `subprocess.run` 改为二进制捕获，并在本模块内统一将 `bytes` 按 UTF-8 解码；为兼容既有 monkeypatch，若返回值已经是 `str` 则原样使用。
4. stdout 和 stderr 必须走同一明确解码策略。无效 UTF-8 不能泄漏原始 traceback；应进入现有中文 `GenerationError` 诊断路径或以安全替换字符保留上下文。
5. 先观察 RED，再观察 GREEN；在报告中记录精确失败与通过输出。

## 范围与隔离

- 允许修改：`src/jewelry_on_hand/generation.py`。
- 优先新增独立测试文件 `tests/test_generation_helper_utf8.py`，避免触碰已含并发戒指改动的 `tests/test_generation.py`。
- 不修改 AIReiter helper、Prompt、QC、scoring、CLI、SPEC、Plan 或历史 run 产物。
- 不调用网络、不执行真实 generate/submit/query，不创建计费。
- `generation.py` 已包含并发戒指工作树改动；只做 `_run_helper` 附近最小补丁，不格式化或回退其他内容。
- 不暂存、不提交。

## 验证

至少运行：

```powershell
python -m pytest tests/test_generation_helper_utf8.py -q
python -m pytest tests/test_generation.py -q
python -m pytest skills/aireiter-image-generation/tests/test_aireiter_image_helper.py -q
```

如果整个工作树仍有外部并发 HERO 测试失败，单独记录，不在本任务内修复。上述覆盖本修复的测试必须全部通过。

## 报告与返回

报告写入 `reference/superpowers/reports/2026-07-13-generation-helper-utf8-fix-report.md`，包含：

- RED/GREEN 精确命令与结果；
- 根因、最小修复和兼容性说明；
- 未触发网络证明；
- 任务专属 diff 自审；
- 关注项。

返回 `DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT` 或 `BLOCKED`，列出修改文件、测试结果和关注项。
