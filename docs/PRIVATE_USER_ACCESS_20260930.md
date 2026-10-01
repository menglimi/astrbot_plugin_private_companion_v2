# 私聊用户权限：口径、执行点与落地顺序（2026-09-30）

需求（用户原话归纳）：**每个私聊用户可以单独设置主动权限与对话权限**；新私聊用户**默认开对话、关主动**；
默认值可配置；无权限时按可配置的文案回复（例："老大不让我和陌生人说话哦"）。

调研结论先说，因为它推翻了最初的做法。

---

## 一、V2 已经有"按人"的权限，不要造第二套

| 需要的东西 | V2 现成的 | 位置 |
| --- | --- | --- |
| 对话权限 | `conversation.reply` grant | 动作定义 `companion_v2/identity_policy/object_access.py:56`；执行点 `conversation/messages.py:192` |
| 主动权限 | `proactive.contact` grant | 动作定义同上 `:57`；执行点 `proactive/preferences.py:92`、`proactive/service.py:363/373/815` |
| 按人存储 | `identity_grants(grant_id, subject_kind, subject_id, capability, payload_json)` | `companion_v2/storage/schema.py:428`（索引 `:436`） |
| 每窗口主动授权 | `ContactManagement._grants`（`proactive-managed:` 前缀） | `companion_v2/proactive/management.py:66-76` |

`docs/V2_USER_PAGE_GAP_PLAN_20260930.md:19/160` 已经明确否掉"再造一个用户级开关"——
**页面改了 grant、grant 又有一份副本**，迟早出现"页面说关了、grant 还开着"的双源状态。

所以本次**不新增按人的权限存储**：最初写的 `access.private_permission.v1` 文档（按 subject 的
`memory_views` 记录）已经删掉。per-person 权限继续只由 grant 表达。

## 二、这一轮真正要补的四件事

| # | 要补什么 | 为什么 | 落点 |
| --- | --- | --- | --- |
| 1 | **优雅拒绝** | 今天撤销 `conversation.reply` 会抛 `host_grant_changed`（`astrbot_host/multi_authority.py:142-144`，在 `select()` 内，早于 `check_context_access`）→ 只有一行 warning，既没拒绝也没文案 | `multi_authority.provision_scope`：只对**必需** capability 硬失败；`conversation.reply` 撤销视为操作员意图 |
| 2 | **统一闸** | 单/多目标唯一汇合点是 `CompanionApplication.accept` | `companion_v2/host/application.py:504`（`flow.accept` 的事务之前，零残留） |
| 3 | **拒绝文案出口** | 文案必须在"对话权限为假"时仍能发出 | 新 `DeliveryOwner`，照 `ImageReviewFallback`（`conversation/media/fallback.py:31` + `application.py:236` 注册）；需自己调一次 `forbidden_word_guard`，且不会写 `conversation_sent_history` |
| 4 | **主动短路** | 撤销 `proactive.contact` 其实已生效（四处都在查），只差"别在读取预算/模型前白跑" | `proactive/scheduling.py:149` 之后 `return None`；**不要写状态**（写 `proactive_contacts` 行会被 `service.py:380-381` 判为"已退休"，永久封死该对象） |

**最高风险的一条**：不要让"权限为假"去摘掉 `text` / `message.delivery` 授权——
`onebot.py:72` 的 `self.authorize()` 会让拒绝文案自己也发不出去，"拒绝但告诉他"就自相矛盾。
正确形状是**保留投递授权，只关对话与主动**。

## 三、配置面（本轮已落地）

新组 `private_access`（`companion_v2/relationships/private_access.py`，层：安装 → 角色）：

| 字段 | 默认 | 含义 |
| --- | --- | --- |
| `private_access.dialogue_default` | `true` | 没人决定过的新私聊用户：可以对话 |
| `private_access.proactive_default` | `false` | 没人决定过的新私聊用户：不可以被主动联系 |
| `private_access.denied_reply` | `老大不让我和陌生人说话哦` | 无对话权限时回的话；留空＝不回 |
| `private_access.notice_cooldown_seconds` | `21600`（6 小时） | 同一个人多久内只回一次拒绝；`0`＝每次都回 |
| `private_access.stranger_notice_enabled` | `true` | 未绑定的陌生号是否也婉拒一句（默认开，见第四节） |
| `private_access.stranger_notice_daily_cap` | `3` | 陌生号每天最多回几条；`0`＝一个都不回 |

