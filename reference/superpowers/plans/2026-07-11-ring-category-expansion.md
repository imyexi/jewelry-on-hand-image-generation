# 戒指品类端到端扩展实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不回归手串、项链、带链吊坠与历史 run 的前提下，让统一珠宝上手图工作流支持单枚常规戒指的真人佩戴图生成。

**Architecture:** 继续复用现有 `prepare-review → record-decision → generate → qc` 四阶段流程，将戒指输入限制、结构校验、参考图适配、Prompt 片段与 QC 清单封装为独立品类策略。飞书多维表格继续作为默认生产参考源；本地 Excel 仅保留显式 `--classification` 兼容路径，不形成第二套业务规则。

**Tech Stack:** Python 3.11+、frozen dataclass、`str, Enum`、标准库 `argparse/json/pathlib`、pytest、飞书 `lark-cli base`、现有 AIReiter 生成助手。

## Global Constraints

- 所有思考、代码注释、CLI 文案、错误信息和文档使用中文；枚举值、JSON 字段和代码标识符使用本计划定义的英文规范值。
- 所有参考文档和流程 `.md` 文件放在 `reference/`；所有 pytest 临时目录、缓存、日志与真实生成证据放在 `output/`，不得新增根目录测试产物。
- 默认生产参考源是飞书 Base `AI生图参考图素材库` 的 `素材收录池`；只有显式传入 `--classification <xlsx>` 时才读取本地 Excel。
- 第一版只支持单枚常规指根戒指：`ring_count=1`、`ring_wear_style=finger_base`、输入 `worn_source`、输出 `worn`。
- 支持闭口戒、开口戒、素圈戒、单主石或有明确戒面的单枚戒指；不支持多枚套装、叠戴、跨指戒、指关节戒、手持展示和白底/平铺输入。
- 默认保持产品原图识别并人工确认后的左右手与佩戴手指；生成时禁止静默换手或换指。
- 产品原图是戒指身份唯一来源；禁止迁移产品原图中的手、皮肤、指甲、掌纹、衣物、人物或背景局部。
- 不可见戒圈背面、镶嵌背面和连接结构只能记录为不确定项，不得在分析或 Prompt 中描述成确定事实。
- 当前工作区已有项链/吊坠和飞书参考源未提交改动；实施时只能增量编辑，不得回退、覆盖或顺带提交无关文件。

---

## 文件结构与接口决策

**新增文件**

- `src/jewelry_on_hand/ring_attributes.py`：定义 `HandSide`、`FingerPosition`、`RingWearStyle` 及中文显示名。
- `src/jewelry_on_hand/category_policies/ring.py`：戒指生成校验、参考图适配、Prompt 片段和 QC 清单。
- `tests/test_ring_attributes.py`：戒指规范枚举与非法值测试。

**重点修改文件**

- `product_types.py`、`display_modes.py`、`models.py`：增加 `ring` 品类和戒指分析/快照字段。
- `feishu_reference_source.py`、`reference_catalog.py`：读写戒指参考图结构化字段，保持 Excel 显式兼容。
- `scoring.py`、`prompt_builder.py`、`qc.py`：通过品类策略接入戒指，不增加平行流程。
- `review_package.py`、`review_decision.py`、`cli.py`、`generation.py`：人工确认、快照一致性和模型提交前硬 gate。
- `skills/jewelry-on-hand-workflow/` 与 `reference/*.md`：全文修订现行契约，避免“仅支持原品类”等矛盾表述。

**新增公共接口**

```python
class ProductType(str, Enum):
    RING = "ring"

class HandSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"

class FingerPosition(str, Enum):
    THUMB = "thumb"
    INDEX = "index"
    MIDDLE = "middle"
    RING = "ring"
    LITTLE = "little"
    UNKNOWN = "unknown"

class RingWearStyle(str, Enum):
    FINGER_BASE = "finger_base"
    MIDI = "midi"
    CROSS_FINGER = "cross_finger"
    UNKNOWN = "unknown"
```

`ProductAnalysis` 与 `ProductConfirmationSnapshot` 同名新增字段：

```python
ring_count: int
hand_side: HandSide
finger_position: FingerPosition
ring_wear_style: RingWearStyle
```

现代戒指分析 JSON 必须显式提供四个字段；其他品类缺省为 `ring_count=0`、三个枚举均为 `unknown`。戒指仍保留公共 `layer_count=1`、`has_pendant=false`、`pendant_count=0`、`is_independent_multi_item=false`，以保持统一快照和旧接口稳定。

`ReferenceRow` 新增六个字符串字段：

```python
hand_side: str = ""
visible_fingers: str = ""
hand_orientation: str = ""
ring_face_visibility: str = ""
finger_separation: str = ""
finger_occlusion_risk: str = ""
```

对应飞书字段依次为：`左右手`、`可见手指`、`手部朝向`、`戒面可见度`、`手指分离度`、`手指遮挡风险`。

---

### Task 1: 建立戒指规范枚举与品类入口

**Files:**
- Create: `src/jewelry_on_hand/ring_attributes.py`
- Modify: `src/jewelry_on_hand/product_types.py`
- Modify: `src/jewelry_on_hand/display_modes.py`
- Test: `tests/test_ring_attributes.py`
- Test: `tests/test_product_types.py`
- Test: `tests/test_display_modes.py`

