# Reality / Together 拓展落地记录

2026-09-27。本文记录按[细化实施清单](REALITY_TOGETHER_EXTENSION_IMPLEMENTATION_CHECKLIST_20260927.md)实际落地的改动、验证结果与**仍未验证的部分**。清单负责"怎么做"，本文负责"做了什么、证明了什么、没证明什么"。

## 1. 落地范围

改动落在**三个工作树**：两个提供方插件 + 本仓库（合同测试同步）。

| 侧 | 文件 | 改动 |
| --- | --- | --- |
| Reality | `native_v2/provider.py` | 动作面 4 → 7；`dispatched_at`；三态派发重写；日志升级兼容 |
| Reality | `mihome_web_api.py` | 新增 `extension_device_target` / `extension_device_actions` / `extension_device_action`；`_DEVICE_WRITABLE_PROPERTIES` |
| Together | `main.py` | `RoomIdentityError`；`resolve_room_mode()`；`open_room` 去回退；`together_command` 标签取 `ticket.mode` |
| Together | `server.py` | 无身份票据拒绝连接（1008） |
| Together | `models.py` | `RoomSession.member_revision`（受众修订） |
| Together | `native_v2/provider.py` | 动作面 3 → 7（+`room.members` / `room.invite` / `room.invitations` / `room.join`）；`InvitationStore`（独立 JSON 正本） |
| 本体 | `tests/test_reality_together_native.py` | 11 → 14 项，含 64 上限钉死断言 |
| 本体 | `tests/test_w1_fixture_harness.py`（新，13 项） | S6 §6 的 18 份夹具登记与可执行部分 |
| 本体 | `pages/陪伴小屋/app.js`、`index.html`、`page-build.json` | 两件家具的能力面与提供方入口；缓存串 `reality-together-20260927` |
| 本体 | `docs/…CHECKLIST_20260927.md` | §11 实施回填（两条清单错误改正） |
| 提供方测试 | Reality `tests/test_native_provider_actions.py`（新，16 项） | 新动作面合同层 |
| 提供方测试 | Together `tests/test_room_identity_and_mode.py`（新，10 项 + 9 子测试） | 身份与 mode 诚实性 |
| 提供方测试 | Together `tests/test_together_invitation.py`（新，16 项） | 邀请/加入/受众修订 |

## 2. 最终动作面（实测）

| 侧 | 动作 | side_effect | 说明 |
| --- | --- | --- | --- |
| Reality | `reality.snapshot.read` | none | 只读 |
| Reality | `reality.device.list` | none | 只读 |
| Reality | `reality.device.status` | none | 只读 |
| Reality | `reality.device.control` | external_network | 原单开关 |
| Reality | `reality.device.action` | external_device | **新**：power / set_mode / set_brightness / set_color_temperature |
| Reality | `reality.operation.lookup` | none | **新**：只读账本 |
| Reality | `reality.operation.cancel` | local | **新**：仅未派发可取消 |
| Together | `together.room.snapshot` | none | 只读 |
| Together | `together.room.create` | local | 建房 |
| Together | `together.room.members` | none | **新**：成员与身份 |
| Together | `together.room.invite` | local | **新**：签发有期限邀请 |
| Together | `together.room.invitations` | none | **新**：列出有效邀请 |
| Together | `together.room.join` | local | **新**：按邀请加入既有房间 |
| Together | `together.room.close` | local | 关房 |

宿主聚合总数 **44**（含其他五家），距 64 条上限仍有余量；`test_registry_discovers_exact_stars` 已把 7 / 7 钉死，动作面再涨必须先改断言。

## 2b. 邀请与加入的语义（本轮新增）

- **邀请是记录，不是凭据**。持有邀请本身不授予房间；`together.room.join` 仍按加入者自己的身份提交。
- **owner 在提供方**：窗口（默认 600 秒，可 60–3600 秒，越界在落账本前拒绝）、谁被接纳、房间指向哪一间，全部由 Together 裁决，V2 不重算。
- **跨 scope 加入**：加入者是另一个人，其上下文哈希与邀请人不相同。因此邀请**按自身标识**解析，而不管它落在哪个 scope 桶里（`InvitationStore.owner()`）；操作行仍记在调用者自己的 scope。
- **同人重放不新增成员**：同一身份再次提交同一邀请记为 `replayed`，不重复计入成员数。
- **受众修订**（`member_revision`）**每接纳一个新的不同身份 +1**，用于让在途输出能按房间当前参与者重验；重放不动修订。
- **被拒只结束该邀请**：不存在的邀请、已过期邀请、已关闭房间的邀请都被拒绝或如实回报，**不会关闭或替换房间里其他人正在进行的活动**。
- 邀请正本是 `native_v2/invitations.json`，损坏时按 `native_invitation_store_invalid` 拒绝加载（与操作账本同一策略）。

