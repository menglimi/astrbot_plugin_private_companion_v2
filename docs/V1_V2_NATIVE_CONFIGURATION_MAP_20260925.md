# V1 配置盘点与 V2 原生配置分类

核对日期：2026-09-25。只核对 V1、V2 源码与 `_conf_schema.json`，不读取或迁移 V1 用户配置、凭据和数据。功能是否接通以 [V1/V2 源码功能差距核对](V1_V2_FUNCTIONAL_GAP_AUDIT_20260925.md)为准；这里解决配置应放在哪里，以及 AstrBot 原生配置页如何排列。

V1 schema 有 748 个顶层键，其中 47 个是可见的 `object` 配置组，701 个顶层标量均隐藏，包含旧键/兼容镜像和内部标记。它们不是 748 个需要迁入 V2 页面或原生配置的新选项。V2 当前原生 schema 只有 7 组：单/多目标接线、模型、回复形式和运行边界；生活、关系、记忆等设置由领域服务和陪伴小屋按实际接入程度管理。

V2 相对 V1 的配置结构改进，是把混在“基础配置”里的目标身份、模型与预算拆开；把群聊目标接线与群内语义行为分开；让角色/业务配置由各领域 owner 维护适用范围、来源和采用回执；并让可选能力提供方保留自己的凭据与专属参数。这些是配置责任的调整，不代表 V1 所有行为已经在 V2 完成。

## V1 功能域与 V2 归属

下表覆盖 V1 全部 47 个可见分组。一个 V1 分组可能同时包含已经接通、部分接通和未接入的字段，因而“归属”不等于已经实现，也不要求逐字段照搬旧开关。

| 功能域 | V1 可见分组键 | V2 归属与当前差异 |
| --- | --- | --- |
| 宿主、权限与模型 | `operation_access`, `basic_config`, `model_assignment_config` | 原生 `staging`/`target`/`multi_host` 绑定入口、目标、角色和投递；`model`/`runtime` 管共享模型及预算。V2 显式区分私聊、群聊授权和稳定记忆归属。V1 细分模型分流和所有操作权限不能视为已经等价迁入。 |
| 对话接收与表达 | `recall_config`, `message_debounce_config`, `private_understanding_config` | 原生 `segmentation`、`voice_reply` 和 `runtime` 仅管宿主通用回复形态、等待与超时。原生撤回、消息合并和对话理解归会话领域；V1 的每项防抖/理解策略仍需按消费者逐项核对。 |
| 主动联系 | `proactive_reach_config`, `balance_awareness_config`, `private_followup_config`, `proactive_dedup_config`, `proactive_generation_config`, `timer_config`, `daily_creative_config` | 归小屋的主动联系、计划及相关领域配置。V2 已有空闲联系、真实活动/书写回执、服务余额和外部 JSON 资讯候选与来源复核；资讯接口由宿主环境提供，领域偏好默认关闭。作品分享及 V1 全部频控尚未等价接入。创作项目配置仍由可选 Content 提供方拥有。 |
| 记忆与关系 | `memory_habit_config`, `emotion_relationship_config`, `external_memory_config` | 归 V2 记忆、关系领域的配置与审阅操作。来源记忆、语义召回和待审关系/情绪提案已有链路；V1 本地画像、表达习惯和外部记忆插件协同不因出现记忆页面而自动完成。 |
| 群聊与社会观察 | `group_observation_config`, `forward_message_config`, `group_scene_config`, `group_wakeup_config`, `group_high_intensity_config`, `group_slang_topic_config`, `group_relationship_config`, `relay_bridge_config`, `group_interject_config` | 原生 `multi_host` 只放群目标、人格映射、投递模式与公共能力；群内语义规则归群会话/记忆领域。V2 已有群旁听与选择性参与、合并转发输入、群公共记忆和有证据的黑话学习；主动插话、跨群转述及完整社会画像仍有差距。 |
| 生活、成长与环境 | `skill_growth_config`, `life_schedule_config`, `schedule_detail_config`, `humanized_state_config`, `dream_diary_config`, `weather_config` | 归小屋生活、状态、日历、成长领域。V2 已有计划管理、默认关闭的原生规划、阅读/睡眠、日记/梦境和审阅式进展；`planning_annual_calendars` 可由管理员明确配置逐年放假、调休和节气供规划参考。角色地点的当前天气、显著变化及官方预警生产链已有源码接线；自动年度数据源和真实天气/QQ 验收仍缺。 |
| 媒体、互动与展示 | `photo_action_config`, `screen_action_config`, `poke_action_config`, `reactive_poke_config`, `voice_action_config`, `voice_playback_config`, `auto_voice_config`, `presence_sync_config`, `wardrobe_config` | 原生 `voice_reply` 只管当前 TTS 附加回复。图片原生执行和 QQ 展示归各自领域；Image/Screen 等可选提供方仍持有自己的配置和凭据。衣柜、戳一戳、V1 主动语音及本机播放不应凭旧 schema 在 V2 新增空开关。 |
| 外部见闻与阅读 | `bilibili_config`, `news_config`, `web_exploration_config`, `qzone_config`, `reading_archive_config` | 已保存材料的阅读归 V2 生活/记忆领域；管理员配置的 HTTPS JSON 资讯源已接默认关闭的私聊主动分享。搜索、B 站、完整网页阅读和 QQ 空间仍缺生产/消费链。资讯源 URL 与凭据由宿主环境管理，不写入对话或 V2 原生 schema。 |
| 实验与兼容 | `experimental_motivation_config`, `legacy_compat_config` | 现实设备能力由可选 Reality 提供方管理；实验项按实际实现另行登记。V1 兼容字段只服务明确的迁移规则，不在 V2 新安装的原生页面重建镜像。 |