**Interfaces:**
- Produces: `HandSide`、`FingerPosition`、`RingWearStyle`、`ProductType.RING`。
- Produces: `default_display_mode(ProductType.RING) -> DisplayMode.WORN`。
- Produces: `validate_product_mode(ProductType.RING, DisplayMode.WORN, SourceImageType.WORN_SOURCE) -> None`。

- [ ] **Step 1: 编写枚举和品类归一化失败测试**

```python
def test_ring_aliases_normalize_to_ring():
    assert normalize_product_type("戒指") is ProductType.RING
    assert normalize_product_type("指环") is ProductType.RING
    assert normalize_product_type("ring") is ProductType.RING

def test_ring_attribute_enums_keep_unknown_explicit():
    assert HandSide("unknown") is HandSide.UNKNOWN
    assert FingerPosition("ring") is FingerPosition.RING
    assert RingWearStyle("finger_base") is RingWearStyle.FINGER_BASE
```

- [ ] **Step 2: 运行测试并确认因接口不存在而失败**

Run: `pytest --basetemp output/pytest-ring/task1-red -o cache_dir=output/pytest-ring/cache tests/test_ring_attributes.py tests/test_product_types.py -v`

Expected: FAIL，原因包含 `ring_attributes` 模块或 `ProductType.RING` 不存在。

- [ ] **Step 3: 实现枚举和戒指别名**

`ring_attributes.py` 只定义三个枚举及 `display_name`；`product_types.py` 从 `_UNSUPPORTED_CATEGORY_TERMS` 删除“戒指”，增加精确中文/英文别名。含“疑似戒指”“戒指吗”等不确定文本仍归一化为 `UNKNOWN`。

- [ ] **Step 4: 编写戒指模式矩阵失败测试**

```python
def test_ring_supports_only_worn_from_worn_source():
    validate_product_mode(ProductType.RING, DisplayMode.WORN, SourceImageType.WORN_SOURCE)
    with pytest.raises(ValueError, match="戒指.*手持展示"):
        validate_product_mode(ProductType.RING, DisplayMode.HAND_HELD, SourceImageType.WORN_SOURCE)
    with pytest.raises(ValueError, match="白底或平铺"):
        validate_product_mode(ProductType.RING, DisplayMode.WORN, SourceImageType.FLAT_LAY_SOURCE)
```

- [ ] **Step 5: 将 `ring` 接入 `_SUPPORTED_MODES` 并运行目标测试**

Run: `pytest --basetemp output/pytest-ring/task1-green -o cache_dir=output/pytest-ring/cache tests/test_ring_attributes.py tests/test_product_types.py tests/test_display_modes.py -v`

Expected: PASS。

- [ ] **Step 6: 仅暂存本任务文件并提交**

```powershell
git add src/jewelry_on_hand/ring_attributes.py src/jewelry_on_hand/product_types.py src/jewelry_on_hand/display_modes.py tests/test_ring_attributes.py tests/test_product_types.py tests/test_display_modes.py
git commit -m "feat: 建立戒指品类与规范属性"
```

---

### Task 2: 扩展产品分析模型与确认快照

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/product_analysis.py`
- Modify: `reference/product-analysis-schema.md`
- Modify: `reference/review-decision-schema.md`
- Test: `tests/test_models.py`
- Test: `tests/test_product_analysis.py`
- Test: `tests/test_review_decision.py`

**Interfaces:**
- Consumes: Task 1 的三个戒指枚举与 `ProductType.RING`。
- Produces: 带四个戒指字段的 `ProductAnalysis.from_dict()`、`ProductConfirmationSnapshot.from_analysis()`、`to_dict()`。
- Produces: `ProductAnalysis.is_supported_product()` 对合法 `ring` 返回 `True`。

- [ ] **Step 1: 编写合法戒指分析和非法边界测试**

```python
def ring_analysis_data(**overrides):
    data = modern_analysis_data(
        product_type="戒指",
        detected_product_type="ring",
        confirmed_product_type="ring",
        source_image_type="worn_source",
        display_mode="worn",
        layer_count=1,
        has_pendant=False,
        pendant_count=0,
        is_independent_multi_item=False,
    )
    data.update({
        "ring_count": 1,
        "hand_side": "left",
        "finger_position": "ring",
        "ring_wear_style": "finger_base",
    })
    data.update(overrides)
    return data

def test_ring_analysis_requires_single_confirmed_finger_base_ring():
    analysis = ProductAnalysis.from_dict(ring_analysis_data())
    assert analysis.ring_count == 1
    assert analysis.hand_side is HandSide.LEFT
    assert analysis.finger_position is FingerPosition.RING

@pytest.mark.parametrize("field,value,message", [
    ("ring_count", 2, "只支持单枚戒指"),
    ("hand_side", "unknown", "必须确认左右手"),
    ("finger_position", "unknown", "必须确认佩戴手指"),
    ("ring_wear_style", "midi", "只支持常规指根佩戴"),
])
def test_ring_analysis_rejects_unsupported_boundaries(field, value, message):
    with pytest.raises(ValueError, match=message):
        ProductAnalysis.from_dict(ring_analysis_data(**{field: value}))
