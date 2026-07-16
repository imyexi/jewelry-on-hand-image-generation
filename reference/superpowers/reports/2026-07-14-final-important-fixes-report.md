# 项链最终重要问题 I1-I4 修复报告

**日期：** 2026-07-14
**范围：** 只处理最终代码审查 I1-I4；不处理 I5 真实 proof，不修改 HERO、戒指、飞书范围，不修改历史 run/output proof，不提交或暂存。

## 基线与根因

- 当前分支为 `codex/feishu-reference-source`，工作树在本波次开始前已有大量 tracked/untracked 并发改动。本波次逐文件保留既有实现，只修改 I1-I4 必需位置。
- I1 根因：`src/jewelry_on_hand/product_fidelity.py` 的 `_first_matching_alias()` 原先只做子串命中；首次修复仍漏同义保留词；第二轮仍漏字段和宾语前置语序；第三轮虽统一字段与动作类别，却把同一分句中的任意禁止词应用到全部动作，导致前半“禁止创造”污染后半正向保留。
- I2 根因：`prepare-review` 先按初始 analysis 评分并复制 Top 3，人工纠正只发生在 `record-decision`；非戒指生成只确认 `selected_reference` 路径存在，未按最终 analysis 复核策略、当前 run review 目录和审核摘要。
- I3 根因：`ProductAnalysis` 为分析/纠正阶段兼容 `length_category=null`，但参考评分、决策、生成和便携 inspector 没有独立的“可评分/可生成”完整性门禁。
- I4 根因：`prepare-review` 直接使用会拒绝 `unknown` 的 `load_product_analysis()`，同时没有评分前人工纠正入口，导致最需要纠正的记录无法进入正式 Top 3 流程。

## I1：否定吊坠语义与 canonical 纵深防御

### RED

- 聚焦测试位于 `tests/test_final_necklace_important_fixes.py`，使用真实历史输入 `output/multi-category-validation/2026-07-13/real-proof/necklace-worn-double/run-20260713-double-necklace-04/analysis/product_analysis.json`；只读取该 analysis，不修改任何历史 proof。
- 首次 RED 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'run04 or negative_pendant or positive_and_mixed or necklace_without_pendant' -q`
- 首次 RED 退出码 `1`，结果 `13 failed, 1 passed`：真实 run04 的“不是悬挂吊坠”和八类否定表达仍提取 `detected_keywords=("吊坠",)`；混合转折句错误选择否定分句中的别名；普通项链 canonical 可注入 `normalized_keyword=吊坠` 或“必须保留主吊坠”而不报错。
- 第二轮复审新增参数化 RED，覆盖 `must_not_change/source_text/visual_shape/relationship/name/location/qc_question` 中的“不得改变主吊坠”“不可改变吊坠连接”“维持主吊坠形状”“继续保有/保有吊坠”“不可删除吊坠”“保全吊坠”。
- 第二轮 RED 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'synonymous_positive_pendant or pendant_creation_prohibitions or pendant_necklace_allows_positive' -q`
- 第二轮 RED 退出码 `1`，结果 `7 failed, 5 passed, 35 deselected in 0.20s`：七种同义正向保留语义均错误通过；四种禁止新增/改造语义和带链吊坠正向语义已通过。
- 第三轮复审把 RED 扩为完整 canonical 字段矩阵：`name/source_text/normalized_keyword/location/visual_shape/relationship/*forbid/qc_question/must_not_change/detected_keywords`，keyword 字段使用规范别名 `链坠/流苏`，并单独覆盖四种动作、对象顺序。
- 第三轮 RED 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'every_canonical_field or order_independent or explicit_absence or creation_prohibitions or rejection_of_pendant_preservation or pendant_necklace_allows' -q`
- 第三轮 RED 退出码 `1`，结果 `13 failed, 12 passed, 35 deselected in 0.25s`：十类字段全部可绕过；“不得对主吊坠进行任何改变”“不得让主吊坠发生改变”“不允许对现有吊坠做删除或替换”三种自然语序漏判，“主吊坠不得发生任何改变”已被第二轮捕获。没有/不是/无吊坠、五种禁止创造、禁止/无需保留吊坠及带链吊坠正向语义共 12 项保持通过。
- 第四轮复审增加三条原样复合语义、11 个连接词矩阵、六种直接否定保留表达和四种禁止破坏既有吊坠表达；同时用“中央圆珠并非吊坠”锁定 `并` 不得拆开 `并非`。
- 第四轮 RED 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'mixed_creation or compound_clause or explicit_absence or rejection_of_pendant_preservation or prohibited_destruction' -q`
- 第四轮 RED 退出码 `1`，结果 `12 failed, 16 passed, 55 deselected in 0.26s`：三条原样语义和 `且/以及/并/而且/又` 五类未切分连接词共 8 项漏判；“不要/不/不需要/不应保留吊坠”四项误拒。已切分的 `并且/同时/但/但是/不过/然而`、明确缺失、禁止/无需保留和禁止破坏既有吊坠共 16 项保持正确。

