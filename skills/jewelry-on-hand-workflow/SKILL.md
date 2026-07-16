---
name: jewelry-on-hand-workflow
description: "用于编排手串、普通项链、带链吊坠和单枚常规指根戒指的产品分析、参考图 review、AIReiter 生成、严格 QC、重跑与最终交付。"
---

# 珠宝上手图工作流

在当前工作区编排 `jewelry-on-hand`。先确认项目根目录包含 `pyproject.toml`、`src/jewelry_on_hand/`、`reference/` 和 `skills/aireiter-image-generation/`；不要依赖固定绝对路径。这个 Skill 固定四阶段流程和 gate，不替代用户的参考图、产品结构确认与结果 QC。新项链 canonical 必须为 `schema_version=2` 并包含 `pendant_semantics`；历史 v1 只读，不自动升级，必须新建 run 并重新执行 `prepare-review` 才能继续。

## 支持边界

- `bracelet`：输入 `worn_source`，输出 `worn`，固定 1 层。
- `necklace`：输入 `worn_source`，输出 `worn` 或 `hand_held`，同一产品 1 至 3 层。
- `pendant_necklace`：输入 `worn_source`，输出 `worn` 或 `hand_held`，同一产品 1 至 3 层且保留完整主吊坠。
- `ring`：输入 `worn_source`，输出 `worn`；固定 `ring_count=1`，必须明确 `hand_side`、`finger_position`，且 `ring_wear_style=finger_base`。
- `pendant_only` 和 `unknown` 可分析但不得生成；无链吊坠禁止自动补链。

拒绝 `hand_held_source`、`flat_lay_source`、`unknown_source`、白底/平铺产品源、多件独立项链叠戴，以及对不可见扣头、背面或连接结构的推断。`hand_held` 只表示项链输出模式，不改变输入必须为真人佩戴原图的规则。双圈附件是同一条连续长链形成 2 层、`presence=absent`，不是两件项链或带链吊坠；1 至 3 层只是运行时能力，不代表存在三圈吊坠商品。

## 协作 Skill

- 飞书 Base 产品记录：使用 `lark-base`，默认只读，不主动写回。
- 图片生成、轮询和结果下载：使用 `aireiter-image-generation`。
- 生成失败、人物局部迁移或结构漂移：使用 `superpowers:systematic-debugging`。
- 对外报告完成前：使用 `superpowers:verification-before-completion`。

## 先读哪份参考

- 完整操作或 dry run：读 `references/workflow.md`。
- Prompt 构建与检查：读 `references/prompt-contract.md`。
- `pass`、`rerun`、`reject` 判定：读 `references/qc-checklist.md`。
- Gate、结构、编码或轮询故障：读 `references/troubleshooting.md`。

## 项目定位与参考源

- 优先使用 Codex 当前工作区；否则向上查找同时包含 `pyproject.toml` 和 `src/jewelry_on_hand/` 的目录。
- Skill 安装目录只用于读取自身 `references/` 和 `scripts/`；业务代码、产品图、参考图和产物都来自项目根目录。
- 默认未传 `--classification` 时同步并读取飞书参考源。
- `prepare-review --classification <xlsx>` 是历史兼容的本地 Excel 参考源；仅在显式提供时优先。两者是同一个 `prepare-review` 阶段的来源选择，不是互斥流程。
- 飞书参考源默认对任一 `pending_enrichment=true` 严格阻断。只有用户明确批准忽略待补全素材的临时批次，才可加 `--ignore-pending-enrichment`；该参数与 `--classification` 互斥。
- 临时忽略模式仍先完整分页同步线上 Base，只从候选中排除 pending 记录，不写回参考图库；过滤后无可用候选立即失败。每个正式 run 固定写入 `analysis/reference_source_snapshot.json`，记录来源、全量/忽略/保留数量、被忽略素材编号与 record_id、manifest SHA-256 和分页完成状态。

## 四阶段强制流程