## 3. 落地时被打回的两条清单错误

详见清单 §11。要点：

1. **`operation.cancel` 不能用 `side_effect: "none"`**。宿主合同规定 `none` 时 `operation_id` 必须为空且 `effect` 必须为 `"none"`（`companion_v2/capabilities/native.py:154-157`），而"取消"必须点名一个 operation 并如实报结果。改用 `"local"`。
2. **按显式 `operation_id` 查账必须跳过 `_same_request`**。原 `lookup()` 只在"同 action 同 invocation"下工作；模型可见的 `reality.operation.lookup` 是**另一次调用**，身份必然不等，实测抛 `native_original_invocation_mismatch`。改为：显式 ID 路径只依赖 `store.get(scope, …)` 的作用域隔离，身份校验只留给"按 invocation 回查自己原请求"的兜底路径。

另外：`reality.device.action` 的 `value` 只能声明为 **`string`**——宿主只收**闭合 JSON Schema 子集**，明确拒绝联合类型（`companion_v2/conversation/external_tools.py:46-72`）。取值转换与范围校验因此落在提供方 `_parse_verb()`。

## 4. 落地过程中发现并修掉的真实缺陷

这些不是设计缺口，是实现写错后被测试和契约打出来的：

| # | 缺陷 | 后果 | 修法 |
| --- | --- | --- | --- |
| L1 | `_bind` 用同一条 power 路径服务两个 handler，而 `extension_device_action` 签名是 `(alias, action, value, …)` | 每次 `device.action` 都把布尔塞进 `action` 位、缺 `value` → TypeError 在 `dispatched_at` 之后被捕获 → **什么都没发却报 unknown** | 拆成 `_bind_power` / `_bind_device_action` 两条显式绑定 |
| L2 | 非 power 动词转发**属性名**，而 API 按**动作键**查表 | `set_brightness` 等永远 400 → 同样被记成 unknown | 转发 `verb`，属性名由 web API 自己查表 |
| L3 | `_bind` 的 power 分支丢掉 `binding_revision` | 换绑 409 守卫对 power 从不生效 | power 走 `extension_control_preflight` 拿修订；参数化动作走 `extension_device_target` |
| L4 | `_parse_verb` 在派发 try 内 | 非法取值被记成 **unknown**（像是已经动过设备） | 取值解析移到派发之前，非法取值落 `failed/not_committed` |
| L5 | `together.room.members` 用 `room in set(...)` 判断 detached | `RoomSession` 是**不可哈希** dataclass → `TypeError` 被吞成 `together_read_failed`，动作完全不可用 | 改为按 `is` 身份遍历列表 |
| L6 | `together_command` 用解析前的 `mode` 拼用户可见标签，用 `ticket.mode` 拼链接 | 能力在 `await` 期间消失时，用户被告知"工作协同"但链接是 `call` | 标签统一取 `ticket.mode` |
| L7 | 新增动作回显内部 `scope_key` | 内部上下文桶标识进入模型可见结果 | 从 `together.room.members` 结果移除 |
| L8 | 换绑守卫**恒定不触发**：提供方在派发前立刻读修订再与自己比较 | "换绑后旧引用失效"这条判据从原生动作面永远无法成立（F15 首次执行即失败） | 新增可选 `expect_revision`：调用方钉住准备时的修订，派发前比对，不一致即 `reality_device_binding_rebound` 且不触达设备 |

## 5. 验证结果（本机实测）

| 检查 | 结果 |
| --- | --- |
| 本体合同 `tests/test_reality_together_native.py` | **14 passed**（基线 11） |
| 隔离层夹具 `tests/test_w1_fixture_harness.py` | **13 passed**（见 §5b） |
| Reality 新动作面 `tests/test_native_provider_actions.py` | **16 passed** |
| Reality 全量 `tests/`（除下述无法收集项） | **134 passed, 1 failed**（失败为既有） |
| Together 全量 `tests/` | **227 passed, 3 failed**（3 项均为既有，见 §6） |
| 相邻原生链 `test_native_content_flow` / `test_native_screen_flow` / `test_native_image_flow` / `test_live_native_provider` | **42 passed** |
| 陪伴小屋页面 `node --check app.js` | 通过 |
| 页面合同 `test_reply_page` / `test_expression_page` / `test_models_page` / `test_semantic_page` / `test_native_perception_page` | **6 / 4 / 24 / 4 / 1 全通过，0 失败** |
| `tools/sync_framework_page.py --check`（71 项哈希） | `{"changed": []}` |
| `python -m compileall -q companion_v2 astrbot_host` | 通过 |
| 两个提供方 `py_compile` | 通过 |

复跑命令（AstrBot 自带 Python）：