```

- [ ] **Step 2: 运行模型测试并确认新增用例失败**

Run: `pytest --basetemp output/pytest-ring/task2-red -o cache_dir=output/pytest-ring/cache tests/test_models.py tests/test_product_analysis.py -v`

Expected: FAIL，原因是 `ProductAnalysis` 尚无戒指字段或仍把 `ring` 视为不支持。

- [ ] **Step 3: 实现模型字段和品类条件校验**

实现规则：

```python
if confirmed is ProductType.RING:
    if self.ring_count != 1:
        raise ValueError("当前版本只支持单枚戒指")
    if self.hand_side is HandSide.UNKNOWN:
        raise ValueError("戒指生成前必须确认左右手")
    if self.finger_position is FingerPosition.UNKNOWN:
        raise ValueError("戒指生成前必须确认佩戴手指")
    if self.ring_wear_style is not RingWearStyle.FINGER_BASE:
        raise ValueError("当前版本只支持常规指根佩戴戒指")
    if self.layer_count != 1 or self.has_pendant or self.pendant_count != 0:
        raise ValueError("戒指不得声明项链层数或吊坠结构")
```

其他品类若显式提供非零 `ring_count` 或非 `unknown` 戒指字段必须拒绝，避免跨品类残留字段被静默忽略。

- [ ] **Step 4: 扩展确认快照完整性测试**

测试戒指快照必须包含四个新字段、`from_analysis()` 保留枚举值、`to_dict()` 输出规范字符串；快照任一字段与最终分析不一致时 `validate_decision_against_analysis()` 必须拒绝。

- [ ] **Step 5: 全文修订两个 Schema 文档**

在现有手串、项链、吊坠契约中加入戒指字段及条件必填规则；删除“戒指属于不支持品类”的现行表述，不在文档末尾孤立追加补丁章节。

- [ ] **Step 6: 运行模型、分析和决策测试**

Run: `pytest --basetemp output/pytest-ring/task2-green -o cache_dir=output/pytest-ring/cache tests/test_models.py tests/test_product_analysis.py tests/test_review_decision.py -v`

Expected: PASS。

- [ ] **Step 7: 仅暂存本任务文件并提交**

```powershell
git add src/jewelry_on_hand/models.py src/jewelry_on_hand/product_analysis.py reference/product-analysis-schema.md reference/review-decision-schema.md tests/test_models.py tests/test_product_analysis.py tests/test_review_decision.py
git commit -m "feat: 增加戒指分析与确认快照"
```

---

### Task 3: 实现戒指品类策略

**Files:**
- Create: `src/jewelry_on_hand/category_policies/ring.py`
- Modify: `src/jewelry_on_hand/category_policies/__init__.py`
- Modify: `src/jewelry_on_hand/category_policies/base.py`
- Test: `tests/test_category_policies.py`

**Interfaces:**
- Produces: `RING_POLICY: CategoryPolicy`。
- Produces: `get_category_policy(ProductType.RING) -> RING_POLICY`。
- Consumes: `ProductAnalysis` 的戒指字段和 `ReferenceRow` 的新参考字段。

- [ ] **Step 1: 编写策略注册和生成边界失败测试**

```python
def test_ring_policy_is_registered_and_worn_only():
    policy = get_category_policy(ProductType.RING)
    assert policy.supported_modes == frozenset({DisplayMode.WORN})
    assert policy.max_layer_count == 1

def test_ring_policy_rejects_multi_item_flag():
    with pytest.raises(ValueError, match="单枚戒指"):
        get_category_policy(ProductType.RING).validate_generation(1, True)
