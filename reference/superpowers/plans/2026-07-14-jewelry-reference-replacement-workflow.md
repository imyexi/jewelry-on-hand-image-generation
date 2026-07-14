# 珠宝真人场景参考底图替换工作流实施计划

> **供 agentic worker 使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行本计划；每一步使用 `- [ ]` 跟踪。实现 Skill 文档任务时还必须使用 `superpowers:writing-skills`，所有生产修改遵循 `superpowers:test-driven-development`。

**目标：** 将 `jewelry-on-hand-workflow` 收敛为仅支持 `hand_worn` 与 `lifestyle` 的真人场景首饰替换工作流，使模型严格保留参考底图的构图、人物、姿势、服装、背景和光线，只把原首饰替换为产品上手图中的一件目标产品。

**架构：** 在现有 `prepare-review -> record-decision -> generate -> qc` 四阶段之间增加一份贯穿全链路的 `ReferenceCompositionSnapshot`。参考选择继续复用飞书字段和品类策略，但固定执行“图片类型与硬 gate -> 质量排序 -> 质量窗口内低重复”；人工决策把一个候选快照与 rank、参考图 SHA-256、输出角色原子固化，Prompt、送模输入、运行审计和 QC 都只读取这份快照。历史 run 保持可读、可审计，但没有新快照时不得追加生成。

**技术栈：** Python 3.11+、标准库 `dataclasses` / `argparse` / `hashlib` / `json` / `pathlib`、pytest 8、现有 `jewelry_on_hand` 包、AIReiter helper、便携 Skill 脚本。

## 全局约束

- 所有思考、代码注释、错误文案、测试名称和文档使用中文；参考与流程 Markdown 放在 `reference/`，测试日志、真实样例和临时产物放在 `output/`。
- 当前工作区已有大量未提交改动；不得回退、覆盖或格式化无关改动。每个任务只暂存该任务“文件”小节列出的路径，并在 `git diff --cached --name-only` 核对后提交。
- 全局保留 `OutputRole.HERO` 供未来主图 Skill 使用，但当前 Skill 的 `prepare-review`、`record-decision`、Prompt 构建和 `generate` 必须明确拒绝 `hero`；不得静默改成其他角色。
- 当前 Skill 的新 run 必须显式声明 `hand_worn` 或 `lifestyle`。飞书素材表“图片类型”（本地 `purpose_category`）是参考图角色唯一来源，不得用视觉推断、关键词、风格分类或推荐方式替代。
- 参考底图是人物、姿势、手势、构图、景别、服装、背景、光线、留白和替换位置的唯一来源；产品上手图只提供珠宝品类、数量、结构、排列、颜色、材质、纹理、反光和尺寸感。
- 支持品类固定为 `bracelet`、`necklace`、`pendant_necklace`、`ring`；品类策略只能控制产品结构、数量、连接、目标身体部位与佩戴物理，不能无条件注入“手腕近景”“锁骨近景”“半身”“全身”等构图要求。
- 参考选择只在完整通过硬 gate 的候选中进行；多样性质量窗口固定为 `score >= max_eligible_score - 10`，最多选 3 张，先按 `composition_signature` 当前批次使用次数升序，再按 score 降序，最后按固定审计种子打破完全平局。
- 新 run 必须产生 `analysis/reference_composition_snapshots.json`、`review/reference_composition_snapshot.json`，以及每次生成目录中的 `scene-reference.*`、`product-reference.*`、`reference-composition-snapshot.json`、`input-manifest.json`。
- 送模图片顺序固定为内部图 1“参考底图”、内部图 2“产品身份图”；Prompt 必须首先声明这是底图编辑任务，并限定只有原首饰、目标产品、必要接触阴影和小面积水印可修改。
- 戒指继续遵守现有送模 Prompt `<= 1200` 字和前 300 字核心规则；新增底图锁定语义必须采用紧凑渲染，不得用放宽上限或静默截断规避。
- `pass` 必须同时完整通过 `reference_preservation_checks`、`fidelity_checks` 和 `checklist_checks`；构图、姿势、人物、服装、背景、光线、替换位置改变，明显原首饰泄漏或产品复制必须 `reject`。
- `reference_jewelry_leakage` 表示肉眼可辨认的原首饰主体仍存在，必须 `reject`；仅边缘像素或小面积接触阴影残留使用 `source_jewelry_removed=result: rerun`，不得滥用严重错误码。
- 同一参考图首次出现参考结构严重错误时，结果仍记为 `reject`，但允许使用同一模型和一段固定强化约束重跑一次；第二次参考结构严重错误必须停用该参考并回到 `prepare-review`。模型切换次数只累计产品保真或局部融合类非 pass，不累计参考结构 reject。
- 历史 run 只读：便携检查器可以识别和审计旧 `hand-reference.*`，但所有新的 `generate` 调用必须具备已确认的新快照；缺失时返回“重新 prepare-review”的迁移提示。
- QY018、QY027 只作为第一批不回写飞书的真实对照；没有用户新的明确授权，不上传附件、不替换 `✅️上手图`、不删除任何飞书附件。
- 当前已知全量基线为 `1033 passed, 6 failed`，6 个失败属于既有项链保真约束 v1/v2 兼容测试。每个定向测试必须全绿；最终全量测试不得新增失败，并把基线与最终差异写入 `output/reference-replacement-workflow/2026-07-14/pytest-comparison.md`。

---

## 文件结构与职责

### 新建文件

- `src/jewelry_on_hand/reference_composition.py`：快照 dataclass、候选草稿、序列化、SHA/角色/rank/唯一替换位置绑定校验、构图签名。
- `src/jewelry_on_hand/qc_review.py`：生成四栏人工 QC 页面，不包含 QC 判定逻辑。
- `tests/test_reference_composition.py`：快照 schema、草稿构建、绑定和错误边界。
- `tests/test_qc_review.py`：四栏页面和缺文件 gate。
- `skills/jewelry-on-hand-workflow/references/reference-composition-contract.md`：便携快照 schema、人工确认和停止条件。
- `skills/jewelry-on-hand-workflow/scripts/validate_reference_snapshot.py`：不依赖项目包安装的便携快照校验器。

### 主要修改文件

- `src/jewelry_on_hand/output_roles.py`：保留全局枚举，新增当前 Skill 的角色边界 helper。
- `src/jewelry_on_hand/scoring.py`：字段驱动硬 gate、质量窗口和确定性低重复选择。
- `src/jewelry_on_hand/review_package.py`：写候选快照并在审核页并列展示产品图、参考图和结构快照。
- `src/jewelry_on_hand/review_decision.py`、`src/jewelry_on_hand/models.py`：原子固化已确认快照并把其 SHA-256 绑定到决策。
- `src/jewelry_on_hand/prompt_builder.py`、`src/jewelry_on_hand/category_policies/*.py`：以快照为画面唯一来源，品类片段只保留产品身份与佩戴物理。
- `src/jewelry_on_hand/generation.py`：生成前校验快照，复制双输入与 manifest，使用 run 内副本按固定顺序提交。
- `src/jewelry_on_hand/qc.py`、`src/jewelry_on_hand/cli.py`：三层 QC、严重错误路由和 CLI 参数。
- `skills/jewelry-on-hand-workflow/SKILL.md` 及其 `references/`、`scripts/`、`agents/openai.yaml`：全文切换为“底图首饰替换”契约。

---

### 任务 1：建立当前 Skill 的输出角色边界

**文件：**
- 修改：`src/jewelry_on_hand/output_roles.py`
- 修改：`src/jewelry_on_hand/cli.py`
- 修改：`tests/test_output_role_compatibility.py`
- 修改：`tests/test_cli.py`

**接口：**
- Consumes：现有 `OutputRole`、`normalize_output_role(value)`、CLI `--output-role`。
- Produces：`SCENE_REPLACEMENT_OUTPUT_ROLES: frozenset[OutputRole]`；`require_scene_replacement_role(value: OutputRole | str | None, *, stage: str) -> OutputRole`。
- 后续依赖：评分、快照、Prompt 与生成 gate 只能接收该 helper 返回的角色。

- [ ] **步骤 1：先写角色边界失败测试**

```python
import pytest

from jewelry_on_hand.output_roles import (
    OutputRole,
    require_scene_replacement_role,
)


@pytest.mark.parametrize("role", [OutputRole.HAND_WORN, "lifestyle"])
def test_scene_replacement_role_accepts_only_supported_roles(role):
    assert require_scene_replacement_role(role, stage="prepare-review") in {
        OutputRole.HAND_WORN,
        OutputRole.LIFESTYLE,
    }


@pytest.mark.parametrize("role", [None, OutputRole.HERO, "hero"])
def test_scene_replacement_role_rejects_missing_or_hero(role):
    with pytest.raises(ValueError, match="主图 Skill|hand_worn|lifestyle"):
        require_scene_replacement_role(role, stage="generate")
```

在 `tests/test_cli.py` 增加三个入口回归：`prepare-review --output-role hero` 在创建 run 前失败；`record-decision --output-role hero` 不写决策；已有 `analysis/output_role.json={"output_role":"hero"}` 的 run 在 `generate` 调用 helper 前失败。

- [ ] **步骤 2：运行测试并确认 RED 原因正确**

运行：

```powershell
python -m pytest tests/test_output_role_compatibility.py tests/test_cli.py `
  -k "scene_replacement_role or rejects_hero" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-01-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-01-red
```

预期：FAIL，原因是 `require_scene_replacement_role` 尚不存在，且现有 CLI 的 choices 仍接受 `hero`。

- [ ] **步骤 3：实现最小角色 helper 并接入三个 CLI 入口**

```python
SCENE_REPLACEMENT_OUTPUT_ROLES = frozenset(
    {OutputRole.HAND_WORN, OutputRole.LIFESTYLE}
)


def require_scene_replacement_role(
    value: OutputRole | str | None,
    *,
    stage: str,
) -> OutputRole:
    role = normalize_output_role(value)
    if role is None:
        raise ValueError(
            f"{stage} 必须显式提供 output_role=hand_worn 或 lifestyle"
        )
    if role not in SCENE_REPLACEMENT_OUTPUT_ROLES:
        raise ValueError(
            f"{stage} 不支持 hero；主图必须交给独立主图 Skill"
        )
    return role
