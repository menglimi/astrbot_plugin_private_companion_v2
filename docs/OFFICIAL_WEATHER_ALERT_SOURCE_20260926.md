# 官方天气预警来源（2026-09-26）

V2 已实现独立的和风天气官方预警读取适配器、领域合同和默认关闭的私聊主动联系链路。Open-Meteo 当前天气码仍只表示观测到的天气现象，不表示官方预警。此链路只读取管理员配置的角色所在地，不推断对方所在地；正常运行不依赖 V1 配置或缓存。陪伴小屋尚无预警设置界面，在线宿主和 QQ 尚未验收。

**2026-09-28 起，和风的实况与预警共用同一份凭据与同一个适配器族**：当前天气走 `/v7/weather/now`，预警走 `/weatheralert/v1/current`。两者认证方式完全一致，凭据读取集中在 `astrbot_host/qweather_credentials.py`。已配置和风凭据时，当前天气默认改用和风（见[规划天气观测](PLANNING_WEATHER_SOURCE_20260926.md)的数据源章节）。

已核对的官方接口为 `GET /weatheralert/v1/current/{latitude}/{longitude}`，查询点最多保留两位小数；开发者使用自己分配的 `*.qweatherapi.com` API Host。宿主适配器仅向固定 HTTPS 路径请求，不跟随重定向、代理或超大响应。

## 凭据环境变量（2026-09-28 起）

**和风天气的实况与预警共用同一份凭据。** 和风一个项目签发一套凭据，两个产品接口都用它认证，因此不需要填两遍，也不应该填两遍——填两遍就会出现「实况换了新凭据、预警还在用旧的」这种只看一半的故障。

环境变量有两代名字，读法是**按组优先、整组生效**：

| 代次 | 变量前缀 | 说明 |
|---|---|---|
| 当前 | `QWEATHER_` | 语义中立，实况与预警共用 |
| 旧版 | `QWEATHER_ALERT_` | 早期只有预警功能时使用；仍然有效 |

规则：先看 `QWEATHER_` 组，只要该组有任何一项非空就以该组为准；否则看 `QWEATHER_ALERT_` 组。**不会跨组各取一半**——组内不完整会直接报配置错误，而不是悄悄用另一组的字段补齐。（跨组补齐会拼出一套从未被验证过的凭据组合，比直接报错危险。）

任一组内的六个变量：

```
QWEATHER_API_HOST           和风分配的 API Host，必须形如 *.qweatherapi.com
```

认证方式二选一，**互斥**：

```
方式一（API Key）
QWEATHER_API_KEY            32 位 API Key

方式二（JWT，Ed25519 私钥签发短时令牌）
QWEATHER_CREDENTIAL_ID
QWEATHER_DEVELOPER_ID
QWEATHER_PROJECT_ID
QWEATHER_PRIVATE_KEY_FILE   现存 PEM 私钥文件的绝对路径
```

全部缺失时两个端口都不可用，当前天气退回 Open-Meteo、预警端口关闭。**混用两种认证方式、或某一方式只填了一部分，都会在启动时报配置错误。**

**凭据不能放入角色设置或仓库。** 角色配置是可导出的，和风令牌不是可导出的秘密。需要在页面上配置天气的操作员应知道：页面上的天气设置只管「观测什么、什么时候说」，不管「用什么凭据」。

改名迁移是安全的：已在用 `QWEATHER_ALERT_*` 的部署可以不动，也可以整体换成 `QWEATHER_*`；两者都存在时以 `QWEATHER_*` 为准。

领域合同保留原始 `metadata.attributions`、预警发布机构、标题、严重程度、发布/生效/失效时间、`alert/update/cancel` 与 `supersedes`。取消、被更新替代、未生效、已过期、来源取样超过 10 分钟或地点已变更的条目都不会成为有效候选。真实零结果响应可能省略归因，此时允许空归因且没有候选；只要有预警，缺少归因、时间或分类异常仍整体拒绝。历史样例的 `Moderate` 等已知严重程度大小写归一化，未知值仍拒绝。跨次轮询由 v34 持久账本追踪更新链和原地点；同一更新链不重复投递，取消或空结果会撤销旧来源。v35 语音诊断迁移之后，预警表与迁移记录仍保留。