```

- [ ] **Step 2: 运行测试并确认策略不存在**

Run: `pytest --basetemp output/pytest-ring/task3-red -o cache_dir=output/pytest-ring/cache tests/test_category_policies.py -k ring -v`

Expected: FAIL，原因包含 `ProductType.RING` 未注册到 `_POLICIES`。

- [ ] **Step 3: 扩展 `CategoryPolicy.validate_generation()` 的戒指分支**

保持现有签名不变：戒指要求 `layer_count == 1` 且 `is_independent_multi_item is False`。戒指专属的 `ring_count`、指位与佩戴方式由 `ProductAnalysis` 和确认快照校验，避免把大量品类字段塞入公共策略签名。

- [ ] **Step 4: 定义戒指 Prompt 与 QC 常量**

`ring.py` 必须导出以下稳定语义：

```python
RING_IMAGE_ONE_ROLE = "内部图1只提供手部姿势、手模、构图、光线和场景；内部图1中的戒指必须移除且不提供产品身份。"
RING_BASIC_QC_ITEMS = (
    "画面中只有一枚目标戒指",
    "戒指位于确认后的左右手和目标手指根部",
    "戒圈、戒面、主石、镶嵌和装饰排列与产品图可见结构一致",
    "戒圈自然环绕手指且前后遮挡、接触和阴影真实",
    "没有迁移产品图中的手、皮肤、指甲、掌纹或背景局部",
)
```

- [ ] **Step 5: 注册 `RING_POLICY` 并运行策略回归**

Run: `pytest --basetemp output/pytest-ring/task3-green -o cache_dir=output/pytest-ring/cache tests/test_category_policies.py -v`

Expected: PASS，且手串、项链、吊坠既有策略用例不回归。

- [ ] **Step 6: 提交任务文件**

```powershell
git add src/jewelry_on_hand/category_policies/ring.py src/jewelry_on_hand/category_policies/__init__.py src/jewelry_on_hand/category_policies/base.py tests/test_category_policies.py
git commit -m "feat: 增加戒指品类策略"
```

---

### Task 4: 扩展飞书参考源与 Excel 兼容解析

**Files:**
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `src/jewelry_on_hand/feishu_reference_source.py`
- Modify: `src/jewelry_on_hand/reference_catalog.py`
- Modify: `reference/feishu-reference-source.md`
- Test: `tests/test_feishu_reference_source.py`
- Test: `tests/test_reference_catalog.py`

**Interfaces:**
- Produces: `ReferenceRow` 六个戒指参考字段。
- Produces: 飞书字段映射与增量指纹覆盖六个字段。
- 保持: 未传 `--classification` 同步飞书；显式传入 Excel 时走 `load_reference_rows()`。

- [ ] **Step 1: 编写飞书记录映射失败测试**

测试飞书记录：

```python
fields = {
    "适用品类": "ring",
    "适用展示模式": "worn",
    "左右手": "left",
    "可见手指": "thumb,index,middle,ring,little",
    "手部朝向": "back",
    "戒面可见度": "高",
    "手指分离度": "高",
    "手指遮挡风险": "低",
}
```

断言同步缓存、`manifest.json`、`ReferenceRow` 和字段指纹均保留这些值；任一字段变化会使记录重新进入待补齐状态。

- [ ] **Step 2: 编写 Excel 显式兼容测试**

使用临时工作簿写入同名中文列，断言解析一致；缺少六列时使用空字符串，不从“饰品类型=戒指”推断指位或可见度。

- [ ] **Step 3: 运行参考源测试并确认失败**

Run: `pytest --basetemp output/pytest-ring/task4-red -o cache_dir=output/pytest-ring/cache tests/test_feishu_reference_source.py tests/test_reference_catalog.py -v`

Expected: FAIL，原因是六个字段尚未进入模型和映射。

- [ ] **Step 4: 扩展字段常量、缓存和映射**

将六个中文字段加入 `OPTIONAL_REFERENCE_FIELD_NAMES`，从而自动进入 `AI_FIELD_NAMES`、`SOURCE_FIELD_NAMES` 和增量指纹；扩展 `_record_to_reference_row()`、manifest 读写及 Excel 表头别名。

- [ ] **Step 5: 保持飞书优先级测试**

```python
def test_prepare_review_defaults_to_feishu_and_explicit_excel_wins(monkeypatch):
    # 不传 classification 时只调用 sync_and_load_reference_rows。
    # 传 classification 时只调用 load_reference_rows，不访问飞书。
```

- [ ] **Step 6: 全文修订飞书数据源文档**

在通用字段表、增量指纹、补齐 JSON 示例和迁移说明中加入六个戒指字段；明确戒指生产记录必须填满这些字段，Excel 仍是显式历史兼容源。

- [ ] **Step 7: 运行参考源完整测试**

Run: `pytest --basetemp output/pytest-ring/task4-green -o cache_dir=output/pytest-ring/cache tests/test_feishu_reference_source.py tests/test_feishu_enrichment_cli.py tests/test_reference_catalog.py tests/test_cli.py -k "reference or classification or prepare" -v`

Expected: PASS。

- [ ] **Step 8: 提交任务文件**

```powershell
git add src/jewelry_on_hand/models.py src/jewelry_on_hand/feishu_reference_source.py src/jewelry_on_hand/reference_catalog.py reference/feishu-reference-source.md tests/test_feishu_reference_source.py tests/test_reference_catalog.py tests/test_cli.py
git commit -m "feat: 增加戒指参考图字段"
```

---

### Task 5: 实现戒指参考图硬过滤、评分与 Top 3

**Files:**
- Modify: `src/jewelry_on_hand/category_policies/ring.py`
- Modify: `src/jewelry_on_hand/scoring.py`
- Test: `tests/test_category_policies.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `ProductAnalysis.hand_side`、`finger_position` 和六个参考字段。
- Produces: 现有 `score_reference()`、`select_top_references()` 和批次重排接口不变。
- Produces: 戒指候选少于 3 张时抛出包含缺失原因计数的 `ValueError`。

- [ ] **Step 1: 编写戒指合格参考图工厂和硬过滤测试**

```python
def ring_reference(**overrides):
    values = {
        "applicable_product_types": "ring",
        "applicable_display_modes": "worn",
        "hand_visibility": "高",
        "hand_side": "left",
        "visible_fingers": "thumb,index,middle,ring,little",
        "hand_orientation": "back",
        "ring_face_visibility": "高",
        "finger_separation": "高",
        "finger_occlusion_risk": "低",
        "crop_risk": "低",
        "file_exists": True,
    }
    values.update(overrides)
    return ReferenceRow(**base_reference_values(), **values)
```

