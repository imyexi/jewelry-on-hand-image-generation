# Review 决策、产品确认与参考快照绑定

## 当前生成决策

`review/review_decision.json` 只记录人工确认结果，不承担自动选图。当前参考底图替换工作流的生成决策必须选择唯一 rank：

```json
{
  "action": "generate_rank_1",
  "selected_ranks": [1],
  "fidelity_confirmed": true,
  "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
  "output_role": "hand_worn",
  "reference_snapshot_sha256": "64位小写十六进制",
  "confirmation_snapshot": {}
}
```

字段规则：

- `action` 在当前生成路径使用 `generate_rank_1` 或单 rank 的 `generate_selected`。`rerank` 和 `manual_reference` 不得进入生成；现代 run 禁止多 rank 生成。
- `selected_ranks` 必须只含一个 1..3 的整数，且存在于 `analysis/selected_references.json` 和候选快照集合。
- 生成动作要求 `fidelity_confirmed=true`。
- `fidelity_constraints_path` 必须规范化为 `analysis/product_fidelity_constraints.json`。`--fidelity-constraints-path` 只是导入源，不允许 decision 指向外部非标准路径。
- `output_role` 只允许 `hand_worn` 或 `lifestyle`，并与 `analysis/output_role.json`、飞书 `图片类型` 和确认快照一致；`hero` 必须交给独立主图 Skill。
- `reference_snapshot_sha256` 必须是确认快照规范化 JSON 的 64 位小写十六进制摘要。
- `confirmation_snapshot` 必须与最终产品 analysis 完全一致。

## 产品确认快照

基础字段必须完整：

```json
{
  "confirmed_product_type": "pendant_necklace",
  "source_image_type": "worn_source",
  "display_mode": "worn",
  "layer_count": 2,
  "length_category": "collarbone",
  "has_pendant": true,
  "pendant_count": 1,
  "pendant_layer": 2,
  "pendant_position": "正面中心",
  "pendant_orientation": "正向",
  "connection_structure": "连接环连接第二层链条",
  "is_independent_multi_item": false
}
```

品类约束：

- `bracelet`：`worn_source`、`worn`、`layer_count=1`，无项链/戒指结构。
- `necklace`：同一产品 1 至 3 层，`has_pendant=false`、`pendant_count=0`、`pendant_layer=null`；不得自动补链。
- `pendant_necklace`：同一产品 1 至 3 层，恰好一个主吊坠，`pendant_layer` 在有效层内；`schema_version=2` canonical 的 `pendant_semantics` 必须完全一致。
- `ring`：额外要求 `ring_count=1`、`hand_side=left|right`、`finger_position=thumb|index|middle|ring|little`、`ring_wear_style=finger_base`；项链字段保持无吊坠的单层中性值。
- `pendant_only`、`unknown` 不得形成生成决策。

产品确认快照不含参考图构图。产品分析只能控制目标珠宝身份与佩戴物理，不能覆盖人物、姿势、手势、景别、服装、背景、光线、留白或替换位置。

## 参考构图确认快照

`review/reference_composition_snapshot.json` 保存唯一 selected rank 的完整结构字段。decision 只保存其摘要，不复制 schema。写入前必须验证：

- rank 与 selected reference 完全一致；
- 源参考图、review 副本、文件名和 SHA-256 一致；
- `output_role` 与 run 角色一致；
- 目标位置唯一，`target_product_count=1`；
- 人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置均可人工确认；
- 产品展示面积足够，文字/UI 风险不是 blocking。

候选快照描述错误时必须修订飞书语义源并重新 `prepare-review`，不得直接改候选 JSON。确认后的任何字段、文件 SHA、analysis 或 canonical 改变都使原决策失效。

## 原子写入

生成决策至少绑定以下四项：最终 `analysis/product_analysis.json`、canonical `analysis/product_fidelity_constraints.json`、`review/review_decision.json`、确认 `review/reference_composition_snapshot.json`。内存校验全部通过后才原子提交；任一写入失败恢复旧内容，不能留下部分成功。

生成前再次加载并交叉验证：

- decision 的角色、单 rank、`fidelity_confirmed`、产品确认快照；
- `reference_snapshot_sha256` 与确认快照实际摘要；
- 确认快照与 selected reference 的 rank、源/review SHA；
- analysis 与 canonical 摘要及结构完全一致。

任一失败都发生在创建 generation 或调用 provider 之前。

## 三态与迁移

- `modern_snapshot`：候选快照、确认快照和有效 decision digest 全部存在；可以继续进入现代 generation gate。
- `legacy_read_only`：现代链全部不存在的完整历史 run；只读审计。
- `damaged`：部分存在、摘要冲突或绑定损坏；停止并报告。

历史 run 只读，不得追加 decision、generation 或 QC。需要重做时新建 run 并重新执行 `prepare-review`。历史 v1 canonical 不自动升级、不补写 `pendant_semantics`；删除单个现代文件不能把 `damaged` 降级成 legacy。

## 非生成动作

`rerank` 只请求回到候选选择并重建 Top 3 与候选快照；`manual_reference` 只记录人工参考意图，不得绕过飞书图片类型、结构快照和 SHA gate。两者都不得被 `generate` 接受。
