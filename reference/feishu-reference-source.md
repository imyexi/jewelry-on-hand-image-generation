# 飞书参考图库数据源

## 数据源与边界

默认生产参考图数据源为飞书多维表格：

- Wiki：`https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink`
- Base：`AI生图参考图素材库`
- 数据表：`素材收录池`

`prepare-review` 未传 `--classification` 时同步并读取上述飞书 Base。只有显式传入 `--classification <xlsx>` 时才读取旧“参考图分类” Excel 作为本地兼容输入；Excel 不形成第二套生产业务规则。线上模式默认对任一 `pending_enrichment=true` 严格阻断。只有用户明确批准的临时批次，才可传 `--ignore-pending-enrichment`：命令仍先完整分页同步线上 Base，再从候选中排除 pending 记录，不写回或修改远端；它与 `--classification` 互斥，过滤后无可用候选立即失败。项目不把 `reference/上手参考图` 目录本身当作候选图库。已生成 review 包中的图片仍是 run 内副本，不受飞书后续修改影响。

每条记录只使用“素材图片”的第一张附件。多附件记录会写入同步警告；需要多张图时应拆成多条素材记录。

## 字段来源

### 基础源字段

| `ReferenceRow` 字段 | 飞书字段或生成方式 |
| --- | --- |
| 序号 | 按素材编号、record_id 稳定排序后生成 |
| 文件名、相对路径、绝对路径 | 下载第一张“素材图片”附件后生成 |
| 宽度、高度、大小MB | 从本地缓存文件计算 |
| 用途分类 | `图片类型` |
| 手链手串适用性 | 根据现有 `适用品类` 确定性推导；未标注时为否 |
| 场景关键词 | `关键词` |
| 饰品类型 | 优先使用现有 `适用品类`，再兼容 `适用产品类型` |

`图片类型` 是三图角色的唯一分类事实来源：含“主图”只可进入 `hero`，含“手部佩戴图”只可进入 `hand_worn`，含“生活场景图”只可进入 `lifestyle`。关键词、风格分类、推荐使用方式和图像语义只可用于类型 gate 之后的排序与风险判断，不能改变或推断图片类型。
| 默认使用策略、风格分类、推荐使用方式、备注、判断置信度 | 飞书同名字段；空值由 Codex 图片分析补齐 |

### 通用参考图字段

| `ReferenceRow` 属性 | 标准飞书字段 | 兼容规则 |
| --- | --- | --- |
| `applicable_product_types` | `适用产品类型` | 标准字段为空时读取现有 `适用品类`；不得从 `饰品类型` 或其他文本推断 |
| `applicable_display_modes` | `适用展示模式` | 缺失时为空 |
| `framing` | `人物取景范围` | 旧字典/Excel 同时兼容 `取景范围` |
| `visible_body_regions` | `可见身体区域` | 缺失时为空 |
| `product_visibility` | `产品预计展示面积` | 旧字典/Excel 同时兼容 `预计展示面积` |
| `neck_visibility` | `颈部可见度` | 缺失时为空 |
| `collarbone_visibility` | `锁骨可见度` | 缺失时为空 |
| `chest_visibility` | `胸前可见度` | 缺失时为空 |
| `hand_visibility` | `手部可见度` | 缺失时为空 |
| `collar_type` | `衣领类型` | 缺失时为空 |
| `clothing_occlusion_risk` | `衣物遮挡风险` | 缺失时为空 |
| `hair_occlusion_risk` | `头发遮挡风险` | 缺失时为空 |
| `pose_keywords` | `姿势关键词` | 缺失时为空 |
| `mirror_relation` | `镜面关系` | 缺失时为空 |
| `existing_jewelry` | `原有首饰类型` | 旧字典/Excel 同时兼容 `原有首饰` |
| `crop_risk` | `裁切风险` | 缺失时为空 |
| `hand_side` | `左右手` | `left`、`right` 或空；只描述参考图中的手，不覆盖产品确认指位 |
| `visible_fingers` | `可见手指` | 使用 `thumb,index,middle,ring,little` 的逗号分隔闭集；缺失时为空 |
| `hand_orientation` | `手部朝向` | 例如 `back`、`palm`、`side`；缺失时为空 |
| `ring_face_visibility` | `戒面可见度` | `高`、`中`、`低`；缺失时为空 |
| `finger_separation` | `手指分离度` | `高`、`中`、`低`；缺失时为空 |
| `finger_occlusion_risk` | `手指遮挡风险` | `高`、`中`、`低`；缺失时为空 |

