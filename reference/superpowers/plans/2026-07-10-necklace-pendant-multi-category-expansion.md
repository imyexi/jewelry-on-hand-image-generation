# 项链与吊坠多品类扩展实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有手串行为和历史运行产物兼容性的前提下，为统一珠宝工作流增加普通项链与带链吊坠的真人佩戴、手持展示能力，并对无链吊坠、非法输入和超范围结构执行明确拦截。

**Architecture:** 继续复用现有 CLI、RunPaths、人工决策 gate、参考图 Top 3、生成和 QC 主流程；新增规范枚举与品类策略层，把输入限制、参考图适配、提示词片段和 QC 必检项从手串专用逻辑中分离。先把现有手串行为迁移到兼容策略，再接入项链产品分析、参考图评分、审核确认、生成校验和分类 QC。

**Tech Stack:** Python 3.11+、frozen dataclass、标准库 `argparse/json/pathlib`、pytest、现有 HTML review package、AIReiter helper。

## Global Constraints

- 所有思考、代码注释、CLI 文案、错误信息和文档使用中文。
- 所有参考文档和流程 `.md` 文件放在 `reference/`；所有真实生成和测试过程产物放在 `output/`。
- 用户仍只提交一张产品原图；模型内部图 1 是参考图，内部图 2 是产品身份唯一来源。
- 第一阶段项链输入只接受真人佩戴原图，不接受白底、平铺或手持产品原图。
- 支持普通项链和带链吊坠的一至三层“单件产品自身结构”；拒绝多件独立项链叠戴。
- 一至三层属于数据模型、运行时和自动化契约测试的兼容目标；真实模型验收只使用当前产品目录中的实际商品，当前没有三圈带链吊坠，不要求该组合的真实生成证据。
- 项链默认真人佩戴，用户可切换为手持；无链独立吊坠和无法识别品类不得生成。
- 禁止自动补链，禁止推断不可见扣头或背面结构。
- 现有手串/手链行为、旧自由文本 `product_type` 和历史 run 必须兼容。
- 当前工作区已有未提交改动；不得回退、覆盖或顺手提交与本功能无关的改动。

---

## 文件结构与职责

**新增文件**

- `src/jewelry_on_hand/product_types.py`：规范产品品类、旧值映射、显示名称和品类判断。
- `src/jewelry_on_hand/display_modes.py`：展示模式、输入图类型、兼容矩阵和生成前基础校验。
- `src/jewelry_on_hand/category_policies/__init__.py`：按规范品类返回策略。
- `src/jewelry_on_hand/category_policies/base.py`：策略协议、通用参考图适配结果和 QC 项接口。
- `src/jewelry_on_hand/category_policies/bracelet.py`：封装现有手串兼容规则。
- `src/jewelry_on_hand/category_policies/necklace.py`：普通项链和带链吊坠的结构、参考图、提示词和 QC 规则。
- `src/jewelry_on_hand/category_policies/pendant.py`：无链吊坠的明确拦截策略。
- `tests/test_product_types.py`：枚举、旧值映射和未知值测试。
- `tests/test_display_modes.py`：模式兼容矩阵测试。
- `tests/test_category_policies.py`：策略选择和品类规则测试。

**重点修改文件**

- `src/jewelry_on_hand/models.py`：扩展产品分析模型，保留旧 JSON 读取兼容。
- `src/jewelry_on_hand/product_analysis.py`：从手串白名单升级为多品类分析校验。
- `src/jewelry_on_hand/reference_catalog.py`：读取通用参考图字段，同时兼容旧分类表。
- `src/jewelry_on_hand/scoring.py`：公共评分框架调用品类策略，支持项链佩戴和手持。
- `src/jewelry_on_hand/prompt_builder.py`：基础安全边界与品类/展示模式片段组合。
- `src/jewelry_on_hand/review_package.py`：审核页展示并确认品类、模式和项链结构。
- `src/jewelry_on_hand/review_decision.py`：决策文件记录确认快照并校验。
- `src/jewelry_on_hand/generation.py`：生成前执行兼容矩阵与结构校验。
- `src/jewelry_on_hand/qc.py`：输出品类/模式必检项并校验严重错误。
- `src/jewelry_on_hand/cli.py`：暴露品类确认、展示模式和结构纠正参数。
- `skills/jewelry-on-hand-workflow/`：实现完成后全文修订技能说明、工作流、Prompt/QC 校验脚本。
- `reference/*.md`：实现完成后全文修订 Schema、人工流程、Prompt 与 QC 文档。

