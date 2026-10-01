# QQ 空间拓展落地记录（2026-10-02）

状态：**基础能力已落地**（刷空间 / 点赞 / 回复 / 发空间四项，按能力安装与授权，装完出现在陪伴小屋行动页）。
发空间的内容生成策略（说什么、什么时候说、概率与时段）**按用户要求留待后续讨论**，本次只提供「已授权即可发布」的安全通道。

## 一、为什么是「本体自带的可安装拓展」

- 旧版（V1）已有完整 QQ 空间实现，但 V2 的生产代码 `qzone` 零命中，只在旧实现里跑；现状是 Content 提供方把开关映射回 V1 属性并代理旧路由，属欠账。
- 本工程约定不允许为领域功能另建 V2 本体，因此 QQ 空间**实现在 V2 内部**，但**不写进核心对话链**：它是一份自带的能力包（`extension_id = "qzone"`），必须经过
  1. 目录登记 → 2. 固定版本安装（`acquire`）→ 3. 按 Bot 角色启用 → 4. 按用户/会话同意 → 5. 身份授权 `extension.tool.invoke`
  任何一步没做，四个动作都不会执行；「插件在跑」不等于「角色被允许公开发言」。
- 安装即可用、撤销即不可用，是本切片要保证的语义；凭据、熔断与配额另行约束。

## 二、分层与文件

| 层次 | 位置 | 职责 |
| --- | --- | --- |
| 协议（纯函数） | `companion_v2/qzone/protocol.py` | Cookie 归一与 `g_tk` 计算、宽松 JSON 与脚本尾巴解析、嵌套错误码、四个端点与点赞票据的请求构造、正文与长度校验 |
| 解析（纯函数） | `companion_v2/qzone/feed.py` | `msglist`、H5/旧版 HTML 动态、评论、原图 URL 归一到统一的动态记录；无作者/无身份/无正文即丢弃，官方推广账号过滤 |
| 动态句柄 | `companion_v2/qzone/references.py` | 刷空间返回**不透明引用**，点赞/回复只能作用于本次会话扫到的动态；引用有过期、容量与「一次动作」约束 |
| 运行状态 | `companion_v2/qzone/policy.py` | 登录失效递进熔断（12h/24h/7d，成功后清除）、动作间隔、每日上限、重复与相似度去重；状态存 `memory_views`（kind `qzone.runtime.v1`），无需迁移 |
| 动作编排 | `companion_v2/qzone/service.py` | 四项动作的统一顺序：配置闸 → 熔断闸 → 引用解析 → 本地操作预留 → 请求 → 判码 → 结果复核 → 回执；「投递结果未知」落 `UNKNOWN` 且不重发 |
| 能力声明 | `companion_v2/qzone/capability.py` | 固定包描述符、能力 id、家具、四个模型工具的声明（工具接线见「后续」） |
| 授权服务 | `companion_v2/capabilities/qzone_access.py` | 安装/撤权、角色启用、四项能力同意、身份授权；`edit_token` CAS + `operation_key` 幂等 |
| 宿主传输 | `astrbot_host/qzone_client.py` | aiohttp 会话、OneBot 凭据获取、`q_tk` 一致的请求头、GET/非 GET 失败语义 |
| 凭据来源 | `astrbot_host/qzone_transport.py` | OneBot `get_cookies`/`get_credentials` 候选与手动 Cookie 来源（`QZONE_COOKIE` 或数据根 `qzone_cookie.txt`） |
| Dashboard 路由 | `astrbot_host/qzone_api.py` | `…/qzone-extension/{status,configure,feed,like,comment,publish,refresh-credentials,agenda-suggestions/resolve}`，只接受 Dashboard 身份与固定私聊目标 |
| 日程建议桥 | `companion_v2/qzone/agenda_link.py` | 把发布时带的 `agenda_proposal` 落成可查询的 `pending` 记录，供模型与页面读取，并记录是哪个日历回执把它关掉；**不写日程** |
| 页面 | `pages/陪伴小屋/app.js` + `action-page.css` | 行动页「QQ 空间拓展」区块：安装/停用、刷空间、点赞、回复、发空间、刷新凭据 |

