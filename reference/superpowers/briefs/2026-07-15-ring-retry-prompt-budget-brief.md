# 补充任务：戒指重试 Prompt 预算修复

## 根因

戒指基础 Prompt 由 `prompt_builder.py` 校验不超过 1200 字，但 `generation.py` 在已有失败 QC 时才追加 `【本轮纠偏】`，没有为纠偏段预留空间。真实 JH501 Rank 2 基础 Prompt 为 1196 字，追加 `ring_structure_mismatch` 纠偏后为 1237 字，于 provider 提交前失败。

参考图原始文件名和 helper 提交源路径已经在 `analysis/selected_references.json`、`reference-rank.txt` 与 generation 审计中完整保存；每个 generation 还保存内容相同的 run 内审计副本 `hand-reference.<ext>`。便携 Prompt contract 仍要求 `参考图文件：`、输出用途和镜面字段存在，因此重试压缩必须保留这些契约字段，只能把文件名改写为更短但语义等价、且真实存在于当前 generation 的审计副本名。手势、风格、产品外观、特殊要求、开口端点和纠偏内容必须保留。helper 第一张图仍使用 selected reference 源路径，不在本任务中改变。

## 目标

当且仅当戒指重试 Prompt 因追加纠偏超过 1200 字时，只在真实 `【参考构图场景】` 区块内执行以下等价压缩，再重新校验长度：

1. 把原始参考文件名改为当前 generation 的审计副本名 `hand-reference.<ext>`，保留 `参考图文件：` 字段；helper 仍提交 selected reference 源路径，两者图片内容一致。
2. 把手部佩戴输出用途行压缩成仍明确包含“输出用途：手部佩戴图”“深色背景”“产品完整清晰”“无文字/水印/logo/平台标识”“确认手指根部”“接触和阴影真实”的短句。
3. 无镜面参考时，只把独立固定行 `镜面构图：无，不要额外添加镜中反射手部。` 压缩为 `镜面构图：无。`；动态风格、手势或其他参考文本中出现的同名文字必须原样保留。有镜面参考时不得删除镜面要求。

若仍超过 1200 字，继续显式抛出 `GenerationError`；不得截断产品事实、动态字段、风格、手势或纠偏内容。

## 文件

- 修改 `tests/test_generation.py`
- 修改 `src/jewelry_on_hand/generation.py`

## TDD

1. 新增失败测试，构造一个接近上限的戒指基础 Prompt，必须包含：

```text
产品事实：背侧重叠开口不得闭合
参考图文件：6ecab8b84dd26e9f19de34eb0e3538c.jpg；风格：黑色背景闪光灯直拍；手势：左手手背朝镜头
```

让基础 Prompt 本身不超过 1200，但追加 `ring_structure_mismatch` 纠偏后超过 1200。Prompt 必须含完整八层、合法输出用途和无镜面行。建立一次 reject QC 后调用 `run_generation()`，目标行为：

- helper 被调用；
- 写出的 retry `prompt.txt` 不超过 1200；
- 保留“产品事实：背侧重叠开口不得闭合”；
- 保留“风格”“手势”；
- 保留 `【本轮纠偏】` 和“戒面、戒圈、开口端点和装饰排列”；
- 包含与当前 generation 审计副本一致的 `参考图文件：hand-reference.jpg；`，不再包含原始长文件名。
- 整份 retry Prompt 继续通过 `validate_prompt_contract.py`。

先运行该测试并确认 RED，失败原因必须是当前实现抛出 1200 字上限错误。

2. 最小实现一个私有 helper，用于组合戒指 retry Prompt：

- 先正常追加纠偏；
- 未超限直接返回，不改现有短 Prompt；
- 超限时只在后续 `【遮挡与接触物理】` 前最后一个 `【参考构图场景】` 区块中执行上述三项等价压缩；
- 参考审计副本名必须根据实际 `reference_path.suffix` 生成，不能硬编码错误后缀；端到端测试必须覆盖该后缀来自本轮实际参考路径；
- 再校验；仍超限则使用现有中文错误显式失败。

不要对字符串做任意长度切片，不要删除产品事实、特殊要求、手势、风格或纠偏段。

3. 新增/保留保护测试：若等价压缩后仍超限，仍抛出 `GenerationError`，并报告压缩后的真实长度，证明没有静默截断产品事实。

4. 验证：

```powershell
py -m pytest tests\test_generation.py::<新增测试名> -q
py -m pytest tests\test_generation.py -q
```

## 全局约束

- 不修改 1200 字合同、不修改标准首次生成 Prompt、不修改任何产品事实或 retry failure 映射。
- 不影响非戒指行为、Rank 切换、模型切换、产品身份图或 helper 图像顺序。
- 当前两个目标文件已有大量未提交改动，只做本任务局部修改。
- 不执行 `git add`、`git commit`、`stash`、`checkout` 或 `reset`。
