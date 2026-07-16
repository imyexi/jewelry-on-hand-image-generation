# 商品主图数量与遮挡保真设计

## 目标

修复商品主图生成中重复部件数量漂移的问题。目标产品的实体数量只由正面图、侧视图和细节图确定；参考图原商品即使存在遮挡，其数量、珠距和排列也不得成为目标商品事实。

本次先覆盖可明确计数的重复部件，QY048 的冻结事实为“圆珠实体总数恰好 13 颗”。

## 方案选择

采用“单阶段生成 + 强制数量契约 + 遮挡感知 QC”。不在本次引入透明商品层和第二次场景合成，原因是第二次生成仍可能改写已校验数量，并会把一次可控修复扩大为新的两阶段架构。

## 数据契约

`product_analysis.json` 增加 `component_counts`：

```json
[
  {
    "name": "圆珠",
    "physical_count": 13,
    "source_views": ["front", "side"]
  }
]
```

规则：

- `physical_count` 是实体总数，不是最终画面的可见数。
- `source_views` 只能来自目标产品的 `front`、`side`、`detail_NN`，禁止出现 `reference`。
- `beaded_bracelet` 必须至少冻结一个精确数量；无法确认时在生成前阻断并请求更清楚的目标产品图。
- 已冻结精确珠数时，`uncertain_features` 不得再声明总珠数未知或不作猜测。
- `fidelity_constraints.json` 必须逐项镜像同一 `component_counts`，避免分析、Prompt 与 QC 各用一套数量。

## Prompt 契约

保留现有五段结构，在 `【产品保真】` 内增加“数量与遮挡”硬约束：

- 明写每个可计数组件的实体总数，例如“圆珠实体总数固定为且仅为 13 颗”。
- 明写参考图原商品的数量、珠距、排列和被遮挡部分不能作为依据。
- 允许前景道具自然遮挡目标商品；遮挡只改变可见数量，不改变实体总数。
- 禁止为填满参考图圆环、匹配参考商品尺寸或补足遮挡弧段而新增、复制、拆分、合并或删除部件。
- 场景与数量冲突时，优先保持实体数量，允许调整目标商品整体尺寸、位置和旋转。

## QC 契约

固定检查项增加 `component_counts`，可修复失败码增加 `component_count_mismatch`。QC 增加 `component_count_checks`：

```json
[
  {
    "name": "圆珠",
    "expected_physical_count": 13,
    "visible_count": 13,
    "occluded_count": 0,
    "occlusion_evidence": "无遮挡，13 颗均可见",
    "result": "pass",
    "notes": "沿闭合单圈逐颗计数为 13 颗"
  }
]
```

`pass` 必须满足 `visible_count + occluded_count = expected_physical_count`。`occluded_count > 0` 时必须给出具体前景道具和遮挡区域证据。数量检查失败必须使用 `component_count_mismatch` 并进入 rerun，不因数量漂移更换参考图。

## QY048 重跑

- 继续使用用户已选择的 Rank 3、素材 `RP000040`。
- 使用原正面图、侧视图和四张细节图。
- 新建独立输出目录，不修改 2026-07-15 原始真实测试产物。
- 生成后逐颗核验；无遮挡时必须清晰可见恰好 13 颗，存在合理前景遮挡时按可见数与遮挡数合计核验。

## 验收标准

- 缺失、非法、来自参考图或与不确定描述冲突的数量事实会被契约拒绝。
- QY048 Prompt 明确包含“圆珠实体总数固定为且仅为 13 颗”和参考图数量隔离规则。
- 17 颗结果无法通过结构化 QC。
- 定向测试、全量测试和 Skill 校验通过。
- 新生成结果通过人工视觉计数与结构化数量 QC 后才写入 `final/result.png`。
