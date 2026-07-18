---
name: jewelry-product-hero-workflow
description: Use when Codex needs to generate a high-fidelity 珠宝产品主图 from a 正面图、侧视图、1–4 张细节图 and 飞书主图 references, including Top 3 review, AIReiter generation, or structured QC.
---

# 珠宝产品主图工作流

## 核心原则

把产品多视图作为商品身份唯一来源，把参考图只作为构图、机位、道具、背景、光线和前后遮挡关系来源。将产品移植到参考场景时，先移除参考图原商品；不得把参考商品的结构、数量、材质或品牌元素迁入结果。目标商品的实体总数不因场景遮挡改变，遮挡只改变可见数量。

默认只读飞书。固定来源为 `https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink` 中的 `AI生图参考图素材库 / 素材收录池`。读取时使用 `lark-wiki` 解析节点、`lark-base` 全量分页读取记录、`lark-drive` 下载素材附件；缺少任一能力就阻断。真实生成必须使用 `$aireiter-image-generation`。

本 Skill 独立安装时只依赖当前文件与 `scripts/` 即可执行核心契约。项目维护时可选读 `reference/product-hero-workflow.md` 获取扩展说明；该项目文档不是运行时硬依赖。

## 不可绕过门禁

1. 接受 1 张正面图、1 张侧视图和 1–4 张细节图。只允许一个商品单元；同款成对耳饰可作为一个商品单元，其他套组立即拒绝。
2. 联合分析多视图并冻结事实。正面图决定整体身份，侧视图补充厚度与连接关系，细节图只补充局部材质；视图冲突或不可见结构不得猜测。用 `component_counts` 冻结可计数重复部件的实体总数和目标图证据；手串必须确认精确珠数，否则生成前阻断。数量证据禁止来自 reference。
3. 从固定飞书 Wiki 的 `AI生图参考图素材库 / 素材收录池` 读取全部分页记录。把固定 URL、Base、数据表、页数、记录数和 `pagination_complete=true` 写入来源快照；仅接受 `图片类型=主图` 且 `适用品类` 显式包含目标中文品类的记录。禁止使用通用素材补位。必须提供全部产品输入哈希用于排除，并按附件 SHA-256 去重。
4. 不得把深色背景作为硬 gate。执行四个硬 gate 和六项 100 分评分；任一阶段少于 3 张立即阻断。
5. 生成并展示 Top 3 评审包后暂停。禁止自动选择，必须等待用户显式选择 rank 1、2 或 3；调用决策脚本时同时提交 `source`、`selected_rank` 和用户原话，作为冻结的用户选择证据。
6. 固定输入顺序为 `reference → front → side → details`，Prompt 图号必须按实际 1–4 张细节图动态结束。Prompt 必须写明实体总数、参考图原商品的数量不得作为依据，以及“遮挡只改变可见数量，不改变实体总数”；`must_keep` 的送模投影只包含商品事实 `name`，`component_counts` 只包含名称和实体总数；两者都不得渲染 `source_views` 或 `qc_question`。场景冲突时允许调整商品尺寸、位置和旋转，不得增删部件。默认使用 GPT Image 2；累计两次非 pass 后改用 Nano Banana V2。最多 4 个进入 QC 的视觉结果，基础设施失败不计入上限。
7. AIReiter 成功结果必须绑定 provider、`out_task_id`、提交 endpoint、模型、Prompt SHA-256、画幅、2K 分辨率、输入 SHA 顺序、completed 查询回执和选中 output URL。由记录脚本直接下载该 HTTPS URL 并冻结 submit/result/PNG 三个摘要；任意本地 PNG 或空回执不得进入 QC。
8. 对每个结果执行结构化 QC。`component_count_checks` 必须逐项记录预期实体数、可见数、遮挡数和遮挡证据，且 pass 时可见数与遮挡数之和等于实体总数；数量失败使用 `component_count_mismatch` 并 rerun。只有 pass 才能创建 `final/result.png` 并交付；rerun 仅把已知 failure code 经固定白名单映射为直接视觉强化要求。原始 failure code、失败 notes、QC 问题/证据和来源视图只留在约束、QC 与 attempt 元数据，不得写入 Prompt；reject 排除当前 rank 并再次等待用户显式选择 rank。

## 执行顺序

| 阶段 | 必用脚本 | 完成条件 |
| --- | --- | --- |
| 输入与分析 | `scripts/product_hero_workflow.py` | `prepare_run`、`freeze_product_analysis` 成功 |
| 候选与 Top 3 | `scripts/reference_review.py` | `write_review_package` 成功并等待人工 rank |
| 保真与生成 | `scripts/generation_contract.py` | Prompt、输入顺序、模型、AIReiter 回执和尝试目录均通过契约 |
| Prompt 预检 | `scripts/validate_prompt_contract.py` | 退出码 0 |
| QC 与交付 | `scripts/validate_qc_record.py`、`scripts/generation_contract.py` | `finalize_qc` 返回 pass manifest |

真实出图时调用 `$aireiter-image-generation`，严格提交生成契约给出的模型、画幅、Prompt 和图片顺序。不得把“API 已完成”当作 QC 通过。

## 快速决策

| 条件 | 动作 |
| --- | --- |
| 显式品类主图不足 3 张 | 阻断，不补通用素材 |
| 手串珠数无法从目标产品图确认 | 阻断，请求更清楚的产品图；不得从参考图猜测 |
| Top 3 已生成但未选 rank | 展示评审包并等待用户 |
| `component_count_checks` 失败 | 使用 `component_count_mismatch` 收紧 Prompt 后重跑，不自动更换参考图 |
| QC 为 rerun 且未达 4 个结果 | 使用失败码白名单映射出的直接视觉强化要求重跑 |
| QC 为 reject 且仍有候选 | 归档决策，排除当前 rank，等待重选 |
| QC 为 pass | 只交付 `final/result.png`、manifest 和 QC 结论 |

## 示例

用户提供戒指正面、侧面和两张细节图后：创建不可覆盖的 run，冻结戒指事实；只读飞书全量筛选“主图 + 戒指”，生成 Top 3 并展示理由与风险；等待用户回复“选 2”，把该原话和 rank 2 一并冻结；再按固定图序调用 AIReiter 并保存同一 `out_task_id` 的提交/完成回执。若首轮材质漂移则把对应失败码映射为“严格保持材质、颜色、透明度、纹理和反光”的直接视觉强化要求，原始失败码与 QC 证据继续留档；若第二轮结构错误则 reject 并等待从剩余 rank 中重选。仅当某轮 QC 为 pass 时交付最终 PNG。

## 常见错误与红旗

- “最高分就是用户选择”——错误；Top 3 排序不能替代显式 rank。
- “专用品类不足，用通用补齐”——错误；禁止使用通用素材补位。
- “商品适合黑底，所以先筛黑底”——错误；不得把深色背景作为硬 gate。
- “结果看起来不错或 API 成功”——错误；没有结构化 pass 就不得交付。
- “参考图能补全看不见的结构”——错误；未知结构必须保持未知。
- “参考图被遮挡，所以可以不确认目标手串珠数”——错误；参考图遮挡与目标商品实体数量无关。
- “被遮挡就多生成几颗填满圆环”——错误；前景遮挡只能隐藏已冻结部件，不能改变实体总数。
- “有一张 PNG 就能进入 QC”——错误；必须先通过 AIReiter 请求与完成回执绑定。
