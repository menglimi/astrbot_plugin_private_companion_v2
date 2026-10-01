# 模型失败诊断现场复验

日期：2026-09-23。接续[失败诊断切片](CORE_MODEL_FAILURE_DIAGNOSTICS_SLICE.md)，在本机运行中的 AstrBot 加载新代码，并使用独立 `sender-3` profile 观察新的单目标私聊批次。新消息在 provider 请求阶段失败，脱敏分类已通过管理接口和重载后数据库核验；本轮没有新的 QQ 发送 ACK。现场结果与独立合成探测分别记录。

## 已完成的现场准备

- 通过 Dashboard 正常登录接口建立临时管理会话；凭据和登录 Token 仅在临时进程内存中使用，没有写入源码、运行配置或本记录。
- 插件元数据确认 V1 `astrbot_plugin_private_companion` 6.6.2 停用，V2 0.2.0 已加载。没有读取 V1 用户数据。
- 在原关闭配置下执行仅针对 V2 的重载。重载成功，状态为 `runtime_open=false`、`session_state=unloaded`、`accepting=false`。
- 仅将 staging 改为 `enabled=true`、`profile_id=sender-3`、`delivery_mode=onebot_private`。配置保存触发 V2 定向重载，随后 probe 和首次初始化成功。
- 原 provider `deepseek/deepseek-v4-flash`、`max_tokens=512` 和运行参数保持原值。平台为 `default`，机器人账号为 `3491542998`，参与者为 `995051631`。
- 对新 profile 数据库作只读核验：`runtime_metadata.schema_version=companion-v2.storage.v15`，`model_call_failures` 存在；初始化时模型调用和失败记录均为 0。这是在线实例加载新核心的证据。
- delivery grant 首次发放成功，有效至 `2026-09-23T05:18:50.147604+00:00`（北京时间 13:18:50）。启动后 `accepting=true`、`session_state=running`，没有恢复任务或未决投递。

## 新批次结果

参与者在授权有效期内发送了一条新私聊纯文本，V2 接管并创建批次 `reply-bc43e349f192450db72703dff365c072`，对应模型调用 `model-call-ad36c355a2254d49812d233cc6c91061`。

| 项目 | 已确认结果 |
| --- | --- |
| 模型调用开始 | `2026-09-23T05:13:45.610100+00:00` |
| 模型调用结束 | `2026-09-23T05:13:48.922636+00:00`，本地等待约 3.31 秒。 |
| 失败阶段 / 错误码 | `provider_request` / `provider_request_failed`。 |
| 模型状态 / 用量 | `unknown` / `usage_state=unknown`，`actual_tokens=null`；37950 tokens 的预留不等同于实际消耗。 |
| 消息与任务 | 入站 1 条，批次停在 `sealed`，生成任务为 `failed`。 |
| 外部结果 | 分段、工具调用及发送回执均为 0，没有新的 QQ 发送 ACK，也没有重放。 |

在线 `/inspect?batch_id=...` 返回上述失败分类，`observed_at=2026-09-23T05:13:48.922636+00:00`。撤权、停机及恢复关闭配置所触发的重载之后，再以只读 SQLite 查询确认：模型调用 1 条、失败分类 1 条、工具调用 0 条、分段 0 条。分类确已持久保存。

## 请求阶段排查

原生 `_query` 在单次调用失败时没有留下可供本次核对的 HTTP 状态或异常类别；已有记录只能定位到 provider 请求阶段，不能还原本次的具体网络、HTTP 或返回类型原因，也不能将其归因为提示词或 JSON/claims 校验。

在 V2 已关闭后，对同一配置的 provider 进行了独立检查，均禁用 SDK 自动重试：

- 只读模型列表成功，列出的 ID 是 `deepseek-flash` 和 `deepseek-v4-pro`，未列出当前配置的 `deepseek-v4-flash`。
- 使用当前配置 ID 发起一次新的最小合成请求，成功返回 `finish_reason=stop`，用量 56 tokens。这说明模型列表缺少该 ID 不能直接判定它不可用。
- 使用合成人格、V2 回复合同及 17 个工具声明发起另一独立请求，成功返回 `finish_reason=stop`，用量 2014 tokens，未请求工具。该探测没有执行任何工具。

两次合成模型探测均未使用现场用户消息、原人格正文或历史批次，没有 QQ 发送。它们是独立 SDK 可用性/请求结构检查，不是 `sender-3` 的重试，也不计为 V2 对话链成功。后续探测成功不足以确定先前失败的根因，不能据此断言只是偶发网络问题。本轮没有更换模型、扩大输出额度或修改提示词。

## 收尾状态

新批次结果读取完毕后，已提前撤销 `sender-3` delivery grant（`state=revoked`），停止会话且待处理句柄为 0。原 `enabled=false`、`profile_id=preview-1`、`delivery_mode=preview` 配置已通过 Dashboard 保存并重载。

最终管理接口确认 `runtime_open=false`、`session_state=unloaded`、`accepting=false`；V1 仍停用，模型选择和 512-token 输出配置保持原值。临时管理进程已退出，凭据及 Token 未写入仓库。

历史 `sender-2` unknown 不重放、不补猜原因。旧 profile 和新 `sender-3` 的原始运行回执保留，临时工具位于系统临时目录；源码根目录仍只有 `main.py` 一个 Python 文件。

本记录保留该次现场诊断事实，具体请求失败原因仍待后续排查。当前实施主线已转到 [CORE-05 角色生活持久化与宿主接入](CORE_ROLE_LIFE_PERSISTENCE_SLICE.md)，模型故障不作为框架建设的前置任务。已撤权的 `sender-3` 和原 unknown 保持原记录，不自动重做。本次现场证明诊断与停机链实机生效，未完成正常回复、完整故障恢复或替换发行验收。