分别断言以下候选不可用：未显式标记 `ring`、非 `worn`、目标手指不可见、戒面可见度低、手指分离度低、遮挡风险高、裁切风险高、文件不存在。

- [ ] **Step 2: 编写加权评分与忽略原戒指测试**

评分顺序固定为：目标手指可见与分离度 > 戒面可见度 > 手部可见度 > 同侧手 > 构图与风格。参考图已有戒指必须进入 `ignored_reference_jewelry`，Prompt 后续明确移除。

- [ ] **Step 3: 编写候选不足测试**

```python
def test_ring_requires_three_eligible_references():
    with pytest.raises(ValueError, match="戒指.*至少 3 张.*当前 2 张"):
        select_top_references(ring_product(), [ring_reference(), ring_reference(index=2)])
```

- [ ] **Step 4: 运行测试并确认失败**

Run: `pytest --basetemp output/pytest-ring/task5-red -o cache_dir=output/pytest-ring/cache tests/test_category_policies.py tests/test_scoring.py -k ring -v`

Expected: FAIL，原因是戒指策略尚未返回适配结果或没有候选数量 gate。

- [ ] **Step 5: 实现 `_evaluate_ring_reference()`**

硬过滤只依赖结构化字段，不从备注、饰品类型或场景关键词猜测缺失的目标手指信息。同侧手给予加分；相反手仍可作为姿势参考但记录风险，不把参考图左右手覆盖到已确认产品指位。

- [ ] **Step 6: 运行评分回归与批次重排测试**

Run: `pytest --basetemp output/pytest-ring/task5-green -o cache_dir=output/pytest-ring/cache tests/test_scoring.py tests/test_category_policies.py tests/test_cli.py -k "scoring or reference or rerank or ring" -v`

Expected: PASS。

- [ ] **Step 7: 提交任务文件**

```powershell
git add src/jewelry_on_hand/category_policies/ring.py src/jewelry_on_hand/scoring.py tests/test_category_policies.py tests/test_scoring.py
git commit -m "feat: 增加戒指参考图筛选与评分"
```

---

### Task 6: 升级审核页、人工纠正与决策快照

**Files:**
- Modify: `src/jewelry_on_hand/review_package.py`
- Modify: `src/jewelry_on_hand/review_decision.py`
- Modify: `src/jewelry_on_hand/cli.py`
- Test: `tests/test_review_package.py`
- Test: `tests/test_review_decision.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `record-decision` 新参数 `--ring-count`、`--hand-side`、`--finger-position`、`--ring-wear-style`。
- Produces: 戒指生成决策必须包含完整 `confirmation_snapshot`。

- [ ] **Step 1: 编写 CLI 参数与纠正事务测试**

```powershell
jewelry-on-hand record-decision `
  --run-root <run> `
  --action generate_rank_1 `
  --fidelity-confirmed `
  --confirmed-product-type ring `
  --ring-count 1 `
  --hand-side left `
  --finger-position ring `
  --ring-wear-style finger_base
```

测试命令原子更新最终 analysis 和 review decision；任一校验失败时两个文件都保持原样。

- [ ] **Step 2: 编写审核页戒指确认区测试**

断言 HTML 同时显示自动识别值、最终确认值、左右手、佩戴手指、佩戴方式、单枚限制、不确定结构和候选参考图的目标手指/戒面风险字段。

- [ ] **Step 3: 编写快照 gate 测试**

覆盖：缺快照、缺四个戒指字段、手侧不一致、指位不一致、戒指数量不一致、佩戴方式不一致均拒绝；合法戒指决策通过。

- [ ] **Step 4: 运行测试并确认失败**

Run: `pytest --basetemp output/pytest-ring/task6-red -o cache_dir=output/pytest-ring/cache tests/test_review_package.py tests/test_review_decision.py tests/test_cli.py -k ring -v`

Expected: FAIL，原因是审核页和 CLI 尚无戒指字段。

- [ ] **Step 5: 实现参数、覆盖字段和审核渲染**

将四个参数加入 `_decision_analysis_overrides()` 的直接字段；使用枚举 `choices` 限制输入。`ProductType.RING` 与项链一样要求完整快照，bracelet 的历史无快照兼容保持不变。

- [ ] **Step 6: 运行审核与 CLI 回归**

Run: `pytest --basetemp output/pytest-ring/task6-green -o cache_dir=output/pytest-ring/cache tests/test_review_package.py tests/test_review_decision.py tests/test_cli.py -v`

Expected: PASS。

- [ ] **Step 7: 提交任务文件**

```powershell
git add src/jewelry_on_hand/review_package.py src/jewelry_on_hand/review_decision.py src/jewelry_on_hand/cli.py tests/test_review_package.py tests/test_review_decision.py tests/test_cli.py
git commit -m "feat: 增加戒指人工确认与决策快照"
```

---

### Task 7: 构建戒指 Prompt 契约

**Files:**
- Modify: `src/jewelry_on_hand/category_policies/ring.py`
- Modify: `src/jewelry_on_hand/prompt_builder.py`
- Modify: `reference/prompt-template.md`
- Modify: `skills/jewelry-on-hand-workflow/references/prompt-contract.md`
- Modify: `skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- Test: `tests/test_prompt_builder.py`
- Test: `tests/test_skill_portability.py`

