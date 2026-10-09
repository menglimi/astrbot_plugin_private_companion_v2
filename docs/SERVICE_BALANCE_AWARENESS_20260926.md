# V2 服务余额感知

V2 可查询 Bot 使用的服务余额，并把低余额作为私聊主动联系的候选。它不是用户的账户余额或付款义务。该能力默认关闭；只有已授权的私聊目标同时开启 `proactive.contact.enabled`、`automatic_enabled`、`balance_awareness_enabled` 和 `environment.enabled` 后才会查询。模型可以跳过联系；真实发送仍受原会话、免打扰、联系预算、来源时效和发送前复核约束。

可用「陪伴小屋 → 此刻，对话能读到什么 → 余额感知」直接配置 NewAPI；可选 NewAPI 用户 ID 用于显式指定账户，额度单位除数默认 `500000`。个人访问令牌保存在 AstrBot 插件宿主设置中，接口只返回是否已配置，不回显令牌。页面保存的数据源优先于环境变量；移除页面配置后会回退到环境变量。自定义 HTTPS JSON 来源继续使用宿主进程环境变量：

页面填写的用户 ID 会通过 `New-Api-User` 请求头传给 NewAPI；留空时使用令牌所属账号。

| 环境变量（均以 `COMPANION_V2_BALANCE_` 开头） | 用途 / 默认值 |
| --- | --- |
| `PROVIDER` | 可选；`json`（默认）或 `newapi`。 |
| `URL` | 必填；JSON 模式填写完整 HTTPS 地址。NewAPI 模式填写实例根地址，可带反向代理子路径；适配器请求 `/api/user/self`。不允许 URL 内嵌凭据或重定向。 |
| `API_KEY`、`AUTH_HEADER`、`AUTH_SCHEME` | 可选；JSON 模式默认用 `Authorization: Bearer <API_KEY>`。NewAPI 模式必填，使用 NewAPI 用户访问令牌并固定以 Bearer 发送。 |
| `CUSTOM_HEADERS` | 可选 JSON 对象，用于接口要求的其他请求头；不能与鉴权请求头重复。 |
| `JSON_PATH` | JSON 模式余额的点分路径，默认 `balance`，例如 `data.remaining` 或 `data.0.remaining`。NewAPI 模式固定读取 `data.quota`。 |
| `TOTAL_JSON_PATH`、`USED_JSON_PATH` | 可选；有总额时可按比例判断。两者均设置且不设置 `JSON_PATH` 时，按总额减已用额计算余额。 |
| `VALUE_DIVISOR` | 数值单位除数，JSON 模式默认 `1`；NewAPI 模式默认 `500000`，并应改为该 NewAPI 实例的 `QuotaPerUnit` 设置值。 |
| `CURRENCY_LABEL` | 页面显示单位，默认 `额度`；NewAPI 可设为实例实际使用的 `USD`、`元` 等单位。 |
| `TIMEOUT_SECONDS` | 单次请求超时，默认 6 秒，允许 1–10 秒。 |

例如接口返回 `{"data":{"balance":825,"total":10000}}`，以分为单位时设置 `JSON_PATH=data.balance`、`TOTAL_JSON_PATH=data.total`、`VALUE_DIVISOR=100`。接口只接受有限大小的 JSON 和非负有限数；失败或过期观测会退避 5 分钟，不生成联系。

NewAPI 模式会调用 `GET /api/user/self` 并直接读取响应中的 `data.quota` 作为当前剩余额度。`data.used_quota` 是累计用量，不能再从 `quota` 中扣减。页面令牌必须是带 `profile:read` 范围的 NewAPI 仪表盘个人访问令牌（Personal Access Token，当前版本使用 `nap_` 前缀），不是模型调用用的 `sk-` API Key；页面不会回传已保存令牌。环境变量模式同样使用用户访问令牌。维护页首次载入时会查询一次，也可点「重新查询」刷新；返回值只包含余额、显示单位和观测时间。额度按 NewAPI 的 `QuotaPerUnit` 换算，标准默认值为 `500000`，实例修改过此设置时请同步调整页面的单位除数或环境变量 `VALUE_DIVISOR`。

联系配置在 `proactive.contact` 组中：`balance_check_interval_minutes` 默认 60、`balance_message_cooldown_hours` 默认 24；绝对低/危急阈值默认 10/3，百分比低/危急阈值默认 15/5。绝对值或百分比满足任一条件即触发，危急优先；没有有效总额时仅用绝对阈值。`balance_include_amount_in_message` 默认 `false`，此时模型只得到等级，不得到金额；开启后用 `balance_currency_label` 标注金额单位。新的正常观测清除提醒冷却，低到危急可提前升级一次。

这份记录只说明当前源码。最终 ZIP 尚未重建，真实接口、模型决策和 QQ 投递按[真实验收表](V2_REAL_WORLD_ACCEPTANCE_CHECKLIST.md)执行；不使用或迁移 V1 用户数据。
