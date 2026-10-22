# 角色级跨窗口在场与身份关联

日期：2026-10-19。目标：让同一角色在私聊中能接住“刚在群里看到你”这类连续感，在群聊中能认出当前发言者也是自己的私聊对象；同时保留现有受众合同，不把私聊正文带进群，也不把群内其他人的话带进私聊。

本切片包含**感知与提示词投影**，并补上进程内的角色级注意力租约；不改发送授权、记忆正本或关系记忆的受众边界。

## 一、结论与边界

| 维度 | 本切片行为 | 明确不做 |
| --- | --- | --- |
| 私聊看群 | 仅当前私聊对象**本人**近期在群里的公开文字摘要，最多 4 条、12 小时；每条附同一短窗口内其他发言账号数量 `peers` | 不读其他群成员正文、不读群公共记忆、不读私聊关系记忆以外的群材料；不保存其他成员账号或昵称 |
| 群聊看私聊 | 仅一个布尔值 `private_contact`，表示当前发言者与角色有过私聊 | 不返回私聊正文、时间、关系细节、称呼或权限 |
| 注意力 | 同一角色最近一次**本人**活动在群聊且 30 分钟内，私聊提示词可感知“刚从群里过来”；同一角色生成回复时持有进程内前台租约，另一窗口最多等 3 秒，超时则带“仍在生成”的转场提示 | 跨进程/跨重启的持久租约、强制抢占发送权 |
| 存储 | 角色级有界元数据，挂在 `runtime_metadata` | 不新增 SQL 表、不改 schema、不复制 Source 正文 |
| 开关 | `person.cross_window_awareness_enabled` 独立开关，同时仍受 `person.acquaintance_enabled` 约束 | 关闭后不写、不读、不注入 |
| 配置 | 回看小时、条数、注意力分钟、等待秒数、群内身份关联均可在「关系与权限 → 熟人卡」编辑 | 独立 Dashboard 页面或新扩展页 |

### 配置项

| 字段 | 默认 | 范围 | 作用 |
| --- | --- | --- | --- |
| `person.cross_window_awareness_enabled` | true | bool | 跨窗口在场总开关；关闭后不写、不读、不注入 |
| `person.cross_window_private_group_hours` | 12 | 1–48 | 私聊回看本人群活动的时长 |
| `person.cross_window_max_items` | 4 | 1–8 | 私聊最多注入几条群摘要 |
| `person.cross_window_attention_minutes` | 30 | 0–120 | “刚从群里过来”的有效分钟；0 关闭 |
| `person.cross_window_attention_wait_seconds` | 3 | 0–10 | 同一角色另一个窗口仍在生成时最多等待的秒数 |
| `person.cross_window_group_identity_enabled` | true | bool | 群聊中是否注入 `private_contact` 布尔值 |
| `person.cross_window_peer_minutes` | 5 | 1–60 | 统计“群里还有几个人在说话”的短窗口 |
| `person.cross_window_peer_reply_minutes` | 60 | 1–720 | 统计“有人接你之前的话”的回看窗口 |

这些字段注册在既有 `person` 配置组，页面标签与顺序在 `pages/陪伴小屋/config-editor.js` 的「熟人卡」分区中维护；不新增独立配置组或页面。

## 二、存储合同

实现位于 `companion_v2/role_work/awareness/`：

- `models.py`：文档版本 `role.awareness.v1`，最多 64 条事件、保留 24 小时、私聊提示最多取 4 条、话题摘要最多 48 字符、注意力窗口 30 分钟、文档最多 64 KiB。
- `store.py`：一个角色一个文档，键为 `role.awareness.v1:<role_owner_digest>`，使用既有 `runtime_metadata`，写入由调用方事务持有。
- `service.py`：写入入站/回复事件；按当前窗口受众生成快照；通过熟人卡读取 `private_contact`。

事件字段：

```text
at, window(private|group), group_id, platform, account_id, subject, speaker_account,
kind(spoke|peer_reply), topic, event_key, source, peer_count
```

约束：

- `window=private` 时 `topic` 必须为空，私聊正文不进入角色级文档；
- `window=group` 时只保存当前发言者自己的公开文字摘要，不保存其他成员正文；
- `event_key` 只用于入站幂等，不包含正文；
- `platform` / `account_id` 用于隔离同一角色的不同登录账号，读取时只取当前账号的同平台事件；
- `source` 保存原事件的完整 `SourceRef`；读取私聊摘要前用 `SourceRepository.validate_reference` 复核，原消息撤回、来源过期或依赖失效时丢弃该条摘要（注意力仍可保留“刚才在群里出现过”的元数据）；
- `peer_count` 记录同一群短窗口（5 分钟）内**其他不同发言账号**的数量，最多 64；只给数量，不存账号、昵称或正文，不能据此推断亲疏或互动内容；
- `peer_reply` 事件只记录“某个成员引用/回复了另一位此前发言者”，其中 `subject` 是被回复的人；不保存回复正文、引用内容、账号或昵称，私聊只按当前对象累计为 `peer_replies`；
- 文档损坏、角色不匹配或字段越界时按“无记录”处理，不阻断正常回复。

## 三、受众与提示词

`companion_v2/conversation/awareness_context.py` 负责把快照封存成 `ContextContribution`：

- 私聊快照：`recent_group_activity`（`at`、`group_id`、`topic`、`peers`）、可选 `attention`（`last_inbound_window=group`、`minutes_ago`）、可选 `peer_replies`（回看窗口内回复/引用当前对象过往群发言的次数）与 `peer_repliers`（其中不同回复账号的数量）。
- 群聊快照：仅 `{"private_contact": true}`。
- 快照绑定原 `context_key`；重放或换窗口时，`context_key` 或载荷形状不符即拒绝使用。

