# 旧版功能指令执行闭环核对（2026-10-22）

核对对象：`astrbot_host/functional_commands.py`（未提交的 V1 指令兼容层）与 V2 当前工作树。只读核对为主，本轮只落地「清空记忆」。

## 结论

兼容层此前只做「识别 + 注入提示词」：工具型指令要求模型调用现有工具，管理型指令统一提示去「陪伴小屋」，没有任何程序侧副作用与回执。评审的三档判断成立，差距集中在第二档。

本轮把「程序执行 + 机器回执」作为管理型指令的唯一形态：能在聊天内安全执行的，由程序执行后把事实回执交给模型转述；不能执行的，明确回「未执行」并给入口，绝不靠提示词冒充完成。

## 第一档：已有后端，保留并做端到端验收

| 指令族 | 现有后端 | 当前行为 | 处置 |
| --- | --- | --- | --- |
| 日程查询/增删改 | `calendar_tools.py`、`CalendarService` | 指令要求模型调用 `companion_v2_calendar_query/command` | 保留；回执以工具结果为准 |
| 日记/梦境/活动历史 | `role_work/timeline/tools.py` | 同上（`companion_v2_role_timeline_query`） | 保留 |
| 记忆/共同经历/熟人资料 | `memory/tools.py`、`acquaintance` 工具 | 同上 | 保留 |
| 群黑话/群片段 | `semantic_service` 群工具、`memory/group` | 受群 scope 与授权过滤 | 保留，不声称完整群观察 |
| 生图/改图 | `image_generate`、`image_edit` 工具与投递链 | 要求实际调用并核对回执 | 保留 |
| 诊断/运行检查 | `diagnostics` 工具 | 只认 inspect 的当前证据 | 保留 |

仍缺的统一契约：授权不足、工具不可用、模型未调用、执行失败四种结果必须在回复里如实区分。第二轮已把该契约作为 `_RECEIPT_CONTRACT` 统一追加到所有工具型指令（日程、时间线、记忆、熟人、群上下文/黑话/片段、生图/改图、诊断、删除话头），并有测试逐类断言。

## 第二轮补充：未完话头删除

- 工具面新增 `memo.delete`（参数 `memo_id`、`expected_revision`），只在成功回执 `state=deleted` 后模型才能说已删除；`memo.delete.commit` 仍是内部授权动作名，但不再作为工具暴露。
- 授权动作从 `memo.delete.commit` 收敛为 `memo.delete`，`DEFAULT_ACTIONS` 同时保留旧名以兼容既有 grant；`AgendaService.change_memo` 继续做 revision 校验与逻辑删除。
- 「话头删除 / 删除话头 / 未完话头删除 / 删除未完话头」独立为 `open_loop_delete` 指令，要求先 `memo.list` 找原件再删；找不到、匹配多条或未授权时如实说没删。
- 测试：`tests/test_agenda_tools.py` 覆盖新工具、旧动作不再暴露、过期 revision 失败；`tests/test_agenda.py` 与 `tests/test_core_reply_tools.py` 同步授权清单。

## 第二档：需要补齐（逐项状态）