通用字段在迁移期允许为空。缺少 `适用产品类型` 和现有 `适用品类` 时，`applicable_product_types` 必须保持空值，不得默认为“通用”、项链适用或戒指适用；这类记录不参与项链或戒指硬筛选。旧手串记录继续通过 `手链手串适用性` 和现有字段读取。戒指候选必须显式标记 `ring`、`worn`，并完整提供左右手、可见手指、手部朝向、戒面可见度、手指分离度和手指遮挡风险；不得从备注或“饰品类型=戒指”猜测缺失字段。

## 本地增量镜像

默认目录为 `output/feishu_reference_cache/`，其中：

- `images/`：飞书附件缓存。
- `manifest.json`：源记录、附件 token、源字段指纹、通用字段和本地路径。
- `pending_enrichment.json`：待 Codex 分析的素材清单，区分必填补齐字段与可选通用字段。
- `enrichment.json`：已确认的本地语义字段镜像。
- `issues.json`：空附件、下载失败等不可用记录。
- `enrichment-import-audit.json`：最近一次补齐导入的逐记录核验结果、实际 patch、错误详情和残余并发风险。

经批准使用 `--ignore-pending-enrichment` 的每个正式 run 另写 `analysis/reference_source_snapshot.json`。快照记录 Wiki/Base/table、完整同步记录数、忽略 pending 数、保留可用数、每条被忽略素材的素材编号与 record_id、`manifest.json` 原始字节 SHA-256，以及 `pagination_complete=true`。快照只读本地同步结果，不触发远端写入；它证明本次候选来源和排除范围，不表示被忽略素材已完成补齐。

增量指纹包含 record_id、素材编号、关键词、图片类型、`适用品类`、全部通用参考图字段（包括六个戒指字段）和第一张附件信息。任一字段或附件发生变化，该记录重新进入待补齐状态；飞书读取失败时不使用旧缓存继续运行。通过导入命令回填通用字段时会同步更新本地源字段和指纹，下一次同步不会把刚导入的结果误判为外部变更。

以下三种远端状态会明确使本地补齐失效，并把原因写入 manifest 的 `enrichment_invalidation_reasons`：

1. `AI补齐状态=需刷新`。
2. 非空 `AI补齐版本` 与当前 `ENRICHMENT_VERSION` 不一致。
3. 远端仍标记 `已完成` 且版本为当前值，但某个此前已写回的字段被清空。

失效后只使用当前远端值，不允许从 `enrichment.json` 静默复活旧值；记录重新进入 `pending_enrichment.json`。第三种情况必须有远端“已完成 + 当前版本”作为曾写回证据，旧缓存中的 `pending=false` 本身不构成证据。

旧缓存没有通用字段时仍可读取，缺失值统一为空。旧的五个语义字段仍是补齐结果的必需字段；新增通用字段为迁移期可选字段，项链和戒指素材必须在对应品类启用前补齐。字段为空的戒指记录会在品类策略硬筛选中明确淘汰，不会回退到文本猜测。

## 操作命令

```powershell
# 只同步并检查状态；有待补齐项时返回退出码 2
jewelry-on-hand reference-sync

# 创建缺失的飞书语义字段、通用字段和追踪字段
jewelry-on-hand reference-ensure-fields

# Codex 完成 pending_enrichment.json 的图片分析后导入结果
jewelry-on-hand reference-import-enrichment --input-json .\output\feishu_reference_cache\enrichment-results.json

# 正常生成 review；命令会先同步飞书并在待补齐时阻断
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\analysis.json `
  --output-role lifestyle

# 仅限用户已批准的临时批次：完整同步后排除 pending，并写 run 内来源快照
jewelry-on-hand prepare-review `
  --product-image .\path\to\product.jpg `
  --analysis-json .\path\to\analysis.json `
  --output-role lifestyle `
  --ignore-pending-enrichment
