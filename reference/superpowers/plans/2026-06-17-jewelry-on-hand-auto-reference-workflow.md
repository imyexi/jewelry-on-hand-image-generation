# 珠宝上手图自动参考选择与生成工作流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 建立“1 张产品上手原图 → 自动推荐 Top 3 上手参考图 → 用户 review → AIReiter nano_banana_v2 生成 → 人工 QC”的第一版可追踪工作流。

**Architecture:** 用 Python CLI 串联本地文件工作流。Codex/视觉执行者在系统内部把用户图分析成 analysis/product_analysis.json，代码负责校验、选图、review、prompt、生成 gate、AIReiter 调用与 QC 记录；用户仍只提交 1 张产品上手原图。正式产物写入 outputs/auto_reference_runs/<run-id>/，测试过程日志写入 output/test-runs/。

**Tech Stack:** Python 3.11、pytest、openpyxl、dataclasses/json/pathlib/subprocess/html、现有 skills/aireiter-image-generation/scripts/aireiter_image_helper.py、本地静态 HTML。

---

## 范围检查

- 覆盖产品分析 JSON、分类表读取、硬过滤、评分、Top 3 review、review gate、固定 prompt、AIReiter 调用、输出目录和人工 QC。
- 第一版不做完整 Web 工作台、不做自动质量评分、不做飞书回填，不扩展戒指、项链、耳饰、白底图工作流。
- 产品图分析不新增独立视觉 API；执行时由系统内部视觉分析产出 JSON，代码提供提示词与 schema 校验，非手串/手链直接停止。

## 文件结构

- Create: pyproject.toml - 包配置、pytest 配置、CLI 入口。
- Create: src/jewelry_on_hand/__init__.py - 包版本。
- Create: src/jewelry_on_hand/models.py - ProductDimensions、ProductAnalysis、ReferenceRow、ScoredReference、ReviewDecision、QcResult。
- Create: src/jewelry_on_hand/run_paths.py - run-id、目录、输入图复制、JSON 读写。
- Create: src/jewelry_on_hand/product_analysis.py - 分析提示词、分析 JSON 加载、品类 gate。
- Create: src/jewelry_on_hand/reference_catalog.py - 读取“分类明细”并标准化字段。
- Create: src/jewelry_on_hand/scoring.py - 硬过滤、放宽、评分、Top 3。
- Create: src/jewelry_on_hand/review_package.py - reference_candidates.json、selected_references.json、review.html。
- Create: src/jewelry_on_hand/review_decision.py - review_decision.json 写入与生成前 gate。
- Create: src/jewelry_on_hand/prompt_builder.py - 固定模板变量拼装。
- Create: src/jewelry_on_hand/generation.py - AIReiter helper 封装，两图顺序固定为参考图在前、产品图在后。
- Create: src/jewelry_on_hand/qc.py - 人工 QC 写入。
- Create: src/jewelry_on_hand/cli.py - prepare-review、record-decision、generate、qc。
- Create: reference/product-analysis-schema.md、reference/review-decision-schema.md、reference/prompt-template.md、reference/qc-checklist.md。
- Create: tests/test_*.py - 每个模块对应测试；fixture 图片和 xlsx 使用临时目录生成。

---

### Task 1: 项目骨架

**Files:**
- Create: pyproject.toml
- Create: src/jewelry_on_hand/__init__.py
- Test: tests/test_package_import.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_package_import.py
import jewelry_on_hand


def test_package_exposes_version():
    assert jewelry_on_hand.__version__ == "0.1.0"
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_package_import.py -q
Expected: FAIL with ModuleNotFoundError: No module named 'jewelry_on_hand'.

- [ ] **Step 3: Write minimal implementation**