| 指令族 | 现有后端 | 本轮处置 |
| --- | --- | --- |
| 清空记忆 | `MemoryManagement.preview_clear/clear`（管理页绑定 operator） | **已实现聊天执行**（见下） |
| 开关群 LLM | 无「本群临时封锁」状态；`group_wakeup_enabled` 只关自主候选，@/引用/唤醒词仍会回复 | **已实现群内命令**（见下） |
| 全部重置 | 无聚合重置服务；只有 `reset_conversation_window`、记忆 clear、语义 reindex | **已实现聊天执行**（见下） |
| 重要日期 | `proactive.contact.important_dates`（JSON，≤32 条，公历/农历） | **已实现**：列表/添加/删除，走配置读写与回执 |
| HDSI 操作与统计 | 无旧版窗口实验；小屋「状态维护 → 日程模式」 | 维持降级说明 |
| 答疑建议确认/取消 | 诊断/配置工作流在 Dashboard | 维持引导 |
| 未完话头删除 | `AgendaService.change_memo(action="delete")` | **已实现**：新增 `memo.delete` 聊天工具（逻辑删除，回执 `state=deleted`） |
| TTS 语种 | `conversation.presentation.voice_language`（zh/ja/en） | **已实现**：写窗口配置并回执语音开关状态 |
| 表达/关系/主动路由/城市/衣柜/生图 API/QQ 空间/新闻/现实触及 | 各域配置与页面 | 维持引导，按批次接 |
| 群状态/气氛/关系网/成员画像 | 仅 `group_memory`/`slang` 有限查询 | 维持「只按可见材料作答」 |
| 群任务 | 页面与工作区 | 维持引导 |

## 第三档：不执行，只识别并说明

- 隐藏口令：`retired_secret` 明确拒绝，不检索、不拼凑、不声称重置（已有测试）。
- `全部重置`、`忘记我`、改配置、临时封锁群 LLM：在补齐授权/范围/回执前，一律不得说成已执行；`忘记我` 与 `未完话头删除` 仍走引导。

## 首批实现：清空记忆

聊天内两段式确认，状态无关（不依赖服务重启后的内存）：

1. `陪伴 清空记忆` → `preview_clear` 返回计数与 `revision_token`；程序用 `MemoryManagement.confirmation_code(token)` 派生 6 位确认码，回执写明数量、确认方式与「逻辑遗忘、保留修订、不物理删除」。
2. `陪伴 清空记忆 确认 <CODE>` → 重新预览并比对确认码；不一致回「未执行：确认码不匹配或记忆内容已变化」，一致才 `clear(expected_revision_token=..., operation_key=chat-clear-<digest>)`。令牌随记忆行与授权版本变化，旧预览自然失效。

授权沿用现有记忆访问检查：私聊 scope、本人 audience、`memory.forget` 能力（CORE 或逐人 grant），不满足时回具体原因。

改动：

- `companion_v2/memory/management.py`：`_clear_token`、`preview_clear`、`list` 改用 `writer.caller(context)`，支持 `operator=None` 的聊天自证；新增 `confirmation_code`。
- `astrbot_host/functional_commands.py`：`FunctionalCommand` 增加 `argument`；`清空记忆` 独立为 `memory_clear`；新增 `execute_functional_command`/`functional_command_receipt`，按事件去重，回执以独立 system 块注入。
- `main.py`：`on_llm_request` 传入 application 与本轮 context。
- 测试：`tests/test_functional_commands.py`、`tests/test_memory_polish.py`；与后两项合计 43 项通过（AstrBot 自带 Python、`backend/app` 入 `PYTHONPATH`）。

## 三项实现细节

### 开关群 LLM（已实现）

- 状态：`companion_v2/conversation/group_llm_block.py`，写 `runtime_metadata`，键按群四元组（platform/account/bot/group）派生，值含 `started_at`、`operator`、`reason`、`revision`；零 schema 迁移，重启后仍保持。
- 闸门：`main.py` 群分支在候选准入之前拦截，命中即 suppress + `_record_no_reply("group_llm_blocked")`；`multi_session.authorize_core_reply` 开头再拦一次，覆盖已经开始的模型请求和逐段发送。
- 命令：`astrbot_host/group_command.py` 在模型之前解析并执行；`authenticate_notice_route(..., ScopeKind.GROUP, expected_post="message")` 校验原路由，CORE tier 才能关/开，`LLM状态` 任何人可读；回执用 `send_text_notice` 平台直发，不进入模型、不建对话批次。
- 回执：关闭含操作者与恢复方式；重复关闭回「没有重复更改」；恢复含封锁时长；无封锁时恢复回「本来就是正常的」。
- 测试：`tests/test_group_llm_block.py` 覆盖状态生命周期、群隔离、重放与时长边界；`tests/test_functional_commands.py` 覆盖 7 个别名与动作映射。