```

可以使用环境变量覆盖连接和缓存配置：

- `JEWELRY_REFERENCE_WIKI_URL`
- `JEWELRY_REFERENCE_TABLE_NAME`
- `JEWELRY_REFERENCE_BASE_TOKEN`
- `JEWELRY_REFERENCE_TABLE_ID`
- `JEWELRY_REFERENCE_CACHE_ROOT`

禁止把用户 token、Cookie 或其他密钥写入仓库。

## AI 补齐 JSON

补齐文件必须包含五个旧语义字段。通用字段在迁移期可选；项链素材应按实际画面完整提供，不确定时写“未知”，不得臆测为适用。

```json
{
  "records": [
    {
      "record_id": "recxxxxxxxx",
      "fields": {
        "默认使用策略": "常规可优先使用",
        "风格分类": "清透自然光",
        "推荐使用方式": "胸前半身项链佩戴展示",
        "备注": "颈部、锁骨和胸前完整",
        "判断置信度": "高",
        "适用产品类型": "necklace,pendant_necklace",
        "适用展示模式": "worn",
        "人物取景范围": "胸前半身",
        "可见身体区域": "颈部 锁骨 胸前",
        "产品预计展示面积": "高",
        "颈部可见度": "高",
        "锁骨可见度": "高",
        "胸前可见度": "高",
        "手部可见度": "低",
        "衣领类型": "低领",
        "衣物遮挡风险": "低",
        "头发遮挡风险": "低",
        "姿势关键词": "正面站立",
        "镜面关系": "无镜面",
        "原有首饰类型": "细项链",
        "裁切风险": "低",
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

导入时以飞书已有人工值为准，只向空字段写入非空 AI 结果，并写入 `AI补齐状态=已完成`、`AI补齐版本=1`。若飞书仍只维护现有 `适用品类`，可以省略 `适用产品类型`；读取时会使用 `适用品类` 作为兼容值。

## 导入并发保护、审计与恢复

当前 `lark-cli base +record-upsert` 没有 revision、etag、if-match 或其他原子 CAS 参数，因此系统不能声称强 CAS。导入采用当前接口下最强的可恢复流程：

1. 写入任何记录前，分页复读全表并预校验所有提交记录，避免已知源字段变化时产生部分写入。
2. 对每条记录第一次 `get_record`，重新合并远端人工值并校验。
3. 紧邻 upsert 前第二次 `get_record`；这次出现的人工值会从 patch 中排除，不被 AI 值覆盖。
4. upsert 后第三次 `get_record`，逐字段比对实际值与 patch。
5. 每条记录从第一次 `get_record` 开始形成独立异常边界；第一次/第二次读取、源字段一致性、戒指六字段、patch 构造、upsert、写后读取或本地核验计算任一步异常都标记 `failed`。只有写后完全一致的记录标记 `verified`，才更新本地 manifest、enrichment 和指纹；写后值不一致标记 `conflict`。`failed` / `conflict` 都保留 pending，并继续处理后续记录，函数末尾仍持久化此前所有 verified 记录和完整审计。

`enrichment-import-audit.json` 的 `records[]` 逐条保存 `record_id`、`status`（`verified` / `failed` / `conflict`）、`patch`、`details` 和 `error`。部分成功是合法、可恢复状态：已核验记录提交本地，失败或冲突记录留在 `pending_enrichment.json`，修正远端或提交内容后可再次导入。

若历史批次只保留了已同步缓存而缺少该文件，执行 `jewelry-on-hand reference-audit-enrichment`。该只读命令逐条复读远端并与 `manifest.json` 的 `resolved_enrichment` 比较，写出 `audit_kind=post_sync_readback`：所有字段一致、没有待补齐项时记录为 `verified`，缺失、源字段变化或值不一致时记录为 `failed`。该状态审计不包含历史 patch，也不能证明写入瞬间没有覆盖并发人工修改；它仅用于恢复候选库准入所需的当前复读证据。

无法消除的残余窗口是“最后一次写前复读之后、upsert 之前”。此窗口内若人工写入同一空字段，upsert 仍可能覆盖；写后若读到本次 upsert 的值，也无法证明是否覆盖过该人工值。审计文件会固定记录这一限制。需要零覆盖保证时，必须由飞书接口提供 revision/if-match 并经 reviewer 决定升级方案；当前实现不得被描述为强 CAS。
