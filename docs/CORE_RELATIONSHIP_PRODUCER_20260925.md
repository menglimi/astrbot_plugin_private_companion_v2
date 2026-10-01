# 真实私聊关系与情绪提案原生链

2026-09-25。本批补齐「私聊原始材料 → 当前角色提案 → 既有人类审阅／采用 → 后续关系上下文」；同时支持同一原生私聊路线重置 conversation/session 后继续读取有依据的关系记录。未接入 V1 用户数据。

## 运行行为

- `companion_v2/relationships/tools.py` 提供 `RelationshipTools(service, messages)`，公开动作只有 `relationship.memory.propose`。角色提交 `kind`、`interpretation`、`evidence_handles`；情绪片段还须声明 `emotion_subject=role|human`。主体、人格、受众、时间、版本及采用状态均由宿主和领域服务确定。
- `tool_sources.py` 从已封存的 `conversation_inputs` 和宿主登记的 `conversation_tool_sources` 提供本轮句柄。`relationship-input-1` 等句柄指向原入站资料，`relationship-source:<handle>` 指向宿主实际提供的原件；模型不能提交裸 `SourceRef`、账号或作用域。未封存的批次不会伪造输入句柄。
- 提案记录始终从 `proposed` 第 1 版开始，保留具体情绪归属与真实来源。模型工具不能审阅、采用、修订或撤回管理记录，也不将新提案即时注入已封存的关系背景。
- 既有 `RelationshipMemoryManagement` 及 Dashboard API 承担人类审阅、采用、修订和撤回；审阅人与采用人保存实际管理员主体。采用之后，下一次对话才通过 `RelationshipContext` 消费。关系理解保持主观材料，不成为可支持客观事实断言的独立证据。
- 提示词引导角色在具体互动带来值得延续的理解时提案，区分用户事实、角色感受与对他人的不确定判断，不逐条记录寒暄，不评分或自动提升关系。

## 回执与失效

`PersistentRelationshipMemoryLedger.propose` 在同一事务保存提案、第一版历史和操作回执，复用既有表，无新 schema。操作标识绑定原 context/batch/call；同一请求重放只返回首次提交结果，不修改原时间。内容冲突拒绝写入。

`applied_revision`、`applied_state` 是提交当时的回执。人类之后采用、修订或撤回，不改写这份回执，也不能通过重放恢复旧内容。工具读取回执时核对原作用域、角色／主体、请求内容、所用句柄、源版本及当前授权；来源撤回或过期会阻止相关待发内容继续投递。

沿用本轮工具调用的持久化 `started/unknown` 屏障。原调用结果未知时不再次执行；同批次换调用 ID 也不能继续提交关系提案来规避未知状态。已确认回复的来源依赖由 `memory/sent_sources.py` 接入，原证据撤回后相关历史正文不可继续使用。

## 重置会话的连续性

`provenance.py` 的 `same_private_route` 保留 installation、platform、bot、account、native_scope_id 与 private 类型，只允许 conversation/session 变化。记录仍归属同一个已认证 human 与同一个 V2 role；不会按昵称共享，也没有扩大到群聊或另一个原生私聊地址。

读取与管理列表可按这条稳定路线查询旧记录，且在分页前过滤。每条原记录与每个来源继续保留原始 scope，分别核查原路由当前映射的人物和角色、原来源受众／版本／撤回／有效期；跨 scope 还检查原 scope 的 `relationship.memory.read` 授权。新会话授权不能替代已撤销的旧会话授权。

管理页面无需增加入口即可在重置后的当前私聊下审阅旧提案。管理操作仍记录当前操作的 scope，而证据 `SourceRef.scope` 保持原值。原来源失效时遮蔽正文，允许有实际管理员归属的撤回。

## 公共装配与权限

统筹在 `conversation/tool_loop.py` 注册本工具的 catalog、来源材料、提示词、执行、回执复核与 mutation 分类；`host/application.py` 显式传入现有 `relationship_memories`；`memory/sent_sources.py` 收集其确认回复依赖。群聊不获得此私聊工具。

多目标配置需要显式包含 `relationship.memory.read` 和 `relationship.memory.propose`，再沿既有 profile 初始化／授权流程应用。单目标 pinned profile 同样需要这两项权限。**默认 capability 集合保持原值**，不因升级改变既有 manifest 指纹或扩权；运行配置和被撤销的 grant 不会被本批改写或恢复。只有提案权限而没有读取权限时，不提供此角色工具。

## 定向验证

最终 **65 项通过**：新增 19 项，以及既有关系 service、storage、context、management 和 SDK 管理 API 回归。

| 范围 | 证据 |
| --- | --- |
| 模型工具与宿主闭环 | `tests/test_relationship_producer.py`：12 项；包括真实 host intake、模型工具续答、人工审阅采用、跨重置消费、确认回复来源传播、重复／冲突回执、伪造参数、情绪归属、权限撤回、重启与未知结果不重放。 |
| 原作用域连续性 | `tests/test_relationship_continuity.py`：5 项；原来源不改写、旧授权撤销、旧人格改变、源撤回、不同人物／路线／群聊隔离。 |
| 原生 MultiSession | `tests/test_relationship_producer_native.py`：2 项；显式 capability，`receive_claimed` → 原生工具 alias → V2 执行 → synthetic provider 续答 → 合成 OneBot ACK → Dashboard 管理身份审阅／采用 → 原生 conversation reset → 后续模型消费和 ACK；同时确认没有权限的旧配置不出现工具。 |

环境为 `C:/Users/99505/.astrbot/backend/python/python.exe -X utf8`；仅测试进程设置 `PYTHONPATH` 包含 V2 工程与 `C:/Users/99505/.astrbot/backend/app`，SDK 导入前将 `ASTRBOT_ROOT` 指向 `TemporaryDirectory`。使用独立 V2 数据库、合成人物／平台／模型和本地 ACK，未调用真实模型或 QQ，未重载在线插件。

复验模块：

```text
tests.test_relationship_producer
tests.test_relationship_continuity
tests.test_relationship_producer_native
tests.test_relationship_memory_service
tests.test_relationship_memory_storage
tests.test_relationship_context
tests.test_relationship_management
tests.test_relationship_management_host
```

## 边界与后续

本批完成当前角色在实际对话中的提案生产与消费，不新增后台情绪抽取、数值好感、长期余韵引擎或跨账号身份合并。现场模型是否能适度提案仍需内容质量验收；未以合成模型通过证明真实表达质量。后续可在此链上补针对具体互动的提案质量样本。同批[群聊旁听与选择性参与](CORE_GROUP_PARTICIPATION_20260925.md)也已接通，剩余缺口按总审计继续推进。
