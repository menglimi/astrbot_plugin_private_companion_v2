# V2 服务余额感知

V2 可查询 Bot 使用的服务余额，并把低余额作为私聊主动联系的候选。它不是用户的账户余额或付款义务。该能力默认关闭；只有已授权的私聊目标同时开启 `proactive.contact.enabled`、`automatic_enabled`、`balance_awareness_enabled` 和 `environment.enabled` 后才会查询。模型可以跳过联系；真实发送仍受原会话、免打扰、联系预算、来源时效和发送前复核约束。

宿主进程环境变量配置 HTTPS JSON 接口，不把密钥写入 V2 配置、页面或模型材料：

| 环境变量（均以 `COMPANION_V2_BALANCE_` 开头） | 用途 / 默认值 |
| --- | --- |
| `URL` | 必填；完整 HTTPS 地址，不允许 URL 内嵌凭据或重定向。 |
| `API_KEY`、`AUTH_HEADER`、`AUTH_SCHEME` | 可选；默认用 `Authorization: Bearer <API_KEY>`。 |
| `CUSTOM_HEADERS` | 可选 JSON 对象，用于接口要求的其他请求头；不能与鉴权请求头重复。 |
| `JSON_PATH` | 余额的点分 JSON 路径，默认 `balance`，例如 `data.remaining` 或 `data.0.remaining`。 |
| `TOTAL_JSON_PATH`、`USED_JSON_PATH` | 可选；有总额时可按比例判断。两者均设置且不设置 `JSON_PATH` 时，按总额减已用额计算余额。 |
| `VALUE_DIVISOR` | 数值单位除数，默认 `1`；接口以分返回、阈值以元配置时设为 `100`。 |
| `TIMEOUT_SECONDS` | 单次请求超时，默认 6 秒，允许 1–10 秒。 |

例如接口返回 `{"data":{"balance":825,"total":10000}}`，以分为单位时设置 `JSON_PATH=data.balance`、`TOTAL_JSON_PATH=data.total`、`VALUE_DIVISOR=100`。接口只接受有限大小的 JSON 和非负有限数；失败或过期观测会退避 5 分钟，不生成联系。

联系配置在 `proactive.contact` 组中：`balance_check_interval_minutes` 默认 60、`balance_message_cooldown_hours` 默认 24；绝对低/危急阈值默认 10/3，百分比低/危急阈值默认 15/5。绝对值或百分比满足任一条件即触发，危急优先；没有有效总额时仅用绝对阈值。`balance_include_amount_in_message` 默认 `false`，此时模型只得到等级，不得到金额；开启后用 `balance_currency_label` 标注金额单位。新的正常观测清除提醒冷却，低到危急可提前升级一次。

这份记录只说明当前源码。最终 ZIP 尚未重建，真实接口、模型决策和 QQ 投递按[真实验收表](V2_REAL_WORLD_ACCEPTANCE_CHECKLIST.md)执行；不使用或迁移 V1 用户数据。