```

在 `_prepare_review` 复制产品图、创建目录之前校验参数；在 `_record_output_role` 校验命令值与 run 值；在 `_generate` 读取 `output_role.json` 后再次校验。CLI choices 仍可由全局枚举产生，以便返回明确的业务错误，而不是 argparse 的模糊非法值错误。

- [ ] **步骤 4：运行角色相关回归并确认 GREEN**

运行：

```powershell
python -m pytest tests/test_output_role_compatibility.py tests/test_cli.py `
  -k "output_role or hero" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-01-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-01-green
```

预期：新增测试 PASS；既有断言“当前 Skill 可生成 hero”的测试必须改为“全局枚举保留、当前入口拒绝”，不得删除枚举兼容测试。

- [ ] **步骤 5：提交任务 1**

```powershell
git add src/jewelry_on_hand/output_roles.py src/jewelry_on_hand/cli.py `
  tests/test_output_role_compatibility.py tests/test_cli.py
git diff --cached --name-only
git commit -m "feat: restrict scene replacement output roles"
```

---

### 任务 2：定义并校验参考构图快照

**文件：**
- 新建：`src/jewelry_on_hand/reference_composition.py`
- 新建：`tests/test_reference_composition.py`

**接口：**
- Consumes：`ProductAnalysis`、`ScoredReference`、`OutputRole`、参考图真实文件。
- Produces：`ReferencePose`、`ReplacementTarget`、`ReferenceCompositionSnapshot`；`build_candidate_snapshot(product: ProductAnalysis, reference: ScoredReference, output_role: OutputRole | str) -> ReferenceCompositionSnapshot`；`load_reference_composition_snapshot(path: str | Path) -> ReferenceCompositionSnapshot`；`validate_snapshot_binding(snapshot: ReferenceCompositionSnapshot, *, reference_file: str | Path, output_role: OutputRole | str, expected_rank: int) -> None`；`reference_composition_sha256(snapshot: ReferenceCompositionSnapshot) -> str`。
- JSON 文件名常量：`REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME` 与 `REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME`。

- [ ] **步骤 1：为完整 round-trip 和强制停止条件写失败测试**

```python
def test_reference_composition_snapshot_round_trip(reference_file, scored_reference, bracelet):
    snapshot = build_candidate_snapshot(
        bracelet,
        scored_reference,
        OutputRole.HAND_WORN,
    )

    restored = ReferenceCompositionSnapshot.from_dict(snapshot.to_dict())

    assert restored == snapshot
    assert restored.reference_sha256 == hashlib.sha256(
        reference_file.read_bytes()
    ).hexdigest()
    assert restored.replacement_target.target_product_count == 1
    assert restored.composition_signature


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"output_role": "hero"}, "hero"),
        ({"reference_sha256": "0" * 64}, "SHA-256"),
        ({"text_or_ui_risk": "blocking"}, "文字或 UI"),
        ({"product_visibility_sufficient": False}, "展示面积不足"),
    ],
)
def test_snapshot_binding_rejects_unsafe_or_mismatched_snapshot(
    valid_snapshot_data, reference_file, mutation, message
):
    data = valid_snapshot_data | mutation
    snapshot = ReferenceCompositionSnapshot.from_dict(data)
    with pytest.raises(ValueError, match=message):
        validate_snapshot_binding(
            snapshot,
            reference_file=reference_file,
            output_role=OutputRole.HAND_WORN,
            expected_rank=1,
        )
```

另加表驱动测试覆盖：空 `framing/camera_angle/subject_placement/clothing/background/lighting`、空身体区域、空 pose、空替换部位、`target_product_count != 1`、多件同类首饰但没有唯一目标描述、角色不一致、rank 不一致、文件名不一致。

- [ ] **步骤 2：运行测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_reference_composition.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-02-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-02-red
```

预期：ERROR/FAIL，原因是新模块和类型尚不存在。

- [ ] **步骤 3：实现不可变 schema、序列化与绑定校验**

```python
@dataclass(frozen=True)
class ReferencePose:
    body: str
    arm: str
    hand: str
    hand_side: str


@dataclass(frozen=True)
class ReplacementTarget:
    body_region: str
    source_jewelry: str
    target_product_count: int


@dataclass(frozen=True)
class ReferenceCompositionSnapshot:
    rank: int
    reference_file: str
    reference_sha256: str
    output_role: OutputRole
    framing: str
    camera_angle: str
    subject_placement: str
    visible_body_regions: tuple[str, ...]
    pose: ReferencePose
    clothing: str
    background: str
    lighting: str
    replacement_target: ReplacementTarget
    other_jewelry_to_remove: tuple[str, ...]
    text_or_ui_risk: Literal["none", "small_removable", "blocking"]
    product_visibility_sufficient: bool
    composition_signature: str
```

`build_candidate_snapshot` 只从已经同步的飞书字段生成审核草稿：`framing` 取 `row.framing`，身体区域取 `row.visible_body_regions`，姿势取 `row.pose_keywords/hand_side/hand_orientation`，服装取 `row.collar_type` 与遮挡描述，背景与光线取 `scene_keywords/style_category/notes`，原首饰取 `existing_jewelry` 与 `ignored_reference_jewelry`。无法形成非空、可确认字段时抛错并让候选停在 `prepare-review`，不得在生成阶段猜测。

`validate_snapshot_binding` 计算实际文件 SHA-256，并逐项校验 `rank`、文件名、角色、唯一替换位置、单件目标、展示面积与文字/UI 风险。`reference_composition_sha256` 对 `to_dict()` 的 UTF-8、`sort_keys=True` 紧凑 JSON 计算摘要，保证决策绑定可重现。

- [ ] **步骤 4：运行快照测试并确认 GREEN**

运行：

```powershell
python -m pytest tests/test_reference_composition.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-02-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-02-green
```

预期：全部 PASS，且异常文案明确指出具体字段和重新 `prepare-review` 的动作。

- [ ] **步骤 5：提交任务 2**

```powershell
git add src/jewelry_on_hand/reference_composition.py tests/test_reference_composition.py
git diff --cached --name-only
git commit -m "feat: add reference composition snapshot contract"
```

---

### 任务 3：重构硬 gate、质量窗口和低重复选择

**文件：**
- 修改：`src/jewelry_on_hand/scoring.py`
- 修改：`src/jewelry_on_hand/category_policies/bracelet.py`
- 修改：`src/jewelry_on_hand/category_policies/necklace.py`
- 修改：`src/jewelry_on_hand/category_policies/ring.py`
- 修改：`tests/test_scoring.py`
- 修改：`tests/test_category_policies.py`

**接口：**
- Consumes：任务 1 的受支持角色、现有 `ReferenceAdaptation`、飞书 `purpose_category` 与语义字段。
- Produces：`select_top_references(product: ProductAnalysis, rows: Iterable[ReferenceRow], output_role: OutputRole | str, *, signature_usage: Mapping[str, int] | None = None, audit_seed: str = "reference-replacement-v1") -> tuple[list[ScoredReference], list[ScoredReference]]`；`select_diverse_eligible_references(candidates: Sequence[ScoredReference], output_role: OutputRole | str, *, signature_usage: Mapping[str, int] | None = None, audit_seed: str = "reference-replacement-v1", limit: int = 3) -> list[ScoredReference]`；`select_batch_diverse_references(candidate_sets: Sequence[Sequence[ScoredReference]], output_roles: Sequence[OutputRole | str], *, limit: int = 3, initial_signature_usage: Mapping[str, int] | None = None, audit_seed: str = "reference-replacement-v1") -> list[list[ScoredReference]]`；`composition_signature_for_row(row: ReferenceRow, output_role: OutputRole | str) -> str`。
- 选择结果：`candidates` 是全部通过硬 gate 的质量排序；`selected` 是最高分减 10 分窗口内、最多 3 张的低重复结果。

- [ ] **步骤 1：先写五类选择失败测试**

```python
def test_role_gate_uses_only_feishu_image_type_field(bracelet, rows):
    rows[0] = replace(
        rows[0],
        purpose_category="主图",
        scene_keywords="手部佩戴图 生活场景图 深色背景",
        recommended_usage="手部佩戴图",
    )
    with pytest.raises(ValueError, match="手部佩戴图"):
        select_top_references(bracelet, rows[:1], OutputRole.HAND_WORN)


def test_diversity_never_selects_below_ten_point_quality_window(bracelet, rows):
    scored = [
        ScoredReference(row, score, rank, (), (), ())
        for rank, (row, score) in enumerate(
            zip(rows, [100, 96, 90, 89], strict=True),
            start=1,
        )
    ]
    selected = select_diverse_eligible_references(
        scored,
        OutputRole.HAND_WORN,
        signature_usage={
            composition_signature_for_row(scored[3].row, OutputRole.HAND_WORN): 0,
            composition_signature_for_row(scored[0].row, OutputRole.HAND_WORN): 8,
        },
        audit_seed="QY027-hand_worn",
    )
    assert [item.score for item in selected] == [100, 96, 90]
    assert 89 not in [item.score for item in selected]


def test_low_usage_signature_wins_only_after_gate_and_score_tie(bracelet, rows):
    scored = [
        ScoredReference(row, 100, rank, (), (), ())
        for rank, row in enumerate(rows[:3], start=1)
    ]
    usage = {
        composition_signature_for_row(scored[0].row, OutputRole.LIFESTYLE): 5,
        composition_signature_for_row(scored[1].row, OutputRole.LIFESTYLE): 0,
        composition_signature_for_row(scored[2].row, OutputRole.LIFESTYLE): 1,
    }
    selected = select_diverse_eligible_references(
        scored, OutputRole.LIFESTYLE, signature_usage=usage, audit_seed="QY018"
    )
    assert selected[0].row == scored[1].row
```

