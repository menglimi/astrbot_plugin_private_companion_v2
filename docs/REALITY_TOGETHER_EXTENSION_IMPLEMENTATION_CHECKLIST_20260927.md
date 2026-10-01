# Reality / Together 拓展细化实施清单

2026-09-27。本文是[Reality / Together 拓展实现思路](REALITY_TOGETHER_EXTENSION_IMPLEMENTATION_PLAN_20260927.md)（下称"思路稿"）的**可执行细化**：逐条对账真实源码、把切片拆成带文件与判据的步骤、给出测试项与命令。范围按用户口径为**两个提供方 + V2 本体宿主接线**。

本轮仍**只出清单**：未改任何运行代码、未连宿主、未调模型/设备/房间服务器、未构建交付包、未跑测试。所有对账结论均注明 `file:line`，并采用**字节级行号**（`(Get-Content).Count` 在本机沙箱下会少报，`main.py` 实测 5845 行）。

设计稿仍为权威依据：[S6 第一波联合交接与验收](../../astrbot_plugin_private_companion/docs/S6_REALITY_TOGETHER_JOINT_ACCEPTANCE_V0.md)（§3 最小配套格式、§6 夹具 W1-F01--18、§8.1 包顺序）、[Together 会话、媒体与插话](../../astrbot_plugin_private_companion/docs/TOGETHER_SESSION_MEDIA_AND_INTERRUPTION_V0.md)（TGX-01--24）、[Reality 核心互动](../../astrbot_plugin_private_companion/docs/REALITY_INTERACTION_AND_RECEIPTS_V0.md)（RIX-01--20）、[Reality 信息视图](../../astrbot_plugin_private_companion/docs/REALITY_INFORMATION_VIEW_AND_QUERY_V0.md)、[Reality 摄像头与音响](../../astrbot_plugin_private_companion/docs/REALITY_CAMERA_SPEAKER_AGENCY_V0.md)。

## 0. 对账结论：思路稿哪几句已经过期

思路稿写于同一日，但两个提供方的工作树已经比它描述的更进一步。**必须先按本节修正，否则清单会重复做已经存在的东西。**

| 思路稿原话 | 源码事实 | 处置 |
| --- | --- | --- |
| "只有 `reality.device.control`（`alias`+`is_on`）单动作，无查询/取消入口" | Reality `native_v2/provider.py:26` 的 `_ACTIONS` 为**四个**动作：`reality.snapshot.read` / `device.list` / `device.status` / `device.control`；`provider.py:381-395` 的 `lookup()` **已完整实现**（含跨重启回执恢复与身份复核 `:377-379,394`），宿主测试 `tests/test_reality_together_native.py:155,188,195,208,279,348` 已在调用它。**它只是不在 manifest 里**——`execute()` 由 `astrbot_host/native_extensions/__init__.py:197` 调用，而 `discovery.py:54` 只要求 `port.execute`，所以 `lookup` 进不了模型工具目录 | RI-1 要补的**不是 lookup 能力，而是把已存在的 lookup 接进 manifest/工具目录**，并扩到多动作。工作量比思路稿估计的小 |
| "Together 停在建房/查房/关房"（含"无成员/邀请/覆盖"） | 三个动作的语义比"最小"更厚：`snapshot` 返回 `{scope_key, rooms[], active_count}` 且**同时扫描 `plugin.rooms` 与 `detached_rooms`**（`provider.py:350-369,354`）；`close` 有 journal 派生的两级解析（`provider.py:446-480`）；房间层还已有 `create_invite`（`main.py:2704-2715`，继承 `room.mode` 与 `asdict(room.native_v2)`，但**复用 `room.user_id`、非成员模型**） | TG-1/2/3 的缺口是真缺口，但**不能按"从零"估工**；成员/端点/覆盖/接管确实 `grep` 零命中 |
| "`RoomTicket` 只有 `token/mode/user_id/native_v2`" | `models.py:36-46` 还有 `created_at`、`expires_at` 与 `expired` 属性；TTL 由 `server.ticket_ttl_minutes`（默认 10，`_conf_schema.json:39-42`）驱动，`main.py:301-302` 折算为 600 秒 | TG-1 只需**加字段**，不改 TTL 机制 |
| "`media_state` 记播放器状态；无逐端点覆盖" | 后半句成立（全仓 `endpoint` 仅命中构建脚本忽略项）；但前半句低估了：`media_state` 仅 6 个字段（`main.py:4825-4847`），另有 `watch_events`（140 条环形、带 `seq`，`models.py:107-108,222-233`）、`watch_epoch`、`last_watch_spoken_media_time`、`watch_memory_cursor/media_time`、`novel_progress_sequence`、`_subtitle_context`（`main.py:4863-4880`）等标量游标 | TG-2 是"把标量升成区间账"，不是"从无到有" |
| "Reality 的只读回执现在不带 operation_id" | 成立（`provider.py:299,305`）；与宿主合同一致：`companion_v2/capabilities/native.py:154-157` 要求 `side_effect=none` 时 `operation_id` 必须为 `None`。**写路径没有复用只读分支**（`read_only` 由请求 action 计算，`device.control ∉ _READ_ACTIONS`）。副作用：`lookup` 一个只读动作时也回 `operation_id: None`，该 id 只能从 `receipt_ref` 里取 | 加写动作时保持这个由 action 派生的判定，不要加"按 state 猜"的分支 |
| "无库、无历史"（Reality） | **半错**：确实无**领域历史表**（无位置/设备/事件表），但已有**两个带 DDL 的 SQLite**：`snapshot_dependencies.db`（`snapshot_dependencies.py:18-23`，构造时无条件创建，`mobile_snapshot_owner.py:84-86` ← `mobile_gateway.py:127-129` ← `main.py:439`，当前在盘 20480 B）与 `role_snapshot_sources.db`（`role_snapshot_sources.py:37-44`，按需）；`reality_companion.json` 还保留**有界历史**：`users[*].reality_touch_camera_policy.audit` = 最近 20 次观察（`reality_touch_camera.py:889-893`）。**无 Repository、无 schema 迁移机制** | RV-2 仍是真缺口（缺的是领域历史与游标），但要按"既有 DDL 风格 + 独立库"来加，不是从零建存储层 |
| 缺陷 B8"目录多返回两个未声明字段" | **少算一个**：`extension_device_directory` 实际返回 4 个键（`mihome_web_api.py:496-498`）：`devices`、`more_devices`、`cache_updated_at`、`logged_in`——后三个均未声明。且 manifest **任何 tool 都没有声明 output schema**（只声明 `parameters`） | 见 §3，B8 的修法要连 `more_devices` 一起纳入声明 |