主动联系只在私聊、环境类联系允许、`official_weather_alert_enabled=true` 且角色地点明确配置预警城市和目标镇街时轮询。`planning_weather_location` 可在原有 `name/latitude/longitude` 外增加 `alert_city` 和 `alert_area`，两者须成对填写；前者是通告所属城市，后者是需要核对的镇街名称，不影响普通天气观测。只有城市级地点标签而无目标镇街时，官方预警不会轮询。

接口按坐标返回预警，但响应没有结构化的受影响镇街列表；坐标命中不能证明通告适用于目标镇街。生成时模型必须核对发布机构、标题与正文，只在通告明确覆盖整个配置城市或明确列出目标镇街，且没有排除目标镇街时发送。模型须附带可在预警标题或正文中找到的范围原文；缺少依据、仅列其他镇街、范围模糊或含目标镇街排除条款时跳过。程序复核引文确实出自原文、包含全市或目标镇街表述，并拦截常见的目标镇街排除语句；这不能替代对非标准自然语言范围的人工验收。

官方预警候选排在普通天气寒暄和天气变化之前。查询失败不发送；生成和逐段投递时复核原账本、地点、来源、受众与 10 分钟观测有效期。marker 必须对应同一预警账本行及来源，不能借用另一条仍有效的预警。最终正文由程序固定追加“和风天气”名称、链接及响应中的完整原始归因，模型只改写自然语言正文。

以上复核基于最近一次本地官方观测和持久状态，实际网络发送瞬间不会再请求官方 API；取消消息要到下一次成功轮询后才会撤销旧来源，不能承诺零延迟。预警合成链路和存储迁移此前 **25 项定向测试通过**；本次 API Key、旧响应形状和主动联系范围 **13 项定向测试通过**。

本次从 V1 配置和数据只读取得有效 API Host、API Key 与已有角色地点，仅在测试进程环境中交给 V2 端口。V1 的专属预警 Host/Token 字段当前为空，生效值来自 `weather_config.weather_api_host` 与 `weather_config.weather_token` 回退；`qweather_location` 的 `label/lat/lon` 可映射为 V2 `planning_weather_location` 的 `name/latitude/longitude`。V2 端口完成一次真实官方请求并归一化：预警 0 条、归因 0 条、有效候选 0 条。未写 V1、未持久化凭据，也未发送 QQ。V1 当前 `weather_alerts` 缓存同样没有预警，`weather_alert_awareness` 没有待发送事件；这两个旧结构是过期风险较高的观测/投递状态，不作为 V2 v34 账本的迁移输入。迁移配置时仍应在 V2 独立数据根显式设置角色地点，并重新查询官方接口建立基线，不能把旧已投递记录作为新事件重发。

真实有效预警响应、在线 AstrBot 和 QQ 投递回执尚未验收。下一步在出现有效官方预警时核对归因与 v34 更新链，再在单账号受控环境验收一次 QQ 发送；此前保持默认关闭。

接口、认证、API Host、归因及预警变更依据：

- https://dev.qweather.com/docs/api/warning/weather-alert/
- https://dev.qweather.com/docs/api/warning/alert-changes/
- https://dev.qweather.com/docs/api/weather/weather-now/ （当前天气实况，2026-09-28 接入）
- https://dev.qweather.com/docs/resource/icons/ （图标码与天气现象对照，用于映射到 WMO 码）
- https://dev.qweather.com/docs/configuration/api-host/
- https://dev.qweather.com/docs/configuration/authentication/
- https://dev.qweather.com/docs/terms/attribution/
