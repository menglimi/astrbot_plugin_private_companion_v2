# Reality / Together 拓展实现思路（按设计稿，不改代码）

2026-09-27。对象：Reality Companion（`astrbot_plugin_reality_companion` 0.4.1）与 Together Companion（`astrbot_plugin_together_companion` 0.9.0）两个能力提供方。

本文**只出实现思路**：核实设计稿的包划分、对账当前源码的真实边界、给出可落地的改动位置与判据。本轮未改任何运行代码、未连宿主、未调模型/设备/房间服务器、未构建交付包。已知缺陷按用户口径**只记录**（见第 8 节），不在本轮修。

设计稿即权威依据：[S6 第一波联合交接与验收](../../astrbot_plugin_private_companion/docs/S6_REALITY_TOGETHER_JOINT_ACCEPTANCE_V0.md)（S6-WAVE1-JOINT-D01 / D）、[Together 会话、媒体与插话](../../astrbot_plugin_private_companion/docs/TOGETHER_SESSION_MEDIA_AND_INTERRUPTION_V0.md)、[Reality 信息视图](../../astrbot_plugin_private_companion/docs/REALITY_INFORMATION_VIEW_AND_QUERY_V0.md)、[Reality 核心互动](../../astrbot_plugin_private_companion/docs/REALITY_INTERACTION_AND_RECEIPTS_V0.md)、[Reality 摄像头与音响](../../astrbot_plugin_private_companion/docs/REALITY_CAMERA_SPEAKER_AGENCY_V0.md)、[Reality 感知方向](../../astrbot_plugin_private_companion/docs/REALITY_PERCEPTION_DESIGN_V0.md)。本体侧既有记录见[Reality/Together 原生接入](REALITY_TOGETHER_NATIVE_20260926.md)与[七个可选伴侣对照表](COMPANION_PROVIDER_STATUS_20260927.md)。

## 1. 设计稿要什么，代码现在有什么

设计稿按实现包交付，每包都有退出证据。当前两个提供方各只有一个 `native_v2/provider.py`，动作面如下（读代码常量，不是文档自评）：

| 侧 | 设计包 | 设计要求 | 代码现状 | 缺口性质 |
| --- | --- | --- | --- | --- |
| Reality | RV-1 | 来源目录、概览、查询结果与**四类范围**（请求/实际采集/查询枚举/返回材料）分别记录，分页带快照游标 | `reality.snapshot.read` 一次返回整份 `mobile_context`，顶层 `available` 只表示位置可用 | 格式与语义缺失 |
| Reality | RV-2 | 领域 Repository、持续采集、时间/覆盖记录、稳定分页、失效通知 | 无库、无历史；`mobile_gateway` 多数短期数据在内存 | 存储缺失 |
| Reality | RI-1 | 目标/覆盖/绑定修订、提交-查询-**取消**分离、设备确认层与未知范围 | 只有 `reality.device.control`（`alias`+`is_on`）单动作，无查询/取消入口；预检 `extension_control_preflight` 在派发前跑 | 动作面缺失 |
| Reality | RI-2 | 位置/设备/关系材料与自主观察、独立音响接入**同一角色与 S5 唯一输出** | 采集与播放各自在 V1 主动链（`reality_touch_camera.py`、`reality_touch_audio.py`），V2 侧无入口 | 消费链接线 |
| Reality | RI-3 | 邀请及期限、接受/拒绝/结束、回拨关联、晚到结果 | 无。`mobile_create_room` 只发房间链接 | 未开工 |
| Together | TG-1 | 版本化 payload、同房邀请/加入/退出、端点与权限、持久 Repository | `RoomSession` 持单个 `user_id` + 单个 WebSocket；票据消费后 `open_room` **新建 room_id** | 身份模型不足 |
| Together | TG-2 | 素材/版本授权、控制修订、逐端点呈现覆盖、模型读入范围、剧透偏好 | `media_state` 记播放器状态；无逐端点覆盖 | 语义缺失 |
| Together | TG-3 | 输入身份/修订、声音让出、S5 unit/part 与播放范围映射、取消边界与未知段 | 有生成取消、停音频、浏览器朗读回退；无"实际已播范围"账 | 账本缺失 |
| Together | TG-4 | 非空完整重启、控制代 CAS、跨端接管、结束释放 | `detach_room`/`resume_room` 是**内存宽限期**（默认 180 秒），不跨进程 | 持久性缺失 |

