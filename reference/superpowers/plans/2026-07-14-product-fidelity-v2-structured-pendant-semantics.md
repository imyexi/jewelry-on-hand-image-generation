# 产品保真 v2 结构化吊坠语义 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为普通项链和带链吊坠的新 run 建立 `schema_version=2` 的结构化吊坠契约，使 prepare-review、record-decision、Prompt、生成 gate、QC 和便携检查器共享同一事实，同时保持历史 v1 只读兼容。

**Architecture:** 在数据模型中新增不可变 `PendantSemantics`，由最终规范化 `ProductAnalysis` 唯一构建并与 canonical 逐字段交叉校验。新项链生命周期强制 v2，历史 v1 只允许读取、检查和展示；Prompt/QC 从结构化契约渲染，不再从 canonical 自由文本推断吊坠存在性或禁止创建策略。

**Tech Stack:** Python 3.11+、dataclasses、pytest、现有 `uv` 项目环境、纯 Python 便携校验脚本、Markdown 操作文档。

## Global Constraints

- 所有代码注释、错误信息、测试名称说明和文档使用中文；代码标识符沿用项目现有英文命名。
- 所有参考和流程 Markdown 放在 `reference/`；测试命令的 stdout、stderr、退出码和审查记录放在 `output/final-verification/2026-07-14/`。
- 当前工作树混有并发戒指、HERO、飞书、output_role 和既有项链修复；实施期间不得回退、覆盖、暂存或提交任何实现改动，每个 Task 以测试和双阶段审查作为检查点。
- 不修改历史 `output/` run03 至 run07，不真实调用 provider，不生成 task ID，不查询 credits，不伪造图片或 QC proof。
- 附件产品是同一条海蓝宝长链绕颈形成双圈，不是两件项链，也不是吊坠；当前不存在三圈带链吊坠商品，不创建三圈 SKU、素材或成功 proof。
- 保留 `ProductAnalysis.layer_count=1/2/3` 的数据与运行时兼容；自动化只验证结构能力，真实 proof 不要求不存在的三圈商品。
- 本计划只关闭 I1；I5 的双圈真人佩戴成功 proof 和并发 HERO 角色过滤问题继续单列，不得在结果中误报完成。
- 不修改戒指、飞书、HERO、真实 proof 和 provider helper 业务逻辑；手串与戒指 v1 行为必须回归通过。
- 新生产代码严格执行 RED -> GREEN -> REFACTOR：先运行新增测试并确认因缺少目标行为失败，再写最小实现，再运行聚焦回归。
- `schema_version=1` 项链 canonical 不自动迁移；历史 run 需要重新生成时必须新建 run 并重新执行 `prepare-review`。

## 文件职责与任务边界

| 文件 | 本计划职责 |
| --- | --- |
| `src/jewelry_on_hand/models.py` | 定义 `PendantSemantics`，支持 canonical v1/v2 严格解析和原样序列化。 |
| `src/jewelry_on_hand/product_fidelity.py` | 新项链 v2 builder、结构一致性、无吊坠自由文本零敏感词门禁。 |
| `src/jewelry_on_hand/review_decision.py` | 在原子替换前阻止新项链导入 v1 或冲突 v2。 |
| `src/jewelry_on_hand/generation.py`、`src/jewelry_on_hand/cli.py` | 在创建 generation 目录和 helper 调用前重复验证 v2。 |
| `src/jewelry_on_hand/prompt_builder.py`、`src/jewelry_on_hand/category_policies/necklace.py` | 只从最终 analysis 与 v2 契约渲染吊坠段。 |
| `src/jewelry_on_hand/qc.py` | 从 v2 presence/count/layer 构建精确 runtime checklist。 |
| `skills/jewelry-on-hand-workflow/scripts/*.py` | 无包依赖地验证 v1 只读、v2 Prompt/QC/canonical 契约。 |
| `tests/test_product_fidelity_v2.py` | v2 模型、builder、字段矩阵和 analysis/canonical 交叉校验。 |
| 既有 `tests/test_*.py` | 生命周期、Prompt、QC、便携和 I2-I4 回归。 |
| `reference/*.md`、`skills/jewelry-on-hand-workflow/**/*.md` | 全文协调 v1/v2 生命周期、错误修复动作和只读边界。 |

---

### Task 1: canonical v1/v2 模型与序列化

**Files:**
- Modify: `src/jewelry_on_hand/models.py:646`
- Modify: `tests/test_models.py:48`
- Create: `tests/test_product_fidelity_v2.py`

**Interfaces:**
- Consumes: 现有 `MustKeepConstraint`、`ProductFidelityConstraints.from_dict()`、`to_dict()`。
- Produces: `PendantSemantics`、`ProductFidelityConstraints.pendant_semantics: PendantSemantics | None`；v1 序列化不增加新键，v2 必须包含新对象。

- [ ] **Step 1: 编写 v1 原样 round-trip 与 v2 普通项链/带链吊坠 round-trip 失败测试**

在 `tests/test_product_fidelity_v2.py` 写入下列测试骨架；复用 `tests/test_models.py::_constraints_data` 的字段形状，但在新文件内定义独立工厂，避免跨测试模块导入私有 helper：

```python
from __future__ import annotations

import pytest
import json

from jewelry_on_hand.models import PendantSemantics, ProductFidelityConstraints


def _constraints_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": 1,
        "source": {
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
            "product_analysis_sha256": "a" * 64,
        },
        "detected_keywords": [],
        "must_keep": [],
        "must_not_change": ["保持整体可见结构"],
        "needs_user_review": False,
        "detail_crop_recommended": False,
        "review_status": "not_applicable",
    }
    data.update(overrides)
    return data


def test_v1_constraints_round_trip_does_not_add_pendant_semantics() -> None:
    payload = _constraints_data()
    constraints = ProductFidelityConstraints.from_dict(payload)

    assert constraints.pendant_semantics is None
    assert constraints.to_dict() == payload


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"presence": "absent", "count": 0, "layer": None, "creation_policy": "forbid"},
            PendantSemantics("absent", 0, None, "forbid"),
        ),
        (
            {"presence": "present", "count": 1, "layer": 2, "creation_policy": "forbid"},
            PendantSemantics("present", 1, 2, "forbid"),
        ),
    ],
)
def test_v2_constraints_round_trip_structured_pendant_semantics(
    payload: dict[str, object], expected: PendantSemantics
) -> None:
    raw = _constraints_data(schema_version=2, pendant_semantics=payload)
    constraints = ProductFidelityConstraints.from_dict(raw)

    assert constraints.pendant_semantics == expected
    assert constraints.to_dict() == raw
```

- [ ] **Step 2: 运行模型测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "round_trip" -v
```

Expected: collection/import 因 `PendantSemantics` 尚不存在而失败；不得把 import 改成临时跳过。

- [ ] **Step 3: 编写非法版本、缺失对象和字段组合失败测试**

在同一测试文件加入：

```python
@pytest.mark.parametrize("schema_version", [0, 3, True, "2"])
def test_constraints_reject_unsupported_schema_versions(schema_version: object) -> None:
    with pytest.raises(ValueError, match="schema_version"):
        ProductFidelityConstraints.from_dict(
            _constraints_data(schema_version=schema_version)
        )


def test_v2_constraints_require_pendant_semantics_object() -> None:
    with pytest.raises(ValueError, match="v2.*pendant_semantics 必填"):
        ProductFidelityConstraints.from_dict(_constraints_data(schema_version=2))


