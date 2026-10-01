# CORE-ASTRBOT 试运行宿主入口

现场证据日期：2026-09-22；目录整理更新：2026-09-23。在[试运行配置与首次初始化](CORE_ASTRBOT_STAGING_BOOTSTRAP_SLICE.md)之上，已接 AstrBot 4.27.2 可加载的宿主入口。入口服务单目标 OneBot 私聊纯文本 preview，以及需要独立 profile 和有限期 delivery grant 的 `onebot_private`；默认关闭，不会自动初始化、启动、调用模型或发送平台消息。`companion_v2` 核心包继续通过静态隔离扫描；根级 `main.py` 负责注册与事件转发，SDK 探测、Dashboard API 和控制器位于 `astrbot_host/`，详见[文件组织](REPOSITORY_LAYOUT.md)。

## 管理入口

宿主通过 `Context.register_web_api` 注册以下路由，统一由 AstrBot Dashboard JWT 鉴权，转发路径前缀为 `/api/plug/astrbot_plugin_private_companion_v2/staging`：

| 路由 | 方法 | 行为 |
| --- | --- | --- |
| `/status` | GET | 返回开关、固定配置、运行态和最近错误摘要；不探测 provider、不调用模型。 |
| `/probe` | POST | 核对当前 OneBot 平台/账号、目标 conversation/persona 和 provider 类型/指纹；不写库、不发请求。 |
| `/initialize` | POST | 将无凭据配置原子写入独立 profile，并调用可信 bootstrap 初始化全新 V2 库。 |
| `/authorize-delivery` | POST | 对已初始化的 `onebot_private` profile 签发固定、精确 scope、15 分钟有效的 `message.delivery` grant；重复调用只返回原 grant，不延长有效期。 |
| `/revoke-delivery` | POST | 先关闭入站，再撤销固定 delivery grant；重复撤销保持幂等。 |
| `/start` | POST | 复核固定 profile，取得新任务/模型运行代后开放目标入站。 |
| `/stop` | POST | 先关闭入站，再有界停止会话。 |
| `/inspect` | GET | 返回脱敏执行、模型用量与投递回执摘要。 |
| `/preview` | GET | 在原 owner/来源/授权仍有效时读取指定 batch 的生成稿。 |

未认证请求由 Dashboard 拒绝；实机请求已验证返回 HTTP 401。API 不接受聊天命令授权，也不保存 JWT、provider key、endpoint 或完整 provider 配置。

## 固定 Profile 与事件边界

`_conf_schema.json` 暴露显式的 `enabled`、`profile_id`、OneBot 平台/登录账号/参与者、V2 Bot/角色、可选 AstrBot persona、provider、任务提示、输出限制、费率、预算、合并时间及任务容量。`delivery_mode` 支持 `preview` 和 `onebot_private`；后者拒绝默认 `preview-1`，必须使用新的独立 profile。

每个合法 `profile_id` 对应 `plugin_data` 下独立目录。首次初始化前先探测当前原生对象，再以 UTF-8、无 BOM、LF 的 `staging-config.json` 固定完整无凭据文档。后续加载使用原 `valid_from` 重建当前候选并比较配置指纹；目标、conversation、persona 提示、provider、预算或模式任一变化都会拒绝，不能借插件重载换目标或把 preview 升级为 sender。新目标和发送 profile 都应使用新的 profile ID 和新库。

`onebot_private` 的身份、基础回复权限和外部投递权分开记录。初始化只签发固定的基础 capability grants；`/authorize-delivery` 在 bootstrap 已完成后才签发 `astrbot-staging-delivery`，能力为 `message.delivery`，有效期固定为 15 分钟。`start`、重新开放已运行 session 的 intake、`receive` 和 OneBot reverse WebSocket 真正调用前都会重新读取当前 grant；撤权先关闭 `_accepting`，生成中的任务在 sender 边界变为 `not_sent`，不会调用平台。替代 grant、错误 scope、过期或撤销均不能恢复发送。热重载只读恢复当前 grant，不自动签发或延长。