一句结论：**两家都已"接线"但都停在最小动作面**。Reality 停在"读一次快照 + 开关一个设备"，Together 停在"建房/查房/关房"，设计稿的 RV-1..4 / RI-1..4 / TG-1..4 基本都还没往上走。这与[对照表](COMPANION_PROVIDER_STATUS_20260927.md)的口径一致，不是文档滞后。

## 2. 三层分工：动哪个文件

设计稿 §8.1 已把顺序定成"配套格式 → 读取与单动作 → 角色与通话接续 → 语音与插话 → 联合恢复与效果"。落到本仓库，这三层必须分清，否则会出现"页面看起来接了、实际没执行"：

**第一层｜提供方（真正的执行与权威）**

- Reality：`native_v2/provider.py`（动作声明与执行）、`mihome_web_api.py`（设备目录/状态/控制/preflight，`:455`/`:469`/`:474`/`:500`）、`mobile_gateway.py`（`:587 mobile_context`、`:1157 mobile_create_room`、`:1996 mobile_close_session`）、`main.py`（`:209 companion_v2_native`、`:338 mobile_context`、`:637` 起装配 provider）。
- Together：`native_v2/provider.py`、`main.py`（`:70 companion_v2_native`、`:1255 issue_room_ticket`、`:1921 open_room`、`:1949 detach_room`、`:1978 resume_room`、`:2028 close_room`、`:454` 起装配 provider）、`models.py`（`:20 NativeRoomBinding`、`:36 RoomTicket`、`:49 RoomTicketStore`、`:95 RoomSession`）、`server.py`（WebSocket 入口）。

判据：设计稿说"规则/状态裁决在提供方，V2 不重算"。所以播放进度、设备确认层、邀请阶段这些**必须**落在提供方，本体只做引用与采用。

**第二层｜V2 本体宿主（授权、复核、采用、回执）**

- `astrbot_host/native_extensions/__init__.py`：`invoke()` 里 `execute` → `parse_result` → 逐 artifact `read_artifact` → 结果处理器 `adopt` → `_validate_response` 的固定链条；`before_dispatch` 是派发边界（`:184-196`）。
- `astrbot_host/native_extensions/discovery.py`：声明发现与聚合（注意 `:113-115` 的超 64 条清空行为）。
- `companion_v2/capabilities/native.py`：`parse_manifest` / `parse_result` 的合同校验，provider generation 只当不透明串。
- 消费侧：`companion_v2/conversation/`（生成与输出）、主动链、记忆域。

**第三层｜陪伴小屋页面**

只显示接入状态与跳转，不在页面里做执行。当前 `pages/陪伴小屋/app.js` 的家具目录已有 `together`（共处电话）与 `reality`（现实设备台）两件，`:236`/`:239` 定义，详情走 `cap-together`/`cap-reality`。

## 3. Reality 侧实现思路

### 3.1 RI-1 先行：把"一个开关"扩成可查询的操作账

这是所有后续动作的地基，也是设计稿 §8.1 第二行的"单动作"退出依据。

**动作面扩展**（`native_v2/provider.py` 的 `_ACTIONS`）：

```text
reality.device.control   已存在：alias + is_on
reality.device.action    新增：alias + action(枚举) + 参数对象（枚举按设备档案白名单派生）
reality.operation.lookup 新增：operation_id 或 invocation_id → 回原账
reality.operation.cancel 新增：仅对已 prepared、未 dispatching 的操作成立
```

关键约束（三条都是设计稿硬要求，也是现状最容易被做错的地方）：

1. **查询不等于采集**。设计稿 RV-1 明确"查询既有资料不会暗中转成相机采集或付费分析"。因此 `operation.lookup` 只读账本，不得触发设备重试。
2. **预检在派发之前，派发之后不再回退**。现有 `execute` 的控制分支已经把 `preflight` 放在 try 里、把外部调用放在之后，这个结构是对的，扩展时保留：`prepared → dispatching → succeeded|unknown` 三态迁移里，`dispatching` 之后任何异常都落 `unknown + effect=unknown`，且**不自动重试**。
3. **确认层只有米家 `confirmed: true` 才记 committed**。现在 `extension_control_power` 返回 dict 带 `confirmed`，扩展时保持这一层不被"HTTP 200 即成功"替代。

