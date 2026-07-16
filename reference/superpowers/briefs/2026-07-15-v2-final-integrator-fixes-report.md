# 产品保真 v2 最终 integrator 残留 Important 修复报告

## 结论

两个残留 Important 已按逐 finding 的 RED→GREEN 流程修复。实现仅触及简报允许的五个代码/测试文件及本报告；未修改生产核心 validator、戒指、HERO、飞书、v6、`output_role`、reference composition 或 provider helper，未调用 provider，未执行暂存或提交。

## Finding 1：absent v2 缺失 `layer` 键被当作 `null`

### 根因

- `PendantSemantics.from_dict()` 使用 `source.get("layer")`，将缺失键与显式 JSON `null` 都转换为 Python `None`。
- portable inspector 与 QC runtime validator 同样使用 `semantics.get("layer")`，因此三个入口都无法区分缺失键和显式 `null`。

### RED

先只新增测试，再运行以下四类缺失键用例：

- 直接调用 `PendantSemantics.from_dict()`：未抛出 `ValueError`。
- 嵌套调用 `ProductFidelityConstraints.from_dict()`：未抛出 `ValueError`。
- portable inspector 进程：错误返回码为 0。
- portable QC 进程：错误返回码为 0。

上述四项均因待修行为而失败；portable 用例同时断言中文错误、无 traceback，且 QC 文件字节不变。

### GREEN

- 核心在读取前显式检查 `"layer" in source`，缺失时抛出中文 `ValueError`；随后使用 `source["layer"]` 保留显式 `null` 的合法含义。
- portable inspector 与 QC 对 v2 `pendant_semantics` 增加相同的显式键存在性检查。
- 定向 GREEN：`10 passed`，覆盖核心 direct/nested、portable inspector/QC、历史 v1 边界和正向用例。

### 正向兼容

- 核心 `test_v2_constraints_round_trip_structured_pendant_semantics` 继续接受 `presence="absent"`、`count=0`、`layer=null`、`creation_policy="forbid"` 的严格四字段对象。
- portable inspector 与 QC 的显式 `layer:null` 正向用例均返回 0。
- 历史 v1 仍不要求 `pendant_semantics`，且保持只读行为。

## Finding 2：portable 未镜像 present 自由文本冲突门禁

### 根因

- 核心 validator 已遍历 10 类语义字段并拒绝 6 个 present 规格冲突短语。
- portable inspector 只有 absent 敏感词逻辑，QC runtime validator 没有等价 present 冲突检查，导致事后篡改的 present canonical 可通过认证。

### RED

先只新增测试，再运行：

- 共享 helper 的 10 路径×6 短语矩阵：60 项均因 helper 尚不存在而失败。
- inspector 与 QC 进程级冲突用例：两项均错误返回码为 0。

Finding 2 共 62 项真实 RED；进程级测试要求错误包含精确字段路径 `must_not_change[0]` 和精确短语 `吊坠缺失`、中文输出无 traceback，且 QC 文件字节不变。

### GREEN

- 在纯 Python portable 脚本 `validate_qc_record.py` 中定义唯一一份 6 短语常量、唯一一份 10 路径遍历 helper 和冲突校验 helper。
- QC 直接调用该 helper；inspector 从同目录 portable 脚本导入并复用该 helper，没有复制第二套短语或遍历实现。
- 调用点显式限定在 `necklace` / `pendant_necklace`，未给 ring/bracelet 新增项链 present 规则。
- Finding 2 定向 GREEN：`66 passed`，包含 60 项矩阵、helper 正向、inspector/QC 拒绝、inspector/QC 正向及无项目 package import 检查。

### 合法保护句正向

`禁止新增第二颗吊坠` 不属于 6 个冲突短语；以下三层均继续通过：

- 共享 helper 返回空错误列表。
- portable inspector 进程返回 0。
- portable QC 进程返回 0。

## portable 边界

- `inspect_run_artifacts.py` 与 `validate_qc_record.py` 均没有 `import jewelry_on_hand` 或 `from jewelry_on_hand`。
- 共享逻辑只依赖 Python 标准库和同目录 portable 脚本，不依赖项目 package。
- 未调用任何 provider。

## 完整验证

```text
uv run pytest tests/test_product_fidelity_v2.py tests/test_skill_portability.py -q
336 passed in 2.05s

uv run pytest tests/test_models.py tests/test_review_decision.py tests/test_generation.py tests/test_prompt_builder.py tests/test_qc.py -q
440 passed in 1.20s
```

## 修改文件

- `src/jewelry_on_hand/models.py`
- `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_skill_portability.py`
- `reference/superpowers/briefs/2026-07-15-v2-final-integrator-fixes-report.md`
