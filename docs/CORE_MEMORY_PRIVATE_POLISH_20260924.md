# 私聊记忆完善切片（2026-09-24）

承接 [V1 专项对照](CORE_MEMORY_V1_PARITY_AUDIT_20260923.md)，本轮补齐常驻核心记忆、已确认 Bot 回复的记忆来源、凭据脱敏，以及私聊事实库的历史查看和批量治理。改动已从隔离副本合入 V2，保留其他窗口增加的只读查询 wire 和角色成长上下文；未读取 V1 用户数据、执行线上重载、调用真实模型或发送平台消息。

## 常驻核心记忆

事实新增 `context_mode=relevant|pinned`，默认 `relevant`。它与 `retention` 分离：置顶决定是否优先进入每轮上下文，保留策略决定存续与治理。`protected` 不会自动变成置顶，取消置顶也不会删掉事实。

- 提示词引导原角色仅将用户明确要求持续遵守的称呼、边界、置顶内容标为 `pinned`，不按关键词自动提升。
- 每轮先读取有权限、有有效原始证据的置顶事实，再补充话题召回；检索索引失败时保留可用的置顶块和本轮来源 handle。
- 相同事实去重，核心块有独立条数和字符预算。所有事实材料受最终注入字符预算限制；被省略时提供覆盖范围提示。
- 写入或纠正置顶事实后，更新本轮权威快照并由工具续答验证器复核。仅收到真实写入回执后才能替换本轮材料；外部纠正、来源撤回仍会使旧快照失效。

| 统一配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `memory.core_items` | 4 | 每轮核心事实最多条数 |
| `memory.core_chars` | 6000 | 核心事实序列化正文字符预算 |
| `memory.context_items` / `context_chars` | 4 / 6000 | 初始话题召回预算 |
| `memory.inclusion_chars` | 24000 | 核心、话题及本轮写回事实的合计注入字符预算 |

这里限制的是 Memory 事实材料，不是整份模型提示的 token 数；人格、其他领域材料、覆盖说明及 handle 元数据由各自合同管理。全部字段通过既有统一配置服务读取，无第二份设置。

## Bot 回复作为有归因的来源

`ConfirmedReplySources` 只从 `conversation_sent_history` 中带有匹配 `delivered` 回执的文本登记 `conversation.confirmed_reply` 来源。登记复核原始 part、操作、发送方、内容哈希、目标上下文和平台回执；`accepted`、`unknown`、`failed` 或未发送草稿均无该入口。

读取时重新验证当前可信用户、Bot、角色、原入站消息、上下文材料及工具依赖。记忆工具的依赖由同一个工具 owner 验证；原查询会话过期后只读取既存 handle 与原证据，不延长会话、不重置预算。工具本轮已经更正而被标为 superseded 的旧结果不重新作为依赖。

来源可供原文查询和反思选材，`source_kind=bot_message` 与角色 speaker 明确保留。Bot 的话只证明当时说过，不能作为用户自述或实际完成的证明。原消息撤回、事实被更正/遗忘或证据不可用时，依赖它的引用与事实不能继续使用。

来源登记发生在选材阶段。后续事实读取、后台任务授权和模型调用前检查只读验证，避免在数据库只读快照中尝试建来源；这也修复了每日反思卡在 `running` 的回归。

## 脱敏边界

共享来源层在 AstrBot 入站发布前清洗常见凭据、Bearer、私钥和带密码的连接地址。原文片段偏移基于清洗后的内容；若发生替换，用安装级随机密钥计算原输入的 HMAC 指纹，以保持“同一事件、不同凭据”仍构成重放冲突。

记忆提案、记忆修订、管理更正、经历正文/标签/关系文本和反思的已解析输出采用同一清洗。Bot 回复进入记忆来源时清洗，不修改已经发送的平台原文。测试使用合成凭据，覆盖中文紧邻 token、JSON 引号/数值、重复清洗及清洗前不同输入的冲突。

这是新增写入链上的常见凭据处理，不宣称通用个人信息识别或已清洗所有历史存储、媒体元数据、模型服务和宿主日志。旧 V2 数据的专项清洗及 V1 数据迁移应另行预览与验收。

## 事实库治理

Dashboard 已有 `/astrbot_plugin_private_companion_v2/memory` 前缀，新增：

| 路由 | 行为 |
| --- | --- |
| `POST /command` 的 `pin` / `unpin` | 带当前 revision、view token 与幂等键置顶/取消置顶 |
| `GET /revisions?atom_id=...` | 按修订号分页；旧值仍需当前证据授权，已遗忘或来源撤回的正文不可读 |
| `GET /clear/preview` | 返回当前宿主选定的私聊关系事实范围、数量与版本 token |
| `POST /clear` | 携带 `expected_revision_token`、`operation_key`，原子遗忘该范围的事实及全部修订 |

操作者来自 Dashboard 登录身份，记忆主体来自既有受信宿主目标；请求不能自行指定用户、角色或群。预览 token 绑定关系、操作者、权限版本和事实版本。空清理也保存回执，重复执行先返回原回执，不会用过期预览误删后来新记忆。

单条和批量遗忘复用 Writer 的同一条治理链：复核 protected 权限、清除事实与历史修订正文、保留墓碑和操作回执、阻止旧证据再学习、撤销派生来源。它是逻辑遗忘，不承诺擦除外部日志和备份。

搜索投影新增分区归属映射，清理时只删除该私聊关系的词项/向量。旧缓存没有归属映射时一次性重建，权威数据库无新增迁移。缓存清理失败不会回滚已经提交的遗忘；回执会提示 `search_projection=cleanup_pending`，重试原操作可再次清理。

批量范围明确为 `private_relationship_facts_and_revisions`，不是全安装“忘记我”：独立经历、原会话历史、未关联提案及日记、关系解释等其他 owner 仍需各自的治理入口。完整事实管理页面仍待统一页面路线接入。

## 验证与剩余边界

最终主树定向回归 **115 项通过**。使用 AstrBot 自带 Python；涉及 SDK 的进程设置 `PYTHONPATH=backend/app`，导入和测试数据由临时根隔离。覆盖置顶及预算、原角色写入/纠正/续答、Bot 回复来源与过期会话、来源撤回、脱敏、批量 CAS/重试、历史授权、缓存清理失败、每日反思、Dashboard 认证与路由、原查询 wire、入站与宿主生命周期。

运行模块为 `test_memory_polish`、`test_memory_writer`、`test_memory_management`、`test_memory_query`、`test_memory_conversation`、`test_memory_experiences`、`test_memory_reflection`、`test_memory_boundaries`、`test_memory_host_api`、`test_memory_wire`、`test_role_tool_loop`、`test_astrbot_inbound_adapter`、`test_source_repositories`、`test_host_application`。该数字是此批主树快照的受影响回归数量，不是全框架、V1 全功能对等或线上语义质量验收。

下一阶段仍包括自动 Embedding provider、重排/去重复、有界增量索引、群聊及多领域适配、全主体治理汇总、导入导出/归档恢复，以及真实模型语义质量验收。本轮不将这些未完成部分计为已迁移。