**Interfaces:**
- 保持: `build_generation_prompt(product, reference, fidelity_constraints=None) -> str`。
- Produces: `validate_prompt_contract.py` 能识别 `ring + worn` 并校验固定句。

- [ ] **Step 1: 编写戒指 Prompt 失败测试**

断言 Prompt 必须包含：

```text
内部图1中的戒指必须移除且不提供产品身份
内部图2是戒指身份唯一来源
只生成一枚目标戒指
佩戴在已确认的左手无名指根部
戒圈自然环绕手指
戒圈背侧按真实遮挡隐藏
不得悬浮、贴片、嵌入皮肤或穿透手指
不得改变戒面、主石、镶嵌、戒圈和装饰排列
不得把产品图中的手、皮肤、指甲或掌纹迁移到结果图
不可见戒圈背面不得补写为确定结构
```

- [ ] **Step 2: 运行 Prompt 测试并确认失败**

Run: `pytest --basetemp output/pytest-ring/task7-red -o cache_dir=output/pytest-ring/cache tests/test_prompt_builder.py -k ring -v`

Expected: FAIL，原因是缺少 `RING_POLICY` 的完整 Prompt 片段。

- [ ] **Step 3: 实现 `_build_ring_prompt_fragments()`**

使用 `hand_side.display_name` 和 `finger_position.display_name` 生成指位句；产品可见结构仍由 `visible_appearance` 与 canonical `must_keep` 提供，不另造戒指款式字段。`occluded_parts` 与 `uncertain_details` 必须出现在不确定性段落。

- [ ] **Step 4: 扩展 Prompt 校验脚本**

当规范品类是 `ring` 时只接受 `worn`，逐句验证单枚、指位、环绕接触、结构保真、来源手部隔离和未知结构禁推断；旧品类规则不变。

- [ ] **Step 5: 全文修订两个 Prompt 文档**

把公共双图职责写成适用于所有已支持品类的规则，再分别说明 bracelet、necklace、pendant_necklace、ring，删除任何把戒指列为不支持品类的现行文案。

- [ ] **Step 6: 运行 Prompt 与技能便携测试**

Run: `pytest --basetemp output/pytest-ring/task7-green -o cache_dir=output/pytest-ring/cache tests/test_prompt_builder.py tests/test_skill_portability.py -v`

Expected: PASS。

- [ ] **Step 7: 提交任务文件**

```powershell
git add src/jewelry_on_hand/category_policies/ring.py src/jewelry_on_hand/prompt_builder.py reference/prompt-template.md skills/jewelry-on-hand-workflow/references/prompt-contract.md skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py tests/test_prompt_builder.py tests/test_skill_portability.py
git commit -m "feat: 增加戒指生成提示词契约"
```

---

### Task 8: 生成前硬校验与分类 QC

**Files:**
- Modify: `src/jewelry_on_hand/generation.py`
- Modify: `src/jewelry_on_hand/qc.py`
- Modify: `src/jewelry_on_hand/models.py`
- Modify: `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- Modify: `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- Modify: `reference/qc-checklist.md`
- Modify: `skills/jewelry-on-hand-workflow/references/qc-checklist.md`
- Test: `tests/test_generation.py`
- Test: `tests/test_qc.py`
- Test: `tests/test_skill_portability.py`

**Interfaces:**
- Produces: 新关键失败代码 `ring_count_mismatch`、`hand_side_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`ring_contact_error`、`finger_deformation`、`source_hand_leakage`。
- 保持: `run_generation()` 只在所有 gate 通过后调用 AIReiter helper。

- [ ] **Step 1: 编写生成 gate 失败测试**

覆盖合法戒指可到达 helper；以下输入在 helper 调用前失败：白底源、手持源、`hand_held` 输出、两枚戒指、未知左右手、未知指位、`midi`、`cross_finger`、决策快照不一致、少于三张合格参考图。

- [ ] **Step 2: 编写戒指 QC 清单测试**

```python
items = build_qc_checklist(ProductType.RING, DisplayMode.WORN)
assert "画面中只有一枚目标戒指" in items
assert "戒指位于确认后的左右手和目标手指根部" in items
assert "戒圈自然环绕手指且前后遮挡、接触和阴影真实" in items
```

- [ ] **Step 3: 编写关键失败状态测试**

以下代码属于必须 `reject`：`ring_count_mismatch`、`finger_position_mismatch`、`ring_structure_mismatch`、`centerpiece_mismatch`、`source_hand_leakage`。`hand_side_mismatch`、`ring_contact_error`、`finger_deformation` 至少不得 `pass`；严重穿透同时使用既有 `severe_intersection` 并必须 `reject`。

- [ ] **Step 4: 运行生成和 QC 测试并确认失败**

Run: `pytest --basetemp output/pytest-ring/task8-red -o cache_dir=output/pytest-ring/cache tests/test_generation.py tests/test_qc.py tests/test_skill_portability.py -k ring -v`

Expected: FAIL，原因是关键失败枚举、检查脚本或戒指 gate 尚未接入。

- [ ] **Step 5: 扩展运行产物与 QC 校验脚本**

`inspect_run_artifacts.py` 对现代戒指 run 强制检查四个分析字段和四个快照字段；历史 bracelet 兼容分支不得吞掉戒指错误。模型和便携脚本使用完全相同的允许代码与 reject 集合。

- [ ] **Step 6: 全文修订 QC 文档**

按公共检查、品类检查、关键失败代码和状态映射重排全文；把戒指数量、指位、结构、接触物理、手指畸变和来源手迁移写入正式契约。

- [ ] **Step 7: 运行生成、QC 和便携技能回归**

Run: `pytest --basetemp output/pytest-ring/task8-green -o cache_dir=output/pytest-ring/cache tests/test_generation.py tests/test_qc.py tests/test_models.py tests/test_skill_portability.py -v`

Expected: PASS。

- [ ] **Step 8: 提交任务文件**

```powershell
git add src/jewelry_on_hand/generation.py src/jewelry_on_hand/qc.py src/jewelry_on_hand/models.py skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py reference/qc-checklist.md skills/jewelry-on-hand-workflow/references/qc-checklist.md tests/test_generation.py tests/test_qc.py tests/test_skill_portability.py
git commit -m "feat: 增加戒指生成硬校验与质检"
```

---

### Task 9: 完成 CLI 端到端回归与参考数据迁移

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_generation.py`
- Create: `output/ring-category-validation/2026-07-11/reference-enrichment-results.json`
- Create: `output/ring-category-validation/2026-07-11/reference-coverage.json`