~~~toml
# pyproject.toml
[project]
name = "jewelry-on-hand"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["openpyxl>=3.1"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
jewelry-on-hand = "jewelry_on_hand.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
~~~

~~~python
# src/jewelry_on_hand/__init__.py
__version__ = "0.1.0"
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_package_import.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add pyproject.toml src/jewelry_on_hand/__init__.py tests/test_package_import.py
git commit -m "chore: scaffold jewelry on hand package"
~~~

---

### Task 2: 数据模型与校验

**Files:**
- Create: src/jewelry_on_hand/models.py
- Test: tests/test_models.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_models.py
import pytest
from jewelry_on_hand.models import ProductAnalysis, ProductDimensions, ReviewDecision


def test_product_analysis_accepts_bracelet_with_dimensions():
    analysis = ProductAnalysis.from_dict({
        "product_type": "手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "一颗深红主珠居中，两侧透明茶金色圆珠，隔圈紧贴主珠。",
        "color_family": ["深红", "茶金", "透明"],
        "style_mood": "暗调闪光",
        "composition": "手腕近景",
        "product_dimensions": {"bead_diameter_mm": 10, "dimension_source": "用户录入"},
        "needs_full_front_display": True,
        "special_requirements": ["保留主珠", "保留隔圈"]
    })
    assert analysis.product_dimensions.bead_diameter_mm == 10
    assert analysis.is_supported_product()


def test_review_decision_requires_selected_ranks():
    assert ReviewDecision.from_dict({"action": "generate_rank_1"}).selected_ranks == [1]
    with pytest.raises(ValueError, match="selected_ranks"):
        ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": []})
    with pytest.raises(ValueError, match="generate_selected"):
        ReviewDecision.from_dict({"action": "generate_selected", "selected_ranks": [1, 2]})
    with pytest.raises(ValueError, match="generate_multiple"):
        ReviewDecision.from_dict({"action": "generate_multiple", "selected_ranks": [2]})
    with pytest.raises(ValueError, match="重复"):
        ReviewDecision.from_dict({"action": "generate_multiple", "selected_ranks": [1, 1]})
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_models.py -q
Expected: FAIL with No module named 'jewelry_on_hand.models'.

- [ ] **Step 3: Write minimal implementation**

~~~python
# src/jewelry_on_hand/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

DecisionAction = Literal["generate_rank_1", "generate_selected", "generate_multiple", "rerank", "manual_reference"]

@dataclass(frozen=True)
class ProductDimensions:
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    bead_diameter_mm: float | None = None
    dimension_source: str | None = None
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProductDimensions":
        data = data or {}
        return cls(*[_positive(data.get(k)) for k in ("length_mm", "width_mm", "height_mm", "bead_diameter_mm")], _text(data.get("dimension_source")))

@dataclass(frozen=True)
class ProductAnalysis:
    product_type: str
    wear_position: str
    visible_appearance: str
    color_family: list[str]
    style_mood: str
    composition: str
    product_dimensions: ProductDimensions = field(default_factory=ProductDimensions)
    needs_full_front_display: bool = True
    special_requirements: list[str] = field(default_factory=list)
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductAnalysis":
        for key in ["product_type", "wear_position", "visible_appearance", "color_family", "style_mood", "composition"]:
            if key not in data or data[key] in (None, ""):
                raise ValueError(f"product_analysis missing field: {key}")
        return cls(str(data["product_type"]), str(data["wear_position"]), str(data["visible_appearance"]), list(data["color_family"]), str(data["style_mood"]), str(data["composition"]), ProductDimensions.from_dict(data.get("product_dimensions")), bool(data.get("needs_full_front_display", True)), list(data.get("special_requirements", [])))
    def is_supported_product(self) -> bool:
        return "手链" in self.product_type or "手串" in self.product_type

@dataclass(frozen=True)
class ReferenceRow:
    index: int; file_name: str; relative_path: str; absolute_path: Path; width: int | None; height: int | None; size_mb: float | None
    purpose_category: str; bracelet_applicability: str; default_strategy: str; style_category: str; scene_keywords: str; jewelry_type: str; recommended_usage: str; notes: str; confidence: str; file_exists: bool
    def combined_text(self) -> str:
        return " ".join([self.purpose_category, self.bracelet_applicability, self.default_strategy, self.style_category, self.scene_keywords, self.jewelry_type, self.recommended_usage, self.notes, self.confidence])

@dataclass(frozen=True)
class ScoredReference:
    row: ReferenceRow; score: int; rank: int; reason: list[str]; risk: list[str]; ignored_reference_jewelry: list[str]
    def to_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "score": self.score, "selected_reference": str(self.row.absolute_path), "reason": self.reason, "risk": self.risk, "ignored_reference_jewelry": self.ignored_reference_jewelry, "metadata": {"序号": self.row.index, "文件名": self.row.file_name, "用途分类": self.row.purpose_category, "风格分类": self.row.style_category, "场景关键词": self.row.scene_keywords, "饰品类型": self.row.jewelry_type, "推荐使用方式": self.row.recommended_usage, "备注": self.row.notes, "判断置信度": self.row.confidence}}