私聊 handler 在同步检查以下条件全部成立后才停止 AstrBot 后续事件链：宿主已显式 start、会话为 running、事件是已验证的原生 OneBot 类型、UMO/平台/登录账号/发送者和 client identity 都与固定 profile 一致。停止事件链后再调用 `AstrBotStagingSession.receive`；即使后续捕获失败，也不会回退到 AstrBot 普通回复链而意外发送。未启用、未启动、其他账号、其他发送者和非原生事件完全旁路。

原生适配器对能力按加载器逐项注册。当前私聊和群 `Forward` 均接入账号固定的展开读取器；群读取核对原群、当前转发者和有界文本、图片及[音视频节点](CORE_GROUP_FORWARD_MEDIA_20260925.md)，复用原件与共享预算。群直接音视频另按原组件位置和附件定位核对；群 Reply 内音视频及合并转发仍等待原消息合同。预处理后的普通文本不能冒充原媒体，不支持的组件保持明确拒绝。

## 生命周期

插件加载只注册管理 API；已有 profile 在 `initialize()` 中只读加载为 `new`，不会自动 start。`start` 失败保持入站关闭并可在原条件恢复后重试。`stop` 和热重载先把 `_accepting` 置为 false，再关闭会话；只有返回 `stopped` 后才关闭 `StorageRuntime`。路由注销按 `(route, handler identity)` 删除本实例项，旧实例不能误删已替换的新 handler。终止后的迟到管理调用明确返回 `staging_host_terminated`。

AstrBot 以 `data.plugins.<目录>.main` 导入插件，不会自动把插件根加入 `sys.path`。根级 `main.py` 因此显式托管 `companion_v2` release package 的搜索路径，并在干净终止后移除路径与该包的模块缓存，保证后续热重载读取当前源码；该兼容逻辑不进入核心包。

本轮将原根级 `astrbot_staging_host.py` 拆入 `astrbot_host/settings.py`、`native.py`、`controller.py` 和 `web_api.py`。入口使用相对导入，宿主子模块沿用 AstrBot 的插件命名空间；原生 PluginManager 按该前缀回收子模块。控制器仍负责授权与运行时，Web API 独立持有本实例的 handler，保留按 handler identity 注销的行为。根目录 Python 文件只剩 `main.py`。目录拆分时 schema 为 v14；随后[模型失败诊断](CORE_MODEL_FAILURE_DIAGNOSTICS_SLICE.md)新增 v15。

## 验证

目录拆分时的宿主与隔离定向测试 16 项通过，AstrBot 4.27.2 原生契约 12 项通过、网络尝试 0 次。宿主测试覆盖注册路由驱动的管理顺序及回执序列化、preview 不调用 OneBot sender、显式有限期授权、撤权/生成中撤权、固定 provider 冲突、重载只读不自启、停止后关库/注销路由、重复注册 handler identity、目标账号筛选，以及关闭且配置不完整时只读发现在线账号和默认 provider。隔离检查拒绝核心导入 `astrbot_host`，并检查根目录只有 `main.py` 一个 Python 文件。自动测试使用临时数据根和模型/平台替身，以下现场测试另行记录。

在独立进程中另以真实插件包名加载 `main.py`，使用临时 AstrBot 数据根和原生 `PluginManager._purge_modules` 完成两轮加载、初始化、终止及模块回收。两轮均注册并注销 9 条路由，保持 `enabled=false`、`session_state=unloaded`，没有创建 profile/运行库；核心搜索路径及模块缓存完成回收，第二轮控制器类型为新导入对象。网络尝试为 0；该检查未向在线 Dashboard 发起重载。

运行中的本机 AstrBot 已完成实际加载验证：