def test_v1_constraints_reject_non_null_pendant_semantics() -> None:
    with pytest.raises(ValueError, match="v1.*pendant_semantics"):
        ProductFidelityConstraints.from_dict(
            _constraints_data(
                pendant_semantics={
                    "presence": "absent",
                    "count": 0,
                    "layer": None,
                    "creation_policy": "forbid",
                }
            )
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"presence": "unknown", "count": 0, "layer": None, "creation_policy": "forbid"}, "presence"),
        ({"presence": "absent", "count": True, "layer": None, "creation_policy": "forbid"}, "count"),
        ({"presence": "absent", "count": 1, "layer": None, "creation_policy": "forbid"}, "absent"),
        ({"presence": "present", "count": 0, "layer": 1, "creation_policy": "forbid"}, "present"),
        ({"presence": "present", "count": 1, "layer": None, "creation_policy": "forbid"}, "layer"),
        ({"presence": "present", "count": 1, "layer": 4, "creation_policy": "forbid"}, "layer"),
        ({"presence": "absent", "count": 0, "layer": None, "creation_policy": "allow"}, "creation_policy"),
    ],
)
def test_pendant_semantics_reject_invalid_combinations(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProductFidelityConstraints.from_dict(
            _constraints_data(schema_version=2, pendant_semantics=payload)
        )
```

- [ ] **Step 4: 运行非法输入测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "require or reject" -v
```

Expected: 因模型仍只接受 v1 或没有 `pendant_semantics` 校验而失败。

- [ ] **Step 5: 实现最小严格模型**

在 `models.py` 的 `FidelityReviewStatus` 后加入，复用 `_required_int` 并显式排除 bool：

```python
PendantPresence = Literal["present", "absent"]
PendantCreationPolicy = Literal["forbid"]


@dataclass(frozen=True)
class PendantSemantics:
    presence: PendantPresence
    count: int
    layer: int | None
    creation_policy: PendantCreationPolicy

    def __post_init__(self) -> None:
        if self.presence not in {"present", "absent"}:
            raise ValueError("pendant_semantics.presence 必须是 present/absent")
        if isinstance(self.count, bool) or not isinstance(self.count, int):
            raise ValueError("pendant_semantics.count 必须是整数 0 或 1")
        if self.count not in {0, 1}:
            raise ValueError("pendant_semantics.count 第一阶段只能是 0 或 1")
        if self.layer is not None and (
            isinstance(self.layer, bool)
            or not isinstance(self.layer, int)
            or not 1 <= self.layer <= 3
        ):
            raise ValueError("pendant_semantics.layer 必须是 null 或 1 至 3")
        if self.creation_policy != "forbid":
            raise ValueError("pendant_semantics.creation_policy 必须为 forbid")
        if self.presence == "absent" and (self.count != 0 or self.layer is not None):
            raise ValueError("presence=absent 时 count 必须为 0 且 layer 必须为 null")
        if self.presence == "present" and (self.count != 1 or self.layer is None):
            raise ValueError("presence=present 时 count 必须为 1 且 layer 必须为 1 至 3")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PendantSemantics":
        source = _ensure_mapping(data, "pendant_semantics")
        return cls(
            presence=_required_string(source, "presence"),  # type: ignore[arg-type]
            count=_required_int(source.get("count"), "count"),
            layer=_optional_int(source.get("layer"), "layer"),
            creation_policy=_required_string(source, "creation_policy"),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "presence": self.presence,
            "count": self.count,
            "layer": self.layer,
            "creation_policy": self.creation_policy,
        }
```

把 `ProductFidelityConstraints` 扩展为：

```python
@dataclass(frozen=True)
class ProductFidelityConstraints:
    schema_version: int
    source: dict[str, Any]
    detected_keywords: tuple[str, ...]
    must_keep: tuple[MustKeepConstraint, ...]
    must_not_change: tuple[str, ...]
    needs_user_review: bool
    detail_crop_recommended: bool
    review_status: FidelityReviewStatus
    pendant_semantics: PendantSemantics | None = None
```

`__post_init__` 必须实现以下精确分支：

```python
if isinstance(self.schema_version, bool) or self.schema_version not in {1, 2}:
    raise ValueError("schema_version 必须为 1 或 2")
if self.schema_version == 1:
    if self.pendant_semantics is not None:
        raise ValueError("v1 的 pendant_semantics 必须为 null 或缺失")
else:
    if self.pendant_semantics is None:
        raise ValueError("v2 的 pendant_semantics 必填")
    if not isinstance(self.pendant_semantics, PendantSemantics):
        object.__setattr__(
            self,
            "pendant_semantics",
            PendantSemantics.from_dict(self.pendant_semantics),
        )
```

`from_dict()` 先检查 schema 与键组合，再只在 v2 解析对象；`to_dict()` 只在 v2 写键，以保持 v1 原样 round-trip：

```python
schema_version = _required_int(source.get("schema_version"), "schema_version")
if schema_version not in {1, 2}:
    raise ValueError("schema_version 必须为 1 或 2")
if schema_version == 1 and source.get("pendant_semantics") is not None:
    raise ValueError("v1 的 pendant_semantics 必须为 null 或缺失")
if schema_version == 2 and "pendant_semantics" not in source:
    raise ValueError("v2 的 pendant_semantics 必填")
pendant_semantics = (
    PendantSemantics.from_dict(source.get("pendant_semantics"))
    if schema_version == 2
    else None
)
```

```python
payload = {
    "schema_version": self.schema_version,
    "source": dict(self.source),
    "detected_keywords": list(self.detected_keywords),
    "must_keep": [item.to_dict() for item in self.must_keep],
    "must_not_change": list(self.must_not_change),
    "needs_user_review": self.needs_user_review,
    "detail_crop_recommended": self.detail_crop_recommended,
    "review_status": self.review_status,
}
if self.schema_version == 2:
    assert self.pendant_semantics is not None
    payload["pendant_semantics"] = self.pendant_semantics.to_dict()
return payload
```

- [ ] **Step 6: 运行 GREEN 与现有模型回归**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_models.py -v
```

Expected: 新增模型测试和既有模型测试全部 PASS；v1 fixture 无需批量增加空键。

- [ ] **Step 7: Task 1 双阶段复审**

审查输入限定为 `models.py`、`test_models.py`、`test_product_fidelity_v2.py` 的本 Task diff。规格审查必须确认 v1 原样、v2 必填、bool 不冒充整数；质量审查必须确认没有自动 v1→v2 推断和未测试分支。Critical/Important 全部修复并重跑 Step 6 后才进入 Task 2。

---

### Task 2: v2 builder、全字段零敏感词与结构交叉校验

**Files:**
- Modify: `src/jewelry_on_hand/product_fidelity.py:121`
- Modify: `tests/test_product_fidelity_v2.py`
- Modify: `tests/test_final_necklace_important_fixes.py:50`

**Interfaces:**
- Consumes: `PendantSemantics`、最终规范化 `ProductAnalysis.product_type/has_pendant/pendant_count/pendant_layer`。
- Produces: `build_product_fidelity_constraints()` 对普通项链输出 `absent/0/null/forbid`，对带链吊坠输出 `present/1/layer/forbid`；`validate_product_fidelity_constraints()` 提供所有后续 gate 复用的唯一 v2 校验。

- [ ] **Step 1: 编写两类项链 builder RED 测试**

在 `tests/test_product_fidelity_v2.py` 增加 `_necklace_analysis()`，字段与现有 `tests/test_prompt_builder.py::_necklace_product` 一致：

```python
from jewelry_on_hand.models import ProductAnalysis
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    validate_product_fidelity_constraints,
)