@dataclass(frozen=True)
class ReviewDecision:
    action: DecisionAction
    selected_ranks: list[int] = field(default_factory=list)
    manual_reference: str | None = None
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewDecision":
        action = str(data.get("action", ""))
        if action not in {"generate_rank_1", "generate_selected", "generate_multiple", "rerank", "manual_reference"}:
            raise ValueError(f"unsupported review action: {action}")
        ranks = [1] if action == "generate_rank_1" else [int(x) for x in data.get("selected_ranks", [])]
        if action == "generate_selected" and len(ranks) != 1:
            raise ValueError("generate_selected requires exactly one selected_ranks item")
        if action == "generate_multiple" and len(ranks) < 2:
            raise ValueError("generate_multiple requires at least two selected_ranks items")
        if any(rank < 1 or rank > 3 for rank in ranks):
            raise ValueError("selected_ranks must be between 1 and 3")
        if len(ranks) != len(set(ranks)):
            raise ValueError("selected_ranks must not contain duplicates")
        manual = _text(data.get("manual_reference"))
        if action == "manual_reference" and not manual:
            raise ValueError("manual_reference is required")
        return cls(action, ranks, manual)

@dataclass(frozen=True)
class QcResult:
    status: Literal["pass", "rerun", "reject"]
    passed: list[str]
    failed: list[str]
    notes: str

def _positive(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number <= 0:
        raise ValueError("dimensions must be positive")
    return number

def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_models.py -q
Expected: PASS with 2 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/models.py tests/test_models.py
git commit -m "feat: add workflow data models"
~~~

---

### Task 3: 运行目录与 JSON 读写

**Files:**
- Create: src/jewelry_on_hand/run_paths.py
- Test: tests/test_run_paths.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_run_paths.py
from jewelry_on_hand.run_paths import RunPaths, create_run_id, read_json, write_json


def test_run_paths_copy_product_and_write_dimensions(tmp_path):
    source = tmp_path / "product.jpg"; source.write_bytes(b"fake")
    paths = RunPaths.create(tmp_path, create_run_id("demo"))
    copied = paths.copy_product_image(source)
    write_json(paths.input_dir / "product_dimensions.json", {"bead_diameter_mm": 10})
    assert copied.name == "product-on-hand.jpg"
    assert read_json(paths.input_dir / "product_dimensions.json") == {"bead_diameter_mm": 10}
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_run_paths.py -q
Expected: FAIL with No module named 'jewelry_on_hand.run_paths'.

- [ ] **Step 3: Write minimal implementation**

~~~python
# src/jewelry_on_hand/run_paths.py
from __future__ import annotations
import json, shutil, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def create_run_id(prefix: str = "auto-reference") -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in prefix).strip("-") or "run"
    return f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}"

@dataclass(frozen=True)
class RunPaths:
    root: Path
    @classmethod
    def create(cls, output_root: Path, run_id: str) -> "RunPaths":
        paths = cls(output_root / run_id)
        for d in [paths.input_dir, paths.analysis_dir, paths.review_dir, paths.generation_dir]:
            d.mkdir(parents=True, exist_ok=True)
        return paths
    @property
    def input_dir(self) -> Path: return self.root / "input"
    @property
    def analysis_dir(self) -> Path: return self.root / "analysis"
    @property
    def review_dir(self) -> Path: return self.root / "review"
    @property
    def generation_dir(self) -> Path: return self.root / "generation"
    def copy_product_image(self, source: Path) -> Path:
        if not source.is_file(): raise FileNotFoundError(source)
        dest = self.input_dir / "product-on-hand.jpg"
        shutil.copy2(source, dest)
        return dest

def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_run_paths.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/run_paths.py tests/test_run_paths.py
git commit -m "feat: create traceable run directories"
~~~

---

### Task 4: 产品分析提示词与品类 Gate

**Files:**
- Create: src/jewelry_on_hand/product_analysis.py
- Create: reference/product-analysis-schema.md
- Test: tests/test_product_analysis.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_product_analysis.py
import pytest
from jewelry_on_hand.product_analysis import UnsupportedProductError, build_analysis_prompt, load_product_analysis
from jewelry_on_hand.run_paths import write_json


