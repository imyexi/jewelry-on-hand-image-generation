# 任务 4 执行报告：戒指产品上手身份图

## 结论

交付状态：`PARTIAL_QC_PASS`。

AIReiter 服务恢复后，JH025、JH026、JH501 的既有 `generation/02` 均使用全新任务 ID 各提交一次并完成，三项共消耗 7.5 credits。每项都只发送两张输入：图 1 为 `hand-reference.jpg`，图 2 直接使用当前 run 的 `input/product-on-hand.jpg`；`product-detail.jpg` 只用于人工结构复核和 QC，没有送模。

三张结果均已完成 5 条 fidelity 与 18 条 runtime checklist 的新一轮视觉 QC。严格结论为：JH025 `pass`，JH026 `reject`，JH501 `reject`。因此只将 JH025 复制到 `output/ring-feishu-test/2026-07-15/final-on-hand-identity/`；没有把两张 reject 图片包装成最终交付，也没有创建 `generation/03`。

## 恢复提交与结果

| SKU | Rank | 新 out_task_id | submit 次数 | provider | credits | Prompt | QC |
| --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| JH025 | 1 | `JH025-hand-worn-recovery2-rank-01-f8b72a0d` | 1 | completed | 2.5 | 1182 字，通过 | pass |
| JH026 | 2 | `JH026-hand-worn-recovery2-rank-02-671206f4` | 1 | completed | 2.5 | 1168 字，通过 | reject |
| JH501 | 2 | `JH501-hand-worn-recovery2-rank-02-5726731c` | 1 | completed | 2.5 | 1193 字，通过 | reject |

恢复脚本先落盘唯一任务 ID，再执行一次 submit；提交异常时只查询同一 ID，不会自动再次提交。上传写超时提高到 300 秒，查询过程允许恢复瞬时不完整分块响应。JH025 首次查询出现一次 `IncompleteRead`，随后通过 `--resume-poll` 只恢复轮询，没有再次 submit。

JH501 使用修复后的 `recovery-attempt-2-prompt.txt`，Prompt 为 1193 字且通过契约校验。此前失败尝试留下的 `generation/02/prompt.txt` 保持原样，没有回写或伪装成新 Prompt。

## 两图身份门禁

| SKU | 图 1：手部参考 SHA-256 | 图 2：产品上手身份 SHA-256 | detail SHA-256（仅 QC） |
| --- | --- | --- | --- |
| JH025 | `9795d9d37d05eb9d791b7662099188e16b1ce5f8503d92cd0b72456ad45533da` | `9795d9d37d05eb9d791b7662099188e16b1ce5f8503d92cd0b72456ad45533da` | `6d6f174ec919af700c1844875217e6c454fc3b3370da0c7998826d58cb3be832` |
| JH026 | `c2d6f0e730783c0ba443c84a2b9103eb5e49a72924932d0f443bbb469e264ac1` | `c2d6f0e730783c0ba443c84a2b9103eb5e49a72924932d0f443bbb469e264ac1` | `f721e4ed80f6a9c67af5e11b555c44c5ee0c6b56ba71997761fac59c14b7e7af` |
| JH501 | `c2d6f0e730783c0ba443c84a2b9103eb5e49a72924932d0f443bbb469e264ac1` | `56130776ea22009e654373f01083b048fd2bc19b6825f92c882d8aa15d7b05ee` | `f06927160584c91447c4143636ec7793c83eb1eba2536710d5e58baffaabe925` |

三个 `product-identity.jpg` 均与各自 `input/product-on-hand.jpg` 哈希一致，且与 detail 图哈希不同。提交请求审计均记录 `product_detail_sent=false`。

JH025 和 JH026 的所选手部参考图恰好与各自产品上手身份图字节相同。这不违反“两张输入且第二张为产品上手图”的调用合同，但会导致手部来源无法仅凭输出独立归因。该限制已写入 JH025 QC 和 `verification.json`；后续生产参考集应避免让图 1 与图 2 为同一字节文件。

## 下载完整性

JH026 和 JH501 的结果 PNG 首次下载即通过完整解码。JH025 首次下载只得到 911168 字节，虽有 PNG 文件头，但 Pillow 报 `Truncated File Read`。本次没有重新生成或重新提交，而是使用同一个 completed 回执 URL 重下：

- 截断文件保留为 `result-truncated-transport.png`，SHA-256 为 `4b891340c5dad20579cfe5f5109cd1cd0ab4567d5ce7903455470bc0f824a800`；
- 完整 `result.png` 为 2482844 字节、1536×2048 RGB，SHA-256 为 `f592e4ff8d1481a6c31e3eb950c07e1fb4b456dfaa3c71ca744d9278d5b96a6b`；
- 传输恢复审计位于 `generation/02/download-recovery.json`。

## 视觉 QC

### JH025：pass

- 仅一颗圆润白色五角星主体，轮廓、朝向和相对尺寸保持；
- 对侧三颗半透明白珠清晰可数，另一侧蓝绿珠和暖金隔件可辨；
- 戒指位于左手食指根部，环绕、遮挡、接触阴影和手部结构正常；
- 只有一枚戒指，没有额外首饰、文字、水印或 logo；
- 5/5 fidelity 与 18/18 checklist 均为 pass。

### JH026：reject

- 乳白大圆珠和淡紫灰珠仍在，主色域基本保持；
- 花朵、卷纹和镶绿色小石的暖金隔件再次缺失，或被普通圆环/间隔片简化；
- 关键识别结构与相邻关系被删除和重组，触发 `ring_structure_mismatch`；
- 3/5 fidelity 与 13/18 checklist 为 pass，其余结构项失败。

### JH501：reject

- 生成图把浅淡半透明蓝主石改成更深、更饱和的蓝色，比例也发生变化；
- 双层颗粒围边、戒肩亮点和开口端点关系被重设计；
- 靠近戒面的突起端件缺少产品证据，属于结构补造，触发 `ring_structure_mismatch`；
- 1/5 fidelity 与 9/18 checklist 为 pass，其余产品保真项失败。

## 产物与终态

- 通过图：`output/ring-feishu-test/2026-07-15/final-on-hand-identity/JH025-hand-worn.png`；
- 两张 reject 测试图保留在对应 `runs-on-hand-identity-v3/<SKU>-hand-worn/generation/02/result.png`；
- 三份完整 QC 位于各自 `generation/02/qc.json`；
- 权威汇总为 `output/ring-feishu-test/2026-07-15/verification.json`；
- 当前终态为 `1/3 QC pass; 2/3 reject`，`delivery_completed=false`。

最终自动验证结果：

- 三份实际提交 Prompt 均通过 `validate_prompt_contract.py`；
- 三份新 QC 均通过 `validate_qc_record.py`；
- 三张 generation 结果与一张 final 副本均通过完整 PNG 解码；
- JH025、JH026 的 run inspector 通过，均报告 `legacy_read_only=true`；
- JH501 inspector 只报告不可覆盖的历史 `generation/02/prompt.txt` 缺少 `参考图文件：`，实际提交的 `recovery-attempt-2-prompt.txt` 已通过；
- generation、Prompt、QC 与 helper UTF-8 定向回归为 `219 passed in 1.38s`。

若要继续追求三张全部通过，需要用户再次明确授权创建 `generation/03`；当前授权范围内不再追加扣费。

## 工作区约束

- 未写回飞书；
- 未覆盖或删除 `generation/01`、历史恢复错误记录或 JH501 历史 Prompt；
- 未创建 `generation/03`；
- 未执行 `git add`、commit、stash、checkout 或 reset。