### GREEN

- 实现文件：`src/jewelry_on_hand/product_fidelity.py`。
- 首次实现按中文标点和转折词拆分语义片段，识别直接否定、禁止“改成/新增/补造/悬挂化”和内部图 1/参考素材语境，只选择肯定片段中的别名；普通项链 `has_pendant=false` 的自动 canonical 不再写吊坠保持项。
- 第二轮补强把 canonical 文本按分句和动作极性分类：禁止改变、删除、丢失既有吊坠，以及保持、维持、保有、保全吊坠，均属于正向保留；禁止新增、补造、改成、转成或悬挂化吊坠属于合法的禁止创造语义。
- 第三轮新增统一的 `_iter_constraint_semantic_fields()`，由 `_constraints_semantic_text()` 与 I1 校验共同遍历全部 canonical 字段；`detected_keywords/normalized_keyword` 对 `吊坠/主吊坠/流苏/链坠` 做结构拒绝，不再依赖长句 keyword 测试。
- 每个分句只按对象、动作类别和极性是否存在判定，不依赖三者顺序：明确缺失、禁止创造/转换为吊坠、禁止或无需保留吊坠可以通过；其余含吊坠对象的分句均拒绝。字段上下文区分 `forbid` 与 `must_not_change`：前者可隐含“禁止保留”，后者只为新增/转换提供隐含禁止，避免误放“必须保留主吊坠”。
- 第三轮聚焦 GREEN 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'every_canonical_field or order_independent or explicit_absence or creation_prohibitions or rejection_of_pendant_preservation or pendant_necklace_allows' -q`
- 第三轮聚焦 GREEN 退出码 `0`，结果 `25 passed, 35 deselected in 0.16s`。
- 首次整文件回归结果 `1 failed, 59 passed`：`must_not_change` 被错误当成可隐含“禁止保留”；按上述单一字段上下文修正后，`uv run pytest tests/test_final_necklace_important_fixes.py -q` 退出码 `0`，结果 `60 passed in 0.37s`。
- 第四轮新增 `_split_pendant_semantic_clauses()`，覆盖 `且/以及/并/并且/同时/而且/但/但是/不过/然而/又` 等并列与转折边界，并用 `并(?!非|不)` 保留 `并非/并不` 的否定短语完整性。
- 第四轮新增 `_actions_are_locally_negated()`：否定只作用于当前 clause 内、且不跨另一类别动作；“禁止创造 + 正向保留”拆开判定，直接否定“不要/不/不需要/不应保留”只否定保留动作，禁止改变/删除/丢失/替换既有吊坠仍拒绝。统一字段迭代器保持不变。
- 第四轮聚焦 GREEN 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'mixed_creation or compound_clause or explicit_absence or rejection_of_pendant_preservation or prohibited_destruction' -q`；退出码 `0`，结果 `28 passed, 55 deselected in 0.14s`。
- I1-I4 聚焦文件命令：`uv run pytest tests/test_final_necklace_important_fixes.py -q`；退出码 `0`，结果 `83 passed in 0.71s`。
- product-fidelity/canonical + portability 命令：`uv run pytest tests/test_product_analysis.py tests/test_skill_portability.py -k 'fidelity or canonical' -q`；退出码 `0`，结果 `30 passed, 74 deselected in 0.60s`。
- 完整 product-analysis + portability 命令：`uv run pytest tests/test_product_analysis.py tests/test_skill_portability.py -q`；退出码 `0`，结果 `104 passed in 0.51s`。

## I2：人工纠正后的参考重选与生成复核

