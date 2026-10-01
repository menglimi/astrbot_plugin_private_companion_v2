# 多目标角色状态、日历与周期管理

2026-09-24。共享宿主原先只有按 target/role 的记忆管理入口，状态、日历和周期仍只能通过单目标 profile 管理。本批把既有 state API 接到每个已配置的私人 target/role，并补齐 QQ 展示回执的归属与重启绑定；领域模型和既有版本表继续共用，没有新增 schema 迁移。

## 管理入口

已登录 Dashboard 后读取 `GET /astrbot_plugin_private_companion_v2/host/status`。每个 `data.targets[].roles[]` 增加 `state_api`，页面应直接使用此地址；群目标返回 null，不注册私人状态路由。

| 请求 | 行为 |
| --- | --- |
| `GET <state_api>` | 当前目标/人格的配置、有效权限、角色状态、周期时间线、日历、维护排程及展示回执。仅接受 `after_id`、`limit` 查询参数。 |
| `POST <state_api>/command` | 既有 `configure`、`state.write`、`cycle.align`、`maintain` 和全部 `calendar.*` 命令，使用 UTF-8 JSON。命令不接受查询参数。 |

地址形态为 `/astrbot_plugin_private_companion_v2/host/targets/<target_id>/roles/<role_hash>/state`。状态与日历命令字段见[状态 API 合同](CORE_STATE_CALENDAR_AND_QQ_PRESENCE_20260924.md)，周期选项、定位与感受结构见[周期合同](CORE_ROLE_CYCLE_20260924.md)及[每轮阶段差异](ROLE_CYCLE_VARIATION_20260924.md)。原单目标 `/state` 和 `/state/command` 继续工作。

每个路由绑定固定 target/role，处理命令时在宿主控制锁内解析当前可信上下文。读取另一人格资料不会切换 AstrBot 当前人格；请求体或查询参数不能另指定 target、role、operator 或 scope。配置令牌、视图令牌、版本检查和来源归属沿用原服务；同一个 `operation_key` 可由不同目标分别使用，各自返回原操作回执。A→B→A 切回后需刷新视图，旧绑定的令牌失效，原状态、周期和日历仍保留。

后台仍使用一个共享任务、模型和预算系统。只有宿主当前已验证并绑定的人格参与维护；管理未绑定人格的配置不会自行启动该人格。`maintain` 只提前对应上下文的排程，返回 `scheduled`，结果从同一路由查询。重启继续使用持久的下一次维护时间，不重新发起已完成的那次模型请求。

## QQ 展示归属与恢复

- 输入提示回执按原完整上下文记录。账号、收件人相同但人格或绑定版本变化时，不把旧回执算给新上下文。
- 自定义状态回执保留原 `context_key`；状态页只投影当前上下文可归属的结果，不返回全宿主结果字典。多个合法拥有者竞争同一账号时，各参与者可见冲突，不向无关账号投影。
- 持久化的成功、失败、unknown 继续去重。重启遇到相同文案时恢复原回执，不重复调用平台；新人格使用相同文案也不会继承旧人格的成功或已解除的冲突提示。
- 多目标宿主启动时重新绑定当前可信人格到展示协调器，修复重启后必须等新消息或配置修改才能恢复日程展示的问题。

`preview` 的 `presentation` 仍为 `{"state":"preview"}`；安装 QQ 展示端口但当前没有可归属结果时返回 `{}`。它不是成功凭据。配置开关、精确展示权限、账号与人格复核、逐目标投递授权仍由既有发送端口检查；多目标没有新增全局发送授权。

## 验证

最终同批 **103/103 项定向测试通过，37.113 秒**。新增 `tests/test_astrbot_multi_state.py` 的 **11 项**集成测试，补强既有输入提示和 unknown 回执恢复的原绑定检查。

覆盖两个账号、两个角色的配置/状态/周期/日历隔离，同操作 key 独立回执，跨目标令牌和来源拒绝，Dashboard 登录及 CORE 权限，挂起请求体时并发修改另一目标，原人格后台维护和定向手动排程，A→B→A 与重载恢复，单目标 QQ 授权，竞争拥有者、同文案人格切换、注册失败回滚和旧实例不能注销新路由。相关既有单目标状态、周期差异、输入提示持续任务、群宿主和工程隔离一并通过。

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_astrbot_multi_state tests.test_astrbot_multi_host tests.test_astrbot_group_host tests.test_astrbot_staging_host tests.test_role_state_api tests.test_role_state tests.test_role_presence tests.test_role_cycle_variation tests.test_isolation -q
```

另用真实 AstrBot SDK 从 `main.py` 加载插件，在临时数据根验证四组状态路由、初始化、共享宿主启动、停机、数据库关闭与路由清理。模型及平台使用替身，实际模型/QQ 调用为零。日志位于系统临时目录的 `companion-multi-state-regression.log` 和 `companion-multi-state-entry.log`。

本批只接后端和管理合同，未在线重载或读取 V1 用户数据。QQ 客户端输入提示显示、真实模型语义、页面交互和跨窗口共享身体时钟仍需后续实施或现场验收。

## 下一步

把阅读、睡眠、日记/梦境的管理入口和当前人格后台绑定接入多目标宿主，验证切换人格、停止与重启后的接续。状态排程在大量已失效上下文下的公平性另做定向复现与优化；本批尚未修改其扫描策略。