## 三、关键不变式

1. **凭据不进配置**：不回显、不写日志、不写插件配置、不进提示词；手动 Cookie 只从环境变量或 V2 数据根文件读取（不进配置导出）。
2. **一次操作一份会话**：同一次请求复用同一份 Cookie 与其 `g_tk`；`send` 内部不重试，也不做「部分成功」推断。
3. **未安装、未启用、未同意就没有动作**：服务层对每个能力在动作前复核「安装包一致且 ACTIVE + 该角色已启用 + 本会话同意」，三条缺一即拒；因此撤权立即生效，与页面/工具走哪条路无关。
3. **未知不重放**：非 GET 超时/断连一律记为「投递结果未知」→ 本地操作落 `UNKNOWN`，同一 `operation_key` 的重放会被拒；页面文案只能说「已受理/已提交，等待同步」，不得说已确认。
4. **扫码才可动**：点赞与回复必须引用本次会话刷到的动态，跨会话/过期引用一律拒绝；扫面结果不暴露平台票据。
5. **公开动作有节流**：可关闭总闸与三项子开关、动作最小间隔、每日说说上限、重复与相似度去重；登录失效时**先熔断再谈生成**。
6. **冷却是保守且可恢复的**：缺连接不算失败（不升级），成功后立即清除；失效原因会显示在页面并暂停写操作。

## 四、发空间的主题与场景策略（模型依据目录判断，程序只守门）

要求：发空间**先定主题**，再按主题决定发布场景与来源处理；分类必须由模型依据固定目录完成，**不得**用「委屈」「新闻」等具体词语触发写死的分支。

**目录（唯一分类依据，`companion_v2/qzone/topics.py`）**
- 七个主题：`life_documentary` 生活纪实类、`emotion_reflection` 情绪感悟类、`interest_hobby` 兴趣爱好类、`opinion_hot` 观点/热点类、`help_interaction` 求助/互动类、`ritual_memory` 仪式纪念类、`meaningless_status` 无意义水动态。每个主题带两段文字：**如何判断**（什么算这一类、什么不算）与**写作边界**（哪些能说、哪些不能）。
- 七个场景：`conversation` 对话、`external_material` 外部资讯或材料、`agenda` 日程与待办、`role_activity` 角色活动与记录、`relationship` 关系与互动、`date_marker` 日期与纪念节点、`free_expression` 自由表达。每个主题只放行它自己的场景——这是集合判断，不做文本匹配。
- `TopicDecision`（主题/场景/置信度/是否发布/依据/来源引用/日程提案）由模型以严格 JSON 给出，`parse_decision` 逐字段校验；`topic_prompt.parse_output` 再叠加**配置的置信度门槛**。

**程序守门（三道，全部与文案无关）**
1. 目录成员与场景匹配：主题、场景必须在目录内，且场景属于该主题（`policy.topic_reason`）。
2. 配置门槛（`qzone` 组，实际生效）：主题开关、该主题放行的场景、置信度门槛、**是否需要人工确认**、该主题每日上限、该主题冷却分钟；任一不过即返回带原因的明确 code。
3. 发布编排（`service.publish`，唯一入口）：窗口/角色配置闸 → 能力闸（安装＋角色启用＋本会话同意）→ 主题闸 → 去重与相似度 → 本地回执预留 → 请求 → 判码 → 结果复核。非 GET 超时/断连记「投递结果未知」并落 `UNKNOWN`，同 key 重放被拒。

**模型引导（两处，同一份目录）**
- 工具说明：`qzone.post.publish` 必填 `text`/`topic`/`scene`/`confidence`，描述里带完整目录（七个主题的判断与可用场景、七个场景、置信度含义、被拒时不要反复重试）。
- 每轮对话指引：`tool_loop.augment` 里**仅当本轮该工具真的被准入**（安装＋角色启用＋本会话同意）才追加 `CONVERSATION_GUIDANCE`。这段只讲目录与边界，**不含**分类任务的「只输出一个 JSON 对象」契约，避免污染普通回复；分类契约保留在 `topic_prompt.INSTRUCTION` 供独立分类调用使用。