**另外两条对账新发现（思路稿未提，但影响 S1 做法）**：

- **`execute()` 有一个无回执的窗口**：`dispatching` 写入在 `provider.py:359`，位于 preflight try（`:345-356`）与 dispatch try（`:360-374`）**之间且都在外面**。该写入失败会**不带回执**地逃出 `execute()`；进程若死在 `:359` 与 `:361` 之间，行会永久停在 `dispatching`，之后 `lookup` 只能看到 `state:"unknown"/effect:"unknown"`（`:295-297,304`），与真实的派发后失败**只差 `error` 字段**。S1 的 `dispatched_at` 改造必须同时把这个窗口收进 try。
- **`confirmed` 是云端 code-0 回执，不是设备状态回读**：`mihome_client.py:444-471` 的 `_validate_action_response` 只在"看到 int `code` 且全为 0"时给 `True`，`code==1` 给 `False`，其它非零码直接 `raise MiHomeControlError("cloud_rejected:{code}")`。这条影响 E12 的口径，S1 的判据 J1-4 应按"云端确认层"表述，不要写成"设备已执行"。

**一句话**：两个提供方都已具备**单动作 + 只读 + 幂等账本 + 宿主合同**的完整地基，其中 Reality 的 lookup 账本**已经写好**只是没暴露；缺的是**动作面宽度、身份/成员模型、区间账与领域历史**。这决定了 §3 的步骤都是"在同一套既有骨架上加"，不是新建框架。

## 1. 范围、前置与硬约束

### 1.1 写入范围

实现涉及**三个工作树**：本仓库（`astrbot_plugin_private_companion_v2`）+ 两个提供方（`astrbot_plugin_reality_companion`、`astrbot_plugin_together_companion`）。后两者在本会话工作区之外，需要更宽的文件权限；本次已确认可写（探针文件已清理）。**改动只落在提供方与本体适配层，不新建第四个插件、不新增公开 Dashboard 页。**

### 1.2 不可协商的硬约束（违反即返工）

1. **权威在提供方**：设备确认层、邀请阶段、播放覆盖由提供方裁决，V2 只引用与采用，不重算（[对照表](COMPANION_PROVIDER_STATUS_20260927.md) §三.4）。
2. **查询不等于采集**：`operation.lookup` 类只读入口不得触发设备重试、不得暗中转成相机采集。
3. **派发后不回退**：`prepared → dispatching → succeeded|failed|unknown` 中，`dispatching` 之后任何异常落 `unknown + effect=unknown`，且**不自动重试**（Reality `provider.py:357-375`、Together `provider.py:433-443` 已是此形状）。
4. **撤权落在派发之前**：`before_dispatch` 必须在 try 之外先行判定，拒绝落 `failed/not_committed` 且**不新建操作行**。参照 Reality/Together 现有写法，**不要照抄 Screen**（`astrbot_plugin_screen_companion/native_v2/provider.py:158-175` 把 `before_dispatch()` 放在 try 内，拒权被记成 `unknown`，即缺陷 B0b）。
5. **合同八字段**：adopted 结果必须保留原 `invocation/binding/state/effect/operation_id/receipt_ref`；只读动作 `operation_id` 必须为 `None`（`companion_v2/capabilities/native.py:154-157`、`astrbot_host/native_extensions/__init__.py:248-262`）。
6. **不读 V1 数据**：不得读取、迁移或修改 V1 用户数据。
7. **文本约定**：UTF-8 无 BOM、LF、末尾换行。

### 1.3 必须先决策的一个规模问题

`astrbot_host/native_extensions/discovery.py:113-115`：聚合后条目数 `> MAX_TOOL_CATALOG`（=64，`companion_v2/model_gateway/models.py:17`）时**清空全部原生声明**。

按当前实测动作数（Game 22 + Content 6 + Image 2 + Reality 4 + Together 3 + Screen 1 + Live 2 = **40**），Reality 到 ~8、Together 到 ~8 后为 **49**，仍有余量。但这是**全有或全无**的悬崖：

- **动工前**：用 §9.4 的 `Select-String` 命令核对七家当前真实动作总数，并留 ≥10 条余量给并行推进的其他会话。
- **本清单的默认取值**：Reality 4 → **7**（+`device.action`、`operation.lookup`、`operation.cancel`），Together 3 → **7**（+`room.member.list`、`room.invitation.create`、`room.join`、`room.media.coverage`）。合计 **47**。
- **不采用的替代方案**：把 lookup/cancel 做成宿主内部调用（非模型可见）。理由是设计稿 §3 要求 `submit/lookup/cancel 分离` 且**原结果查询是本方能力**，藏进宿主会让"这次到底有没有执行"无法被原模型接续。若余量不足，**优先砍 `room.media.coverage` 为 snapshot 内嵌字段**，而不是砍 lookup/cancel。

## 2. 步骤总表