## V2 原生配置页顺序

AstrBot 以顶层 `object` 展示插件配置组。保留现有组键和所有子字段路径，让已保存的 V2 值继续被 `HostSettings`/`MultiHostSettings` 读取；只整理顺序、标题和提示。

| 顺序 | 原生组键 | 页面职责 | 生效范围 |
| --- | --- | --- | --- |
| 1 | `staging` | 单目标启用、运行档 ID 与私聊投递 | 仅单目标；与 `multi_host.enabled` 互斥 |
| 2 | `target` | 单目标平台、账号、参与者、Bot/角色/人格 | 仅单目标 |
| 3 | `multi_host` | 多目标安装 ID、私群目标、人格映射、投递与公共能力 | 仅多目标；不读取 `target` 的身份字段 |
| 4 | `model` | AstrBot Provider、任务提示、Token 及费率 | 两种宿主模式共享 |
| 5 | `segmentation` | 回复分段策略 | 两种宿主模式共享 |
| 6 | `voice_reply` | TTS 附加回复开关 | 两种宿主模式共享 |
| 7 | `runtime` | 预算、等待、超时、并发与任务容量 | 两种宿主模式共享 |

原生配置是启动接线，不是陪伴小屋业务配置的第二份正本。保存并重载原生设置后，仍须在小屋宿主管理中探测、初始化及启动；真实投递仍需独立授权。已初始化运行档的身份和部分模型/分段参数受固定指纹约束，改描述或排序不会解除这些约束。

## 后续新增配置的放置规则

1. 平台目标、账号/人格映射、投递模式，以及所有目标共享的模型和运行资源，放入原生宿主组；不在小屋另存一份可写镜像。
2. 生活、记忆、关系、主动、群语义及媒体行为按领域 owner 和适用安装/角色/会话范围登记，再由小屋展示有效值、来源和采用状态；配置字段须有真实消费者。
3. 第三方提供方的凭据、后端地址与提供方专属参数保留在该插件配置中。V2 只保存所需的引用、授权和能力状态，不复制密钥。
4. 新字段先确认稳定键名、默认值、权限、scope、写入 owner、消费者及生效时机。未接通的 V1 功能只在差距清单登记，不显示成似乎可用的开关。
5. 已发布 V2 字段若需迁移，先提供兼容读取与明确升级路径，再改 schema；不能单靠移动 JSON 分组，否则 AstrBot 会按新路径补默认值，旧配置的实际含义会丢失。
