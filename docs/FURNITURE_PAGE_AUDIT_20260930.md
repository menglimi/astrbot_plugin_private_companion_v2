# 家具对应拓展页勘察（2026-09-30）

## 结论

七件拓展家具对应四个已有基本管理接线的独立工作台、两个缺少正式业务页的入口，以及一个在 V2 原生模式下不能使用的旧页面。小屋内的七个家具面板目前都没有嵌入对应提供方的完整业务工作区。

| 家具 | 正式页面构建 | 当前可用范围与缺口 |
| --- | --- | --- |
| 创作书架 / Content | 未构建正式作品页 | `pages/index.html` 是“澄汐的小屋”静态稿，没有业务 API 调用；真实 SDK 发现结果为空。小屋点击后只显示能力说明，没有作品列表、版本读取或创作表单。 |
| 画面工作室 / Image | 没有独立页；已有本体图像配置分区 | 在“模型与连接”的图像页签可配置 Image 路由，调用当前角色的 `/model/image/config` 和 `/model/image/config/save`。家具本身只打开状态说明，没有生成工作台或相册业务页。 |
| 共处电话 / Together | 已构建“一起房间” | 房间入口、服务状态、对话／视觉／STT／TTS 配置及观影、阅读设置有真实 API；本地配置读写检查通过。使用房间仍需启用服务和有效对话模型，媒体能力取决于相应配置。 |
| 游戏棋桌 / Game | 已构建“游戏管理台” | 可加载房间管理和游戏配置；后端 `page_rooms()` 读取 `manager.rooms` 中的网页房间，没有读取 `_native_provider` 的 V2 聊天对局。不能把它当作原生对局管理台。 |
| 屏幕台 / Screen | 已构建“屏幕伴侣”旧页 | 旧运行、观察、日记及配置 UI 可以加载，但 V2 原生模式构造提前返回，未注册该页使用的 API。原生模式下此旧页不能使用。 |
| 现实设备台 / Reality | 已构建 `reality-companion` | 设备、摄像头、家居、用户与提醒、Android 网关的工作台有页面和状态／操作 API。页面加载和导航通过；真实设备动作及授权配置没有在线执行。 |
| 直播与表演 / Live | 已构建“直播面板” | 总览、记忆、观众、事件、Soullink、配置界面及相应 API 已有。页面可加载；监听、OBS、VTS、模型呈现与真实外部操作没有在线验收。 |

这里的“已有基本管理接线”表示正式入口、静态资源、页面脚本和相应 API 实现均存在，不表示真实模型、设备、房间或直播外部服务已经验收成功。V2 本体的调用授权缺口仍见 [拓展能力检查](EXTENSION_CAPABILITY_AUDIT_20260930.md)。

## SDK 发现结果

使用本机 AstrBot `PluginPageService` 执行真实目录发现、入口解析和 HTML 消息桥重写：

| 提供方 | SDK 正式页 |
| --- | --- |
| Content | 无 |
| Image | 无 |
| Together | 一起房间 |
| Game | 游戏管理台 |
| Screen | 屏幕伴侣 |
| Reality | reality-companion |
| Live | 直播面板 |

五个正式页的直接引用本地资源全部存在。Content 的根级 `pages/index.html` 未处于 SDK 要求的命名页面目录，不能从 Dashboard 正常发现；其内容也不能作为作品管理页使用。Image 的独立页已按提供方既有接管约定取消，不能仅靠恢复旧页面解决 V2 工作台缺口。

## 小屋到工作台的入口

`pages/陪伴小屋/app.js` 的 `FURNITURE_WORKSPACES` 只嵌入日记书桌和睡眠工作区；七件拓展家具进入介绍面板，再通过 `showDetail()` 打开公开状态弹窗。

