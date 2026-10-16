# CORE-06 自动联系机会与后台发送历史接续

日期：2026-09-23。继[主动联系偏好与执行链](CORE_PROACTIVE_CONTACT_SLICE.md)，本批把首个自动机会生产者、窗口及关系级联系额度、未回应背景和后台已发历史接入统一宿主。测试使用临时 V2 数据、替身模型和发送器；没有在线重载或真实模型、平台请求。跨窗口额度的具体合同见[关系级额度切片](CORE_RELATIONSHIP_CONTACT_BUDGET_SLICE.md)。

> **额度合同后续已调整（2026-10-16）。** 唯一主动联系硬上限是每个私聊窗口的每日实际联系数，按免打扰时区的本地午夜刷新。模型决策与人格复核调用只作独立用量统计，不设置额外次数上限；跨窗口关系级联系额度已移除。Provider Token/费用预算仍按模型成本策略生效。

## 当前额度合同

`max_contacts_24h` 是唯一主动联系次数上限，按完整私聊窗口分别配置，范围为 0–100。已确认发送计入额度；待回执、unknown 和未解决的投递预留名额，可信回执确认未发送后释放。模型选择 skip、生成失败和人格复核调用都不增加实际联系数，也不会消耗另一项主动次数额度。模型决策、复核和实际发送仍分别显示统计。真实 Provider 调用仍可能受模型 Token/费用预算、模型故障、权限、免打扰、节奏和来源时效影响；这些不是额外联系次数上限。

## 当前执行链

```mermaid
flowchart LR
    Input[宿主已接纳的私聊与原人格] --> Timer[当前空闲时段]
    Timer --> Policy[联系偏好与独立额度]
    Policy --> History[经原 owner 复核的已发背景]
    History --> Model[公共后台模型：发送或跳过]
    Model --> Queue[原机会任务与公共投递]
    Queue --> Check[发送前重验新输入、权限与来源]
    Check --> Receipt[真实投递回执]
    Receipt --> Next[下一次主动联系与普通回复]
```

`ContactSchedule` 由 `CompanionApplication` 的现有唤醒循环调用。每次只扫描最多 16 个窗口的最新宿主管理批次，扫描游标跨过关闭或无权限的窗口；只在最新私聊流程完成、原输入仍可读且配置允许时提出机会。原 Bot、账号、角色绑定、完整窗口、受众与人格提示均从该批次复核，不重新认领旧角色的数据。

首批自动生产者负责空闲后的 `chat` 机会。它给角色一个可跳过的交流意向及最近原输入，不生成用户消息，不宣称角色完成了生活活动。其他 12 类目的仍可通过显式可信机会入口使用；生活、资讯、环境等领域的自动生产者需后续接入。

机会按最近接纳输入、配置的空闲时间和间隔确定当前时段，时段有效期最长五分钟。重启只评估当前时段，已提交的稳定任务 ID 和持久联系决定阻止重复，过往时段不补发。后台名额不足时等待下一次有界扫描；已提交但未能领取的原机会会结束，不悬挂等待一份已失去原生成输入的任务。

生成期间或发送边界接纳新输入、发生撤回、换绑、来源撤回或偏好改变，都会使旧决定失效。新输入按实际接纳顺序辨认，因此迟到且带较旧时间戳的消息也能中断旧联系。已产生的模型用量保留；平台 unknown 继续沿原回执核账，不重发。

## 配置与额度

所有新增字段属于公共 `proactive.contact` 分组，采用原安装 → Bot 内角色 → 角色/用户关系 → 完整窗口继承、CAS、reset 和采用回执。以下为省略 `proactive.contact.` 前缀的字段名：

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| `automatic_enabled` | `false` | 开启空闲私聊机会生产；还需原 `enabled` 与 `chat.enabled` 允许。 |
| `idle_seconds` | `900` | 最近接纳输入后至少等待的秒数；允许 0–86400。 |
| `interval_seconds` | `3600` | 自动机会时段间隔；允许 60–604800 秒，不是权重或触发概率。 |
| `max_contacts_24h` | `3` | 当前完整窗口每日实际联系上限；允许 0–100。 |