再覆盖：相同 usage 与 score 在相同 seed 下顺序稳定、不同 seed 可改变完全平局；`blocking` UI、展示面积低、严重遮挡、高裁切风险、原首饰无法完整识别的候选不会因“未使用”进入 selected；戒指参考手侧/指位必须与快照目标兼容，不再接受“相反手仅复用姿势”。
为 `select_batch_diverse_references` 增加两组 candidate sets，断言第一个 run 选过的 signature 会增加 usage，第二个 run 在同质量同分时选择使用次数更少的 signature；不同角色的 signature 因含 `output_role` 不会互相误计数。

- [ ] **步骤 2：运行定向测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_scoring.py tests/test_category_policies.py `
  -k "image_type or quality_window or signature or replacement_target" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-03-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-03-red
```

预期：FAIL；现有窗口为 40 分、惩罚式重排可从窗口外回退，且 ring 允许相反手。

- [ ] **步骤 3：实现固定三层选择算法**

```python
DIVERSITY_SCORE_WINDOW = 10
DEFAULT_AUDIT_SEED = "reference-replacement-v1"


def _audit_tie_break(seed: str, signature: str, file_name: str) -> str:
    payload = f"{seed}\0{signature}\0{file_name}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_diverse_eligible_references(
    candidates: Sequence[ScoredReference],
    output_role: OutputRole,
    *,
    signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
    limit: int = 3,
) -> list[ScoredReference]:
    if not candidates:
        return []
    usage = signature_usage or {}
    floor = max(item.score for item in candidates) - DIVERSITY_SCORE_WINDOW
    pool = [item for item in candidates if item.score >= floor]
    ordered = sorted(
        pool,
        key=lambda item: (
            usage.get(composition_signature_for_row(item.row, output_role), 0),
            -item.score,
            _audit_tie_break(
                audit_seed,
                composition_signature_for_row(item.row, output_role),
                item.row.file_name,
            ),
        ),
    )
    return _rerank(ordered[:limit])


def select_batch_diverse_references(
    candidate_sets: Sequence[Sequence[ScoredReference]],
    output_roles: Sequence[OutputRole | str],
    *,
    limit: int = 3,
    initial_signature_usage: Mapping[str, int] | None = None,
    audit_seed: str = DEFAULT_AUDIT_SEED,
) -> list[list[ScoredReference]]:
    if len(candidate_sets) != len(output_roles):
        raise ValueError("candidate_sets 与 output_roles 数量必须一致")
    usage = dict(initial_signature_usage or {})
    selections = []
    for index, (candidates, role) in enumerate(
        zip(candidate_sets, output_roles, strict=True)
    ):
        selected = select_diverse_eligible_references(
            candidates,
            role,
            signature_usage=usage,
            audit_seed=f"{audit_seed}:{index}",
            limit=limit,
        )
        selections.append(selected)
        for item in selected:
            key = composition_signature_for_row(item.row, role)
            usage[key] = usage.get(key, 0) + 1
    return selections
```

删除“窗口内没有候选就回退到 remaining”的路径。硬 gate 先按 `purpose_category` 的唯一 marker 过滤，再执行深色背景、品类/模式、目标位置、展示面积、裁切、遮挡、UI 和原首饰可清除性；风格、材质和颜色只能加分，不能改变 `eligible`。

- [ ] **步骤 4：运行评分与品类策略全文件**

运行：

```powershell
python -m pytest tests/test_scoring.py tests/test_category_policies.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-03-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-03-green
```

预期：全部新契约测试 PASS。凡是依赖旧“40 分窗口”或“相反手可复用”的断言，应改成新设计的拒绝断言，不得通过调高分数伪造兼容。

- [ ] **步骤 5：提交任务 3**

```powershell
git add src/jewelry_on_hand/scoring.py `
  src/jewelry_on_hand/category_policies/bracelet.py `
  src/jewelry_on_hand/category_policies/necklace.py `
  src/jewelry_on_hand/category_policies/ring.py `
  tests/test_scoring.py tests/test_category_policies.py
git diff --cached --name-only
git commit -m "feat: select diverse references inside strict quality gate"
```

---

### 任务 4：在 prepare-review 生成候选快照并升级审核页

**文件：**
- 修改：`src/jewelry_on_hand/review_package.py`
- 修改：`src/jewelry_on_hand/cli.py`
- 修改：`tests/test_review_package.py`
- 修改：`tests/test_cli.py`

**接口：**
- Consumes：任务 2 的 `build_candidate_snapshot`、任务 3 的 Top 3。
- Produces：`analysis/reference_composition_snapshots.json`（恰好对应 selected rank）；`write_review_package(paths: RunPaths, product_image: str | Path, selected: Sequence[ScoredReference], candidates: Sequence[ScoredReference], *, composition_snapshots: Sequence[ReferenceCompositionSnapshot]) -> Path`；包含产品图、参考图、快照与人工确认提示的 `review/review.html`。

- [ ] **步骤 1：写产物与 HTML 失败测试**

```python
def test_review_package_writes_and_renders_composition_snapshots(
    run_paths, product_image, selected, candidates, snapshots
):
    html_path = write_review_package(
        run_paths,
        product_image,
        selected,
        candidates,
        composition_snapshots=snapshots,
    )

    data = read_json(
        run_paths.analysis_dir / "reference_composition_snapshots.json"
    )
    html = html_path.read_text(encoding="utf-8")
    assert [item["rank"] for item in data] == [1, 2, 3]
    assert "参考底图" in html
    assert "产品身份图" in html
    assert "目标替换位置" in html
    assert snapshots[0].subject_placement in html
    assert "预计展示面积不足时不要选择" in html
```

CLI 测试还要断言：输出角色缺失或候选快照任一必填字段无法形成时，`prepare-review` 返回非零；失败 run 中不得出现 `review_decision.json`。

- [ ] **步骤 2：运行测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_review_package.py tests/test_cli.py `
  -k "composition_snapshot or prepare_review" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-04-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-04-red
```

预期：FAIL，现有 `write_review_package` 没有快照参数，也不写新 JSON。

- [ ] **步骤 3：构建快照并在同一次 review 写入**

```python
snapshots = tuple(
    build_candidate_snapshot(product, item, output_role)
    for item in selected
)
write_review_package(
    paths,
    copied_product,
    selected,
    candidates,
    composition_snapshots=snapshots,
)
```

`write_review_package` 在复制参考图并取得 review SHA 后再写候选快照；每份快照绑定源图内容 SHA，`selected_references.json` 继续保存源/review 双摘要。写文件前校验 snapshot rank 集合与 selected rank 集合完全一致。审核卡片用 `<dl>` 显示景别、机位、主体位置、可见身体区域、姿势、服装、背景、光线、替换位置、需移除首饰、UI 风险和展示面积，不能只显示一段自由文本。`_rerank_batch` 为每个 run 同时加载 `product_analysis.json` 与 `output_role.json`，把角色列表传给任务 3 的 batch selector，并在重写 Top 3 后重新构建三份 candidate snapshot 和审核页；不得保留旧 rank 的快照。

- [ ] **步骤 4：运行 review 与 CLI 相关回归**

运行：

```powershell
python -m pytest tests/test_reference_composition.py tests/test_review_package.py tests/test_cli.py `
  -k "review or snapshot or output_role" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-04-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-04-green
```

预期：PASS；审核页在桌面和 720px 以下均保持产品图、参考图和快照可读。

- [ ] **步骤 5：提交任务 4**

```powershell
git add src/jewelry_on_hand/review_package.py src/jewelry_on_hand/cli.py `
  tests/test_review_package.py tests/test_cli.py
git diff --cached --name-only
git commit -m "feat: add composition snapshots to reference review"
```

---

### 任务 5：在 record-decision 原子固化单一人工确认快照

**文件：**
- 修改：`src/jewelry_on_hand/models.py`
- 修改：`src/jewelry_on_hand/review_decision.py`
- 修改：`src/jewelry_on_hand/cli.py`
- 修改：`tests/test_models.py`
- 修改：`tests/test_review_decision.py`
- 修改：`tests/test_cli.py`

**接口：**
- Consumes：必填确认旗标 `--reference-snapshot-confirmed`、候选快照列表、单一 selected rank、最终 analysis、canonical。
- Produces：`ReviewDecision.reference_snapshot_sha256: str | None`；`review/reference_composition_snapshot.json`；`_confirmed_reference_snapshot(paths: RunPaths, decision: ReviewDecision) -> ReferenceCompositionSnapshot`；原子四文件事务。
- 约束：新 run 的生成 action 只能确认一个 rank；`generate_multiple` 只保留历史读取，不允许新快照 run 使用。

- [ ] **步骤 1：写缺失、篡改和回滚失败测试**

```python
def test_write_review_bundle_atomically_binds_confirmed_reference_snapshot(
    run_paths, decision_data, analysis_data, confirmed_snapshot
):
    decision_data["selected_ranks"] = [2]
    write_review_bundle(
        run_paths,
        decision_data,
        analysis_data=analysis_data,
    )

    saved_snapshot = read_json(
        run_paths.review_dir / "reference_composition_snapshot.json"
    )
    saved_decision = read_json(run_paths.review_dir / "review_decision.json")
    assert saved_snapshot["rank"] == 2
    assert saved_decision["reference_snapshot_sha256"] == (
        reference_composition_sha256(confirmed_snapshot)
    )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("rank", 3),
        ("reference_file", "other-reference.jpg"),
        ("reference_sha256", "0" * 64),
        ("output_role", "lifestyle"),
    ],
)
def test_record_decision_rejects_snapshot_binding_mutation(
    run_paths, decision_data, snapshot_data, field, invalid_value
):
    snapshot_data[field] = invalid_value
    with pytest.raises(ReviewGateError, match=field.replace("_", ".*")):
        write_json(
            run_paths.analysis_dir / "reference_composition_snapshots.json",
            [snapshot_data],
        )
        write_review_bundle(run_paths, decision_data)
    assert not (run_paths.review_dir / "review_decision.json").exists()
    assert not (run_paths.review_dir / "reference_composition_snapshot.json").exists()
```