| 序号 | 切片 | 提供方改动 | 本体改动 | 依赖 | 退出证据（设计稿 §8.1） |
| --- | --- | --- | --- | --- | --- |
| S1 | Reality RI-1 动作面与操作账 | `native_v2/provider.py`、`mihome_web_api.py` | 无代码（合同测试） | 无 | 原请求可定位；授权重验、未知结果与取消竞争可核对 |
| S2 | Reality RV-1 信息视图格式 | `mobile_gateway.py`、`native_v2/provider.py` | 无代码 | 可与 S1 并行 | 无历史/无法读取时**如实降级** |
| S3 | Together TG-1 会话/成员/身份 | `models.py`、`main.py`、`server.py`、`native_v2/provider.py` | `astrbot_host/native_extensions/__init__.py` | 无 | 同一身份/会话可核对；**旧票据不冒名** |
| S4 | Together TG-3 轮次/语音/插话账 | `models.py`、`main.py`、`web/app.js`、`native_v2/provider.py` | 无代码 | S3（成员/端点身份） | 中断不混入旧片段；已确认部分不自动重播 |
| S5 | Reality RI-3 + Together TG-2 邀请/回拨与媒体覆盖 | `mobile_gateway.py`、`models.py`、`main.py`、`native_v2/provider.py` | 页面（§6） | S1、S3 | 真实连接逐步取证；覆盖不填洞 |
| S6 | RV-2 / RI-2 / TG-4 历史·自主观察·重启 | 三家均需领域 Repository | 消费链接线 | 真实依赖齐备 | 非空完整重启；资源未就绪不报 active |

**依赖图**：`S1 → S5`、`S3 → S4 → S5`、`S2` 独立、`S6` 最后。S1 与 S2 可并行；S3 与 S1 可并行但 S3 风险最高，建议**先合 S3 的身份拒绝路径**再往下走。

## 3. S1｜Reality RI-1：把"一个开关"扩成可查询的操作账

### 3.1 文件与改动点

| 文件 | 改动 | 依据 |
| --- | --- | --- |
| `native_v2/provider.py:26` | `_ACTIONS` 增 `reality.device.action`、`reality.operation.lookup`、`reality.operation.cancel` | 动作面扩展 |
| `native_v2/provider.py:27` | `_READ_ACTIONS` 增 `reality.operation.lookup`（**必须**，否则 `parse_result` 会因 `side_effect=none` 却带 `operation_id` 而拒绝，见 `native.py:154-157`） | 只读回执合同 |
| `native_v2/provider.py:238-258` | `manifest()["tools"]` 增三条：`parameters` 为**闭合 JSON Schema**（`additionalProperties: false`，现有四条都这么写），只读用 `side_effect: "none"`，设备动作用 `"external_network"`。**并把 `package.capabilities`（`:237`）同步加新 action**，否则 `parse_manifest` 报 `native tool exceeds its package`（`native.py:83-84`） | 宿主按声明建目录 |
| `native_v2/provider.py:281-291` | `_request()` 参数校验分支：`device.action` 需 `alias` + `action`(枚举) + 参数对象；`lookup` 沿用 `operation_id`；`cancel` 需 `operation_id` + 期望修订 | 校验在提供方 |
| `native_v2/provider.py:345-375` | 抽成按动作派生的单一路径（见 3.2），并把 `:359` 的 `dispatching` 写入**收进 try** | 消除无回执窗口 |
| `native_v2/provider.py:193-202` | `OperationStore.update()` 增 `dispatched_at`；`update()` 目前**不校验** state/effect 取值（`:193-202` 接受任意字符串，无 Enum/CHECK），扩多动作时至少加一层断言 | 见 3.2 |
| `native_v2/provider.py:381-395` | `lookup()` 现有实现**读取请求顶层的 `operation_id`**（`:385` `value.get("operation_id")`），不是 `arguments` 里的键；`_operation_identity`（`:95-101`）**不含** `operation_id`。暴露成 action 时要按这个既有形状接线，不要改成 arguments | 与宿主 artifact 请求同形（`native_extensions/__init__.py:209`） |
| `mihome_web_api.py:455-467` | `extension_control_preflight` 现在**直接返回 DID** 且以 `WebAPIError` 抛错（409 无映射 / 404 未知别名 / 403 未启用或不在白名单 / 403 native+admin_only）。扩为**目标描述**（类别 + 场所 + `binding_revision`）时注意：DID 是本插件对外承诺**不下发**的字段，目标描述用于修订核验、**不进入模型可见结果** | 绑定与覆盖可核对 |
| `mihome_web_api.py:469-472` | `extension_control_power` 返回**恰好三个键** `{alias, is_on, confirmed}`，且**自己会再跑一次 preflight**（`:470`）。新增 `extension_device_action(alias, action, params, *, native=False)` 时保持"自己再验一次"的既有形状 | 复验修订 |
| `mihome_web_api.py:474-498` | 目录返回补声明：`more_devices`、`cache_updated_at`、`logged_in` **三个**键当前都未声明（`devices` 行另有 `alias/category/cached_online/control_allowlisted/control_requires_admin`，上限 100）；`logged_in` 与 `cache_updated_at` 建议**移除**而非补声明（缺陷 B8，`logged_in` 会被读作声明中排除的登录信息） | 声明与返回一致 |

### 3.2 三态迁移的具体形状（最容易做错的一处）

思路稿 §3.1 指出"`dispatched` 用 `store.get(...)["state"] == "dispatching"` 判定"是隐患。核实：**两个提供方今天都用这个判定**（Together `provider.py:441`；Reality 的控制分支靠"`dispatching` 之后同一段 `except`"隐式表达）。

Reality 现状的确切顺序（`provider.py:310-375`）：

```text
:312  await _checked(before_dispatch)        # 最外层，before store.begin
:314  operation, fresh = store.begin(...)    # 幂等；非 fresh 直接回放（:315-316）
:317-344  只读分支（内含 :337 二次 before_dispatch）
:345-356  preflight try：:346 before_dispatch → :352 preflight(...)
          → 失败落 failed/not_committed（:355），不派发
:359  store.update(state="dispatching", effect="unknown")   # ← 在两个 try 之外
:360-374  dispatch try：:361 外部调用 → confirmed 判定（:362-365）
          → succeeded/committed（:366）；CancelledError → unknown（:369）并 re-raise（:371）
          → 其它异常 → unknown/unknown（:374）
```

