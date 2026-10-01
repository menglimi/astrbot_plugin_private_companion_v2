# 05 · 感知（`manage/perception`，A 段）

代码位置：`renderPerception`（`pages/陪伴小屋/app.js:1091-1118`）；缺对象时整页引导 `pageNeedsTarget('感知设置')`（`app.js:1093-1094`）。模块：`perception-native-page.js`（V2 自有感知设置，341 行）、`semantic-page.js`（语义理解与素材，195 行）、`perception-page.js`（屏幕/现实提供方表单嵌入器，211 行）。

## 一、页面功能

回答"角色**能得到**什么信息"：身边环境（地点/天气/日历）、对话里的信息（消息形态与语义/黑话）、屏幕与设备（识屏解读与提供方）、外部资讯（新闻源）。管理 V2 自有感知配置 + 语义素材目录 + 两个外部提供方的桥接设置。

## 二、展示部分

四个分区（`app.js:1097-1116`）：

| 分区 | 内容 | 数据来源 |
| --- | --- | --- |
| 身边的环境 | `#nativeEnvironmentWorkspace`：天气源/预警源「已装配/尚未就绪」状态（`perception-native-page.js:144-145`）；`#knowledgeConfigWorkspace` 知识库配置编辑器 | `GET {perception_native_api}` |
| 对话里的信息 | 静态来源卡 `perceptionSources`（文字与引用/图片与动图/语音/视频/合并转发，`app.js:1061-1067`）；`#semanticWorkspace` 语义页：嵌入状态徽章（已就绪/关键词回退/已停用）+ revision、素材计数（表情 N·群词义 N）、检索结果（索引状态、fallback 提示）、素材列表（enabled/analysis/来源已失效） | `GET/POST …/semantic`（`semantic-page.js:44-51,113,151`） |
| 屏幕与设备 | `#nativeModelWorkspace`（固定说明"配置在下一条封存的对话输入生效"，`perception-native-page.js:147`）；`#screenConfigWorkspace` 编辑器；两张提供方卡（astrbot_plugin_screen_companion / astrbot_plugin_reality_companion 的 integration_state、runtime_ready、reason，`app.js:1069-1084`）+「提供方配置地址」只读框与复制按钮（`app.js:1085`，复制逻辑 `:1500`） | `product.provider()`（integration manifest） |
| 外部资讯 | `#nativeNewsWorkspace`：资讯源装配状态、最近检查时间与条数、最近失败 code/HTTP、主动联系总开关与后台联系开关 | `GET {perception_native_api}`（`perception-native-page.js:149-157`） |

## 三、配置部分

### ① `knowledge`（知识库与世界书）— 14 项，installation/role/window，立即生效，通道 `/config`

挂载 `configEditors('knowledgeConfigWorkspace',['knowledge'])`（`app.js:1100`）。按功能划分：

| 功能簇 | 字段 |
| --- | --- |
| 导入 | `import_enabled` 允许导入本机知识来源、`import_paths` 世界书文件路径、`source_ids` 知识库/文档标识、`entry_limit` 单次导入条目上限、`entry_char_limit` 单条素材最长字数、`source_limit` 来源数量上限、`candidate_char_budget` 单轮候选字符预算 |
| 注入 | `inject_enabled` 允许在对话中引用知识、`inject_max_entries` 每轮最多引用条数、`inject_max_chars` 每轮引用字符上限 |
| 成员线索 | `member_recognition_enabled`、`member_match_aliases`、`member_inject_limit`、`member_clue_chars` |

后端：`companion_v2/knowledge/configuration.py:34` → knowledge/* 消费。

### ② `screen`（屏幕解读与日记素材）— 3 项，window，下一轮生效，通道 `/config`

挂载 `configEditors('screenConfigWorkspace',['screen'])`（`app.js:1110`）：`interpretation_enabled` 解读屏幕画面、`journal_material_enabled` 允许作为日记素材、`journal_material_max_chars` 单条素材最长字数。后端 `companion_v2/screen/configuration.py:15` → screen/interpretation.py、peek.py。

### ③ `conversation.perception`（9 项，window，下一轮生效）— 通道 ② `perception-native` 专用工作台

`perception-native-page.js` 分 environment/model/news 三段表单，`POST {perception_native_api}/configure`（`:83,266`），两段式提交（operation_key+edit_token+changes）；冲突时保留草稿并给「采用最新版本」rebase（`:294-303`）。前端校验：时区合法、年度日历 1-3 份 JSON、地点名+经纬度、开天气需先有地点、沿用 5-120 分钟、guidance ≤2KiB、资讯间隔 15-1440、B 站 UID 十进制、RSS/JSON 必须 HTTPS（`:198-252`）。

### ④ 语义素材（非配置组）— 通道 ② `/semantic`

`semantic-page.js` 动作：configure（带 revision）、reindex 重建索引、import（表情图片 ≤5MB 转 base64）、analyze 识别图片、edit 编辑、search 检索（`:125-189`）。

### ⑤ 屏幕陪伴/现实触及提供方设置（非 V2 组）— 通道 ② `/perception` 桥

`perception-page.js` 按提供方 `settings.groups` 生成表单，`POST perception {provider, section, updates}` 只发改动字段，password 留空保持原值（`:119,148-153`）；screen 在 `native_v2 && read_only` 时只显示"绑定项在屏幕陪伴插件配置中修改"（`:77-79`）。设置由两个提供方插件自持（`astrbot_host/perception_api.py:17-18` 桥接到 `extension_api.companion_v2_perception_settings`）。

## 四、边界与空态

- 提供方不可用 → 显示 `entry.reason` 或「配置暂不可读取，请确认插件已启用并更新」（`perception-page.js:109`）；未读到宿主目录 → 「尚未读到宿主目录」+ 重新读取（`:101-103`）。
- semantic 页在 staging 未初始化/宿主已停止时只给「打开宿主管理」（`semantic-page.js:66-74`）；群会话无可验证成员输入时说明"收到群消息后即可管理"（`:92`）。
- 识屏是否进入对话以能力目录接入状态为准；识图用哪个模型在模型与连接页指派（本页不放）。

## 五、后端情况

| 路由 | 服务 |
| --- | --- |
| `GET/POST …/perception-native`、`POST /news-diagnostic`（`astrbot_host/native_perception_api.py:31-34`） | `conversation/perception_management.py` `PerceptionManagement` + `role_work/state/management.py` + `proactive/management.py`（`native_perception_api.py:9-13,37-39`） |
| `GET/POST …/semantic`（`semantic_api.py:23-24`） | `session.application.semantics` 运行时服务（`semantic_api.py:89`） |
| `GET/POST …/perception`（`perception_api.py:28-29`） | 外部插件桥（`astrbot_plugin_screen_companion` / `astrbot_plugin_reality_companion`） |
| `/config` 的 knowledge、screen 组 | `KnowledgeManagement`、`ScreenManagement`（`configuration_api.py:35-48`） |

## 六、相关设计稿与复核

- 表情素材检索参数在表达 D3 → [10-expression.md](10-expression.md)；识屏模型 → [14-models.md](14-models.md)。
- 复核分区：`sed -n '1091,1118p' pages/陪伴小屋/app.js`。