### 全部重置（已实现）

- 入口：`astrbot_host/reset_command.py`，在私聊分支、建批次之前拦截；`prepare_core_reply_context` 只做路由与身份解析，不建会话批次，因此窗口重置不会取消确认消息自身。
- 范围：当前私聊会话窗口 + 该关系记忆事实。人格、模型与连接配置、日历、关系资料不动；平台消息、日志与备份不物理删除。
- 授权：`is_core_subject`（`astrbot_host/command_authority.py`）要求 CORE tier，否则回「未执行」。
- 确认：预览返回总数/活跃数；6 位确认码由 `reset-all-confirm.v1 + window.key + 记忆预览令牌` 派生，内容变化即失效。确认后先 `reset_conversation_window`，再 `MemoryManagement.clear`，两者共用同一个 `chat-reset-<digest>` 幂等键。
- 回执：全部成功报取消批次数与遗忘条数；窗口失败报「未执行」；窗口成功而记忆失败报「部分完成」，绝不合并成「全部完成」。
- 测试：`tests/test_reset_command.py` 覆盖预览、错误确认码、正确确认码的执行顺序与幂等键、别名面。

## 第三轮补充：重要日期

- 指令拆成 `dates_list` / `dates_add` / `dates_remove`，在 `on_llm_request` 由程序直接读写 `proactive.contact.important_dates`，回执单独注入；模型只转述。
- 解析同时接受「5月20日」「2026-11-02」「12/24」「农历8月15」；年份只用于识别，不写入（纪念日按每年重复）。日期不存在、缺名称、超过 32 条、重复项都会明确回「未执行/未添加/未删除」，不做猜测。
- 写入走 `ConfigurationService.patch`：读快照拿 `edit_token`，`OperationRef` 归属 `proactive.contact`，`configuration.write` 授权由现有 `_authorize` 校验（窗口 subject 必须是本人）。冲突、越权、格式错误按 `_FAILURE_TEXT` 转成中文回执。
- 删除先按名称精确匹配，再按「名称+日期」，再按纯日期；命中多条要求说得更具体，找不到明确说没删。
- 测试：`tests/test_important_dates_command.py` 覆盖解析与列表/添加/重复/农历/按日期删除/歧义不删；命令层合计 51 项通过。

## 第四轮补充：TTS 语种

- `陪伴 TTS语种 日语/英语/中文/默认` 由程序写 `conversation.presentation.voice_language`，直接走 `ConfigurationService`（窗口 target + `configuration.write`，私有 owner 免逐人 grant），不经过 `ReplyManagement`——后者基于 `RoleLifeManagement`，要求 CORE，普通私聊用户会被误拒。
- 只写入固定值 `zh/ja/en`，不会把无法识别的词存进配置；同值回「没有更改」，语音开关关闭时回执会说明「开启后才会按该语种朗读」。
- 测试：`tests/test_voice_language_command.py` 覆盖名称映射、未知值不写、同值不写、开关关闭提示。

## 剩余第二档的处置（识别并引导，附原因）

以下指令保留识别，但只给准确入口，不模拟执行——它们要么缺少聊天内安全完成所需的信息，要么与 V1 语义不同：