目标形状：

```text
1) await _checked(before_dispatch)           # 拒权 → failed/not_committed，不建行（现状已如此）
2) operation, fresh = store.begin(...)       # 幂等：同 invocation 直接回放
3) preflight(...) 失败 → failed/not_committed（不派发）
4) store.update(state="dispatching", effect="unknown", dispatched_at=now)   # 显式时间戳
5) 外部调用；confirmed is True → succeeded/committed
6) 任何异常/CancelledError → unknown/unknown，**不重试**
```

两处必须一并修：

- **把第 4 步收进 try**。现在 `:359` 裸在外面，写入失败会不带回执地逃出 `execute()`。
- **`dispatched_at` 替代 state 判定**。取消与查询判"是否已越过分派边界"时读它，而不是读 `state`——否则在 `dispatching` 窗口内会读到中间态并做出错误裁决。取消只对 **已 `prepared`、`dispatched_at is None`** 的操作成立；已越界的一律回 `unknown/unknown` 并保留原 operation。

**为什么不能照抄 Screen**：`astrbot_plugin_screen_companion/native_v2/provider.py:158-175` 把 `before_dispatch()` 放在 try 内（`:159`），于是拒权被 `except Exception` 捕获成 `return self._result(request, "unknown")`（`:175`）——即缺陷 B0b。Reality/Together 现有写法（Reality `:345-356`、Together `provider.py:389-393`）都是**先把权限判定做完再进派发 try**，扩动作时保持这个结构。

### 3.3 绑定与换绑

- 领域记录增 `target`（`alias` + 类别 + 场所）与 `binding_revision`。
- 投递前用 `preflight` **复验修订未变**；不一致即拒，不沿用旧 DID。
- **换绑必须让旧引用失效**：旧的 `operation_id`/`binding` 引用在换绑后查回时返回明确的"绑定已变更"，而不是静默映射到新设备。
- Reality 侧没有 `NativeRoomBinding` 这样现成的领域记录类（它是 Together 的），需在 Reality 内新建一个轻量 dataclass，**归属 Reality 领域**，不要复用 Together 的类型。

### 3.4 判据（逐条可验）

| # | 判据 | 观测点 |
| --- | --- | --- |
| J1-1 | 同一 operation 可被 `lookup` 读回，且**两次读回一致** | 重启 provider 后再 `lookup` 得同一结果 |
| J1-2 | 撤权后立即拒绝，且**不新建操作行** | 拒权回执 `failed/not_committed`，`latest()` 行数不变 |
| J1-3 | 未知结果保留原 operation 且**不重试** | 外部调用抛错后 `effect=unknown`，同 invocation 重放命中账本、外部调用次数不增 |
| J1-4 | 只有米家 `confirmed: true` 才 `committed` | `confirmed=False` 落 `unknown/unknown` |
| J1-5 | 取消只对未派发成立 | 派发后 cancel → `unknown`；派发前 cancel → 阻止派发且外部调用为 0 |
| J1-6 | 换绑后旧引用失效 | 换绑前签发的 `operation_id` 查回为"绑定已变更" |
| J1-7 | 只读回执不带 `operation_id` | `lookup` 回执 `operation_id is None`，`parse_result` 通过 |
| J1-8 | 目录不再返回未声明字段 | 目录键集合 ⊆ 声明 |

## 4. S2｜Reality RV-1：信息视图格式与诚实降级

### 4.1 现状的确切形状

`mobile_gateway.py:587-628` 的 `mobile_context()` 顶层为：

```text
{ available, user_id, location, device, activity, telemetry, privacy }
```

`available` **只表示位置可用**（`:604` `bool(snapshot.get("available"))`，`snapshot` 来自 `_mobile_location_snapshot`）。各来源**各自**带自己的 `available`/`reason`（`:591,596,601,632,638,643,715,730,756,762,767`），但**顶层没有把它们聚合**，于是"没有位置"会被读成"什么都没有"。

### 4.2 改造形状

| 项 | 现状 | 目标 |
| --- | --- | --- |
| 顶层 `available` | 只表示位置 | 改为**聚合**语义（任一来源可用即 true），并逐来源给可用性枚举 |
| 来源目录 | 无 | 逐来源声明身份、修订、可读能力、可用性 ∈ `available` / `unknown` / `unsupported` / `unauthorized`；覆盖位置、设备（米家）、手机活动摘要、遥测指标、屏幕共享状态、摄像头、音响 |
| 请求范围 | 无 | 时间窗、来源筛选、限额 |
| 实际采集范围 | 无 | 各来源真正返回了什么 |
| 查询枚举范围 | 无 | 翻页实际枚举到哪里 |
| 返回材料范围 | 无（模型直接拿整份快照） | 最终交给模型的材料清单 |
| `captured_at` / `received_at` | **已在内存里分开存**（location `:1549-1550`、device `:1631-1632`、activity `:1695-1696`、telemetry `:1932-1933`），但**暴露不一致**：location 只回 `captured_at`+`age_seconds`（`:582-583`，`received_at` 仅内部用于保留期 `:534-537`）；device/activity 回 `captured_at`+`last_report_at`(=`received_at`)（`:747`、`:654`）；只有 telemetry 同时回两者（`:885-886`） | 统一为结构化的 `captured_at`/`received_at` 对；**心跳只更新 `received_at`**，不更新 `captured_at`（存储已对，缺的是投影口径统一） |
| 健康类累计值 | 无窗口/单位 | 必须带统计窗口与单位，且**不允许把多个窗口相加** |
| `history` 能力 | 无声明；底层**只有最新值**（每用户每类覆盖写：`:1557`、`:1639`、`:1704`；遥测按测量类型合并、事件去重上限 `MOBILE_TELEMETRY_MAX_EVENTS = 24`，`:50,1894-1940`；过期即删 `:388-447`），且 `mobile_gateway.py` **全文件不落盘**（无 `data_dir`/写文件/sqlite） | 显式 `unsupported`（RV-2 未做前的诚实降级） |
| 分页游标 | 无 | 游标**绑来源修订**；revision 变化或撤权时旧游标**显式失效**，不能让旧页凑成一次完整查询（夹具 W1-F02） |
| `app_id` 泄漏面 | `activity` 的 `app_id` 仅在 `prompt_safe=False` 时加入（`:665`），而 `mobile_context` 恒传 `prompt_safe=True`（`:609`），故当前不下发 | 拆格式时**保持这条**，别在新路径里漏出去 |

