# Task 9 全流程 CLI 与历史兼容回归实施计划

> **执行要求：** 在当前绑定分支内按严格 TDD 顺序逐场景推进；不派发子代理，不覆盖派发前脏内容，受保护文件只形成相对 Task 9 baseline 的 supplemental diff。

**目标：** 证明普通项链佩戴、带链吊坠手持、历史手串旧 JSON 均能从 CLI 依次完成 `prepare-review → record-decision → generate → qc`，并补齐端到端暴露的最小数据流和兼容映射。

**实现方式：** 测试从 `jewelry_on_hand.cli.main()` 驱动四个阶段，参考图库边界使用可控本地 `ReferenceRow`，生成边界使用真实磁盘 helper 脚本和真实 `subprocess.run`。现代项链必须校验 confirmation snapshot、保真确认、展示模式和结构字段；QC 必须从标准 generation 路径反推 constraints，并完整传递 fidelity checks 与 critical failures；旧手串继续允许无现代分类字段和无 snapshot。

**技术栈：** Python 3、argparse、pytest、临时目录、本地 helper 子进程、JSON 磁盘产物。

## 全局约束

- 规范品类仅为 `bracelet`、`necklace`、`pendant_necklace`；`pendant_only`、`unknown` 不得生成。
- 项链输入只接受 `worn_source`，展示可为 `worn` 或 `hand_held`；同一产品只支持 1 至 3 层，拒绝多件独立叠戴。
- `record-decision` 保存并验证产品确认快照、`fidelity_confirmed` 和人工纠正；`generate` 重新执行 gate，非法状态不得调用 helper。
- 所有测试输出写入 `output/multi-category-validation/2026-07-11/`，不提交。

### 场景一：普通项链 worn

**文件：** 修改 `tests/test_cli.py`；仅在 RED 证明后最小修改 `src/jewelry_on_hand/cli.py`、`src/jewelry_on_hand/generation.py` 或 `src/jewelry_on_hand/review_package.py`。

- [ ] 写一个完整 CLI 链路测试：准备 worn_source 普通项链分析、本地项链参考图和 helper；依次调用四个子命令。
- [ ] 断言 RED 来自缺失数据流或兼容映射，不是 fixture/路径错误。
- [ ] 做最小实现并重跑该用例至 GREEN。
- [ ] 验证 analysis、selected references、review decision snapshot、generation/01、helper 命令证据和 qc.json。

### 场景二：带链吊坠 hand_held

**文件：** 修改 `tests/test_cli.py`；生产代码范围同场景一。

- [ ] 写一个完整 CLI 链路测试：输入仍为 worn_source，人工确认 hand_held 和完整吊坠结构。
- [ ] 先运行并确认 RED，再做最小实现至 GREEN。
- [ ] QC 使用与 must_keep 精确对应的 fidelity check，并验证 pass 结果。
- [ ] 另由该场景覆盖 CLI `critical_failures` 的传递和 pass 拒绝边界，确保失败时不写 qc.json。

### 场景三：历史手串旧 JSON

**文件：** 修改 `tests/test_cli.py`；如路径或导入兼容确有缺口，精确修改 `tests/test_run_paths.py` 或 `tests/test_package_import.py`。

- [ ] 使用不含现代分类字段的旧手串 analysis JSON 驱动完整四阶段。
- [ ] 先运行并确认 RED，再做最小兼容实现至 GREEN。
- [ ] 验证 decision 可不含 confirmation snapshot，生成仍经过 fidelity gate，QC 可从标准路径写入。

### 最终验证与交付

- [ ] 运行 `python -m pytest tests/test_cli.py tests/test_generation.py tests/test_run_paths.py tests/test_package_import.py -v`。
- [ ] 运行 `python -m pytest -q`。
- [ ] 运行 `git diff --check`，逐文件执行 `git diff --no-index` 对比 Task 9 baseline。
- [ ] 将 RED/GREEN、helper 命令、测试结果、baseline 增量和风险写入 `.superpowers/sdd/task-9-report.md`。
- [ ] 只有派发前 clean 文件确有变更时才精确暂存并以中文 Conventional Commit 提交；受保护文件永不整体暂存。
