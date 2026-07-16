# 真人参考底图首饰替换验证报告

## 结论

当前实现已完成非计费阶段验证，并停在四个本地决策可生成、尚未调用 AIReiter 的状态。QY018/QY027 均未写回飞书，未加水印、未上传附件、未删除附件。真实生成仍需单独计费确认。

## 本轮修复

- 深色背景改为硬 gate，明亮候选不能进入；`RP000298` 仅保留受控的生活场景深色例外。
- `lifestyle` 的“非手腕构图，默认不优先”按角色匹配处理，保留半身、行走和环境构图。
- 原首饰只从 `existing_jewelry` / 飞书“原有首饰类型”读取，不从适用品类或历史备注推断。
- `background`、`lighting` 只抽取对应语义片段，候选签名与最终快照使用相同投影。
- 多张真人产品上手图可确定性拼接为同一件产品的多视角身份图；不得使用 AI 改像素或用白底平铺图补视角。
- 便携 inspector 按 `ProductAnalysis` 默认值比较现代手串确认快照，避免把缺省的 `has_pendant=false`、`pendant_count=0` 误报为漂移。

## 测试证据

- Skill 结构：`quick_validate.py` 输出 `Skill is valid!`。
- Skill 便携测试：`295 passed`（包含缺省确认快照回归）。
- 定向套件：`1207 passed, 0 failed`。
- 全量套件：`1912 passed, 0 failed`。
- 计划基线为 `1033 passed, 6 failed`；当前新增失败为 0，历史六个 v1/v2 兼容失败已不再出现。原计划未保存六个 node id，报告不补造名称。

原始日志与基线对比保存在 `output/reference-replacement-workflow/2026-07-14/`。

## 四个对照决策

| Run | Rank | 参考图 | 构图意图 | 快照摘要 |
| --- | ---: | --- | --- | --- |
| `QY018-hand_worn` | 1 | `RP000116.png` | 左手手背近景、黑色布景 | `ebac501b108d32d5f07e82eb54ca44dd507370e41dd76754704fddc2a9a02bbf` |
| `QY018-lifestyle` | 2 | `RP000081.png` | 俯拍行走、浅紫衬衫、深色沥青路面 | `caa67695051e5605695b810715863bc03ce1f0e7da266de5003e73c5a744f9a6` |
| `QY027-hand_worn` | 1 | `RP000119.png` | 右手手背近景、黑色衣物背景 | `0109560a693305ea04441127d2b3e87a8c5e7a35edb5f434c20789f0ad88f1d4` |
| `QY027-lifestyle` | 3 | `RP000297.jpg` | 正面半身、低调暗色背景、右腕唯一替换位置 | `0c0ba9530efb35a472e21228f54e0f0c8f219ccecf7a40d5be76690ea90bf825` |

四个 run 的便携 inspector 与快照 validator 均通过，generation 文件数均为 0。

## QY027 产品身份

QY027 使用飞书“产品上手图”中的两张真人佩戴附件，按固定顺序左右拼接为 `3096x2048` 的单张多视角身份图。输出 SHA-256 为 `04c44edd4e3dc623f4bf395cbea7f7d5b224ded7fd6061c23a37f2d68da46821`。拼接仅缩放和排版，没有 AI 像素修改，没有白底/平铺输入；两侧视图共同描述同一件产品，生成结果仍必须只有一件目标手串。

## 禁止行为审计

- `aireiter_called=false`，AIReiter 任务号为空。
- `watermark_applied=false`。
- `feishu_writeback=false`。
- 上传附件数为 0，删除附件数为 0。
- QY018/QY027 仍是本地不回写对照；在用户再次确认计费前不得执行 `generate`。