**形态要求**：来源目录、概览、query/read 是**三个独立输入/结果格式**，不是把 `mobile_context` 整份塞给模型（思路稿 §3.2）。

### 4.3 判据

| # | 判据 | 观测点 |
| --- | --- | --- |
| J2-1 | 无位置但有活动时，顶层 `available` 为 true 且 `location.available` 为 false | 不再"一票否决" |
| J2-2 | 心跳到达后 `received_at` 前进、`captured_at` 不动 | 夹具 W1-F01 |
| J2-3 | 两个样本之间有离线缺口时，覆盖保留缺口 | 不称"持续停留" |
| J2-4 | 两个不同统计窗口的累计值不相加 | 材料里窗口与单位齐备 |
| J2-5 | 来源 revision 变化后旧游标被显式拒绝 | 夹具 W1-F02 |
| J2-6 | `history` 报告 `unsupported` 而非空数组 | 无历史如实返回 |

## 5. S3｜Together TG-1：身份、成员与同房（风险最高）

### 5.1 必须先修的身份安全问题

**问题**：无身份时回退主用户，且**两处都回退**：

- `main.py:1257`（签发）：`resolved_user = _single_line(user_id, 80) or self._resolve_primary_user_id()`
- `main.py:1929`（开房）：`user_id=ticket.user_id or self._resolve_primary_user_id()`

`_resolve_primary_user_id()`（`main.py:1267-1283`）先读本地配置 `conversation.primary_user_id`，再**借道 V1** 的 `resolve_historical_chat_identities` 拿主用户。

**后果**：任何持票者在无身份时可能被判成一个**并非自己**的主体；`server.py:489-513` 全程不校验身份（`get()` 验票 → `prepare()` → `consume()` → `open_room()`），所以"缺身份"不会被拒绝，只会被冒名顶替。

**修法**（TG-1 第 1 步，先于其他任何 TG 工作）：

1. `open_room` 去掉回退：缺身份即拒绝。
2. **签发侧（`main.py:1257`）同样不能回退给原生票据**。注意 `self.primary_user_id` 可能为空，而 `_resolve_primary_user_id()` 兜底会去调 V1 插件 API——即"回退"本身可能返回空串，此时 `room.user_id == ""`（`main.py:1939` 的日志分支 `room.user_id or "未指定"` 就承认了这点）。**空身份进会话必须变成拒绝**，而不是"空着继续"。
3. 错误码明确化，例如 `together_ticket_identity_required`；`server.py` 侧映射为**拒绝连接的关闭码**（现有可用码：`server.py:505`、`:511` 的 `1008`，另 `:484` 的 `403`、`:492` 的 `401`）。
4. 旧票据**兼容读字段**，但不再享受回退；`native_v2` 票据本就必定带身份（`provider.py:406-407` 传 `_text` 校验过的 `user_id`，`_text` 拒绝空串，`provider.py:47-50`），故 V2 路径不受影响。
5. 保留 `_resolve_primary_user_id()` 给**非身份用途**（如 `novel_import_allowed`，`main.py:1261-1265`），但不得再作为会话身份来源。

### 5.2 票据 → 邀请实体

`RoomTicket`（`models.py:36-46`）扩为邀请记录，加：`invitation_id`、`inviter`、`target_subject`、`requested_media[]`、`revision`。

`NativeRoomBinding`（`models.py:20-32`）**不动**——它已经是"每成员一份身份+授权+可见范围"的现成形状，新增 `members` 结构时按成员各持一份。

一次性消费语义保留（`models.py:76-82`），但**同房加入必须能引用既有 Session**（见 5.3）。

### 5.3 `open_room` 的两条路径

现状 `main.py:1921-1934`：**永远新建** `room_id=uuid.uuid4().hex`，只 `self.rooms[room_id] = room`，无"查既有房间"分支。

改为：

- **加入既有 Session**：按 `participants_ref` 校验身份与授权，挂到既有 `RoomSession`。
- **新建 Session**：维持现状路径。

**关键约束**：票据不能让新成员继承主用户的私有上下文。历史可见范围**单独给**，不共享 `room.history`（夹具 W1-F07/W1-F08）。

**连带风险（必须一起处理）**：现状下若客户端持**票据**连接而该票据对应房间已 `detached`，`resuming` 为 False（`server.py:488-489`），于是**新建第二个 `RoomSession`**，而 detached 那个仍占着 `detached_rooms` 直到宽限期结束——同一票据产生两个房。加"加入既有"路径时必须一并消除这个分叉。

### 5.4 端点与权限分离

设计稿反复强调的**成员管理权、媒体控制权、运行接管权是三种权**，不是一种。

落点：`RoomSession` 目前只有**一个** `websocket`（`models.py:100`）和**单通道**状态（`call_camera_frame`，`models.py:135`），且没有 endpoint 概念。需把单通道状态改为**按端点分桶**，并让三种权分别核验。

### 5.5 判据

| # | 判据 | 观测点 |
| --- | --- | --- |
| J3-1 | 缺身份即拒绝，不回退主用户 | 夹具 W1-F07；返回明确错误码，不产生会话 |
| J3-2 | 票据重放不建第二成员、不建第二房 | 同票据二次连接不产生新 `RoomSession` |
| J3-3 | 拒绝该邀请**不结束**原 Session | 其他成员继续 |
| J3-4 | 新成员看不到主用户私事 | 夹具 W1-F08；`history` 按成员范围投影 |
| J3-5 | 三种权分别授权 | 有媒体控制权 ≠ 有接管权 |
| J3-6 | 旧票据兼容读且不再回退 | 旧格式票据仍可解析，缺身份仍被拒 |

