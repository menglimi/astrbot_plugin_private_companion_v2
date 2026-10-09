# 我会永远陪着你 V2.0 · 陪伴小屋

V2 的正式拓展页就是这版体素小屋。规范源位于本体 `pages/陪伴小屋/`；Content 的历史预览目录只是可选发布目标。

## 正式使用

从已登录的 AstrBot Dashboard 打开「我会永远陪着你 V2.0 → 陪伴小屋」。页面读取 V2 的能力目录及授权目标，在顶部选择对象和角色。宿主未初始化时可查看能力目录并进入账号与会话。

- 首页：体素庭院、真实生活与状态、活动、日记/梦境摘要、成长、记忆与家具。
- 日程：当前角色的日历、状态、共享睡眠与 QQ 展示设置/回执。
- 日记书桌、阅读角、睡眠与梦境：既有日记与生活工作区。
- 人物与关系：关系记录审阅、采用、修订与撤回。
- 事实与经历：事实、检索、来源、反思、修订、历史、设置和有范围的遗忘管理。
- 成长花架：目标/技能及确认、修订、暂停、恢复、完成和归档。
- 能力目录：本体模块与可选伴侣的真实安装、适配和配置状态。
- 账号与会话：Bot 账号 → 人格 → 会话窗口的三列只读拓扑，以及探测、初始化、启动、停止和实际接管状态；会话窗口较多时按页显示并限制列表高度。

左侧按“小屋、塑造角色、互动能力、连接与运行”分组。角色设定统一在“自我”中管理：人格问卷整理角色底色、边界、表达和目标，世界知识管理它可引用的资料；输入感知、群聊决策、主动联系、表达和内容产出各由对应页面负责。账号与会话负责绑定和运行，模型与连接负责模型路线和后台预算，资料与备份负责记录来源、备份和还原。完整配置归属见[配置归属表](../../docs/CONFIG_ALLOCATION_20261001.md)。Content、Image、Together、Game、Screen、Reality、Live 七项可选能力在首页家具目录查看状态和提供方入口，不占用原生一级导航。旧的 `#library`、`#activities` 和 `#manage/capabilities` 链接会转到家具目录，`#manage/semantic` 转到感知能力。

感知能力页集中显示 V2 本体已实现的文字、图片、语音、视频、引用与合并转发输入；其嵌入、记忆召回、表情、群黑话和发送前视觉复核沿用 `semantic` API 保存。Screen 与 Reality 显示各自公开的安装、开关与就绪状态，并提供可复制的独立页面地址。Screen 已接入原生桌面采集：在 Screen 插件中启用 `native_v2` 并填好设备与 Bot 身份后重载提供方，再为具体私聊单独授权；获得授权不代表每轮自动截图，只有对话确实需要桌面画面时才会调用。Reality 的手机摘要、摄像头单帧、设备目录/状态、电源/属性动作和操作回执已进入 V2 原生工具目录，在「屏幕与设备」中按当前 Bot、角色、绑定私聊窗口逐项授权；Reality 自身的设备配置和白名单仍由提供方保存。Dashboard 的沙箱页不能直接导航到其他插件页，因此独立页面地址需要在主界面打开。

各业务读取沿用现有 API 的权限和对象范围；切换目标或失去授权会清除旧内容。没有记录时显示空状态，不使用设计样例补足。

## 小屋与布置

庭院有六种天气、四个时段、旋转、缩放及巡游。天气和时段属于显示预览，尚无真实天气联动。布置模式在桌面并排显示场景与工具，在手机上将工具置于场景下方；支持拖动、微调、旋转、外观、收纳及撤销重做。

布局按安装/对象/角色隔离。允许 localStorage 的浏览器可本地保存；AstrBot 沙箱限制存储时仅保留到当前页面关闭，不表示已经保存至插件或支持跨设备同步。衣柜属于陈设；没有新增换装或手账业务。见闻电台工作台待接入。

## 工作区构建

`product-page.js` 提供统一导航、只读总览、能力发现及成长操作。`memory-page.js`、`state-page.js` 和 `state-editor.js` 直接复用管理 API。

`tools/sync_framework_page.py` 将本体另外三个工作区构建为 `workspace-bundle.js` 与 `workspaces/`。源码保留在 `pages/宿主管理/`、`pages/日记与生活/`、`pages/关系与记忆/`，HTML 入口统一为 `workspace.html`，因此不再单独作为一级 Dashboard Page 被发现。小屋使用 srcdoc 和 `embedded-bridge.js`，通过 Dashboard 消息桥转发到当前目标 API，兼容 opaque-origin 沙箱。不要单独编辑生成资源。

Content 开发预览位于 `astrbot_plugin_content_companion/design-previews/companion-v2/`，已经移出公开 pages 扫描，也不进入 Content 插件安装包。

```powershell
python -X utf8 tools/sync_framework_page.py
python -X utf8 tools/sync_framework_page.py --check
python -X utf8 tools/sync_framework_page.py --preview <静态预览目录>
```

静态预览中的 `config-snapshot.js` 仅含通用分发默认值，页面明确展示样例；不承载本机配置或凭据。静态 URL 不等同于真实插件入口。

## 验收与范围

桌面、390px、320px、非模态布置、WebGL、键盘、目标隔离、鉴权失败、真实 SDK 消息桥与工作区操作均使用定向检查验证。详见 [V2.0 发行说明](../../docs/RELEASE_V2_0.md) 与 [整合验收](../../docs/INTEGRATION_ACCEPTANCE_V2_0.md)。

[结构说明](STRUCTURE.md)、[历史 V1/V2 对照](V1_TO_V2_UI_AUDIT.md)保留设计依据；其中历史“尚未接入”的状态以当前发行说明为准。