- V1 `astrbot_plugin_private_companion` 版本 6.6.2 保持停用。
- V2 `astrbot_plugin_private_companion_v2` 原 preview 现场验证版本为 0.1.0；sender 现场测试版本为 0.2.0，测试后 staging 开关恢复 `false`。
- 关闭状态下的 `/probe` 识别到 1 个在线 OneBot 账号和受支持的默认 provider，不触发模型或发送。写入明确目标后，定向重载、`probe`、`initialize` 和 `start` 均成功，固定 profile 的 conversation、persona、provider 指纹及配置指纹通过复核。
- 最初的 preview 测试中，一条真实 OneBot 私聊纯文本被精确目标围栏接管。`astrbot_openai` 模型调用状态为 `generated`，用量已结算为 5677 tokens，耗时约 1.96 秒；管理 API 读取到一段 preview 草稿。这是历史 preview 用量，不是后续 sender 的结果。
- preview 返回 `sent=false`；批次 confirmed part 为 0，投递回执没有 `platform_ref` 或 `delivered_at`。preview adapter 的可信 `not_sent` 在通用消息状态机中按设计归一为终态 `failed`，不表示平台调用失败。
- `/stop` 返回 `stopped` 且待处理句柄为 0；关闭开关并定向热重载后，`runtime_open=false`、`session_state=unloaded`、`accepting=false`。固定 profile 保留供后续只读核对；固定配置与运行库均未保存 Dashboard JWT、provider key、endpoint 或完整 provider 配置。
- Dashboard 插件、平台配置和平台统计 API 均正常；默认 provider `deepseek/deepseek-v4-flash` 已完成本次实测。
- 首次标准插件重载暴露 package 搜索路径缺口并返回失败；补齐根级路径托管后，使用 failed-plugin 定向重载成功。没有跳过或掩盖该失败。

## 有限目标 sender 现场结果

后续在授权的单账号纯文本范围内完成两组 sender 测试：

| Profile / 批次 | 已确认结果 | 外部发送 |
| --- | --- | --- |
| `sender-1` | 消息到达时 15 分钟 delivery grant 已过期，返回 `authorization_expired`；没有模型调用，已接管的事件未落回 AstrBot 普通回复链。 | 无 |
| `sender-2` / `reply-e2cd040a02bc4929931e338dc82e230e` | 模型 `generated`，5740 tokens 已结算；一段回复收到原生 OneBot ACK。 | 一次确认发送 |
| `sender-2` / `reply-01b62a499c734d2aac2b3de8faccbf41` | 模型 unknown，5960 tokens 已结算且有原始响应回执引用；任务 `failed/worker_error`，模型轮记录停在 started。没有分段或工具调用，也未自动重放。 | 无 |

首批投递时间为 `2026-09-22T14:35:32.305304+00:00`，平台引用为 `onebot-message:cc3ae0d2815095768ebe66ce:278059699`，回执依据为 `onebot_reverse_websocket`。该回执证明平台 ACK，不证明用户阅读。

第二批模型调用开始于 `2026-09-22T14:35:47.253386+00:00`，结束于 `2026-09-22T14:35:51.096252+00:00`。它在首条发送完成约 15 秒后才开始，记录不支持并发冲突判断。现场测试时的 adapter 将派发后的原生解析、wire 校验及配置/人格复核异常统一归入 unknown，并尽量保留实际用量；现有持久记录没有原始回复或具体失败分类，不能据此确认是 JSON/claims 校验错误。

现场结束后已撤销 delivery grant、停止会话并恢复 `enabled=false`、`profile_id=preview-1`、`delivery_mode=preview`；关闭重载后的状态为 `runtime_open=false`、`session_state=unloaded`、`accepting=false`。独立 profile 和历史回执保留，未重放 unknown，也未读取或迁移 V1 用户数据。

随后已完成[模型失败分类与持久诊断](CORE_MODEL_FAILURE_DIAGNOSTICS_SLICE.md)：新调用可从 inspect 查看不含正文或原始异常的阶段和固定错误码，本地已验证原生解析、wire 拒绝及响应后复核失败；历史第二批仍没有可还原的分类。2026-09-23 已在在线实例定向重载新代码，新的 `sender-3` 运行库确认为 v15，新私聊批次的 `provider_request_failed` 已通过接口和重载后只读数据库核验，实际用量未知、未发送。独立 provider 探测、具体原因的证据限制，以及撤权/停机/恢复关闭的结果见[诊断现场复验](CORE_ASTRBOT_DIAGNOSTICS_LIVE_20260923.md)。timeout/unknown 对账、恢复和更广的 Delivery 场景仍需补齐；此前单目标 ACK 不代表 G4/G8 或直接替换发行完成。
