# 我会永远陪着你 V2.0

> **群聊通知（2026-10-11）：** 原群聊被停用一周，期间可先加入 bot 群：**145326153**。

基于已实现 V2 框架的统一陪伴插件。版本 **2.0.0**，声明兼容 **AstrBot >=4.27.2,<5**，以 **4.27.2** 为验收基线；插件身份为 `astrbot_plugin_private_companion_v2`。

当前源码已接入 [Image V2 原生生成与投递](docs/CORE_NATIVE_IMAGE_DELIVERY_20260925.md)：提供方支持生成、同源与私聊输入图多参考编辑、以及由真实后端工作流声明的蒙版局部编辑。宿主使用一次性授权句柄传递本轮私聊图片；V2 在采用时保护蒙版外像素，并沿用图片额度、撤权、未知结果和恢复核验。新交付包需按本次源码重新构建并验收。

当前源码还已接入 [QQ 撤回通知](docs/CORE_PLATFORM_RECALL_20260925.md)、[关系与情绪提案](docs/CORE_RELATIONSHIP_PRODUCER_20260925.md)和[群旁听与选择性参与](docs/CORE_GROUP_PARTICIPATION_20260925.md)：撤回会使旧来源及待发内容失效；关系提案经审阅采用后可沿同原生私聊路线跨会话重置延续；群角色可选择安静旁听。关系工具需要显式 read/propose 权限，实际角色表达仍待现场验收。

源码还已接入[状态维护参数与周期校准](docs/CORE_STATE_MAINTENANCE_EDITING_20260925.md)，并完成[角色计划管理](docs/CORE_ROLE_PLAN_MANAGEMENT_PAGE_20260925.md)：创建、整组改期、单次移动/跳过、提醒与取消均保留来源、版本和原请求回执。计划管理 15 项后端定向用例与三种桥返回格式的完整浏览器流程通过；真实 QQ 状态和提醒效果另行验收。

非页面运行链已接入[原生规划与真实活动联动](docs/CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)：默认关闭的每日/跨周规划及临近日程细化写入角色日历；实际活动、阅读和私人书写回执进入经历记忆；已完成阅读与睡眠可成为有时效的主动联系候选。[角色所在地天气观测](docs/PLANNING_WEATHER_SOURCE_20260926.md)可在显式启用后进入规划。计划不会自动成为完成经历，睡眠回执也不会推导出梦境。天气预警、资讯和其他生活事件生产仍待接入。

**天气数据源默认使用和风天气**（2026-09-28 起）：已配置和风凭据时实况与官方预警共用同一份凭据，未配置时当前天气退回零配置的 Open-Meteo。凭据只从环境变量读取，**不写入角色设置**；变量名、认证方式与旧版 `QWEATHER_ALERT_*` 的兼容规则见[官方天气预警来源](docs/OFFICIAL_WEATHER_ALERT_SOURCE_20260926.md)的凭据章节。使用环境变量是为了让角色配置保持可导出——和风令牌不是可导出的秘密。

**正式拓展页：插件 → 我会永远陪着你 V2.0 → 陪伴小屋。** 首页以体素小屋为中心，整合生活总览、观察与家具入口；记忆、关系、日记、阅读、睡眠、状态、日历、成长和账号与会话使用真实 V2 API，并共享目标/角色选择。交流继续在原聊天渠道。

本体包含会话、多 Bot/多角色、私聊与群聊、来源记忆、关系、连续生活、媒体与引用、主动联系、后台任务、模型网关、能力配置、身份授权及诊断恢复框架。各领域完成程度和页面范围见[发行说明](docs/RELEASE_V2_0.md)。

私聊与[群聊原图回复](docs/CORE_GROUP_IMAGE_DELIVERY_20260925.md)支持本轮已有图片和完整动画，接通图片选择、图文回执、确认历史、再次引用及撤权恢复。Image 原生链另支持多参考编辑与蒙版外像素保护的局部改图；Image 输入参考只在当前私聊授权范围内开放，群聊不开放蒙版局部编辑。真实后端与 QQ 客户端效果仍需现场验收。

[被动回复 TTS 强化](docs/CORE_VOICE_REPLY_ENHANCEMENT_20260925.md)支持按请求或模型标签选句、私群概率与冷却、中日英 Provider、外语译文、分段范围、语音独占及语音组件位置。默认关闭；合成失败保留文字和原图。真实 Provider 与 QQ 客户端的混合组件效果仍需现场验收。

Content、Image、Together、Game、Screen、Reality、Live 七个可选伴侣保留各自插件身份。已交付套件只接安装与状态发现；当前源码已增加统一原生执行端口，以及 Image 基础执行链和 [Content 作品主链](docs/CONTENT_NATIVE_CONSUMER_20260925.md)，使用各自独立原生配置与数据，不调用 V1 执行入口。Content 支持作品/候选、不可变版本、采用、读取和撤回传播；专用创作编排、封面与主动分享仍待完成。Together、Reality、Screen、Game、Live 已有范围各异的原生切片，完整配置与行为仍待补齐，不能按旧交付包视为完成。范围见[本批整合](docs/CORE_NATIVE_GAP_CLOSURE_20260925.md)、[原生重构分工](docs/NATIVE_REFACTOR_COORDINATION_20260925.md)与[构建状态](docs/BUILD_STATUS.md)。

## 安装与运行

