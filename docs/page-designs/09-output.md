# 08 · 产出（`manage/output`，C 段）

代码位置：`renderOutput`（`pages/陪伴小屋/app.js:1156-1159`）；挂载 `imageControlWorkspace`/`materialControlWorkspace`（`app.js:1247,1257`）。

## 一、页面功能

回答"角色**产出**什么"：图像生成的额度与审核治理、参考图与衣柜，以及创作与作品能力的接入状态。

## 二、展示部分

| 分区 | 内容 | 数据来源 |
| --- | --- | --- |
| 图像生成 · 生图治理 | 编辑器挂载头说明（额度按安装与角色生效；审核只作用于群受众的成图，不通过可改走私聊投递，`app.js:1157`） | `/config` |
| 图像生成 · 参考图与衣柜 | 说明头（两项按角色生效；两个总闸默认关闭，`app.js:1157`） | `/config` |
| 图像生成 · 能力卡 | V2 内置 Image 拓展的装配状态与原因 | `GET integration/manifest` 的 `extensions` |
| 创作与作品 | V2 内置 Content 拓展卡（原稿、版本、作品由本体拓展保存；用哪个模型在模型页指定，`app.js:1158`） | 同上 |

## 三、配置部分（四组，全部通道 `/config`）

### `conversation.media_quota`（生图每日额度）— 4 项，installation+role，下一轮生效

| 字段 | 含义 |
| --- | --- |
| `private_owner_max_daily` | 本人私聊每日张数 |
| `private_friend_max_daily` | 他人私聊每日张数 |
| `group_max_daily` | 群聊每日张数 |
| `proactive_max_daily` | 主动消息每日张数 |

后端 `companion_v2/conversation/media/quota.py:26` → media/quota.py 消费。

### `conversation.image_review`（群图成图审核）— 11 项，window，立即生效

| 功能簇 | 字段 |
| --- | --- |
| 总闸与降级 | `enable_group_nsfw_private_fallback` 审核不通过时降级私聊投递 |
| 审核判定 | `group_nsfw_image_review_mode` 审核方式、`..._sensitivity` 判定尺度、`..._min_confidence` 置信度下限 |
| 执行参数 | `..._timeout_seconds`、`..._max_dimension` 送审最长边像素、`..._max_images` 单次送审张数 |
| 失败处理 | `..._failure_action`、`..._custom_prompt` 审核提示词补充 |
| 审核模型 | `review_provider`、`review_dual_provider` 第二审核模型 |

后端 `conversation/media/review.py:100` → media/review_service.py 消费。

### `photo.reference`（参考图）— 4 项，role，下一轮生效

`enabled` 启用参考图、`group_enabled` 单独允许群聊使用角色参考图（默认关闭，不影响私聊）、`daily_outfit_enabled` 启用每日穿搭、`daily_outfit_rotation_days` 同一套穿搭的轮换间隔（天）。后端 `references/configuration.py:20`。

### `wardrobe`（衣柜）— 6 项，role，下一轮生效

`enabled`、`tendency` 穿衣倾向说明、`prompt_enabled` 允许把衣柜写进提示词、`prompt_max_items` 单次提示词最多列出的衣物件数、`image_max_count` 一次穿搭请求最多识别的图片数、`image_prompt` 穿搭识图要求。后端 `references/wardrobe.py:21`。

挂载：`configEditors('imageControlWorkspace',['quota','image_review'])` + `configEditors('materialControlWorkspace',['photo.reference','wardrobe'])`（`app.js:1157`，挂载 `:1247,1257`）。

### 待接：`content.authoring`（6 项，installation+role，立即生效）

`authoring_service.py:31` 4 项 + `cover_assets.py:49` 2 项（创作总闸、方向提示、正文上限、候选数、封面张数等）。**当前无页面挂载点、无 `/config` SECTIONS 条目**——接入需补：字段声明 → SECTIONS → spec → `app.js` 挂载（产出 C2）。

## 四、边界与空态

- 生图参数（默认尺寸、步数、批量、并发、存储配额）**不在本页**：它们属于提供方/路线队列配置，在模型与连接页的「生图模型」页签（`app.js:1157` 的 settingsJump 文案；见 [14-models.md](14-models.md)）。
- Content 无配置控件时只显示内置拓展卡，不放假开关。

## 五、后端情况

- `/config` 的 quota、image_review、photo.reference、wardrobe 四组：`ImageQuotaManagement`、`ImageReviewManagement`、`ReferenceManagement`、`WardrobeManagement`（`configuration_api.py:35-48`）。
- 能力卡：`GET /integration/manifest`（`integration_api.py:25`）。

## 六、相关设计稿与复核

- 模型路线与生图后端 → [14-models.md](14-models.md)；行动类能力 → [08-action.md](08-action.md)。
- 复核字段标签：spec 导出命令（[README.md](README.md) 第五节）后看 `quota/image_review/photo.reference/wardrobe` 组。