def test_prompt_forbids_material_guessing(tmp_path):
    prompt = build_analysis_prompt(tmp_path / "product.jpg", {"bead_diameter_mm": 10})
    assert "只描述肉眼可见外观" in prompt
    assert "不要猜测材质名" in prompt


def test_rejects_non_bracelet_analysis(tmp_path):
    path = tmp_path / "analysis.json"
    write_json(path, {"product_type": "戒指", "wear_position": "手指", "visible_appearance": "银色戒指", "color_family": ["银色"], "style_mood": "清透", "composition": "手部近景", "product_dimensions": {}, "needs_full_front_display": True, "special_requirements": []})
    with pytest.raises(UnsupportedProductError, match="手串/手链"):
        load_product_analysis(path)
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_product_analysis.py -q
Expected: FAIL with No module named 'jewelry_on_hand.product_analysis'.

- [ ] **Step 3: Write minimal implementation**

~~~python
# src/jewelry_on_hand/product_analysis.py
from __future__ import annotations
from pathlib import Path
from typing import Any
from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.run_paths import read_json

class UnsupportedProductError(ValueError):
    pass

def build_analysis_prompt(product_image: Path, dimensions: dict[str, Any] | None = None) -> str:
    return f"""请分析用户输入图：{product_image}
输出严格 JSON：product_type、wear_position、visible_appearance、color_family、style_mood、composition、product_dimensions、needs_full_front_display、special_requirements。
只描述肉眼可见外观：颜色、透明度、内部纹理、反光、珠子大小、排列节奏、主珠位置、隔珠/隔圈/吊坠位置和佩戴关系。
不要猜测材质名；不要把琥珀、红宝石、水晶等概念写进 visible_appearance，除非图片上有可见文字。
第一版只支持手串/手链。可选尺寸信息只作为比例参考，不能覆盖图片可见外观：{dimensions or {}}
"""

def load_product_analysis(path: Path) -> ProductAnalysis:
    analysis = ProductAnalysis.from_dict(read_json(path))
    if not analysis.is_supported_product():
        raise UnsupportedProductError("当前版本只支持手串/手链产品图")
    return analysis
~~~

~~~markdown
# reference/product-analysis-schema.md

产品分析 JSON 是系统内部产物，不是用户第二输入。用户只提供产品上手原图；Codex/视觉执行者根据图片生成 JSON，代码负责校验。visible_appearance 必须只写肉眼可见外观，避免材质猜测。第一版只允许 product_type 包含“手链”或“手串”。
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_product_analysis.py -q
Expected: PASS with 2 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/product_analysis.py reference/product-analysis-schema.md tests/test_product_analysis.py
git commit -m "feat: validate internal product analysis"
~~~

---

### Task 5: 分类表读取

**Files:**
- Create: src/jewelry_on_hand/reference_catalog.py
- Test: tests/test_reference_catalog.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_reference_catalog.py
from openpyxl import Workbook
from jewelry_on_hand.reference_catalog import load_reference_rows


def test_load_reference_rows_maps_columns(tmp_path):
    image = tmp_path / "ref.jpg"; image.write_bytes(b"fake")
    workbook = tmp_path / "catalog.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "分类明细"
    ws.append(["序号", "文件名", "相对路径", "绝对路径", "宽度", "高度", "大小MB", "用途分类", "手链手串适用性", "默认使用策略", "风格分类", "场景关键词", "饰品类型", "推荐使用方式", "备注", "判断置信度"])
    ws.append([1, "ref.jpg", "reference/ref.jpg", str(image), 100, 200, 0.1, "上手姿势/手模构图参考", "是：手腕露出", "常规可优先使用", "暗调闪光", "车内 闪光", "手链/手串", "近景手腕", "手腕/前臂露出面积足", "高"])
    wb.save(workbook)
    rows = load_reference_rows(workbook)
    assert rows[0].file_exists
    assert rows[0].style_category == "暗调闪光"
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_reference_catalog.py -q
Expected: FAIL with No module named 'jewelry_on_hand.reference_catalog'.

- [ ] **Step 3: Implement**