def _necklace_analysis(
    *,
    pendant: bool = False,
    layer_count: int = 2,
    pendant_count: int | None = None,
    visible_appearance: str | None = None,
) -> ProductAnalysis:
    product_type = "pendant_necklace" if pendant else "necklace"
    return ProductAnalysis.from_dict(
        {
            "product_type": product_type,
            "wear_position": "颈部",
            "visible_appearance": visible_appearance or (
                "双层细链，第二层中央有水滴形吊坠"
                if pendant
                else "同一条连续海蓝宝微珠长链绕颈形成上下双圈"
            ),
            "color_family": ["海蓝"],
            "style_mood": "清透",
            "composition": "真人佩戴正面构图",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
            "detected_product_type": product_type,
            "confirmed_product_type": product_type,
            "classification_confidence": "high",
            "classification_evidence": ["肉眼可见结构"],
            "classification_source": "manual_override",
            "display_mode": "worn",
            "source_image_type": "worn_source",
            "layer_count": layer_count,
            "length_category": "long",
            "chain_or_strand_type": "连续微珠链",
            "has_pendant": pendant,
            "pendant_count": (
                1 if pendant else 0
            ) if pendant_count is None else pendant_count,
            "pendant_layer": 2 if pendant else None,
            "pendant_position": "第二层中央" if pendant else None,
            "pendant_orientation": "正面向前" if pendant else None,
            "connection_structure": "吊环连接第二层链条" if pendant else None,
            "symmetry": "沿身体中线对称",
            "is_independent_multi_item": False,
        }
    )


def test_plain_necklace_builder_emits_v2_absent_contract() -> None:
    constraints = build_product_fidelity_constraints(_necklace_analysis())

    assert constraints.schema_version == 2
    assert constraints.pendant_semantics == PendantSemantics("absent", 0, None, "forbid")


def test_plain_necklace_builder_sanitizes_non_pendant_rule_text() -> None:
    product = _necklace_analysis(
        visible_appearance="双圈微珠链中央有一个活动跑环，没有任何垂饰"
    )
    constraints = build_product_fidelity_constraints(product)
    semantic_text = json.dumps(constraints.to_dict(), ensure_ascii=False)

    assert "跑环" in semantic_text
    assert all(term not in semantic_text for term in PENDANT_TERMS)


def test_pendant_necklace_builder_emits_v2_present_contract_and_traceable_item() -> None:
    constraints = build_product_fidelity_constraints(_necklace_analysis(pendant=True))

    assert constraints.schema_version == 2
    assert constraints.pendant_semantics == PendantSemantics("present", 1, 2, "forbid")
    pendant_items = [item for item in constraints.must_keep if item.normalized_keyword == "吊坠"]
    assert len(pendant_items) == 1
    assert "第 2 层" in pendant_items[0].relationship


def test_pendant_necklace_v2_rejects_multiple_pendants_in_first_phase() -> None:
    with pytest.raises(ValueError, match="第一阶段.*1 颗主吊坠"):
        build_product_fidelity_constraints(
            _necklace_analysis(pendant=True, pendant_count=2)
        )
```

- [ ] **Step 2: 运行 builder 测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "builder" -v
```

Expected: 当前 builder 返回 schema v1，两个用例因版本/结构对象不匹配失败。

- [ ] **Step 3: 编写普通项链全部自由文本字段 × 全别名矩阵 RED**

定义敏感词和注入 helper，确保错误包含精确字段路径：

```python
from dataclasses import replace
import re

from jewelry_on_hand.models import MustKeepConstraint


PENDANT_TERMS = ("吊坠", "主吊坠", "链坠", "流苏", "坠子")
SEMANTIC_FIELD_PATHS = (
    "detected_keywords[0]",
    "must_not_change[0]",
    "must_keep[0].name",
    "must_keep[0].source_text",
    "must_keep[0].normalized_keyword",
    "must_keep[0].location",
    "must_keep[0].visual_shape",
    "must_keep[0].relationship",
    "must_keep[0].forbid[0]",
    "must_keep[0].qc_question",
)


def _safe_item() -> MustKeepConstraint:
    return MustKeepConstraint(
        name="微珠链整体结构",
        source_text="同一条连续微珠链绕颈形成上下双圈",
        normalized_keyword="微珠链",
        location="颈前可见区域",
        visual_shape="连续细密圆珠链",
        relationship="同一条长链形成上下两圈",
        forbid=("改成两件独立首饰",),
        qc_question="同一条连续微珠链是否仍形成上下双圈",
    )


def _inject_semantic_text(
    constraints: ProductFidelityConstraints, field_path: str, text: str
) -> ProductFidelityConstraints:
    if field_path == "detected_keywords[0]":
        return replace(constraints, detected_keywords=(text,))
    if field_path == "must_not_change[0]":
        return replace(constraints, must_not_change=(text,))
    item = _safe_item()
    field_name = field_path.removeprefix("must_keep[0].")
    if field_name == "forbid[0]":
        item = replace(item, forbid=(text,))
    else:
        item = replace(item, **{field_name: text})
    return replace(constraints, must_keep=(item,), review_status="pending", needs_user_review=True, detail_crop_recommended=True)


@pytest.mark.parametrize("term", PENDANT_TERMS)
@pytest.mark.parametrize("field_path", SEMANTIC_FIELD_PATHS)
def test_absent_v2_rejects_pendant_term_in_every_free_text_field(
    term: str, field_path: str
) -> None:
    product = _necklace_analysis()
    constraints = _inject_semantic_text(
        build_product_fidelity_constraints(product), field_path, f"禁止新增{term}"
    )

    with pytest.raises(ValueError, match=re.escape(field_path)):
        validate_product_fidelity_constraints(product, constraints)
```

- [ ] **Step 4: 编写 analysis/canonical 冲突和 present 可追溯性 RED**

```python
@pytest.mark.parametrize(
    "semantics",
    [
        PendantSemantics("present", 1, 1, "forbid"),
        PendantSemantics("present", 1, 2, "forbid"),
    ],
)
def test_plain_necklace_rejects_present_contract(semantics: PendantSemantics) -> None:
    product = _necklace_analysis()
    constraints = replace(
        build_product_fidelity_constraints(product), pendant_semantics=semantics
    )
    with pytest.raises(ValueError, match="analysis=.*necklace.*canonical=.*present.*prepare-review"):
        validate_product_fidelity_constraints(product, constraints)


def test_pendant_necklace_rejects_wrong_layer_contract() -> None:
    product = _necklace_analysis(pendant=True)
    constraints = replace(
        build_product_fidelity_constraints(product),
        pendant_semantics=PendantSemantics("present", 1, 1, "forbid"),
    )
    with pytest.raises(ValueError, match="analysis=.*2.*canonical=.*1.*prepare-review"):
        validate_product_fidelity_constraints(product, constraints)


def test_present_v2_requires_traceable_pendant_must_keep() -> None:
    product = _necklace_analysis(pendant=True)
    constraints = replace(build_product_fidelity_constraints(product), must_keep=())
    with pytest.raises(ValueError, match="可追溯.*must_keep"):
        validate_product_fidelity_constraints(product, constraints)
```

- [ ] **Step 5: 运行结构门禁测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py -k "absent_v2 or conflict or wrong_layer or traceable" -v
```

Expected: 当前词法极性实现会允许至少“禁止新增吊坠”并且没有结构交叉校验，测试失败。

- [ ] **Step 6: 实现项链 v2 builder，吊坠存在性不调用 alias/NLP helper**

在 `product_fidelity.py` 导入 `PendantSemantics`。`build_product_fidelity_constraints()` 保持 ring 与 bracelet 的 v1 分支，把两类项链交给独立 helper：

```python
if product.normalized_product_type is ProductType.RING:
    return _build_ring_fidelity_constraints(product, source)
if product.normalized_product_type in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}:
    return _build_necklace_v2_fidelity_constraints(product, source)
