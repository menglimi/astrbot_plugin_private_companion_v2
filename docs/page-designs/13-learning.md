# 13 · 学习（manage/learning）

当前基线：2026-10-08，按用户提供的六张学习设计图重排。页面由 `app.js` 的 `renderLearningPage` 承载，统一顶栏选择学习范围和角色，六个子页保持相同骨架、主题色和字号体系。

| 子页 | 展示与实际入口 |
| --- | --- |
| 总览 | 成长、待审数量、当前学习概况；确认成长建议、打开成长链路 |
| 审阅中心 | 成长进度、表达候选、复盘建议的统一审阅；明确来源、状态与可执行动作 |
| 成长链路 | 目标／技能列表、证据、修订、暂停与恢复；成长和技能配置工作台 |
| 表达学习 | 规则库、观察素材、22 项学习配置；已采用／停用规则、使用统计、分享包和素材审核 |
| 语义目录 | 群词义／表情目录、检索、编辑、模型与向量配置 |
| 每日复盘 | 有效建议、待审建议、失效历史；来源证据与复盘配置 |

## 表达学习

挂载点为 `#expressionSignalsWorkspace`、`#expressionSamplesWorkspace`、`#expressionWorkspace`。模块分别是 `expression-signals-page.js`、`expression-samples-page.js`、`expression-page.js`，配置使用 `CompanionWorkbench` 的真实后端合同。

规则库展示人工采用后的规则、使用次数和反馈；停用、恢复、导入预览／应用、导出均有真实接口。候选进入审阅中心；来源失效的规则不展示旧正文，也不再注入回复。

观察素材来自当前精确窗口的原始用户消息，显示成员账号、时间、正文、审核状态与允许／排除操作。默认自动取样；开启手审后仅批准的素材可学习。素材列表最多扫描 512 条，每页 24 条；学习单批上限由独立配置控制。立即学习使用真实门槛和每日预算，显示进度，完成后刷新候选。保存配置刷新素材状态，无需重新打开页面。

| 配置分区 | 字段 |
| --- | --- |
| 学习来源 | `learning_mode`、`private_learning_enabled`、`group_learning_enabled`、`group_member_mode`、`group_member_ids`、`sample_review_enabled` |
| 表达应用 | `private_application_enabled`、`group_application_enabled`、`style_review_enabled`、`rules_per_turn`、`payload_chars` |
| 采样与频率 | `window_hours`、`sample_limit`、`min_samples`、`group_min_samples`、`sample_chars`、`scan_interval_minutes`、`group_daily_batch_limit`、`group_new_messages` |
| 容量与轮换 | `active_signal_limit`、`rotation_candidate_limit`、`rotation_decay_hours` |

私聊与群聊的学习、应用分别控制；群学习默认关闭，应用只使用已人工采用的规则。换发言成员不重置同群工作状态。规则可用于回复和主动消息，表达复核在分段／TTS／发送前完成，失败保留原稿。

## 接口与状态

配置 `GET {reply_api}/expression`、`POST {reply_api}/expression/configure`；规则 `/style`、`/style/command`、`/style/export`、`/style/import/preview`、`/style/import/apply`；素材 `/style/samples`、`/style/samples/command`；学习 `/style/learn`。私聊与群聊使用各自注册的 `reply_api`，范围由顶栏选择。

页面不填造样本、规则或进度。读取失败提供就地重新读取；切换范围丢弃旧请求，卸载清理轮询。视觉与交互验收使用 `tools/check_learning_page.cjs`，通过实际 AstrBot 资源重写和桥接 SDK 加载页面，以合成接口覆盖 1559／960／390／320 四宽度与四主题。

功能对照、V1 owner 筛选差异和测试范围见 [V1 表达学习对照](../EXPRESSION_V1_ALIGNMENT_20261008.md)。