Implement load_reference_rows with REQUIRED_COLUMNS exactly matching: 序号、文件名、相对路径、绝对路径、宽度、高度、大小MB、用途分类、手链手串适用性、默认使用策略、风格分类、场景关键词、饰品类型、推荐使用方式、备注、判断置信度. Convert each row to ReferenceRow and set file_exists from absolute_path.is_file().

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_reference_catalog.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/reference_catalog.py tests/test_reference_catalog.py
git commit -m "feat: load reference classification workbook"
~~~

---

### Task 6: 硬过滤与评分 Top 3

**Files:**
- Create: src/jewelry_on_hand/scoring.py
- Test: tests/test_scoring.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_scoring.py
from pathlib import Path
from jewelry_on_hand.models import ProductAnalysis, ProductDimensions, ReferenceRow
from jewelry_on_hand.scoring import select_top_references


def row(index, exists=True, strategy="常规可优先使用"):
    return ReferenceRow(index, f"{index}.jpg", f"ref/{index}.jpg", Path(f"C:/tmp/{index}.jpg"), 100, 200, 0.1, "上手姿势/手模构图参考", "是：可用于手链/手串", strategy, "暗调闪光", "车内 闪光", "手链/手串", "近景手腕", "手腕/前臂露出面积足", "高", exists)


def test_select_top_references_filters_missing_and_scores_priority():
    product = ProductAnalysis("手链/手串", "手腕", "深红主珠", ["深红"], "暗调闪光", "手腕近景", ProductDimensions(bead_diameter_mm=10), True, ["保留主珠"])
    selected, candidates = select_top_references(product, [row(1), row(2, exists=False), row(3, strategy="无特殊要求不优先使用")])
    assert [item.row.index for item in selected] == [1]
    assert [item.row.index for item in candidates] == [1]
    assert any("暗调" in reason for reason in selected[0].reason)
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_scoring.py -q
Expected: FAIL with No module named 'jewelry_on_hand.scoring'.

- [ ] **Step 3: Implement**

Implement select_top_references and score_reference with the spec hard filter first: file exists, high confidence, default strategy can be used first, jewelry type contains 手链/手串 only, and bracelet applicability is yes/usable. If no candidates remain, relax in order: allow medium confidence, then allow `无特殊要求不优先使用` with penalty, then allow combined target jewelry such as 手链+项链/戒指 while recording ignored non-target jewelry. Use these exact scoring points after filtering: type +30, applicability +25, pose-purpose +20, wearing-display +12, priority strategy +15, high confidence +10, dark/flash match +15, clear/natural match +15, red/chinese-style match +10, mirror +20, wrist/forearm area +15, gesture/skin/light/negative-space usage +10, close-up +8, large bead close-up +15, non-priority -30, non-target jewelry -40, still/object/earring purpose -50, stacked/complex jewelry -10, crop risk -15. Return selected Top 3 and full candidate list, both ranked.

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_scoring.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/scoring.py tests/test_scoring.py
git commit -m "feat: score and rank hand references"
~~~

---

### Task 7: Review 包与 HTML

**Files:**
- Create: src/jewelry_on_hand/review_package.py
- Test: tests/test_review_package.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_review_package.py
from pathlib import Path
from jewelry_on_hand.models import ReferenceRow, ScoredReference
from jewelry_on_hand.review_package import write_review_package
from jewelry_on_hand.run_paths import RunPaths, read_json


