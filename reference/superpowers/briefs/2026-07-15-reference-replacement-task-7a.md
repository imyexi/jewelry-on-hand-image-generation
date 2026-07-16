# 参考底图替换工作流：任务 7A 飞书参考源前置固化

## 目标

把主工作区当前未跟踪的 `src/jewelry_on_hand/feishu_reference_source.py` 及其直接模块测试固化为独立、可导入、可审查的提交，为后续 CLI 与 Task 7 提供稳定依赖。保留当前文件已有功能，不重写业务规则。

## 范围

- 新建并提交：`src/jewelry_on_hand/feishu_reference_source.py`
- 新建并提交：`tests/test_feishu_reference_source.py`
- 只有在纯提交 tree 可独立运行且不依赖未提交 CLI 时，才可一并提交 `tests/test_feishu_enrichment_cli.py`；否则保留该文件在主工作区，不纳入本任务。

不得修改或提交 `src/jewelry_on_hand/cli.py`、`generation.py`、产品保真、QC、模型或其他并发文件。不得调用真实飞书、网络、生图或付费接口；所有外部命令/API 必须由测试替身拦截。

## 契约

- 模块在纯当前 HEAD tree 中可导入，不依赖主工作区未提交模块。
- 飞书配置、记录读取、附件下载、语义补齐导入和审计接口保持当前实现的公开签名与中文错误行为。
- 对空字段只补齐、不覆盖已有值；失败与冲突进入审计，不能静默当成功。
- 外部 CLI/网关发现失败必须给出中文可行动错误；测试不得访问真实网络。
- Windows 路径、UTF-8 JSON 和附件文件名处理保持确定性。

## 验证

1. 以主工作区当前未跟踪文件为行为基线，在 `output/` 下 detached worktree 重建文件。
2. 先运行已有直接测试确认 RED/基线；若测试本身已经对应实现，可补最小缺口 RED，不得为了全绿删除断言。
3. 至少运行：

```powershell
python -m pytest tests/test_feishu_reference_source.py -v `
  --basetemp=output/t07a -o cache_dir=output/cache-t07a
```

4. 若 `test_feishu_enrichment_cli.py` 在纯 tree 可收集，再运行并决定是否纳入；若依赖未提交 CLI，报告为后续接缝，不纳入提交。
5. 运行 `py_compile` 与 `git diff --check`。

所有测试显式设置隔离 worktree 的 `PYTHONPATH=<worktree>/src`。

## 安全集成

- 基线以执行时最新主 HEAD 为准；用户已持续授权保留同类并发 HEAD 前进并自动重基线。
- 开始与集成前记录主工作区两个目标文件状态和 SHA；不得覆盖主工作区未跟踪内容。
- detached 提交只含获准文件；主树使用 index plumbing 写入已测试 blob，创建非 amend 提交。
- 集成后主工作区原文件字节不变、索引为空，tested/detached/main commit tree 一致。
- 报告写入 `.superpowers/sdd/reference-replacement-task-7a-report.md`。
