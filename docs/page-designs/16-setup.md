# 16 · 开始使用（`manage/setup`）

代码位置：`pages/陪伴小屋/app.js` 的 `renderSetupPage` 挂载 `CompanionSetup`（`setup-guide.js`）；后端为 `astrbot_host/setup_api.py`。

## 首次配置顺序

| 步骤 | 操作 | 完成条件 |
| --- | --- | --- |
| 1. 运行模式 | 选择单/多账号与单/多人格。切换宿主控制器类型时保存后需重载插件。 | 当前已加载控制器与选择一致 |
| 2. 核心管理员窗口 | 在指定私聊发送 `companion_bind`；多人格发送 `companion_bind <AstrBot 人格名>`。核对平台、Bot 账号、私聊对象和人格后，由 Dashboard 管理员确认。 | V2 本地绑定记录已确认；多人格/多账号首条映射已登记 |
| 3. 插件模型 | 选择 AstrBot 已加载且 V2 可适配的文本 Provider。 | Provider 保存，运行实例初始化；不会启动入站接管或调用模型 |
| 4. 世界知识 | 打开知识库与世界书，填写或选择来源。 | 用户标记完成或暂时跳过 |
| 5. 关系教学 | 打开关系与权限，补充核心管理员及重要对象。 | 用户标记完成或暂时跳过 |
| 6. 主动消息测试 | 用户点击按钮后，V2 向已确认私聊发送一次固定 OneBot 消息。 | 收到平台送达确认；未知结果不会重放 |

设置进度存于 V2 自己的数据根，刷新和插件重载后保留。保存运行规模与绑定候选不会发送消息；步骤顺序也不会要求用户每次启动插件都重新配置。

## 固定运行档诊断

单目标固定档的连接身份由平台/Bot 账号、私聊对象、已配置群目标和人格构成。出现 `host_binding_changed`（兼容旧状态的 `staging_profile_conflict`）时，状态会点名发生变化的绑定类别；模型/provider、预算、投递模式或其他运行参数差异只作为环境变化，不阻止同一绑定重新连接。人格提示词内容变化也不等于换了人格。

首次设置不提供十年授权或预览选项。主动测试只由用户明确点击触发；插件其余投递规则由正式运行设置决定。

完成向导后，状态会写入 V2 独立数据根。宿主重启时会通过 `POST /astrbot_plugin_private_companion_v2/setup/host/start` 按已确认的账号、私聊对象、群目标和人格重新连接；模型或运行参数变化不会把用户退回向导。只有这些固定绑定发生变化时才需要在「账号与会话」中重新确认。

## V1 配置迁移

迁移入口仅在首次设置完成后显示，必须由用户显式检查、试算、再执行。侦察只读；执行只写入当前 V2 目标，不删除或改写 V1。

当前转换器只覆盖 V1 宿主配置中的天气设置；其他来源会按 catalog 标记为只读保留、由外部插件负责、归属待定或暂缺转换器，不应误称为已迁移。V1 配置来源未被宿主传入时，天气转换还依赖 V1 数据根中的受支持配置转储。

## 路由

- `GET /setup/status`、`GET /setup/targets`
- `POST /setup/mode`、`POST /setup/binding/confirm`、`POST /setup/model`
- `POST /setup/complete`、`POST /setup/proactive-test`
- 显式 V1 迁移：`GET /legacy`、`GET /legacy/plan`、`POST /legacy/apply`

连接与模式问题只在 AstrBot Dashboard 管理员会话下操作；状态端点不发送模型请求或平台消息。