**踩到的坑（值得记住）**：`FieldDefinition.owner_id` 必须是**已注册的 owner**。
最初写了 `owner_id="private_access"` 但没有在 `application.py` 的 `owners=` 里注册，
宿主启动时契约校验失败，被 `multi_controller._failure()` 吞成 `host_control_failed`
（一句通用原因，看不出真因）。改成跟随默认 owner（与 `person` 组一致）后恢复。

## 四、已拍板的两个产品问题（2026-09-30）

1. **默认权限不签发 grant**——"没人决定过"就是读的时候按配置默认值解释，不写任何记录。
   省掉一次写，也不会出现"记录说关、grant 说开"的第二真源。
2. **陌生号也要回**——这需要一条新的"陌生首触"通道（见下），因为今天它根本走不到发送路径。
   代价与风险要在动手前说清：接管本不属于本插件的事件（`stop_event()`）、对未绑定账号做一次
   真实外部发送、并且这条发送没有 grant 兜底，只能靠配置与频率限制约束。

### 陌生首触通道的形状（下一步实现）

| 项 | 决定 |
| --- | --- |
| 触发条件 | 私聊事件、插件处于运行态、发送者解析不到任何目标/绑定、`stranger_notice_enabled` 为真 |
| 发送内容 | **只有** `denied_reply` 这一行；不读记忆、不调模型、不建身份、不进相识目录 |
| 频率 | 同一账号 `notice_cooldown_seconds` 内只回一次；每天总量不超过 `stranger_notice_daily_cap` |
| 归属层 | 发送实现必须在 `astrbot_host/`（依赖 AstrBot SDK），核心包不得反向导入 |
| 记录 | 记一条有界回执（账号、时间、命中哪条配置），便于"为什么回了这个人"可查 |
| 不做 | 不签发任何 grant、不创建 binding、不写 `conversation_*` 表、不进入投递队列的对话语义 |

新增的两个配置字段（本轮已落地）：`private_access.stranger_notice_enabled`（默认 `true`）、
`private_access.stranger_notice_daily_cap`（默认 `3`，`0` 表示一个都不回）。

## 五、验证现状

**已实现（本轮结束时的真实状态）**

| 件 | 状态 | 证据 |
| --- | --- | --- |
| 配置面（6 字段：默认对话开/主动关、拒绝文案、冷却、陌生号开关与日上限） | ✅ | `tests/test_private_access.py` **3/3** |
| 收回权限不再被当成宿主故障（多目标 + 单目标两处供给路径） | ✅ | `tests/test_astrbot_multi_host.py` **15/15**（含 2 条新用例） |
| **对话权限在收信入口真实生效**：没有权限就不进对话（无批次、无模型调用），失败码是明确的 `private_access_dialogue_denied` | ✅ | `tests/test_private_access_host.py` **9/9** |
| **无权限时按配置回一句**：经平台反向 WebSocket 直发（系统行为，不经过角色、不读记忆），按人冷却，留空则安静，预览模式不出网 | ✅ | 同上 |
| **主动权限在规划阶段短路**：收回 `proactive.contact` 后不再准备主动联系，且**不写任何状态**（写了会被判"已退休"永久封死） | ✅ | `tests/test_proactive_permission.py` **2/2**；相邻 `test_contact_scheduling` **22/22**、`test_proactive_contacts` **28/28**、`test_background_history` **13/13** |
| **6 个字段挂进陪伴小屋**（决策页「关系与理解」一节；分区自检 18 区 / 288 字段全过） | ✅ | `test_section_wiring.cjs` **8/8**、`test_configuration_api` **6/6**、`tools/audit_page_config_coverage.py` 通过 |
| **默认值真的决定新用户**：默认关的能力不签发（`dialogue_default=false` 时下一条消息也不会被重新放行），默认开的能力即使不在能力表里也签发 | ✅ | `tests/test_private_access_host.py` 两条新用例 |
| **关系页写入口**：`GET/POST /acquaintance/authorization` + `PersonAuthorizationManagement`（页管能力 = `conversation.reply` / `message.delivery` / `proactive.contact`，每次改动一条操作回执，运行档签发的那些明确拒绝并指路） | ✅（另一窗口实现，本轮核对） | `tests/test_person_authorization.py` **20/20**（连跑两次） |
| **陌生号（未绑定）也回一句**：只对本插件拥有的账号发、只在真实投递模式发、只发配置那一行、不建身份/不写对话表/不签发 grant；同一账号冷却 + 每日总量上限；真发了才 `stop_event()` | ✅ | `tests/test_stranger_notice.py` **7/7** |

