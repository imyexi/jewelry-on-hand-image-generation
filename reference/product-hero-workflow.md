# 珠宝产品主图工作流

## 目录

1. [目标与边界](#目标与边界)
2. [输入契约](#输入契约)
3. [飞书参考图数据源](#飞书参考图数据源)
4. [候选评估与 Top 3](#候选评估与-top-3)
5. [人工选择门禁](#人工选择门禁)
6. [保真约束与生成契约](#保真约束与生成契约)
7. [AIReiter 生成策略](#aireiter-生成策略)
8. [结构化 QC 与状态迁移](#结构化-qc-与状态迁移)
9. [运行目录与不可变产物](#运行目录与不可变产物)
10. [脚本接口](#脚本接口)
11. [失败处理](#失败处理)

## 目标与边界

本流程把同一商品的多视角照片平移、移植到参考图的场景中，生成一张可作为电商产品主图的高保真图片。“平移”不是简单像素位移，而是保持目标商品身份，在参考图的构图、机位、道具、背景、光线、阴影和视觉高度中重新呈现商品。

职责边界固定如下：

- 产品正面图、侧视图和细节图是商品身份的唯一来源。
- 参考图只提供构图、机位、道具、背景、光线、阴影、留白和前后遮挡关系。
- 必须移除参考图原商品、文字、水印、logo 和平台标识。
- 不得从参考图继承品类、部件、材质、颜色、数量或品牌元素。
- 目标商品实体总数只由产品图确定；参考场景遮挡只改变可见数量，不改变实体总数。
- 默认只读飞书，不写回字段、记录、附件或视图。
- 自动 QC 通过后即可交付，不增加第二个人工成图确认门禁。

## 输入契约

每次运行必须提供：

- 1 张产品正面图；
- 1 张产品侧视图；
- 1–4 张细节图；
- 非空产品编号；
- 一个全新的空 run 目录。

支持 JPEG、PNG 和 WebP。`prepare_run` 复制输入到 run 内，记录角色、相对路径、SHA-256 和文件大小，禁止覆盖已有运行。

产品分析必须冻结以下字段：

| 字段 | 规则 |
| --- | --- |
| `product_id` | 与输入清单一致 |
| `category` | 固定九类英文键之一 |
| `product_unit` | `single` 或 `matched_earring_pair` |
| `physical_piece_count` | 正整数；成对耳饰必须为 2 |
| `silhouette` | 可见整体轮廓 |
| `component_topology` | 部件及拓扑关系 |
| `component_counts` | 可计数重复部件的名称、实体总数和目标产品证据视图 |
| `colors`、`materials` | 只记录多视图可确认事实 |
| `distinctive_features` | 可识别的关键款式特征 |
| `uncertain_features` | 看不清、冲突或不可确认的事实 |
| `evidence_by_view` | 事实对应的输入图角色 |

固定九类映射为：

| 英文键 | 飞书中文品类 |
| --- | --- |
| `beaded_bracelet` | 手串 |
| `bracelet` | 手链 |
| `necklace` | 项链 |
| `long_necklace` | 长链 |
| `pendant` | 吊坠 |
| `cord_jewelry` | 编绳 |
| `ring` | 戒指 |
| `bangle` | 手镯 |
| `earrings` | 耳饰 |

流程只支持一个商品单元。同款成对耳饰视为一个商品单元，必须恰好两只；其他多件套、混合套组或无法确认是否同款的组合必须拒绝。

`component_counts` 每项固定包含 `name`、正整数 `physical_count` 和非空 `source_views`。证据视图只允许 `front`、`side` 或 `detail_NN`，禁止使用 `reference`。手串必须冻结精确珠数；目标产品图无法确认时立即阻断，不得把参考图原商品的可见珠数、被遮挡部分或圆环尺寸当作补全依据。已冻结精确珠数后，`uncertain_features` 不得再声明总珠数未知或不作猜测。

## 飞书参考图数据源

生产数据源固定为：

- Wiki：`https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink`
- Base：`AI生图参考图素材库`
- 数据表：`素材收录池`

先通过飞书 Wiki/Base 能力解析资源，再只读分页获取全部记录，直到 `has_more=false`。至少读取 `record_id`、`素材编号`、`素材图片`、`图片类型`、`适用品类` 和 `关键词`。每条本地候选缓存必须保留 `source_fields` 原始字段、附件本地路径和可用状态。

调用严格筛选前必须构建来源快照：

```json
{
  "wiki_url": "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink",
  "base_name": "AI生图参考图素材库",
  "table_name": "素材收录池",
  "pagination_complete": true,
  "page_count": 2,
  "record_count": 299
}
```

`record_count` 必须等于传给筛选器的全量记录数，`page_count` 必须为正整数。来源 URL、Base、数据表或分页完成标志不一致时阻断。调用方还必须传入输入清单中全部产品图片的 SHA-256，不能为空或遗漏。

候选硬筛选顺序：

1. 记录与第一张素材附件可用，附件非空且可读取。
2. `图片类型` 的结构化 token 精确包含 `主图`。
3. `适用品类` 的结构化 token 精确包含产品分析映射出的目标中文品类。
4. 附件 SHA-256 不得与任何产品输入图相同。
5. 相同附件 SHA-256 只保留一条稳定排序记录。

禁止使用通用素材补位。`适用品类=通用`、空品类、关键词或肉眼相似都不能替代显式目标品类。全量飞书读取失败时必须阻断，不得静默使用旧缓存声称本轮已同步。

严格筛选返回带来源快照、来源快照 SHA-256、候选集合 SHA-256 和产品排除哈希的候选批次。`write_review_package` 只接受该批次，不接受调用方手工拼装的普通候选列表；写包前先重算候选集合 SHA-256，任何追加、删除、替换或字段修改都会阻断，再检查 `usable`、`source_fields.图片类型`、`source_fields.适用品类` 和产品哈希排除。

## 候选评估与 Top 3

结构化候选通过四个硬 gate 后才能评分：

| 硬 gate | 通过值 |
| --- | --- |
| `compatible` | `true` |
| `single_product_unit` | `true` |
| `requires_product_stretch` | `false` |
| `requires_large_background_rebuild` | `false` |

不得把深色背景作为硬 gate。背景明暗、色调和材质只参与匹配理由或风险，不得先验淘汰亮色、中性或彩色主图。

六项评分总计 100 分：

| 评分项 | 分值 |
| --- | ---: |
| `topology_layout` | 0–30 |
| `complete_replace_region` | 0–20 |
| `camera_orientation_scale` | 0–15 |
| `background_props` | 0–15 |
| `lighting_material` | 0–10 |
| `cleanup_cost` | 0–10 |

候选和视觉评估必须按 `record_id` 一一绑定，并同时绑定 `material_id` 与 `image_sha256`。先按总分降序，再按素材编号和 record_id 稳定打破并列。初筛后少于 3 张，或四个硬 gate 后少于 3 张，均立即阻断。

`write_review_package` 在临时目录构建并校验后提交：

- `analysis/reference_assessments.json`
- `review/top3.json`
- `review/review.html`
- `review/candidates/rank-N-<素材编号>.<扩展名>`

复制候选后再次计算 SHA-256，防止筛选与复制之间源文件变化。任何目标已存在时拒绝覆盖，提交失败恢复原 state 并删除本轮产物。

## 人工选择门禁

Top 3 评审包必须向用户展示每张候选的素材编号、缩略图、分数、通过理由和风险，然后暂停。

禁止自动选择最高分、最低风险或“最像”的候选。必须由用户显式选择 rank 1、2 或 3，之后才能调用 `record_reference_decision`。调用同时提交 `user_selection_evidence`：`source` 只能是 `user_message` 或 `user_interface`，`selected_rank` 必须与决策相同，`verbatim` 保存非空用户原话或界面确认文案。决策同时冻结该证据、Top 3、产品分析和候选图片哈希。该证据用于审计和阻止无证据自动调用，不声称提供密码学上的真人身份证明。

当 QC 判定 reject 时，当前 rank 进入 `excluded_ranks`，原决策归档到 `review/decision-history/NN.json`。下一轮仍必须由用户显式选择未排除的剩余 rank；不得自动切换。

## 保真约束与生成契约

保真约束至少包含：

- `must_keep`：名称、证据视图和逐项 QC 问题；
- `must_not_change`：不可改变的结构、数量、颜色和连接关系；
- `uncertain_features`：不得补造的未知特征。
- `component_counts`：与产品分析完全一致的实体数量事实和目标图证据。

冻结阶段同时将输入清单、产品分析和保真约束的实际 SHA-256 写入 state。生成前再次校验 state、sidecar 与实际文件，任何不一致都阻断。

图片顺序固定为：

1. reference；
2. front；
3. side；
4. detail_01 至 detail_04。

Prompt 固定包含 `【任务目标】`、`【图片职责】`、`【产品保真】`、`【场景保持】`、`【禁止项】` 五段，且顺序唯一。图号按实际输入动态生成：1 张细节图时使用“图 2–4 / 图 4”，4 张细节图时使用“图 2–7 / 图 4–7”，不得引用不存在的图片。`must_keep` 在约束 JSON 中仍保存 `source_views` 和 `qc_question`，`component_counts` 仍保存数量证据视图；送模投影中前者只渲染商品事实 `name`，后者只渲染名称和实体总数。来源视图、QC 问题和选择依据不得进入 Prompt。核心约束包括：

- 图 1 只负责参考场景；
- 图 2 正面图具有最高商品身份优先级；
- 图 3 只补充侧面厚度、弧度和连接关系；
- 图 4–7 只补充局部材质和可见细节；
- 多视图冲突时停止，不可见结构不得补造；
- 每个已冻结的可计数组件必须写明“实体总数固定为且仅为 N”；
- 参考图原商品的数量、珠数、珠距、排列和被遮挡部分不得作为目标商品结构依据；
- 前景遮挡只改变可见数量，不改变实体总数；不得为填满参考图圆环或补足遮挡弧段增删、复制、拆分或合并部件；
- 场景构图与数量冲突时优先保持实体数量，允许调整商品整体尺寸、位置和旋转；
- 产品输入的白色或中性背景不得迁移；
- 只出现一个商品单元，成对耳饰必须恰好两只。

参考图宽高由标准库读取，并映射到最近的受支持画幅。`validate_prompt_contract.py` 必须在提交前返回退出码 0。

## AIReiter 生成策略

真实生成通过 AIReiter 执行：

- 默认模型：GPT Image 2；
- 累计两次非 `pass` 后：Nano Banana V2；
- 提交内容：契约指定模型、画幅、Prompt 和固定图片顺序；
- 生成结果：必须下载为真实 PNG，并在复制后复核 SHA-256。

每次提交写入新的 `generation/NN`。基础设施失败只增加提交记录，不增加视觉结果和 non-pass 次数。最多允许 4 个成功进入 QC 的视觉结果；达到上限后进入失败状态，不得继续生成。

`record_generation_result` 不接受裸 API JSON 或任意本地 PNG。提交回执的 `request_contract` 必须绑定：

- `provider=aireiter`、固定 submit endpoint 和非空 `out_task_id`；
- 与 `attempt.json` 一致的模型、Prompt SHA-256、画幅、`resolution=2K` 和输入图片 SHA-256 顺序；
- 能证明任务已接受的 AIReiter submit response。

结果回执必须使用相同 `out_task_id` 和固定 query endpoint，状态为 `completed`，包含非空 `data.output[].url`，并明确记录本轮下载使用的 `selected_output_url`。该 URL 必须属于返回 output 且使用 HTTPS。`record_generation_result` 直接从该 URL 下载字节，不再接受调用方提供的本地结果路径；下载字节必须是 50MB 内的真实 PNG。只有回执、直接下载、真实 PNG 和复制后 SHA-256 同时通过，结果才能进入 QC。

结果记录成功时，state 同时冻结 `submit.json`、`result.json` 和 `result.png` 三个 SHA-256。finalize 必须先用这些记录时摘要校验磁盘文件，再重新验证 AIReiter 回执和 PNG；结构仍合法但内容在记录后变化也会阻断。

## 结构化 QC 与状态迁移

QC 必须完整覆盖固定 16 项：品类、商品单元、部件拓扑、组件数量、连接关系、识别特征、材质颜色纹理、完整未裁切、参考商品清除、场景布局、背景道具、光线、接触阴影与反射、源背景泄漏、文字水印 logo、生成伪影。

`fidelity_checks` 必须与 `must_keep` 的 `name + question` 完整且唯一绑定。每项必须包含 `pass/fail` 结果和非空中文证据说明。

`component_count_checks` 必须与 `component_counts` 同序完整绑定。每项记录 `expected_physical_count`、`visible_count`、`occluded_count`、`occlusion_evidence`、`result` 和 `notes`。通过时 `visible_count + occluded_count` 必须等于实体总数；存在遮挡数时必须指出具体前景道具和遮挡区域。数量不符使用 `component_count_mismatch`，属于可修复的 rerun，不因该失败自动更换参考图。

三种状态：

| QC 状态 | 条件 | 下一步 |
| --- | --- | --- |
| `pass` | 全部检查通过且无 failure code | 创建 final 和 manifest，状态进入 `passed` |
| `rerun` | 存在可修复失败和 rerun code，无 reject code | 累计 non-pass；把失败码经固定白名单映射为直接视觉强化要求后重跑 |
| `reject` | 存在关键失败和 reject code | 累计 non-pass；排除当前 rank，等待显式重选 |

原始 failure code、失败 notes、QC 问题/证据和来源视图继续保存在约束、QC 与 attempt 元数据中，不得写入 Prompt；下一轮只接收白名单映射后的直接视觉指令，不得包含“上次错误”“质检认为”等过程叙述。

只有 `pass` 才能创建并交付 `final/result.png`。API 成功、主观相似、用户催促或总体美观都不能替代结构化 pass。

finalize 前重新校验磁盘上的生成尝试、AIReiter 提交/结果回执和记录时冻结的三个结果摘要，防止记录后被篡改。`final/manifest.json` 额外冻结 attempt SHA-256、provider、`out_task_id`、选中 output URL、submit/result 回执路径及各自 SHA-256，并保留 `user_selection_evidence`。

## 运行目录与不可变产物

标准目录：

```text
run/
  input/input_manifest.json
  input/front.*
  input/side.*
  input/details/01.*
  analysis/product_analysis.json
  analysis/product_analysis.sha256
  analysis/fidelity_constraints.json
  analysis/fidelity_constraints.sha256
  analysis/reference_assessments.json
  review/top3.json
  review/review.html
  review/decision.json
  review/decision-history/NN.json
  generation/NN/attempt.json
  generation/NN/prompt.txt
  generation/NN/input_order.json
  generation/NN/result.png
  generation/NN/result.json
  generation/NN/qc.json
  final/result.png
  final/manifest.json
  state.json
```

正式产物禁止覆盖。所有多文件提交必须先在 run 内临时目录构建，再原子提交；发生异常时恢复原 state 字节并清理本轮创建项。

## 脚本接口

| 文件 | 公开接口 |
| --- | --- |
| `skills/jewelry-product-hero-workflow/scripts/product_hero_workflow.py` | `prepare_run`、`validate_product_analysis`、`freeze_product_analysis`、`model_for_non_pass_count` |
| `skills/jewelry-product-hero-workflow/scripts/reference_review.py` | `collect_explicit_category_candidates`（要求来源快照和全部产品哈希）、`validate_reference_assessments`、`select_top3`、`write_review_package`、`record_reference_decision`（要求用户选择证据） |
| `skills/jewelry-product-hero-workflow/scripts/generation_contract.py` | `freeze_fidelity_constraints`、`build_generation_contract`、`prepare_generation_attempt`、`record_infrastructure_failure`、`record_generation_result`（直接下载已选 AIReiter output URL）、`validate_qc_record`、`finalize_qc` |
| `skills/jewelry-product-hero-workflow/scripts/validate_prompt_contract.py` | 只读 Prompt 与输入顺序校验 CLI |
| `skills/jewelry-product-hero-workflow/scripts/validate_qc_record.py` | 只读 QC 与保真约束校验 CLI |

两个 CLI 参数错误退出 2；输入或契约错误输出中文 stderr 并退出 1；成功退出 0。CLI 不修改输入文件。

## 失败处理

- 飞书分页读取不完整：阻断，不使用旧缓存冒充本轮全量结果。
- 显式品类主图不足 3 张：阻断，禁止使用通用素材补位。
- 多视图冲突或商品单元不合法：阻断并请求更清楚的产品图。
- 手串精确珠数无法从目标产品图确认：阻断；参考图即使局部无遮挡也不得提供数量事实。
- Top 3 未经显式选择：保持等待状态，不提交生成任务。
- AIReiter 提交、轮询或下载失败：记录基础设施错误，不消耗视觉结果次数。
- AIReiter 回执缺失、任务 ID/模型/Prompt/画幅/输入顺序不一致：阻断，不允许本地 PNG 进入 QC。
- QC rerun：把已知失败码经固定白名单映射为直接视觉强化要求，原始失败码和失败 notes 只留档，不得写入 Prompt；随后重新执行全部 QC。
- 组件数量不符：写入 `component_count_mismatch`；保持用户选择的参考图，优先收紧实体数量和遮挡规则后重跑。
- QC reject：归档并排除当前 rank，等待用户选择剩余 rank。
- 第 4 个视觉结果仍非 pass，或三个 rank 全部 reject：状态进入 `failed`。
- 真实 SKU 验收必须有用户提供的正面图、侧视图和 1–4 张细节图；在 `final/result.png` 与 QC pass 产生前，不得声称真实成图验收完成。