- Together、Reality：`providerEntries` 提供正式页面地址、打开链接和复制地址控件。
- Game、Screen、Live：`product-page.js` 的 `providerLinks()` 只输出“到插件中打开某拓展页”的文字，没有直达链接或嵌入工作区。
- Content：没有可发现的正式作品页，也没有本体作品管理工作区。
- Image：家具的“相关配置”统一转到“行动”，没有直接转到已有的“模型与连接 → 图像”配置；状态弹窗也没有图像配置入口。

基础家具另有两个明确缺口：“相框与相册”目前也是 Image 状态入口，不能浏览相册；“见闻电台”没有接入专属工作台。衣柜按现有页面说明仍是陈设。

## Screen 原生模式的实际装配证据

用 AstrBot 自带 Python、临时数据根和合成账号构造真实 `ScreenCompanion`，为 `context.register_web_api` 设置计数探针。没有截图或外部调用：

```json
{"native_ready": true, "page_routes_registered": 0, "legacy_runtime_created": false}
```

源码位置为 Screen `main.py` 的 `__init__()`：原生 provider 构造结束即返回，后面的 `_register_plugin_page_api_if_available()` 不执行。旧 `page_api.py` 依赖旧 `WebServer` 与旧运行数据，不能直接将其注册到原生分支；需要独立的 V2 页面合同。

## 页面与配置检查

本地 Chromium 在与 Dashboard 相同的 opaque-origin iframe 沙箱中加载真实 SDK 重写后的五个页面，并使用本地合成只读 API 回包。桌面 1440×1000、手机 390×844，检查页面加载、可见控件、局部导航、脚本异常、资源错误与横向溢出：

| 页面 | 控件数 | 脚本异常 | 资源错误 | 两种宽度横向溢出 |
| --- | --- | --- | --- | --- |
| 一起房间 | 49 | 0 | 0 | 无 |
| 游戏管理台 | 19 | 0 | 0 | 无 |
| 屏幕伴侣旧页 | 48 | 0 | 0 | 无 |
| reality-companion | 68 | 0 | 0 | 无 |
| 直播面板 | 66 | 0 | 0 | 无 |

浏览器检查未发出业务 POST，也未访问外部服务。Screen 这一行仅证明旧 UI 可以渲染，与上一节原生模式没有注册 API 的结论兼容。合成回包的设备缺省状态不代表本机 OpenCV、摄像头或音频设备故障；Live 合成总览也不代表在线监听状态。

Together 的 `tests/test_launcher.py::PageConfigApiTests` 四项定向后端检查通过，覆盖提供方选项、设置保存及运行参数采用、缺失对话模型拒绝、数值校验。全部使用本地配置和提供方替身。

本轮没有修改生产插件或家具行为，新增两个可复用勘察工具：

- `tools/audit_furniture_pages.py`：临时 SDK 数据根内发现正式页面，生成消息桥重写后的 HTML 和目录记录。
- `tools/check_furniture_provider_pages.cjs`：加载上述页面，记录消息桥请求与布局结果，生成桌面／手机截图；业务写入和外部网络被检查宿主拦截。

运行产物保存在插件扫描目录之外：

`D:/codex/visualizations/2026/09/30/01a0f169-423c-7cb1-be6b-e956dfbf69fd/furniture-page-audit/`

其中 `inventory.json` 为 SDK 目录，`browser-results.json` 为逐页结果，`page-contact-sheet.png` 为桌面／手机截图总览。没有读取或修改 V1 用户资料，没有构建新交付包。

## 接入优先顺序

1. 为五个已存在的提供方页补齐可达入口，并让 Screen 明确显示原生模式的可用范围。
2. 建立 Content 作品工作区，以及 Image 家具到已有图像配置的入口；相册和生成操作需各自补业务界面。
3. 补 Screen 原生工作区、Game 原生对局投影，并接入选中 Bot／人格／会话的能力管理合同。
4. 按工程顺序构建当前源码的交付包，再对新包进行宿主、页面及所选真实外部链路验收。