## 6. S4/S5/S6：其余切片要点与判据

### 6.1 S4｜TG-3 轮次、语音与插话

现状已有：生成取消（`models.py:169-174`，`Task.cancel()`）、停音频（`main.py:2823-2828,2846` → 客户端 `web/app.js:2320-2336`）、浏览器朗读回退（`main.py:5448-5459` 与异常分支 `5642-5653` → `web/app.js:2287-2318`）。

**缺的是"实际已播范围"的账**（`played_range|watched_range|playback_ledger` 全树 0 命中），且客户端**从不回报**渲染了多少（`handle_room_payload` 的入站类型里没有播放覆盖上报）。

| 项 | 做法 |
| --- | --- |
| 输出记账 | 按 S5 的 `unit/part/载荷版本` 记录 |
| 范围映射 | **文本范围与音频范围分别映射**；文字完整显示 ≠ 完整播完 |
| 声音让出 | 可先发生；是否附和/纠正由原模型理解；**已明确的停止不等模型** |
| 换代隔离 | 旧模型/TTS 块晚到只结算原操作的合法结果与费用，**不加入新轮次** |
| fallback | 接**原输出身份**，不生成第二份回答；无法证明是否播出时停机自动重播、按未知接续（夹具 W1-F13） |

### 6.2 S5｜TG-2 媒体覆盖

`media_state` 当前只有 6 个字段（`main.py:4825-4847`）：`title`、`source`、`current_time`、`duration`、`paused`、`playback_rate`。

扩为：`{source_version, control_revision, per_endpoint: {endpoint_id: [(start,end)]}}`。

- 换源/跳转产生**新的控制修订**，旧进度晚到**不得写入新版本**。
- **覆盖不填洞**：不取最大位置当所有人已看（夹具 W1-F10）。
- 缺字幕/音轨/正文时**如实降级**，不能从标题或另一人的进度补齐内容。

### 6.3 S5｜RI-3 邀请与回拨

Reality 侧 `grep` `invitation|invite|ringing|振铃|来电|拒接|回拨`：**零命中**——完全空白。`mobile_create_room`（`mobile_gateway.py:1157`）返回的是房间链接，"开房链接不等于接通"。

最小形态是**邀请实体 + 期限 + 领域阶段**，不新建联合状态机：

```text
Invitation {
  invitation_id, revision, direction(inbound|outbound), purpose_ref,
  requester(已鉴别主体), target, requested_media[], expires_at,
  stage(ringing | accepted | rejected | revoked | expired),
  session_ref?, operation_ref?
}
```

四条要点（思路稿 §3.3，与夹具一一对应）：

1. **不按消息次数计意愿**——域内只记真实阶段，是否改口归原模型。
2. **拒接 `succeeded` ≠ 解释已发出**——两条独立账（W1-F05）。
3. **接受与取消/到期在同一修订上竞争**——owner 只提交合法裁决；迟到决定不作用于新邀请（W1-F03）。
4. **回拨是新的联系**——新 operation/key 关联原 purpose，先查原账再拨，未知不重拨（W1-F06）。

**owner 归属**：邀请 owner 放 **Reality**（它持有移动网关与用户身份），Together 只接收"合法加入"，避免两家各存一份邀请表。

### 6.4 S6｜必须留到最后的三个包

| 包 | 为什么最后 |
| --- | --- |
| RV-2 历史与 Repository | 需要**独立 DDL/迁移**，不改已固定 SQL；不能从旧内存缓存反推过去 |
| RI-2 自主观察与独立音响 | 依赖真实设备与授权；且要**替换 V1 的"陪伴档位门槛 + 未回应计数"**（`main.py:542-543` 的 `proactive_min_tier` 默认 4、`reality_touch_camera.py:373-374,418-424` 的档位门槛），并让旧 `_mirror_reality_touch_proactive_voice`（`reality_touch_audio.py:413`）镜像路径退出 |
| TG-4 重启与结束 | 需要领域 Repository + 控制代 CAS；现状 `resume_token` 是**普通 uuid 且跨次恢复复用**，无修订、无 CAS（`main.py:1933,1978-1988`） |

RI-2 两条硬边界：**音响是独立通道，不是聊天语音的镜像**；**"可能已经播放"不能当作可随意重播**。并沿用有效授权，**不为"迁移"强迫重新授权**。

## 7. 本体宿主接线

好消息：**宿主侧几乎不需要为新动作写代码**。

| 接线点 | 现状 | 需要做什么 |
| --- | --- | --- |
| 声明发现 | `discovery.py:71-83` 按 `manifest.tools` 逐条建 `ExtensionToolDescriptor`；`parse_manifest`（`native.py:56-85`）校验闭合字段集、唯一 action、`capability` 属于 package、`source_owner` 属于 `dataset_owners` | 提供方 `package.capabilities` 必须**同步**加新 action，否则 `native tool exceeds its package` |
| 重复动作 | `discovery.py:105-111`：同 action 出现两次 → 整家 `native_action_conflict` 被剔除 | 新 action 名全局唯一 |
| 上限 | `discovery.py:113-115`，见 §1.3 | 动工前核对总数 |
| 执行链 | `native_extensions/__init__.py:154-246` 固定链条：`_role` → `before_dispatch` 闭包 → `execute` → `parse_result` → 逐 artifact `read_artifact` → handler `adopt` → `_validate_response` | **无需改**；只读动作自动走 `_source_response`（`:264-277`） |
| 只读回执 | `native.py:154-157`：`side_effect=none` 时 `effect` 必须 `none` 且 `operation_id` 必须 `None` | `_READ_ACTIONS` 必须包含所有新只读动作 |
| 结果处理器 | `__init__.py:221-225`：默认 handlers 只覆盖 Image；Screen/Content 有专用 adopter；其余走 `_source_response` | Reality/Together 新动作**不需要**专属 adopter（除非引入 artifact） |
| 目录登记 | `astrbot_host/integration_catalog.py:28-47` 是**静态**表，页面只显示接入状态 | 仅在换家具/名称时改；**页面不读清单** |
| Together 特例 | `__init__.py:30,162-168`：只有 `together.room.create` 需要 `host_persona` + `host_execution` | 新增 `room.join`/`invitation.create` 若也要人格绑定，需在同处扩展；否则无身份成员项风险 |
| Together 执行绑定 | `__init__.py:33-38,48` | 若新动作需要 TTS/模型绑定，复用 `together_execution_binding` |