**当前 `execute` 的实现坑**（要在改的时候一并处理，属实现细节不是新缺陷）：控制分支的 `dispatch` 之后仍走同一段 `except`，`dispatched` 判定用的是 `store.get(...)["state"] == "dispatching"`——扩展出多动作后，这个判定应改为在操作行上显式记一个 `dispatched_at`，否则取消与查询会读到中间态。

**绑定与覆盖**：设计稿要求"设备/绑定修订"可核对。落点是在 `NativeRoomBinding` 风格的领域记录里加 `target`（别名 + 类别 + 场所）与 `binding_revision`，并在投递给设备前用 `preflight` 复验修订未变。换绑（别名重映射）必须让旧引用失效，不能沿用旧 DID。

**判据**：同一 operation 可被 `lookup` 读回；撤权后立即拒绝且**不新建**操作行；未知结果保留原 operation 且不重试；换绑后旧引用失效。

### 3.2 RV-1 / RV-2：信息视图与历史

RV-1 的形态是三个独立输入/结果格式——**来源目录**、**概览**、**query/read**，不是把 `mobile_context` 整份塞给模型。现状 `mobile_context` 顶层 `available` 只表示位置可用，这个语义必须拆开，否则模型会把"没有位置"读成"什么都没有"。

**来源目录**：逐来源声明的身份、修订、可读能力、可用性（`available` / `unknown` / `unsupported` / `unauthorized`）。Reality 侧来源至少包括：位置、设备（米家）、手机活动摘要、遥测指标、屏幕共享状态、摄像头、音响。

**四类范围必须分别记录**（设计稿 §3 RV-1 行的硬要求）：

| 范围 | 含义 | 现在有没有 |
| --- | --- | --- |
| 请求范围 | 本次查询要什么（时间窗、来源筛选、限额） | 无 |
| 实际采集范围 | 来源真正返回了什么 | 无 |
| 查询枚举范围 | 翻页时实际枚举到哪里 | 无 |
| 返回材料范围 | 最终交给模型的材料 | 无（模型直接拿整份快照） |

**时间语义**：`captured_at` 与 `received_at` 分开；心跳只更新 `received_at`，**不更新 `captured_at`**（现状 README 已说明，但快照里未成结构）。健康类累计值必须带统计窗口与单位，且不允许把多个窗口的值相加。

**RV-2 的降级路径**（这是可先做、不必等库的部分）：先让快照适配器诚实地返回"仅支持快照 / 历史未知"，把 `history` 能力显式声明为 `unsupported`。设计稿明确"无历史如实返回"就能与来源目录、模型、关注机制隔离对接。真正的历史要等 Reality 领域 Repository（独立 DDL/迁移，不改已固定的 SQL），**不能从旧内存缓存反推过去的完整过程**。

**分页**：游标要绑来源修订；来源 revision 变化或撤权时旧游标失效并**显式**返回，不能让旧页凑成一次完整查询（夹具 W1-F02 就是这条）。

### 3.3 RI-3：来电、拒接与回拨

设计稿把这部分的要求写成"真实连接与输出逐步取证；振铃不提前采集，过期决定不作用到新通话"。现状完全空白——`mobile_create_room` 返回的是房间链接，"开房链接不等于接通"。

最小可行形态是**邀请实体 + 期限 + 领域阶段**，而不是新建联合状态机：

```text
Invitation {
  invitation_id, revision, direction(inbound|outbound), purpose_ref,
  requester(已鉴别主体), target, requested_media[], expires_at,
  stage(ringing | accepted | rejected | revoked | expired),
  session_ref?, operation_ref?
}
```

四条要点：

1. **邀请不按消息次数计意愿**。设计稿 §9 的对照表明确否掉"达到次数后强制请假"和"第二次必须接"。域内只记真实阶段，是否改口的判断归原模型。
2. **拒接 `succeeded` 不等于解释已发出**。拒接操作与私信输出是两条独立账（夹具 W1-F05）。
3. **接受与取消/到期在同一修订上竞争**，邀请 owner 只提交合法裁决；迟到决定不作用于新邀请（夹具 W1-F03）。
4. **回拨是新的联系**，以新 operation/key 关联原 purpose，先查原账再拨，未知不重拨（夹具 W1-F06）。