---

### Task 1: 建立规范品类、模式与策略骨架

**Files:**
- Create: `src/jewelry_on_hand/product_types.py`
- Create: `src/jewelry_on_hand/display_modes.py`
- Create: `src/jewelry_on_hand/category_policies/__init__.py`
- Create: `src/jewelry_on_hand/category_policies/base.py`
- Create: `src/jewelry_on_hand/category_policies/bracelet.py`
- Create: `src/jewelry_on_hand/category_policies/necklace.py`
- Create: `src/jewelry_on_hand/category_policies/pendant.py`
- Test: `tests/test_product_types.py`
- Test: `tests/test_display_modes.py`
- Test: `tests/test_category_policies.py`

**Interfaces:**
- Produces: `ProductType`、`normalize_product_type(value: str) -> ProductType`、`DisplayMode`、`SourceImageType`、`validate_product_mode(...) -> None`、`get_category_policy(product_type: ProductType) -> CategoryPolicy`。
- Consumes: 无新增接口，仅使用标准库枚举、dataclass 和现有 `ReferenceRow` 类型提示。

- [ ] **Step 1: 编写规范品类与旧值映射失败测试**

覆盖中文/英文手串旧值、普通项链、带链吊坠、无链吊坠和无法识别值。

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `pytest tests/test_product_types.py -v`

- [ ] **Step 3: 最小实现 `product_types.py`**

使用 `str, Enum`，保留原始自由文本映射；模糊值不静默猜测为支持品类。

- [ ] **Step 4: 编写展示模式兼容矩阵失败测试**

覆盖项链默认佩戴、项链手持、无链吊坠拒绝、unknown 拒绝、非法输入类型拒绝。

- [ ] **Step 5: 运行测试并确认失败**

Run: `pytest tests/test_display_modes.py -v`

- [ ] **Step 6: 最小实现 `display_modes.py`**

错误信息必须指出产品品类、展示模式或输入图类型不兼容的具体原因。

- [ ] **Step 7: 编写策略选择与基础规则失败测试**

覆盖手串、项链、带链吊坠、无链吊坠及 unknown。

- [ ] **Step 8: 运行测试并确认失败**

Run: `pytest tests/test_category_policies.py -v`

- [ ] **Step 9: 实现最小策略骨架**

策略先提供品类名称、支持模式、最大层数、生成拦截和基础 QC 项；不在本任务改动现有评分/Prompt。

- [ ] **Step 10: 运行新增测试和现有模型测试**

Run: `pytest tests/test_product_types.py tests/test_display_modes.py tests/test_category_policies.py tests/test_models.py -v`

---