**唯一需要判断的宿主改动**：`TOGETHER_CREATE_ACTION` 这一处特例是否要扩成"需要人格绑定的动作集合"。建议扩成集合常量 `TOGETHER_PERSONA_ACTIONS = {"together.room.create", "together.room.join"}`，并保留原行为不变。

## 8. 陪伴小屋页面

页面只做两件事：**如实显示接入状态**、**给提供方入口**；不在页面里做执行。

现有落点：`pages/陪伴小屋/app.js:236`（`together` 共处电话）、`:239`（`reality` 现实设备台），详情走 `cap-together`/`cap-reality`。

设计稿（[可选能力与家具](../../astrbot_plugin_private_companion/docs/OPTIONAL_CAPABILITIES_AND_FURNITURE_V0.md) §6）要求显示"设备与现实场所、使用方式、联动偏好、音量与资源、状态与停用"，且**无需向普通用户展示内部 operation 或 generation 名词**：

- **Reality 设备台**：真实设备与场所、镜头/声音覆盖**分开**、最近实际动作及**已知**结果、停止/撤权/换绑入口。
- **Together 共处电话**：当前房间与模式、成员、素材与进度、邀请入口。

**改页面后的必查项**（同[构建状态](BUILD_STATUS.md)口径）：

1. `node --check` 语法检查；
2. `pages/陪伴小屋/index.html` 缓存串升版；
3. `tools/sync_framework_page.py` 重新生成 `workspace-bundle.js` 与 `page-build.json`，`--check` 必须为 0 差异；
4. 相关 `tests/test_*_page.cjs` 夹具同步（现有 6 个：`test_semantic_page.cjs`、`test_native_perception_page.cjs`、`test_models_page.cjs`、`test_perception_page.cjs`、`test_reply_page.cjs`、`test_expression_page.cjs`）。
5. 注意 `page-build.json` 哈希**只挡交付包**——页面运行时不读清单。

## 9. 测试与验收清单

### 9.1 分层（不能互相替代）

| 层 | 做法 | 能证明什么 |
| --- | --- | --- |
| 合同层 | 扩 `tests/test_reality_together_native.py`（370 行 11 项）：新动作参数校验、只读回执不带 `operation_id`、未知不重试、撤权立即拒、目录字段不超声明 | 声明与执行边界 |
| 隔离适配层 | 假米家/假房间/合成音频，按 S6 §6 的 18 份夹具 W1-F01--18 逐条固定原输入、初始快照、授权修订、可控时钟与注入点 | 覆盖/治理/竞争语义 |
| 真机层 | 真实米家设备、真实房间服务器、真实 TTS/STT、真实 QQ | 实际效果 E09--E12 |

**夹具到切片的分配**：W1-F01→S2、W1-F02→S2、W1-F03/04→S5(RI-3)、W1-F05/06→S5(RI-3)、W1-F07/08/09→S3、W1-F10→S5(TG-2)、W1-F11/12/13→S4、W1-F14→S5、W1-F15→S1/S2、W1-F16/17→S6(TG-4)、W1-F18→S4。

### 9.2 逐切片新增测试项

| 切片 | 新增测试文件/用例 | 覆盖判据 |
| --- | --- | --- |
| S1 | `tests/test_reality_together_native.py` 增"多动作账本"用例组 | J1-1--J1-8 |
| S1 | Reality 插件内新增 `tests/test_native_provider_actions.py`（该插件现有 8 个测试文件，无 provider 专项） | 目录键集合、preflight 修订、动作白名单 |
| S2 | `tests/test_reality_view.py`（新建） | J2-1--J2-6，含假时钟 |
| S3 | `tests/test_together_members.py`（新建）+ Together 侧 `tests/test_native_room_isolation.py` 扩 | J3-1--J3-6 |
| S4 | `tests/test_together_turns.py`（新建） | 覆盖账、换代隔离、fallback 不双播 |
| S5 | `tests/test_together_coverage.py`、`tests/test_reality_invitation.py`（新建） | 覆盖不填洞、邀请竞争、回拨查账 |

### 9.3 既有测试必须一起跑

- 本体：`tests/test_reality_together_native.py`（当前 `test_registry_discovers_exact_stars` 硬断言 **7** 条声明，动作面扩到 14 条后**该断言必须同步改**——这是最先会红的用例）。
- Reality 插件 `tests/`：8 个文件（`test_reality_touch_camera.py` 43344 B、`test_mobile_gateway.py` 38544 B、`test_wakeup_alarm.py`、`test_reality_touch_audio.py`、`test_reality_touch_commands.py`、`test_legacy_migration.py`、`test_page_takeover.py`、`test_plugin_boundary.py`）。
- Together 插件 `tests/`：**25 个文件 4753 行**（23 个 `test_*.py`），其中与本次最相关：`test_native_room_isolation.py`(105)、`test_room_lifecycle.py`(218)、`test_server_security.py`(118)、`test_models.py`(86)、`test_release_package.py`(47)。

### 9.4 可复跑命令

