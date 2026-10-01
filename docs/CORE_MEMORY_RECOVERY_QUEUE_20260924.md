# V2 记忆恢复队列与连续整理

本切片接续[模型输出容错与恢复](CORE_MEMORY_OUTPUT_RECOVERY_20260924.md)，修复已经保存失败记录后，仍可能因重启、日程更新、重复选材或管理队列不可达而无法继续整理的问题。代码已落入 V2 主树；本批不新增 SQL 表或 schema 迁移。

## 已修复的行为

| 场景 | 原问题 | 现在的行为 |
| --- | --- | --- |
| 已准备批次尚未调用模型 | 新批次可以再次选中同一材料 | prepared 与运行中、待解析、待写入及失败批次一起保留材料占用；重启后仍有效 |
| 多批次处理待确认提案 | 每次都取最早 32 项，重复占用，后面的提案不可达 | 在数据库取数上限之前排除已占用 operation ID；第 33 项可以进入新批次 |
| JSON 整批失败后修复 | 重新读取当前所有 pending，混入失败后才出现的新事项 | 只重新读取原批次的 pending ID；已有部分回执时继续限定原未完成项 |
| 日程修改或暂停后启用 | 修复批次继承过期 schedule revision，永远无法运行 | 新修复批次引用当前仍启用、仍属于原账号/角色/会话的日程版本及角色提示；原记录保持原版本 |
| 日程仍暂停 | 会先创建一个注定无法执行的子批次 | 在创建前返回 memory_schedule_changed，不占用新的修复关联；恢复启用后同一操作键可以再提交 |
| 重新认证或无关授权更新 | actor.policy_revision 变化让旧队列消失或重新创建日程 | 使用已有 TaskContext.key 识别相同执行归属；现行身份、权限与来源仍逐次校验 |
| 排队任务过期或已终止、尚未调用模型 | 批次永远停留 prepared，旧 task 无法再次启动 | 核对任务终态、运行名额和模型账本后转为已知失败，可显式创建新修复批次 |
| 待处理批次超过 50 条 | has_more 没有配套续页入口 | 增加 after_id / next_cursor；锚点完成或转交子修复后仍可继续翻页 |

材料占用同时包含批次来源和待确认提案的证据。修复时保留原来源，不重新抓取新的聊天窗口。新批次可继续处理没有被占用的新来源；不会把“暂时由旧批次保留”当作“已经处理”。修复本身也不把父批次占用的材料计为新的 deferred_sources，修复完成后的日程可以正常推进覆盖时间。

此次调整属于身份、调度、持久回执和输入归属校验。事实是否值得记住、如何概括、能否采用仍沿用现有角色提示与模型判断，没有加入关键词分类或固定记忆内容。

## 恢复与授权边界

- 相同 TaskContext.key 仍包含账号主体、账号绑定 ID/版本、完整角色绑定和受众。只兼容身份记录中的政策版本变化，不跨账号重绑、角色切换或会话读取队列。
- 新修复按当前记忆配置和当前启用日程准备，执行前及写入前仍核对版本。修复准备后再暂停日程，仍阻止模型调用与保存。
- 已派发而结果未确认的调用保持未知，不能因为任务过期就重放。新加的 prepared 核对仅在任务已经终止、没有持有运行名额、账本证明未开始或已确认丢弃时允许显式重试；检测到不确定调用则保留 running。
- 确认未调用模型的过期任务记录 `memory_task_not_started`，不触发自动格式修复。自动格式修复仍只适用于既有格式错误集合，最多一次。
- 列表可在记忆功能关闭后由认证核心操作者查看；是否能继续执行仍以当前权限、配置、来源和版本为准。管理接口不返回 raw_output。

## 管理 API 接线

前缀为 `/astrbot_plugin_private_companion_v2/memory`。

1. `GET /reflections?limit=20` 读取首批未完成末端记录。
2. 返回 `has_more=true` 时，把 `next_cursor` 原样作为下一次请求的 `after_id`：`GET /reflections?limit=20&after_id=...`。
3. `next_cursor=null` 表示当前已到末页。游标锚点使用持久批次 ID，按 `(created_at, batch_id)` 前进；每次请求重新验证管理员和原执行归属。
4. `GET /reflections?batch_id=...` 保持单批次核对；不能与 after_id 混用。重复参数、超长游标和跨范围锚点会被拒绝。
5. `POST /reflections/retry` 保持原合同 `{"batch_id":"...","operation_key":"..."}`，继续复用原恢复结果或已关联修复回执。

这是动态队列分页，不封存跨请求快照。翻页期间新出现的修复子批次可通过刷新首批查看；未知批次不会因翻页被重新执行。本批没有制作新的管理页面。

## 宿主联调修正

定向宿主回归发现新增角色状态模块在 `RoleStateService.settings()` 中使用参与者身份读取 core-only 配置组。即使状态能力默认关闭，staging 启动绑定也会被 `core_access_required` 阻止，连带使记忆 API 的执行验收失败。

已作最小修正：可信运行时先核对当前私聊上下文，再从同一配置 owner 读取有效值和版本令牌；读取/写入角色状态仍有原领域权限检查，管理配置仍由公共配置服务要求核心管理员。没有给普通参与者授予管理权限。新增用例验证普通参与者读取运行值、管理员更改即时生效、普通参与者即使获得普通配置 grants 也不能管理核心字段，以及账号重绑后拒绝旧上下文。

## 定向验证

使用 AstrBot 自带 Python、模拟模型/发送器和临时 V2 数据根。按测试 ID 去重共 **124 项，最终每项都有通过记录**，其中本批新增 **17 项**：恢复队列 14 项、管理分页 1 项、宿主配置消费边界 2 项。

- 七个最初缺口均先用失败用例复现；另补排队到期后的恢复用例，确认原实现一直停留 prepared。
- 记忆恢复队列、容错、反思、写入、管理、私聊上下文、权限边界、宿主恢复及 SDK 路由共 122 项组合检查，112 项通过，10 项因上述宿主配置读取问题失败。
- 修正后 SDK 宿主与记忆 API 22 项全部通过；新增配置边界用例最初暴露夹具缺少普通配置 grant 和配置 owner 不匹配，修正夹具后 2 项通过。没有放宽生产权限判断或超时时间。
- 早期两轮曾遇到共享工作树宿主依赖尚未写完造成的导入/初始化失败，日志保留；相关测试在依赖完整后重跑。其他窗口加入的角色状态、日历、平台状态、订阅和回执功能不计为本批实现成果。

复验范围：`test_memory_recovery_queue`、`test_memory_recovery`、`test_memory_reflection`、`test_memory_host_api`、`test_memory_writer`、`test_memory_boundaries`、`test_memory_management`、`test_memory_conversation`、`test_memory_polish`、`test_host_recovery`、`test_astrbot_staging_host`、`test_role_state_configuration`。宿主进程设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`；SDK 导入的数据根由测试夹具指向临时目录。

本机证据目录：`D:/codex/workspaces/v2-memory-queue-on3_hhxl/`。主要记录为 `reproduction.log`、`expiry-reproduction.log`、`validation-final.log`、`host-final.log`、`state-settings-confirmed.log`、去重结果 `test-inventory.json` 及文件校验清单 `delivery-manifest.json`。

本批没有调用真实提供商、发送 QQ 消息、操作鼠标、重载在线插件或访问 V1 用户数据。真实模型提取质量、提供商严格 schema 兼容性和修复管理页面仍需后续验收；本地模拟通过不代表整个记忆拓展已达到 V1 全功能替代。