**Interfaces:**
- Consumes: Tasks 1-8 的全部公共接口。
- Produces: 戒指完整四阶段测试；飞书回填文件只作为待审核产物，未经用户明确授权不得调用写回命令。

- [ ] **Step 1: 编写戒指 CLI 端到端测试**

使用假飞书 gateway 和假生成 helper，执行 `prepare-review → record-decision → generate → qc`；断言 Top 3、确认快照、Prompt、生成目录和 `qc.json` 均包含戒指契约。

- [ ] **Step 2: 编写旧品类回归矩阵**

覆盖历史 bracelet JSON、现代 bracelet、necklace worn、necklace hand_held、pendant_necklace worn，并断言戒指字段缺省不会改变既有输出。

- [ ] **Step 3: 运行 CLI 与生成测试**

Run: `pytest --basetemp output/pytest-ring/task9 -o cache_dir=output/pytest-ring/cache tests/test_cli.py tests/test_generation.py tests/test_run_paths.py tests/test_package_import.py -v`

Expected: PASS。

- [ ] **Step 4: 同步飞书并生成戒指补齐清单**

```powershell
jewelry-on-hand reference-sync --reference-cache-root output/ring-category-validation/2026-07-11/feishu-cache
```

从 `pending_enrichment.json` 中筛选 `适用品类` 含 `ring` 的记录，分析并写入 `reference-enrichment-results.json`。至少覆盖现有 7 张戒指专用参考图，并从综合佩戴图中筛选可明确标注目标手指的补充候选。

- [ ] **Step 5: 校验生产参考覆盖率**

`reference-coverage.json` 必须按 `thumb/index/middle/ring/little` 输出可用候选数和拒绝原因；每种目标手指至少有 3 张合格候选。任何手指不足 3 张时先补充或重新标注参考图，不以重复同一图片伪造 Top 3。

- [ ] **Step 6: 在获得明确写回授权后导入飞书**

```powershell
jewelry-on-hand reference-import-enrichment `
  --reference-cache-root output/ring-category-validation/2026-07-11/feishu-cache `
  --input-json output/ring-category-validation/2026-07-11/reference-enrichment-results.json
```

Expected: 退出码 `0`；只向空字段写入非空值，不覆盖飞书已有人工值。

- [ ] **Step 7: 仅提交自动化测试代码**

`output/` 验证产物不进入产品代码提交；如仓库政策允许保存验收索引，只提交不含附件和令牌的摘要 JSON。

```powershell
git add tests/test_cli.py tests/test_generation.py
git commit -m "test: 覆盖戒指完整工作流"
```

---

### Task 10: 全文修订技能与操作文档

**Files:**
- Modify: `CLAUDE.md`
- Modify: `skills/jewelry-on-hand-workflow/SKILL.md`
- Modify: `skills/jewelry-on-hand-workflow/references/workflow.md`
- Modify: `skills/jewelry-on-hand-workflow/references/troubleshooting.md`
- Modify: `reference/manual-workflow.md`
- Modify: `reference/product-fidelity-constraints-schema.md`
- Modify: `reference/codex-skill-installation.md`（仅在安装或调用方式实际变化时）
- Test: `tests/test_skill_portability.py`

**Interfaces:**
- Produces: 与实际实现一致的支持矩阵、命令、字段、gate、Prompt 与 QC 说明。

- [ ] **Step 1: 搜索所有品类边界和戒指旧表述**

Run:

```powershell
rg -n --encoding utf-8 "仅支持|当前支持|不支持品类|戒指|ring|bracelet|necklace|pendant" CLAUDE.md skills reference --glob "*.md" --glob "!reference/superpowers/plans/**"
```

