# 跑环约束增强与 7 个商品纠错重跑实施计划

> **供 agentic worker 使用：** 必须按任务逐项执行；本会话使用 `superpowers:executing-plans`，每个步骤以复选框跟踪。

**目标：** 增强通用跑环约束，重新生成并严格验收 11 张错误上手图，加 Yuan Studio 水印后替换飞书中 7 个商品的错误附件。

**架构：** 生产代码只增强 `跑环` 的通用结构化规则，不增加 PN 特例。批次特定修订和生成任务保存在新的 `output/021-20260717-correction-20260713/`，以旧批次的产品图、手模参考图和提示词为输入，生成独立可审计产物；只有通过严格 QC 的结果进入水印和飞书附件替换。

**技术栈：** Python 3.11+、pytest、AIReiter `gpt_image_2` 异步 API、Pillow 水印脚本、`lark-cli base`。

## 全局约束

- 所有输出、注释和文档使用中文；所有参考文档放在 `reference/`，所有测试过程和临时产物放在 `output/`。
- 保留当前脏工作区的用户改动，不回退、不覆盖、不提交无关修改。
- 生产代码必须测试先行，先看到预期失败，再写最小实现。
- 不把“小珠结”“珠结”“金属连接环”加入跑环别名。
- 不覆盖旧批次 `output/021-20260717-multiview-20260711-021536/` 的任何产物。
- 重跑范围固定为 11 张：QY002 1/2、QY004 1/2、QY013 1/2、QY020 1/2、QY022 1、QY024 2、QY025 1。
- 沿用旧图固定为 3 张：QY022 2、QY024 1、QY025 2。
- 新图只有完整 QC 通过后才允许水印和上传；飞书最终必须为 7 条记录、每条 2 张、总计 14 张。

---

### 任务 1：以 TDD 增强跑环通用约束

**文件：**
- 修改：`tests/test_product_analysis.py`
- 修改：`tests/test_prompt_builder.py`
- 修改：`src/jewelry_on_hand/product_fidelity.py`

**接口：**
- 输入：`build_product_fidelity_constraints(product: ProductAnalysis, ...)`
- 输出：`normalized_keyword == "跑环"` 的 `MustKeepConstraint`
- 下游：`build_generation_prompt(...)` 通过现有 `_fidelity_section()` 原样渲染该约束。

- [ ] **步骤 1：新增跑环结构失败测试**

在 `tests/test_product_analysis.py` 新增：

```python
def test_running_ring_constraint_is_a_closed_independent_small_bead_loop():
    analysis = ProductAnalysis.from_dict(
        _analysis_data("手链/手串")
        | {
            "visible_appearance": "黄色主珠旁套接一个红色小珠跑环。",
            "special_requirements": ["保持跑环套接黄色主珠的关系"],
        }
    )

    constraints = build_product_fidelity_constraints(analysis)
    running_ring = next(
        item for item in constraints.must_keep if item.normalized_keyword == "跑环"
    )

    assert "多颗小珠" in running_ring.visual_shape
    assert "独立闭合小环" in running_ring.visual_shape
    assert "环绕、套接或连接对象" in running_ring.relationship
    assert "并入手串主串" in running_ring.forbid
    assert "绳结或普通珠结" in running_ring.forbid
    assert "单个金属环" in running_ring.forbid
    assert "流苏或链坠" in running_ring.forbid
    assert "多颗小珠" in running_ring.qc_question
    assert "连接对象" in running_ring.qc_question
```

- [ ] **步骤 2：新增防过拟合失败测试**

```python
@pytest.mark.parametrize("text", ["红色小珠结", "普通珠结", "金色连接环"])
def test_knot_or_metal_ring_text_does_not_trigger_running_ring(text):
    analysis = ProductAnalysis.from_dict(
        _analysis_data("手链/手串") | {"visible_appearance": text}
    )

    constraints = build_product_fidelity_constraints(analysis)

    assert "跑环" not in constraints.detected_keywords
```

- [ ] **步骤 3：新增 Prompt 渲染失败测试**

在 `tests/test_prompt_builder.py` 新增一个 `ProductFidelityConstraints`，其跑环项使用新结构语义，然后断言生成 Prompt 包含：

```python
assert "多颗小珠串成的独立闭合小环" in prompt
assert "保持产品图中的环绕、套接或连接对象" in prompt
assert "并入手串主串" in prompt
assert _prompt_contract_errors(tmp_path, prompt) == []
```

