# V2 本体注册协调回执

日期：2026-09-25。来源任务：整合现有已实现框架为「我会永远陪着你 V2.0 插件」。

## 当前身份

- 唯一本体源码目录：`C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2`。
- 插件目录 / metadata.name / 页面 API 前缀：`astrbot_plugin_private_companion_v2`，本任务未新增第二个新框架本体。
- 产品显示名：`我会永远陪着你 V2.0`；产品版本、metadata、pyproject 和 main 的 PLUGIN_VERSION：`2.0.0`。
- main.py 装饰器注册名：`PrivateCompanionV2`。Python 类名 `PrivateCompanionV2StagingPlugin` 为兼容保留。
- 本次早先已修改 main.py 的注册文案/版本，挂上 `UnifiedCompanionExtensionAPI`，未增加第二个注册装饰器。
- 产品 ID：`private_companion.v2`。单目标 / 多目标仍按现有配置选择同一个本体的控制器。

## 页面与 API

- 规范页：本体 `pages/陪伴小屋/`。其余三个既有页「宿主管理」「日记与生活」「关系与记忆」继续保留。
- 小屋内嵌的工作区由 `tools/sync_framework_page.py` 从上述三个页构建为资源包，不单独注册为插件或新的 Dashboard Page。
- 本体增加 `/astrbot_plugin_private_companion_v2/integration/manifest`；多目标目录补 relationships/growth API 路径，不注册第二个宿主。
- Content 的 `pages/framework-preview-v1` 仅作为可选静态预览输出，已不作为 V2 规范源；可选插件安装包会排除该预览副本。
- 七个伴侣插件与旧版主插件仅在各自已有 extension_api 增加只读 `companion_v2_status()`。未改变其注册身份，未导入 V1 用户库。

## 在线操作时间与责任

收到本次协调消息之前，本任务已于本地约 12:38–12:40 在已登录 AstrBot Dashboard 的插件列表，对唯一目录 `astrbot_plugin_private_companion_v2` 点击过一次「重载插件」。结果已核对：插件列表显示「我会永远陪着你 V2.0」，版本 `2.0.0`。此前在线版本为 `0.2.0`。

本次没有点击宿主 start，没有授予真实投递权限，没有重载旧版核心或其他七个伴侣。重载前已有 V2 profile 为 preview 且未启动。重载后正在核对小屋只读状态。

收到协调消息后：本任务不再单独在线重载、不新增或重命名本体注册；后续注册/重载请由协调任务统一执行。页面刷新及本地合成测试继续。

## 继续负责的范围

- 小屋与真实目标/角色、生活/记忆/关系/状态/成长/宿主工作区接线。
- Dashboard 沙箱兼容、桌面与手机验收。
- 现有领域框架模块清单、V2 发布说明、可安装本体 ZIP 和七个可选伴侣 ZIP 的套件构建。
- 本体运行代码、页面、测试和文档打包；排除用户数据、凭据、个人模型及产物。

本任务尊重其他窗口已完成的严格只读预览、SDK 查询兼容和 Demo 修复；打包包含当前工程中的既有成果，不回退这些改动。用户没有要求另一个本体身份、V1 自动替换或 V1 数据迁移。

补充：重载后小屋实际显示「已连接」，已有 preview 运行档正常只读加载；宿主管理实测为「未接管消息」。能力目录识别 8 个已安装提供方、0 个已加载新版状态适配器，本任务未重载这些提供方。

页面兼容修复：实际 AstrBot Page SDK 会解包返回值，因此 `pages/陪伴小屋/state-page.js` 的 api() 必须同时接受直接对象、status/data 以及嵌套 data/status/data。当前已恢复这项兼容，并保留新加入的 state-editor 配置/日历功能；请后续合并不要退回只接收 envelope 的版本。已将首页「日程」接到现有角色状态与日历工作区。

## 入口统一完成回执

- `pages/宿主管理/index.html`、`pages/日记与生活/index.html`、`pages/关系与记忆/index.html` 已分别改名为同目录 `workspace.html`；其他源码文件保持原位。
- 构建脚本读取三个 `workspace.html`，仍在小屋资产内生成 `workspaces/{host,life,relationships}/index.html` 和 `workspace-bundle.js`。公开根目录仅「陪伴小屋」有一级 `index.html`。
- Content 预览已从 `pages/framework-preview-v1/` 移至 `design-previews/companion-v2/`，完整开发素材保留且已发布最新小屋。其安装包不包含该开发预览。原 8769 端口的 Python 静态预览服务仅更新了目录；没有重载 AstrBot 或任何插件。
- `tests/demo_host_process.py` 的 `/page/index.html` 已映射到源码 `workspace.html`。host/life/relationships 三个独立浏览器检查均更新并通过；host 7 项，life 和 relationships 各自完整原检查通过。
- SDK 页面发现测试改为断言唯一公开页「陪伴小屋」，同时验证内部宿主资产可解析、Content 不再公开旧预览；产品/页面/隔离收尾组合 15 项通过。
- 主产品浏览器 10 项通过，记忆浏览器 22 项通过，均没有浏览器/服务端错误。实际 sandbox 与 SDK 解包兼容有专项覆盖。
- main.py 已采用协调任务修改后的 `@register(PLUGIN_NAME, ...)`。本窗口不再修改其注册身份，不在线重载。

首版 8 个插件包已写入 `D:/codex/workspaces/companion-v2-release-20260925/dist/`，正在 `snapshot/` 中验证解压副本。本轮快照保留已验收状态编辑器；状态维护/周期校准窗口的新开发按对方要求不提前纳入未经验证的内容。套件最终校验完成后补充交付记录。

## 最终交付完成

已将协调任务的注册统一记录、AGENTS.md 约定及导航纳入最终快照。构建使用已经验收的 `snapshot/`，没有重新从并行开发中的状态页面取未验证改动。

- 本体：`D:/codex/workspaces/companion-v2-release-20260925/dist/astrbot_plugin_private_companion_v2-2.0.0.zip`，12,793,434 字节；SHA-256：`61cfed459fc1f266b8a31a36b474953d7e726bb8af02af1559a0c9c36dbc21b5`。
- 套件：`D:/codex/workspaces/companion-v2-release-20260925/dist/companion-v2-2.0.0-suite.zip`，16,034,613 字节；SHA-256：`116d5142bcfc66a7ea0d1b4670ce40e0df36e5c18797b1d89af218fa525dd9cc`。
- 套件包含 8 个独立插件 ZIP；本体 750 个文件，含 570 个 Python 源文件。已排除用户数据、凭据配置、个人模型、缓存、开发预览和注册协调回执。
- 首次解压副本通过真实 SDK 主入口的 4 个多目标生活路由、启停、路由注销；真实模型和平台调用为 0。解压副本另通过产品/页面/隔离 15 项、记忆浏览器 22 项。
- 最终包再次解压到 `verified/`，逐文件哈希、源码语法、默认关闭/preview、唯一公开页、套件 CRC 与 8 个嵌套包哈希全部通过。最终检查记录：`verified/package-verification.json`；SDK 运行证据：`snapshot/package-verification.json`。
- 正式小屋已刷新复核：图片能力 0.4.5 的状态适配器已接入，无重复冲突。其余未重载实例显示待加载适配器，停用提供方保持停用。没有启动真实消息接管。

本任务入口整合、源码归档和可安装套件交付完成。后续领域新功能可继续更新同一本体；需要新发行时，从对应已验收版本重建包即可。
