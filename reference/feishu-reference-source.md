# 飞书参考底图库与审计

## 数据源和角色边界

默认生产来源：

- Wiki：`https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink`
- Base：`AI生图参考图素材库`
- 数据表：`素材收录池`

`prepare-review` 未传 `--classification` 时同步并读取该 Base。显式提供本地 Excel 时只作为历史兼容导入源，不形成第二套规则。每条记录仅使用“素材图片”的第一张附件；多图应拆成多条记录。

`图片类型` 字段是角色唯一来源：

- `hand_worn` 只接收“手部佩戴图”；
- `lifestyle` 只接收“生活场景图”；
- “主图”不进入当前 Skill，必须交给独立主图 Skill；
- 关键词、风格、推荐使用方式、模型视觉判断和其他字段不能推断、改变或跨用图片类型。

参考底图是画面结构唯一来源。飞书语义字段必须足以确认人物、姿势、手势、构图、景别、服装、背景、光线、留白、原首饰和唯一替换位置；缺字段时停止，不在 Prompt 中猜测。

## 字段映射

### 基础字段

| `ReferenceRow` | 飞书来源 |
| --- | --- |
| 序号 | 按素材编号、record_id 稳定排序 |
| 文件名、路径 | 下载第一张“素材图片”后生成 |
| 宽高、大小 | 本地缓存文件计算 |
| `purpose_category` | `图片类型` |
| 场景关键词 | `关键词` |
| 饰品/适用品类 | 优先 `适用品类`，兼容 `适用产品类型` |
| 默认策略、风格、推荐方式、备注、置信度 | 飞书同名字段；空值进入 enrichment |

### 参考构图字段

| 属性 | 标准飞书字段 | 用途 |
| --- | --- | --- |
| `applicable_product_types` | `适用产品类型` | 品类硬 gate；空值不得推断通用 |
| `applicable_display_modes` | `适用展示模式` | `worn` / `hand_held` 硬 gate |
| `framing` | `人物取景范围` | 景别和裁切 |
| `visible_body_regions` | `可见身体区域` | 人物/身体区域 |
| `product_visibility` | `产品预计展示面积` | 面积不足即淘汰 |
| `neck_visibility` | `颈部可见度` | 项链适用性 |
| `collarbone_visibility` | `锁骨可见度` | 项链适用性 |
| `chest_visibility` | `胸前可见度` | 项链适用性 |
| `hand_visibility` | `手部可见度` | 手部/手持适用性 |
| `collar_type` | `衣领类型` | 服装结构 |
| `clothing_occlusion_risk` | `衣物遮挡风险` | 遮挡 gate |
| `hair_occlusion_risk` | `头发遮挡风险` | 遮挡 gate |
| `pose_keywords` | `姿势关键词` | 身体和手臂姿势 |
| `mirror_relation` | `镜面关系` | 镜像风险 |
| `existing_jewelry` | `原有首饰类型` | 唯一替换位置与清除范围 |
| `crop_risk` | `裁切风险` | 画面完整度 gate |

戒指参考必须额外完整提供：

| 属性 | 字段 |
| --- | --- |
| `hand_side` | `左右手` |
| `visible_fingers` | `可见手指` |
| `hand_orientation` | `手部朝向` |
| `ring_face_visibility` | `戒面可见度` |
| `finger_separation` | `手指分离度` |
| `finger_occlusion_risk` | `手指遮挡风险` |

戒指候选必须显式标记 `ring` 与 `worn`，不能从备注或“饰品类型=戒指”补猜。项链与戒指启用前必须补齐对应字段；旧手串记录仍可按旧字段读取，但不自动获得其他品类资格。

## 本地增量镜像

默认 `output/feishu_reference_cache/`：

- `images/`：附件缓存；
- `manifest.json`：record、附件 token、源字段指纹、语义字段和本地路径；
- `pending_enrichment.json`：待补全记录；
- `enrichment.json`：已确认本地语义镜像；
- `issues.json`：附件/下载/字段问题；
- `enrichment-import-audit.json`：逐记录 patch、读回、冲突和错误审计。

指纹包含 record_id、素材编号、关键词、图片类型、适用品类、全部参考构图字段和第一张附件信息。字段或附件改变会使本地补全失效并重新进入 pending；飞书读取失败时不得用旧缓存继续生产。

以下远端状态明确使 enrichment 失效：

1. `AI补齐状态=需刷新`；
2. 非空版本与当前 `ENRICHMENT_VERSION` 不一致；
3. 远端标记已完成且版本当前，但此前写回字段被清空。

失效后只读当前远端值，不从本地静默复活旧内容。

