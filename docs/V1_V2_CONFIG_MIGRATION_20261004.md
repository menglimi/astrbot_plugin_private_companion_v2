# V1 到 V2 配置迁移覆盖（2026-10-09）

配置映射由 `docs/V1_V2_CONFIG_RESOLVED_20260928.csv` 生成；生成物同时携带全部 1,010 个台账来源，供迁移预览解释未自动转换的现存配置。当前台账分类为：156 项已在 V2、319 项改名等价、166 项由其他机制承接、29 项仍欠账、316 项按设计不迁移、24 项不适用。审计分类描述的是 V1 配置键，不代表迁移时会读取或改写 V1 用户数据。

| 自动转换目标 | 规则数 | 处理方式 |
| --- | ---: | --- |
| V2 配置注册表 | 346 | 按 V2 运行时字段合同校验；图片范围、情绪总开关和组件策略有专项说明或转换 |
| V2 插件配置 | 42 | 按当前插件 schema 类型、范围和选项校验 |
| V2 语义目录 | 15 | 按语义设置类型、范围和选项校验 |

上表合计 403 条通用映射。另有 9 类账号、目标与人格配置由专用转换器处理；天气、分段作用域/参数、技能成长日程强度由领域转换器处理。两项经过审计的旧设置不进入直接映射：`emotion_relationship_config.enable_smart_silence` 没有 V2 独立开关，`voice_action_config.tts_message_scope` 不能推导 V2 主动语音授权。迁移预览会列出当前来源中存在但没有自动转换的键及审计原因，不包含这些配置的实际值。

本次复核新版配置消费路径后修正了下列映射：

- `experimental_motivation_config.enable_emotion_simulation` 写入 `role.state.mood_enabled`，不再误写到情绪半衰期。它只覆盖 V2 角色短期情绪维护；V1 的关系边界惩罚与 QQ 空间发布能力分别审计，不随此开关迁移。
- `message_debounce_config.enable_private_image_self_recognition` 写入 `conversation.presentation.enable_private_image_self_recognition`；`group_observation_config.enable_group_image_understanding` 写入 `conversation.presentation.image_understanding_group_enabled`。两者是部分映射：V2 对应开关管理额外视觉转述/历史摘要及范围权限，本轮原图仍会进入主回复模型。
- `emotion_relationship_config.enable_smart_silence` 不再误映射到 `proactive.contact.silence_min_confidence`。V2 在主动联系的单次生成决策中直接决定发送或沉默，没有同义总开关。
- `forward_message_config.forward_message_image_vision_timeout_seconds` 不再映射到全局轮次超时。V2 没有转发图片视觉的独立阻塞步骤，全局轮次和其他媒体任务超时均不是等价设置。
- 分段图片与语音策略使用专项转换：旧值 `inline` 可转换为 V2 的 `image_position=after_text` 或 `voice_position=after_text`；`separate`、`previous`、`next` 涉及独立消息或跨段组件归属，在预览说明且不写入近似值。旧 `at` 的 `inline` 已由 V2 默认同条顺序承接，其他策略不改写“是否提及说话人”的开关。

V1 拟人状态总开关到 `role.state.enabled` 的迁移是部分等价：该字段只控制 V2 状态维护，日记、梦境和生活能力由各自字段处理。迁移预览会明确列出边界。模型 token 上限、备用 Provider、任务提示词、消息防抖布尔总开关以及仍待实现的欠账配置不会按相似名称直接复制。技能成长的 0–1 日程强度仍按已审计规则折算为 V2 的 0–3 档；插件级目标仍由宿主 schema 校验；V2 已有显式设置优先保留。

迁移页面默认范围为主动消息与天气基础设置；选择“全部可迁移配置”才会试算其余自动映射。执行仍只写入当前选择的 V2 目标与人格，V1 来源只读且不删除、不修改。目标账号/人格无法明确匹配、值超出 V2 合同、多个旧别名互相冲突或策略无法表示时，会保留现状并在预览列出原因。

2026-10-09 定向检查：生成规则为注册表 346 条（高置信 280、中置信 66）、插件 42 条（高置信 35、中置信 7）、语义 15 条（高置信 14、中置信 1）；审计来源与台账 1,010 个键逐项一致。源码和新解包本体包中的配置迁移、发现与计划、账号范围及宿主安装 API 测试各 107 项通过；陪伴小屋向导 16 项通过，小屋同步检查无差异。核心包哈希记录在交付目录的 `release-manifest.json`；包哈希、CRC、文件清单、语法、迁移合同和宿主启动/停机、4 条生活路由注销均通过，模型/平台调用为 0。验证报告位于对应解包目录的 `package-verification.json`。八包套件未能构建：同级可选 Screen 插件的 `metadata.yaml` 缺少 `astrbot_version`；本次已构建并验收核心本体包，不改动该插件。
