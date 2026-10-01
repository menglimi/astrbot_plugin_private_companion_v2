# 群公共记忆与原角色工具闭环

2026-09-24。群前台在[多成员共享上下文](CORE_GROUP_CONTEXT_20260924.md)之上接入持久成员陈述：本轮发言可以保存、查询、由本人修订或撤回，原角色依据实际工具回执继续回复；后续成员能召回同群记忆，并保留原发言者归因。当前实现是有来源的成员陈述，不将单人说法认定为全群共识。

## 所属领域与接线

业务放在 `companion_v2/memory/group/`：`access.py` 核验群身份与原输入，`service.py` 负责正本、版本及原子操作回执，`context.py` 管理引用快照和同轮更新证明，`tools.py` 提供群专用查询与变更工具。

`conversation/messages.py` 在封存时保存群记忆引用；`conversation/tool_loop.py` 按场景提供工具并复核回执、来源和续答材料。`conversation/group_history.py` 追踪已确认 Bot 回复的群记忆依赖。`astrbot_host/group_authority.py` 在可信群入站时建立独立的 `group.memory.read` / `group.memory.write` 权限，已撤销的可选记忆权限不因再次入站而恢复，也不阻断普通聊天。

复用统一事务、Source/依赖治理、公共操作和现有 `memory_views`、`memory_operations`、`memory_guards`；记录种类为 `group.public.statement.v1`，操作归属为 `memory.group`。本切片不新增 SQL 表或 schema 升级，也不改变私人事实正本和私聊工具集合。

## 归属、受众与来源

长期 owner 包含安装、平台、逻辑 Bot、登录账号、群号、原生 session 和 V2 role，不含单个成员、conversation ID 或角色绑定 revision。因此同群共享 session 可跨成员、跨 conversation 重置召回；原生 `成员QQ_群号` 独立 session 继续隔离。不同群、Bot、账号或角色不能互读；切回原角色可读取仍有效的原记忆，读取仍复核原发言者与当前角色归属。

每条记忆固定 `speaker_id`、`attribution=member_statement` 和 `visibility=group`。群受众视图可展示某位成员的陈述，不给其他成员直接读取该成员原 Source 的权限；群陈述不进入私聊画像，私聊记忆及私人角色资料不进入群上下文。

写入只接受本轮已封存、由当前本人发送的纯文本 `group-input-N` 句柄。服务重读原事件、正文及哈希，核对原身份、群受众、角色及原 `text` / `group.memory.write` 权限；不能通过工具参数指定其他作者、任意 Source 或其他批次证据。图片、引用、转发和音频尚不作为本切片的群记忆输入。

提示词要求保留原说法、时间和不确定性；仅在有持续价值或成员明确希望保留时保存，所选原话须独立支持记忆。指代不清或必须借用其他成员旧说法时先澄清；相反观点分别归因，不提升为群共识，不自动认定为已核实事实。

## 工具、版本与更新

| 工具 | 行为 |
| --- | --- |
| `group.memory.query` | 按文字线索分页查询本群当前角色记忆，返回原发言者、版本及续页游标 |
| `group.memory.remember` | 根据本轮本人输入保存陈述；提供 `memory_id` 和 `expected_revision` 时修订本人原记录 |
| `group.memory.retract` | 根据本人当前请求撤回本人精确版本，不删除平台消息 |
| `group.memory.operation` | 查询本人原操作回执，不能读取其他成员操作 |

写入固定作者并检查当前版本；记录、派生来源、依赖、回执与本轮快照更新共用事务。相同调用 ID 和相同参数重读原回执，不同参数返回冲突；失败回滚，不留下半条记忆。撤回保留回执，停止继续使用原记录，并阻止换调用 ID 重用被撤回的同一原文恢复记录。

封存快照只保存 ID/revision，默认最近 4 项、16 KiB，最多检查 32 个候选。查询每页最多扫描 64 条，最多返回 16 项、24,000 字节；有界覆盖明确标记为 partial，并提供游标，未显示不代表不存在。单条陈述最多 1024 字符。