落点：邀请是 Reality/Together **共同**需要的东西——Reality 发起（来电/回拨），Together 承载（接入 Session）。建议**邀请 owner 放 Reality**（它持有移动网关与用户身份），Together 侧只接收"合法加入"，这样能避免两家各存一份邀请表。

### 3.4 RI-2：自主观察与独立音响

设计稿 [§8 现有代码差距](../../astrbot_plugin_private_companion/docs/REALITY_CAMERA_SPEAKER_AGENCY_V0.md)已逐文件核过，改造要点是**把旧实现里"陪伴档位门槛 + 未回应计数"换成"有目的的自主观察 + 原模型理解关系与沉默"**，同时保留采集/授权 owner 与额度。

两条硬边界：

- **音响是独立通道，不是聊天语音的镜像**。现状 `_mirror_reality_touch_proactive_voice` 是跟随；设计稿要的是独立播放操作、明确目标（含配置过的备用目标）、准确进度与未知结果。特殊要求：**"可能已经播放"不能当作可随意重播**（这正是 B0b 那类记账问题的同类风险）。
- **沿用有效授权，不为"迁移"强迫重新授权**。用户既有"关闭 / 先问 / 限额 / 镜像"选择必须保留，且不能把"同意同步聊天语音"静默解释成"已开启任意时机的独立外放"。

V2 侧接线点：采集与播放要接**可信执行资格 + 原角色工具续答**，分别交回"采集失败"与"解释不确定"，不能把 V1 的固定不确定回复台词带过来。

## 4. Together 侧实现思路

### 4.1 TG-1 先行：同房与身份

这是 Together 侧的地基，且有一个**身份安全问题必须先解决**。

**当前身份模型的真实边界**（设计稿点名，代码确认）：

- `RoomTicket` 只有 `token / mode / user_id / native_v2`，`RoomTicketStore.consume` 是一次性。
- `open_room`（`:1921`）里 `user_id=ticket.user_id or self._resolve_primary_user_id()`——**无身份时回退主用户**。
- `RoomSession` 只有一个 `websocket`，`detach_room` 直接把它置 `None`。

因此要做的三件事：

1. **邀请票据实体化**：把 `RoomTicket` 升级为带 `invitation_id / inviter / target_subject / requested_media / expires_at` 的邀请记录，`native_v2` 之外新增 `members` 结构（每个成员一份身份 + 授权 + 可见范围）。旧票据兼容读，但**不再回退主用户**：缺身份即拒绝并返回明确错误码。
2. **同房加入**：`open_room` 变为"加入既有 Session"和"新建 Session"两条路径。加入时按 `participants_ref` 校验身份与授权，且**票据不能让新成员继承主用户的私有上下文**（历史可见范围单独给，夹具 W1-F07/W1-F08）。
3. **端点与权限分离**：成员身份、媒体控制、运行接管**分别授权**（设计稿反复强调的三件事不是一件事）。落点是在 `RoomSession` 上把 `call_camera_frame` 一类单通道状态改为按端点分桶。

**持久化**：`detach_room`/`resume_room` 现在是内存宽限期，设计稿的 TG-4 明确要求非空完整重启与**控制代 CAS**。可行路径是引入领域 Repository（与 V2 主库同构但**独立于 V2 schema**，因为 Together 是独立插件），把 `RoomSession` 的可恢复投影（成员/授权修订、素材版本、输入修订、部分播放确认、未决 operation）落盘；进程重启后从 Repository 读回引用，**网络句柄一律视为无效**。

### 4.2 TG-2：素材版本与覆盖

要点是**四个量分开**：播放器位置、共读 cursor、逐端点实际覆盖、模型实际读入范围。设计稿的 W1-F10 就是"覆盖不填洞，不取最大位置当所有人已看"。

- `media_state` 现在记播放器状态，需扩为 `{source_version, control_revision, per_endpoint: {endpoint_id: [(start,end)]}}`。
- 换源/跳转产生**新的控制修订**，旧进度晚到不得写入新版本。
- 缺字幕/音轨/正文时**如实降级**，不能从标题或另一人的进度补齐内容。