再模拟 `os.replace` 在第 4 个目标失败，断言 analysis、decision、canonical、confirmed snapshot 全部恢复旧内容。测试还必须拒绝两个 selected ranks、新 run 的 `generate_multiple`、未传 `--reference-snapshot-confirmed`、selected rank 未出现在候选列表、角色与 `analysis/output_role.json` 不一致。候选描述若不准确，必须修订飞书语义字段并重新 `prepare-review`；不允许直接编辑候选 JSON 后继续决策。

- [ ] **步骤 2：运行测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_models.py tests/test_review_decision.py tests/test_cli.py `
  -k "reference_snapshot or four_file or generate_multiple" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-05-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-05-red
```

预期：FAIL；`ReviewDecision` 尚无摘要字段，事务最多写三文件。

- [ ] **步骤 3：扩展决策 schema 与原子事务**

```python
reference_snapshot_sha256: str | None = None


def _confirmed_reference_snapshot(
    paths: RunPaths,
    decision: ReviewDecision,
) -> ReferenceCompositionSnapshot:
    if len(decision.selected_ranks) != 1:
        raise ReviewGateError("新快照 run 必须且只能确认一个 selected rank")
    data = read_json(
        paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    )
    if not isinstance(data, list):
        raise ReviewGateError("候选参考构图快照必须是 JSON 列表")
    rank = decision.selected_ranks[0]
    matches = [item for item in data if isinstance(item, dict) and item.get("rank") == rank]
    if len(matches) != 1:
        raise ReviewGateError(f"selected rank {rank} 必须对应唯一候选构图快照")
    snapshot = ReferenceCompositionSnapshot.from_dict(matches[0])
    selected_data = read_json(paths.analysis_dir / "selected_references.json")
    if not isinstance(selected_data, list):
        raise ReviewGateError("selected_references.json 必须是 JSON 列表")
    selected_matches = [
        item
        for item in selected_data
        if isinstance(item, dict) and item.get("rank") == rank
    ]
    if len(selected_matches) != 1:
        raise ReviewGateError(f"selected rank {rank} 必须对应唯一参考图")
    selected_reference = selected_matches[0].get("selected_reference")
    if not isinstance(selected_reference, str) or not selected_reference.strip():
        raise ReviewGateError(f"selected rank {rank} 缺少参考图路径")
    validate_snapshot_binding(
        snapshot,
        reference_file=Path(selected_reference),
        output_role=decision.output_role,
        expected_rank=rank,
    )
    return snapshot
```

在 `ReviewDecision.__post_init__` 和 `from_dict` 中校验摘要必须是 64 位小写十六进制。CLI 生成 action 必须传 `--reference-snapshot-confirmed`，然后从候选列表按唯一 selected rank 读取不可编辑草稿；`_confirmed_reference_snapshot` 将 rank/file/SHA/output_role 与 `selected_references.json` 绑定。`write_review_bundle` 在现有 analysis/canonical/decision 内存校验完成后，把 snapshot digest 写入 normalized decision，并把 `(review/reference_composition_snapshot.json, snapshot.to_dict())` 追加到同一个 transaction entries；`_commit_json_transaction` 的标签不再硬编码“三文件”，使用 `f"{len(entries)} 文件"`。

- [ ] **步骤 4：运行决策、模型与 CLI 全量文件**

运行：

```powershell
python -m pytest tests/test_models.py tests/test_review_decision.py tests/test_cli.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-05-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-05-green
```

预期：新增测试 PASS；既有产品确认快照与 canonical 原子性测试继续 PASS。

- [ ] **步骤 5：提交任务 5**

```powershell
git add src/jewelry_on_hand/models.py src/jewelry_on_hand/review_decision.py `
  src/jewelry_on_hand/cli.py tests/test_models.py tests/test_review_decision.py tests/test_cli.py
git diff --cached --name-only
git commit -m "feat: bind approved composition snapshot to review decision"
```

---

### 任务 6：把 Prompt 重构为严格底图编辑契约

**文件：**
- 修改：`src/jewelry_on_hand/prompt_builder.py`
- 修改：`src/jewelry_on_hand/output_roles.py`
- 修改：`src/jewelry_on_hand/category_policies/bracelet.py`
- 修改：`src/jewelry_on_hand/category_policies/necklace.py`
- 修改：`src/jewelry_on_hand/category_policies/ring.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- 修改：`tests/test_prompt_builder.py`
- 修改：`tests/test_skill_portability.py`

**接口：**
- Consumes：已确认 `ReferenceCompositionSnapshot`、产品 analysis、canonical、选中参考图。
- Produces：`build_generation_prompt(product, reference, fidelity_constraints, output_role, reference_snapshot) -> str`；快照驱动的角色与画面锁定段。
- 兼容：`build_prompt` 继续作为别名；历史无角色调用只允许离线读取测试，不得由新 CLI generate 使用。

- [ ] **步骤 1：写“底图第一、产品第二”的 Prompt 失败测试**

```python
def test_prompt_is_reference_base_image_replacement_not_scene_regeneration(
    bracelet, reference, constraints, lifestyle_snapshot
):
    product = replace(
        bracelet,
        composition="手腕近景，放大产品",
        style_mood="改成白色影棚",
    )
    prompt = build_generation_prompt(
        product,
        reference,
        constraints,
        OutputRole.LIFESTYLE,
        lifestyle_snapshot,
    )

    assert prompt.startswith("这是参考底图编辑任务，不是重新设计或重新生成场景。")
    assert "内部图1是画面底图" in prompt
    assert "内部图2只提供目标产品身份" in prompt
    assert "唯一允许修改" in prompt
    assert lifestyle_snapshot.framing in prompt
    assert lifestyle_snapshot.subject_placement in prompt
    assert "手腕近景，放大产品" not in prompt
    assert "改成白色影棚" not in prompt
    assert "把生活场景改成产品特写" in prompt
```

再按四品类参数化：所有 Prompt 保留 snapshot 的景别、姿势、服装、背景、光线和目标位置；`hand_worn` 不自行改手势；`lifestyle` 不推进镜头；ring Prompt 仍 `<=1200` 且不得注入 `ring_finger_anchor_instruction` 中与快照冲突的“手背朝镜头/拇指位于某侧”；项链只保留层数、连接、重力和接触规则。

- [ ] **步骤 2：运行 Prompt 测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_prompt_builder.py tests/test_skill_portability.py `
  -k "base_image or reference_preservation or composition_conflict" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-06-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-06-red
```

预期：FAIL；现有 Prompt 以“请生成小红书自然上手图”开头，仍发送产品 `composition/style_mood`，并把参考图描述成弱参考。

- [ ] **步骤 3：实现固定编辑前言和快照渲染**

```python
BASE_IMAGE_EDIT_PREAMBLE = """这是参考底图编辑任务，不是重新设计或重新生成场景。
内部图1是画面底图。锁定内部图1的人物身份、身体姿势、手势、服装、背景、道具、镜头角度、景别、主体位置、光线方向、色调和留白。
唯一允许修改：
1. 移除内部图1中的全部原首饰及其直接接触阴影；
2. 在确认的目标位置放入内部图2中的一件目标产品；
3. 为新产品重建必要的接触、遮挡、受力和局部阴影；
4. 清除小面积水印或平台标识。
禁止重新生成、裁切、放大、缩小、换景、换姿势、换衣服、改变人物位置或把生活场景改成产品特写。"""


def _reference_lock_section(snapshot: ReferenceCompositionSnapshot) -> str:
    return (
        f"景别：{snapshot.framing}\n"
        f"机位：{snapshot.camera_angle}\n"
        f"主体位置：{snapshot.subject_placement}\n"
        f"姿势：{snapshot.pose.body}；{snapshot.pose.arm}；{snapshot.pose.hand}\n"
        f"服装：{snapshot.clothing}\n背景：{snapshot.background}\n"
        f"光线：{snapshot.lighting}\n"
        f"唯一替换位置：{snapshot.replacement_target.body_region}"
    )
```

从公共和戒指专用模板中删除 `product.composition`、`product.style_mood`、推荐方式、匹配理由和会改变画面的风格指令。`PromptFragments` 中 `image_one_role` 统一为“底图锁定”，品类 builder 只返回产品保真、展示接触物理和禁止改款；戒指指位必须先与 snapshot target 一致，再只描述戒圈接触，不描述新的镜头或手势。

便携校验器为新 Prompt 增加：固定开头、唯一修改清单、内部图职责顺序、快照字段出现、无冲突构图词、当前 Skill 无 hero。脚本参数固定为一个位置参数 `prompt_path: Path` 和一个必填选项 `--snapshot snapshot_path: Path`；`inspect_run_artifacts.py` 使用 generation 目录中的两个固定文件调用同一 `validate_prompt(prompt_path, snapshot_path)` 函数。

历史单参数调用仍可检查旧 Prompt，但输出 `legacy_read_only=true`，不能作为新 generation gate。

- [ ] **步骤 4：运行四品类 Prompt 与便携契约回归**

运行：

```powershell
python -m pytest tests/test_prompt_builder.py tests/test_skill_portability.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-06-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-06-green
```

预期：PASS；戒指真实样例 Prompt 仍不超过 1200 字；手串、项链和带链吊坠保真字段不丢失。

- [ ] **步骤 5：提交任务 6**

```powershell
git add src/jewelry_on_hand/prompt_builder.py src/jewelry_on_hand/output_roles.py `
  src/jewelry_on_hand/category_policies/bracelet.py `
  src/jewelry_on_hand/category_policies/necklace.py `
  src/jewelry_on_hand/category_policies/ring.py `
  skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py `
  tests/test_prompt_builder.py tests/test_skill_portability.py