**人工确认与自动发布**
- 页面发布＝人在操作：选了主题与场景即视为确认，传 `topic_confirmed=True`。
- 模型调用恒为 `topic_confirmed=False`；只有管理员同时打开 `topic_auto_enabled` 且关掉 `topic_require_confirmation` 时才可能自动发布（默认关/开，模型只能提出主题，不能自己确认）。

**求助类结果反向影响日程**
- 发布求助时可带 `agenda_proposal`（`agenda_id`＋读到的 `expected_revision`＋意图＋来源引用，`status=pending_confirmation`）。它随公开求助作为**证据**记录，**不修改日程**，也不得声称已修改。
- **提案会被真的留住**：`companion_v2/qzone/agenda_link.py` 把它落成一条可查询记录（`memory_views` kind `qzone.agenda_proposal.v1`，按角色归属，`view_id` 由「角色＋发布操作＋日程项」决定，因此同一次发布不会重复登记），状态为 `pending`；发布路径在**预留回执之后、发出请求之前**登记，所以「结果未知」的发布同样会留下这条待办。
- **模型看得到它**：这一步的工具被准入时，`tool_loop.augment` 会把待处理建议作为一条 `PromptMaterial`（`qzone.agenda/open_agenda_suggestions`）注入本轮，让角色知道「这个问题还开着，答案要带回日程」。
- **写回仍然归日程域**：真正的改动是显式操作——`CalendarService.command(context, identifier=<agenda_id>, action="revise|exception", expected_revision=…, sources=(结果来源,))`，它自己做证据校验、回执落 `calendar_receipts`、来源进 `calendar_history`。qzone 侧**不代替**它写，因为回复的受治理来源与日历域的访问规则都不属于这个域。
- **闭合是可审计的**：`service.resolve_agenda_suggestion` 把建议标记为 `applied`（**必须带日历回执编号**）或 `dismissed`，走与其他空间动作同一套 `reserve/transition`（同 key 重放答回执）；宿主路由 `POST …/agenda-suggestions/resolve` 供页面调用，`status.runtime.agenda_suggestions` 供页面与模型读取。

**配置（`qzone` 组 47 个字段）**
基础 12 项（总开关、三项动作开关、读取条数、动作间隔、单轮上限、回复扫描条数、每日上限、`topic_auto_enabled`、`topic_require_confirmation`、`topic_prompt_guidance`）＋ 每主题 5 项（`_enabled`、`_scenes`、`_min_confidence`、`_daily_max`、`_cooldown_minutes`），全部经真实配置服务读写并纳入页面覆盖审计。

## 五、定向验证（开发期与交付包）

```powershell
# 开发期（工作树）
python -m unittest tests.test_qzone_extension -v     # 53 项通过（唯一用例数，夹具已拆出基类避免重复执行）
python -m compileall -q companion_v2 astrbot_host
python tools/audit_page_config_coverage.py           # 19 个分区 / 335 字段全通过（已纳入 qzone 组）
node tests/test_section_wiring.cjs                   # 8/8 全绿（后端 22 = spec 22 = 挂载 22）
python tools/sync_framework_page.py --check          # changed: []
```

覆盖：Cookie 形状（含 OneBot 包裹 `{"cookies": ...}`）、`g_tk` 一致、宽松 JSON 与脚本尾巴、嵌套错误码、点赞票据、H5 票据、引用过期/跨会话/一次动作/容量、熔断升级与恢复、间隔与每日上限与重复去重、扫描不写操作回执、禁用时不触网、未安装/已撤权时不触网、点赞回执 `COMPLETED`、未确认只报 `accepted`、未知落 `UNKNOWN` 且不重发、同 key 重放答以回执、鉴权失败冷却落盘、本地日期换算、能力包声明、**缺昵称时不外泄账号号段**，**配置组经真实配置服务读写**（默认值全关、写入后读回、超范围被拒），**安装链本身**（安装后角色随即能刷空间、撤权后立刻不能、旧 `edit_token` 与畸形命令被拒），**发空间的主题策略**（七主题×七场景放行矩阵、必填项、配置门槛、置信度门槛、确认与自动发布语义、主题级上限与冷却、严格决策解析、工具目录完整性、对话指引不含分类契约、页面目录=实际放行集合），以及**求助建议的闭环**（一次发布只登记一条、重放不新增、模型材料里可见、标记已写回必须带日历回执、同 key 重放答回执、忽略不需要回执、别的角色读不到）。

