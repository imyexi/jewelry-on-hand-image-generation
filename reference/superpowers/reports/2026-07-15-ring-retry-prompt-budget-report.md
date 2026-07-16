# 戒指重试 Prompt 预算修复报告

## 状态

- 状态：完成。
- 提交：无；未执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
- 修改范围：仅对 `src/jewelry_on_hand/generation.py`、`tests/test_generation.py` 做本任务局部修改，并全文修订本报告。

## 最终契约

戒指基础 Prompt 继续遵守 1200 字上限，首次生成 Prompt 不变。仅当历史 QC 失败、存在戒指纠偏且追加纠偏后超限时，在真实 `【参考构图场景】` 到后续 `【遮挡与接触物理】` 之间执行三项等价压缩：

1. 保留 `参考图文件：` 字段，把原始长文件名改为当前 generation 内真实存在的审计副本名 `hand-reference.<原后缀>`。
2. 把手部佩戴输出用途行压缩为仍包含“输出用途：手部佩戴图”“深色背景”“产品完整清晰”“无文字/水印/logo/平台标识”“确认手指根部”“接触和阴影真实”的短句。
3. 仅把参考区内行首、整行固定字段 `镜面构图：无，不要额外添加镜中反射手部。` 压缩为 `镜面构图：无。`；动态风格、手势和其他参考文本中的相同字面量保持原样，有镜面要求保持完整。

`hand-reference.<ext>` 是 run 内审计副本名，不是 helper 输入路径。helper 第一张 `--image` 继续使用 `analysis/selected_references.json` 中本轮 Rank 的 `selected_reference` 路径；生成流程用 `shutil.copy2` 写出审计副本，端到端测试确认两者文件内容一致。

等价压缩后仍超过 1200 字时显式抛出 `GenerationError`，不截断产品事实、特殊要求、风格、手势或纠偏内容。

## 根因

真实 JH501 Rank 2 基础 Prompt 为 1196 字，追加 `ring_structure_mismatch` 纠偏后为 1237 字。原生成流程没有为纠偏预留预算。早期删除整个 `参考图文件：` 字段的方案违反 portable Prompt contract，后续未锚定的无镜面字符串替换又可能误改动态字段，因此最终实现采用区块限定、真实字段行锚定和语义等价压缩。

## TDD RED

### Prompt 预算 RED

主复现使用 1190 字完整合法八层戒指 Prompt。测试先调用真实 `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`，确认基础 Prompt 退出码为 0；追加 `ring_structure_mismatch` 后超过 1200 字。

执行：

```powershell
py -m pytest tests\test_generation.py::test_ring_retry_compacts_contract_fields_when_correction_exceeds_prompt_limit -q
```

旧实现得到预期 RED：`1 failed`，异常为：

```text
GenerationError: 戒指重试 Prompt 长度为 1216，超过 1200 字上限
```

### 镜面作用域 RED

新增保护测试，让动态风格文本先出现完整字面量 `镜面构图：无，不要额外添加镜中反射手部。`，其后再出现真正的独立固定镜面行。

执行：

```powershell
py -m pytest tests\test_generation.py::test_ring_retry_compaction_only_shortens_fixed_no_mirror_line -q
```

未锚定 `replace()` 先改坏动态风格文本，测试以 `dynamic_reference_text` 未保留得到预期 `1 failed`。

## 最小实现

- `_build_generation_jobs()` 在组合 retry Prompt 前取得本轮 `reference_path`，仅把后缀传给压缩 helper；helper 提交路径和图片顺序均未改变。
- 文件字段使用行首锚定，只改写真正的 `参考图文件：...；` 行，生成 `hand-reference.<原后缀>` 审计名。
- 输出用途只匹配行首 `输出用途：手部佩戴图` 行，并保留全部合同语义。
- 无镜面压缩使用 `(?m)^镜面构图：无，不要额外添加镜中反射手部。$`，只匹配独立固定行。
- 任一章节边界缺失时不扩大替换范围；压缩后按实际结果长度复检并报错。

## GREEN 与路径证据

相关测试：

```powershell
py -m pytest tests\test_generation.py::test_ring_retry_compacts_contract_fields_when_correction_exceeds_prompt_limit tests\test_generation.py::test_ring_retry_compaction_preserves_mirror_requirements tests\test_generation.py::test_ring_retry_compaction_only_shortens_fixed_no_mirror_line tests\test_generation.py::test_ring_retry_png_reference_keeps_helper_source_and_writes_matching_audit_copy tests\test_generation.py::test_ring_retry_prompt_still_fails_when_equivalent_compaction_is_insufficient -q
```

最终复验结果：`5 passed in 0.31s`，无警告。

这些测试确认：

- retry `prompt.txt` 不超过 1200 字并通过真实 portable validator；
- helper command 的 `--prompt` 精确等于落盘 retry Prompt；
- 产品事实、动态参考文本、输出用途全部关键语义、风格、手势、镜面字段和纠偏内容均按合同保留；
- 有镜面要求不被压缩；无镜面时只压缩真正的独立固定行；
- 等价压缩后仍超限时，错误长度等于压缩后的实际长度。

`.png` 端到端测试把真实 Rank 2 `selected_reference` 设置为 review 目录中的 `.png` 路径。retry Prompt 写入 `参考图文件：hand-reference.png；`；helper 第一张 `--image` 仍精确等于该 selected reference 路径；generation 内 `hand-reference.png` 审计副本存在，且字节与 selected reference 完全一致。

## 完整回归

```powershell
py -m pytest tests\test_generation.py -q
```

最终复验结果：`104 passed in 0.97s`。

portable validator 戒指定向回归：

```powershell
py -m pytest tests\test_prompt_builder.py::test_portable_prompt_validator_accepts_complete_ring_contract tests\test_prompt_builder.py::test_ring_prompt_contract_rejects_text_over_1200_chars tests\test_prompt_builder.py::test_ring_prompt_contract_requires_core_rules_in_first_300_chars tests\test_prompt_builder.py::test_ring_prompt_contract_requires_extra_jewelry_ban tests\test_skill_portability.py::test_portable_prompt_contract_declares_complete_ring_support -q
```

结果：`5 passed in 0.15s`。

## 顾虑

无已知阻塞。压缩有意依赖标准八层章节和标准行首字段；非标准格式不会触发宽泛替换，仍超限时显式失败。
