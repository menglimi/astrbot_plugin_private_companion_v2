# 多目标阅读、睡眠与私人书写

日期：2026-09-24。

多目标宿主已接入阅读、睡眠、日记和梦境管理。每个私人 target/role 使用固定管理路由；启动和已受理的私聊绑定当前原生人格的生活执行器，沿用共享的任务、模型、预算和 V2 数据库。本批复用现有表，没有新增 schema 迁移。

## 管理入口

已登录 Dashboard 后读取 `GET /astrbot_plugin_private_companion_v2/host/status`，使用 `data.targets[].roles[].life_api`。群目标返回 null，不注册私人生活路由。

- `GET {life_api}`：配置、活动及阅读进度、日记/梦境归档、运行任务、回执和下次作息时间；保留 `before`、`after_activity` 分页。
- `POST {life_api}/command`：沿用 `configure`、`add_text`、`read`、`sleep`、`wake`、`cancel`、`withdraw`、`diary`、`dream`、`derive`、`edit`、`delete`、`restore`。

路由在创建时固定 target/role，收到请求体后在宿主控制锁内解析可信上下文；请求体及查询参数不能替换身份、目标或角色。模型工作交给原任务生命周期执行，停止和撤回请求可以继续进入。查询响应增加 `target_id`，`profile_id` 为共享安装的既有 profile 标识。

管理命令沿用 Dashboard 登录、CORE 权限、配置编辑令牌、视图令牌、原记录版本和来源复核。同一个操作 key 可分别在不同上下文使用，回执 ID 包含原上下文。旧版本未分区的配置/操作 ID 仅在原 scope 内保留幂等重试兼容；禁用生活功能只撤销对应主体、scope 的生活授权。

## 当前人格与生活执行

`role_work/life/coordinator.py` 为每个可信上下文保留独立 `RoleLifeRuntime`。`role.life` 配置消费者 generation 由协调器共享，一次宿主生命周期只登记一次，避免多个目标互相替换采用回执。每日书写的注册 ID 包含上下文，各窗口分别使用自己的时区、时间和配置。

读取或配置未选中的角色不会切换 AstrBot 人格，也不会自行启动其模型任务。宿主切换同一私人目标的人格后，旧执行器退出、撤销自己的未来日记排程并取消在途任务，其他目标继续运行。无关授权变化引起的 `policy_revision` 更新不会替换原身份和角色执行器。

A→B→A 切回会取得新的角色绑定版本，旧活动保留历史并显示 `current_context=false`，旧视图令牌失效。当前执行器不能直接接管旧绑定的未完成阅读或睡眠；管理员可在原 scope 内取消历史活动或撤回原文，再按新绑定明确安排活动。

阅读完成必须来自原文片段的实际任务回执。睡眠保存开始时间和到期意图，运行中的可信执行器核验当前人格后报告醒来，再独立记录梦境；普通日程和时间流逝不会被用来证明阅读完成。日记/梦境仍沿用素材语义和原人格提示，正文与衍生提取分开执行。

停止后可读取归档；重载重新绑定当前人格并恢复原配置、未结束睡眠及书写回执。已完成阅读不重读，同一日期已完成书写不重新调用模型。中断或未知阅读保持暂停，未决模型结果不能用新操作 key 自动或显式重放。

## 验证

最终同批 **156/156 项定向回归通过，103.035 秒**。范围包含多目标生活/状态、私聊与群宿主、身份策略版本刷新、单目标生活 API、私人生活上下文、角色状态、日记排程/触发、阅读和工程隔离。

新增 `tests/test_astrbot_multi_life.py` 的 6 项和 `tests/test_astrbot_multi_life_recovery.py` 的 3 项已通过：两个账号/两个角色的配置和资料隔离、旧格式回执重试、跨目标令牌/活动拒绝、挂起请求体期间的并发路由、原人格阅读/日记/梦境、独立日记时间与配置 generation、在途切换、停机与两次重载、未知结果不重放。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_astrbot_multi_life tests.test_astrbot_multi_life_recovery tests.test_astrbot_multi_host tests.test_astrbot_multi_state tests.test_astrbot_group_host tests.test_group_conversation_context tests.test_astrbot_staging_host tests.test_role_life_runtime tests.test_role_life_api tests.test_role_life_host tests.test_role_life_context_host tests.test_role_state tests.test_role_state_api tests.test_role_journal_scheduling tests.test_role_journal_triggers tests.test_role_reading tests.test_isolation -q
```

真实 AstrBot SDK 在独立进程加载 `main.py`，验证四组生活路由、配置管理、共享宿主启动、睡眠命令、停机归档读取、任务退出、数据库关闭与路由注销。入口验收可重复运行：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m tests.multi_life_entry_process
```

所有宿主验证使用临时数据根及合成模型/平台；没有在线重载、真实模型或 QQ 调用，也未读取、迁移或修改 V1 用户数据。入口日志在系统临时目录 `companion-multi-life-entry.log`，定向回归日志为 `companion-multi-life-regression.log`。

## 后续进展与边界

本批完成时，页面接线和角色身体时钟尚未统一。后台等待公平性已由[生活任务排队记录](CORE_BACKGROUND_FAIRNESS_20260924.md)完成；身体状态、睡眠连续性和共享作息已由[跨窗口角色状态记录](CORE_SHARED_ROLE_BODY_20260924.md)及[共享自动睡眠排程](CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md)完成。当前生活工作区接入「陪伴小屋」，日记仍保持 installation + bot + role + kind + 当地日期唯一键，并复核私人 scope。

仍未覆盖的是生产 QQ/模型现场效果，以及超出已记录私聊输入和阅读时长的实际工作量来源；当前负荷分数不把未确认的日程计划当作已完成劳累。
