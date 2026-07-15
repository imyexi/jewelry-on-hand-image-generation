# 戒指送模产品身份图来源修订设计

## 1. 背景与问题

2026-07-15 的真实货盘测试中，戒指 generation 将经过确认的平铺细节图作为内部图 2。虽然细节图便于识别主石、开口和装饰，但模型需要把平铺结构重新解释为环绕手指的立体佩戴状态，增加戒圈、珠序、开口和镶嵌被重绘的概率。

当前根因位于 `generation._product_identity_path()`：戒指 run 只要存在 `input/product-detail.*`，就优先把它传给 AIReiter，并将其复制为 `generation/NN/product-identity.*`。现有 generation、CLI 和便携技能测试及文档也固化了这一行为。

## 2. 已确认决策

采用方案 A：产品上手图是模型唯一的产品身份来源；正面图和细节图只服务于人工分析与 QC。

具体边界：

1. AIReiter 内部图 1 仍是手模、姿势、构图、光线和场景参考。
2. AIReiter 内部图 2 固定为当前 run 的 `input/product-on-hand.jpg`。
3. `input/product-detail.*` 可以继续用于 review、产品结构分析、canonical 约束构建和人工 QC 对照。
4. 正面图或细节图不得作为第三张模型输入，也不得替代内部图 2。
5. `generation/NN/product-identity.jpg` 固定复制送模使用的 `product-on-hand.jpg`，用于审计。

## 3. 备选方案与取舍

### 方案 A：分离分析证据与送模身份（采用）

细节图保留在分析和 QC 环节，生成只使用上手图。它同时保留结构审核能力并降低重绘风险，改动集中在 generation 输入选择、测试和文档。

### 方案 B：完全移除细节图

实现最简单，但会失去对偏心主石、开口端点和细小装饰的人工核对证据，不利于 canonical 和 QC，不采用。

### 方案 C：上手图与细节图同时送模

可能增加局部信息，但模型仍会同时接收平铺结构，无法消除重绘倾向，还会增加图像职责冲突，不采用。

## 4. 数据流

`prepare-review` 继续保存两类输入：

- `input/product-on-hand.jpg`：真实佩戴状态，是生成阶段唯一产品身份图；
- `input/product-detail.<ext>`：可选分析证据，只进入 review、约束确认和 QC 对照。

`generate` 不再扫描或选择 `product-detail.*`。在全部现有 gate 通过后，它将：

1. 把选定 Rank 的 review 副本作为内部图 1；
2. 把 `input/product-on-hand.jpg` 作为内部图 2；
3. 把同一产品上手图复制为 `generation/NN/product-identity.jpg`；
4. 使用原有 Prompt、Rank 重试和模型切换逻辑提交任务。

细节图缺失、多张或格式不同不再影响 generation 输入选择；其 prepare-review 格式校验和非戒指拒绝规则保持不变。

## 5. 兼容与错误处理

- 新 run 和历史 run 均使用 `input/product-on-hand.jpg` 作为内部图 2。
- 调用方传入的 `product_image` 若不是 run 内 `input/product-on-hand.jpg`，继续由现有路径和 gate 规则处理，不新增静默回退。
- 旧 generation 目录不改写，历史 `product-identity.png/webp` 保持原样供审计。
- 新 generation 统一生成 `product-identity.jpg`，其 SHA-256 必须与当前 run 的 `input/product-on-hand.jpg` 一致。

## 6. 测试与验收

按 TDD 增加或修订以下验证：

1. 戒指同时存在 `product-on-hand.jpg` 和 `product-detail.png` 时，helper 第二个 `--image` 必须是上手图。
2. `generation/NN/product-identity.jpg` 必须与上手图字节和 SHA-256 一致。
3. 细节图不得出现在 helper 的任何 `--image` 参数中。
4. 无细节图的历史兼容路径继续通过。
5. 非戒指 generation 行为不变。
6. CLI 戒指四阶段端到端测试同步断言内部图 2 和审计副本均为上手图。
7. 全文修订操作文档和便携技能，删除“细节图优先作为生成身份输入”的旧规则。
8. 使用 JH025、JH026、JH501 新建 run 重新生成；每个结果通过 Prompt 合同、完整 QC 和 run 产物检查后才能替换本次测试交付。

## 7. 非目标

- 不删除 `--product-detail-image`。
- 不新增第三张模型输入。
- 不改变产品分析字段、参考图 Top 3、失败码纠偏或模型切换策略。
- 不覆盖 2026-07-15 已生成的历史 run 和结果。
- 不写回产品货盘或参考素材飞书 Base。