```

新 helper 的吊坠 contract 只能读取规范字段；非吊坠规则可以继续使用 `KEYWORD_RULES`，但必须排除 normalized=`吊坠`。如果某条命中的 `source_text` 含任一敏感词，则将该项 `source_text` 收敛为不含敏感词的 `matched_alias`，不能把“无/禁止吊坠”复制进 canonical：

```python
def _build_necklace_v2_fidelity_constraints(
    product: ProductAnalysis, source: dict[str, Any]
) -> ProductFidelityConstraints:
    has_structured_pendant = (
        product.normalized_product_type is ProductType.PENDANT_NECKLACE
        and product.has_pendant
    )
    semantics = PendantSemantics(
        presence="present" if has_structured_pendant else "absent",
        count=1 if has_structured_pendant else 0,
        layer=product.pendant_layer if has_structured_pendant else None,
        creation_policy="forbid",
    )
    must_keep, detected_keywords = _extract_non_pendant_necklace_items(product)
    if has_structured_pendant:
        assert product.pendant_layer is not None
        must_keep.append(
            MustKeepConstraint(
                name="主吊坠可见结构",
                source_text=product.visible_appearance,
                normalized_keyword="吊坠",
                location=product.pendant_position or "产品图中肉眼可见位置",
                visual_shape=product.visible_appearance,
                relationship=(
                    f"保持第 {product.pendant_layer} 层、原朝向和肉眼可见连接关系："
                    f"{product.connection_structure or '只按产品图可见连接'}"
                ),
                forbid=("删除", "复制", "换层", "新增第二颗"),
                qc_question=(
                    f"现有 1 颗主吊坠是否仍位于第 {product.pendant_layer} 层，"
                    "并保持产品图中的位置、朝向和肉眼可见连接关系"
                ),
            )
        )
        detected_keywords.append("吊坠")
    constraints = ProductFidelityConstraints(
        schema_version=2,
        source=source,
        detected_keywords=tuple(detected_keywords),
        must_keep=tuple(must_keep),
        must_not_change=_non_ring_must_not_change(product),
        needs_user_review=bool(must_keep),
        detail_crop_recommended=bool(must_keep),
        review_status="pending" if must_keep else "not_applicable",
        pendant_semantics=semantics,
    )
    return validate_product_fidelity_constraints(product, constraints)
```

`_extract_non_pendant_necklace_items()` 不得调用吊坠 rule，也不得根据文本决定 `PendantSemantics`。它只保留非吊坠细节，并用 `_contains_pendant_term()` 防止完整源句污染 absent canonical：

```python
_PENDANT_SENSITIVE_TERMS = ("主吊坠", "吊坠", "链坠", "流苏", "坠子")


def _contains_pendant_term(text: str) -> bool:
    return any(term in text for term in _PENDANT_SENSITIVE_TERMS)


def _without_pendant_terms(text: str) -> str:
    result = text
    for term in _PENDANT_SENSITIVE_TERMS:
        result = result.replace(term, "垂饰")
    return result


def _extract_non_pendant_necklace_items(
    product: ProductAnalysis,
) -> tuple[list[MustKeepConstraint], list[str]]:
    text = _constraint_source_text(product)
    must_keep: list[MustKeepConstraint] = []
    detected_keywords: list[str] = []
    for rule in KEYWORD_RULES:
        if rule.normalized == "吊坠":
            continue
        matched_alias = _first_matching_alias(text, rule.aliases)
        if matched_alias is None:
            continue
        source_text = _source_text_for_alias(product, matched_alias)
        if _contains_pendant_term(source_text):
            source_text = matched_alias
        detected_keywords.append(rule.normalized)
        must_keep.append(
            MustKeepConstraint(
                name=_constraint_name(rule.normalized, matched_alias),
                source_text=source_text,
                normalized_keyword=rule.normalized,
                location=_infer_location(source_text, matched_alias),
                visual_shape=_without_pendant_terms(rule.visual_shape),
                relationship=_without_pendant_terms(rule.relationship),
                forbid=tuple(_without_pendant_terms(text) for text in rule.forbid),
                qc_question=_without_pendant_terms(rule.qc_question),
            )
        )
    return must_keep, detected_keywords
```

在 `_build_necklace_v2_fidelity_constraints()` 开头对带链吊坠要求 `product.pendant_count == 1`；不满足时抛出“第一阶段只支持 1 颗主吊坠”，不能静默把 analysis 的 2 改成 canonical 的 1。

- [ ] **Step 7: 实现统一 v2 结构和字段路径校验**

把 `_iter_constraint_semantic_fields()` 的路径改为精确索引，不改变字段全集：

```python
for index, keyword in enumerate(constraints.detected_keywords):
    yield f"detected_keywords[{index}]", keyword
for index, text in enumerate(constraints.must_not_change):
    yield f"must_not_change[{index}]", text
for item_index, item in enumerate(constraints.must_keep):
    prefix = f"must_keep[{item_index}]"
    yield f"{prefix}.name", item.name
    yield f"{prefix}.source_text", item.source_text
    yield f"{prefix}.normalized_keyword", item.normalized_keyword
    yield f"{prefix}.location", item.location
    yield f"{prefix}.visual_shape", item.visual_shape
    yield f"{prefix}.relationship", item.relationship
    for forbid_index, text in enumerate(item.forbid):
        yield f"{prefix}.forbid[{forbid_index}]", text
    yield f"{prefix}.qc_question", item.qc_question
```

新增 `_validate_v2_pendant_semantics(product, constraints)` 并在 SHA 校验之后、旧词法逻辑之前调用。行为必须精确为：

```python
if constraints.schema_version != 2 or constraints.pendant_semantics is None:
    raise ValueError(
        "历史 v1 只读，不得用于新的项链决策或生成；请新建 run 并重新执行 prepare-review"
    )
expected = (
    PendantSemantics("present", 1, product.pendant_layer, "forbid")
    if product.normalized_product_type is ProductType.PENDANT_NECKLACE
    else PendantSemantics("absent", 0, None, "forbid")
)
if constraints.pendant_semantics != expected:
    raise ValueError(
        "吊坠结构冲突："
        f"analysis={product.normalized_product_type.value}/{product.has_pendant}/"
        f"{product.pendant_layer}，canonical={constraints.pendant_semantics.to_dict()}；"
        "请新建 run 并重新执行 prepare-review"
    )
```

当 `presence=absent`，逐项执行纯字符串包含检查，发现第一个敏感词立即报告字段路径；不得调用 `_has_positive_pendant_semantics()`：

```python
for field_path, text in _iter_constraint_semantic_fields(constraints):
    for term in ("吊坠", "主吊坠", "链坠", "流苏", "坠子"):
        if term in text:
            raise ValueError(
                f"v2 无吊坠 canonical 的 {field_path} 不得包含敏感词：{term}"
            )
```

当 `presence=present`，要求有且只有一项 `normalized_keyword` 属于敏感词集合的主吊坠 `must_keep`，且它的 `relationship` 包含 `第 N 层`；模型已经保证其他可追溯字段非空。历史 `_has_positive_pendant_semantics()` 只保留给 v1 兼容测试，不再参与新项链 correctness gate。

- [ ] **Step 8: 修订旧 I1 测试的版本语义而不删除攻击样例**

`tests/test_final_necklace_important_fixes.py` 中针对普通项链的旧词法极性用例改为两组：

1. builder 断言新项链输出 v2，且上述复合否定文本不会进入任何 canonical 自由文本；
2. 手工把任一吊坠词写入 absent v2 时一律拒绝，不再断言“禁止新增吊坠”可以留在 canonical。

保留原复合句参数集作为回归输入，断言它们无法改变结构化 `presence=absent`，而不是继续扩大 NLP 极性闭集。

- [ ] **Step 9: 运行 GREEN 与 I1 聚焦回归**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_final_necklace_important_fixes.py -k "pendant or canonical or run04" -v
```

Expected: 全部 PASS；输出中没有真实 provider 调用。

- [ ] **Step 10: Task 2 双阶段复审**