### 4.3 TG-3：轮次、语音与插话

现状已有生成取消、停音频、浏览器朗读回退。缺的是**"实际已播范围"的账**：

- 输出按 S5 的 unit/part/载荷版本记；文本范围与音频范围**分别映射**（文字完整显示 ≠ 完整播完）。
- **声音让出可先发生，是否附和/纠正由原模型理解**；已明确的停止**不等模型**。
- 换代隔离旧输出：旧模型/TTS 块晚到只结算原操作的合法结果与费用，**不能加入新轮次**。
- fallback 接**原输出身份**，不生成第二份回答；"无法证明原音频是否播出"时停止自动重播并按未知接续（夹具 W1-F13）。

### 4.4 TG-4：恢复与结束

- 非空重启：撤权/换成员/迟到结果下，恢复只签**一个新控制代**（CAS 在预期修订上），资源未就绪**不报 active**。
- 普通 resume 只适用于未过期的 `paused/reconnecting`；仍 active 的 Session 需要**另外明确的端点接管能力**，不能借 resume 抢占（夹具 W1-F16）。
- 结束：只释放本场资源与所属 World 阻碍；摘要/来源补存/费用对账可独立收尾，**失败不拖住挂断**，也**不延长原内容保留期**。

## 5. 本体宿主接线

新动作要经现有合同进本体，不能另起一套：

1. **声明**：`native_v2/provider.py` 的 `manifest()` 里 `tools[]` 增加条目（`action / capability / parameters / side_effect / timeout_seconds`）。`side_effect` 要按真实语义取：只读用 `none`，设备动作与建房用 `external_network`/`local` 要与实际一致。
2. **装配**：`discovery.py` 聚合并受**64 条上限**约束（现状超限会清空全部原生声明，见 `:113-115`）。动作面从 4+3 扩到十几条后，要提前评估这个上限，否则一次超限全家能力消失。
3. **执行**：`behind before_dispatch` 的派发边界、`parse_result` 的合同校验、逐 artifact 的 `read_artifact`、以及**同步**结果处理器 `adopt` 的固定八字（`_validate_response` 要求 adopted 结果保留原 invocation/binding/state/effect/operation_id/receipt_ref，产物还要保留原受众与 `native` metadata）。Reality 的只读回执现在**不带 operation_id**（`_response` 里 `read_only` 分支），加写动作后要注意这个分支不要被误用。
4. **消费**：Reality 的材料进入生成要沿**已封存快照 + 来源引用**的路子，不能把设备材料当作"用户发言"；Together 的 Session 摘要若进记忆，要按"只引用已确认回执"的既有口径。这部分与 `CORE_GROUP_CONTEXT_20260924.md`、`CORE_NATIVE_GAP_CLOSURE_20260925.md` 同一套边界。

## 6. 陪伴小屋页面

页面只做两件事：**如实显示接入状态**、**给提供方入口**。设计稿的家具/能力页口径（[OPTIONAL_CAPABILITIES_AND_FURNITURE_V0.md](../../astrbot_plugin_private_companion/docs/OPTIONAL_CAPABILITIES_AND_FURNITURE_V0.md) §6）要求显示"设备与现实场所、使用方式、联动偏好、音量与资源、状态与停用"，且**无需向普通用户展示内部 operation 或 generation 名词**。

因此 Reality 设备台的能力详情应显示：真实设备与场所、镜头/声音覆盖分开、最近实际动作及已知结果、停止/撤权/换绑入口；Together 共处电话显示：当前房间与模式、成员、素材与进度、邀请入口。

按[改小屋页面后的必查项](BUILD_STATUS.md)的口径，落地时页面改动要同时处理语法（`node --check`）、`index.html` 缓存串、`tools/sync_framework_page.py` 的 `page-build.json` 哈希、以及 `tests/test_*_page.cjs` 夹具。注意**页面不读清单**，所以哈希只挡交付包。

## 7. 测试与验收

设计稿 §8.3 把"设计结束"与"运行退出"分开登记，测试也要分层，不能互相替代：

