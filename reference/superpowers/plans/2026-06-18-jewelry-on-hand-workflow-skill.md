# 珠宝上手图工作流 Skill 化实施计划

> 计划目标：把当前“飞书货盘表读取 → 产品图下载 → 参考图筛选 → 人工 review → AIReiter 生成 → QC → 重跑 → 汇总交付”的流程，封装成一个可被 Codex 自动触发的编排型 Skill。

## 结论

可以写成 Skill 触发，但不应该做成完全无人值守的一键黑盒。

推荐定位为“编排型 Skill”：

- Skill 负责固定流程、路径、模型选择、提示词约束、检查清单、失败重跑规则。
- 飞书 Base 读取继续复用 `lark-base`。
- 图片生成继续复用 `aireiter-image-generation`，手部自然度优先使用 `gpt_image_2`。
- 参考图选择必须保留人工 review gate，用户确认 rank 1/2/3 后才能生成。
- 结果必须保留 QC gate，尤其检查“原图手腕/手臂随饰品一起被迁移”的问题。
- Skill 不打包大图片库、飞书附件、API key 或生成结果，只引用当前项目和现有资源。

## 目标 Skill

目标路径：

```text
C:\Users\Administrator\.codex\skills\jewelry-on-hand-workflow
```

目标结构：

```text
C:\Users\Administrator\.codex\skills\jewelry-on-hand-workflow\
  SKILL.md
  agents\
    openai.yaml
  references\
    workflow.md
    prompt-contract.md
    qc-checklist.md
    troubleshooting.md
  scripts\
    validate_prompt_contract.py
    validate_qc_record.py
    inspect_run_artifacts.py
```

触发示例：

- “按珠宝上手图工作流生成 JH483/JH484 上手图”
- “从飞书 Base 读取 20260618 货盘表并生成产品上手图”
- “用产品上手图和参考图生成小红书上手图”
- “重跑某个货号，修复手部不和谐/原图手腕拼接/戒指/水印问题”

## 边界

Skill 负责：

- 识别用户输入的飞书 Base 链接、货盘表、SKU 列表、日期批次。
- 调用飞书能力读取记录和下载“产品上手图”。
- 调用当前项目的参考图筛选逻辑生成 Top 3 review 包。
- 等待用户选择参考图 rank。
- 构建并校验生成提示词。
- 调用 AIReiter 生成图片。
- 记录 `submit.json`、`result.json`、`prompt.txt`、`qc.json` 和最终图片。
- 按 QC 结论决定通过、重跑或拒绝。

Skill 不负责：

- 绕过用户选择参考图。
- 未经用户允许写回飞书。
- 保存或暴露飞书凭证、AIReiter API key。
- 把图片素材库、历史输出或客户数据打包进 Skill。
- 在未做 QC 的情况下宣称结果可用。

## 开发任务

### 任务 1：初始化 Skill 骨架

创建 Skill 目录和基础文件：

```powershell
$PY='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $PY 'C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\init_skill.py' jewelry-on-hand-workflow `
  --path 'C:\Users\Administrator\.codex\skills' `
  --resources scripts,references `
  --interface display_name='Jewelry On-Hand Workflow' `
  --interface short_description='Run the Feishu-to-AIReiter jewelry on-hand image workflow with review and QC gates.' `
  --interface default_prompt='按珠宝上手图工作流读取产品、选择参考图、生成并做 QC'
