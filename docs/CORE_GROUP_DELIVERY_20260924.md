# 群聊独立授权与 OneBot 投递闭环

2026-09-24。在[群聊可信入站与预览](CORE_GROUP_PREVIEW_20260924.md)基础上，已接通群文本发送、逐群短期授权、原平台回执和重启恢复。群发送仍默认关闭；本批完成代码与模拟验收，没有在线重载、真实模型请求或向 QQ 群发送消息。

## 配置与管理

`multi_host.delivery_mode` 继续控制私聊；新增独立的 `multi_host.group_delivery_mode`，仅接受 `preview` 和 `onebot_group`。群目标仍由已有 `group_targets` 绑定平台实例、自账号、逻辑 Bot 与群号，不改变目标身份字段。省略群模式或显式设置 `preview` 时，旧私聊及旧群预览安装的配置指纹保持兼容。配置变更需在停止后重新 initialize；仅修改模式不会重新绑定既有 target。

群投递配置示意（与现有 `personas`、模型、运行时配置共同使用）：

```json
{
  "multi_host": {
    "enabled": true,
    "installation_id": "main",
    "delivery_mode": "preview",
    "group_delivery_mode": "onebot_group",
    "group_targets": [
      {
        "target_id": "group-1",
        "platform_id": "default",
        "account_id": "10001",
        "bot_id": "bot-1",
        "group_id": "30001"
      }
    ]
  }
}
```

已认证 Dashboard 管理 API 前缀为 `/astrbot_plugin_private_companion_v2/host`：

| 接口 | 行为 |
| --- | --- |
| `POST /authorize-group-delivery?target_id=group-1` | 对这个群签发 15 分钟的 `message.group.delivery` 授权；每次授权有新版本 |
| `POST /revoke-group-delivery?target_id=group-1` | 撤销这个群的发送权；不会更改其他群或私聊授权 |
| `GET /status` | 列出私聊/群模式及各群当前有效授权、期限和版本 |
| `GET /batches?target_id=group-1` | 列出该目标原批次，保持原发言者与角色归因 |
| `GET /preview?target_id=group-1&batch_id=...` | 返回原批次投递模式、当前配置模式、草稿、状态、操作/回执引用及原平台消息引用 |

管理入口拒绝未登录和 `api_key:*` 身份。私聊 `authorize-delivery` / `revoke-delivery` 拒绝群目标；群接口拒绝私聊目标。群授权使用独立 metadata 命名空间，固定 `message.group.delivery` capability、目标完整身份、初始化 manifest 指纹和有限有效期，不能解释或复用私聊授权记录。群前台身份/回复 grants 与宿主平台发送授权分别检查。

## 受理、发送与恢复

`astrbot_host/group_delivery.py` 持有群发送授权及每个输入批次的原始投递意图。可信入站调用同步 `on_admitted`，将群模式、目标、原任务上下文、sender binding 和当时有效的授权版本，与身份/来源/消息受理放在同一事务中保存；任一步失败整批回滚。

只有在群发送模式、有效群授权下新受理的批次，才具备发送资格。无授权时受理的批次、旧 preview、缺少记录的历史批次不会因后来开关模式或授权而变成待发送消息。合并输入保留批次最初的意图；重新授权产生新版本，旧批次不能借新版本继续发送。正常停止后，尚未开始且仍处于原期限、原授权版本的任务可以继续；结果为 `unknown` 或已送达的任务不重发。

`OneBotGroupSender` 检查原群 scope、当前发言者及其原生 session、完整集体受众、原 Bot/账号、文本哈希和 sender binding。与私聊发送器共用窄 reverse WebSocket 传输，但群路由只构造 `send_group_msg(self_id=原账号, group_id=原群号, message=文本段)`。不会使用私聊 API、宿主布尔返回值、HTTP 或另一个登录账号作为回退。

发送前两次检查授权，中间复核当前 persona、原 prompt 指纹和固定 client；最后调用公共任务的 `before_dispatch` 复核来源、撤回、身份、grants、任务和原发送权。最后一次检查与进入 API 调用之间没有额外 await。

有效 OneBot `message_id` 生成带平台/账号命名空间的 `platform_ref`，支持真实负数消息 ID。公共投递层按原 part、operation、context、payload hash 和 sender 保存回执；只有确认送达才进入已送达历史。派发前拒绝返回 `not_sent`，公共分段状态为 `failed`；派发后超时、异常、无效 ACK 返回 `unknown`。重复入站、重启、撤权或重新授权都不自动重发这些分段。

本批使用既有 runtime metadata 与会话投递账本，无数据库 schema 迁移。群受众仍与私人 owner 分离，不读取私人记忆、关系、生活或身体状态，不启动私人后台任务。

## 验收

当前定向测试按测试 ID 去重共 **112 项通过**，其中群相关 **25 项**，本批新增 **13 项**：

- `test_astrbot_group_host`：12 项，保留原群身份/人格/隐私/preview 及恢复覆盖。
- `test_astrbot_group_delivery`：11 项，包含多组子场景；覆盖独立授权、目标/账号/群路由、授权期限、受理事务回滚、授权更新不提升旧稿、persona/prompt/来源/权限/连接竞态、ACK/unknown、历史 preview、正常待处理消息恢复及防重发。
- `test_astrbot_group_native_delivery`：2 项，使用已安装的 AstrBot 群事件、unique-session 构造器和真实 `WebSocketReverseApi` / `ResultStore` 编解码；仅 socket 与模型为无网络替身。验证真实协议帧、原账号选择、echo 关联、ACK、平台错误、超时和结果未知不重试。
- 相关回归 87 项：`test_astrbot_multi_host`、`test_astrbot_multi_live_acceptance`、`test_astrbot_onebot`、`test_astrbot_staging_host`、`test_isolation`、`test_astrbot_native`、`test_astrbot_inbound_adapter`、`test_conversation_messages`、`test_host_recovery`。

真实插件 `main.py` 另在独立进程验收通过：按插件 namespace 导入、注入合成模型/时钟与本地 socket、使用真实 SDK 群消息，完成 initialize、逐群授权、start、事件终止及 V2 转发、平台 ACK 入账、terminate、数据库关闭和路由注销。运行时数据根全部为临时目录，不读取 V1 数据。首次入口夹具使用了宿主墙钟与历史消息时间，触发身份尚未生效检查；统一模拟时钟后验收通过。隔离检查发现相对导入 `.onebot` 与外部包名冲突，已改用完整内部包路径，未放宽隔离规则。

运行环境为 `C:/Users/99505/.astrbot/backend/python/python.exe -X utf8`；仅在测试进程将 `backend/app` 加入 `PYTHONPATH`，在导入 SDK 前将 `ASTRBOT_ROOT` 设为临时目录。测试分批执行，重复验证不累计数量。

## 下一步

[群内多成员共享上下文](CORE_GROUP_CONTEXT_20260924.md)随后已落地：固定群受众、原发言者归因、Bot/角色/session 边界以及撤回传播，防止单人私聊材料进入群回复。下一步在该合同上增加群公共记忆；群媒体、群工具与线上发送验收分别推进。
