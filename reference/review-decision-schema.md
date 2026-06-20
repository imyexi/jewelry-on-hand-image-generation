# Review 决策 Schema

`review/review_decision.json` 是 AIReiter 生成前的强制 gate。文件缺失、JSON 非法、字段非法、产品保真未确认，或 action 不允许进入生成时，流程必须停止，不得调用生成接口。

## 通用字段

- `action`：必填字符串，合法值为 `generate_rank_1`、`generate_selected`、`generate_multiple`、`rerank`、`manual_reference`。
- `selected_ranks`：整数列表，取值范围为 1..3，不允许重复。写入决策文件时会规范化输出。
- `manual_reference`：手动参考图路径，仅在 `manual_reference` action 中必填；第一版只记录，不进入生成。
- `fidelity_confirmed`：生成类 action 必填且必须为 `true`，表示用户已经确认或修正产品保真约束。
- `fidelity_constraints_path`：可选字符串，默认 `analysis/product_fidelity_constraints.json`，相对路径以 run 根目录为基准。
- `fidelity_notes`：可选字符串，仅记录补充说明；如果用户补充了关键识别点，必须先更新 `analysis/product_fidelity_constraints.json`，不能只写在 notes 中。

## Action 规则

- `generate_rank_1`：只生成 rank 1。缺失或空 `selected_ranks` 会规范化为 `[1]`；显式传入时只能是 `[1]`。
- `generate_selected`：必须且只能提供 1 个 Top 3 范围内的 rank。
- `generate_multiple`：必须提供至少 2 个 Top 3 范围内的 rank。
- `rerank`：表示需要重新匹配，不允许进入生成。
- `manual_reference`：表示记录人工参考图诉求，必须提供 `manual_reference`；第一版不允许进入生成。

## 产品保真 Gate

生成类 action 还必须满足：

- `fidelity_confirmed: true`。
- `analysis/product_fidelity_constraints.json` 存在且合法。
- `product_fidelity_constraints.review_status` 为 `confirmed`、`corrected` 或 `not_applicable`。
- `pending` 不允许生成，即使 rank 选择合法也必须停止。

## 示例

```json
{
  "action": "generate_selected",
  "selected_ranks": [3],
  "fidelity_confirmed": true,
  "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
  "fidelity_notes": "已确认白水晶随形和海蓝宝跑环均写入 must_keep"
}
```