| 指令族 | 不执行的原因 |
| --- | --- |
| 表达与关系设置（昵称/称呼/语气/风格/表达学习） | V2 对应 relationship profile 与表达风格审阅流，逐字段写入会绕过草稿与审阅；“语气/风格”没有 V1 的单一字段 |
| 主动路由（绑定/查看/解绑主动会话） | V2 目标是宿主固定配置（target/persona），改动需重启并影响整个安装，不能按单条私聊命令热改 |
| 城市（绑定/查看/解绑） | `role.state.planning_weather_location` 需要坐标或地图选择器；只有城市名不足以取天气，写入后会留下无法使用的配置 |
| 衣柜/穿搭 | 需要参考图素材与生成链路，聊天命令无法等价 |
| 生图 API | Provider 与密钥配置属安全配置，不在聊天暴露或轮换 |
| QQ 空间 / 新闻 / 现实触及 | 分别需要账号授权、资讯来源配置、设备授权，属于页面与提供方管理 |
| 撤回消息/转述 | V2 有撤回治理视图；转述会复制他人消息内容，隐私风险高，明确不迁移 |
| HDSI / 人格重置 / 查看提示词 | V2 无旧版窗口实验、无人格重置服务；提示词只有 V2 任务提示层且需页面查看 |

## 交付包与统一验收（2026-10-22）

从当前源码构建：`tools/build_v2_release.py --output C:\Users\99505\.astrbot\release-candidates\companion-v2-7.0.0-20261022-commands-r2`，产物 `astrbot_plugin_private_companion-7.0.0.zip`（23,412,697 字节，sha256 `d5c8dba4ae3545fed2b3da7827647cdfa6311b875f6f6f55c36d664d49f67fed`）。

- 第一次构建的 `--host-check` 发现真实回归：`main.py` 的群封锁检查对测试替身 target 直接取 `.platform_id` 抛 `AttributeError`，包内 `test_main_no_reply` 3 项报错。修复为 `status_for_target` 只接受完整群四元组、否则返回 `None`，并给群命令的 `target.group_id` 取值加保护。
- 重建后 `tools/verify_v2_release.py --host-check` 全绿：哈希与语法通过、单一 Star、唯一公开页「陪伴小屋」、7 项原生扩展、无外部插件依赖；迁移验收 **544 项通过**；重载检查 5 次启动 / 3 次禁用启用、0 重复 handler、0 重复路由；宿主检查 4 条生活路由、停机后路由清理、自动启动与原生开关正常，模型调用 0、平台调用 0、数据根隔离。
- 解包副本上运行本次新增的命令层测试（`test_functional_commands`、`test_important_dates_command`、`test_voice_language_command`、`test_group_llm_block`、`test_reset_command`、`test_memory_polish`）**54 项通过**，证明新模块确实进入交付包。

## 验收口径

本轮对「清空记忆」「开关群 LLM」「全部重置」及依赖的 `MemoryManagement`、`authorize_core_reply`、`main.py` 拦截顺序负责。`tests.test_reset_command`、`tests.test_group_llm_block`、`tests.test_functional_commands`、`tests.test_memory_polish` 共 43 项通过；宿主回归 `tests.test_astrbot_multi_host` 44 项通过（跳过 1）。

第二轮（未完话头删除与回执契约）：`tests.test_agenda`、`tests.test_agenda_tools`、`tests.test_core_reply_tools`、`tests.test_role_tool_loop`、`tests.test_functional_commands` 共 102 项通过；随后 `tests.test_functional_commands`、`tests.test_agenda`、`tests.test_agenda_tools` 复核 62 项通过。未构建交付包、未重载在线插件、未做真实模型或平台发送。

宿主 `tests.test_astrbot_staging_bootstrap` 的 7 项错误与 `tests.test_astrbot_staging_host` 的 1 项失败，已在 HEAD 基线的独立 worktree 复现，属既有环境问题（bootstrap 预检未进入），不计入本轮改动结论。

第三轮（重要日期）：`tests.test_important_dates_command`、`tests.test_functional_commands`、`tests.test_memory_polish`、`tests.test_group_llm_block`、`tests.test_reset_command` 共 51 项通过。`tests.test_proactive_date_events` 的 4 项农历失败经确认为环境缺少 `lunardate`/`lunarcalendar` 可选依赖（`importlib.util.find_spec` 均为空），与本轮改动无关。

第四轮（TTS 语种）：在第三轮批次上加入 `tests.test_voice_language_command`，六个模块共 54 项通过。