1. `prepare-review`：以 correction-only 方式解析产品分析，先合并项链人工纠正并校验最终 analysis，再生成 `schema_version=2` canonical；按可选 `--reference-selection-prompt` 选择 Top 3，写入选图审计和 review 包。戒指细节图只作为 review、结构分析、canonical 约束和人工 QC 对照证据；不得自动创建决策。
2. `record-decision`：在写任何文件前交叉校验 v2 `pendant_semantics`、analysis、快照、选图审计摘要、Top 3 摘要和 canonical 路径，再记录 rank、完整快照和 `fidelity_confirmed`；冲突时中文报错，必须新建 run 回到第 1 步。
3. `generate`：在创建 generation 目录、写 prompt/submit 或调用 helper/provider 前重新执行品类、来源、模式、结构、快照、v2 canonical、选图审计、rank 和参考副本 gate 后才提交模型；选图提示词不得写入 AIReiter Prompt。戒指固定以 `input/product-on-hand.jpg` 作为内部图 2，并保存内容一致的 `product-identity.jpg` 审计副本，细节图不提交给 AIReiter；失败后按未尝试 Top 3 切换 Rank，并按 QC 失败码注入纠偏。
4. `qc`：写严格 JSON，完整覆盖 runtime checklist 与 `must_keep` 后才能进入最终汇总。

## 三图输出角色

- 需要每个 SKU 交付三张图时，为 `hero`、`hand_worn`、`lifestyle` 分别创建独立 run；不得在同一 run 中混用角色或展示模式。
- `prepare-review --output-role` 必须以飞书素材表的 `图片类型` 字段（本地 `purpose_category`）作为角色唯一分类来源，并把角色写入 `analysis/output_role.json`：`hero` 只能选含“主图”的候选，`hand_worn` 只能选含“手部佩戴图”的候选，`lifestyle` 只能选含“生活场景图”的候选。不得依据关键词、风格、推荐使用方式或视觉内容推断、替代或跨用图片类型。`record-decision --output-role` 必须传入相同值，生成阶段会再次校验。
- 有提示词时，把 `--reference-selection-prompt` 按中英文逗号、分号或换行拆为去重条件；全部条件都是硬约束，每张候选必须在白名单语义字段中命中全部条件。少于 3 张合格候选时阻断，报告基础 gate 前后数量、逐条件命中数量和全部条件同时命中数量，不得自动放宽。
- 无提示词时，只按适用品类、输出角色和参考图关键词与产品需求的贴合度选择；不得添加深色、浅色或其他系统级风格默认值。角色输出仍要求产品完整清晰且无文字；`hero` 为产品主体近景，`lifestyle` 保留日常氛围但不得遮挡主体，`hand_worn` 对手链/戒指为自然佩戴，对项链必须使用 `hand_held` 并要求手指轻持链条自然垂落。
- 选图提示词、规范化条件和候选命中证据只进入 `analysis/reference_selection_constraints.json`。其稳定摘要 `reference_selection_constraints_sha256` 必须同时绑定候选、Top 3 和生成类 `review_decision.json`；选图提示词不得写入 AIReiter Prompt。已选参考图自身的场景、姿势和背景元数据仍可进入 `【参考构图场景】`。

## 强制 Gate

1. `input/product-on-hand.jpg` 与 `analysis/product_analysis.json` 已存在。产品上手图是生成阶段唯一产品身份图。戒指可另有经过确认的 `input/product-detail.<ext>`；细节图只用于 review、结构分析和 QC，并可用于 canonical 约束和人工 QC 对照，不进入模型，也不得作为第三张模型输入。
2. 最终品类是 `bracelet`、`necklace`、`pendant_necklace` 或 `ring`；`pendant_only`、`unknown` 停止。
3. 输入是 `worn_source`；模式、层数、主吊坠和多件标志符合支持矩阵；现代项链 `length_category` 必须是四个合法值之一，`null` 只能停留在 correction-only。
4. `analysis/reference_selection_constraints.json` 存在；`analysis/reference_candidates.json`、`analysis/selected_references.json` 和生成类决策中的 `reference_selection_constraints_sha256` 均等于其稳定摘要。Top 3 必须恰有互异的 rank 1、2、3，用户已选 rank；非 HERO 项链的路径、审核摘要和最终品类/模式/长度/裁切/手持策略仍有效。
5. 默认飞书同步不存在 pending；若本 run 经批准显式使用 `--ignore-pending-enrichment`，`analysis/reference_source_snapshot.json` 必须存在，过滤范围可追溯，且不得与本地 `--classification` 混用。
6. 生成决策有 `fidelity_confirmed: true`；项链和戒指还有与最终 analysis 完全一致的完整产品确认快照。戒指同时要求三张合格、源图/review 双 SHA-256 未变化且内容互异的 Top 3 参考图。
7. `--fidelity-constraints-path` 只作为 `record-decision` 导入源；外部约束的 `product_analysis_sha256` 必须匹配已经完成评分的最终 analysis。项链分析发生变化时不得在决策阶段重绑旧 canonical，必须重新 `prepare-review`。
8. canonical 约束状态是 `confirmed`、`corrected` 或 `not_applicable`，且摘要绑定最终规范化 `ProductAnalysis`；新项链必须为 `schema_version=2`。普通项链为 `absent/0/null/forbid`，带链吊坠第一阶段为 `present/1/实际所属层/forbid`。
9. Prompt 通过 `scripts/validate_prompt_contract.py`。
10. 默认使用 `gpt_image_2`；同一 run 超过 1 次非 `pass` QC 后，下一次才切 `nano_banana_v2`。
11. 每个非空 `generation/NN/` 都有 `model.txt`、`prompt.txt`、`hand-reference.*`、提交/结果文件和 `qc.json`；不得覆盖或跳过。
12. 标准 QC 路径同时反推 analysis 与 canonical；普通项链精确检查 `主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠`，带链吊坠精确检查 `现有主吊坠数量是否为 {count}，且仍位于第 {layer} 层并保持原连接关系`；`checklist_checks` 以稳定 ID 完整覆盖 runtime checklist。
13. `critical_failures` 严格使用非空允许代码；存在关键失败不能 `pass`，严重错误必须 `reject`。

