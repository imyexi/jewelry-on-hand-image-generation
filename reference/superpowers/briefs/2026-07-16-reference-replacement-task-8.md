# 参考底图替换工作流：任务 8 三层 QC 与四栏审核页

## 目标

在已固化的五输入 generation 审计之上增加参考底图保留层 QC，使 `pass` 必须同时通过参考保留、产品保真和 runtime checklist；实现参考结构严重错误的一次固定重跑与第二次停用参考；生成四栏人工 QC 页面。不得自动做视觉判定，不得调用真实生图或飞书。

## 范围

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

只允许上述十个文件。Task 9 的便携检查器、Task 11 文档和真实 proof 不在本任务。

## 参考保留层

定义不可变 `ReferencePreservationCheck(name, question, result, notes)`，`result` 只允许 `pass/rerun/fail`。固定十项：

- `framing_preserved`
- `pose_preserved`
- `subject_placement_preserved`
- `person_preserved`
- `clothing_preserved`
- `background_preserved`
- `lighting_preserved`
- `source_jewelry_removed`
- `replacement_target_preserved`
- `single_target_product`

`build_reference_preservation_checklist(snapshot)` 返回固定顺序 `(name, question)`。每项 notes 必须是非空、可验证的人工说明；“人工 QC 通过”等统一空泛说明拒绝。

## 三层状态契约

- `pass`：十项 reference checks 全部 pass、全部 fidelity checks pass、全部 checklist checks pass，三层集合完整、ID/名称唯一、问题与期望一致。
- `reject`：任一 reference check 为 fail，或出现参考结构严重错误。
- `rerun`：仅允许局部融合、阴影、小面积原首饰边缘残留和非核心纹理问题；不得用于构图、人物、姿势、服装、背景、光线、替换位置改变、明显原首饰泄漏或产品复制。
- 严重错误码固定：`reference_framing_changed`、`reference_pose_changed`、`reference_person_changed`、`reference_clothing_changed`、`reference_background_changed`、`reference_lighting_changed`、`reference_jewelry_leakage`、`replacement_target_changed`、`target_product_duplicated`。
- `source_jewelry_removed` 的轻微边缘残留可 rerun；肉眼可辨主体残留必须用 `reference_jewelry_leakage` reject。

CLI `qc` 的现代写入口必须显式接收三份检查 JSON，其中 `--reference-preservation-checks-json` 必填；历史离线 QC 仅只读，不得用现代写入口伪造。

## 严重错误历史与模型切换

定义 `GenerationFailureHistory(reference_structure_rejects, model_switch_failures)`。包含任一结构严重错误的 QC 只增加 `reference_structure_rejects`，不增加模型切换计数；其他产品保真/局部融合非 pass 才累计模型切换。

第一次结构 reject：模型仍为 `gpt_image_2`，下一次 prompt 精确追加一次固定 `REFERENCE_STRUCTURE_RETRY_SUFFIX`：

`这是当前参考底图唯一一次构图纠偏重跑。逐项锁定已确认快照，除原首饰替换区域外不得重绘、裁切、移动或重构任何画面元素。`

第二次结构 reject：在创建 generation 目录和 helper 调用前 fail-closed，停用当前参考图并要求重新 `prepare-review`。不得自动换未确认 rank。

## 四栏 QC 页面

`write_qc_review_page(generation_dir)` 生成 `qc-review.html`，同时展示：参考底图、产品身份图、生成结果、已确认构图快照。图片使用真实相对路径；快照以可读结构呈现。缺 scene/product/result/snapshot 任一文件都拒绝生成页面。页面只呈现，不自动写 QC 结论。

`run_generation(wait=True)` 下载结果后生成页面；页面或输入缺失时不得伪报成功。

## TDD 必测

- pass 缺任一 reference/fidelity/checklist 项拒绝；重复、未知、问题不匹配、空泛 notes 拒绝。
- 九个严重错误用 rerun 均拒绝；轻微允许 rerun 的问题与严重泄漏区分。
- 第一次结构 reject：history 只加结构计数、模型不切换、suffix 精确一次进入 prompt.txt 和 helper prompt。
- 第二次结构 reject：目录/helper 零副作用，要求 prepare-review。
- 非结构失败按既有模型切换阈值累计。
- 页面四栏、相对路径、快照内容；缺任一文件拒绝。
- CLI 三份 JSON、历史只读、hero/legacy gate；Task 7 的 future checklist fail-closed 在本任务被真实接入。
- 现有产品保真与 QC stable item/ID 契约不回归。

RED：

```powershell
python -m pytest tests/test_models.py tests/test_qc.py tests/test_qc_review.py tests/test_cli.py `
  -k "reference_preservation or qc_review or reference_framing" -v `
  --basetemp=output/t08-red -o cache_dir=output/cache-t08-red
```

GREEN：

```powershell
python -m pytest tests/test_models.py tests/test_qc.py tests/test_qc_review.py `
  tests/test_generation.py tests/test_cli.py -v `
  --basetemp=output/t08-green -o cache_dir=output/cache-t08-green
```

使用短 `output/` basetemp 与隔离 `PYTHONPATH`；禁止真实 helper、网络、飞书、生图。

## 安全与集成

- 从执行时最新 HEAD 建全新短路径 detached worktree。十个主目标文件先复制到 `output/` 只读快照并记录 SHA；主树禁止 restore/checkout/merge/rebase/reset/文件写入。
- 正确选择各文件 merge-base，逐块保留 Task 1-7 已提交契约和当前用户并发 Task 8 代码；不得用主工作字节覆盖 HEAD。
- 同类并发/HEAD 前进已持续授权，自动重新快照、三方合并、重测。
- detached 非 amend提交，主 index plumbing 非 amend；主工作字节不变、索引空、tested/detached/main tree 一致。
- 报告全文写入 `.superpowers/sdd/reference-replacement-task-8-report.md`，只保留唯一当前状态。
