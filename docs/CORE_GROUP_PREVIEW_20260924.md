# 群聊可信入站与前台预览

后续进展：[群聊独立授权与 OneBot 投递](CORE_GROUP_DELIVERY_20260924.md)已补齐发送链。以下保留首批 preview 阶段的实施与验收记录；当前群聊默认 preview，可另行配置并逐群授权发送。

2026-09-24。V2 多目标宿主现已接通显式群目标的文本入站、实际发言者身份、原生人格解析、公共任务/模型链、持久草稿和管理查询。群目标始终为 preview；这批是群聊前台基础，不代表群记忆、完整群工具或真实群发送已交付。

## 接入与归属

- `astrbot_host/group_settings.py` 解析 `multi_host.group_targets`。每个目标绑定平台实例、Bot 登录账号、逻辑 Bot 和群号。目标 ID 在私聊、群聊间唯一；相同数字的用户 QQ 和群号属于不同场景。
- `companion_v2/adapters/astrbot/group.py` 对照原始 OneBot `message/group` 事件验证规范化消息的 sender、自账号、群号与消息 ID；拒绝匿名、Bot 自发、字段冲突及不匹配的 client。文本、账号提及和全体提及可以接收，引用/转发/媒体须另行定义群受众来源合同。
- 群 session 接受 AstrBot 4.27.2 的两种明确格式：`群号` 和 `发言者QQ_群号`。后一种来自宿主的 unique_session 选项；persona 按本次事件的实际 UMO 解析，不以私聊 UMO 或另一个群作为回退。
- 人格仍使用显式 `persona_id → role_id` 映射，并复核 prompt 指纹。V2 conversation ID 附加 role 标识，切换人格不会重标旧来源；原 session 切走后旧任务失效，另一个群或独立成员 session 不受影响。
- `astrbot_host/group_authority.py` 在原生快照全部验证后，将人类身份、群路由、角色绑定、逐发言者的精确 grants、来源与输入同事务受理。拒绝消息不创建成员、授权或来源；已撤销身份/grant 不会在入站或重启时自动恢复。

## 群受众与私人领域

群路由的 `user` 固定为空，`group_id` 保存实际群号；发言者保留为当前 human actor。`identity_policy/group_audience.py` 生成“当前发言者 + 群集体”的 `AudienceRef`，集体引用使用 `SubjectKind.GROUP`，不冒充某个用户，也不声称已枚举全部群成员。

公共任务调度检查群路由及集体受众，当前仅开放前台回复所需的 `text`、`configuration.read` 和 `conversation.reply`。群消息不继承私聊 target 的能力 grants，不启动私人状态维护、自动反思或主动联系。前台封存不读取私聊记忆、关系、日记/梦境、成长、角色状态、私密事项和后台投递历史，群 profile 暂不提供角色工具。私聊记忆服务本身也要求私聊 scope 和独占受众，包含管理操作者入口；不能仅更换 audience 或借同一个 human/role 读取私聊记忆。

模型仍使用已配置的原人格提示，并补充群聊表达约束：当前发言者仅代表本人，提及不构成授权，不推断未提供的私聊关系或群聊历史。群消息当前按原发言者组成有界回复批次，没有跨成员历史汇集或群长期记忆。

## 配置与草稿查询

在已有 `multi_host` 配置中增加：

```json
{
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
```

同一配置的 `personas` 需包含该逻辑 Bot 使用的人格映射。支持仅配置群目标，私聊 `targets` 可以为空。未配置群不会被接管。保存配置后仍通过已认证 Dashboard 的共享宿主 `probe → initialize → start` 流程启用；重载只读加载，不自动开始接收消息。

管理 API 前缀为 `/astrbot_plugin_private_companion_v2/host`：

- `GET /status`：目标场景及实际投递模式；群目标不注册私聊 memory API。
- `GET /batches?target_id=group-1`：最近 20 个批次的标识、原发言者、role、状态及分段数，`has_older` 表示列表有截断。
- `GET /preview?target_id=group-1&batch_id=...`：复核原任务权限与素材，返回草稿及 `sent` 状态；跨目标查询拒绝。

群 draft 的投递回执为 `not_sent`，沿现有 preview 路径保存，不能计入已送达历史。即使安装启用 `onebot_private` 或某私聊 target 已获投递授权，群目标也只保留草稿；对群调用 `authorize-delivery` 返回 `host_group_preview_only`。后续真实群发需要独立 capability、逐群授权、群 sender 与回执验收。

## 本地验收

`tests/test_astrbot_group_host.py` 覆盖群目标配置、群/成员 session、多 Bot/群/persona 隔离、发言者与群受众、字段伪造、未配置群、匿名与离线账号、私聊记忆不披露、授权不混用、撤权、重复事件、重启及停机竞态。真实 `AiocqhttpMessageEvent`、`AstrBotMessage`、`At/AtAll`、`MessageType` 和宿主 unique-session 构造器也参与端到端预览测试；模型与平台客户端使用网络无关替身。

验证结果：群聊专项 **12/12** 通过（5.863 秒）；宿主、OneBot 私聊发送、公共引用和隔离扫描回归 **39/39** 通过；任务调度/存储、会话、宿主恢复、记忆边界/消费/管理/协议回归 **106/106** 通过（58.889 秒）。后两组共 145 项，和群专项不重复。真实插件入口另在独立进程完成导入、初始化、原生群事件转发、preview、终止及路由注销；平台发送调用为零。

定向回归模块为 `test_astrbot_multi_host`、`test_astrbot_multi_live_acceptance`、`test_astrbot_staging_host`、`test_astrbot_onebot`、`test_references`、`test_isolation`、`test_execution`、`test_execution_storage`、`test_conversation_messages`、`test_host_application`、`test_host_recovery`、`test_memory_boundaries`、`test_memory_conversation`、`test_memory_management` 和 `test_memory_wire`。验证只覆盖受影响路径，不代表所有领域或真实群场景已经验收。

运行方式使用 AstrBot 自带 Python，将 `backend/app` 加入进程 `PYTHONPATH`，并在导入 SDK 前把 `ASTRBOT_ROOT` 设置为临时目录。验证仅使用合成身份、独立 V2 SQLite 和临时宿主数据根，没有读取 V1 数据、在线重载、真实模型调用或 QQ 群发。本批无需数据库 schema 迁移；未配置群时保留已有私聊宿主设置指纹。