### 陌生首触通道的实现要点（2026-09-30 完成）

`astrbot_host/stranger_notice.py` + `main.py` 的一处分支：

| 项 | 做法 |
| --- | --- |
| 触发 | `main.py` 里 `claims()` 为假（不属于任何目标）**且**是私聊消息；插件运行中 |
| 账号校验 | `self_id` 必须是本插件已配置的账号，且平台实例、客户端、反向 WS 连接都与事件一致；否则一律不发 |
| 排除 | 已配置对象**永远不被这条路回答**（他们有自己的窗口与权限判定）——这条是防御性的，即使调用方判断错了也抢不走 |
| 配置来源 | 读**安装层**默认值（陌生号没有角色，不去编一个出来） |
| 频率 | 同一账号 `notice_cooldown_seconds` 内一次；每天总量不超过 `stranger_notice_daily_cap`（`0` = 完全不回）；**送出去了才记账**，失败不占额度 |
| 事件处置 | 真发了这一句才 `stop_event()`：插件已经作答，就不该让对方再收到 AstrBot 默认管线里的第二条回复 |
| 不做 | 不签发 grant、不创建 binding、不写 `conversation_*`、不读记忆、不调模型 |

**关键实现说明（两条，都是踩出来的）**

1. **礼拒不走核心投递通道**。最初按 `ImageReviewFallback` 的形状给核心投递加了一个 owner，
   结果 `unknown_access_action`：`DeliveryOwner.action` 必须是一个**已注册的访问动作**，
   而 `feature_access` 对 STANDARD 主体还要求该动作的 grant——对"刚被收回权限的人"
   甚至"没有任何身份的陌生号"根本走不通（顺带发现既有的 `conversation.image_review_fallback`
   也是这个状态）。因此改为：**核心只做决定**（`PrivateRefusalNotice.due()` + 冷却记账），
   **发送在 `astrbot_host/private_notice.py`**，用平台反向 WebSocket 直发一行纯文本。
2. **路由认证复用 notice 那一套**。`authenticate_notice_route` 原本只认 `post_type == "notice"`；
   加一个 `expected_post` 参数后，消息事件用 `expected_post="message"` 走同一套严格认证
   （账号、平台、客户端、会话来源），不另写一份。

- 回归：`test_person_acquaintance` **12/12**、`test_astrbot_poke_host` **8/8**、
  配置覆盖自检 17 分区 / 282 字段全过。
- **另有一条与本功能无关的红灯**：`test_astrbot_staging_host.test_sender_requires_explicit_authorization_then_records_ack`
  期望 `authorization_denied` 却拿到 `authorization_revoked`。用"把我的单目标改动临时回退再跑"的方式二分过，
  **回退后同样失败**，属另一窗口在建面，不是本轮引入。

## 六、落地顺序

1. 修 `multi_authority.provision_scope` 的硬失败（高风险，先补测试锁住"撤销不再抛、必需 capability 仍硬失败"）；
2. `application.accept` 统一闸 + 拒绝文案 `DeliveryOwner`（含冷却）；
3. `proactive/scheduling._plan` 短路；
4. 关系页写入口（读/写 grant，走操作账本）——同时回答上一版文档 `:143-144` 的"grant 与页面写入如何同源"；
5. 把 4 个字段挂进陪伴小屋分区（SECTIONS + GroupEditor + 审计 MODULES）。