- [ ] **Step 2: 全文修订现行文档**

统一写明：支持 `bracelet`、`necklace`、`pendant_necklace`、`ring`；戒指只支持单枚、`worn_source → worn`、确认左右手和手指、飞书参考源结构化字段和严格 QC。旧设计文档保留历史语境时应明确版本，不把旧限制伪装成当前行为。

- [ ] **Step 3: 更新便携技能契约测试**

测试技能副本包含 `ring`、四个分析字段、六个参考字段、八个 QC 失败代码和完整四阶段 gate；同时继续检查飞书默认、Excel 显式兼容。

- [ ] **Step 4: 运行文档与技能测试**

Run: `pytest --basetemp output/pytest-ring/task10 -o cache_dir=output/pytest-ring/cache tests/test_skill_portability.py -v`

Expected: PASS。

- [ ] **Step 5: 提交任务文件**

```powershell
git add CLAUDE.md skills/jewelry-on-hand-workflow/SKILL.md skills/jewelry-on-hand-workflow/references/workflow.md skills/jewelry-on-hand-workflow/references/troubleshooting.md reference/manual-workflow.md reference/product-fidelity-constraints-schema.md reference/codex-skill-installation.md tests/test_skill_portability.py
git commit -m "docs: 修订戒指品类工作流契约"
```

---

### Task 11: 自动化验证与三类真实模型验收

**Files:**
- Create: `output/ring-category-validation/2026-07-11/pytest.txt`
- Create: `output/ring-category-validation/2026-07-11/real-proof/<case>/...`
- Create: `output/ring-category-validation/2026-07-11/acceptance-summary.json`

**Interfaces:**
- Consumes: 完整 CLI、飞书已补齐参考记录和真实戒指佩戴原图。
- Produces: 素圈戒、单主石戒、开口戒各至少一个严格 QC 为 `pass` 的结果。

- [ ] **Step 1: 运行全套自动化测试并保存日志**

```powershell
New-Item -ItemType Directory -Force output/ring-category-validation/2026-07-11 | Out-Null
pytest --basetemp output/pytest-ring/final -o cache_dir=output/pytest-ring/cache -v 2>&1 | Tee-Object output/ring-category-validation/2026-07-11/pytest.txt
```

Expected: 全部测试通过，退出码 `0`。

- [ ] **Step 2: 验证非法输入不调用真实模型**

分别验证两枚戒指、白底源、手持源、未知指位、指关节戒和跨指戒在 `generate` 前失败；保存命令、退出码和错误文案到各案例目录。

- [ ] **Step 3: 运行素圈戒真实流程**

执行四阶段流程，检查戒圈粗细、颜色、闭口可见关系、目标手指、接触阴影和来源手部隔离；必须生成 `qc.json` 且状态为 `pass`。

- [ ] **Step 4: 运行单主石戒真实流程**

检查主石数量、形状、颜色、朝向、镶嵌位置、戒圈关系和目标指位；必须生成 `qc.json` 且状态为 `pass`。

- [ ] **Step 5: 运行开口戒真实流程**

只保持产品原图肉眼可见的开口、端点和装饰关系，不推断不可见背面；必须生成 `qc.json` 且状态为 `pass`。

- [ ] **Step 6: 按现有模型降级规则处理重跑**

每个案例第一次非 `pass` 后按现有规则切换或重试；同一案例最多 3 次。3 次仍无 `pass` 时，`acceptance-summary.json` 标记该案例失败并记录关键失败代码，功能不得宣布验收完成。

- [ ] **Step 7: 写入验收摘要**

```json
{
  "automated_tests": "pass",
  "reference_coverage": "pass",
  "cases": {
    "plain_band": {"status": "pass", "generation": "generation/NN"},
    "single_center_stone": {"status": "pass", "generation": "generation/NN"},
    "open_ring": {"status": "pass", "generation": "generation/NN"}
  },
  "legacy_regression": "pass"
}
```

- [ ] **Step 8: 最终核对工作区和提交范围**

Run:

```powershell
git status --short
git diff --check
pytest --basetemp output/pytest-ring/final-rerun -o cache_dir=output/pytest-ring/cache -v
```

Expected: `git diff --check` 无错误、pytest 退出码 `0`；原有未提交改动未被回退或混入戒指任务提交。

---

## 完成定义

只有同时满足以下条件，戒指能力才算完成：

1. `ring` 可通过统一四阶段 CLI 生成，非法输入在模型调用前拦截。
2. 飞书生产参考源已具备戒指六个结构化字段，并且五种目标手指各至少有 3 张合格候选。
3. 人工决策快照完整保存并校验单枚、左右手、佩戴手指和常规指根佩戴。
4. Prompt、运行产物检查和 QC 对戒指使用同一套固定契约与关键失败代码。
5. 全量自动化测试通过，手串、项链、带链吊坠和历史 bracelet run 无回归。
6. 素圈戒、单主石戒、开口戒真实模型验证各至少有一个严格 QC 为 `pass` 的结果。
7. 所有现行文档已全文修订，不存在“戒指仍不支持”或“Excel 是默认业务源”的矛盾说明。