### Task 2: 扩展产品分析模型并兼容历史 JSON

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/product_analysis.py`
- Modify: `reference/product-analysis-schema.md`
- Test: `tests/test_models.py`
- Test: `tests/test_product_analysis.py`

**Interfaces:**
- Consumes: `ProductType`、`DisplayMode`、`SourceImageType`、`normalize_product_type`。
- Produces: 扩展后的 `ProductAnalysis`，包含 `detected_product_type`、`confirmed_product_type`、`classification_confidence`、`classification_evidence`、`classification_source`、`display_mode`、`source_image_type`、`layer_count`、`length_category`、吊坠结构和不确定字段；旧属性 `product_type` 保持可读兼容。

- [ ] **Step 1: 为旧手串 JSON 兼容读取编写测试**
- [ ] **Step 2: 为项链和带链吊坠结构编写有效测试**
- [ ] **Step 3: 为层数越界、吊坠层越界、多件独立叠戴和非法输入类型编写失败测试**
- [ ] **Step 4: 运行目标测试并确认新增用例失败**

Run: `pytest tests/test_models.py tests/test_product_analysis.py -v`

- [ ] **Step 5: 最小扩展 dataclass 与 `from_dict` 兼容逻辑**
- [ ] **Step 6: 在产品分析加载阶段调用兼容矩阵和结构校验**
- [ ] **Step 7: 全文修订产品分析 Schema，使其同时描述已实现手串与目标多品类字段**
- [ ] **Step 8: 运行模型与分析测试**

Run: `pytest tests/test_models.py tests/test_product_analysis.py -v`

---

### Task 3: 通用化参考图库字段

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/reference_catalog.py`
- Modify: `src/jewelry_on_hand/feishu_reference_source.py`
- Modify: `reference/feishu-reference-source.md`
- Test: `tests/test_reference_catalog.py`
- Test: `tests/test_feishu_reference_source.py`

**Interfaces:**
- Consumes: 旧中文表头和新增通用字段。
- Produces: `ReferenceRow` 的通用属性：适用品类、适用模式、取景范围、可见身体区域、预计展示面积、颈/锁骨/胸前/手部可见度、衣领、衣物/头发遮挡风险、原有首饰和裁切风险；`combined_text()` 仍供兼容评分使用。

- [ ] **Step 1: 编写新旧分类表并存读取测试**
- [ ] **Step 2: 编写缺少项链关键标注时不默认为适用的测试**
- [ ] **Step 3: 运行测试并确认失败**

Run: `pytest tests/test_reference_catalog.py tests/test_feishu_reference_source.py -v`

- [ ] **Step 4: 扩展 `ReferenceRow` 与字段别名读取**
- [ ] **Step 5: 保持旧手串分类表解析行为不变**
- [ ] **Step 6: 运行参考来源相关测试**

Run: `pytest tests/test_reference_catalog.py tests/test_feishu_reference_source.py tests/test_feishu_enrichment_cli.py -v`

---

### Task 4: 将参考图筛选与评分接入品类策略

**Files:**
- Modify: `src/jewelry_on_hand/scoring.py`
- Modify: `src/jewelry_on_hand/category_policies/base.py`
- Modify: `src/jewelry_on_hand/category_policies/bracelet.py`
- Modify: `src/jewelry_on_hand/category_policies/necklace.py`
- Test: `tests/test_scoring.py`
- Test: `tests/test_category_policies.py`

**Interfaces:**
- Consumes: `ProductAnalysis`、通用化 `ReferenceRow`、`get_category_policy()`。
- Produces: 保持 `score_reference()`、`select_top_references()` 和批次多样性接口兼容；新增按品类/模式硬过滤和风险理由。

- [ ] **Step 1: 固化现有手串评分回归测试**
- [ ] **Step 2: 编写项链佩戴硬过滤测试**

覆盖颈胸区域、长度取景、产品展示面积、衣领/头发遮挡和缺少项链标注。

- [ ] **Step 3: 编写项链手持硬过滤测试**

覆盖手部可见、垂落空间、关键结构遮挡和腕部专用图拒绝。

- [ ] **Step 4: 编写长项链与多层项链评分测试**
- [ ] **Step 5: 运行测试并确认失败**

Run: `pytest tests/test_scoring.py tests/test_category_policies.py -v`

- [ ] **Step 6: 抽取公共评分并由策略返回适配结果/加减分项**
- [ ] **Step 7: 保持旧手串字段的回退路径**
- [ ] **Step 8: 扩展多样性 profile：取景、衣领、头发位置、身体朝向或手持方式**
- [ ] **Step 9: 运行评分与批次重排测试**