规格审查逐项确认：contract 只读规范 analysis；absent 字段全集和五个词全部覆盖；present 可追溯；冲突错误含 analysis、canonical 和 `prepare-review`。质量审查确认不再把词法极性作为 v2 正确性 gate，且 bracelet/ring v1 builder 未改变。修复全部 Critical/Important 后重跑 Step 9。

---

### Task 3: record-decision 与 generation 生命周期门禁

**Files:**
- Modify: `src/jewelry_on_hand/review_decision.py:83`
- Modify: `src/jewelry_on_hand/generation.py:52`
- Modify: `src/jewelry_on_hand/cli.py:385`
- Modify: `tests/test_review_decision.py:720`
- Modify: `tests/test_generation.py`
- Modify: `tests/test_cli.py:868`
- Modify: `tests/test_final_necklace_important_fixes.py:429`

**Interfaces:**
- Consumes: Task 2 的 `validate_product_fidelity_constraints()`；现有 analysis SHA、`ProductConfirmationSnapshot`、canonical 相对路径和原子事务。
- Produces: 新项链 v1/冲突 v2 在任何文件替换、generation 目录创建或 helper 调用前失败；合法 v2 到达本地 fake helper。

- [ ] **Step 1: 编写 record-decision 在任何替换前拒绝 v1 的 RED 测试**

在 `tests/test_review_decision.py` 复用现有 `_constraints_data`、run path 和 monkeypatch 事务测试模式，新增：

```python
def test_necklace_review_bundle_rejects_v1_before_any_replace(
    tmp_path, monkeypatch
) -> None:
    paths = RunPaths.create(tmp_path, "necklace-v1-rejected")
    analysis_data = _necklace_analysis_data()
    write_json(paths.analysis_dir / "product_analysis.json", analysis_data)
    imported_path = paths.review_dir / "legacy-v1-constraints.json"
    legacy = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis_data)
    ).to_dict()
    legacy["schema_version"] = 1
    legacy.pop("pendant_semantics")
    legacy["review_status"] = "pending"
    write_json(imported_path, legacy)
    decision_data = {
        "action": "generate_rank_1",
        "fidelity_confirmed": True,
        "fidelity_constraints_path": "review/legacy-v1-constraints.json",
        "confirmation_snapshot": _confirmation_snapshot(),
    }
    replaced: list[object] = []
    monkeypatch.setattr("jewelry_on_hand.review_decision.os.replace", lambda *args: replaced.append(args))

    with pytest.raises(ReviewGateError, match="历史 v1 只读.*prepare-review"):
        write_review_bundle(paths, decision_data)

    assert replaced == []
    assert not (paths.review_dir / "review_decision.json").exists()
```

同时修订 `tests/test_review_decision.py::_constraints_data()`：当传入 `analysis_data` 时，除现有摘要、must_keep 和 must_not_change 外，还复制 builder 的 `schema_version`，并在 builder 为 v2 时复制 `pendant_semantics`；未传 analysis 的历史 bracelet fixture 保持 v1。这样测试工厂不会把 v2 builder 结果错误包装成 v1。

在 `tests/test_cli.py::make_constraints()` 使用同一规则复制 builder 的版本和结构对象，并增加 CLI 级断言：

```python
def test_record_decision_cli_rejects_legacy_v1_necklace_without_writing(
    tmp_path, capsys
) -> None:
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "legacy-v1-necklace"
    analysis_path = run_root / "analysis" / "product_analysis.json"
    analysis = make_modern_analysis(
        analysis_path,
        product_type="普通项链",
        detected_product_type="necklace",
        confirmed_product_type="necklace",
        classification_confidence="high",
        classification_evidence=["同一条双圈长链"],
        classification_source="manual_override",
        layer_count=2,
        length_category="long",
        visible_appearance="同一条海蓝宝长链绕颈形成上下双圈",
    )
    imported_path = run_root / "review" / "legacy-v1.json"
    legacy = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis)
    ).to_dict()
    legacy["schema_version"] = 1
    legacy.pop("pendant_semantics")
    write_json(imported_path, legacy)
    before = analysis_path.read_bytes()

    result = main([
        "record-decision",
        "--run-root", str(run_root),
        "--action", "generate_rank_1",
        "--fidelity-confirmed",
        "--fidelity-constraints-path", str(imported_path),
    ])

    assert result != 0
    assert "历史 v1 只读" in capsys.readouterr().err
    assert analysis_path.read_bytes() == before
    assert not (run_root / "review" / "review_decision.json").exists()
    assert not (run_root / "analysis" / "product_fidelity_constraints.json").exists()
```

- [ ] **Step 2: 编写 generation v1/冲突 v2 helper=0 的 RED 测试**

在 `tests/test_generation.py` 复用 fake helper 计数方式：

```python
@pytest.mark.parametrize("canonical_kind", ["v1", "wrong_presence", "wrong_layer"])
def test_generation_rejects_invalid_necklace_canonical_before_helper(
    tmp_path, monkeypatch, canonical_kind
) -> None:
    product_type = "pendant_necklace" if canonical_kind == "wrong_layer" else "necklace"
    paths, product_image, _review_copy = _ready_modern_run(
        tmp_path,
        product_type=product_type,
    )
    analysis_path = paths.analysis_dir / "product_analysis.json"
    analysis = read_json(analysis_path)
    if canonical_kind == "wrong_layer":
        analysis["layer_count"] = 2
        analysis["pendant_layer"] = 2
        write_json(analysis_path, analysis)
        decision = read_json(paths.review_dir / "review_decision.json")
        decision["confirmation_snapshot"] = _snapshot_from_analysis(analysis)
        write_json(paths.review_dir / "review_decision.json", decision)
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    canonical = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis)
    ).to_dict()
    canonical["review_status"] = "confirmed"
    if canonical_kind == "v1":
        canonical["schema_version"] = 1
        canonical.pop("pendant_semantics")
    elif canonical_kind == "wrong_presence":
        canonical["pendant_semantics"] = {
            "presence": "present",
            "count": 1,
            "layer": 1,
            "creation_policy": "forbid",
        }
    else:
        canonical["pendant_semantics"]["layer"] = 1
    write_json(canonical_path, canonical)
    helper_calls: list[list[str]] = []
    monkeypatch.setattr(
        "jewelry_on_hand.generation._run_helper",
        lambda command, **kwargs: helper_calls.append(command),
    )

    with pytest.raises((ReviewGateError, GenerationError, ValueError), match="v1|吊坠结构冲突"):
        run_generation(paths, product_image, {1: "本地测试 Prompt"}, HELPER)

    assert helper_calls == []
    assert not any(paths.generation_dir.iterdir())
```

`wrong_layer` 使用带链吊坠 analysis 且 canonical layer 与 analysis 不同；`wrong_presence` 使用普通项链 analysis 且 canonical present。

- [ ] **Step 3: 编写合法 v2 到达 fake helper 的 GREEN 目标测试**

```python
def test_generation_accepts_valid_v2_necklace_until_fake_helper(
    tmp_path, monkeypatch
) -> None:
    paths, product_image, _review_copy = _ready_modern_run(tmp_path)
    commands: list[list[str]] = []

    def fake_helper(command, **kwargs):
        commands.append(command)
        return {"task_id": "local-test-task"}

    monkeypatch.setattr("jewelry_on_hand.generation._run_helper", fake_helper)
    monkeypatch.setattr("jewelry_on_hand.generation._download_result_image", lambda *a, **k: None)

    run_generation(paths, product_image, {1: "本地测试 Prompt"}, HELPER, wait=False)

    assert len(commands) == 1
```

