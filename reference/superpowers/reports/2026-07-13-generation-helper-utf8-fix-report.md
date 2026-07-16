# generation helper UTF-8 解码修复报告

## 状态

`DONE`

## 根因

`src/jewelry_on_hand/generation.py::_run_helper()` 使用 `subprocess.run(..., text=True)` 捕获 helper 输出，使 Windows 父进程在 JSON 解析前先按系统默认编码解码。helper 实际输出的是包含中文的 UTF-8 JSON，因此在 GBK 环境可抛出 `UnicodeDecodeError`。同时，原实现对测试替身返回的 `bytes` 直接调用 `str(...)`，会得到 `"b'...'"` 而不是 JSON 文本。

## RED

命令：

```powershell
python -m pytest tests/test_generation_helper_utf8.py -q
```

结果：退出码 `1`。

```text
FF                                                                       [100%]
FAILED tests/test_generation_helper_utf8.py::test_run_helper_decodes_utf8_bytes_without_platform_default_encoding
FAILED tests/test_generation_helper_utf8.py::test_run_helper_safely_decodes_invalid_utf8_in_diagnostics
2 failed in 0.33s
```

失败原因与目标缺口一致：第一个测试在 `json.loads` 处拿到字节 repr，进入“AIReiter helper 返回非 JSON”路径；第二个测试确认 stdout/stderr 都未安全解码。

## 最小修复

- 将 `_run_helper()` 的 subprocess 捕获改为 `text=False`，明确在二进制边界接收 stdout/stderr，不再依赖 Windows 系统默认文本编码。
- 新增模块内 `_decode_helper_stream()`，stdout 和 stderr 共用同一策略：`bytes` 按 UTF-8 解码，无效字节用 `�` 安全替换；已是 `str` 则原样返回。
- JSON 解析、JSON 对象类型校验、非零退出码处理和中文 `GenerationError` 路径均未放宽。

## GREEN 与回归

```powershell
python -m pytest tests/test_generation_helper_utf8.py -q
```

```text
..                                                                       [100%]
2 passed in 0.32s
```

```powershell
python -m pytest tests/test_generation.py -q
```

```text
........................................................................ [ 85%]
............                                                             [100%]
84 passed in 0.71s
```

```powershell
python -m pytest skills/aireiter-image-generation/tests/test_aireiter_image_helper.py -q
```

```text
............                                                             [100%]
12 passed in 0.06s
```

现有 `tests/test_generation.py` 的 fake subprocess 签名仍接收 `text` 关键字参数，本修复仅将其值由 `True` 改为 `False`，84 个回归测试通过证明了既有 monkeypatch 兼容性。

完成前将三组覆盖范围合并后重新运行：

```powershell
python -m pytest tests/test_generation_helper_utf8.py tests/test_generation.py skills/aireiter-image-generation/tests/test_aireiter_image_helper.py -q
```

```text
........................................................................ [ 73%]
..........................                                               [100%]
98 passed in 0.56s
```

## 未触发网络证明

本任务仅执行了本地文件读取、Git 只读检查和上述 pytest 命令。新增测试完全 monkeypatch `generation.subprocess.run`；未运行 CLI、`generate`、真实 helper、submit、wait 或 query，未重提 `run-20260713-double-necklace-04`，未创建计费任务。

## 任务专属 diff 自审

- `src/jewelry_on_hand/generation.py`：只在 `_run_helper` 附近改动 `text` 模式、stdout/stderr 转换和新增 6 行解码函数；未格式化、回退或覆盖该文件中已有的并发戒指改动。
- `tests/test_generation_helper_utf8.py`：独立新增 2 个回归测试，未触碰已有 `tests/test_generation.py`。
- `output/generation-helper-utf8-test-log.md`：保存本任务 RED/GREEN 与回归测试过程。
- `reference/superpowers/reports/2026-07-13-generation-helper-utf8-fix-report.md`：按 brief 新增本报告。
- `git diff --check -- src/jewelry_on_hand/generation.py tests/test_generation_helper_utf8.py` 退出码为 `0`，仅有 Git 的 LF/CRLF 工作区提示，无空白错误。
- 未修改 helper、CLI、scoring、QC、SPEC、Plan 或历史 run 产物；未暂存、未提交。

## 关注项

- 工作树原本存在大量其他未提交改动，包括 `generation.py` 中的并发戒指改动；本任务已保留它们，没有将其纳入修复范围。
- 按 brief 只运行了指定的三组测试，未运行整树测试；本任务覆盖的测试均通过。

## 复审整改 Fix Report（2026-07-13）

### 整改状态

`DONE`

`.superpowers/sdd/generation-helper-utf8-fix-review.md` 提出的 2 项 Important 已按独立 RED→GREEN 循环修复；Minor 所指的 RED 证据缺口已在本节和 `output/generation-helper-utf8-test-log.md` 补齐。

### 原始 RED 失败证据补充

原报告只保留了失败测试名和计数。实际失败链的关键行如下：