历史实现中的双层联系/决策额度已退役。当前唯一主动次数上限为每窗口的 `max_contacts_24h`，在本地自然日刷新。模型调用单独统计，不阻止未达到实际联系上限的机会；模型 Provider 的 Token/费用预算仍独立保护真实成本。

同一配置采用回执只在版本或运行代变化时更新，普通扫描不每秒重写相同回执。开启普通联系不会自动开启这一新增生产者；两个开关都沿现有配置服务设置，实际发送仍需原宿主与平台授权。

## 已发历史与未回应

新增 `BackgroundHistory` 按原完整上下文读取公共后台投递。只有带匹配原操作、sender、受众、哈希、平台引用和投递时间的 `delivered` 回执可提供正文。accepted、unknown、未发送草稿和 skip 不进入已发材料，重复或迟到回执不会制造重复历史。

首批历史 owner 为主动联系与 Agenda 提醒。主动历史读取不依赖当前联系开关、暂停或机会是否过期，仍要求原正文、来源、受众和权限有效；提醒由原 Agenda owner 复核原准备版本。暂停未来联系不会改变过去确实说过什么，来源失效则继续阻止正文使用。

普通回复在封存输入时固定历史引用；主动决策也固定相同引用。持久快照只保存投递 ID、回执和哈希，不另存一份正文。每次生成、模型返回与发送前均通过原 owner 重读；来源撤回会沿主动消息使用过的历史依赖传播，阻止通过后续生成消息重新暴露旧内容。

上下文最多选取最近 32 条候选中的 8 条、正文材料共 8192 字符；每条候选的祖先读取也有明确上限，无法在本次有界读取内证明的候选不进入新上下文。已封存引用后来失效时结束旧生成或旧投递，不静默更换为其他材料。

提示词将这些材料标为角色曾发送的背景，保留发送时间、未知阅读状态及提醒语境，不发布成用户事实 Source。最近有效入站记录之后的确认联系次数、尚未核清的联系次数和原入站时间作为交流背景提供；未回应不表示已读、拒绝、忙碌、生气或需要安慰。继续联系或 skip 的表达选择由原角色完成。

可信读取入口为 `application.background_history.recent(context)`；原 `messages.history()` 的前台分段游标继续保留原合同。后台历史通过独立投影接入两类生成，不向旧前台表伪造批次。schema 仍为 v20，没有新增表、V1 数据访问或在线升级。

## 本地验证

新增 33 项测试覆盖真实时钟自动唤醒、分页公平性、默认关闭、原人格和来源、重启去重、错过时段、skip、暂停/免打扰、换绑/撤回、新输入中断、后台容量竞争、独立额度、24 小时边界、关系额度跨窗口共享、unknown 回执持续占额及配置范围、顽固 worker 停机、可信历史回执、跨窗口隔离和依赖撤回传播。

以下三组定向验证按测试 ID 去重共 **298 项通过**：主动/历史及消息/关系/工具 136 项，宿主/提醒/生活共存 70 项，AstrBot 加载、停机、路由注销和隔离 92 项。最终配置采用优化后，主动及历史相关 68 项再次通过。另补验了并行接入的 `tests.test_role_life_context`，本次运行 23 项通过；该模块由另一窗口继续维护。21 个本批涉及文件通过 UTF-8、无 BOM、LF、末尾换行和 Python 语法检查。相关命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_contact_scheduling tests.test_background_history tests.test_proactive_contacts tests.test_proactive_preferences tests.test_conversation_messages tests.test_relationship_context tests.test_role_tool_loop -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_host_application tests.test_host_recovery tests.test_host_external_tools tests.test_agenda_background tests.test_role_life_host tests.test_role_life_runtime tests.test_role_life_api tests.test_role_journal_host -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging tests.test_astrbot_staging_config tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap tests.test_astrbot_model_wire tests.test_astrbot_native tests.test_isolation -q
```

当前范围是私聊空闲机会、窗口及关系级滚动额度与受治理的文本历史。更多领域机会、群聊/转述、媒体、正式非 staging 宿主和线上运行验收仍未完成；本批不构成整个插件的替换发行。
