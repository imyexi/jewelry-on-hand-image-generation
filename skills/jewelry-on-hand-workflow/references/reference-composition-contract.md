# 参考构图快照 Contract

## 文件与职责

- `analysis/reference_composition_snapshots.json`：`prepare-review` 为 Top 3 生成的候选快照列表；它是从飞书同步字段构建的审核草稿。
- `review/reference_composition_snapshot.json`：`record-decision` 从唯一 selected rank 固化的人工确认快照；它与 decision digest、角色、rank 和参考文件 SHA 绑定。
- `generation/NN/reference-composition-snapshot.json`：生成前复制的确认快照，供 Prompt、manifest、QC 与 inspector 独立复核。

候选不是确认。候选描述有误时，修订飞书语义源并重新 `prepare-review`；不得直接编辑候选 JSON 后继续决策。确认快照生成后，任何结构内容变化都必须重新开始新 run。

## 完整 schema

快照必须是只含以下字段的 JSON 对象，不允许缺字段或未知字段：

```json
{
  "rank": 1,
  "reference_file": "RP000001.jpg",
  "reference_sha256": "64位小写十六进制",
  "output_role": "hand_worn",
  "framing": "hand_closeup",
  "camera_angle": "正面平视",
  "subject_placement": "左手和前臂位于画面中下部",
  "visible_body_regions": ["left_hand", "left_wrist", "left_forearm"],
  "pose": {
    "body": "躯干未入镜",
    "arm": "前臂斜向右上",
    "hand": "手背朝镜头",
    "hand_side": "left"
  },
  "clothing": "无可见衣物；无遮挡风险",
  "background": "深色布面；无大面积文字",
  "lighting": "左上侧柔光",
  "replacement_target": {
    "body_region": "left_wrist",
    "source_jewelry": "单条手串",
    "target_product_count": 1
  },
  "other_jewelry_to_remove": ["左手无名指戒指"],
  "text_or_ui_risk": "none",
  "product_visibility_sufficient": true,
  "composition_signature": "64位小写十六进制"
}
```

字段约束：

- `rank` 为大于等于 1 的整数，并且必须存在于 selected references。
- `reference_file` 只能是文件名，不能包含目录逃逸；`reference_sha256` 必须等于实际源图与 review 副本的 SHA-256。
- `output_role` 只允许 `hand_worn` 或 `lifestyle`；`hero` 在构建候选前即拒绝。
- `framing`、`camera_angle`、`subject_placement`、`clothing`、`background`、`lighting` 必须是可人工确认的非空描述。
- `visible_body_regions` 必须是非空字符串列表。
- `pose` 必须且只能包含 `body`、`arm`、`hand`、`hand_side`，每项非空。
- `replacement_target` 必须且只能包含 `body_region`、`source_jewelry`、`target_product_count`；目标数量固定为 1。
- 多件同类原首饰必须有内外、上下、次序或具体手指选择器，确保唯一替换位置。
- `other_jewelry_to_remove` 列出目标之外仍需清除的全部首饰，可为空列表但不得缺失。
- `text_or_ui_risk` 只允许 `none`、`small_removable`、`blocking`；`blocking` 不得确认。
- `product_visibility_sufficient` 必须为 `true`；面积不足要换参考图，不得靠生成阶段裁切。
- `composition_signature` 由角色、景别、姿势、背景、光线和替换位置的规范化 JSON 计算 SHA-256，用于低重复审计，不替代质量 gate。

## 候选构建

候选只从已经同步并通过硬 gate 的飞书字段构建：

- 景别来自 `framing`；身体区域来自 `visible_body_regions`；
- 姿势来自 `pose_keywords`、`hand_side`、`hand_orientation`；
- 服装来自 `collar_type` 与服装遮挡风险；
- 背景、光线、机位、主体位置和文字/UI 风险来自场景、风格与 notes；
- 原首饰与清除项来自 `existing_jewelry`、`ignored_reference_jewelry`；
- 展示面积来自 `product_visibility`。

任何必需字段为空、描述互相冲突、风险无法判断、目标不唯一或展示面积不足时，停在 `prepare-review` 并返回中文错误；不得在 Prompt 阶段猜测。

候选集合必须恰好对应 Top 3 的 rank。重排候选时必须同步重建三份快照与 review 页面，不能保留旧 rank 的快照。

## 人工确认与绑定

`record-decision` 只接受一个 selected rank。确认时按以下顺序验证：

1. `rank` 与 selected reference 的唯一 rank 一致；
2. `reference_file` 与 run 内 review 副本文件名一致；
3. 源参考图、review 副本和快照 `reference_sha256` 完全一致；
4. `output_role` 与 `analysis/output_role.json`、decision 命令和飞书 `图片类型` 一致；
5. `replacement_target` 唯一且 `target_product_count=1`；
6. 所有结构字段可人工确认，产品可见面积足够，文字/UI 风险可处理；
7. 对快照规范化 JSON 计算摘要并写入 decision 的 `reference_snapshot_sha256`。

analysis、canonical、decision 与确认快照必须作为同一事务写入。任何目标写入失败都恢复事务前内容；不得留下只有 decision 没有确认快照，或只有快照没有 digest 的部分状态。

## 不可修改字段

确认后以下内容全部不可在原 run 中修改：

- `rank`、`reference_file`、`reference_sha256`、`output_role`；
- 人物、身体区域、姿势、手侧、手势；
- 机位、景别、主体位置、裁切、留白；
- 服装、背景、光线；
- 替换部位、原首饰描述、需清除首饰和目标数量；
- 文字/UI 风险、展示面积判断与 `composition_signature`。

产品 analysis、canonical 或角色变化也会使快照失效。唯一恢复动作是新建 run 并重新执行 `prepare-review`，不能晚绑定、补字段、改摘要或在 generation 副本上修补。

## 三态迁移

`classify_reference_run` 必须返回且只返回：

- `modern_snapshot`：候选快照、确认快照、有效 decision digest 全部存在；如已有 generation，现代 manifest 与五份固化输入也必须完整。
- `legacy_read_only`：候选、确认与 digest 全部不存在，且已有 generation 仅由完整旧格式产物组成。只能读、检查和审计。
- `damaged`：三项部分存在、摘要不一致，或现代 generation 缺 manifest/固化输入、混入旧命名、路径逃逸、文件摘要变化。

删除单个现代文件不能让 `damaged` 降级为 `legacy_read_only`。历史 run 不得追加 decision、generation 或 QC；需要重做时必须新建 run 并重新执行 `prepare-review`。

## 强制停止条件

以下任一情况都在 provider 调用和创建正式 generation 前停止：

- 运行态不是 `modern_snapshot`；
- 角色、rank、文件名或任一 SHA 绑定失败；
- 快照缺字段、含未知字段或字段类型错误；
- 目标位置不唯一、目标数量不是 1；
- `text_or_ui_risk=blocking` 或展示面积不足；
- 快照与 Prompt、analysis、canonical 冲突；
- generation 快照副本与 decision digest 不一致；
- 五输入 manifest 的路径、顺序或摘要无法闭环。