Run: `pytest tests/test_scoring.py tests/test_cli.py -k "rerank or scoring or reference" -v`

---

### Task 5: 分层构建多品类 Prompt

**Files:**
- Modify: `src/jewelry_on_hand/prompt_builder.py`
- Modify: `src/jewelry_on_hand/category_policies/base.py`
- Modify: `src/jewelry_on_hand/category_policies/bracelet.py`
- Modify: `src/jewelry_on_hand/category_policies/necklace.py`
- Modify: `reference/prompt-template.md`
- Modify: `skills/jewelry-on-hand-workflow/references/prompt-contract.md`
- Modify: `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- Test: `tests/test_prompt_builder.py`

**Interfaces:**
- Consumes: 已确认 `ProductAnalysis`、`ScoredReference`、品类策略。
- Produces: 现有 `build_generation_prompt()` 签名保持兼容；输出基础安全边界、双图职责、品类保真、模式约束、遮挡物理和禁止项片段。

- [ ] **Step 1: 固化现有手串 Prompt 契约回归测试**
- [ ] **Step 2: 编写项链佩戴 Prompt 失败测试**

断言包含层数、长度等级、层间落差、吊坠所属层、禁止颈部/衣服贴片、禁止自动补链。

- [ ] **Step 3: 编写项链手持 Prompt 失败测试**

断言包含真实接触、自然垂落、禁止穿手、禁止删改链条和禁止迁移原图人物。

- [ ] **Step 4: 运行测试并确认失败**

Run: `pytest tests/test_prompt_builder.py -v`

- [ ] **Step 5: 抽取公共 Prompt 片段并接入品类策略**
- [ ] **Step 6: 全文修订 Prompt 参考文档和便携技能契约**
- [ ] **Step 7: 运行 Prompt 测试和校验脚本测试**

Run: `pytest tests/test_prompt_builder.py tests/test_skill_portability.py -v`

---

### Task 6: 升级审核页与决策快照

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/review_package.py`
- Modify: `src/jewelry_on_hand/review_decision.py`
- Modify: `src/jewelry_on_hand/cli.py`
- Modify: `reference/review-decision-schema.md`
- Test: `tests/test_models.py`
- Test: `tests/test_review_package.py`
- Test: `tests/test_review_decision.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: 扩展 `ProductAnalysis`、Top 3 参考图。
- Produces: 审核页产品确认区、参考图风险区；决策文件保存 `confirmed_product_type`、`source_image_type`、`display_mode`、结构确认快照和 `fidelity_confirmed`。

- [ ] **Step 1: 编写审核页展示自动识别、输入图类型、人工确认、层数/长度/吊坠、遮挡/不确定细节和风险字段的测试**
- [ ] **Step 2: 编写决策文件缺少确认快照时拒绝项链生成的测试**
- [ ] **Step 3: 编写 CLI 人工纠正品类、输入图类型、模式和结构参数测试**
- [ ] **Step 4: 运行测试并确认失败**

Run: `pytest tests/test_review_package.py tests/test_review_decision.py tests/test_cli.py -v`

- [ ] **Step 5: 扩展审核 HTML，保持旧手串页面兼容**
- [ ] **Step 6: 扩展决策模型与写入校验，保存品类、输入图类型、模式和结构确认快照**
- [ ] **Step 7: 增加 CLI 参数并把纠正结果写入分析/决策快照**
- [ ] **Step 8: 运行审核与 CLI 测试**

Run: `pytest tests/test_review_package.py tests/test_review_decision.py tests/test_cli.py -v`

---

### Task 7: 生成前多品类硬校验

**Files:**
- Modify: `src/jewelry_on_hand/generation.py`
- Modify: `src/jewelry_on_hand/display_modes.py`
- Modify: `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- Test: `tests/test_generation.py`
- Test: `tests/test_skill_portability.py`

