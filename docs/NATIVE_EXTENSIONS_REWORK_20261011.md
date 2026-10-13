# 七项能力的 V2 原生拓展改造

日期：2026-10-11。版本：2.1.0。

Content、Image、Screen、Reality、Together、Game、Live 由 V2 本体内部装配，分别配置和启停。AstrBot 的插件注册、公开页面、安装包各只有一个，七项能力的实现、默认配置、网页和运行资产随本体交付。

## 实际归属

| 能力 | 领域实现 | 宿主接线 |
| --- | --- | --- |
| Content | `companion_v2/content/` | `astrbot_host/native_extensions/content.py` |
| Image | 内部图片原件、生成与编辑服务 | `astrbot_host/native_extensions/image_native/` |
| Screen | `companion_v2/screen/` | `astrbot_host/native_extensions/screen_provider.py`、`screens.py` |
| Reality | `companion_v2/reality/` | `astrbot_host/native_extensions/reality/` |
| Together | `companion_v2/together/` | `astrbot_host/native_extensions/together/` |
| Game | `companion_v2/games/` | `astrbot_host/native_extensions/game/` |
| Live | `companion_v2/live/` | `astrbot_host/native_extensions/live/` |

`builtins.py` 创建内部模块，`NativeExtensionRegistry` 管理它们的生命周期。暂停、保存配置后的重建及停机会回收原实例和网络端口。模块声明中的包身份用于内部版本和授权管理，不注册新的 Star。

小屋从 `manifest.extensions` 读取七项内部模块的装配状态、配置和运行状态；`manifest.providers` 保留真正的外部兼容入口。旧七个伴侣 Star 被排除出执行发现，即使它们仍安装在宿主中，也不提供这七项能力的执行器。

## 调用链与验证范围

普通私聊与获准群聊继续通过 AstrBot 核心回复管线。V2 使用原生钩子补充背景、工具和媒体，并在后台记录观察及统计。核心 Token、模型请求、工具耗时、发送返回与缓存回执沿实际执行路径计量；未取得回执的字段保留未知状态。

核心工具接入作品创建、续写、原件读取和本地诊断。写作复用 V2 专用写作模型及固定版本服务，保存候选后仍需显式采用；普通对话不创建旧回复批次。诊断设计说明与实际检查分开，原件只读取本轮真实提供的句柄；重读继续检查撤权、撤回和报告有效期。提示词目录展示实际注入的核心工具规则与按需启用的写作规则。

图片编辑和蒙版编辑可读取当前认证消息的直接附图及引用图片，顺序与核心一致。引用解析复用官方 OneBot 解析器，保留原账号、窗口、引用消息及发送者，并在读取和采用前复核撤回；普通聊天不因仅有引用 ID 而额外下载图片。模型请求里的任意图片 URL 不作为本轮编辑授权。

现实提醒、位置变化、共处房间历史和直播记忆通过 V2 内部服务接入当前人格、会话与数据 owner。真实外部投递复核原身份和授权，未知发送结果不重放；这些功能的观察记录保留自身来源，不伪造核心聊天批次或平台确认。

小屋的 Reality 管理接入本机音频输出、本人授权提示、主动语音策略、叫醒安排和提醒取消。音频授权由本人在对应私聊中确认；设备试听失败、提醒取消未完成均返回实际失败，不显示操作成功。管理页读取状态时不扫描设备，设备操作释放普通回复所需的控制锁。

Reality 同意页首次启用能力后会启动内部服务，相机工具接入本体内的实际采集入口。感知页合并历史操作与核心工具的原始记录，读取最近的成功快照并逐次检查权限；超过八次读取仍显示最新值。相机在进入设备调用前明确拒绝时保存已知未执行回执，后续合法请求可正常调用；进入真实设备 I/O 后的未知结果仍不重放。

Live 与 Game 的模型调用直接进入各自的实际回执账本，停机前落盘；治理页提供共处、现实、直播和游戏的用量来源，缺少模型或缓存回执时仍显示未知。独立服务账本不重复计入角色的核心回复预算。

共处房间包含本地默认 SVG 头像，远程头像不可用时仍能显示；缓存头像根据实际内容返回 MIME。Live 的 SoulLink 桥接脚本和引擎均位于本模块内，并由构建脚本检查必需资源，不搜索另装插件目录。

后台 SQLite 写入可能从工作线程通知宿主。`CompanionApplication.notify()` 将这类唤醒送回所属事件循环，避免跨线程修改 asyncio 等待对象后造成共处房间停机卡住。

安装级工具目录保留全部可信声明，避免七项内置能力与 QQ 空间合计超过 64 项时阻断已有运行档的加载。单次插件模型请求保留自身预算；普通聊天工具由核心按本轮授权发布。冷启动验证见 [HOST_TOOL_CATALOG_STARTUP_20261011.md](HOST_TOOL_CATALOG_STARTUP_20261011.md)。

V2 保持独立数据根。2.1.0 的能力目录升级仅转换已有 V2 记录的内部包身份并保留授权和状态；V1 资料仍需通过明确请求的正式迁移流程读取。

最终验收从新 ZIP 的解包副本运行，核对唯一 Star、唯一「陪伴小屋」、七项资源、加载与停机、路由注销、核心回复和治理统计。交付目录中的 `ACCEPTANCE_20261011.md` 与验收目录的 `package-verification.json` 保存对应包的哈希、测试结果及范围。设备、米家、TTS 和直播连接效果仍需在实际使用环境验证。