git diff --cached --name-only
git commit -m "feat: make generation prompts preserve reference composition"
```

---

### 任务 7：固化双输入、快照和 manifest 的生成审计

**文件：**
- 修改：`src/jewelry_on_hand/generation.py`
- 修改：`src/jewelry_on_hand/cli.py`
- 修改：`tests/test_generation.py`
- 修改：`tests/test_cli.py`

**接口：**
- Consumes：已绑定的 `ReviewDecision`、确认快照、selected review 副本、产品图、按 rank 构建的 Prompt。
- Produces：`generation/NN/scene-reference.*`、`product-reference.*`、`reference-composition-snapshot.json`、`input-manifest.json`；helper 的两个 `--image` 参数指向这两个 run 内副本。
- Manifest schema：`schema_version=1`、`output_role`、两个有序 input 条目，每条含 `order/role/source_path/copied_file/sha256`。

- [ ] **步骤 1：写生成前无副作用与输入顺序失败测试**

```python
from jewelry_on_hand import generation


def test_generation_copies_audited_inputs_and_submits_scene_then_product(
    modern_run, helper_script, monkeypatch
):
    commands = []

    def fake_run_helper(command, **_kwargs):
        commands.append(command)
        return {"data": {"task_id": "fake-task"}}

    monkeypatch.setattr(generation, "_run_helper", fake_run_helper)

    [generation_dir] = run_generation(
        modern_run.paths,
        modern_run.product_image,
        {1: modern_run.prompt},
        helper_script,
        wait=False,
    )

    manifest = read_json(generation_dir / "input-manifest.json")
    scene = next(generation_dir.glob("scene-reference.*"))
    product = next(generation_dir.glob("product-reference.*"))
    assert [item["role"] for item in manifest["inputs"]] == [
        "scene_reference",
        "product_identity",
    ]
    assert (generation_dir / "reference-composition-snapshot.json").is_file()
    image_args = [
        commands[0][index + 1]
        for index, value in enumerate(commands[0][:-1])
        if value == "--image"
    ]
    assert image_args == [str(scene), str(product)]


def test_generation_rejects_snapshot_sha_mismatch_before_writing_or_submit(
    modern_run, helper_script, monkeypatch
):
    modern_run.scene_reference.write_bytes(b"tampered")
    helper_calls = []

    def unexpected_helper_call(command, **_kwargs):
        helper_calls.append(command)
        raise AssertionError("快照预检失败后不得调用 helper")

    monkeypatch.setattr(generation, "_run_helper", unexpected_helper_call)
    with pytest.raises(GenerationError, match="SHA-256.*prepare-review"):
        run_generation(
            modern_run.paths,
            modern_run.product_image,
            {1: modern_run.prompt},
            helper_script,
            wait=False,
        )
    assert helper_calls == []
    assert not any(modern_run.paths.generation_dir.iterdir())
```

另加测试：decision digest 与确认快照不一致、角色不一致、产品图缺失、manifest 两张摘要不一致、复制失败、第二个 job 预检失败时均不得提交任何 rank。

- [ ] **步骤 2：运行测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_generation.py tests/test_cli.py `
  -k "input_manifest or scene_reference or snapshot_sha" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-07-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-07-red
```

预期：FAIL；现有生成目录只有 `hand-reference.*`，helper 直接读取外部源路径，没有 manifest。

- [ ] **步骤 3：在 helper 调用前完成全量预检和输入固化**

```python
def _input_manifest(
    *,
    output_role: OutputRole,
    scene_source: Path,
    scene_copy: Path,
    product_source: Path,
    product_copy: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "output_role": output_role.value,
        "inputs": [
            {
                "order": 1,
                "role": "scene_reference",
                "source_path": str(scene_source.resolve()),
                "copied_file": scene_copy.name,
                "sha256": _file_sha256(scene_copy),
            },
            {
                "order": 2,
                "role": "product_identity",
                "source_path": str(product_source.resolve()),
                "copied_file": product_copy.name,
                "sha256": _file_sha256(product_copy),
            },
        ],
    }
```

在创建任何 `generation/NN` 之前加载并验证：decision、decision snapshot digest、confirmed snapshot、参考 review 副本 SHA、产品图、所有 prompt 与所有目标目录。每个 job 创建目录后复制两张输入和快照，重新计算副本 SHA 写 manifest，再以副本路径调用 `_submit_command`。新 run 不再写 `hand-reference.*`。

- [ ] **步骤 4：运行 generation 与 CLI 回归**

运行：

```powershell
python -m pytest tests/test_reference_composition.py tests/test_generation.py tests/test_cli.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-07-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-07-green
```

预期：PASS；所有 monkeypatch helper 测试确认图片顺序为场景在前、产品在后。

- [ ] **步骤 5：提交任务 7**

```powershell
git add src/jewelry_on_hand/generation.py src/jewelry_on_hand/cli.py `
  tests/test_generation.py tests/test_cli.py
git diff --cached --name-only
git commit -m "feat: persist audited scene and product generation inputs"
```

---

### 任务 8：实现三层 QC、严重错误路由和四栏审核页

**文件：**
- 新建：`src/jewelry_on_hand/qc_review.py`
- 新建：`tests/test_qc_review.py`
- 修改：`src/jewelry_on_hand/models.py`
- 修改：`src/jewelry_on_hand/qc.py`
- 修改：`src/jewelry_on_hand/generation.py`
- 修改：`src/jewelry_on_hand/cli.py`
- 修改：`tests/test_models.py`
- 修改：`tests/test_qc.py`
- 修改：`tests/test_generation.py`
- 修改：`tests/test_cli.py`

**接口：**
- Consumes：generation 双输入、结果图、确认快照、现有 fidelity 与 runtime checklist。
- Produces：`ReferencePreservationCheck`；`build_reference_preservation_checklist(snapshot: ReferenceCompositionSnapshot) -> tuple[tuple[str, str], ...]`；`generation/NN/qc-review.html`；QC JSON 的 `reference_preservation_checks`。
- Produces：`GenerationFailureHistory(reference_structure_rejects: int, model_switch_failures: int)`；首次参考漂移的固定 `REFERENCE_STRUCTURE_RETRY_SUFFIX`；第二次漂移的 `prepare-review` 停止错误。
- CLI：新增必填 `--reference-preservation-checks-json`；历史离线 QC 只读校验不使用该新写入口。

- [ ] **步骤 1：写三层覆盖、严重错误与页面失败测试**

```python
REFERENCE_CHECK_NAMES = {
    "framing_preserved",
    "pose_preserved",
    "subject_placement_preserved",
    "person_preserved",
    "clothing_preserved",
    "background_preserved",
    "lighting_preserved",
    "source_jewelry_removed",
    "replacement_target_preserved",
    "single_target_product",
}


def test_qc_pass_requires_complete_reference_preservation_checks(modern_generation):
    checks = [
        {
            "name": name,
            "question": question,
            "result": "pass",
            "notes": f"逐项对照确认：{name}",
        }
        for name, question in build_reference_preservation_checklist(
            modern_generation.snapshot
        )
    ]
    checks.pop()
    with pytest.raises(ValueError, match="reference_preservation_checks.*完整覆盖"):
        write_qc_result(
            modern_generation.path,
            "pass",
            [],
            [],
            "逐项人工审核",
            reference_preservation_checks=checks,
            fidelity_checks=modern_generation.fidelity_checks,
            checklist_checks=modern_generation.checklist_checks,
        )


@pytest.mark.parametrize(
    "failure",
    [
        "reference_framing_changed",
        "reference_pose_changed",
        "reference_person_changed",
        "reference_clothing_changed",
        "reference_background_changed",
        "reference_lighting_changed",
        "reference_jewelry_leakage",
        "replacement_target_changed",
        "target_product_duplicated",
    ],
)
def test_reference_structure_critical_failures_require_reject(tmp_path, failure):
    with pytest.raises(ValueError, match="必须标记为 reject"):
        write_qc_result(tmp_path, "rerun", [], [failure], "", critical_failures=[failure])


def test_reference_drift_retries_once_without_switching_model(modern_run):
    generation_dir = modern_run.paths.generation_dir / "01"
    generation_dir.mkdir(parents=True)
    write_json(
        generation_dir / "qc.json",
        {
            "status": "reject",
            "passed": [],
            "failed": ["参考景别改变"],
            "notes": "参考底图结构未保持",
            "critical_failures": ["reference_framing_changed"],
        },
    )
    history = generation_failure_history(modern_run.paths.generation_dir)
    assert history.reference_structure_rejects == 1
    assert history.model_switch_failures == 0
    assert select_generation_model(modern_run.paths) == "gpt_image_2"
    assert REFERENCE_STRUCTURE_RETRY_SUFFIX in reference_retry_suffix(history)


def test_second_reference_drift_returns_to_prepare_review(modern_run):
    for index, failure in enumerate(
        ("reference_pose_changed", "reference_background_changed"),
        start=1,
    ):
        generation_dir = modern_run.paths.generation_dir / f"{index:02d}"
        generation_dir.mkdir(parents=True)
        write_json(
            generation_dir / "qc.json",
            {
                "status": "reject",
                "passed": [],
                "failed": [failure],
                "notes": "参考底图结构未保持",
                "critical_failures": [failure],
            },
        )
    with pytest.raises(GenerationError, match="停用当前参考图.*prepare-review"):
        require_reference_retry_allowed(modern_run.paths)
```

`tests/test_qc_review.py` 断言页面同时出现“参考底图 / 产品身份图 / 生成结果 / 已确认构图快照”，使用实际相对图片路径，并在缺少任一输入或结果时拒绝生成页面。所有 reference check 的 `notes` 必须是非空、可验证的人工说明，统一“人工 QC 通过”不得通过校验。

- [ ] **步骤 2：运行 QC 测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_models.py tests/test_qc.py tests/test_qc_review.py tests/test_cli.py `
  -k "reference_preservation or qc_review or reference_framing" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-08-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-08-red
```

预期：FAIL/ERROR；模型没有第三层检查，严重错误码未知，QC 页面模块不存在。

- [ ] **步骤 3：实现第三层检查与状态一致性**

