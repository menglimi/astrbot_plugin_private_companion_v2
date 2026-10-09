# 规划天气观测（2026-09-26，来源于 2026-09-28 扩展）

V2 规划可读取角色所在地的当前天气。此能力默认关闭，仅在 `planning_enabled`、`calendar_enabled`、`planning_weather_enabled` 同时启用，角色日历写入有授权，且 `calendar.plan` 后台模型可用时取样。设置保存在角色生活配置中，使用独立 V2 数据；不读取 V1 的天气城市、凭据或缓存。

## 数据源：全局选择，自动模式按凭据回退

天气源在插件级全局配置 `weather.provider` 中选择：`auto`、`qweather` 或 `open-meteo`。
默认 `auto` 会在存在和风凭据时使用和风，否则使用 Open-Meteo；显式选 `qweather` 时
必须配置和风凭据，显式选 `open-meteo` 时始终使用 Open-Meteo。

| 情况 | 实况来源 | 说明 |
|---|---|---|
| `weather.provider=auto` 且已配置和风凭据 | **和风天气** `/v7/weather/now` | 自动模式优先和风 |
| `weather.provider=auto` 且没有和风凭据 | Open-Meteo | 零配置可用 |
| `weather.provider=qweather` | **和风天气** `/v7/weather/now` | 必须有和风凭据，否则配置无效 |
| `weather.provider=open-meteo` | Open-Meteo | 不使用和风凭据 |

和风优先的理由不是偏好，而是只有它能同时提供实况与官方预警——一套凭据覆盖两件事。
官方预警仍由独立的和风预警端口读取；实况源选择不会替代预警凭据。迁移时，V1 的
`qweather` 会写入全局 `weather.provider=qweather`，Open-Meteo 的旧拼写会归一到
`open-meteo`；V2 不支持的 OpenWeatherMap 或高德来源不会伪装成等价源。天气凭据仍从
环境变量读取，见[官方天气预警来源](OFFICIAL_WEATHER_ALERT_SOURCE_20260926.md)的环境变量章节。

两个源都归一化到同一份 `WeatherSnapshot`，下游（规划、主动联系、预警）不感知来源差异。和风的天气图标码会映射到 Open-Meteo 使用的 WMO 码，因此 `weather_code` 语义一致；映射表见 `astrbot_host/qweather_weather.py`。未知图标码按族（1xx 晴、3xx 雨、4xx 雪、5xx 雾）降级而不是整条丢弃。实况文本缺失时按图标回填中文描述，不因少一个标签就作废整次观测。

## 地点

`planning_weather_location` 是管理员明确设置的 JSON 字符串，例如：

```json
{"name":"角色所在城市","latitude":31.23,"longitude":121.47}
```

`name` 仅为角色地点标签，经纬度用于固定接口请求；它不表示用户所在城市。启用天气前必须填写有效地点。更换地点后，采样中的旧地点结果不会进入新规划。

**`name` 是给人看的标签，不是查询参数。** V1 的 `weather_location` 允许填和风 LocationID（形如 `101020100`），那不是地名；迁移时要用可读的城市名填 `name`，LocationID 不能直接搬进来，否则界面上会显示成一串数字。

官方天气预警可在同一个 JSON 中额外成对填写 `alert_city` 和 `alert_area`，分别为通告所属城市和需核对的目标镇街。普通天气观测不要求这两个字段；缺少目标镇街时不会触发官方预警联系。

## 新鲜度

规划材料只包含来源、地点、观测时间、有效截止时间及当前天气数据。观测超过两小时、比取样时钟超前超过五分钟、来源或地点不符时会被舍弃。接口失败、超时或响应异常只标记 `weather_unavailable`，规划本身继续执行。

**新鲜度上限是结构性的两小时（`WEATHER_MAX_AGE_MINUTES`），操作员只能在 5–120 分钟之间收窄，不能放宽。** 这个上限匹配「一次当前天气观测」的语义：观测越旧，越不能拿来描述现在。V1 允许把刷新间隔配到几百分钟，迁移时会被截断到 120——刷新会比原来频繁，这是有意的，不是迁移缺陷。

天气用于临近时段安排，不是未来预报，也不证明角色已外出。

主动联系另有默认关闭的 `proactive.contact.weather_checkin_enabled` 与本地时间 `weather_checkin_time`。启用后，仅在管理员已明确配置 `planning_weather_location` 的私聊中，于联系设置的 `quiet_timezone` 对应时段取一次当前天气（和风或 Open-Meteo，见上）；它不要求启用生活规划。天气来源有两小时新鲜度与本次时段的截止时间，进入既有来源复核、联系额度、免打扰、模型决定和投递链。取样失败短暂退避；地点、偏好或原对话变更会使旧候选失效；同一天已生成的任务在重启后不重发。模型可以跳过，不应把角色所在地说成用户所在地，也不应根据当前观测推断未来天气或要求用户采取行动。

天气变化与[官方预警主动联系](OFFICIAL_WEATHER_ALERT_SOURCE_20260926.md)已有独立的默认关闭链路；仍没有真实用户定位或小屋场景天气同步。规划及主动联系运行链用宿主替身与合成响应验证；单次命令行请求确认 Open-Meteo 返回 UTC 偏移字段，和风实况源以合成响应验证码表映射与边界，尚未验收在线 AstrBot、真实模型或 QQ 效果。