### RED

- 新增三组聚焦测试：四类晚期纠正（佩戴→手持、手持→佩戴、长链、层数）必须拒绝且不改写 analysis/Top 3/decision；相同纠正在新 `prepare-review` 中必须按最终分析重评分；生成前必须拒绝外部 selected path、review 副本 SHA-256 篡改和展示模式 metadata 篡改。
- 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'late_reference_affecting or applies_corrections_before_rescoring or revalidates_necklace_reference' -q`
- 退出码：`1`。
- 结果：`10 failed, 1 passed, 24 deselected in 0.41s`。
- 预期失败原因：四类晚期纠正均被静默提交；`prepare-review` 不识别 display/layer 参数；非戒指生成放过外部路径、摘要篡改和策略 metadata 篡改。

### GREEN

- 实现文件：`src/jewelry_on_hand/cli.py`、`src/jewelry_on_hand/generation.py`；回归夹具同步更新 `tests/test_cli.py`、`tests/test_generation.py`。
- `prepare-review` 在评分前接受并应用项链参考适配字段纠正：`confirmed_product_type`、`source_image_type`、`display_mode`、`layer_count`、`length_category`、吊坠结构字段和多件独立组合标记；随后按最终 analysis 评分、复制 Top 3 和构建 canonical。
- `record-decision` 若检测到真实改变项链参考适配的字段，则在写文件前拒绝，要求新建 run 并重新执行 `prepare-review`；传入与当前 analysis 相同的值不会改写文件。戒指既有晚期纠正路径保持不变。
- 非 HERO 项链生成 gate 逐项校验 selected path 位于当前 run `review_dir`、`source_sha256/review_sha256` 与实际副本一致，并从审核 metadata 重建 `ReferenceRow`，按最终品类、展示模式、长度、裁切和手持策略重新执行 `policy.evaluate_reference()`。HERO 分支显式保持既有行为，不修改角色评分策略。
- 聚焦命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'late_reference_affecting or applies_corrections_before_rescoring or revalidates_necklace_reference' -q`
- 退出码：`0`；结果：`11 passed, 24 deselected in 0.25s`。
- 首轮相关回归命令：`uv run pytest tests/test_cli.py tests/test_generation.py tests/test_review_decision.py tests/test_review_package.py tests/test_scoring.py tests/test_product_analysis.py tests/test_skill_portability.py tests/test_final_necklace_important_fixes.py -q`
- 首轮退出码：`1`；结果：`35 failed, 398 passed`。失败来自旧 CLI 测试仍期待晚期项链纠正，以及现代 generation 夹具仍直接引用 review 外路径或缺少摘要；均属于新契约下的过时夹具，不是生产 gate 误拒。
- 协调后复跑退出码：`0`；结果：`433 passed in 1.93s`。旧项链 CLI 用例改为验证晚期拒绝或在 prepare 前纠正；现代 generation 夹具改用当前 run review 副本和审核摘要；legacy 无 analysis 流程仍兼容。

## I3：现代项链长度等级完整性

### RED

- 聚焦测试覆盖 `prepare-review`、`record-decision`、`generate`、便携 inspector，以及合法四值 `choker/collarbone/upper_chest/long`。
- 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'null_necklace_length or legal_necklace_lengths' -q`
- 退出码：`1`。
- 结果：`4 failed, 4 passed, 14 deselected in 0.20s`。
- 预期失败原因：现代项链 `length_category=null` 可写出 Top 3、生成决策并走到 helper；inspector 也不报错。四个合法长度值均保持通过，证明失败只针对缺失值而非闭集误判。

### GREEN

- 实现文件：`src/jewelry_on_hand/product_analysis.py`、`src/jewelry_on_hand/scoring.py`、`src/jewelry_on_hand/review_decision.py`、`skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`；同步修订既有合法项链测试数据 `tests/test_product_analysis.py`。
- `ProductAnalysis.from_dict()` 继续允许 correction-only 的 `null`；新增“可评分/可生成”校验，供正式加载、评分、决策与生成共同调用。便携 inspector 独立执行同一中文边界。非项链及历史手串的 `null` 行为未改变。
- 聚焦命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'null_necklace_length or legal_necklace_lengths' -q`
- 退出码：`0`；结果：`8 passed, 14 deselected in 0.38s`。
- 相关回归命令：`uv run pytest tests/test_product_analysis.py tests/test_scoring.py tests/test_review_decision.py tests/test_generation.py tests/test_skill_portability.py -q`
- 首轮退出码：`1`；结果：`2 failed, 337 passed`。两条旧合法/来源测试未填写长度，分别被新门禁先于原断言拒绝；为其补入合法 `collarbone` 后复跑。
- 复跑退出码：`0`；结果：`339 passed in 1.14s`。
- 后续 CLI 回归补充：`uv run pytest tests/test_cli.py tests/test_product_analysis.py -q` 首轮发现 5 条旧 `record-decision` 项链夹具仍用 `length_category=null`，补合法 `collarbone` 并移除一次误插入的重复关键字参数后，复跑 `67 passed in 0.61s`、退出码 `0`。

