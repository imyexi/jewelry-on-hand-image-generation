# Product Fidelity Constraints Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SPEC 修订中的产品保真约束、关键识别点 review、生成前 gate、prompt 消费和 QC 逐项验收完整接入现有本地工作流。

**Architecture:** 新增一个独立的产品保真约束模型与构建模块，作为 `product_analysis` 与 review/generate/QC 之间的结构化中间产物。现有 `review_decision`、`prompt_builder`、`qc`、`cli` 只通过该模型读取、校验和渲染约束，避免把单个 SKU 修复逻辑写进 prompt 临时字符串。

**Tech Stack:** Python 3.11+、dataclasses、pytest、现有 `RunPaths` JSON 读写工具、现有 CLI 子命令。

---

## 文件结构

- Modify: `src/jewelry_on_hand/models.py`
  - 增加 `MustKeepConstraint`、`ProductFidelityConstraints`、`FidelityCheck` 模型。
  - 扩展 `ReviewDecision`，支持 `fidelity_confirmed`、`fidelity_notes`、`fidelity_constraints_path`。
  - 扩展 `QcResult`，支持 `fidelity_checks` 并阻止关键识别点失败时标记 `pass`。
- Create: `src/jewelry_on_hand/product_fidelity.py`
  - 内置关键结构词典。
  - 从 `ProductAnalysis.visible_appearance` 与 `special_requirements` 生成默认 `product_fidelity_constraints.json`。
  - 提供 `load_product_fidelity_constraints()` 与 `require_confirmed_constraints()`。
- Modify: `src/jewelry_on_hand/product_analysis.py`
  - 在分析 prompt 中明确要求关键结构描述。
  - 导出保真约束构建函数供 CLI 调用。
- Modify: `src/jewelry_on_hand/review_package.py`
  - 生成 review 包时读取并展示 `analysis/product_fidelity_constraints.json`。
- Modify: `src/jewelry_on_hand/review_decision.py`
  - 写入和读取决策时保留 fidelity 字段。
  - 生成前同时校验决策确认和约束文件状态。
- Modify: `src/jewelry_on_hand/prompt_builder.py`
  - `build_prompt()` 增加 `fidelity_constraints` 参数并渲染 `must_keep` / `must_not_change`。
- Modify: `src/jewelry_on_hand/generation.py`
  - 继续复用 `require_generation_decision()`，让生成入口自动获得保真 gate。
- Modify: `src/jewelry_on_hand/qc.py`
  - 写入 `qc.json` 时支持 `fidelity_checks`。
- Modify: `src/jewelry_on_hand/cli.py`
  - `prepare-review` 写入 `analysis/product_fidelity_constraints.json`。
  - `record-decision` 支持 `--fidelity-confirmed`、`--fidelity-notes`、`--fidelity-constraints-path`。
  - `generate` 读取约束并传给 prompt builder。
  - `qc` 支持从 JSON 文件传入 `fidelity_checks`。
- Modify: `reference/product-fidelity-constraints-schema.md`
- Modify: `reference/review-decision-schema.md`
- Modify: `reference/prompt-template.md`
- Modify: `reference/qc-checklist.md`
- Modify: `reference/manual-workflow.md`

---

### Task 1: 产品保真约束模型

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add tests that express the desired API:

```python
def test_product_fidelity_constraints_accepts_pending_must_keep_and_exports_detached_dict():
    constraints = ProductFidelityConstraints.from_dict(
        {
            "schema_version": 1,
            "source": {
                "product_id": "JH016",
                "product_image": "input/product-on-hand.jpg",
                "product_analysis": "analysis/product_analysis.json",
            },
            "detected_keywords": ["随形"],
            "must_keep": [
                {
                    "name": "白水晶随形",
                    "source_text": "白水晶随形",
                    "normalized_keyword": "随形",
                    "location": "主珠右侧",
                    "visual_shape": "透明不规则随形，非圆珠",
                    "relationship": "位于两颗圆珠之间",
                    "forbid": ["改成圆珠", "改成椭圆珠"],
                    "qc_question": "白水晶随形是否仍是不规则透明异形珠",
                }
            ],
            "must_not_change": ["珠子排列顺序"],
            "needs_user_review": True,
            "detail_crop_recommended": True,
            "review_status": "pending",
        }
    )

    exported = constraints.to_dict()
    exported["must_keep"][0]["forbid"].append("后续修改")

    assert constraints.detected_keywords == ("随形",)
    assert constraints.must_keep[0].normalized_keyword == "随形"
    assert constraints.must_keep[0].forbid == ("改成圆珠", "改成椭圆珠")
    assert constraints.to_dict()["must_keep"][0]["forbid"] == ["改成圆珠", "改成椭圆珠"]
```

Add validation tests:

```python
@pytest.mark.parametrize("status", ["pending", "confirmed", "corrected", "not_applicable"])
def test_product_fidelity_constraints_accepts_known_review_status(status):
    data = _constraints_data(review_status=status)
    if status == "not_applicable":
        data["must_keep"] = []
    assert ProductFidelityConstraints.from_dict(data).review_status == status


def test_product_fidelity_constraints_rejects_missing_required_must_keep_fields():
    data = _constraints_data()
    data["must_keep"][0].pop("qc_question")
    with pytest.raises(ValueError, match="qc_question"):
        ProductFidelityConstraints.from_dict(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\珠宝上手图片生成\src'
$env:PYTHONUTF8='1'
$PY='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $PY -m pytest tests/test_models.py -q
```

Expected: FAIL because `ProductFidelityConstraints` is not defined.

- [ ] **Step 3: Write minimal implementation**

Implement dataclasses with `from_dict()` / `to_dict()` and validation for schema version, required strings, string lists, booleans, and review status.

- [ ] **Step 4: Run test to verify it passes**

Run the same test command. Expected: PASS for `tests/test_models.py`.

---

### Task 2: 默认约束生成与文件写入

**Files:**
- Create: `src/jewelry_on_hand/product_fidelity.py`
- Modify: `src/jewelry_on_hand/product_analysis.py`
- Modify: `src/jewelry_on_hand/cli.py`
- Test: `tests/test_product_analysis.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add unit tests:

```python
def test_build_default_fidelity_constraints_detects_keyword_from_visible_appearance():
    analysis = ProductAnalysis.from_dict(
        _analysis_data("手链/手串")
        | {
            "visible_appearance": "主珠右侧有一颗透明白色不规则随形，旁边连接海蓝宝跑环。",
            "special_requirements": ["保留白水晶随形", "不要丢失跑环"],
        }
    )

    constraints = build_product_fidelity_constraints(
        analysis,
        product_id="JH016",
        product_image="input/product-on-hand.jpg",
    )

    assert constraints.review_status == "pending"
    assert constraints.needs_user_review is True
    assert constraints.detail_crop_recommended is True
    assert constraints.detected_keywords == ("随形", "跑环")
    assert [item.normalized_keyword for item in constraints.must_keep] == ["随形", "跑环"]
    assert "珠子排列顺序" in constraints.must_not_change


def test_build_default_fidelity_constraints_marks_not_applicable_without_keyword():
    analysis = ProductAnalysis.from_dict(_analysis_data("手链/手串"))

    constraints = build_product_fidelity_constraints(analysis)

    assert constraints.must_keep == ()
    assert constraints.review_status == "not_applicable"
    assert constraints.needs_user_review is False