本轮成功修订或撤回后，只有实际写回执涉及的旧记忆及依赖它的 Bot 历史可从当前材料中移除，其他封存材料保持；旧查询或保存结果被后续本轮操作取代时标为 superseded。新文本通过重验后的工具结果参与续答，不能把材料任意变化解释成正常刷新。

## 撤回、撤权与恢复

读取、模型续答和发送前持续重验来源与授权。原消息撤回、原作者写权限撤销或当前读权限失效后，相关记忆不能继续召回；依赖该记忆的 Bot 历史也停止使用，已有发送回执保留。生成期间来源失效会阻断发送，本地保存成功不等于回复已送达。

重启恢复原记忆、版本和操作回执；重复入站不重复保存，未知投递不自动重发。不同成员的确认 Bot 历史仍遵守原群上下文、人格绑定及投递回执合同。

## 定向验收

按测试 ID 去重 **159 项最终均有通过记录**，其中新增群记忆专项 **16 项**。只验证受影响路径，未运行全库：

| 模块 | 项数 |
| --- | ---: |
| `test_group_memory` | 16 |
| `test_group_conversation_context` | 14 |
| `test_astrbot_group_host` | 12 |
| `test_astrbot_group_delivery` / `test_astrbot_group_native_delivery` | 11 + 2 |
| `test_memory_conversation` / `test_memory_boundaries` | 5 + 10 |
| `test_role_tool_loop` / `test_conversation_messages` | 21 + 27 |
| `test_astrbot_multi_host` / `test_astrbot_staging_host` | 12 + 15 |
| `test_host_recovery` / `test_isolation` | 11 + 3 |

专项覆盖跨成员归因、原 Source 访问边界、群/Bot/角色/session 隔离、conversation 重置召回、仅作者修改、同轮修订续答、查询分页及冻结、模型证据引用、撤回和撤权、重启和重复入站、未知不重放、伪造句柄/身份/回执、操作幂等、原文撤回保护、事务回滚及正文预算。

群既有回归 39 项通过，公共与私聊回归首轮 104 项中 94 项通过、10 项多目标宿主初始化失败。当时共享工作树的 `native.py` 已引用音频模块而该目录尚未落盘，独立入口复现 `ModuleNotFoundError: astrbot_host.audio`。依赖齐备后群记忆与多目标宿主合计 28 项全部通过，用时 34.725 秒；不重复累计。纯文本兼容边界收尾后群记忆与共享上下文 **30 项复验通过**，用时 44.867 秒。

另通过[独立进程 SDK 验证脚本](../tests/group_memory_entry_process.py)：真实 AstrBot 4.27.2 插件 namespace 导入、初始化/启动、两位成员的真实 SDK 群事件、群记忆工具保存、带原发言者归因和证据的模型召回、reverse WebSocket 本地两次 ACK、终止、数据库关闭、路由注销与核心模块释放。脚本核对只有群记忆记录、私人事实表为空。

使用 `C:/Users/99505/.astrbot/backend/python/python.exe -X utf8`；仅为测试进程设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`，SDK 导入前将 `ASTRBOT_ROOT` 指向临时目录。可在工程根运行 `python -X utf8 -m tests.group_memory_entry_process` 复验独立入口。所有身份、模型、原件与 ACK 都为本地合成；没有访问或迁移 V1 数据、在线重载、真实模型调用或 QQ 群发。真实语义表现及平台现场效果仍待验收。

本切片 20 个实现、测试及文档文件通过 UTF-8、无 BOM、LF、末尾换行和尾部空白检查；14 个 Python 文件 AST/编译、208 个本地文档链接及配置 JSON 校验通过。根级 Python 仍仅 `main.py`，隔离扫描包含在上述测试中。

## 下一步

先接群图片与引用消息的输入合同，沿用原件、群受众、原发言者及撤回依赖，把媒体材料接入已验证的群对话链。群记忆管理员治理、自动反思/向量索引、其他群工具与公共跨进程协议分别后续推进；当前闭环不代表这些能力或 V1 完整替换已完成。

后续进展：[群图片与引用消息](CORE_GROUP_MEDIA_20260924.md)已完成原件、群受众、模型证据、工具续答及撤回依赖闭环。群记忆继续只接受本人纯文本陈述；下一段为群合并转发与嵌套节点。