## pending 默认阻断

线上模式任一 `pending_enrichment=true` 都阻断 `prepare-review`。只有用户明确批准临时批次才可使用 `--ignore-pending-enrichment`：

- 仍完整分页同步 Base；
- 只从候选中排除 pending，不修改远端；
- 与 `--classification` 互斥；
- 过滤后没有合格候选立即失败；
- 每个正式 run 写 `analysis/reference_source_snapshot.json`。

来源快照记录 Wiki/Base/table、全量记录数、pending 排除数、保留数、被忽略素材编号/record_id、`manifest.json` 原始字节 SHA-256 和 `pagination_complete=true`。它只证明本次来源和排除范围，不表示 pending 已补全。

## 命令

```powershell
# 只读同步；存在 pending 时退出码 2
jewelry-on-hand reference-sync

# 创建缺失字段（这是显式维护动作，不属于默认生成流程）
jewelry-on-hand reference-ensure-fields

# 导入人工审核后的 enrichment
jewelry-on-hand reference-import-enrichment `
  --input-json .\output\feishu_reference_cache\enrichment-results.json

# 正常只读来源准备
jewelry-on-hand prepare-review `
  --product-image .\product.jpg `
  --analysis-json .\analysis.json `
  --output-role lifestyle

# 仅用户批准的临时排除模式
jewelry-on-hand prepare-review `
  --product-image .\product.jpg `
  --analysis-json .\analysis.json `
  --output-role lifestyle `
  --ignore-pending-enrichment
```

连接和缓存可由 `JEWELRY_REFERENCE_WIKI_URL`、`JEWELRY_REFERENCE_TABLE_NAME`、`JEWELRY_REFERENCE_BASE_TOKEN`、`JEWELRY_REFERENCE_TABLE_ID`、`JEWELRY_REFERENCE_CACHE_ROOT` 覆盖。不得把 token、Cookie 或密钥写入仓库。

## enrichment 输入

每条记录以 `record_id` 定位，`fields` 中提供五个旧语义字段和必要构图字段。未知内容写“未知”并让硬 gate 淘汰，不能臆测为适用。示例：

```json
{
  "records": [
    {
      "record_id": "recxxxxxxxx",
      "fields": {
        "默认使用策略": "常规可优先使用",
        "风格分类": "清透自然光",
        "推荐使用方式": "半身生活场景",
        "备注": "正面平视；人物居中；无文字或平台界面",
        "判断置信度": "高",
        "适用产品类型": "bracelet,ring",
        "适用展示模式": "worn",
        "人物取景范围": "胸前半身",
        "可见身体区域": "上半身,left_hand,left_wrist,left_forearm",
        "产品预计展示面积": "充足",
        "姿势关键词": "身体正面；左前臂斜向右上",
        "原有首饰类型": "左腕单条手串",
        "左右手": "left",
        "可见手指": "thumb,index,middle,ring,little",
        "手部朝向": "back",
        "戒面可见度": "高",
        "手指分离度": "高",
        "手指遮挡风险": "低"
      }
    }
  ]
}
```

导入只向空字段写非空结果，保留已有人工值，并写状态与版本。

## 并发保护与 CAS 审计

现有 `lark-cli base +record-upsert` 没有 revision、etag 或 if-match，不能声称强 CAS。导入采用可恢复的 compare/readback 流程：

1. 写前完整分页复读，全批预校验源字段和附件指纹；
2. 每条记录第一次读，合并远端人工值；
3. 紧邻 upsert 前第二次读，把新出现的人工值从 patch 排除；
4. upsert 后第三次读，逐字段比较实际值与 patch；
5. `verified` 才更新本地 manifest/enrichment/指纹；`failed` 或 `conflict` 保持 pending，继续处理其余记录并持久化审计。

`enrichment-import-audit.json` 保存 `record_id`、`status`、`patch`、`details`、`error`。部分成功可恢复；失败记录修复后再导入。缺历史导入审计时可运行只读 `reference-audit-enrichment`，它只能证明当前读回状态，不能证明写入瞬间没有并发覆盖。

残余 CAS 窗口位于最后一次写前复读与 upsert 之间；若需要零覆盖保证，必须等待飞书提供 revision/if-match 并由 reviewer 批准升级。默认生成流程绝不写回飞书。

## 与 run 的绑定

`prepare-review` 把选中记录的源/review SHA、role、rank 和构图字段固化为候选快照；人工确认后生成单一确认快照。飞书后续变化不修改已有 run。需要采用新数据时，新建 run 并重新执行 `prepare-review`；历史 run 只读且不得追加。