**Interfaces:**
- Consumes: 产品分析、决策快照、选中参考图、兼容矩阵。
- Produces: 只在全部 gate 通过后提交模型；错误信息精确说明 unknown、无链吊坠、输入类型、展示模式、层数或独立叠戴问题。

- [ ] **Step 1: 编写合法项链佩戴与手持生成测试**
- [ ] **Step 2: 编写 unknown、无链吊坠、白底/手持输入、四层、多件叠戴和决策快照不一致的拒绝测试**
- [ ] **Step 3: 运行测试并确认失败**

Run: `pytest tests/test_generation.py -v`

- [ ] **Step 4: 将固定手串校验替换为规范品类/模式/结构校验**
- [ ] **Step 5: 更新 run 产物检查脚本，兼容旧手串和新项链 JSON**
- [ ] **Step 6: 运行生成与便携技能测试**

Run: `pytest tests/test_generation.py tests/test_skill_portability.py -v`

---

### Task 8: 分类 QC 与严重错误 gate

**Files:**
- Modify: `src/jewelry_on_hand/qc.py`
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- Modify: `reference/qc-checklist.md`
- Modify: `skills/jewelry-on-hand-workflow/references/qc-checklist.md`
- Test: `tests/test_qc.py`
- Test: `tests/test_models.py`
- Test: `tests/test_skill_portability.py`

**Interfaces:**
- Consumes: 产品品类、展示模式、`must_keep` 和人工 QC 输入。
- Produces: 品类/模式必检项；关键项失败时禁止整体 `pass`。

- [ ] **Step 1: 编写项链佩戴 QC 必检项测试**
- [ ] **Step 2: 编写项链手持 QC 必检项测试**
- [ ] **Step 3: 编写层数、长度、吊坠换层、自动补链、人物贴片失败时不能 pass 的测试**
- [ ] **Step 4: 运行测试并确认失败**

Run: `pytest tests/test_qc.py tests/test_models.py -v`

- [ ] **Step 5: 实现策略驱动的 QC 清单和状态校验**
- [ ] **Step 6: 全文修订 QC 文档和校验脚本**
- [ ] **Step 7: 运行 QC 与便携技能测试**

Run: `pytest tests/test_qc.py tests/test_models.py tests/test_skill_portability.py -v`

---

### Task 9: 全流程 CLI 与历史兼容回归

**Files:**
- Modify: `src/jewelry_on_hand/cli.py`
- Modify: `src/jewelry_on_hand/generation.py`
- Modify: `src/jewelry_on_hand/review_package.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_generation.py`
- Test: `tests/test_run_paths.py`
- Test: `tests/test_package_import.py`

**Interfaces:**
- Consumes: Tasks 1-8 的所有公共接口。
- Produces: 手串旧流程和项链新流程均可从 CLI 完成 prepare-review → record-decision → generate → qc。

- [ ] **Step 1: 编写普通项链佩戴端到端测试**
- [ ] **Step 2: 编写带链吊坠手持端到端测试**
- [ ] **Step 3: 编写历史手串 run 和旧 JSON 端到端回归测试**
- [ ] **Step 4: 运行端到端测试并确认新增用例失败**
- [ ] **Step 5: 补齐 CLI 数据流和兼容映射**
- [ ] **Step 6: 运行所有自动化测试**

Run: `pytest -v`

---

### Task 10: 全文修订技能和操作文档

**Files:**
- Modify: `CLAUDE.md`
- Modify: `skills/jewelry-on-hand-workflow/SKILL.md`
- Modify: `skills/jewelry-on-hand-workflow/references/workflow.md`
- Modify: `skills/jewelry-on-hand-workflow/references/troubleshooting.md`
- Modify: `reference/manual-workflow.md`
- Modify: `reference/product-fidelity-constraints-schema.md`
- Modify: `reference/codex-skill-installation.md`（仅在调用方式变化时）
- Test: `tests/test_skill_portability.py`