```powershell
# 本体合同层（AstrBot 自带 Python + backend/app 入 PYTHONPATH）
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_reality_together_native

# 两家提供方各自的测试目录
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest discover -s 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/tests' -t 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest discover -s 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/tests' -t 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion'

# 宿主侧 64 条上限的实际占用（动工前跑一次）
Select-String -Path 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_*/native_v2/provider.py','C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion/native_v2/adapter.py' -Pattern '_ACTIONS\s*=|ACTION\s*='

# 编译与页面检查
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m compileall -q companion_v2 astrbot_host
node --check 'pages/陪伴小屋/app.js'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/sync_framework_page.py --check
```

按 AGENTS.md：开发期只做**阻断性问题所需的最小定向检查**，统一回归留到交付包构建之后；**旧包的验收结果不能替代新包测试**。

## 10. 排期建议（含放弃项）

### 10.1 顺序

1. **S3 的身份拒绝路径**（`open_room` 去回退 + 服务端拒绝码）——独立、小、风险最高，最先合。
2. **S1**（Reality RI-1 动作面 + `dispatched_at` + B8 目录字段）——地基，可与 1 并行。
3. **S2**（RV-1 格式 + 诚实降级）——不依赖库，可与 1/2 并行。
4. **S3 其余**（票据→邀请、同房加入、端点分权）。
5. **S4**（TG-3 范围账）——依赖 S3 的端点身份。
6. **S5**（RI-3 + TG-2）——跨两家，邀请 owner 放 Reality。
7. **S6**（RV-2 / RI-2 / TG-4）——依赖真实依赖齐备。

### 10.2 本轮明确不做（并说明为什么）

| 不做 | 原因 |
| --- | --- |
| 缺陷 B0b（Screen 拒权记 `unknown`） | 思路稿 §8 按用户口径**只记录**；但它与 S1 同源，改 S1 时**照 Reality/Together 的写法**，不要照 Screen |
| 缺陷 B0c（`work` 静默降级为 `call`，回执仍报 `work`） | 已核实：降级在 `main.py:1923-1924`，回执取 `ticket.mode`（`provider.py:419`）。属 S3 同一区域，**建议随 S3 一并修**（回执报实际 mode，或创建前即拒绝），但不单独立项 |
| 缺陷 B0d（账本损坏连带关闭无关功能） | 已核实并**比思路稿更糟**：`NativeTogetherProvider` 构造抛错从 `initialize()` 直接冒出（`main.py:453-457` 无 try/except），不仅房间后台任务不启动，`companion_v2_native()` 也返回 None，整家原生能力消失（不是"静默"）。同样只记录 |
| 缺陷 B8（目录多返回 `cache_updated_at`/`logged_in`） | **并入 S1**（一行改动，且 `logged_in` 有语义泄漏风险） |
| TG-4 的跨端接管、RI-4/RV-4 联合恢复 | 依赖 Repository 与真实依赖，归 S6 |
| 真实设备/房间/QQ 现场验收 | 按统一顺序在交付包构建后统一测试 |

## 11. 遗留确认点（动工前需要用户拍板）

1. **规模**：§1.3 的 47 条是否接受？如不接受，砍 `room.media.coverage` 还是砍 lookup/cancel？
2. **B0c 是否随 S3 一并修**？它会让 `together.room.create{mode:"work"}` 在 Screen 缺席时报成功但按 `call` 运行，属用户可见行为变化。
3. **邀请 owner 放 Reality**（思路稿建议）是否确认？这决定 TG-1 是否要建成员邀请表，还是只接收 Reality 签发的合法加入。
4. **页面接入批次**：本清单的 S5 才涉及页面（§8）。若希望更早看到页面变化，需要提前抬 S5。

## 11. 实施回填（2026-09-27 落地时修正的两条清单错误）

清单在落地时被实现打回两处，**原文的取值是错的**，此处按实测改正：

| 原清单写法 | 实测结论 | 原因 |
| --- | --- | --- |
| `reality.operation.cancel` 用 `side_effect: "none"` | **必须用 `"local"`** | 宿主合同（`companion_v2/capabilities/native.py:154-157`）规定 `side_effect=none` 时 `operation_id` 必须为 `None`、`effect` 必须为 `"none"`。但"取消"必须点名一个 operation 并如实报出结果，所以它不能声明为无副作用。`local` 是唯一既允许 `operation_id` 又表示"没有外部世界副作用"的取值（`SideEffect` 枚举见 `companion_v2/execution/models.py:53-58`）。 |
| `operation.lookup` 复用 `_same_request()` 身份校验 | **按显式 `operation_id` 查账时必须跳过该校验** | 原 `lookup()` 只在"同一 action + 同一 invocation"下工作，身份自然相等。而模型可见的 `reality.operation.lookup` 是**另一次调用**（不同 action、不同 invocation），身份必然不等，实测抛 `native_original_invocation_mismatch`。改正：显式 `operation_id` 路径只依赖 `store.get(scope, ...)` 的作用域隔离；身份校验只保留给"按 invocation 回查自己原请求"的兜底路径。 |

另外两项落地取值调整：

- `reality.device.action` 的 `side_effect` 用 `"external_device"`（比原写的 `external_network` 更准确：操作对象是物理设备）。
- `reality.device.action` 的 `value` 声明为 **`string`** 而非联合类型：宿主只接受**闭合 JSON Schema 子集**（`companion_v2/conversation/external_tools.py:46-72` 的 `_check_schema` 明确拒绝 `"type": [...]`），取值转换与范围校验因此落在提供方 `_parse_verb()`。

已落地的动作面（实测）：Reality **7** 个动作（原 4 + `device.action` / `operation.lookup` / `operation.cancel`），Together **4** 个（原 3 + `room.members`）。宿主聚合总数因此为 **41**，未触及 64 条上限。

---

**本轮性质**：只出清单。未改运行代码、未连宿主、未调模型/设备/房间服务器、未构建交付包、未跑测试；对账依据全部为工作树源码 `file:line`，读的是当前工作树而不是文档自评。