```text
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

The above exception was the direct cause of the following exception:

jewelry_on_hand.generation.GenerationError: AIReiter helper 返回非 JSON；...
stdout=b'{"ok": true, "data": {"message": "\xe4\xbb\xbb\xe5\x8a\xa1\xe5\xb7\xb2\xe5\xae\x8c\xe6\x88\x90"}}'

E assert 'stdout=not-json-�' in "AIReiter helper 返回非 JSON；...stdout=b'not-json-\\xff'；stderr=b'...\\xfe'"

FAILED tests/test_generation_helper_utf8.py::test_run_helper_decodes_utf8_bytes_without_platform_default_encoding
FAILED tests/test_generation_helper_utf8.py::test_run_helper_safely_decodes_invalid_utf8_in_diagnostics
2 failed in 0.33s
```

这些行独立证明了原 RED 的两个失败点：字节 stdout 变成 `b'...'` repr 导致 JSON 解析失败；坏字节诊断中只有 repr，没有可读中文和 replacement 字符。

### Important 1：建立子进程 UTF-8 编码契约

新增测试对 `_submit_command()` 和 `_wait_command()` 同时断言 Python 命令前缀为 `sys.executable -X utf8 <helper>`。

RED：

```powershell
python -m pytest tests/test_generation_helper_utf8.py::test_helper_commands_force_python_utf8_mode -q
```

```text
F                                                                        [100%]
================================== FAILURES ===================================
_________________ test_helper_commands_force_python_utf8_mode _________________

>       assert submit_command[:4] == expected_prefix
E       AssertionError: assert ['C:\\Users\\...t', '--model'] == ['C:\\Users\\..., 'helper.py']
E         At index 1 diff: 'helper.py' != '-X'
E         Use -v to get more diff

FAILED tests/test_generation_helper_utf8.py::test_helper_commands_force_python_utf8_mode
1 failed in 0.06s
```

GREEN：

```text
.                                                                        [100%]
1 passed in 0.04s
```

最小生产修复是在 submit/wait 两条 Python helper 命令中加入 `-X utf8`。这在代码级别保证子进程 stdout/stderr 管道使用 UTF-8；没有向 `subprocess.run` 新增 `env` 或任何关键字参数，所以既有 fake_run 签名不受影响。

### Important 2：分离严格协议解码与宽松诊断渲染

新增“结构合法的 JSON 字符串内含 `\xff`、returncode=0”用例，并断言必须抛出中文 `GenerationError` 且不写 `result.json`。

RED：

```powershell
python -m pytest tests/test_generation_helper_utf8.py -q -k invalid_utf8
```

```text
FF                                                                       [100%]
================================== FAILURES ===================================
_________ test_run_helper_safely_reports_invalid_utf8_in_diagnostics __________

>       assert "AIReiter helper stdout 不是有效 UTF-8" in message
E       AssertionError: assert 'AIReiter helper stdout 不是有效 UTF-8' in 'AIReiter helper 返回非 JSON；...stdout=not-json-�；stderr=帮助程序错误�'

_ test_run_helper_rejects_invalid_utf8_inside_valid_json_without_writing_output _

>       with pytest.raises(
E       Failed: DID NOT RAISE GenerationError

FAILED tests/test_generation_helper_utf8.py::test_run_helper_safely_reports_invalid_utf8_in_diagnostics
FAILED tests/test_generation_helper_utf8.py::test_run_helper_rejects_invalid_utf8_inside_valid_json_without_writing_output
2 failed, 2 deselected in 0.07s
```

GREEN：

```text
..                                                                       [100%]
2 passed, 2 deselected in 0.17s
```

最小生产修复将输出处理分为两条显式路径：

- `_decode_helper_protocol()` 仅用于 stdout 协议数据，`bytes.decode("utf-8")` 保持 strict。
- `_decode_helper_diagnostic()` 仅用于 stderr 和失败时的上下文渲染，此处才允许 `errors="replace"`。
- stdout 严格解码失败在 `json.loads` 和 `write_json` 之前抛出“AIReiter helper stdout 不是有效 UTF-8”，使用 `from None` 不泄漏原始 `UnicodeDecodeError` traceback，但诊断仍保留 replacement 后的 stdout/stderr 上下文。

### 整改后验证

```powershell
python -m pytest tests/test_generation_helper_utf8.py -q
```

```text
....                                                                     [100%]
4 passed in 0.13s
```

```powershell
python -m pytest tests/test_generation.py -q
```

```text
........................................................................ [ 85%]
............                                                             [100%]
84 passed in 0.47s
```

```powershell
python -m pytest skills/aireiter-image-generation/tests/test_aireiter_image_helper.py -q
```

```text
............                                                             [100%]
12 passed in 0.05s
```

`git diff --check -- src/jewelry_on_hand/generation.py tests/test_generation_helper_utf8.py` 退出码为 `0`，仅有已知 LF/CRLF 工作区提示。

### 网络与范围证明

- 整改期间只运行本地 pytest、文件读取和 Git 只读检查；新增/修改的测试均 monkeypatch `generation.subprocess.run`。
- 未运行真实 helper、CLI、generate、submit、wait 或 query；未重提 run04，未创建计费。
- 仅修改原任务允许的 `generation.py`、独立 UTF-8 测试、本报告和 `output` 中的测试记录；未触碰 helper、CLI、scoring、QC、SPEC、Plan、历史 run 产物或 `tests/test_generation.py`。
- 未暂存、未提交；`generation.py` 中并发戒指改动仍原样保留。

完成前合并验证：

```powershell
python -m pytest tests/test_generation_helper_utf8.py tests/test_generation.py skills/aireiter-image-generation/tests/test_aireiter_image_helper.py -q
```

```text
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 0.51s
```
