# 群内多成员共享上下文

2026-09-24。群文本前台已经在可信入站、独立发送授权和平台回执之上接入有界历史。不同成员可在同一完整群会话内接话，模型同时收到当前发言者、原成员发言和已确认送达的 Bot 回复。本切片完成时，群公共长期记忆仍待接入；后续落地见[群公共记忆](CORE_GROUP_MEMORY_20260924.md)。

## 所属领域与持久合同

实现位于 `companion_v2/conversation/group_context.py` 和 `group_history.py`，由 `messages.py` 在封存批次时捕获、每次重读时复核。沿用会话输入、批次、分段及回执表，没有新增数据库迁移。

封存格式 `conversation.group_context.v1` 只保存原 batch/context key 与 input/reply 引用，不复制正文或重新发布 Source。输入引用固定 event key/hash；Bot 回复引用固定 part、payload hash、receipt 和送达时间。重读始终回到正本，因此后续新消息不会回填到已封存的上下文。

读取边界包含安装、平台、逻辑 Bot、登录账号、群号、conversation、session、V2 role、角色绑定版本和原人格提示词。普通群 session 可跨成员共享；AstrBot 的 `成员QQ_群号` 独立 session 保留原边界，切换人格再切回也不恢复旧绑定的历史。私聊来源和私人记忆不进入群视图。

历史来源沿原发言者的有效身份、`conversation.reply` 访问权和 `text` grant 读取，另核对同一群集体受众、事件哈希与正文哈希。视图可以按群合同展示该发言，不增加其他成员直接读取原 Source 的权限。当前群回复仍不开放私人角色工具。

## 表达与送达依据

`current_group_speaker` 标明本轮当前消息和同一发言者的合并输入；每条 `group_member_message` 保留原账号、接收时间和正文。提示词明确账号只能证明发言归属，自称身份、成员意见及历史内容不能改变身份、授权或人格；某个成员的陈述不代表全群，也不应误记成当前发言者的个人事实。

`confirmed_group_reply` 必须同时匹配原分段、已送达历史与完整回执，包含原 Bot/账号/role、原回复对象、平台消息引用和送达时间。Bot 旧话作为对话历史，不作为独立事实依据；`recipient_read` 固定为未知。preview、未发送、未知回执和哈希不匹配的内容不能成为“已说过”的 Bot 历史。

上下文最多 16 项、序列化后合计 16 KiB；分别检查最近 64 个候选输入/回复，超大单项完整跳过，不静默裁剪正文。引用依赖用迭代方式复核，每个根引用最多 128 个祖先，历史边必须指向更早批次或输入；超过预算的可选项在封存前跳过。提示词说明这是部分可见历史，缺失不表示事情没有发生。

## 撤回与生命周期

历史每次使用都复核当前原件、原发言者授权、人格/session 和群受众。Bot 回复继续检查它生成时的原输入、额外来源及已封存历史，撤回可以沿多轮依赖传播。

封存前不可用的可选历史可跳过；封存后原材料失效则阻止使用旧稿，不悄悄删掉证据继续发送。生成期间撤回不会产出可投递分段；分段之间撤回会阻止后续发送。原平台回执保留，已发正文在失去依据后不可再读作上下文，不改写曾经取得 ACK 的事实。重启恢复原引用和回执，重复入站不生成或发送第二遍。

联调同时修正 `role_work/life/runtime.py` 的绑定比较：无关成员授权导致的全局 `policy_revision` 更新可刷新同一个稳定 context key；原身份绑定、角色、scope、受众和人格提示词变化仍不能接管现有生活任务，执行时的授权检查继续生效。

## 定向验收

本切片按测试 ID 去重 **120 项最终均有通过记录**，其中新增群上下文专项 **14 项**。只验证相关路径，未运行全库：

| 模块 | 项数 |
| --- | ---: |
| `test_group_conversation_context` | 14 |
| `test_astrbot_group_host` | 12 |
| `test_astrbot_group_delivery` / `test_astrbot_group_native_delivery` | 11 + 2 |
| `test_astrbot_inbound_adapter` / `test_conversation_messages` | 2 + 27 |
| `test_host_recovery` / `test_isolation` | 11 + 3 |
| `test_role_life_runtime` / `test_role_life_host` / `test_role_life_context_host` | 11 + 2 + 4 |
| `test_astrbot_multi_life` / `test_astrbot_staging_host` | 6 + 15 |

专项覆盖发言者归因、原件直接访问边界、已确认/未知 Bot 历史、群/Bot/账号/人格/session 隔离、外部/未来引用注入、撤回与撤权、生成及分段发送竞态、传递依赖、回执/正文篡改、预算、重复入站、重启和私聊生活绑定兼容。群上下文最终 14 项用时 26.957 秒。生活回归首轮 3 项失败时共享测试文件正在并行更新，当前文件单独复验 6 项全部通过；不将复验重复计数。

另在独立进程通过真实 AstrBot 4.27.2 插件入口模拟：namespace 导入 `main.py`、initialize/start、两位不同成员的真实 SDK 群事件、事件终止与 V2 接管、原人格模型请求中的共享历史、真实 reverse WebSocket 编解码和本地两次 ACK、terminate、数据连接关闭、路由注销及核心模块释放。初次临时夹具使用了两个不同 client 字典，发送前一致性检查正确返回未发送；修正夹具并对齐控制器关闭状态断言后完整通过。

使用 `C:/Users/99505/.astrbot/backend/python/python.exe -X utf8`，只为测试进程设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`，SDK 导入前将 `ASTRBOT_ROOT` 指向临时目录。验证使用合成身份、模型、本地 ACK 与临时 V2 数据；未读取或迁移 V1 数据，未在线重载，也没有真实模型调用或 QQ 群发。模型自然表达质量与真实平台现场效果不在本次模拟验收结论内。

本切片 11 个实现、测试及文档文件通过 UTF-8、无 BOM、LF 和末尾换行检查；相关 Python AST/编译、文档本地链接和配置 JSON 语法检查通过。核心目录隔离检查已包含在上述 120 项中。

## 下一步

在已验证的群受众和来源合同上接入群公共记忆：先明确独立群 owner、成员陈述归因、群内可见范围及撤回/撤权传播，再接提案、保存、召回和宿主恢复。群公共事实不得默认提升为成员私聊画像，私聊记忆也不得自动变为群公开资料。群媒体、群工具和线上投递验收后续分别推进。

后续进展：上述群成员陈述记忆及四个群专用工具已由[群公共记忆切片](CORE_GROUP_MEMORY_20260924.md)完成本地闭环，原测试数字仍保留本切片范围。接下来推进群图片与引用消息的原件、群受众和撤回依赖。