```powershell
# 交付包（源码在插件目录之外构建，解包后再跑一次）
python tools/build_v2_release.py --output D:\codex\workspaces\companion-v2-release-20261002-qzone-r2
python tools/verify_v2_release.py --release D:\codex\workspaces\companion-v2-release-20261002-qzone-r2 `
  --extract-to D:\codex\workspaces\companion-v2-verified-20261002-qzone-r2 --host-check
```

结果：8 个包（核心 + 七个可选提供方）哈希、CRC、文件清单与 Python 语法全部通过；`_conf_schema.json` 默认值断言通过；**唯一公开页仍为「陪伴小屋」**（本次只加 API 路由，不加页面）；宿主检查 `{"life_routes": 4, "state": "stopped", "route_cleanup": true, "model_calls": 0, "platform_calls": 0}`。
核心包 `astrbot_plugin_private_companion_v2-2.0.0.zip` SHA-256 `a96d7c24d68c107a532dbc8f4ad3999f6c32a7a21b609b93db6a4d2edfdcc60d`（1530 个文件 / 1051 个 Python 文件）；解包目录内再跑 `tests.test_qzone_extension` → **33 项通过**；抽查六个关键文件（`page-build.json`、`app.js`、`config-editor.js`、`page_api.py`、`qzone/feed.py`、`qzone_api.py`）源码与包内 SHA-256 完全一致。

未覆盖的验收：真实 AstrBot 加载后的页面点击、真实 OneBot 凭据获取与真实 QQ 空间读写；`tools/check_action_page.cjs` 等 13 个浏览器检查需要 Playwright 与本机 Chromium，本沙箱禁止其建管道，须在沙箱外补跑（建议 320/390/960 三档看无横向溢出）。

## 六、已知限制

- 页面桥的请求上限是共享的 15 秒（`product-page.js` 的 `bounded()`），而写超时是 30 秒并带最多三次结果复核；慢网络上可能先超时并显示「结果未知」。这是诚实的措辞，但属假阴性；要减少它需要给这一族请求单独放宽上限。
- 宿主客户端 `trust_env=False`（忽略代理环境变量）与 `allow_redirects=False`（3xx 不静默跟随）；响应体未封顶。需要代理访问空间时另加开关。
- 作者昵称缺失时按 `1******89` 脱敏（领域层与页面各挡一次），因此模型与页面都拿不到完整账号号段。

## 七、后续（未做，明确记录）

1. **模型工具接线**：`capability.py` 已声明四个工具，但尚未注册进对话工具目录。本体自带能力需要 ① 独立的工具端口（或复合端口）② 成功结果发布 `SourceRecord`；两者都涉及对话链改动，单独一片做。
2. **发空间内容策略**：说什么、何时说、概率/时段窗口/风格提示词、配图（`cgi_upload_image` + `richval`/`pic_bo`）。
3. **回复评论收件箱**：定时扫描自己动态下的评论并回复（V1 的 `qzone_comments.py` 语义，含首轮播种与三层幂等）。
4. **沙箱外补跑浏览器验收**：`node tools/check_action_page.cjs`（320/390/960 三档）。

## 八、手工启用步骤

1. 让目标账号的 OneBot 连接在线（或把 Cookie 写到 `QZONE_COOKIE`／数据根 `qzone_cookie.txt`）。
2. 打开陪伴小屋 → 行动 → 「QQ 空间拓展」→ 点「安装并启用」。
3. 刷新凭据，确认状态显示已就绪；此后可按需开启点赞/回复/发空间子开关。