```python
@dataclass(frozen=True)
class ReferencePreservationCheck:
    name: str
    question: str
    result: Literal["pass", "rerun", "fail"]
    notes: str


REFERENCE_PRESERVATION_QUESTIONS = {
    "framing_preserved": "景别、裁切边界、主体大小和留白是否与参考底图一致",
    "pose_preserved": "身体、手臂、手掌朝向和手指关系是否与参考底图一致",
    "subject_placement_preserved": "人物和目标部位在画面中的位置是否保持",
    "person_preserved": "人物身份、脸、发型和可见身体区域是否保持",
    "clothing_preserved": "服装款式、衣领和遮挡关系是否保持",
    "background_preserved": "背景、道具和环境元素是否保持",
    "lighting_preserved": "光向、明暗、色温和整体色调是否保持",
    "source_jewelry_removed": "参考底图中的全部原首饰是否已清除",
    "replacement_target_preserved": "目标产品是否仅出现在确认的替换位置",
    "single_target_product": "结果中是否只有一件目标产品",
}
```

将 9 个严重错误加入 `QcCriticalFailure`、允许集合和必须 reject 集合。`QcResult.__post_init__` 要求 pass 时三层全部 pass；任一 reference check 为 `fail` 或出现严重错误时 status 必须 reject；`rerun` 只允许局部融合、阴影、微小原首饰边缘残留和非核心纹理问题。

在 `generation.py` 中按 `critical_failures` 分类历史，不再用所有 `status != pass` 的总数切模型：

```python
REFERENCE_STRUCTURE_FAILURES = frozenset(
    {
        "reference_framing_changed",
        "reference_pose_changed",
        "reference_person_changed",
        "reference_clothing_changed",
        "reference_background_changed",
        "reference_lighting_changed",
        "reference_jewelry_leakage",
        "replacement_target_changed",
        "target_product_duplicated",
    }
)
REFERENCE_STRUCTURE_RETRY_SUFFIX = (
    "这是当前参考底图唯一一次构图纠偏重跑。逐项锁定已确认快照，"
    "除原首饰替换区域外不得重绘、裁切、移动或重构任何画面元素。"
)


def reference_retry_suffix(history: GenerationFailureHistory) -> str:
    return (
        REFERENCE_STRUCTURE_RETRY_SUFFIX
        if history.reference_structure_rejects == 1
        else ""
    )
```

`generation_failure_history` 对含任一 `REFERENCE_STRUCTURE_FAILURES` 的 qc 只增加 `reference_structure_rejects`，不增加 `model_switch_failures`；其他 `rerun/reject` 才按现有阈值累计模型切换。`run_generation` 在第二次结构 reject 后、创建目录和调用 helper 前停止；首次结构 reject 时把固定 suffix 附加到本次 `prompt.txt` 和实际提交 prompt，便携 Prompt validator 只允许这一段精确后缀。

`run_generation(wait=True)` 下载 `result.png` 后调用 `write_qc_review_page(generation_dir)`；页面只负责呈现，不自动判定。`qc` CLI 先确认页面和四类源文件存在，再加载三份检查 JSON 写 `qc.json`。

- [ ] **步骤 4：运行模型、QC、页面与 CLI 回归**

运行：

```powershell
python -m pytest tests/test_models.py tests/test_qc.py tests/test_qc_review.py `
  tests/test_generation.py tests/test_cli.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-08-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-08-green
```

预期：PASS；现有产品保真和品类 checklist 测试仍完整执行，没有把第三层替代前两层。

- [ ] **步骤 5：提交任务 8**

```powershell
git add src/jewelry_on_hand/qc_review.py tests/test_qc_review.py `
  src/jewelry_on_hand/models.py src/jewelry_on_hand/qc.py `
  src/jewelry_on_hand/generation.py src/jewelry_on_hand/cli.py `
  tests/test_models.py tests/test_qc.py tests/test_generation.py tests/test_cli.py
git diff --cached --name-only
git commit -m "feat: enforce reference preservation quality checks"
```

---

### 任务 9：补齐便携快照、Prompt、QC 和运行产物校验器