```

Add CLI integration test:

```python
def test_prepare_review_cli_writes_product_fidelity_constraints(tmp_path):
    # Reuse existing catalog/product/analysis helpers.
    assert main([... "prepare-review", ...]) == 0
    data = read_json(run_root / "analysis" / "product_fidelity_constraints.json")
    assert data["schema_version"] == 1
    assert "must_keep" in data
    assert data["review_status"] in {"pending", "not_applicable"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
& $PY -m pytest tests/test_product_analysis.py tests/test_cli.py -q
```

Expected: FAIL because `product_fidelity.py` and CLI write path do not exist.

- [ ] **Step 3: Implement minimal code**

Implement keyword dictionary for `随形/随行`、`跑环`、`双尖`、`回纹`、`貔貅`、`桶珠`、`雕刻/雕花`、`吊坠/流苏/链坠` and a deterministic builder that uses the source text as context and outputs conservative location/shape/relationship defaults.

- [ ] **Step 4: Run tests to verify they pass**

Run the same command. Expected: PASS for the changed test files.

---

### Task 3: Review Gate 确认字段与约束状态校验

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/review_decision.py`
- Modify: `src/jewelry_on_hand/cli.py`
- Test: `tests/test_models.py`
- Test: `tests/test_review_decision.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add tests:

```python
def test_review_decision_requires_fidelity_confirmed_for_generation_actions():
    with pytest.raises(ValueError, match="fidelity_confirmed"):
        ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": [1]})

    decision = ReviewDecision.from_dict(
        {"action": "generate_selected", "selected_ranks": [1], "fidelity_confirmed": True}
    )
    assert decision.fidelity_confirmed is True
    assert decision.fidelity_constraints_path == "analysis/product_fidelity_constraints.json"


def test_require_generation_decision_rejects_pending_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="pending"))
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True})

    with pytest.raises(ReviewGateError, match="pending"):
        require_generation_decision(paths)
```

Add confirmed/not applicable happy path:

```python
def test_require_generation_decision_allows_confirmed_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="confirmed"))
    write_review_decision(paths, {"action": "generate_rank_1", "fidelity_confirmed": True})
    assert require_generation_decision(paths).selected_ranks == [1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
& $PY -m pytest tests/test_models.py tests/test_review_decision.py tests/test_cli.py -q
```

Expected: FAIL because `fidelity_confirmed` and constraints gate are not implemented.

- [ ] **Step 3: Implement minimal code**

Add fields to `ReviewDecision`; persist them in `_decision_to_dict()`; in `require_generation_decision()` verify `fidelity_confirmed is True`, resolve default constraints path relative to run root, load constraints, and require `confirmed/corrected/not_applicable`.

- [ ] **Step 4: Run tests to verify they pass**

Run the same command. Expected: PASS.

---

### Task 4: Review 包展示关键识别点

**Files:**
- Modify: `src/jewelry_on_hand/review_package.py`
- Test: `tests/test_review_package.py`

- [ ] **Step 1: Write the failing test**

Add tests:

```python
def test_write_review_package_displays_product_fidelity_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="pending"))
    selected = [make_scored(tmp_path, 1)]

    html = write_review_package(paths, product, selected, selected).read_text(encoding="utf-8")

    assert "产品保真约束" in html
    assert "关键识别点" in html
    assert "白水晶随形" in html
    assert "改成圆珠" in html
    assert "待确认" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
& $PY -m pytest tests/test_review_package.py -q
```

Expected: FAIL because review HTML does not render constraints.

- [ ] **Step 3: Implement minimal code**

Load `analysis/product_fidelity_constraints.json` if present; render a section with review status, detected keywords, `must_keep`, `must_not_change`, and detail crop recommendation. Escape all text.

- [ ] **Step 4: Run test to verify it passes**

Run the same command. Expected: PASS.

---

### Task 5: Prompt Builder 消费约束

**Files:**
- Modify: `src/jewelry_on_hand/prompt_builder.py`
- Modify: `src/jewelry_on_hand/cli.py`
- Test: `tests/test_prompt_builder.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add tests:

```python
def test_prompt_includes_product_fidelity_constraints_sections():
    constraints = ProductFidelityConstraints.from_dict(_constraints_data(review_status="confirmed"))

    prompt = build_prompt(_product(), _scored(_row()), constraints)

    assert "本产品必须保留的关键识别点" in prompt
    assert "白水晶随形" in prompt
    assert "主珠右侧" in prompt
    assert "改成圆珠" in prompt
    assert "产品整体禁止变化" in prompt
    assert "珠子排列顺序" in prompt


def test_prompt_includes_no_extra_keypoint_text_when_must_keep_empty():
    constraints = ProductFidelityConstraints.from_dict(_constraints_data(review_status="not_applicable", must_keep=[]))

    prompt = build_prompt(_product(), _scored(_row()), constraints)

    assert "无额外局部关键识别点" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
& $PY -m pytest tests/test_prompt_builder.py tests/test_cli.py -q
```

Expected: FAIL because `build_prompt()` signature and CLI call do not pass constraints.

- [ ] **Step 3: Implement minimal code**

Make `build_prompt(product, reference, fidelity_constraints=None)` backward compatible for existing tests, but CLI must always pass loaded constraints. Render must_keep and must_not_change immediately after product info or inside product fidelity section.

- [ ] **Step 4: Run tests to verify they pass**

Run the same command. Expected: PASS.

---

### Task 6: QC 逐项验收关键识别点

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/qc.py`
- Modify: `src/jewelry_on_hand/cli.py`
- Test: `tests/test_models.py`
- Test: `tests/test_qc.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add tests:

```python
def test_qc_result_rejects_pass_when_fidelity_check_failed():
    with pytest.raises(ValueError, match="must_keep"):
        QcResult(
            status="pass",
            passed=["构图正确"],
            failed=[],
            notes="",
            fidelity_checks=[{"name": "白水晶随形", "question": "是否保留", "result": "fail", "notes": "变圆珠"}],
        )


def test_write_qc_result_writes_fidelity_checks(tmp_path):
    path = write_qc_result(
        tmp_path,
        "rerun",
        ["构图正确"],
        ["关键识别点失败"],
        "需要重跑",
        fidelity_checks=[{"name": "白水晶随形", "question": "是否保留", "result": "fail", "notes": "变圆珠"}],
    )

    data = read_json(path)
    assert data["fidelity_checks"][0]["result"] == "fail"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
& $PY -m pytest tests/test_models.py tests/test_qc.py tests/test_cli.py -q
```

Expected: FAIL because QC does not support `fidelity_checks`.

- [ ] **Step 3: Implement minimal code**

Add `FidelityCheck` model with result values `pass/rerun/fail` and enforce `QcResult.status == "pass"` only if all checks pass. Add CLI `--fidelity-checks-json` accepting a JSON list.

- [ ] **Step 4: Run tests to verify they pass**

Run the same command. Expected: PASS.

---

### Task 7: 文档修订与全量验证

**Files:**
- Modify: `reference/product-fidelity-constraints-schema.md`
- Modify: `reference/review-decision-schema.md`
- Modify: `reference/prompt-template.md`
- Modify: `reference/qc-checklist.md`
- Modify: `reference/manual-workflow.md`

- [ ] **Step 1: Revise reference docs**

Rewrite each affected section so it matches the implemented behavior:

- `product_fidelity_constraints.json` is always generated during prepare-review.
- `review_decision.json` must carry `fidelity_confirmed: true` for generation actions.
- `review_status` must be `confirmed/corrected/not_applicable` before generation.
- Prompt must include `本产品必须保留的关键识别点` and `产品整体禁止变化`.
- QC must include `fidelity_checks`; a failed must_keep check cannot be `pass`.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
& $PY -m pytest tests/test_models.py tests/test_product_analysis.py tests/test_review_decision.py tests/test_review_package.py tests/test_prompt_builder.py tests/test_qc.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full regression**

Run:

```powershell
& $PY -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Inspect git diff**

Run:

```powershell
git diff -- src tests reference docs/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md
```

Expected: diff only contains planned code/tests/reference docs changes and no unrelated asset cleanup.
