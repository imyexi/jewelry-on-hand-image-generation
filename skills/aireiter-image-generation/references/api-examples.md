# AIReiter API Examples

这些样例来自真实跑通的调用，便于后续在不同 agent 中复用。

## 文生图示例 1

请求思路：
- 主题：宇航服橘猫
- 模型：`gpt_image_2`
- 比例：`1:1`

提交后查询结果要点：
- `out_task_id`: `aireiter-20260424-011507`
- `status`: `completed`
- `credits_used`: `1`
- `output[0].url`: `https://s1.pxz.ai/upload/image-generator/20260424/TAJqHAr4sb4rvoXAthTAk-item-0.png`

## 文生图示例 2

请求思路：
- 主题：小学一年级爱护眼睛、防控近视手抄报
- 风格：儿童插画、适合打印和抄写

提交后查询结果要点：
- `out_task_id`: `aireiter-20260424-011914`
- `status`: `completed`
- `credits_used`: `1`
- `output[0].url`: `https://s1.pxz.ai/upload/image-generator/20260424/gXIsqPEdZWyQUMZzgd_lR-item-0.png`

## 图生图示例：本地参考图

请求思路：
- 输入图：本地 JPG 文件路径
- 主题：基于参考图版式生成更适合小学一年级的爱护眼睛、防控近视手抄报
- 关键点：`--image /absolute/path/to/file.jpg`

提交后查询结果要点：
- `out_task_id`: `aireiter-20260424-012323`
- `status`: `completed`
- `credits_used`: `1`
- `output[0].url`: `https://s1.pxz.ai/upload/image-generator/20260424/oQBf2QyGW3gU607VnBTmU-item-0.png`

## 使用提醒

- 初次 `submit` 返回里 `task_id` 可能为空，不要依赖它；优先记录 `out_task_id`。
- 本地图片图生图无需手动转码，脚本会自动转成 data URL。
- 若要长期复用，推荐保留成功提示词模板，而不是只保留输出 URL。