```powershell
# 本体合同
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_reality_together_native

# Reality 提供方（注意 plugins 目录与 tests 目录都要在 PYTHONPATH）
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m pytest 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/tests' -q --ignore='C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_reality_companion/tests/test_legacy_migration.py'

# Together 提供方（tests 目录与插件根都要在 PYTHONPATH，astrbot_stubs 与 scripts 才可导入）
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/tests;C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m pytest 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_together_companion/tests' -q
```

## 5b. 隔离层夹具（S6 §6 的 W1-F01--18）

`tests/test_w1_fixture_harness.py` 把 S6 §6 的 **18 个定位符逐条登记**，每条给出规格、状态与理由，然后对**当前行为确实存在**的那些按规格执行：固定原输入、初始领域快照、授权修订、**可控时钟**（`ControlledClock` 同时补 `time.time` 与提供方模块内的 `time`）与注入点（`FakeReality.targets` 的别名→修订映射即换绑注入点）。

| 状态 | 夹具 | 验证了什么 |
| --- | --- | --- |
| **已实现（7）** | W1-F03 | 到期即终态：迟到的加入被拒、`stage=expired`、无成员被接纳、受众修订不动；已接纳的决定在到期后**不被撤销** |
| | W1-F04 | 换代后原调用按原身份回放，不虚增第二份邀请；独立新请求保留独立身份 |
| | W1-F05 | 拒接是**独立事实**：只结束该邀请，不结束房间、不牵连另一成员的活动 |
| | W1-F07 | 缺身份票据被拒且 `rooms` 为空；重放不建第二成员；不同人仍可被同一邀请接纳 |
| | W1-F08 | 受众修订每接纳一个**新的不同身份** +1；成员视图只报身份事实，`prompt`/`ticket`/`token`/`scope_key` 零泄漏 |
| | W1-F15 | 换绑令钉住旧修订的引用失效；撤权拒绝且**不新建操作行**；未知结果保留原 operation 且**不重试** |
| | W1-F17 | 结束是终态：只释放本场房间，另一成员的房间与其约定不动，旧回调无法重开 |
| **阻塞（11）** | W1-F01/F02/F06/F09/F10/F11/F12/F13/F14/F16/F18 | 每条都写明缺的是什么能力（样本序列与覆盖缺口、分页游标绑修订、Reality 回拨实体、逐端点分桶、逐端点覆盖区间、输入修订实体、已播范围账、原生播放确认账、Calendar 归属、持久 Repository 与控制代 CAS、队列水位观测点） |

**阻塞项按 S6 §8.3 的口径登记为未运行，不计入通过数。** 最后一项 `test_blocked_fixtures_are_registered_and_not_counted_as_passing` 把 7/11 的划分钉死：将来某片把某个定位符从阻塞挪到实现，必须显式改这条断言，而不是悄悄继承一个"已通过"的说法。

### 夹具打出来的一处真实缺口

F15 首次执行时**失败**，因为提供方在派发前**立刻**读取绑定修订再与它自己比较，等于恒定相等——"换绑后旧引用失效"从原生动作面**永远无法触发**。已补 `reality.device.action` 的可选 `expect_revision`：调用方钉住它准备动作时的修订，派发前比对，不一致即 `reality_device_binding_rebound` 并且**不触达设备**。F15 因此从"写了但不会成立"变成真正成立。

## 6. 既有失败（**非本次引入，未修**）

已逐项定性，证据为"改动前后同样失败"以及"把新代码路径替换成必炸的探针后失败形态不变（探针 0 次命中）"：

