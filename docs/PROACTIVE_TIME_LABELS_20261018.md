# 主动联系的时间标签：星期由程序给出，不由模型推算

日期：2026-10-18。用户报告 00:43 的主动消息写了“周六了呢”，当天实际是周日。

## 1. 症状与现场证据

运行库 `profiles/qq-v2-stream-20260926/runtime/companion-v2.sqlite3` 中 `proactive_contacts` 第 148 行：

- `body`：`过了零点啦…周六了呢刚把书桌收拾好安静得有点不习惯`
- `created_at`：`2026-10-17T16:43:16Z`，即本地 `2026-10-18 00:43:16 +08:00`，星期日

同轮 `proactive_prompt_snapshots` 第 10 行保存的实际提示词里，模型只拿到：

```json
"local_now": "2026-10-18T00:43:01.094730+08:00",
"local_date": "2026-10-18",
"local_time": "00:43",
"timezone": "Asia/Shanghai"
```

全部 10 条材料（contact_intent、communication_state、最近对话、已发送背景）没有 `星期`／`weekday` 字样。也就是说：“过了零点”是对的，因为时间直接给了；星期是模型自己把 ISO 日期换算出来的，换错了一天。

同一批库内 153 条主动消息里只有 6 次提到星期，其中 3 次差一天（10-11 周日说周六、10-17 周六说星期五、10-18 周日说周六）；同一模型在 10-17 08:46 又说对了“今天周六”。这说明它是在推算而不是读数据，因此同一路径上正确率不稳定。

## 2. 根因

前台回复路径一直有星期：`astrbot_host/core_reply_context.py` 用 `project_local_date` 生成 `local_calendar_context`，其中 `weekday` 为“星期日”这类标签。主动路径的 `contact_intent` 由 `companion_v2/proactive/prompts.py` 的 `request_for()` 组装，只有 `local_now`／`local_date`／`local_time`／`timezone`，没有 `weekday`、也没有时段标签，于是每个主动目的（问候、关怀、资讯、日历、饭点……）都要模型自己做日历换算。

## 3. 改动

- `companion_v2/conversation/date_context.py`：`_period()` 提升为公开的 `period_label()`，回复路径与新代码共用同一套时段词（凌晨／早上／上午／中午／下午／晚上／夜里）。
- `companion_v2/proactive/prompts.py`：`contact_intent` 新增 `weekday`（取自既有 `WEEKDAYS`）、`is_weekend`、`period`；主指令写明星期只取 `contact_intent.weekday`、周末只取 `is_weekend`，不要用日期自己换算、不要沿用历史里的星期、字段缺失时不提星期；日常问候指令按 `local_time`／`period`／`weekday` 对齐时段；夜间低压力问候明确“不报时、不报日期和星期”。
- `companion_v2/proactive/greetings.py`：夜间问候的联系由头同样写明不报时、不报日期和星期，避免提示词与由头互相矛盾。

标签仍由程序计算，模型只负责使用；权威时钟、时区、周几换算不交给模型，符合“提示词负责表达、程序负责可信事实”的既有分工。

## 4. 验证

新增/更新的定向用例：

- `tests/test_style_prompts.py`：真实事故回归（2026-10-18 00:43 → 星期日、周末、凌晨），隔夜资讯用例补 `weekday`／`is_weekend`／`period`，夜间问候补“不报日期和星期”。
- `tests/test_proactive_dedup.py`：真实联系链路上 `contact_intent` 的三个新字段与时钟一致。
- `tests/test_conversation_date_context.py`：`period_label()` 的时段词边界。

本轮运行（AstrBot 自带 Python 3.12）：`test_style_prompts`、`test_conversation_date_context`、`test_proactive_dedup`、`test_proactive_rhythm_and_greetings`、`test_proactive_memory` 共 88 项通过；`test_proactive_contacts` 46 项通过。

已知与本改动无关、在干净树上同样失败的用例（供后续统一验收时甄别）：`tests/test_proactive_date_events.py` 4 项（`不证明对方生日`、`管理员配置农历日期` 两处断言在未改动的树上也失败）、`tests/test_proactive_end_to_end.py::test_source_failure_opens_a_durable_breaker_and_its_window_release_recovers` 1 项（`1 != 0`）。

## 5. 未做

日记的 `writing_date` 材料仍只有日期与时区；角色日记若要点出星期，同样需要程序给标签。本轮只修用户可见的主动消息，未改日记、日程规划与前台回复路径的既有口径。