| 层 | 做法 | 能证明什么 |
| --- | --- | --- |
| 合同层 | 扩 `tests/test_reality_together_native.py`（现有 370 行 11 项）：新动作的参数校验、只读回执不带 operation_id、未知不重试、撤权立即拒 | 声明与执行边界 |
| 隔离适配层 | 用假米家/假房间/合成音频，按 S6 §6 的 18 份夹具（W1-F01--18）逐条固定原输入、初始快照、授权修订、可控时钟与注入点 | 覆盖/治理/竞争语义 |
| 真机层 | 真实米家设备、真实房间服务器、真实 TTS/STT、真实 QQ | 实际效果（E09--E12） |

[验收清单](V2_REAL_WORLD_ACCEPTANCE_CHECKLIST.md)的 E09（房间）、E10（完整活动）、E11（设备读）、E12（设备控制）目前**全部"待测"**。设计稿特别提醒：**文字夹具通过不能代替真实通话**，只支持文字的切片只能报告其真实结果。

可复跑命令（AstrBot 自带 Python）：

```powershell
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_reality_together_native
```

Together 提供方自带 23 个测试文件、Reality 8 个，改动后应一并跑该插件自己的测试目录。

## 8. 风险与已知缺陷（**仅记录，本轮不修**）

按用户口径，以下既有缺陷只登记，待统一回归时处理：

| # | 缺陷 | 证据 | 影响 |
| --- | --- | --- | --- |
| B0b | Screen 把"设备调用前被拒"记 `unknown` 而非未提交 | 提供方 `native_v2/provider.py:158-175` 把 `before_dispatch()` 放在 try 内；同位置 Reality/Together 落 `failed/not_committed` | 撤权后账本记"可能已执行"，妨碍"这次到底有没有截屏"的判断。**与本次 Reality 扩动作同源风险，扩 RI-1 时要照 Reality 的写法而不是 Screen 的** |
| B0c | `work` 模式可能被静默降级，回执仍报 `work` | 提供方 `main.py:1921-1932` 在 Screen 工作协同不可用时把 `work` 改成 `call`；create 回执 `provider.py:419-422` 取自票据 | V2 被告知建成 work、实际按 call 运行，且 `snapshot` 又回报 `"call"`，同批数据自相矛盾 |
| B0d | 操作日志损坏会连带关闭无关 V1 功能 | `OperationStore._load` 抛错（Reality `provider.py:113-125`、Together `:115-127`），`main.py` 构造处未捕获（Reality `:636-639`、Together `:449-457`） | Together 房间服务后台任务不启动，V1 房间功能随之中断；与设计稿"停止加载提供方"的范围不符 |
| B8 | Reality 设备目录多返回两个未声明字段 | `mihome_web_api.py:497-498` 额外返回 `cache_updated_at` 与 `logged_in`，整份进入模型上下文 | `logged_in` 可被读作声明中排除的"登录信息" |

另有两条与本次设计直接相关的**结构风险**（非缺陷，是排期约束）：

- **聚合声明 64 条上限**：`astrbot_host/native_extensions/discovery.py:113-115` 超限清空全部原生声明。Reality 4 → ~8、Together 3 → ~8 后仍在限内，但加上 Game 22 条等其他家要留余量。
- **`companion_v2/games/` 同规则第二份实现**的先例说明：在多插件并行推进（本机同时有游戏/生图/Content 三个会话）时，容易出现同一能力两处实现。Reality/Together 的新逻辑**一律落在提供方**，本体侧只做适配，避免漂移。

## 9. 建议推进顺序

设计稿已定顺序，落地时按"可独立交付、不互相等待"切片：

1. **RI-1**（设备目标/动作/反馈）——地基，且能顺带把 Reality 侧三态迁移写对。
2. **TG-1**（会话/成员/邀请）——含身份安全修复，风险最高，宜早。
3. **RV-1**（信息视图格式 + 快照适配诚实降级）——可与 1/2 并行，不依赖库。
4. **TG-3**（轮次/语音/插话）——依赖 S5 的 unit/part 边界。
5. **RI-3 + TG-2**（邀请/回拨 + 媒体覆盖）——跨两家，建议邀请 owner 放 Reality。
6. **RV-2**（历史与 Repository）、**RI-2**（自主观察与独立音响、旧 mirror/本地播放路径退出）、**TG-4**（重启与结束）——依赖真实依赖齐备，最后做。

每步的退出证据按设计稿 §8.1 表取，**不把格式检查当作运行验收**。