| 失败项 | 定性 | 证据 |
| --- | --- | --- |
| Reality `test_plugin_boundary.py::test_private_companion_uses_optional_bridge_instead_of_device_mixin` | 既有，与本批无关 | 断言 V1 插件桥 facade 文本，不涉本批文件 |
| Reality `test_legacy_migration.py`（**无法收集**） | 既有，第三方损坏 | 它 `import astrbot_plugin_private_companion.main`，而该 V1 文件 `main.py:20517` 被写成字面量 `` `n `` 而非换行 → `SyntaxError`。**不是本批造成**（另一会话正在改该文件），按 AGENTS.md 不得读取/迁移 V1 数据，故不代修 |
| Together `test_call_hangup.py::…test_action_marker_never_enters_history_or_tts` | 既有，与 mode/身份无关 | 测试替身 `lambda **_kwargs` 与生产 `_conversation_log_models(room, *, has_image)` 签名不符 → `TypeError`，在 `_reply_to_user` 第 3 句即炸，未触及票据逻辑 |
| Together `test_launcher.py::…test_connected_room_can_issue_fresh_invite_ticket` | 既有 | 期望字典少一个 `'native_v2': None` 键；该键由 `create_invite` 的 V2 绑定接线产生，且被**通过中的** `test_native_room_isolation.py::test_invite_ticket_inherits_native_binding` 依赖。mode 两处都是 `call`，未涉 mode 解析 |
| Together `test_work_collaboration.py::…test_web_room_and_launcher_hide_work_until_capability_is_available` | 既有 | 断言 `web/app.js` 里 `["call", "watch", "work"].includes(mode)` 字面量；实际已是 `["watch", "call", "work", "novel"]`（novel 模式前端改造时漂移）。同测试另 11 条断言全部匹配 |

**这 5 项需要另行安排修复，不应被当作本批的通过数。**

## 7. 仍未验证的部分（不得当作已通过）

按设计稿 §8.3 与验收清单口径，以下**全部仍是「待测」**：

- **真机层**：真实米家设备、真实房间服务器、真实 TTS/STT、真实 QQ。E09（房间）、E10（完整活动）、E11（设备读）、E12（设备控制）**没有一行现场结论**。
- **`confirmed` 的语义边界**：它是米家**云端 code-0 回执**，不是设备状态回读（`mihome_client.py:444-471`）。V2 据此记 `effect: "committed"`。"云端已受理"不等于"设备已执行"，E12 现场验收时必须按这个层级核对。
- **隔离适配层**：S6 §6 的 18 份夹具**已登记并做了 7 份**（见 §5b）；其余 11 份因缺少对应能力（样本序列/游标、逐端点覆盖、已播范围账、输入修订、持久 Repository 与控制代 CAS、Reality 回拨实体等）**仍为未运行**，不计入通过数。
- **S3 邀请/加入/成员修订（Together 侧）已完成**：邀请签发/列出/加入、跨 scope 解析、同人重放去重、受众修订 `member_revision`，见 §2b。
- **未实现的设计要求**：RV-1 的四类范围与来源目录（S2）、RV-2 领域历史、RI-2 自主观察与独立音响、**RI-3 的 Reality 发起侧**（来电/拒接/回拨——Together 侧只做了"接收合法加入"，Reality 侧尚无邀请实体）、TG-2 逐端点媒体覆盖、TG-3 已播范围账、TG-4 非空重启与控制代 CAS。**"邀请 owner 放 Reality"这一归属仍未落地**：本轮把邀请放在 Together 是因为加入的目标房间由 Together 持有；若按设计稿把 owner 移到 Reality，需要把本轮的 `InvitationStore` 迁成 Reality 签发、Together 只做合法性核对。
- **受邀者同房连接已在 2026-10-01 补齐**：Reality 手机网关现在把 V2 `together.room.join` 返回的成员 URL 改写到统一网关；Together WebSocket 会校验成员票据并挂到既有 `RoomSession`。成员有独立恢复令牌，房主身份不复制，摄像头帧按成员隔离。原先“尚未真正入房”的结论只代表 2026-09-27 的历史快照，当前口径以 `REALITY_TOGETHER_V2_COMPOSITION_20261001.md` 和 `V1_V2_TOGETHER_MOBILE_COMPARISON_20261001.md` 为准。
- **既有缺陷仍未修**：B0b（Screen 拒权记 unknown）、B0c（work 静默降级——已改为在**签发时**诚实解析并在标签上取 `ticket.mode`，但回执字段层面的完整处理随 S3 继续）、B0d（账本损坏连带关闭整家原生能力）、B8（目录多返回 `more_devices`/`cache_updated_at`/`logged_in`）。
- **交付包状态已在 2026-10-01 更新**：当前源码已构建最终完整 8 包套件，输出目录为 `D:\codex\workspaces\companion-v2-mobile-together-20261001-final`，并在 `D:\codex\workspaces\companion-v2-mobile-together-20261001-final-extracted-page-sync` 完成解包清单、哈希、CRC、UTF-8/Python 语法、唯一公开页和 AstrBot 宿主启动/停机/路由注销验收；手机 Together 合同 **6/6**、Reality/Together 原生合同 **14/14** 均从最终解包包验证通过。该结果替代本段原先的“未构建交付包、未统一测试”状态，但仍不代表在线插件已重载或真实 Android、HTTPS/WebSocket 公网房间服务器、QQ、TTS/STT、摄像头/麦克风、米家设备已经现场验收；合成包测试也不能替代这些现场验证。

## 8. 结论

两项拓展的**原生动作面已可用并被合同层验证**：Reality 从"读一次快照 + 开关一个设备"扩到 7 个动作（含可查询的操作账与可取消的未派发操作），Together 从"建房/查房/关房"扩到 4 个动作并修掉了身份回退这一安全缺口。落地过程中被打出的 7 个实现缺陷（§4）全部已修并有回归覆盖。

**但"可用"仅限合成夹具与合同层。** 真实设备、真实通话、真实 QQ 的效果一行未验；设计稿的 RV/RI/TG 后段（历史、覆盖、邀请、恢复）仍未开工。按设计稿口径：**文字夹具通过不能代替真实通话**。
