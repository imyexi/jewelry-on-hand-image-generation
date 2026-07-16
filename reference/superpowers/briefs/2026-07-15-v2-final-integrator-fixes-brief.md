# 产品保真 v2 最终 integrator 残留 Important 修复简报

## Finding 1：absent v2 缺失 layer 键被当作 null

`pendant_semantics` v2 是严格四字段对象。当前核心 `PendantSemantics.from_dict()` 与两个 portable validator 都使用 `.get("layer")`，导致完全缺少 `layer` 键的 absent canonical 被当作显式 `layer:null` 接受。

要求：

- 先写 RED：直接 `PendantSemantics.from_dict()`、嵌套 `ProductFidelityConstraints.from_dict()`、portable inspector、portable QC 均拒绝缺少 `pendant_semantics.layer` 的 absent v2；
- 核心抛中文 `ValueError`，portable 非零退出、中文无 traceback，QC 不改写文件；
- 显式 `"layer": null` 的合法 absent v2 继续通过；
- 只要求 v2 对象显式含四个键，不改变历史 v1。

## Finding 2：portable 未镜像 present 自由文本冲突门禁

核心已对 10 类语义字段拒绝 6 个规格冲突短语，但 portable inspector/QC 未执行等价规则，事后篡改的 present canonical 仍可能被认证。

要求：

- 在纯 Python portable 层定义并复用同一份 6 短语集合和 10 路径遍历逻辑；inspector 与 QC 不得复制两套；
- 6 个短语：`无吊坠`、`未见吊坠`、`吊坠不存在`、`吊坠缺失`、`必须新增第二颗吊坠`、`要求生成第二颗吊坠`；
- 10 路径：`detected_keywords[]`、`must_not_change[]`、`must_keep[].name/source_text/normalized_keyword/location/visual_shape/relationship/forbid[]/qc_question`；
- 先写 RED：共享 helper 的 10×6 矩阵、inspector 进程级拒绝、QC 进程级拒绝；错误含精确字段路径和短语、中文无 traceback，QC 不改写；
- 合法保护句 `禁止新增第二颗吊坠` 必须在 helper、inspector、QC 中继续通过；
- portable 不导入项目 package；ring/bracelet 不新增项链 present 规则。

## 允许修改

- `src/jewelry_on_hand/models.py`
- `skills/jewelry-on-hand-workflow/scripts/inspect_run_artifacts.py`
- `skills/jewelry-on-hand-workflow/scripts/validate_qc_record.py`
- `tests/test_product_fidelity_v2.py`
- `tests/test_skill_portability.py`
- `reference/superpowers/briefs/2026-07-15-v2-final-integrator-fixes-report.md`

不得修改生产核心 validator、戒指、HERO、飞书、v6、`output_role`、reference composition 或 provider helper；不得调用 provider，不得暂存或提交。

## 验证

至少运行：

```powershell
uv run pytest tests/test_product_fidelity_v2.py tests/test_skill_portability.py -q
uv run pytest tests/test_models.py tests/test_review_decision.py tests/test_generation.py tests/test_prompt_builder.py tests/test_qc.py -q
```

报告必须记录逐 finding RED/GREEN、显式 null 正向、合法保护句正向、portable 无 package import 与修改文件清单。
