# 14 · 模型与连接（`manage/models`）

代码位置：`renderModelsPage`（`pages/陪伴小屋/app.js:1201`，挂载点 `#modelWorkspace`）；模块 `models-page.js`（1312 行，自带页头、三页签与刷新控件）。端点基址 `role().model_api`（`models-page.js:1293-1297`）。

## 一、页面功能

任务 × Provider 的路由矩阵 + 语音（TTS）与生图后端管理 + Provider 连通性测试。页头注释（`app.js:1199-1200`）：模型页自带页签，不再套配置控制台的子类统计与边界卡，避免与真实工作区重复。

## 二、展示部分（三页签，`models-page.js:835-839`）

| 页签 | 内容 |
| --- | --- |
| 功能模型 | 按组陈列任务档卡片（`fnCard` `:183-232`）：主/备 Provider、超时、输出上限（按 Provider 能力封顶 `fitLimit` `:59-64`）、任务附加提示词 ≤8000 字、8 个继承开关；**快速配置**（按组统一指派，`:929-970`）；态势图（`:854-879`）；替换策略三模式（关键词换模/高价时段替代/拒答替代，`:1139-1156`）；批量测试（`:916-928`） |
| 语音模型 | zh/ja/en 三语种绑定 Provider + 合成超时；试听样句；TTS Provider 连接管理（新建/编辑/克隆，写入 AstrBot Provider 配置）（`:398-599`） |
| 生图模型 | Native 动作开关（`image.generate` 文生图 / `image.edit` 多参考改图 / `image.mask_edit` 蒙版局部改图）+ 逐动作注册检查；「路线队列与连接」编辑器（每行 route_id/operation/backend comfyui\|sd_webui/workflow_id/profile、默认路线、daily_limit/retention_days/max_storage_mb/max_concurrency、ComfyUI 工作流列表、两种后端的 base_url+api_key+timeout）（`:600-833`） |

### 任务档清单

- 前端 `groups` 常量（`models-page.js:10-15`）**11 个任务档**、4 组：对话（`conversation.reply`）；主动与记忆（`proactive.compose`、`memory.reflect`）；生活与成长（`calendar.plan`、`role.state.maintain`、`role.reading.consume`、`role.growth.progress`）；私人书写（`role.journal.diary/dream/derive/select`）。
- 后端注册 **15 个任务档 × 9 字段 = 135 项**（`companion_v2/adapters/astrbot/staging.py:209-217`）：上表 11 个 + `model.proactive.judge`、`model.screen.interpretation`、`model.content.authoring.draft/review`——后端另注册的四档未在前端分组常量单列，由通用渲染兜底。

替换策略按设计稿使用「策略分段栏 + 单一编辑面板」；任务选择、作用范围与保存动作留在同一工具栏。拒答策略编辑与精确配置共用的备用 Provider，并可编辑匹配词；普通对话核心任务不进入替换任务选择器。

## 三、配置部分

### `model.*`（15 档 × 9 字段）— installation+role+window，下一轮生效 — 通道 ② `/model` 专用工作台

每档 9 字段（`models-page.js:6-9`）：`provider` 主 Provider、`fallback` 备用（主失败/超时/拒答时尝试一次）、`prompt` 附加提示词、`max_output_tokens` 输出上限、`timeout_seconds` 请求超时 1–600、`replacement_rules` 替换规则、`fallback_on_refusal` 拒答替代、`refusal_terms` 拒答匹配词、`replacement_scope` 替换作用范围。拒答词每行或分号分隔，保存后由模型网关匹配本次模型正文；提供方结构化拒答标记始终保留。保存前校验 `validatePatch`（`:114-123`）；保存 `POST {model_api}/configure`（patch：operation_key+edit_token+changes/reset，`:261-284`），失败可「核对原保存结果」重试（`:285-294`）。

**测试与保存分离**：测试按钮 `POST /test {provider_id}` 只探测连接不写配置（`:224,369-370,882-892`）；批量测试逐 Provider 探测。

### 语音与生图后端（非 `model.*` 组，走 model_api 专用路由）

- TTS：`GET/POST /voice(/save)` 绑定、`POST /voice/test` 试听、`GET /tts/providers` + `POST /tts/providers/create|update|clone`（Provider 配置写入 AstrBot，凭据不回显）。
- 生图：`GET/POST /image(/save)` 开关、`POST /image/test` 注册检查、`GET/POST /image/config(/save)` 路线队列（带 revision）。

`image.mask_edit` 只会在 Image 提供方声明当前后端确实绑定蒙版输入时出现；群聊不开放此动作。局部结果由宿主保护蒙版外像素。页面的注册检查只核验声明与当前注册，不会调用图片后端。

### 不在本页

- `model.budget` 每日软限额在**自我页 E4**（`app.js:1170`；models-page.js 全文无 budget）——`model.budget` 是独立组，与任务档分开。

## 四、边界与空态

- `model-empty` 空态；未注册 Provider 选项标「· 未注册」（`:177,1024`）；草稿 stale/pending 提示与 rebase/retry（`:200-201,226-227`）。
- 桥未就绪不再报「请从管理界面打开」，给「重新读取」入口（`:1289-1294`）。
- **凭据、Cookie、Provider ID 不回显**（api_key 输入留空保持原值的约定与感知提供方表单一致）。

## 五、后端情况

`astrbot_host/model_api.py:104-118` 共 **15 条路由** → `companion_v2/model_gateway/management.py` `ModelManagement`（`model_api.py:15,134`）+ `ReplyManagement`（`:12,200,231`，用于语音/分段联动读取）。路由注册：任务档字段进 `FieldRegistry`（`adapters/astrbot/staging.py:219`），消费端是 `ModelRouter`（`model_gateway/routing.py:51`）。

## 六、相关设计稿与复核

- 预算 → [11-governance.md](11-governance.md)；识屏任务档的感知侧 → [06-perception.md](06-perception.md)；生图额度/审核 → [09-output.md](09-output.md)。
- 复核任务档：`sed -n '209,217p' companion_v2/adapters/astrbot/staging.py`（后端 15 档）；`sed -n '10,15p' pages/陪伴小屋/models-page.js`（前端 11 组）。