**文件：**
- 新建：`skills/jewelry-on-hand-workflow/scripts/validate_reference_snapshot.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- 修改：`tests/test_skill_portability.py`

**接口：**
- Consumes：单个 confirmed snapshot、参考图、output role；generation 目录及三层 QC。
- Produces：便携脚本退出码 `0/1/2` 和中文错误；`inspect_run` 对新 run 的完整审计。
- 便携要求：脚本只能依赖 Python 标准库，不导入 `jewelry_on_hand`。

- [ ] **步骤 1：写脚本级失败测试**

```python
def test_portable_snapshot_validator_checks_file_sha_role_and_single_target(
    tmp_path, valid_snapshot, scene_reference
):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(valid_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(SNAPSHOT_VALIDATOR),
            str(snapshot_path),
            "--reference",
            str(scene_reference),
            "--output-role",
            "hand_worn",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0
    assert "参考构图快照校验通过" in completed.stdout


def test_artifact_inspector_requires_new_generation_manifest(modern_run_root):
    (modern_run_root / "generation/01/input-manifest.json").unlink()
    errors = inspect_run(modern_run_root)
    assert "缺少 generation/01/input-manifest.json" in errors
```

再覆盖：坏 JSON 返回 2 且无 traceback；snapshot SHA/role/rank/target count 错误返回 1；manifest 图片顺序反转、摘要错误、Prompt 缺 snapshot、QC 缺任一第三层 check、check 重复或统一 notes 均被拒绝。

- [ ] **步骤 2：运行测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_skill_portability.py `
  -k "reference_snapshot or input_manifest or reference_preservation" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-09-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-09-red
```

预期：FAIL/ERROR；快照脚本不存在，inspect 仍要求 `hand-reference.*`。

- [ ] **步骤 3：实现便携 schema 和交叉文件校验**

`validate_reference_snapshot.py` 使用 `argparse`，参数固定为位置参数 `snapshot_path: Path`、必填 `--reference reference_path: Path` 和必填 `--output-role {hand_worn,lifestyle}`。

校验与任务 2 保持同名字段和同一错误边界。`validate_prompt_contract.py` 读取 snapshot 后检查 prompt 中的锁定值与禁止冲突词。`validate_qc_record.py` 从 generation 目录向上读取 snapshot、analysis、canonical，重建三层预期集合。`inspect_run_artifacts.py` 对新 run 要求新文件、核对 manifest 顺序和 SHA；对历史 run 进入只读分支，不把 `hand-reference.*` 重命名或重写。

- [ ] **步骤 4：直接运行三个脚本和便携测试**

运行：

```powershell
python -m pytest tests/test_skill_portability.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-09-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-09-green
python -m py_compile `
  skills/jewelry-on-hand-workflow/scripts/validate_reference_snapshot.py `
  skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py `
  skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py `
  skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py
```

预期：pytest PASS；`py_compile` 退出 0 且无输出。

- [ ] **步骤 5：提交任务 9**

```powershell
git add skills/jewelry-on-hand-workflow/scripts/validate_reference_snapshot.py `
  skills/jewelry-on-hand-workflow/scripts/validate_prompt_contract.py `
  skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py `
  skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py `
  tests/test_skill_portability.py
git diff --cached --name-only
git commit -m "feat: validate portable reference replacement artifacts"
```

---

### 任务 10：封住历史 run 追加生成，同时保留只读审计

**文件：**
- 修改：`src/jewelry_on_hand/reference_composition.py`
- 修改：`src/jewelry_on_hand/review_decision.py`
- 修改：`src/jewelry_on_hand/generation.py`
- 修改：`skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- 修改：`tests/test_generation.py`
- 修改：`tests/test_review_decision.py`
- 修改：`tests/test_skill_portability.py`

**接口：**
- Consumes：任意历史或现代 run 目录。
- Produces：`classify_reference_run(paths) -> Literal["modern_snapshot", "legacy_read_only", "damaged"]`；`require_modern_reference_run(paths) -> ReferenceCompositionSnapshot`。
- 行为：读取/inspect 允许 legacy；`record-decision` 和 `generate` 只允许 `modern_snapshot`。

- [ ] **步骤 1：写三态迁移失败测试**

```python
def test_historical_run_without_composition_snapshot_is_read_only(legacy_run):
    assert classify_reference_run(legacy_run.paths) == "legacy_read_only"
    with pytest.raises(GenerationError, match="历史 run 只读.*重新执行 prepare-review"):
        run_generation(
            legacy_run.paths,
            legacy_run.product_image,
            {1: legacy_run.prompt},
            legacy_run.helper_script,
            wait=False,
        )


def test_inspector_accepts_legacy_artifacts_but_reports_read_only(legacy_run):
    completed = subprocess.run(
        [sys.executable, str(ARTIFACT_INSPECTOR), str(legacy_run.paths.root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0
    assert "legacy_read_only=true" in completed.stdout


def test_partial_snapshot_artifacts_are_damaged_not_legacy(modern_run):
    (modern_run.paths.review_dir / "reference_composition_snapshot.json").unlink()
    assert classify_reference_run(modern_run.paths) == "damaged"
```

三态判断必须覆盖候选快照、确认快照、decision digest 和 generation manifest 的部分存在组合；不能通过删除单个文件降级为 legacy。

- [ ] **步骤 2：运行测试并确认 RED**

运行：

```powershell
python -m pytest tests/test_generation.py tests/test_review_decision.py `
  tests/test_skill_portability.py -k "legacy_read_only or damaged or migration" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-10-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-10-red
```

预期：FAIL；现有 legacy bracelet 仍可进入 generation，检查器没有新 schema 三态。

- [ ] **步骤 3：实现三态分类并接入写入口**

```python
def _decision_has_snapshot_digest(path: Path) -> bool:
    if not path.is_file():
        return False
    data = read_json(path)
    if not isinstance(data, dict):
        return False
    digest = data.get("reference_snapshot_sha256")
    return isinstance(digest, str) and bool(re.fullmatch(r"[0-9a-f]{64}", digest))


def classify_reference_run(paths: RunPaths) -> str:
    candidate = paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME
    confirmed = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    decision = paths.review_dir / "review_decision.json"
    present = (candidate.is_file(), confirmed.is_file(), _decision_has_snapshot_digest(decision))
    if present == (True, True, True):
        return "modern_snapshot"
    if present == (False, False, False):
        return "legacy_read_only"
    return "damaged"
```

`require_generation_decision` 在返回前要求 modern；`run_generation` 再次调用并加载 confirmed snapshot，防止绕过 CLI。检查器用相同判定语义但标准库独立实现；legacy 继续验证旧文件，最终输出 `legacy_read_only=true`，damaged 返回非零。

- [ ] **步骤 4：运行迁移与完整 generation/decision/portability 测试**

运行：

```powershell
python -m pytest tests/test_generation.py tests/test_review_decision.py `
  tests/test_skill_portability.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-10-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-10-green
```

预期：PASS；原“legacy bracelet 可继续生成”测试改为“可审计但拒绝新生成”，历史 JSON 不被修改。

- [ ] **步骤 5：提交任务 10**

```powershell
git add src/jewelry_on_hand/reference_composition.py `
  src/jewelry_on_hand/review_decision.py src/jewelry_on_hand/generation.py `
  skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py `
  tests/test_generation.py tests/test_review_decision.py tests/test_skill_portability.py
git diff --cached --name-only
git commit -m "feat: make historical jewelry runs audit only"
```

---

### 任务 11：全文修订 Skill、便携 references 与项目文档

**文件：**
- 修改：`skills/jewelry-on-hand-workflow/SKILL.md`
- 修改：`skills/jewelry-on-hand-workflow/agents/openai.yaml`
- 修改：`skills/jewelry-on-hand-workflow/references/workflow.md`
- 修改：`skills/jewelry-on-hand-workflow/references/prompt-contract.md`
- 新建：`skills/jewelry-on-hand-workflow/references/reference-composition-contract.md`
- 修改：`skills/jewelry-on-hand-workflow/references/qc-checklist.md`
- 修改：`skills/jewelry-on-hand-workflow/references/troubleshooting.md`
- 修改：`reference/manual-workflow.md`
- 修改：`reference/prompt-template.md`
- 修改：`reference/qc-checklist.md`
- 修改：`reference/review-decision-schema.md`
- 修改：`reference/feishu-reference-source.md`
- 修改：`reference/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md`
- 修改：`tests/test_skill_portability.py`

**接口：**
- Consumes：任务 1-10 的最终行为与文件 schema。
- Produces：可发现、渐进披露、无冲突的 Skill；与实现一致的项目主文档。
- Skill 边界：`SKILL.md` 只保留触发条件、角色边界、强制流程、gate 和 reference 路由；详细 schema 只写在对应 reference，不重复粘贴。

- [ ] **步骤 1：按 writing-skills 先做旧 Skill 的 RED 前向测试**

使用三个全新 subagent，均只提供当前未修订 Skill 路径与原始场景，不泄露设计答案。将逐字输出保存为：

```text
output/reference-replacement-workflow/2026-07-14/skill-red/01-reference-priority.md
output/reference-replacement-workflow/2026-07-14/skill-red/02-hero-boundary.md
output/reference-replacement-workflow/2026-07-14/skill-red/03-legacy-run.md
```

三个 exact prompt：

```text
使用 C:/Users/Administrator/Documents/珠宝上手图片生成/skills/jewelry-on-hand-workflow/SKILL.md。
QY027-lifestyle 已人工选择一张半身生活场景参考图，产品图是手腕上的手串。请说明生成时两张图各自提供什么，以及允许改变哪些画面内容。
```

```text
使用 C:/Users/Administrator/Documents/珠宝上手图片生成/skills/jewelry-on-hand-workflow/SKILL.md。
现有 run 的 output_role 是 hero，用户希望继续用当前 Skill 生成。请给出下一步。
```

```text
使用 C:/Users/Administrator/Documents/珠宝上手图片生成/skills/jewelry-on-hand-workflow/SKILL.md。
一个历史 bracelet run 已有 review_decision.json 和 hand-reference.jpg，但没有 reference_composition_snapshot.json。请继续 generate。
```

RED 成功标准：旧 Skill 至少出现一次把参考图说成“参考氛围/可调整构图”、允许 hero、或允许缺快照历史 run 继续生成。若旧 Skill 三项都已正确拒绝，记录实际输出并以自动化测试失败作为 RED 证据，不伪造失败。

- [ ] **步骤 2：先写文档契约失败测试**

```python
def test_skill_declares_reference_base_image_and_excludes_hero():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "只支持 `hand_worn` 和 `lifestyle`" in text
    assert "参考底图是画面结构唯一来源" in text
    assert "产品上手图只提供珠宝身份" in text
    assert "主图必须交给独立主图 Skill" in text
    assert "hand-reference" not in text


def test_skill_links_every_reference_contract_directly():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for name in (
        "workflow.md",
        "prompt-contract.md",
        "reference-composition-contract.md",
        "qc-checklist.md",
        "troubleshooting.md",
    ):
        assert f"references/{name}" in text
```

运行：

```powershell
python -m pytest tests/test_skill_portability.py `
  -k "skill_declares or links_every_reference" -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-11-red `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-11-red
```

预期：FAIL；旧 Skill 仍描述三图和 `hand-reference.*`。

- [ ] **步骤 3：按渐进披露原则全文重写 Skill 与 references**

`SKILL.md` frontmatter 只保留 `name` 与 `description`；description 使用中文触发条件句，明确真人场景首饰替换、手部佩戴/生活场景和参考图严格保留，不概括内部执行步骤。正文删除 hero 生成规则、深色主图例外和旧 hand-reference 产物，改为直接链接五份 references。

`reference-composition-contract.md` 完整写 schema、候选草稿/人工确认差异、不可修改绑定字段、强制停止条件和三态迁移。`workflow.md` 全文改为新四阶段命令；`prompt-contract.md` 写底图编辑开头和快照冲突规则；`qc-checklist.md` 写三层检查和错误代码；`troubleshooting.md` 写 SHA、角色、快照、历史 run、构图漂移的恢复动作。

同步全文修订项目 `reference/` 文档，删除“主图由当前 Skill 生成”“参考图只提供氛围”“产品构图字段可以覆盖参考图”“新 run 写 hand-reference”等冲突段落。保留原有项链 v2、戒指 1200 字和产品保真契约，不在末尾追加补丁说明。

用 skill-creator 的 deterministic generator 更新 `agents/openai.yaml`：

```powershell
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py `
  skills/jewelry-on-hand-workflow `
  --interface 'display_name=Jewelry Scene Replacement' `
  --interface 'short_description=严格保留真人参考图并替换为目标珠宝' `
  --interface 'default_prompt=Use $jewelry-on-hand-workflow to replace jewelry in a hand-worn or lifestyle reference while preserving the reference composition.'
```

- [ ] **步骤 4：执行 Skill GREEN 前向测试和结构校验**

使用三个新的 subagent 原样重跑步骤 1 prompt，输出到 `output/reference-replacement-workflow/2026-07-14/skill-green/`。GREEN 标准分别为：明确锁定参考构图且只替换首饰；拒绝 hero 并指向独立主图 Skill；拒绝历史 run 生成并要求新 `prepare-review`。不得向 subagent 提供预期答案。

运行：

```powershell
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py `
  skills/jewelry-on-hand-workflow
python -m pytest tests/test_skill_portability.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/task-11-green `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-task-11-green
```

预期：quick_validate 输出 Skill 有效；便携测试全部 PASS。人工再核对 `SKILL.md` 少于 500 行，且没有 README、CHANGELOG 或重复 schema 文件。

- [ ] **步骤 5：提交任务 11**

```powershell
git add skills/jewelry-on-hand-workflow/SKILL.md `
  skills/jewelry-on-hand-workflow/agents/openai.yaml `
  skills/jewelry-on-hand-workflow/references/workflow.md `
  skills/jewelry-on-hand-workflow/references/prompt-contract.md `
  skills/jewelry-on-hand-workflow/references/reference-composition-contract.md `
  skills/jewelry-on-hand-workflow/references/qc-checklist.md `
  skills/jewelry-on-hand-workflow/references/troubleshooting.md `
  reference/manual-workflow.md reference/prompt-template.md `
  reference/qc-checklist.md reference/review-decision-schema.md `
  reference/feishu-reference-source.md `
  reference/superpowers/specs/2026-06-12-jewelry-on-hand-generation-workflow-design.md `
  tests/test_skill_portability.py
git diff --cached --name-only
git commit -m "docs: redefine jewelry skill as reference replacement"
```

---

### 任务 12：完成集成回归与 QY018/QY027 不回写对照验证

**文件：**
- 创建：`reference/superpowers/reports/2026-07-14-jewelry-reference-replacement-verification.md`
- 创建：`output/reference-replacement-workflow/2026-07-14/pytest-targeted.txt`
- 创建：`output/reference-replacement-workflow/2026-07-14/pytest-full.txt`
- 创建：`output/reference-replacement-workflow/2026-07-14/pytest-comparison.md`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY018-hand_worn/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY018-lifestyle/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY027-hand_worn/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/QY027-lifestyle/`
- 创建：`output/reference-replacement-workflow/2026-07-14/cross-category/`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/manual-qc.json`
- 创建：`output/reference-replacement-workflow/2026-07-14/real-proof/verification-report.json`

**接口：**
- Consumes：任务 1-11 完整实现、当前飞书参考源只读数据、现有 QY018/QY027 产品图和 analysis。
- Produces：无新增生产接口；提供自动化回归证据和 4 个不回写真实 run 的人工 QC 证据。
- 外部边界：本任务可以读取飞书参考源；真正提交 AIReiter 前必须再次向用户确认计费生成，且无论结果如何都不得回写飞书。

- [ ] **步骤 1：运行全部定向测试并保存原始输出**

```powershell
python -m pytest tests/test_output_role_compatibility.py `
  tests/test_reference_composition.py tests/test_scoring.py `
  tests/test_review_package.py tests/test_review_decision.py `
  tests/test_prompt_builder.py tests/test_generation.py tests/test_qc.py `
  tests/test_qc_review.py tests/test_cli.py tests/test_skill_portability.py -v `
  --basetemp=output/reference-replacement-workflow/pytest/final-targeted `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-final-targeted `
  *> output/reference-replacement-workflow/2026-07-14/pytest-targeted.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

预期：退出 0，所有定向测试 PASS。

- [ ] **步骤 2：运行全量测试并对比已知基线**

```powershell
python -m pytest -v `
  --basetemp=output/reference-replacement-workflow/pytest/final-full `
  -o cache_dir=output/reference-replacement-workflow/pytest/cache-final-full `
  *> output/reference-replacement-workflow/2026-07-14/pytest-full.txt
```

预期：不得出现 6 个已知项链 v1/v2 兼容失败之外的新失败。如果已知失败已被当前工作区其他改动修复，记录更少失败是允许的；不能为了匹配数字恢复失败。`pytest-comparison.md` 逐项列出基线、最终结果、新增失败数（必须为 0）和 6 个历史测试名称。

- [ ] **步骤 3：为 QY018/QY027 建立四个新 review run，禁止复用旧决策**

```powershell
$proof = 'output/reference-replacement-workflow/2026-07-14/real-proof'
$source = 'output/021-20260717-three-role-type-gated-review-20260714-v6'
foreach ($sku in @('QY018', 'QY027')) {
  foreach ($role in @('hand_worn', 'lifestyle')) {
    python -m jewelry_on_hand.cli prepare-review `
      --product-image "$source/$sku-hand_worn/input/product-on-hand.jpg" `
      --analysis-json "$source/$sku-$role/analysis/product_analysis.json" `
      --output-root $proof `
      --run-id "$sku-$role" `
      --output-role $role `
      --reference-cache-root 'output/feishu_reference_cache'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
}
```

预期：四个 run 各有 Top 3、三份 candidate snapshot 与 review.html；不存在 hero run、review_decision 或 generation 目录内容。人工审核必须分别确认 QY018/QY027 的手部与生活场景构图明显不同，生活场景没有被改成腕部特写。

- [ ] **步骤 4：人工确认单一快照并记录决策**

审核者逐个打开四个 `review/review.html`，确认候选快照描述与参考图一致。任一描述不准确时，保留本轮 run 作为失败审计，停止任务 12 并回到任务 2/3 修正字段映射或硬 gate；不得删除旧 run、直接编辑候选 JSON或带错继续。四个页面都确认准确后执行以下交互式命令，人工输入各 run 唯一选择的 `1`、`2` 或 `3`：

```powershell
$proof = 'output/reference-replacement-workflow/2026-07-14/real-proof'
foreach ($name in @(
  'QY018-hand_worn',
  'QY018-lifestyle',
  'QY027-hand_worn',
  'QY027-lifestyle'
)) {
  $role = if ($name.EndsWith('-hand_worn')) { 'hand_worn' } else { 'lifestyle' }
  $rank = [int](Read-Host "$name 选择唯一 rank（1/2/3）")
  if ($rank -notin @(1, 2, 3)) { throw "$name 的 rank 必须是 1、2 或 3" }
  python -m jewelry_on_hand.cli record-decision `
    --run-root "$proof/$name" `
    --action generate_selected `
    --selected-ranks $rank `
    --output-role $role `
    --fidelity-confirmed `
    --reference-snapshot-confirmed
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

预期：decision、canonical、confirmed snapshot 的摘要一致；任何字段不一致都在写文件前失败。把选择 rank、参考编号、composition signature、确认人和确认时间写入 `verification-report.json`。

- [ ] **步骤 5：在获得用户计费确认后生成，未确认则停在可审计 review 状态**

确认后逐个运行：

```powershell
$proof = 'output/reference-replacement-workflow/2026-07-14/real-proof'
foreach ($name in @(
  'QY018-hand_worn',
  'QY018-lifestyle',
  'QY027-hand_worn',
  'QY027-lifestyle'
)) {
  python -m jewelry_on_hand.cli generate `
    --run-root "$proof/$name" `
    --helper-script skills/aireiter-image-generation/scripts/aireiter_image_helper.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

预期：每个 run 只有一个新 generation 目录，包含两张输入副本、快照、manifest、Prompt、模型任务记录、结果和四栏 QC 页面。此步骤不调用水印 Skill、不上传飞书、不删除旧附件。

- [ ] **步骤 6：逐项人工 QC 并写验证报告**

每张结果必须逐项填写 10 条 reference preservation、全部 must_keep 和 runtime checklist。`manual-qc.json` 至少记录：

```json
{
  "sku": "QY027",
  "output_role": "lifestyle",
  "reference_file": "RP000000.jpg",
  "reference_preservation": {
    "framing_preserved": true,
    "pose_preserved": true,
    "subject_placement_preserved": true,
    "person_preserved": true,
    "clothing_preserved": true,
    "background_preserved": true,
    "lighting_preserved": true,
    "source_jewelry_removed": true,
    "replacement_target_preserved": true,
    "single_target_product": true
  },
  "feishu_writeback": false
}
```

验收要求：QY018、QY027 的 4 张结果都保留各自参考构图；手部与生活图不收敛到同一种腕部特写；原首饰全部移除；目标产品只出现一次且结构保真。任一项失败时按 QC 路由记录 reject/rerun，不得把失败结果计入通过率。

- [ ] **步骤 7：在 QY 对照通过后做四品类第二批 review-only 验证**

QY018/QY027 的 4 张结果全部通过后，再用现有真实素材建立 6 个非手串 review-only run；加上 QY018/QY027，覆盖 `bracelet`、`necklace`、`pendant_necklace`、`ring` 各 2 个产品。执行：

```powershell
$root = 'output/reference-replacement-workflow/2026-07-14/cross-category'
$cases = @(
  @{
    Name='necklace-worn'; Role='lifestyle';
    Source='output/multi-category-validation/2026-07-11/real-proof/necklace-worn-single/run-20260711-222800'
  },
  @{
    Name='necklace-handheld'; Role='hand_worn';
    Source='output/multi-category-validation/2026-07-11/real-proof/necklace-handheld-single/run-20260712-final-handheld-01'
  },
  @{
    Name='pendant-worn'; Role='lifestyle';
    Source='output/multi-category-validation/2026-07-11/real-proof/pendant-worn-single/run-20260711-203407'
  },
  @{
    Name='pendant-handheld'; Role='hand_worn';
    Source='output/multi-category-validation/2026-07-11/real-proof/pendant-handheld-double/run-20260712-review-fix-01'
  },
  @{
    Name='ring-open'; Role='hand_worn';
    Source='output/ring-category-validation/2026-07-11/real-proof/open-ring/run-v2'
  },
  @{
    Name='ring-plain-band'; Role='hand_worn';
    Source='output/ring-category-validation/2026-07-11/real-proof/plain-band/run-v2'
  }
)
foreach ($case in $cases) {
  python -m jewelry_on_hand.cli prepare-review `
    --product-image "$($case.Source)/input/product-on-hand.jpg" `
    --analysis-json "$($case.Source)/analysis/product_analysis.json" `
    --output-root $root `
    --run-id $case.Name `
    --output-role $case.Role `
    --reference-cache-root 'output/feishu_reference_cache'
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

预期：6 个 run 都产生类型正确、硬 gate 合格且有三份快照的 Top 3；项链手持参考保留手指接触和垂落位置，项链/吊坠佩戴参考保留原景别，戒指参考目标手与指位一致。第二批只做 review、snapshot 和便携快照校验；四品类 Prompt 由任务 6 的真实 analysis/canonical 参数化测试覆盖。若要提交 6 张额外计费生成，必须取得单独授权，仍不得回写飞书。

- [ ] **步骤 8：运行最终产物检查与 diff 检查**

```powershell
Get-ChildItem 'output/reference-replacement-workflow/2026-07-14/real-proof' -Directory | `
  Where-Object { $_.Name -match '^QY0(18|27)-(hand_worn|lifestyle)$' } | `
  ForEach-Object {
    python skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py $_.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
git diff --check
git status --short
```

预期：所有已实际生成并 QC 的 run 检查通过；未获计费确认而没有 generation 的 run 在报告中标记 `review_only`，不伪报完成；`git diff --check` 退出 0；没有飞书写回产物。

- [ ] **步骤 9：写验证报告并提交（不提交大图与临时日志）**

在 `reference/superpowers/reports/2026-07-14-jewelry-reference-replacement-verification.md` 记录：定向测试命令与结果、全量基线/最终差异、四个 proof run 的 run-id/rank/参考编号/AIReiter 任务号、10 条参考保留检查结果、产品保真结论、失败与重跑记录、`feishu_writeback=false`。原始 pytest 输出、Prompt、manifest、QC JSON 和图片只保留在 `output/`，不要用 `git add -f` 提交。

```powershell
git add reference/superpowers/reports/2026-07-14-jewelry-reference-replacement-verification.md
git diff --cached --name-only
git commit -m "test: verify reference preserving jewelry workflow"
```

如果集成验证暴露实现缺陷，先回到对应任务补 RED/GREEN 和独立修复提交，再重新执行任务 12；不得把未解释的生产修复混入验证报告提交。

---

## 完成定义

- [ ] 当前 Skill 的全部入口都拒绝 `hero`，全局 `OutputRole.HERO` 仍可被未来主图 Skill 导入。
- [ ] 每个新 run 的 Top 3、人工确认快照、decision digest、generation 副本和 manifest 可以通过 SHA-256 互相追溯。
- [ ] Prompt 不再把产品 `composition/style_mood` 或品类近景偏好当成画面指令，参考图画面结构是唯一构图来源。
- [ ] 送模只读取 run 内 `scene-reference.*` 与 `product-reference.*`，顺序固定且与 manifest 一致。
- [ ] QC 三层检查完整、唯一、有人工备注；任何参考结构严重变化都不能得到 pass 或普通 rerun。
- [ ] 历史 run 可检查但不能追加生成，部分迁移文件被判定为 damaged 而不是 legacy。
- [ ] Skill 与项目文档全文一致，不存在“当前 Skill 生成主图”“参考图只是氛围”“hand-reference 是新产物”等旧规则。
- [ ] 所有定向测试通过，全量测试相对已知基线无新增失败。
- [ ] QY018/QY027 的真实对照没有任何飞书写回；若执行了计费生成，4 张结果均有逐项人工 QC 和完整审计。
