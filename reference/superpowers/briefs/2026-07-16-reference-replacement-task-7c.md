# 参考底图替换工作流：任务 7C QC 稳定 ID 与参数契约

## 目标

把主工作区当前 `qc.py` 的并发扩展固化为纯提交 tree 可用的 QC 基础契约，提供稳定 `qc_check_id()` 与当前四品类/产品保真参数接口，为 Task 7 CLI 和后续三层 QC 提供可追溯 checklist。

## 范围

- 修改并提交：`src/jewelry_on_hand/qc.py`
- 修改并提交：`tests/test_qc.py`

不得修改 generation、CLI、models、product_analysis、product_fidelity、review_decision、便携脚本或其他测试。

## 契约

- `qc_check_id(question)` 对规范化问题文本生成稳定、小写、确定性 ID；相同问题稳定，不同问题不得碰撞于测试样例；空/非字符串中文 fail-closed。
- `build_qc_checklist(...)` 当前接口支持 `product_analysis` 与 `fidelity_constraints`，并保留既有 `product_type/display_mode/must_keep` 兼容路径；不得用宽松默认让现代调用绕过保真约束。
- checklist 每项具有稳定 `id`、非空 `question` 与确定顺序；ID 必须从问题文本唯一生成，禁止位置索引漂移。
- 四品类问题覆盖现有保真结构；pendant_necklace 必须包含吊坠数量/层/位置/朝向/连接与禁止新增第二颗吊坠，bracelet/necklace/ring 不得被吊坠问题污染。
- QC 参数中的产品分析与保真约束必须品类一致、状态可用于生成；digest/结构不一致中文 fail-closed。
- 不在本任务实现 Task 8 的参考保留三层判定或严重错误路由；只稳定 checklist 构建与 ID。

## TDD 与验证

- 从最新 HEAD 建全新 detached worktree；主两文件先做 output只读快照与 SHA，三方保留用户并发。
- 先在纯 HEAD 取得 `qc_check_id`/新参数缺失的 RED，再最小 GREEN。
- 必测：ID 稳定/差异/非法输入；旧兼容与现代严格路径；四品类问题集合和顺序；吊坠字段全覆盖/非吊坠隔离；品类、状态、摘要不一致拒绝。
- 运行：

```powershell
python -m pytest tests/test_qc.py tests/test_product_fidelity_v2.py `
  tests/test_models.py -v `
  --basetemp=output/t07c -o cache_dir=output/cache-t07c
```

- 纯 tree 导入、`py_compile`、`git diff --check`；不跑全量。

## 安全

- 用户已持续授权同类并发/HEAD前进自动重基线；主树禁止写入或 restore/checkout。
- 只提交两文件，detached非amend + 主index plumbing；工作字节SHA不变、索引空、tested/detached/main tree一致。
- 报告全文写入 `.superpowers/sdd/reference-replacement-task-7c-report.md`。
- 禁止真实网络、飞书、生图或付费接口。