导入本体 ZIP，或将 ZIP 内的同名插件目录放入 AstrBot 的 `data/plugins/`。完整套件需先解压，再按需导入其中的各插件 ZIP。

首次打开小屋的「连接与运行 → 首次连接」时，依次选择单/多账号与单/多人格模式，在核心管理员私聊发送 `companion_bind`（多人格模式附上 AstrBot 人格名），回到小屋核对并确认，再选择插件文本模型、填写世界知识与关系资料，最后由用户点击一次主动消息测试。首次进度保存在 V2 独立数据根；完成后日常使用聊天窗口和小屋，不需要重复向导。正式私聊使用 OneBot 投递，按人权限仍由关系设置控制；没有全局预览档或十年投递授权步骤。测试结果未知时不会自动重发。

V2 使用独立数据根，保留已有 V2 配置键和运行档。不读取、迁移或修改 V1 用户数据。旧版核心只作为可选兼容状态项，不作为本体发行。

## 开发与交付

排查模型回复时可临时把 AstrBot Dashboard 中本插件的「日志级别」设为 `DEBUG`，然后在插件日志里搜索 `[CompanionV2][开发者追踪]`。日志会依次记录实际提示词、模型原始回复、合同解析结果、正文处理各阶段和最终分段；角色状态维护也会记录对应的提示词、JSON 正文和解析结果。详细字段见[开发者日志说明](docs/DEVELOPER_LOGGING.md)。日志可能包含用户内容，排查完成后建议恢复为 `INFO`。

当前源码按以下顺序推进，完成上一阶段后再进入下一阶段：

1. 补齐各领域功能代码和实际生效的配置项，确认作用域、默认值及消费者；开发中只做必要的最小检查。
2. 将已完成的能力统一接入唯一公开拓展页「陪伴小屋」，核对页面读写与真实 V2 API 一致。
3. 从当前源码构建本体及可选提供方的插件交付包，核对包内清单和版本。
4. 对新交付包统一测试，覆盖安装/重载、宿主生命周期、关键业务链与受控真实环境；不沿用旧 ZIP 的验收结论。

Game/Live 现有原生切片仍属于第 1 阶段：独立 V2 开关和读取范围已接通，其他游戏与直播互动/呈现行为尚未补齐。历史 V2.0 ZIP 是旧源码快照，不能代表当前增量。

- [V2 完成后逐项执行的真实环境验收任务表](docs/V2_REAL_WORLD_ACCEPTANCE_CHECKLIST.md)
- [安装、框架清单、已接入范围与限制](docs/RELEASE_V2_0.md)
- [本次整合验收](docs/INTEGRATION_ACCEPTANCE_V2_0.md)
- [原生规划、活动记忆与主动联系联动](docs/CORE_PLANNING_ACTIVITY_INTEGRATION_20260925.md)
- [角色所在地天气观测配置与边界](docs/PLANNING_WEATHER_SOURCE_20260926.md)
- [服务余额感知配置与来源边界](docs/SERVICE_BALANCE_AWARENESS_20260926.md)
- [注册盘点、唯一入口与跨任务分工](docs/REGISTRATION_UNIFICATION_20260925.md)
- [构建状态与各领域记录](docs/BUILD_STATUS.md)
- [V1 与当前 V2 的功能差距、源码证据及补齐顺序](docs/V1_V2_FUNCTIONAL_GAP_AUDIT_20260925.md)
- [V1 旧配置盘点、V2 原生配置分类与后续字段归属](docs/V1_V2_NATIVE_CONFIGURATION_MAP_20260925.md)
- [撤回、关系、群参与与 Content 的本批整合](docs/CORE_NATIVE_GAP_CLOSURE_20260925.md)
- [Content 原生消费与撤回传播](docs/CONTENT_NATIVE_CONSUMER_20260925.md)
- [原生 QQ 撤回通知与来源失效](docs/CORE_PLATFORM_RECALL_20260925.md)
- [关系与情绪提案、审阅采用及跨会话延续](docs/CORE_RELATIONSHIP_PRODUCER_20260925.md)
- [群旁听与选择性参与](docs/CORE_GROUP_PARTICIPATION_20260925.md)
- [原生工具目录与模型预算](docs/CORE_TOOL_CATALOG_20260925.md)
- [Image 原生生成、采用与投递](docs/CORE_NATIVE_IMAGE_DELIVERY_20260925.md)
- [无 V1 独立运行验收](docs/NATIVE_INDEPENDENCE_ACCEPTANCE_20260925.md)
- [整合前实施历史](docs/IMPLEMENTATION_HISTORY_20260925.md)
- [目录职责](docs/REPOSITORY_LAYOUT.md)
- [小屋源码与工作区构建](pages/陪伴小屋/README.md)

```powershell
python -X utf8 tools/sync_framework_page.py
python -X utf8 tools/sync_framework_page.py --check
python -X utf8 tools/build_v2_release.py --output <安装目录以外的交付目录>
```

仅构建本体可加 `--core-only`。开发期间只做必要的最小检查，完整测试留待从当前源码构建交付包后统一进行；宿主测试使用 AstrBot 自带 Python，并把 `backend/app` 加入该进程的 `PYTHONPATH`。测试夹具在 SDK 导入前切换至临时数据根，模型和平台使用本地替身。所有文本采用 UTF-8、无 BOM、LF。
