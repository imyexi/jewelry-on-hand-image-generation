# 真人参考底图替换 Troubleshooting

先停止写入，再依据中文错误定位最早失败的 gate。不得通过删除文件、改摘要、补写决策或绕过校验继续生成。

## SHA-256 或 manifest 不一致

症状：源参考图、review 副本、generation 副本、确认快照或 `input-manifest.json` 的摘要不一致。

恢复：

1. 保留现场，只读运行 inspector，确认变化发生在源图、review 还是 generation 固化副本。
2. generation 已发布但五输入不完整或摘要错误时，运行态为 `damaged`；不得局部重拷或改 manifest。
3. 源参考图或产品图发生变化时，新建 run 并重新执行 `prepare-review`。
4. 只有未发布 staging 复制失败时才允许由程序自动清理 staging；不得覆盖已发布 generation。

## output role 被拒绝

症状：`--output-role` 缺失、不一致，飞书 `图片类型` 不匹配，或传入 `hero`。

恢复：`hand_worn` 只选“手部佩戴图”，`lifestyle` 只选“生活场景图”；`图片类型` 字段是唯一来源。角色错误必须重新 `prepare-review`。`hero` 必须交给独立主图 Skill，不能改名、静默降级或在 decision 阶段重绑。

## 参考构图快照缺失或冲突

症状：候选快照为空、确认快照缺失、decision digest 不匹配、rank/角色/目标位置冲突，或 Prompt 出现快照外构图指令。

恢复：

- 候选字段不完整：补全飞书语义源，重新 `prepare-review`，不要直接编辑 JSON。
- 确认前发现描述不准：选择其他合格 rank，或回到同步源修订后重跑。
- 确认后任一字段、文件或 analysis 改变：新建 run 并重新执行 `prepare-review`。
- 不能确认唯一替换位置、产品展示面积不足或 `text_or_ui_risk=blocking`：拒绝该参考图。

## 候选背景、生活构图或原首饰语义异常

症状：明亮背景进入候选、`lifestyle` 半身/行走构图被腕部近景策略扣分、适用品类中的戒指/项链被误当成画面原首饰，或 `background` / `lighting` 混入整段备注。

恢复：先复核飞书 `图片类型`，再执行深色背景硬 gate；`背景干净` 不能单独放行，`RP000298` 只豁免深色背景判定。`非手腕构图，默认不优先` 在 `lifestyle` 角色下按角色匹配候选处理。`existing_jewelry`（飞书 `原有首饰类型`）是原首饰判断的唯一来源，不得从 `jewelry_type`、适用品类或历史备注推断原首饰。`background` 和 `lighting` 只抽取各自语义片段，不得拼入整段备注；候选签名与最终快照使用同一抽取结果。修复字段映射后新建 run 并重新 `prepare-review`。

## 产品身份缺少关键视角

症状：单张真人上手图只显示部分主件，产品 analysis 却要求另一张真人上手附件中的结构；或模型把两张视角理解成两件产品。

恢复：仅当多张真人产品上手图明确属于同一件产品时，才可通过缩放、留白和确定性拼接建立同一件产品的多视角身份图。不得使用 AI 修改产品像素，不得使用白底或平铺图补齐视角。审计源附件 token、源 SHA-256、拼接顺序和输出 SHA-256，并在 analysis、Prompt 与 QC 中明确多视角只表示一件目标产品。任何来源不一致或结构无法确认都停止。

## 历史 run 与 damaged

三态含义：

- `modern_snapshot`：候选、确认、decision digest 及已有 generation 的五输入链完整；
- `legacy_read_only`：现代链全部不存在的完整历史 run；
- `damaged`：部分现代文件存在、摘要冲突或固化不完整。

历史 run 只读，不得追加 decision、generation 或 QC。历史 bracelet 有 `review_decision.json` 和旧参考副本但缺现代快照时，也只能审计；要重做必须新建 run 并重新执行 `prepare-review`。不要补写快照，不要删除现代文件把 `damaged` 伪装成 legacy。

历史 v1 canonical 只读，不得补写 `pendant_semantics` 或自动升级为 `schema_version=2`。历史手串可以保留合法旧字段，但显式非法的来源、模式或结构仍拒绝。

