# 参考底图替换工作流：任务 7E 产品分析前置固化

## 目标

把主工作区当前 `product_analysis.py` 的并发扩展固化为纯提交 tree 可用的基础契约，重点提供 `review_decision.py` 所需的 `validate_analysis_ready_for_reference_selection`，并保持四品类产品身份分析、吊坠语义与尺寸规范化的确定性。该任务不修改保真约束、决策、生成、CLI 或 QC。

## 范围

- 修改并提交：`src/jewelry_on_hand/product_analysis.py`
- 修改并提交：`tests/test_product_analysis.py`
- 仅在直接模型契约需要时增加同一直接测试文件内容；不得提交其他文件。

## 契约

- `ProductAnalysis.from_dict()` / `to_dict()` 对 bracelet、necklace、pendant_necklace、ring 保持稳定 round-trip。
- `validate_analysis_ready_for_reference_selection(product)` 必须中文 fail-closed，并至少拒绝：未支持品类、非 `worn_source`、分析未确认/结构未确认、缺少必要结构字段、戒指手侧/指位不完整、吊坠项链缺少必要吊坠结构。
- 该 gate 只判断产品身份是否可进入参考选择/决策，不得注入或判断参考图构图、背景、人物或风格。
- 产品尺寸数字规范化与 Task 6 builder 一致；明确排除 bool 伪装数字。
- composition/style_mood 可以作为历史产品分析数据保留，但不得进入该 gate 的构图决策或改变输出角色。
- `PendantSemantics` 使用已提交模型契约；非吊坠品类不得产生 present 吊坠语义，吊坠项链不得静默缺失。
- 所有错误顺序和序列化确定性，未知/额外字段按现有 schema 策略处理，不得默默放宽已有约束。

## TDD 与验证

1. 从最新主 HEAD 建全新 `output/` detached worktree；记录主两文件 SHA，三方保留用户当前实现。
2. 先在纯 HEAD 证明 `validate_analysis_ready_for_reference_selection` 缺失或行为不完整的 RED，再最小 GREEN。
3. 必测四品类合法通过，以及上述各拒绝边界、bool/int/float尺寸边界、吊坠语义和 composition/style_mood 不影响 gate。
4. 运行：

```powershell
python -m pytest tests/test_product_analysis.py tests/test_models.py -v `
  --basetemp=output/t07e -o cache_dir=output/cache-t07e
```

5. 用纯 tree 临时探针确认当前主工作区 `review_decision.py` 的 import 所需符号已存在；不要提交或运行脏 `review_decision.py` 业务测试作为本任务成功条件。
6. 纯 tree 导入、`py_compile`、`git diff --check`。

显式隔离 `PYTHONPATH`；不访问外部接口、生图或飞书。

## 安全集成

- 用户已持续授权同类 HEAD 前进与目标并发重基线；主工作区只读，保留原字节。
- 只提交两个获准文件，detached 与主 index plumbing 均非 amend。
- 集成前后索引为空，主目标 SHA 不变，tested/detached/main tree 一致。
- 报告全文写入 `.superpowers/sdd/reference-replacement-task-7e-report.md`。