- [ ] **步骤 4：运行定向测试并确认按预期失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_product_analysis.py::test_running_ring_constraint_is_a_closed_independent_small_bead_loop tests/test_product_analysis.py::test_knot_or_metal_ring_text_does_not_trigger_running_ring tests/test_prompt_builder.py -q
```

预期：第一项因旧规则只有“环状连接结构或活动环”而失败；防过拟合测试通过；Prompt 新断言失败。

- [ ] **步骤 5：写最小生产实现**

将 `src/jewelry_on_hand/product_fidelity.py` 中 `normalized="跑环"` 的规则改为：

```python
_KeywordRule(
    normalized="跑环",
    aliases=("跑环",),
    visual_shape=(
        "由多颗小珠串成的独立闭合小环，保持可见环形轮廓和活动结构；"
        "不是绳结、流苏、单个金属环或主串的一部分"
    ),
    relationship=(
        "保持产品图中的环绕、套接或连接对象，以及与主珠、连接件或相邻结构的关系；"
        "不得并入手串主串或改接到其他对象"
    ),
    forbid=(
        "改成绳结或普通珠结",
        "改成流苏或链坠",
        "改成单个金属环、金属片或连接扣",
        "改成普通圆珠",
        "并入手串主串",
        "改变环绕、套接或连接对象",
    ),
    qc_question=(
        "跑环是否仍由多颗小珠形成独立闭合小环，保持原来的环绕、套接或连接对象，"
        "且没有变成珠结、流苏、金属单环、链坠、普通圆珠或主串的一部分"
    ),
),
```

- [ ] **步骤 6：运行定向测试和完整测试集**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_product_analysis.py tests/test_prompt_builder.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

预期：全部通过，输出无新增警告或错误。

- [ ] **步骤 7：只提交本任务的代码和测试 hunk**

不得把这些文件中原有的用户改动一并提交。先保存修改前快照并生成仅包含本任务增量的 patch，再将该 patch应用到索引；确认 `git diff --cached` 只有跑环规则和对应测试后提交：

```powershell
git commit -m "fix: 细化跑环产品保真约束"
```

---

### 任务 2：创建独立纠错批次和 11 个生成任务

**文件：**
- 创建：`output/021-20260717-correction-20260713/prepare_correction_batch.py`
- 创建：`output/021-20260717-correction-20260713/correction-manifest.json`
- 创建：`output/021-20260717-correction-20260713/jobs/<PN>-rank<N>/...`

**接口：**
- 输入：旧批次 7 个 run 的产品分析、约束、提示词、手模参考图和产品图。
- 输出：11 个完全独立的 job 目录，每个包含 `analysis/`、`input/`、`prompt.txt`、`hand-reference.*`、`generation-metadata.json`。

- [ ] **步骤 1：用 `apply_patch` 创建批次准备脚本**

脚本必须定义固定任务清单：

```python
TARGETS = {
    "QY002": (1, 2),
    "QY004": (1, 2),
    "QY013": (1, 2),
    "QY020": (1, 2),
    "QY022": (1,),
    "QY024": (2,),
    "QY025": (1,),
}
```

脚本复制而不是移动旧文件；QY002 将 `visible_appearance` 和 `special_requirements` 中的“红色小珠结”改为“由多颗红色小珠串成、套接在原连接位置的独立闭合跑环”，重新调用 `build_product_fidelity_constraints()` 并将状态设为 `corrected`。其他 6 个商品在复制的 canonical 文件中加入 SPEC 第 5 节对应的 `must_keep`，同时保留已有约束和 `must_not_change`。

每个 job 从旧 `generation/<rank>/prompt.txt` 复制基础 Prompt，再替换产品外观、特殊要求和“本产品必须保留的关键识别点”段，确保完整包含本商品定向约束。双视角 job 按旧 `generation-metadata.json.product_view_order` 复制并保持内部图 2/3 顺序。

- [ ] **步骤 2：运行准备脚本**

```powershell
.\.venv\Scripts\python.exe .\output\021-20260717-correction-20260713\prepare_correction_batch.py
```

预期：输出 `prepared=11 failed=0`。

- [ ] **步骤 3：机械校验批次清单**

校验：11 个 job、11 个 Prompt、11 个手模参考、QY002 两个 job 均包含“独立闭合跑环”，其他 6 个商品均包含对应定向约束；旧批次文件哈希在运行前后不变。

- [ ] **步骤 4：运行 Prompt contract**

对 11 个 `prompt.txt` 逐一执行：

```powershell
.\.venv\Scripts\python.exe .\skills\jewelry-on-hand-workflow\scripts\validate_prompt_contract.py <prompt-path>
```

预期：11 个全部通过。

---

### 任务 3：提交并轮询 11 个 AIReiter 生成任务

**文件：**
- 写入：`output/021-20260717-correction-20260713/jobs/*/submit.json`
- 写入：`output/021-20260717-correction-20260713/jobs/*/result.json`
- 写入：`output/021-20260717-correction-20260713/jobs/*/result.png`
- 写入：`output/021-20260717-correction-20260713/generation-progress.json`

**接口：**
- 输入：每个 job 的 Prompt、手模参考图和 1 至 2 张产品图。
- 输出：AIReiter `gpt_image_2` 的异步任务结果和本地原图。

- [ ] **步骤 1：逐 job 提交任务并即时记录 `out_task_id`**

使用：

```powershell
.\.venv\Scripts\python.exe .\skills\aireiter-image-generation\scripts\aireiter_image_helper.py submit --model gpt_image_2 --prompt-file <prompt.txt> --aspect-ratio 3:4 --resolution 2K --image <hand-reference> --image <product-view-1> [--image <product-view-2>] --task-id <unique-id>
```

若项目 helper 的参数名不同，以 `--help` 的真实参数为准；不得在没有确认提交失败时重复提交。

- [ ] **步骤 2：轮询每个已提交任务**

```powershell
.\.venv\Scripts\python.exe .\skills\aireiter-image-generation\scripts\aireiter_image_helper.py wait --task-id <out_task_id>
```

预期：11 个任务均得到 `completed`，每个结果包含可下载 URL。失败响应按 AIReiter skill 规则处理；积分不足或无有效输出时进入 `imagegen` 单次兜底。

- [ ] **步骤 3：下载并校验本地结果**

每个 `result.png` 必须存在、非空、可由 Pillow 打开，尺寸不小于 1K；写入 `generation-progress.json`，状态只能是 `generated` 或含原始错误的 `failed`。

---

### 任务 4：逐张严格 QC 并只重跑失败任务

**文件：**
- 创建：`output/021-20260717-correction-20260713/qc-contact-sheets/*.jpg`
- 创建：`output/021-20260717-correction-20260713/jobs/*/qc.json`
- 创建：`output/021-20260717-correction-20260713/qc-evaluation.md`

**接口：**
- 输入：产品源图、11 张新图及各自 canonical 约束。
- 输出：逐项 QC 和最终可交付清单。

- [ ] **步骤 1：生成源图/结果对照拼图并逐张查看原图**

每个商品的对照图至少包含全部产品视角、旧错误图和新结果；跑环、小配件、爱心珠和珠序需要回看原始分辨率，不得只看缩略拼图。

- [ ] **步骤 2：填写完整 QC**

每张新图必须检查通用清单和本商品定向约束。QY002 跑环必须验证多颗小珠、独立闭合、原锚点和禁止换型。任一核心结构错误使用 `must_keep_failed`、`core_structure_missing` 和 `reject`。

- [ ] **步骤 3：只重跑未通过 job**

首次失败仍用 `gpt_image_2`；同一 job 累计超过 1 次非 `pass` 后才用 `nano_banana_v2`。每次重跑创建新的 `attempt-NN/`，不覆盖失败结果。

- [ ] **步骤 4：确认最终 11/11 通过**

运行批次校验脚本并确认：11 个最终结果都有 `qc.json`、`status=pass`、完整 `fidelity_checks` 和 `checklist_checks`。未达到 11/11 时不得进入任务 5。

---

### 任务 5：为 11 张通过图添加 Yuan Studio 水印

**文件：**
- 创建：`output/021-20260717-correction-20260713/watermark-queue.csv`
- 创建：`output/021-20260717-correction-20260713/watermarked/*.png`
- 创建：`output/021-20260717-correction-20260713/watermark-verification.md`

**接口：**
- 输入：11 张最终 `pass` 结果和对应 PN。
- 输出：11 张带 `YUAN STUDIO`、`PN QYxxx` 的图片。

- [ ] **步骤 1：生成 11 行水印队列**

CSV 字段固定为 `image_path,product_id,output_path`，输出名固定为 `<PN>-rank<N>-corrected.png`。

- [ ] **步骤 2：运行水印脚本**

```powershell
<Pillow-Python> C:\Users\Administrator\.codex\skills\yuanyuan-ruyi-watermark\scripts\watermark_images.py --queue .\output\021-20260717-correction-20260713\watermark-queue.csv --output-dir .\output\021-20260717-correction-20260713\watermarked
```

预期：`success=11 failed=0 total=11`。

- [ ] **步骤 3：视觉抽查和机械校验**

至少查看 QY002、QY013、QY020、QY025 及一个复杂珠序样本；确认徽章未遮挡主体，文字严格为 `YUAN STUDIO` 和 `PN QYxxx`。机械校验 11 个文件均可打开、非空、尺寸与源图一致。

---

### 任务 6：安全替换飞书 7 条记录的错误附件

**文件：**
- 创建：`output/021-20260717-correction-20260713/feishu-before.json`
- 创建：`output/021-20260717-correction-20260713/upload-map.json`
- 创建：`output/021-20260717-correction-20260713/upload-results.json`

**接口：**
- 输入：Base `D4Vjbv19WaVVTwsGKdJcsnt5neg`、表 `tblEtBnKFwkgTp22`、字段 `fldbVkuz9O`、11 张新水印图和 3 张保留附件。
- 输出：7 条记录各 2 张正确附件。

- [ ] **步骤 1：解析 Base URL 并回读真实字段和 7 条记录**

```powershell
lark-cli base +url-resolve --url "https://i1zdcv06pi.feishu.cn/base/D4Vjbv19WaVVTwsGKdJcsnt5neg?from=from_copylink" --as user
lark-cli base +field-list --base-token D4Vjbv19WaVVTwsGKdJcsnt5neg --table-id tblEtBnKFwkgTp22 --as user
```

使用 `+record-search` 定位 7 个 PN，保存记录 ID、附件 token、文件名和当前数量。任一记录不是恰好 2 张时停止该记录写入。

- [ ] **步骤 2：读取附件命令帮助并锁定安全语义**

```powershell
lark-cli base +record-upload-attachment --help
lark-cli base +record-remove-attachment --help
```

优先使用原子替换参数；若 CLI 只支持追加/删除，则对每条记录执行“上传新附件 → 回读确认新 token → 删除对应旧错误附件”。不得删除 QY022 rank2、QY024 rank1、QY025 rank2。

- [ ] **步骤 3：串行处理 7 条记录**

每条记录处理完立即回读并确认最终 2 张，再处理下一条。连续写同一表不得并发；遇到 `1254291` 短暂等待后重试。

- [ ] **步骤 4：保存完整上传证据**

`upload-results.json` 必须逐 PN 记录：记录 ID、保留 token、删除 token、新 token、新文件名、命令状态和回读数量。

---

### 任务 7：完成前交叉验证和报告

**文件：**
- 创建：`output/021-20260717-correction-20260713/upload-verification.md`
- 创建：`output/021-20260717-correction-20260713/final-verification.json`

**接口：**
- 输入：代码测试、11 个生成 job、QC、水印和飞书回读结果。
- 输出：可追溯的最终完成证据。

- [ ] **步骤 1：重新运行完整测试集**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

预期：0 失败。

- [ ] **步骤 2：验证本地产物计数**

确认 11 个最终 `result.png`、11 个 `status=pass` QC、11 张水印图、0 个空文件、PN 映射错误为 0。

- [ ] **步骤 3：重新回读飞书 7 条记录**

确认每条 2 张、合计 14 张；11 个新附件存在，3 个指定旧附件仍存在；其他 24 条记录的附件 token 与写入前快照一致。

- [ ] **步骤 4：写最终验证报告**

报告必须区分代码测试、真实生成、人工视觉 QC、水印、飞书写入和回读证据；不得用“命令成功”代替附件内容与数量验证。

- [ ] **步骤 5：检查 git 状态和改动边界**

确认只提交了跑环生产规则、对应测试、设计和实施计划；`output/` 产物保留在工作区但不纳入代码提交；用户原有脏改动保持不变。
