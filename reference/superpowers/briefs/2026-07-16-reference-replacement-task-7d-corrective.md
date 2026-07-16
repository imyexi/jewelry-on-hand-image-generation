# 参考底图替换工作流：任务 7D 终审 corrective

## 背景与安全边界

Task 7D 主提交 `88cd0fb227b8b6922d30ba26d7852fd458968e9c` 已固化模型扩展，但独立终审发现 3 个 Important。此前代理误在主工作区执行 restore，两个用户文件已按原 SHA-256 精确恢复。新代理不得在主工作区执行 `git restore`、`git checkout`、merge、rebase、reset 或任何文件写入；主工作区只允许只读 SHA/HEAD/index 检查与最终 index plumbing。

允许修改并提交的文件仅限：

- `src/jewelry_on_hand/models.py`
- `tests/test_models.py`
- `src/jewelry_on_hand/review_decision.py`
- `tests/test_review_decision.py`

## 必修问题

1. `ReviewDecision.from_dict()` 可保留默认宽松供历史只读，但 `require_generation_decision()` 必须总是启用 `require_reference_snapshot_sha256=True`。任何缺失 digest 的生成决策都不能进入 generation gate；历史读取仍可审计但不可生成。
2. 实际 writer 必须复用 `ReviewDecision.to_dict()` 或同一个唯一严格序列化 helper；删除私有 writer 与模型边界漂移。现代 bundle 注入 digest 后可写，旧 writer 对 generation action 继续拒绝。
3. `ProductFidelityConstraints` 必须按 `source.product_type` 绑定 `pendant_semantics`：
   - `bracelet`、`ring`、普通 `necklace` 必须 `presence=absent`，不得携带吊坠结构。
   - `pendant_necklace` 的现代/v2 约束必须 `presence=present`，并具备必要 count、layer、position、orientation、connection。
4. 对 present 吊坠，position/orientation/connection 不得为 `None`、空值或错误类型。允许值必须从当前上游真实 canonical 数据和现有测试中归纳，不得随意发明导致合法数据误拒；若当前数据是开放中文描述，至少执行去空白后的非空结构校验，并在报告说明未使用闭枚举的原因。
5. 严格排除 bool 伪装整数；错误文案中文且指出字段。

## TDD 与验证

- 先复现终审问题 RED：生产 `require_generation_decision()` 接受无 digest；三种非吊坠品类携带 present；pendant_necklace absent；position/orientation/connection 为 None。
- GREEN 后运行：

```powershell
python -m pytest tests/test_models.py tests/test_review_decision.py `
  tests/test_output_role_compatibility.py -v `
  --basetemp=output/t07d-fix -o cache_dir=output/cache-t07d-fix
python -m pytest tests/test_cli.py -k "review_decision or generate" -v `
  --basetemp=output/t07d-fix-cli -o cache_dir=output/cache-t07d-fix-cli
```

- 显式隔离 `PYTHONPATH=<worktree>/src`；纯 tree 导入、`py_compile`、`git diff --check`。
- 不运行全量，不访问网络、飞书或生图。

## 集成

- 从最新主 HEAD 创建新的 `output/` detached worktree；将四个主工作区用户文件先复制到 `output/` 只读快照并记录 SHA，再在隔离 worktree 三方合并。
- 主工作区目标 SHA 如有同类并发变化，按持续授权重新快照、合并、重测。
- detached 非 amend 提交；主树只用 index plumbing 创建非 amend corrective。
- 集成前后主工作区四文件 SHA 不变、索引为空，tested/detached/main tree 一致。
- 全文重写 `.superpowers/sdd/reference-replacement-task-7d-report.md` 为唯一当前状态。