```

验收：

- `C:\Users\Administrator\.codex\skills\jewelry-on-hand-workflow\SKILL.md` 存在。
- `C:\Users\Administrator\.codex\skills\jewelry-on-hand-workflow\agents\openai.yaml` 存在。
- `references` 和 `scripts` 目录存在。

### 任务 2：编写 `SKILL.md`

`SKILL.md` 只写触发条件、协作 Skill、必读 reference、强制 gate 和输出规则，保持短小。

必须写清楚：

- 遇到飞书 Base 链接或货盘表时使用 `lark-base`。
- 图片生成必须使用 `aireiter-image-generation`。
- 生成失败分析使用 `superpowers:systematic-debugging`。
- 完成前使用 `superpowers:verification-before-completion`。
- 没有 `review_decision.json` 禁止生成。
- 没有 QC 记录禁止交付。

验收：

```powershell
$PY='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $PY 'C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py' 'C:\Users\Administrator\.codex\skills\jewelry-on-hand-workflow'
```

期望输出：`OK`

### 任务 3：编写 `references/workflow.md`

记录完整运行流程：

1. 解析用户输入：飞书 Base URL、日期、货号、模型偏好、是否重跑。
2. 读取飞书 Base 表和目标记录。
3. 下载“产品上手图”到项目 `output/`。
4. 生成 prepared 输入图。
5. 生成或读取 `product_analysis.json`。
6. 自动筛选 Top 3 参考图。
7. 生成 review 包并停止等待用户选择。
8. 写入 `review_decision.json`。
9. 构建 prompt 并运行 prompt contract 校验。
10. 调用 AIReiter 生成。
11. 保存生成过程文件和结果图片。
12. 按 QC checklist 检查。
13. 对失败项创建新的 timestamp rerun 目录。
14. 汇总通过项，输出最终交付说明。

验收：

- 文档明确标出“review gate”和“QC gate”。
- 文档明确禁止覆盖旧 `result.png`。
- 文档明确所有测试与运行产物放在项目 `output/` 下。

### 任务 4：编写 `references/prompt-contract.md`

固定提示词契约，解决之前的核心失败原因：模型把“产品图里的饰品 + 原手腕/原手臂”当成整体迁移到参考手上。

必须包含：

- 图 1 只作为手部姿态、肤色、手腕粗细、光线、背景参考。
- 图 2 只作为珠宝产品身份、珠子、隔圈、金属件、颜色、透明度、纹理、反光、排列参考。
- 禁止继承图 2 的皮肤、手腕、手臂、掌纹、指甲、肤色、手臂粗细、背景。
- 手腕宽度、手臂轮廓、皮肤连续性和肤色必须以图 1 为准。
- 不要把图 2 中的“手串 + 手腕局部”作为整体贴到图 1。
- 禁止额外戒指、参考图原有首饰、水印、logo、文字、畸形手。

验收：

- prompt contract 中能检索到“只提取珠子”“禁止继承图 2 的皮肤”“手腕宽度以图 1 为准”“不要把手串+手腕局部整体贴到图 1”。

### 任务 5：编写 `references/qc-checklist.md`

QC 结果只能是：

- `pass`
- `rerun`
- `reject`

必须检查：

- 产品是否保真。
- 是否出现参考图中的旧首饰。
- 是否新增戒指或额外首饰。
- 是否有水印、logo、文字。
- 手指、手掌、手腕是否自然。
- 手串是否自然贴合目标手腕。
- 是否出现原图手腕/手臂/皮肤块随产品一起迁移。
- 是否出现“粗手腕贴到细手上”的不连续拼接。

验收：

- checklist 中有独立的“原图手腕/手臂迁移检查”章节。
- 任何没有做该检查的 QC 记录都不能通过验证脚本。

### 任务 6：编写 `references/troubleshooting.md`

记录常见失败原因和修复策略：

- 额外戒指：参考图本身有戒指、prompt 负面约束不足。
- 原图手腕拼接：图 2 是真实上手图，模型把手串和手腕当作同一主体。
- 手部不和谐：模型对手部结构控制弱，优先改用 `gpt_image_2` 并强化图 1 作为手部唯一来源。
- 产品漂移：prompt 过度概括材质，缺少具体珠子/隔圈/颜色/排列约束。
- 提示词乱码：PowerShell 写入中文时编码损坏，必须 UTF-8 写入并在提交前校验。
- AIReiter 轮询失败：已有 `submit.json` 时优先继续查询原 `out_task_id`，不要重复提交。

验收：

- 每类问题都有“原因”和“处理方式”。
- 特别记录 `gpt_image_2` 适合手部自然度重跑。

### 任务 7：编写 `scripts/validate_prompt_contract.py`

脚本功能：

- 输入 `prompt.txt`。
- 检查必需提示词片段是否存在。
- 拒绝 `???`、`锟` 等乱码。
- 缺少产品隔离约束时返回非 0。

验收：

- 坏 prompt 必须失败。
- 当前项目 `prompt_builder` 生成的好 prompt 必须通过。

### 任务 8：编写 `scripts/validate_qc_record.py`

脚本功能：

- 输入 `qc.json`。
- 检查 `status` 必须是 `pass`、`rerun` 或 `reject`。
- 检查 `passed` 和 `failed` 必须是列表。
- 检查 `notes` 必须是字符串。
- 检查 QC 文本必须提到原图手腕/手臂迁移检查。

验收：

- 没有 source-arm/source-wrist 检查的 QC 必须失败。
- 明确记录“未发现原图手腕/皮肤块迁移”的 QC 可以通过。

### 任务 9：编写 `scripts/inspect_run_artifacts.py`

脚本功能：

- 输入单个运行目录，可选输入最终汇总 JSON。
- 检查是否存在：
  - `input/product-on-hand.jpg`
  - `analysis/product_analysis.json`
  - `analysis/selected_references.json`
  - `review/review_decision.json`
  - `generation/*/prompt.txt`
  - `generation/*/submit.json`
  - `generation/*/result.json`
  - `generation/*/result.png`
  - `generation/*/qc.json`
- 检查 `analysis/product_analysis.json` 的 `product_type` 必须是手链/手串。
- 检查 `analysis/selected_references.json` 至少包含 Top 3，rank 必须覆盖 1/2/3，且候选参考图副本存在。
- 检查 `review/review_decision.json` 必须是可生成 action；`rerank` 和 `manual_reference` 不允许进入生成。
- 检查所选 rank 必须在 Top 3 中，不能重复，且符合 `generate_rank_1`、`generate_selected`、`generate_multiple` 的数量约束。
- 检查每个生成目录必须包含 `hand-reference.*`。
- 对每个 `prompt.txt` 调用或等价执行 `validate_prompt_contract.py`。
- 对每个 `qc.json` 调用或等价执行 `validate_qc_record.py`。
- 检查 `result.json` 状态是否完成。
- 如果提供最终汇总 JSON，检查最终汇总只引用当前 run 内 QC 为 `pass` 的 `generation/NN/result.png`。

验收：

- 空目录会列出缺失文件。
- 文件齐全但品类、review decision、prompt、QC 或 hand-reference 错误的 run 会失败。
- 完整运行目录输出 `run artifacts OK`。
- 最终汇总包含非 `pass` 图片时会失败。

### 任务 10：联动当前项目能力

Skill 不重新实现业务代码，只调用或约束当前项目能力：

- 产品分析模型：`C:\Users\Administrator\Documents\珠宝上手图片生成\src\jewelry_on_hand`
- prompt 构建：`C:\Users\Administrator\Documents\珠宝上手图片生成\src\jewelry_on_hand\prompt_builder.py`
- 参考图与 QC 文档：`C:\Users\Administrator\Documents\珠宝上手图片生成\reference`
- 运行与测试产物：`C:\Users\Administrator\Documents\珠宝上手图片生成\output`

验收：

```powershell
Set-Location 'C:\Users\Administrator\Documents\珠宝上手图片生成'
$PY='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $PY -m pytest -q
```

期望输出：`184 passed`

### 任务 11：正向触发测试

用自然语言触发 Skill 做一次 dry run，不调用 AIReiter、不写回飞书：

```text
使用 $jewelry-on-hand-workflow，基于已下载的 JH483 产品图规划一次上手图生成 dry run，不调用 AIReiter，不修改飞书，列出生成前必须存在的 gate。
```

期望回答必须包含：

- 产品图已保存。
- 产品分析 JSON 已生成。
- Top 3 参考图 review 包已生成。
- 用户已选择 rank。
- `review_decision.json` 已存在。
- prompt contract 已通过。
- AIReiter 生成产物已保存。
- QC 已检查原图手腕/手臂迁移。
- 最终汇总只包含 QC 通过图片。

验收：

- 如果 dry run 回答漏掉任何 gate，返回修改 `SKILL.md` 或 `workflow.md`，然后重新验证。

## 测试计划

### 静态验证

- `quick_validate.py` 校验 Skill 元数据。
- `rg` 检查 reference 中关键约束是否存在。
- Python 脚本无参运行时应返回 usage 和退出码 2。

### 单元级验证

- 坏 prompt 触发 `validate_prompt_contract.py` 失败。
- 好 prompt 触发 `validate_prompt_contract.py` 通过。
- 缺少原图手腕检查的 QC 触发 `validate_qc_record.py` 失败。
- 完整 QC 触发 `validate_qc_record.py` 通过。
- 空运行目录触发 `inspect_run_artifacts.py` 报缺失项。

### 项目回归

- 在项目根目录运行 `pytest -q`。
- 期望保持当前基线：`184 passed`。

### 端到端 dry run

- 不调用 AIReiter。
- 不写回飞书。
- 只验证从输入识别到 gate 列表的触发路径是否完整。

## 执行方式选择

推荐执行方式：

1. Subagent-Driven：按任务拆给子代理逐项实现，每完成一个任务主代理 review，适合减少遗漏。
2. Inline Execution：在当前会话按计划逐项实现，速度更快，但需要更频繁手动核对。

建议选择 1，因为这个 Skill 涉及多个文档、脚本、工作流 gate 和回归验证，子任务边界清晰，适合逐项 review。
