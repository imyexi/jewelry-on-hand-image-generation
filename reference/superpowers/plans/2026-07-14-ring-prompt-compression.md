# 戒指送模 Prompt 精简实施计划

> **供 agentic worker 使用：** 必须使用 `superpowers:executing-plans` 在当前会话逐项执行，所有生产修改遵循测试先行。

**目标：** 将标准戒指送模 Prompt 从约 3000 字压缩到不超过 1200 字，同时强化目标指位、真实环绕、产品身份和禁止额外首饰的优先级。

**架构：** 保留完整 `ProductAnalysis`、`ProductFidelityConstraints` 和参考图审计元数据，新增戒指专用精简渲染路径；其他品类继续使用现有公共模板。便携校验器验证八层契约、戒指核心语义、前 300 字优先规则和 1200 字上限。

**技术栈：** Python 3.11+、pytest、现有 `CategoryPolicy`、便携 Prompt contract 校验器。

## 全局约束

- 所有输出、注释和文档使用中文；参考文档放在 `reference/`，测试过程和临时产物放在 `output/`。
- 保留当前脏工作区已有改动，只修改与戒指 Prompt 精简直接相关的代码块。
- 标准戒指 Prompt 不超过 1200 个字符，前 300 字包含目标指位、真实环绕和禁止额外首饰。
- 超长时显式失败，不静默截断产品事实。
- canonical、审核数据和 QC 规则保持完整；只压缩实际送模文本。
- 手串、项链和带链吊坠行为不变。

---

### 任务 1：新增戒指精简 Prompt 失败测试

**文件：**
- 修改：`tests/test_prompt_builder.py`

**接口：**
- 输入：`build_generation_prompt(product, reference, constraints)`
- 输出：八层戒指 Prompt 或超长错误。

- [x] 新增单主石戒测试，断言长度不超过 1200、前 300 字包含右手无名指/真实环绕/禁止额外首饰，并且不包含参考图路径、rank、score 和匹配理由。
- [x] 新增开口戒测试，断言左手中指使用相邻手指定位、非目标手指不得佩戴、现有开口不得闭合。
- [x] 新增超长产品外观测试，断言抛出包含实际长度和 1200 上限的 `ValueError`。
- [x] 运行三个测试并确认它们因现有 3000 字模板和缺少新规则而失败。

### 任务 2：实现戒指专用精简渲染器

**文件：**
- 修改：`src/jewelry_on_hand/prompt_builder.py`
- 修改：`src/jewelry_on_hand/category_policies/ring.py`

**接口：**
- 新增：`build_ring_generation_prompt(product, reference, fidelity_constraints) -> str`
- 新增：戒指指位锚点、开口/主石条件规则和去重后的产品事实渲染。
- 保持：`build_generation_prompt(...) -> str` 公共签名不变。

- [x] 在公共入口仅对 `ProductType.RING` 分流到精简渲染器。
- [x] 把只生成一枚、确认指位、真实环绕和禁止额外首饰放到前 300 字。
- [x] 只渲染模型需要的产品事实和参考图信息，不展开完整 canonical 审计字段。
- [x] 构建后执行 1200 字硬上限检查，超限抛错。
- [x] 运行任务 1 测试并确认通过，再运行完整 `tests/test_prompt_builder.py`。

### 任务 3：更新便携 Prompt 契约

**文件：**
- 修改：`skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- 修改：`tests/test_prompt_builder.py`
- 修改：`tests/test_skill_portability.py`

**接口：**
- 输入：戒指 `prompt.txt`。
- 输出：缺少核心语义、核心语义位置过后或长度超限时返回中文错误。

- [x] 先新增校验器失败测试：超过 1200 字、前 300 字缺少指位/环绕/额外首饰禁令分别被拒绝。
- [x] 保留八层顺序和跨品类隔离校验，调整戒指固定片段为新精简文案。
- [x] 实现长度和优先位置检查，运行定向测试确认通过。

### 任务 4：全文修订 Prompt 文档

**文件：**
- 修改：`reference/prompt-template.md`
- 修改：`skills/jewelry-on-hand-workflow/references/prompt-contract.md`

- [x] 全文修订戒指策略、参考图字段和校验章节，明确完整审计数据与送模文本分离。
- [x] 删除“参考区必须发送路径、rank、score、匹配理由”等与新实现冲突的规定。
- [x] 检查文档不存在旧规则和新规则并存的矛盾表述。

### 任务 5：真实样例与完整回归验证

**文件：**
- 创建：`output/ring-prompt-compression/2026-07-14/verification.json`
- 创建：`output/ring-prompt-compression/2026-07-14/single-center-stone-prompt.txt`
- 创建：`output/ring-prompt-compression/2026-07-14/open-ring-prompt.txt`

- [x] 用两个 `run-v2` 的 analysis、canonical 和 rank 1 参考图重新构建 Prompt。
- [x] 记录字符数、前 300 字核心语义位置、Prompt contract 结果和 SHA-256。
- [x] 运行 `tests/test_prompt_builder.py`、`tests/test_skill_portability.py` 和完整测试集。
- [x] 检查 `git diff`，确保没有覆盖或回退工作区原有无关修改。