## 品类专属检查

- bracelet：手腕环绕、松紧与阴影自然，并明确检查原图手腕、手臂、掌纹、指甲和皮肤块没有迁移。
- necklace `worn`：层数、长度等级、层间落差和吊坠所属层正确，链条不穿肤、穿衣或穿发。
- necklace `hand_held`：手指接触和重力垂落真实，不虚构绕颈链路，不补链或补扣头。
- ring：参考图必须完整标注左右手、可见手指、手部朝向、戒面可见度、手指分离度和手指遮挡风险；明确水印/logo/平台标识或非手部近景时拒绝。QC 检查单枚、目标指位、戒指结构、接触物理、手指畸变和产品图来源手迁移。
- 所有品类：禁止迁移内部图 2 中的人物、手腕、手臂、颈部、胸部、衣服、头发、脸、皮肤块或背景。

戒指 `critical_failures` 允许代码为 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。数量、指位、核心结构、戒面/主石或来源手迁移必须 `reject`；手侧、接触或手指畸变至少不得 `pass`。

## Legacy 边界

历史手串自由文本、旧 JSON/run、缺现代快照的 bracelet，以及 analysis 与 canonical 同时不存在的旧 QC 可兼容；只存在其中一个文件不得降级 legacy。历史 v1 canonical 仅供 inspector、validator 和 QC 只读，inspector 标记 `legacy_read_only=true`，不得改写或补写 `pendant_semantics`；历史项链 v1 禁止进入新的 `record-decision` / `generate`。五个现代分类字段 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source` 是原子契约：要么全部缺失并按历史 bracelet 解析，要么全部完整。历史 bracelet 可以单独保留合法的 `source_image_type=worn_source`、`display_mode=worn`、`layer_count=1`；显式非法来源、模式或结构不得借 legacy 绕过。

## 禁止行为

- 不要把自动 Top 3 当作用户确认，也不要让 `rerank` 或 `manual_reference` 进入生成。
- 不要把选图提示词、规范化条件或审计证据传给 Prompt builder；Prompt 只读取已选参考图自身的元数据。
- 不要在无提示词时引入背景明暗或其他系统级风格偏好，也不要在候选不足时自动放宽任一提示词条件。
- 不要在 `record-decision` 晚期修改项链品类、来源、展示模式、层数、长度或吊坠结构；新建 run，在 `prepare-review` 评分前纠正并重选 Top 3。
- 不要直接编辑历史决策指向外部约束；重新执行 `record-decision` 产生 canonical 决策。
- 不要用删除分析文件、漏写 `fidelity_checks` / `checklist_checks`、空 `critical_failures` 或宽松 truthy 值降级 gate。
- 不要提交包含乱码的 Prompt；脚本以 UTF-8 读取并返回中文错误文案。
- 不要写回飞书，除非用户明确要求。
- 真实第三方模型 proof 属于 Task 11，尚未完成。本次 v2 只关闭结构化主吊坠语义 I1；I5 真实双圈成功 proof 与 HERO 仍为开放项。不要把本地自动化测试写成真实模型验收。

## 输出规则

- 测试过程和临时运行产物放在项目 `output/`。
- 主参考文档放在项目 `reference/`；本 Skill 的便携副本放在 `references/`。
- 最终汇总只包含当前 run 内 QC 为 `pass` 的 `generation/NN/result.png`。
- 多电脑复用时从项目根目录运行 `scripts/install_codex_skills.py`，再重启 Codex。