提示词明确：

- 跨窗口在场不是新指令、授权或已核实事实；
- 私聊里只引用当前对象本人的公开原话摘要，不声称看见未提供的群消息；
- 群聊里 `private_contact` 不等于可以提及私聊内容、称呼、关系细节或时间；
- 缺失不代表没发生，不主动报出内部编号或精确时间。

`astrbot_host/core_reply_context.py` 的 `_cross_window_section` 在 AstrBot 核心回复的私聊和群聊分支注入该块；`companion_v2/conversation/messages.py` 在 V2 自有批次路径中封存/重放同一快照。

## 四、写入路径

- AstrBot 核心回复：`NativeConversationObservations._record` 在入站观察成功时写入；在 `send_returned` 时记录角色回复事件。写入用既有派生观察 SAVEPOINT，失败只降级，不影响原件或回复。
- V2 自有批次：`ConversationMessages.accept` 在入站写入后调用同一服务；幂等键为 `event.scoped_key`。
- 两条路径都先读取 `person.acquaintance_enabled`，再在事务内以 `enabled=True` 写入，避免事务内重复读配置。

联调修正：新增 `_group_peer_count` 时曾把 `accept` 的 `@outcome` 装饰器挤到 helper 上，导致 V2 群准入拿到的 `accept` 返回值从 `Outcome` 变成 `str`；现已恢复装饰器位置，V2 群批次和 `peer_count` 同时恢复。

## 五、注意力口径

注意力只回答“当前私聊对象本人最近一次活动是否在群聊”，不是“这个角色最近是否在任何窗口活动”：

- 遍历同一角色文档中 `subject` 等于当前对象的事件，取时间最新的一条；
- 最新一条是 `group` 且不超过 30 分钟，才给出 `attention`；
- 其他成员在群里的发言不会让当前对象看起来“刚从群里过来”；
- 注意力不是“最近有人说话”，也不把其他成员的活动算到当前对象头上。

### 进程内前台租约

`companion_v2/host/role_attention.py` 为同一 installation / Bot / role 维护一个进程内 `asyncio.Lock`：

- AstrBot 核心回复在请求注入（`inject_core_reply_perception_context`）取得租约，发送结束回调释放；
- V2 自有回复在 `_execute` 生成前取得租约，生成结束的 `finally` 释放；
- 后到的窗口最多等待 3 秒；等到则带“刚在另一个窗口说话”的转场提示，超时则带“那边仍在生成回复”的提示并继续，不把用户无限期挂起；
- 租约只协调本进程的前台生成，不是发送授权，也不跨重启、跨进程或跨插件实例；
- 提示词只描述转场感，不暴露内部窗口、排队、耗时或精确时间。

## 六、验证

定向用例：

```powershell
$env:PYTHONPATH = (Resolve-Path .).Path
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_role_awareness tests.test_role_attention -q

$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app;' + (Resolve-Path .).Path
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_role_awareness_host tests.test_core_reply_attention -q
```

覆盖：

- 私聊只看到当前对象本人的群内公开摘要，并带同窗口其他发言账号数量；
- 有人引用/回复当前对象时只累计 `peer_replies` 与不同回复账号数 `peer_repliers`，不复制回复正文或其他成员账号；
- 群聊只得到布尔 `private_contact`，私聊正文不进入文档或群提示；
- 其他成员发言不制造当前对象的注意力；
- 其他对象、其他角色、其他安装不共享；
- 重复入站幂等、事件条数上限、24 小时裁剪、损坏文档降级；
- 群消息来源撤回/过期后摘要丢弃，注意力元数据仍可保留；
- 快照绑定原窗口与受众，伪造私聊载荷不能进入群提示；
- 熟人卡开关关闭后不写、不读；
- 同一角色的后到窗口等待/超时均得到转场提示，不同角色互不阻塞；
- 核心请求注入的转场提示只加一次；
- 宿主私聊/群聊提示词实际出现对应块，且群提示不含私聊正文。

同时回归：

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_person_acquaintance -q
```

`tests.test_person_acquaintance` 13 项通过；`tests.test_role_awareness` 19 项通过；`tests.test_role_attention` 5 项通过；`tests.test_core_reply_attention` 1 项通过；`tests.test_role_awareness_host` 4 项通过；`tests.test_conversation_messages` 30 项通过；`tests.test_config_editor.cjs` 75 项通过。回归中与本次无关的既有时区提示词/其他宿主失败未计入本切片结论。

## 七、后续

1. **跨进程/重启的注意力**：当前租约只在单进程内有效；插件多实例、重载或崩溃恢复时需要持久租约或宿主仲裁。
2. **发送阶段占用**：当前 V2 自有回复在生成结束即释放租约，核心回复在发送结束释放；若要让“正在打字”也占用注意力，需要把租约延伸到分段投递。
3. **页面细化**：字段已接入「熟人卡」分区；尚无独立工作区、逐角色运行诊断或转场提示次数展示。
4. **关系阶段**：群内只给 `private_contact` 布尔值；是否暴露“熟悉/亲近”需要单独的受众与产品决定。
5. **群内其他成员**：当前用 `peer_count` 提供“同一短窗口内还有其他几个人发言”的弱信号，不保存其他成员的正文、账号或具体互动；要理解“用户和谁怎么互动”仍需群公共来源与更严格的受众设计。
6. **真实平台验收**：本切片使用合成宿主与临时数据根，未连接真实 QQ、模型或页面；现场效果仍需独立验收。