## I4：unknown 人工纠正正式闭环

### RED

- 新增正式 CLI 正向 E2E：`detected_product_type=unknown`，在 `prepare-review` 传入人工确认品类与长度，随后检查按最终项链 analysis 生成的 Top 3，再执行 `record-decision` 与 `generate` gate；helper 由本地假函数代替，不提交真实生成任务。同时保留未纠正最终 unknown 的预评分拒绝用例。
- 命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'unknown_can_be_corrected or final_unknown' -q`
- 退出码：`1`。
- 结果：`1 failed, 1 passed, 22 deselected in 0.20s`。
- 预期失败原因：正式 `prepare-review` 尚无 `--confirmed-product-type` 和 `--length-category`，argparse 退出码为 2；未纠正 unknown 仍在 Top 3 前被拒，原安全边界保持。

### GREEN

- 实现文件：`src/jewelry_on_hand/cli.py`。
- `prepare-review` 先用 correction-only 路径解析输入，保留 `detected_product_type=unknown`，再把人工值写入最终 `confirmed_product_type`，并记录 `classification_source=manual_override`；完成现代项链结构校验后才允许评分、复制 Top 3 和构建 canonical。未纠正最终 unknown 仍在 Top 3 前拒绝。
- 聚焦命令：`uv run pytest tests/test_final_necklace_important_fixes.py -k 'unknown_can_be_corrected or final_unknown' -q`
- 退出码：`0`；结果：`2 passed, 22 deselected in 0.29s`。
- 相关回归命令：`uv run pytest tests/test_cli.py tests/test_product_analysis.py -q`
- 退出码：`0`；结果：`67 passed in 0.61s`。

## 回归、自审与遗留 concern

- 首轮全量命令：`uv run pytest -v`；结果：`891 passed, 1 failed`。唯一失败为 `tests/test_output_role_compatibility.py::test_cli_generate_without_output_role_validates_prompt_without_provider_call`：该现代项链测试仍手工写入 review 外路径且没有审核摘要，新 I2 生产 gate 按设计拒绝。
- 夹具修复：只调整 `tests/test_output_role_compatibility.py`，改用正式 `write_review_package()` 生成 review 副本与摘要，并补齐长链策略所需的取景、展示面积、遮挡和裁切字段；未放宽生产 gate。原失败单测复跑 `1 passed`，整文件复跑 `2 passed in 0.40s`。
- I1-I4 首轮收尾曾执行 `uv run pytest -v`，收集 `892` 项并全部通过；第二轮 I1 复审新增 12 项后增至 904，第三轮新增 13 项后增至 917，第四轮复合分句与直接否定边界新增 23 项，最终总数为 940。
- 第四轮最终全量命令：`uv run pytest -v`；收集 `940` 项，退出码 `0`，结果 `940 passed in 2.66s`。
- 第四轮严格只修改 `src/jewelry_on_hand/product_fidelity.py`、`tests/test_final_necklace_important_fixes.py` 和本报告；没有改动 I2-I4、I5、HERO 角色评分策略、Minor、戒指生产逻辑、飞书并发范围或历史 `run/output` proof，没有提交或暂存。
- 遗留 concern：I5 仍未完成，真实双层真人佩戴成功图与正式 QC `pass` 仍需后续独立执行；当前 `940 passed` 证明工作树集成自动化闭环，不替代真实成图验收。全量也包含并发 HERO、戒指和飞书工作树状态，本报告只对 I1-I4 的自动化闭环负责。
