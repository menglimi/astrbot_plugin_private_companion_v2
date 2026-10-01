# Reality / Together V2 原生拓展接入

2026-09-26。Reality 与 Together 两个现有可选插件各自向 V2 原生注册器提供同步 manifest 和异步执行端口；**Reality / Together 是陪伴插件 V2 本体的拓展能力，不另注册 V2 插件**。V2 唯一本体仍为 `astrbot_plugin_private_companion_v2`，负责原任务身份、能力授权、角色复核与最终回执采纳。Reality 声明 `reality.snapshot.read`、`reality.camera.observe`、`reality.device.list`、`reality.device.status`、`reality.device.control`、`reality.device.action`、`reality.operation.lookup` 和 `reality.operation.cancel` 八项能力；Together 声明 `together.room.snapshot`、`together.room.create`、`together.room.close`。提供方只有在自身插件启用并初始化后才暴露端口；Together 创建房间还要求房间服务已运行。

### Reality 私聊授权闭环（2026-10-01）

V2 为八项 Reality 能力各自注册状态与配置路由，并由当前目标/角色下发路由基址。宿主从已绑定的 V2 私聊和登录 Dashboard 管理员身份解析授权对象，不接受请求参数覆盖目标身份；每个能力使用独立的 `capability_id` 记录授权，打开或撤回后立即重新计算模型工具目录。授权不会代替 Reality 的提供方启用状态、设备映射、设备白名单、管理员策略或本轮用户确认。路由在插件停止时注销。

「陪伴小屋 / 感知能力 / 屏幕与设备」为手机摘要、摄像头单帧、设备目录、单设备状态、电源控制、设备属性动作、操作查询和未派发操作取消提供各自状态、逐项允许/撤回与原请求核对。设备控制的聊天回复经 V2 正常投递账本记录确认回执；设备操作结果未知时必须沿用原操作查询，不自动重发。页面切换 Bot、角色或私聊窗口时，迟到的旧目标状态不会显示到新目标。

用户账号从 V2 已认证 `actor.principal.native_account_id` 取得，不接受模型参数中的用户 ID。`actor.subject.subject_id` 仍用于确认上下文完整，但它是 V2 稳定标识，不能直接传给旧插件的手机/房间接口。操作以完整上下文（排除轮换的 `policy_revision`）分桶；Bot、角色、用户或会话不同，不能读取对方操作或房间。同一个 invocation ID 换上下文会被拒绝。Together 快照只枚举当前 scope 的成功创建且尚未关闭的房间，不再展示同用户在旧插件或其他 scope 的房间；连续关闭按最新未关闭房间逐个处理，未消费票据也会撤销。

各插件在自己的 `native_v2/operations.json` 保存原请求身份、状态和回执，重启后可显式 lookup；存储损坏时停止加载，避免把旧操作当作新操作重放。无副作用快照的公开回执不带 operation ID。设备控制只有米家确认 `confirmed: true` 才记为已提交；无确认、超时或调用中断均为 unknown，不自动重试。调用前权限或房间服务检查失败记为未提交。原生提供方不调用真实 QQ 发送端。

Reality 设备目录只返回已映射别名、类别、缓存在线状态、控制白名单与管理员策略提示，不下发 DID、型号、设备原名、登录信息或整个管理快照；最多列出 100 项，并标示余量。精确别名的状态查询遵守 `enable_readonly_tool`，只向米家请求设备档案指定的最多 32 个属性，回执裁剪敏感文本与长度。原有 WebUI 状态路由也复用这一查询路径。设备控制要求米家总开关、控制开关和精确别名白名单同时允许。V2 原生请求目前不能证明 AstrBot 管理员身份，因此 `control_tool.admin_only=true` 时拒绝原生聊天控制；Dashboard 管理员页面仍走自己的鉴权入口。白名单信息是配置提示，不表示当前对话拥有控制权。

建房前，V2 宿主复核当前 AstrBot 人格和提示词，向 Together 原生端口交付与 Bot、账号和作用域匹配的人格绑定；房间票据、会话及后续邀请票据继承这一绑定。V2 房间系统提示词使用固定人格，不读取 V1 场景、记忆、历史对话及语音配置，也不向旧直播字幕、短期记忆或共享活动端口写入。小说书库按 V2 作用域存于 Together 自有 `native_v2/novel_library/<scope>/`，上传、书目、章节、进度及阅读检索均走相同目录；V1 书库保持原路径和原上传权限。原生操作日志仅保存人格提示词摘要，不保存原文。房间快照和关闭也识别从同一 V2 房间创建的邀请房间。

V2 宿主还把已配置的模型 ID、按语言选出的 TTS Provider ID、语音语言和超时固定在新房间票据中；Together 创建前验证 V2 模型可用。模型回复、视觉、STT、TTS 与能力显示按房间票据及原会话路由，不借用 Together 的 V1 模型或 TTS 配置；指定的 V2 TTS Provider 不可用时不回退到 V1，未指定时才查询原会话的 AstrBot TTS Provider。V2 通话选日语或英语时，模型提示词按票据语言生成直出语音段。邀请票据继承同一执行绑定。

Reality 原生拓展的定向验证（2026-10-01）：提供方动作合同 20 项通过；V2 Reality 授权与原生感知宿主 API 合计 11 项通过；陪伴小屋授权页在 1440px、390px、320px Playwright 检查中，八项独立授权/撤回、原请求核对、目标切换隔离、无脚本错误及无横向溢出均通过。端到端使用临时数据根、合成手机/摄像头/设备和假 OneBot 回执，没有读取 V1 用户数据或连接真实设备。真实手机、摄像头、米家设备、房间服务器、模型与 QQ 现场验收仍未完成。

此前 Together 模型路由、房间隔离与 TTS 定向测试 42 项通过，覆盖 V2 模型实际回复、语音生成、原会话 STT、外语提示词和 V1 Provider 不被调用。原生提供方不调用真实 QQ 发送端。

下一步：继续补齐其他可选功能域的 V2 原生能力；功能齐备后，在受控 AstrBot 环境统一检查七项声明、房间与语音链路、只读设备目录与状态查询。真实米家设备控制必须单独现场确认，不由离线测试代替。
