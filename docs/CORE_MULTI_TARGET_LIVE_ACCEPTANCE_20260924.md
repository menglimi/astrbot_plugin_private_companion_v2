# 多 Bot／多人格宿主现场验收清单

这份清单用于把本地合成宿主推进到真实 AstrBot 多账号现场。验收先使用 `preview`，只验证入站、人格解析、记忆边界和重启恢复；确认这些结果后，才对单个 target 做有限期 `onebot_private` 投递授权。不要把真实账号、Dashboard 凭据或 API Key 写入仓库。

## 现场准备

1. 确认 AstrBot 版本为 4.27.2，两个或更多 OneBot 平台账号已经在线，且每个平台实例、账号和原生 persona 都能从 AstrBot 当前进程解析。
2. 在插件配置中只启用 `multi_host`，保持 `staging.enabled=false`。为本次现场使用新的稳定小写 `installation_id`，例如 `live-preview-20260924`。
3. 为每个私聊目标填写唯一 `target_id`、真实 `platform_id`、`account_id`、`bot_id` 和 `participant_id`。为每个 Bot 登记当前可解析的 `persona_id`，并明确对应的 V2 `role_id`。
4. 首轮使用 `delivery_mode=preview`，保存配置并重载插件。重载只允许加载已有 profile，不会自动启动或发送消息。

推荐的最小验证矩阵：

| target | 平台账号 | 逻辑 Bot | 私聊参与者 | persona | V2 role | 预期记忆关系 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 实际账号 A | bot-a | 用户 A | persona-a | role-a | 与 B 隔离 |
| B | 实际账号 B | bot-b | 用户 B 或 A | persona-b | role-b | 与 A 隔离 |

需要验证人格共享时，再增加同一 Bot 下映射到同一个 `role_id` 的第二个原生 persona；不要只改显示名称来推断隔离已经发生。

## Dashboard 顺序

使用已登录的 Dashboard 管理员会话调用插件前缀 `/astrbot_plugin_private_companion_v2/host`：

1. `GET /status`：确认 `mode=multi`、target 数量和 `state=uninitialized` 或已加载的 stopped 状态。
2. `POST /probe`：确认所有账号在线、原生 persona 可解析、provider 类型可验证；此步不应产生模型请求、平台发送或 V2 数据库。
3. `POST /initialize`：固定 installation manifest、原生身份、role 绑定、scope 和 grants。
4. `POST /start`：启动共享 runtime；状态应为 `running`，并且仍没有平台发送。
5. 读取 `/targets/<target_id>/roles/<sha256-role>/memory` 及 `/settings`：确认每个 target/role 都有独立路由，管理员身份来自 Dashboard 会话。
6. 结束预览后调用 `POST /stop`。若要重载，先让插件终止，再确认旧路由已注销；重新加载后应保持 stopped，不能自动接管消息。

`authorize-delivery` 和 `revoke-delivery` 必须带唯一的 `target_id` 查询参数。preview 模式下授权请求应明确返回投递模式不允许的错误，不得改变任何发送状态。

## 入站和记忆验收

对 A、B 各发送一条可识别的私聊文本，检查：

- 两条消息都被正确的 target 接管；未配置的账号或参与者不写入 V2 数据库。
- A、B 共用一个 V2 runtime，但生成上下文包含各自的 Bot、role 和私聊 scope。
- 在 A 的可信上下文写入一条 pending 或 durable 记忆后，B 的 memory API、查询、operation ID 和 pending 决定都不能读取或采用它。
- 同一 Bot 切换到不同 `role_id` 后，旧 role 的事实和 pending 不能被当前 role 读取；切回原 role 并重新获取上下文后，durable 记忆可恢复读取。
- 同一 Bot 的两个原生 persona 映射同一 `role_id` 时，长期 owner 相同；映射不同 `role_id` 时，owner 不同。原生 persona ID 或名称本身不构成隔离键。

记录每个 target 的 owner key、scope key、当前 role binding、模型调用数量和平台发送数量。日志和截图中脱敏账号与参与者标识。

## 单 target 投递验收

仅在 preview 验收通过后执行：

1. 停止共享宿主，确认配置改为 `onebot_private` 后重新 probe、initialize 或加载同一固定安装。
2. 通过 Dashboard 只授权 target A，启动宿主并让 A 产生一条回复；确认 A 收到一次可核对 ACK。
3. 让 B 产生回复；确认 B 因没有投递授权而不发送，模型和本地回执仍按原边界记录。
4. 撤销 A 的授权，再提交一条 A 回复；确认发送边界失败且没有第二次平台请求。
5. 不复用旧 operation、旧授权或旧 unknown 回执；所有不确定结果先通过原 operation ID 查账。

现场发送属于真实外部副作用。每次授权只覆盖一个 target，授权有效期结束后必须重新从 Dashboard 显式授权。

## 重启恢复验收

在 preview 和单 target 投递各完成一轮后，执行一次插件重载：

- 已初始化 profile 可只读加载，保持 stopped；不会因为插件加载自动接管私聊。
- 显式 start 后，原 target 的上下文和 pending 操作仍能恢复；其他 target 不能采用该操作。
- 已撤销的身份、memory grant 或 delivery grant 不会被初始化、重启或入站流程重新创建。
- 旧实例的 Dashboard 路由不会覆盖或注销新实例的 handler。

## 本地合成回放

没有真实账号凭据时使用合成 AstrBot context 回放同一验收顺序。它创建两个在线假平台账号和两个原生 persona，实际走 `AstrBotMultiController`、Dashboard route handler、V2 SQLite runtime、模型替身和 OneBot reverse API 替身：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_multi_live_acceptance -v
```

当前回放结果：**1 项通过**（约 2.3 秒）。preview 阶段两个 target 均完成生成且平台调用为 0；停机后只读加载并显式 start 可恢复原 owner 与 pending operation；`onebot_private` 阶段只授权 target A，A 产生 1 次发送，B 产生 0 次发送；撤销 A 后再次生成没有新增平台请求；两个 controller 终止后 Dashboard route 列表为空。

## 通过条件与回退

通过条件是：所有 target admission、role/owner 隔离、按 target memory API、preview 无发送、单 target 授权、撤权、重启恢复和路由注销均有记录。任一账号解析、人格映射、scope 或授权结果不符合预期时，保持 `preview`、停止宿主并保留原始回执，先修正配置或代码再继续。

这份现场清单不迁移 V1 数据，也不改变现有生产插件。现场结果应追加到本文件或单独的脱敏验收记录，并同时更新 `docs/BUILD_STATUS.md`。
