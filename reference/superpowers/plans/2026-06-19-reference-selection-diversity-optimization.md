# Reference Selection Diversity Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将上手参考图选择从“最高分前三张”改成“质量合格且互相差异明显的 Top 3”。

**Architecture:** 保留 `score_reference()` 的基础质量评分和硬过滤，把多样性选择封装在 `select_top_references()` 的排序阶段。新增小型内部 helper 计算风格簇、场景簇、姿势簇和拍摄组，并在 Top 3 选择时对重复簇降权。

**Tech Stack:** Python 3.11、pytest、现有 `jewelry_on_hand.scoring` 与 `tests/test_scoring.py`。

---

## 文件结构

- Modify: `src/jewelry_on_hand/scoring.py`
  - 保留硬过滤、基础评分、风险记录。
  - 新增 diversity rerank helper。
  - 收窄清透自然风格匹配词。
  - 调整大珠近景加分权重。
- Modify: `tests/test_scoring.py`
  - 增加同风格/同拍摄组不重复进 Top 3 的测试。
  - 增加“自然”不单独触发清透自然加分的测试。
  - 增加大珠产品仍可选入不同风格候选的测试。
- Modify: `docs/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md`
  - 修订自动参考图评分与 Top 3 输出规则，加入质量阈值内多样性选择。
- Modify: `reference/manual-workflow.md`
  - 说明 Review 包里的 Top 3 是三种参考方向，不是单纯最高分前三。

---

## Task 1: 锁定同风格/同拍摄组重复问题

**Files:**
- Modify: `tests/test_scoring.py`
- Modify: `src/jewelry_on_hand/scoring.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_scoring.py` 增加测试：构造 3 张同一暗调拍摄组高分图和 2 张略低分但不同风格图，期望 Top 3 不全是同组图。

```python
def test_select_top_references_diversifies_same_score_shoot_group():
    rows = [
        row(30, file_name="1（30）.png", style_category="暗调高级/黑衣近景"),
        row(31, file_name="1（31）.png", style_category="暗调高级/黑衣近景"),
        row(32, file_name="1（32）.png", style_category="暗调高级/黑衣近景"),
        row(
            101,
            file_name="outdoor-101.jpg",
            style_category="户外自然光",
            scene_keywords="户外 阳光 手腕清晰",
            recommended_usage="手腕中景",
            notes="手腕/前臂露出面积足，无裁切",
        ),
        row(
            102,
            file_name="mirror-102.jpg",
            style_category="对镜生活感",
            scene_keywords="对镜 室内 自然光",
            recommended_usage="对镜手腕构图",
            notes="手腕露出完整，无裁切",
        ),
    ]

    selected, _ = select_top_references(product(), rows)

    assert [item.row.index for item in selected] == [30, 101, 102]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_scoring.py::test_select_top_references_diversifies_same_score_shoot_group -q
```

Expected: FAIL because current selection returns `[30, 31, 32]`.

- [ ] **Step 3: Write minimal implementation**

Update `select_top_references()` so it sorts by base score, then calls a helper that selects Top 3 with diversity penalties for repeated `style_cluster` and `shoot_group`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
pytest tests/test_scoring.py::test_select_top_references_diversifies_same_score_shoot_group -q
```

Expected: PASS.

---

## Task 2: 收窄“自然”风格匹配

**Files:**
- Modify: `tests/test_scoring.py`
- Modify: `src/jewelry_on_hand/scoring.py`

- [ ] **Step 1: Write the failing test**

```python
def test_clear_natural_match_requires_specific_visual_signal():
    generic = score_reference(
        product(style_mood="自然真实的小红书上手试戴图"),
        row(201, style_category="清透奶油系/白衬衫", scene_keywords="室内自然光 白衣"),
    )
    specific = score_reference(
        product(style_mood="清透浅色自然光"),
        row(202, style_category="清透奶油系/白衬衫", scene_keywords="室内自然光 白衣"),
    )

    assert not any("清晰自然风格匹配" in reason for reason in generic.reason)
    assert any("清晰自然风格匹配" in reason for reason in specific.reason)
    assert specific.score == generic.score + 15
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_scoring.py::test_clear_natural_match_requires_specific_visual_signal -q
```

Expected: FAIL because current code lets “自然” trigger the match.

- [ ] **Step 3: Write minimal implementation**

Change the clear/natural match terms from `("清晰", "自然", "自然光", "清透")` to a stricter set like `("清透", "自然光", "白衬衫", "浅色", "奶油", "柔和生活感")`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
pytest tests/test_scoring.py::test_clear_natural_match_requires_specific_visual_signal -q
```

Expected: PASS.

---

## Task 3: 保持候选 rank 和兼容性

**Files:**
- Modify: `tests/test_scoring.py`
- Modify: `src/jewelry_on_hand/scoring.py`

- [ ] **Step 1: Write the failing or regression test**

Add a test that selected ranks remain `[1, 2, 3]`, candidates ranks remain continuous, and candidates remain sorted by base score.

- [ ] **Step 2: Run test**

Run:

```powershell
pytest tests/test_scoring.py -q
```

Expected before final implementation may fail if rank reassignment is incomplete.

- [ ] **Step 3: Finish implementation**

Ensure `_rerank()` is still applied after candidate sorting and after selected diversity order. `reference_candidates.json` should still represent base-score candidates; `selected_references.json` should represent diversity-selected Top 3.

- [ ] **Step 4: Run all scoring tests**

Run:

```powershell
pytest tests/test_scoring.py -q
```

Expected: PASS.

---

## Task 4: Update docs and run focused suite

**Files:**
- Modify: `docs/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md`
- Modify: `reference/manual-workflow.md`

- [ ] **Step 1: Update docs**

Document that Top 3 uses “quality threshold + diversity rerank” and that same style/shoot group should not fill all slots.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
pytest tests/test_scoring.py tests/test_review_package.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Search docs for old wording**

Run:

```powershell
rg -n "最高分前三|直接取前三|Top 3.*最高分" docs reference -g "*.md"
```

Expected: no contradictory wording unless it explicitly explains the old behavior being replaced.

---

## 自检结果

- Spec coverage: covers diversity rerank, stricter style match, compatibility, docs.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: all referenced functions already exist or are internal helpers to add in `scoring.py`.