**Interfaces:**
- Consumes: 已完成且验证的实际行为。
- Produces: 不互相矛盾的完整操作文档；不得只在文档末尾追加“新增项链支持”。

- [ ] **Step 1: 搜索所有“仅支持手串/手腕专用”现行说明**

Run: `rg -n "只支持|仅支持|手串/手链|手链/手串|手腕来源|原图手腕" CLAUDE.md skills reference --glob "*.md" --glob "!reference/superpowers/plans/**" --glob "!reference/superpowers/specs/2026-06-12-*"`

- [ ] **Step 2: 按实际实现全文修订现行文档**
- [ ] **Step 3: 更新技能便携副本和三个校验脚本**
- [ ] **Step 4: 运行技能可移植性测试**

Run: `pytest tests/test_skill_portability.py -v`

---

### Task 11: 真实模型证据与最终验证

**Files:**
- Create: `output/multi-category-validation/<date>/...`
- Modify: `reference/superpowers/specs/2026-07-10-necklace-pendant-multi-category-expansion-design.md`（仅当真实验证暴露规格歧义时，全文修订相关章节）

**Interfaces:**
- Consumes: 完整 CLI 工作流和真实测试素材。
- Produces: SPEC 第 19.2、19.3 节的全部验收证据，包括一至三层兼容、超过三层拒绝、多件独立叠戴拒绝和不得自动补链的自动化契约证据；基于当前产品目录的手串回归、普通项链单层/双层真人佩戴、带链吊坠单层真人佩戴、普通项链单层手持和带链吊坠双层手持真实生成与 QC 证据；无链吊坠、白底/平铺图、手持产品原图和多件独立叠戴的预提交拒绝证据；`unknown` 必须人工纠正的证据；长项链不得选择会裁切产品的锁骨特写参考图的证据。不要求不存在的三圈带链吊坠真实证据。

- [ ] **Step 1: 运行全套自动化测试并保存输出到 `output/`，确认一至三层结构契约、超过三层拒绝、多件独立叠戴拒绝和禁止自动补链均有覆盖**
- [ ] **Step 2: 用一个手串 SKU 做真实回归生成和 QC**
- [ ] **Step 3: 用一个普通项链单层 SKU 做真人佩戴生成和 QC**
- [ ] **Step 4: 用一个普通项链双层 SKU 做真人佩戴生成和 QC**
- [ ] **Step 5: 用一个带链吊坠单层 SKU 做真人佩戴生成和 QC**
- [ ] **Step 6: 用一个普通项链单层 SKU 做手持生成和 QC**
- [ ] **Step 7: 用一个带链吊坠双层 SKU 做手持生成和 QC**
- [ ] **Step 8: 验证无链吊坠、白底/平铺图、手持产品原图和多件叠戴在提交模型前被拒绝**
- [ ] **Step 9: 验证 `unknown` 品类必须先人工纠正，并验证长项链不会选择会裁切产品的锁骨特写参考图**
- [ ] **Step 10: 检查 git diff，确认没有覆盖原有未提交改动**
- [ ] **Step 11: 运行最终测试**

Run: `pytest -v`

Expected: Step 1 至 Step 11 全部完成：一至三层兼容、超过三层拒绝、多件独立叠戴拒绝和不得自动补链均有自动化契约证据；第 2 至 7 步按当前产品目录完成真实生成和人工 QC；第 8 步四类非法输入或结构均在提交模型前被拒绝；第 9 步证明 `unknown` 必须人工纠正且长项链参考图不会裁切产品；git diff 未覆盖既有改动；最终测试全部通过。当前不存在三圈带链吊坠，因此不以该组合的真实生成作为完成条件；任何真实场景都不能用“任务已提交”替代成图与 QC 证据。