- [ ] **Step 4: 运行生命周期测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_review_decision.py tests/test_generation.py tests/test_cli.py -k "v1 or v2 or canonical or necklace" -v
```

Expected: v1 仍可能越过模型读取或错误发生在过晚阶段，至少一个新增断言失败。

- [ ] **Step 5: 在现有事务与生成入口复用唯一校验，不建立第二套规则**

`write_review_bundle()` 必须保持顺序：解析最终 analysis → 校验 decision/snapshot → 读取导入 canonical → 校验 SHA 与 v2 结构 → 形成 payload → `_commit_json_transaction()`。不要在事务后补校验。

`require_generation_decision()` 保持顺序：读取 decision → 校验 snapshot → 读取 canonical → `require_confirmed_constraints()` → `validate_product_fidelity_constraints()` → 返回 decision。

`run_generation()` 在 `_prepare_generation_dir()` 之前已经调用 `require_generation_decision()`；新增显式注释并确保不存在绕过该入口的项链 helper 路径。CLI `_generate()` 的二次校验继续保留，使直接 API 与 CLI 都 fail closed。

v1 错误统一为：

```python
"历史 v1 只读，不得用于新的项链决策或生成；请新建 run 并重新执行 prepare-review"
```

不得为兼容旧 run 增加自动 `pendant_semantics` 推断、schema 改写或摘要重绑。

- [ ] **Step 6: 保留 I2-I4 生命周期回归**

Run:

```powershell
uv run pytest tests/test_final_necklace_important_fixes.py -k "length or correction or reference or unknown or digest or policy" -v
```

Expected: prepare 前纠正重评分、晚期适配字段拒绝、null length correction-only、unknown 正向纠正、最终参考图路径/摘要/策略复核全部 PASS。

- [ ] **Step 7: 运行 Task 3 GREEN**

Run:

```powershell
uv run pytest tests/test_review_decision.py tests/test_generation.py tests/test_cli.py tests/test_final_necklace_important_fixes.py -v
```

Expected: 全部 PASS；fake helper 之外没有网络调用；非法 canonical 的 helper_calls 为 0。

- [ ] **Step 8: Task 3 双阶段复审**

规格审查确认所有失败发生在 `os.replace`、generation 目录和 provider 调用之前，并确认复制历史 v1 到新 run 不能绕过。质量审查确认复用 Task 2 validator、无重复词法逻辑、原子回滚不退化。修复全部 Critical/Important 并重跑 Steps 6-7。

---

### Task 4: 结构化 Prompt、QC 与便携 validator

**Files:**
- Modify: `src/jewelry_on_hand/prompt_builder.py:22`
- Modify: `src/jewelry_on_hand/category_policies/necklace.py:31`
- Modify: `src/jewelry_on_hand/qc.py:34`
- Modify: `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py:566`
- Modify: `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py:398`
- Modify: `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py:385`
- Modify: `tests/test_prompt_builder.py:520`
- Modify: `tests/test_qc.py:153`
- Modify: `tests/test_product_fidelity_v2.py`
- Modify: `tests/test_skill_portability.py:427`
- Modify: `tests/test_final_necklace_important_fixes.py:545`

**Interfaces:**
- Consumes: 最终 `ProductAnalysis` 与已通过 Task 2 校验的 v2 canonical。
- Produces: 普通项链固定“主吊坠：无/禁止新增”段、带链吊坠固定 presence/count/layer 段；QC 精确检查结构化事实；inspector 对 v1 输出 `legacy_read_only=true` 并且不改写文件。

- [ ] **Step 1: 编写 Prompt 结构来源 RED 测试**

在 `tests/test_prompt_builder.py` 将项链 helper 默认改为 `build_product_fidelity_constraints(product)` 返回的 v2；新增：

```python
def test_plain_necklace_v2_prompt_renders_structured_absent_contract() -> None:
    product = _necklace_product(
        visible_appearance="同一条海蓝宝长链绕颈形成上下双圈，不是两件项链",
        layer_count=2,
    )
    constraints = build_product_fidelity_constraints(product)

    prompt = build_generation_prompt(product, _scored(_row()), constraints)

    assert "主吊坠：无。" in prompt
    assert "禁止新增、补造、复制、悬挂化吊坠" in prompt
    assert "三圈吊坠" not in prompt


def test_pendant_necklace_v2_prompt_renders_exact_count_and_layer() -> None:
    product = _necklace_product(product_type=ProductType.PENDANT_NECKLACE, layer_count=2)
    constraints = build_product_fidelity_constraints(product)

    prompt = build_generation_prompt(product, _scored(_row()), constraints)

    assert "主吊坠：有；数量：1；所属层：第 2 层。" in prompt
    assert "禁止删除、复制、换层或新增第二颗吊坠" in prompt
```

再构造一个 analysis=普通项链、canonical=present 的冲突对象，断言 `build_generation_prompt()` 在输出任何 prompt 前调用 Task 2 validator 并失败；测试不得 monkeypatch `_has_positive_pendant_semantics()`，以证明 v2 不依赖它。

把 `tests/test_prompt_builder.py` 中所有项链/带链吊坠 `build_prompt()` 或 `build_generation_prompt()` 调用改为显式传入 `build_product_fidelity_constraints(product)`；bracelet/ring 调用保持不变。现有“两颗吊坠”用例改成第一阶段唯一合法的 `pendant_count=1`，并断言新的单颗数量/所属层文案；三层普通项链测试保留 `layer_count=3`，但仍使用 `presence=absent`，它只证明层数兼容，不代表三圈吊坠商品存在。新增无 canonical 失败测试：

```python
def test_new_necklace_prompt_rejects_missing_v2_canonical() -> None:
    product = _necklace_product()
    with pytest.raises(ValueError, match="v2 canonical"):
        build_generation_prompt(product, _scored(_row()))
```

- [ ] **Step 2: 运行 Prompt 测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_prompt_builder.py -k "v2_prompt or pendant_necklace or plain_necklace" -v
```

Expected: 当前品类策略仅按 analysis 渲染且不消费 v2 canonical，新增精确文案或冲突 gate 失败。

- [ ] **Step 3: 从品类策略移除 analysis-only 吊坠段并在 prompt_builder 结构化渲染**

`category_policies/necklace.py::_build_necklace_prompt_fragments()` 继续输出层数、长度、链型、顺序、展示模式和物理规则，但删除 `if product.has_pendant` 的整段吊坠存在性渲染。

`prompt_builder.py` 新增：

```python
def _pendant_semantics_lines(
    product: ProductAnalysis,
    constraints: ProductFidelityConstraints,
) -> str:
    validate_product_fidelity_constraints(product, constraints)
    semantics = constraints.pendant_semantics
    assert semantics is not None
    if semantics.presence == "absent":
        return (
            "主吊坠：无。\n"
            "禁止新增、补造、复制、悬挂化吊坠，也不得把珠子、跑环或其他元件改成吊坠。"
        )
    assert semantics.layer is not None
    return (
        f"主吊坠：有；数量：{semantics.count}；所属层：第 {semantics.layer} 层。\n"
        "保持肉眼可见的位置、朝向与连接关系；"
        "禁止删除、复制、换层或新增第二颗吊坠。"
    )
```

只有 product 是 `necklace/pendant_necklace` 时在【品类保真】插入该段；bracelet/ring 保持现有 Prompt。新项链未传 canonical 时抛出“新项链 Prompt 必须提供已校验的 v2 canonical”，不能回退到 analysis-only 推断。

- [ ] **Step 4: 编写 QC presence/count/layer RED 测试**

在 `tests/test_product_fidelity_v2.py` 复用 Task 2 已定义的 `_necklace_analysis()`，扩展 `build_qc_checklist()` 测试：