## 参考构图漂移

症状：结果改变景别、姿势、人物位置、服装、背景、光线或留白，或把 `lifestyle` 收敛成产品特写。

恢复：核对 `reference_preservation_checks` 与快照。第一次固定同一 rank，只注入对应 reference 纠偏并重跑一次；再次漂移，停用该参考图并重新 `prepare-review`。不得用裁切结果、改快照或切模型掩盖不合格参考。

## 原首饰残留或替换位置改变

症状：参考底图原手串/项链/戒指仍在，目标产品换到不同身体部位，或出现第二件目标产品。

恢复：小面积残留第一次可强化清除范围 `rerun`；位置改变或产品复制直接 `reject`。确认 `replacement_target` 唯一且 `target_product_count=1`，必要时更换参考并重新 `prepare-review`。

## 产品源人物区域迁移

症状：结果出现产品图手腕、手臂、手指、颈胸、服装、头发、脸、皮肤块、肤色或背景。

恢复：标记 `source_person_region_migrated`；戒指来源手污染标记 `source_hand_leakage`。两者都是严重错误并 `reject`。检查五输入顺序必须为 scene 后 product，Prompt 必须声明产品上手图只提供珠宝身份。

## 产品 canonical 或确认快照冲突

症状：`schema_version=2`、`pendant_semantics`、项链层数/长度/主吊坠，或戒指 `ring_count`、`hand_side`、`finger_position`、`ring_wear_style` 与 analysis 不一致。

恢复：在 `prepare-review` 评分前纠正产品分析并重建 canonical。`--fidelity-constraints-path` 只作为 `record-decision` 导入源，摘要不匹配、非标准路径或晚期重绑一律拒绝。完整产品确认快照、analysis 与 canonical 必须完全一致。

## 戒指参考或 QC 失败

候选少于 Top 3 时，检查飞书“手部佩戴图”是否完整标注左右手、可见手指、手部朝向、戒面可见度、手指分离度、手指遮挡风险；不得用视觉猜测补字段。

`ring_count_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`source_hand_leakage` 必须 `reject`。`hand_side_mismatch`、`ring_contact_error`、`finger_deformation` 至少不得 `pass`；按参考或产品责任分别路由。

## 三层 QC 不完整

症状：缺 `reference_preservation_checks`、`fidelity_checks` 或 `checklist_checks`，`must_keep` 项没有完全一致映射，或 `critical_failures` 与状态冲突。

恢复：从确认快照重建十项 reference evidence，从 canonical 重建 `must_keep`，从 analysis/角色重建 runtime checklist。逐项人工填写，不复制统一结论。存在严重错误必须 `reject`；不能用空数组、truthy 值或宽松文本降级。

## 飞书 pending/enrichment/CAS

症状：同步返回 pending 阻断、导入发生 CAS 冲突、分页不完整或缓存 manifest 摘要变化。

恢复：保留 `pending_enrichment.json` 与冲突审计，重新同步最新记录后基于新版本合并；不得强制覆盖。临时忽略 pending 仅在用户明确批准时使用 `--ignore-pending-enrichment`，仍完整分页、排除 pending 并保存 run 内来源快照，不写回飞书。

## UTF-8、乱码与退出码

- 先设置 `PYTHONUTF8=1`，再确认 JSON/Markdown/Prompt 均以 UTF-8 读取；不要用替换字符修复损坏文本。
- `0` 表示校验成功；`1` 表示契约或产物错误；同步命令的 `2` 表示存在待补全素材。以实际脚本帮助和 stderr 为准。
- 乱码、JSON 解析失败或非零退出码都发生在 provider 调用前。修复源文件或重新同步后，从失败阶段重新运行；不得把失败命令当作成功。

## provider、轮询或结果下载失败

先确认 helper 尚未调用还是已得到任务 ID。未调用时修复本地 gate；已提交时保留 `submit.json` 与任务记录，只做幂等查询/下载，不重复付费提交。任何 provider 结果仍必须进入三层 QC；命令可运行不等于真实验收。