def test_write_review_package_outputs_json_and_html(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"; product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"; ref.write_bytes(b"ref")
    row = ReferenceRow(1, "ref.jpg", "ref.jpg", ref, 100, 200, 0.1, "上手姿势/手模构图参考", "是", "常规可优先使用", "暗调闪光", "车内", "手链/手串", "近景", "手腕露出", "高", True)
    scored = [ScoredReference(row, 100, 1, ["理由"], ["风险"], ["参考图中的原有手链"])]
    html = write_review_package(paths, product, scored, scored)
    assert "Top 3 参考图" in html.read_text(encoding="utf-8")
    assert read_json(paths.analysis_dir / "selected_references.json")[0]["rank"] == 1
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_review_package.py -q
Expected: FAIL with No module named 'jewelry_on_hand.review_package'.

- [ ] **Step 3: Implement**

Create write_review_package(paths, product_image, selected, candidates). It writes analysis/reference_candidates.json, analysis/selected_references.json, copies each selected reference to review/rank-N-file, and writes review/review.html with product preview, Top 3 cards, rank, score, purpose, style, scene keywords, reasons, risks, ignored jewelry.

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_review_package.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/review_package.py tests/test_review_package.py
git commit -m "feat: generate top reference review package"
~~~

---

### Task 8: Review 决策 Gate

**Files:**
- Create: src/jewelry_on_hand/review_decision.py
- Create: reference/review-decision-schema.md
- Test: tests/test_review_decision.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_review_decision.py
import pytest
from jewelry_on_hand.review_decision import ReviewGateError, require_generation_decision, write_review_decision
from jewelry_on_hand.run_paths import RunPaths


def test_generation_requires_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    with pytest.raises(ReviewGateError, match="review_decision.json"):
        require_generation_decision(paths)


def test_write_and_read_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_review_decision(paths, {"action": "generate_selected", "selected_ranks": [2]})
    assert require_generation_decision(paths).selected_ranks == [2]
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_review_decision.py -q
Expected: FAIL with No module named 'jewelry_on_hand.review_decision'.

- [ ] **Step 3: Implement**

Implement write_review_decision(paths, data) to validate ReviewDecision and write review/review_decision.json. Implement require_generation_decision(paths) to raise ReviewGateError when the file is missing, malformed, or action is not allowed to generate. `rerank` must stop before generation; `manual_reference` is only a recorded first-version request and must also stop before generation.

~~~markdown
# reference/review-decision-schema.md

review/review_decision.json 是 AIReiter 生成前的强制 gate。合法 action：generate_rank_1、generate_selected、generate_multiple、rerank、manual_reference。generate_rank_1 的 selected_ranks 固定为 [1]；generate_selected 必须且只能携带 1 个 selected_ranks；generate_multiple 必须携带至少 2 个 selected_ranks；selected_ranks 不允许重复；rerank 不允许进入生成；manual_reference 第一版只记录诉求，不允许进入生成。
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_review_decision.py -q
Expected: PASS with 2 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/review_decision.py reference/review-decision-schema.md tests/test_review_decision.py
git commit -m "feat: enforce review gate before generation"
~~~

---

### Task 9: Prompt Builder

**Files:**
- Create: src/jewelry_on_hand/prompt_builder.py
- Create: reference/prompt-template.md
- Test: tests/test_prompt_builder.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_prompt_builder.py
from pathlib import Path
from jewelry_on_hand.models import ProductAnalysis, ProductDimensions, ReferenceRow, ScoredReference
from jewelry_on_hand.prompt_builder import build_prompt


def test_prompt_includes_fixed_sentence_dimensions_mirror_and_ignored_jewelry():
    product = ProductAnalysis("手链/手串", "手腕", "深红主珠居中，两侧透明茶金纹理珠", ["深红"], "暗调闪光", "手腕近景", ProductDimensions(bead_diameter_mm=10, dimension_source="用户录入"), True, ["保留主珠"])
    row = ReferenceRow(1, "ref.jpg", "ref.jpg", Path("C:/tmp/ref.jpg"), 100, 200, 0.1, "上手姿势/手模构图参考", "是", "常规可优先使用", "暗调闪光", "对镜 车内", "手链/手串、戒指", "对镜近景", "手腕露出", "高", True)
    prompt = build_prompt(product, ScoredReference(row, 100, 1, ["理由"], [], ["参考图中的原有手链", "参考图中的原有戒指"]))
    assert "产品保真以内部图2中肉眼可见的外观为准" in prompt
    assert "珠径约 10mm" in prompt
    assert "参考图中的原有戒指" in prompt
    assert "前景手部 + 镜中反射手部" in prompt
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_prompt_builder.py -q
Expected: FAIL with No module named 'jewelry_on_hand.prompt_builder'.

- [ ] **Step 3: Implement**

Implement build_prompt(product, reference) from the fixed template in the spec. It must include the exact fidelity sentence: “产品保真以内部图2中肉眼可见的外观为准，不要根据材质名称自行改款、换色、重设计或美化成其他款式。” It must format bead diameter as “珠径约 Nmm”, include ignored_reference_jewelry, include mirror instructions when reference text contains 对镜/镜子/反射, and keep 3:4、2K、小红书自然上手图.

~~~markdown
# reference/prompt-template.md

固定模板必须保留产品保真句。内部图片顺序固定为：内部图1 自动参考图；内部图2 用户输入产品上手原图。
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_prompt_builder.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/prompt_builder.py reference/prompt-template.md tests/test_prompt_builder.py
git commit -m "feat: build fixed generation prompt"
~~~

---

### Task 10: AIReiter 生成封装

**Files:**
- Create: src/jewelry_on_hand/generation.py
- Test: tests/test_generation.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_generation.py
import json
from pathlib import Path
from jewelry_on_hand.generation import run_generation
from jewelry_on_hand.run_paths import RunPaths, write_json


def test_generation_uses_reference_then_product(tmp_path, monkeypatch):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"; product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"; ref.write_bytes(b"ref")
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1"})
    write_json(paths.analysis_dir / "selected_references.json", [{"rank": 1, "selected_reference": str(ref), "score": 100, "reason": [], "risk": [], "ignored_reference_jewelry": [], "metadata": {}}])
    calls = []
    def fake_run(command, capture_output, text, check):
        calls.append(command)
        class R: stdout = json.dumps({"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}})
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    run_generation(paths, product, {1: "prompt text"}, Path("skills/aireiter-image-generation/scripts/aireiter_image_helper.py"), wait=False)
    command = calls[0]
    first = command.index("--image") + 1
    second = command.index("--image", first) + 1
    assert command[first] == str(ref)
    assert command[second] == str(product)
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_generation.py -q
Expected: FAIL with No module named 'jewelry_on_hand.generation'.

- [ ] **Step 3: Implement**

Implement run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True). It must call require_generation_decision, read selected_references.json, create generation directories by output sequence (`generation/01` for a single selected rank, `generation/01` and `generation/02` for two selected ranks), write prompt.txt, copy hand-reference with the source extension, call helper submit with model nano_banana_v2, aspect-ratio 3:4, resolution 2K, then pass --image reference_path before --image product_image. Save submit.json, wait result.json when wait=True, download the first `data.output[].url` to result.png, and return generation directories.

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_generation.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/generation.py tests/test_generation.py
git commit -m "feat: submit reviewed generation jobs"
~~~

---

### Task 11: QC 记录

**Files:**
- Create: src/jewelry_on_hand/qc.py
- Create: reference/qc-checklist.md
- Test: tests/test_qc.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_qc.py
import pytest
from jewelry_on_hand.qc import write_qc_result
from jewelry_on_hand.run_paths import read_json


def test_write_qc_result(tmp_path):
    path = write_qc_result(tmp_path, "rerun", ["无水印"], ["主珠被裁切"], "调整参考图")
    assert read_json(path)["status"] == "rerun"
    with pytest.raises(ValueError, match="status"):
        write_qc_result(tmp_path, "unknown", [], [], "")
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_qc.py -q
Expected: FAIL with No module named 'jewelry_on_hand.qc'.

- [ ] **Step 3: Implement**

Implement write_qc_result(generation_dir, status, passed, failed, notes) and allow only pass/rerun/reject. Include checklist entries for product fidelity, composition transfer, wearing naturalness, hand realism, and forbidden items.

~~~markdown
# reference/qc-checklist.md

QC 状态只能是 pass、rerun、reject。必须检查产品保真、构图迁移、佩戴自然度、手部真实性和禁止项；出现文字、水印、logo、继承参考图首饰、核心配件缺失或明显手部畸形时标记为 reject。
~~~

- [ ] **Step 4: Run test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_qc.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Commit**

~~~powershell
git add src/jewelry_on_hand/qc.py reference/qc-checklist.md tests/test_qc.py
git commit -m "feat: record manual qc outcomes"
~~~

---

### Task 12: CLI 串联与端到端 Gate

**Files:**
- Create: src/jewelry_on_hand/cli.py
- Create: reference/manual-workflow.md
- Test: tests/test_cli.py

- [ ] **Step 1: Write the failing test**

~~~python
# tests/test_cli.py
import json
from openpyxl import Workbook
from jewelry_on_hand.cli import main


def make_catalog(path, ref):
    wb = Workbook(); ws = wb.active; ws.title = "分类明细"
    ws.append(["序号", "文件名", "相对路径", "绝对路径", "宽度", "高度", "大小MB", "用途分类", "手链手串适用性", "默认使用策略", "风格分类", "场景关键词", "饰品类型", "推荐使用方式", "备注", "判断置信度"])
    for i in range(1, 4): ws.append([i, f"ref{i}.jpg", f"ref{i}.jpg", str(ref), 100, 200, 0.1, "上手姿势/手模构图参考", "是：可用于手链/手串", "常规可优先使用", "暗调闪光", "车内 闪光", "手链/手串", "近景手腕", "手腕/前臂露出面积足", "高"])
    wb.save(path)


def test_prepare_review_cli_creates_review_html(tmp_path):
    product = tmp_path / "product.jpg"; product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"; ref.write_bytes(b"ref")
    catalog = tmp_path / "catalog.xlsx"; make_catalog(catalog, ref)
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps({"product_type": "手链/手串", "wear_position": "手腕", "visible_appearance": "深红主珠", "color_family": ["深红"], "style_mood": "暗调闪光", "composition": "手腕近景", "product_dimensions": {}, "needs_full_front_display": True, "special_requirements": ["保留主珠"]}, ensure_ascii=False), encoding="utf-8")
    assert main(["prepare-review", "--product-image", str(product), "--analysis-json", str(analysis), "--classification", str(catalog), "--output-root", str(tmp_path / "runs"), "--run-id", "demo"]) == 0
    assert (tmp_path / "runs" / "demo" / "review" / "review.html").is_file()
    assert not (tmp_path / "runs" / "demo" / "review" / "review_decision.json").exists()
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_cli.py -q
Expected: FAIL with No module named 'jewelry_on_hand.cli'.

- [ ] **Step 3: Implement**

Implement argparse commands:
- prepare-review: copy product image, optionally write product_dimensions.json, require or generate product_analysis_prompt.txt, load product_analysis.json, load classification workbook, score Top 3, write review package.
- record-decision: write review_decision.json.
- generate: require a valid and generatable review decision, re-load product analysis through the product gate, load selected references, build prompts only for approved ranks, and call run_generation.
- qc: write qc.json.

~~~markdown
# reference/manual-workflow.md

1. prepare-review 复制用户图、加载产品分析 JSON、读取分类表并生成 review/review.html。
2. 用户选择候选图后运行 record-decision 写入 review/review_decision.json。
3. generate 在存在有效且可生成的 review 决策后调用 AIReiter；rerank 和第一版 manual_reference 不会进入生成；内部图片顺序固定为自动参考图在前、用户产品图在后；生成目录按本次输出序号写入，并在 wait 成功后保存 result.json 和 result.png。
4. qc 写入 generation/NN/qc.json，状态只能是 pass、rerun、reject。
~~~

- [ ] **Step 4: Run CLI test to verify it passes**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_cli.py -q
Expected: PASS with 1 passed.

- [ ] **Step 5: Run all tests**

Run: & 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
Expected: PASS with all tests passing.

- [ ] **Step 6: Commit**

~~~powershell
git add src/jewelry_on_hand/cli.py reference/manual-workflow.md tests/test_cli.py
git commit -m "feat: add reviewed jewelry generation cli"
~~~

---

## 验收映射

- 用户只输入 1 张产品上手原图：Task 3、Task 12。
- 可选尺寸信息：Task 2、Task 4、Task 9、Task 12。
- 只支持手串/手链并拦截其他品类：Task 2、Task 4。
- 读取分类表并找到文件存在候选图：Task 5。
- 硬过滤、放宽、评分、Top 3、推荐理由与风险：Task 6、Task 7。
- review/review.html 与 review 包：Task 7、Task 12。
- review/review_decision.json 与生成前 gate：Task 8、Task 10、Task 12。
- 固定 prompt、尺寸约束、对镜关系、忽略参考图首饰：Task 9。
- AIReiter nano_banana_v2、3:4、2K、内部图1/内部图2顺序：Task 10。
- 每次选择和生成有可追踪 JSON 与本地文件：Task 3、Task 7、Task 10、Task 11。
- 人工 QC 通过、待重跑、淘汰：Task 11。

## 自检结果

- Spec coverage：规格第 1-17 节均映射到任务；规格列为暂不纳入第一版的工作未进入实施任务。
- Placeholder scan：计划没有使用占位语；每个变更任务都包含测试、运行命令、实现要求和提交命令。
- Type consistency：后续任务统一使用 Task 2 中的 ProductAnalysis、ReferenceRow、ScoredReference、ReviewDecision；路径统一使用 outputs/auto_reference_runs/<run-id>/input|analysis|review|generation。