```python
from jewelry_on_hand.qc import build_qc_checklist


def test_qc_checklist_uses_absent_v2_contract_for_double_loop_plain_necklace() -> None:
    product = _necklace_analysis(layer_count=2)
    constraints = build_product_fidelity_constraints(product)

    checklist = build_qc_checklist(
        product.normalized_product_type,
        product.display_mode,
        constraints.must_keep,
        product_analysis=product,
        fidelity_constraints=constraints,
    )

    assert "主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠" in checklist
    assert all("第 3 层吊坠" not in question for question in checklist)


def test_qc_checklist_uses_present_v2_count_and_layer() -> None:
    product = _necklace_analysis(pendant=True, layer_count=2)
    constraints = build_product_fidelity_constraints(product)

    checklist = build_qc_checklist(
        product.normalized_product_type,
        product.display_mode,
        constraints.must_keep,
        product_analysis=product,
        fidelity_constraints=constraints,
    )

    assert "现有主吊坠数量是否为 1，且仍位于第 2 层并保持原连接关系" in checklist
```

- [ ] **Step 5: 运行 QC 测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_qc.py -k "v2_contract or count_and_layer or double_loop" -v
```

Expected: 当前 `build_qc_checklist()` 没有结构化参数，测试因签名或缺少精确问题失败。

- [ ] **Step 6: 最小扩展 QC 接口并保持旧调用兼容**

扩展函数签名：

```python
def build_qc_checklist(
    product_type: ProductType,
    display_mode: DisplayMode,
    must_keep: Iterable[MustKeepConstraint] = (),
    *,
    product_analysis: ProductAnalysis | None = None,
    fidelity_constraints: ProductFidelityConstraints | None = None,
) -> tuple[str, ...]:
```

当 product_type 是两类项链且传入标准 runtime 的两个 keyword-only 参数时，要求二者同时存在，先调用 Task 2 validator，再追加且仅追加一个结构化吊坠问题；无标准 runtime context 的旧直接调用保持现有通用 checklist，不伪造结构事实：

```python
if semantics.presence == "absent":
    pendant_question = "主吊坠应为无，且没有新增、补造、复制或悬挂化吊坠"
else:
    pendant_question = (
        f"现有主吊坠数量是否为 {semantics.count}，"
        f"且仍位于第 {semantics.layer} 层并保持原连接关系"
    )
```

`write_qc_result()` 从标准 runtime context 调用时传入 analysis 与 constraints。legacy bracelet 和无标准 context 的旧 QC 保持现有签名和宽松边界。

- [ ] **Step 7: 编写便携 inspector/Prompt/QC validator 的 v1/v2 RED 测试**

在 `tests/test_skill_portability.py` 增加三个独立用例：

1. 复制代表性历史 v1 项链 run 到 `tmp_path`，运行 inspector，断言退出 0、stdout 含 `legacy_read_only=true`，并比较运行前后所有 JSON 的 SHA-256 不变；
2. 构造合法 v2 普通项链 run，断言 inspector 与 Prompt validator 退出 0、stdout 含 `legacy_read_only=false`；
3. 构造 v2 带链吊坠 QC，checklist 精确包含 count=1/layer=2 时通过，改成 layer=1 时 QC validator 非零。

核心断言：

```python
before = {path: path.read_bytes() for path in run_root.rglob("*.json")}
result = subprocess.run(
    [sys.executable, str(INSPECTOR), str(run_root)],
    text=True,
    capture_output=True,
    check=False,
)
after = {path: path.read_bytes() for path in run_root.rglob("*.json")}
assert result.returncode == 0
assert "legacy_read_only=true" in result.stdout
assert after == before
```

- [ ] **Step 8: 运行便携测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_skill_portability.py -k "legacy_read_only or structured_pendant or v2" -v
```

Expected: inspector 尚不读取 canonical schema，也不输出只读标记；QC validator 尚未重建结构化吊坠问题，新增测试失败。

- [ ] **Step 9: 实现三个便携脚本的独立 v1/v2 逻辑**

`inspect_run_artifacts.py` 不导入项目包；新增 `_validate_fidelity_constraints_data(analysis, constraints) -> tuple[list[str], bool]`：

- schema=1 返回 `([], True)`，仅用于读取/检查，不改写文件；
- schema=2 严格校验 `pendant_semantics` 类型、presence/count/layer/policy、analysis 对照和 absent 字段路径敏感词；
- 其他版本返回中文错误；
- `main()` 成功时在“run 产物检查通过”后输出 `legacy_read_only=true|false`。

`validate_prompt_contract.py` 将普通项链固定要求更新为“主吊坠：无。”和完整禁止创建句；带链吊坠要求解析并验证“数量：1”和“所属层：第 1/2/3 层”，但不假设现实存在三圈商品。

`validate_qc_record.py::_expected_runtime_checklist_for_qc()` 读取 schema：v1 继续按历史 `must_keep` 和原品类 checklist；v2 先验证 analysis/canonical 对照，再按 presence 追加与核心 `qc.py` 完全相同的唯一问题。为避免漂移，两个文件把两条固定中文问题定义为同名常量；便携脚本不能导入 package。

- [ ] **Step 10: 运行 Task 4 GREEN 与原双圈附件事实回归**

Run:

```powershell
uv run pytest tests/test_prompt_builder.py tests/test_qc.py tests/test_skill_portability.py tests/test_final_necklace_important_fixes.py -v
```

Expected: 全部 PASS；普通双圈项链始终是 `layer_count=2 + pendant absent`，没有任何三圈吊坠产品或 proof 断言。

- [ ] **Step 11: Task 4 双阶段复审**

规格审查确认 Prompt/QC 只从 v2 + 最终 analysis 渲染、v1 inspector 只读且字节不变、普通双圈没有被建模成两件项链/吊坠/三圈商品。质量审查确认核心和便携固定文案一致、旧 bracelet/ring Prompt/QC 未改变、validator 无网络/包依赖。修复全部 Critical/Important 并重跑 Step 10。

---

### Task 5: 全文文档协调、全量验证与最终独立复审

**Files:**
- Modify: `reference/product-fidelity-constraints-schema.md`
- Modify: `reference/manual-workflow.md`
- Modify: `reference/review-decision-schema.md`
- Modify: `reference/qc-checklist.md`
- Modify: `reference/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md`
- Modify: `skills/jewelry-on-hand-workflow/SKILL.md`
- Modify: `skills/jewelry-on-hand-workflow/references/workflow.md`
- Modify: `skills/jewelry-on-hand-workflow/references/prompt-contract.md`
- Modify: `skills/jewelry-on-hand-workflow/references/qc-checklist.md`
- Modify: `skills/jewelry-on-hand-workflow/references/troubleshooting.md`
- Modify: `tests/test_skill_portability.py`
- Create: `output/final-verification/2026-07-14/README.md`
- Create: `output/final-verification/2026-07-14/*.stdout.txt`
- Create: `output/final-verification/2026-07-14/*.stderr.txt`
- Create: `output/final-verification/2026-07-14/*.exitcode.txt`
- Create: `output/final-verification/2026-07-14/final-code-review.md`

**Interfaces:**
- Consumes: Tasks 1-4 的实际行为和测试结果。
- Produces: 无前后矛盾的 v1/v2 操作契约、可复核的全量测试证据、I1 关闭结论；明确 I5/HERO 仍未关闭。

- [ ] **Step 1: 先写文档契约失败测试**

在 `tests/test_skill_portability.py` 增加参数化测试，逐文件断言以下事实，不只检查末尾新增段：

```python
@pytest.mark.parametrize(
    "document",
    [
        Path("reference/product-fidelity-constraints-schema.md"),
        Path("reference/manual-workflow.md"),
        Path("reference/review-decision-schema.md"),
        Path("skills/jewelry-on-hand-workflow/SKILL.md"),
        Path("skills/jewelry-on-hand-workflow/references/workflow.md"),
        Path("skills/jewelry-on-hand-workflow/references/troubleshooting.md"),
    ],
)
def test_operator_documents_describe_v2_and_v1_read_only_boundary(document: Path) -> None:
    text = document.read_text(encoding="utf-8")
    assert "schema_version=2" in text
    assert "pendant_semantics" in text
    assert "历史 v1" in text
    assert "只读" in text
    assert "重新执行 `prepare-review`" in text or "重新执行 prepare-review" in text
    assert "历史 v1 会自动升级为 v2" not in text
```

另外解析 `reference/product-fidelity-constraints-schema.md` 中的所有 fenced JSON，断言 v2 示例可由 `ProductFidelityConstraints.from_dict()` 解析，v1 示例保持不含 `pendant_semantics`。

- [ ] **Step 2: 运行文档测试并确认 RED**

Run:

```powershell
uv run pytest tests/test_skill_portability.py -k "v2_and_v1_read_only or schema_json" -v
```

Expected: 现有文档仍声明 schema 固定为 1，新增断言失败。

- [ ] **Step 3: 全文修订 schema、流程、决策、Prompt、QC 和 troubleshooting**

逐章替换旧“当前固定为 1”“项链可继续 v1 生成”等现行表述，至少包含：

- v1 顶层字段、只读允许范围和禁止进入新项链 record-decision/generate；
- v2 顶层完整 JSON、普通项链和带链吊坠各一个可解析示例；
- absent 自由文本字段全集和五个敏感词；
- `creation_policy=forbid` 替代 canonical 中“禁止新增吊坠”自由文本；
- `prepare-review` 在最终纠正后构建 v2；
- record-decision 和 generate 在写文件/helper 前的交叉校验与中文修复动作；
- Prompt/QC 的精确结构化文案；
- 历史 v1 inspector/QC 只读，不自动升级；
- 双圈附件是同一条长链、无吊坠，不是两件项链；1 至 3 层是运行时能力，不代表存在三圈吊坠商品；
- I5 成功 proof 和 HERO 不属于本 v2 交付。

不得在文档末尾追加“以本节为准”；必须修改原字段表、示例、生命周期和错误处理章节，使全文只有一个现行规则。

- [ ] **Step 4: 运行文档与便携 GREEN**

Run:

```powershell
uv run pytest tests/test_skill_portability.py -v
```

Expected: 全部 PASS，所有 Markdown/脚本按 UTF-8 读取。

- [ ] **Step 5: 运行聚焦测试并保存三件套证据**

先用 `apply_patch` 创建 `output/final-verification/2026-07-14/README.md`：

```markdown
# 产品保真 v2 最终验证

- 日期：2026-07-14
- 范围：结构化吊坠语义 v2（I1）
- 不在范围：I5 真实双圈成功 proof、HERO、戒指、飞书
- 证据约定：每个测试组保存 stdout、stderr、exitcode；只有 exitcode=0 且 stderr 为空才记为通过。
- 真实生成：本验证没有提交或查询 provider 任务。
```

在 PowerShell 中执行，不使用会吞掉真实退出码的管道：

```powershell
$dir = "output/final-verification/2026-07-14"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$stdout = Join-Path $dir "pytest-v2-focused.stdout.txt"
$stderr = Join-Path $dir "pytest-v2-focused.stderr.txt"
uv run pytest tests/test_product_fidelity_v2.py tests/test_final_necklace_important_fixes.py tests/test_review_decision.py tests/test_generation.py tests/test_prompt_builder.py tests/test_qc.py tests/test_skill_portability.py -v 1> $stdout 2> $stderr
$LASTEXITCODE | Set-Content -Encoding ASCII (Join-Path $dir "pytest-v2-focused.exitcode.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: exitcode 文件为 `0`；stderr 文件为空；stdout 显示全部 selected tests PASS。

- [ ] **Step 6: 运行 I2-I4、output_role 与 helper UTF-8 回归并保存证据**

```powershell
$dir = "output/final-verification/2026-07-14"
$stdout = Join-Path $dir "pytest-critical-regressions.stdout.txt"
$stderr = Join-Path $dir "pytest-critical-regressions.stderr.txt"
uv run pytest tests/test_final_necklace_important_fixes.py tests/test_output_role_compatibility.py tests/test_generation_helper_utf8.py skills/aireiter-image-generation/tests/test_aireiter_image_helper.py -v 1> $stdout 2> $stderr
$LASTEXITCODE | Set-Content -Encoding ASCII (Join-Path $dir "pytest-critical-regressions.exitcode.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: exitcode `0`，stderr 空，I2-I4、角色兼容和 Windows UTF-8 helper 全部 PASS。

- [ ] **Step 7: 运行全量测试并保存最终证据**

```powershell
$dir = "output/final-verification/2026-07-14"
$stdout = Join-Path $dir "pytest-full.stdout.txt"
$stderr = Join-Path $dir "pytest-full.stderr.txt"
uv run pytest -v 1> $stdout 2> $stderr
$code = $LASTEXITCODE
$code | Set-Content -Encoding ASCII (Join-Path $dir "pytest-full.exitcode.txt")
if ($code -ne 0) { exit $code }
if ((Get-Item $stderr).Length -ne 0) { throw "pytest-full.stderr.txt 非空" }
```

Expected: exitcode `0`、stderr 0 bytes、stdout 最后一行是全量通过摘要；不得沿用 v2 实施前的 `940 passed` 作为证据。

- [ ] **Step 8: 独立最终代码复审**

给独立 reviewer 的输入必须包含：批准的 v2 设计、本文计划、Task 1-4 的完整 diff、三组新鲜测试证据。审查报告保存为 `output/final-verification/2026-07-14/final-code-review.md`，必须分别给出：

1. I1 是否已由结构化契约关闭；
2. v1 是否仅只读且无法进入新项链决策/生成；
3. Prompt/QC 是否不依赖自然语言极性；
4. 所有校验是否发生在文件替换/provider 调用之前；
5. bracelet/ring、I2-I4、output_role、helper UTF-8 是否无回归；
6. I5 与 HERO 仍为开放项，不得算作本 Task 缺失实现。

任何 Critical/Important 发现必须回到对应 Task 以 RED 测试复现、修复、重新聚焦/全量验证并复审；Minor 记录在报告中，不借机修改范围外并发代码。

- [ ] **Step 9: 最终状态核对**

运行：

```powershell
git status --short
git diff --check
rg -n "schema_version.*固定为.*1|自动.*v1.*v2|三圈吊坠.*商品|两件.*双圈" reference skills src tests
```

Expected: `git diff --check` 退出 0；搜索结果只允许出现在历史说明、禁止规则或测试反例中。实现工作树保持未暂存；不得把并发文件带入提交。

## 自审映射

| SPEC 要求 | 计划覆盖 |
| --- | --- |
| v1/v2 模型、round-trip、非法字段 | Task 1 Steps 1-6 |
| 新项链 builder 只读规范 analysis | Task 2 Steps 1-7 |
| absent 字段全集零敏感词 | Task 2 Steps 3、7 |
| present 数量/层/可追溯 must_keep | Task 2 Steps 1、4、7 |
| v1 只读，禁止新决策/生成/自动迁移 | Task 3 Steps 1-5；Task 4 Steps 7-9 |
| 文件替换和 provider 调用前失败 | Task 3 Steps 1-8 |
| v2 Prompt 只从结构化事实渲染 | Task 4 Steps 1-3 |
| v2 QC 与 presence/count/layer 精确一致 | Task 4 Steps 4-6、7-9 |
| inspector/validator 同时接受历史 v1 和 v2 | Task 4 Steps 7-10 |
| 双圈附件事实、无三圈商品伪造 | Global Constraints；Task 4 Steps 1、4、10-11 |
| 文档全文协调、非末尾补丁 | Task 5 Steps 1-4 |
| 聚焦、关键回归、全量和独立复审 | Task 5 Steps 5-9 |

计划中没有自动迁移命令、真实 provider 调用、历史 run 改写、三圈商品 proof、I5/HERO 实现或范围外戒指/飞书改动。
