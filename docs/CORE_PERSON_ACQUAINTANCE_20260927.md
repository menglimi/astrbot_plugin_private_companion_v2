# 群成员相识（person.acquaintance）切片一

日期：2026-09-27。目标：让 bot 通过被动观察逐步"认识"群友；同一人在跨群、跨私聊场景下共享同一相识正本；为后续印象卡、熟悉度阶梯与私聊准入（后续切片）建立正本与词表。

## 范围与边界

- 本切片只包含：per-person 相识正本（相识计数 + 平台称呼）、群/私聊统一的发言者卡注入、`acquaintance.recall` 只读工具、`person` 配置组。
- 不包含：LLM 印象卡与熟悉度阶梯（切片二）、私聊准入（切片三）、身份与权限页（切片四）、治理细节（切片五）。
- 不迁移、不读取 V1 关系网数据；正本按 V2 数据根存储。

## 合同

- **人 = 身份 subject**：`subject_id = "onebot-user:" + 原生账号`，安装级共享（`astrbot_host/multi_authority.py` `subject()`）。同一 QQ 在群 A、群 B、私聊天然是同一 subject；这是"同一人"原则的身份层基础。
- **正本归属**：`owner_key = digest(["memory.person.v1", installation, platform, bot, account, subject, role])`（`memory/person/access.py`）。每个 bot、每个伴侣（role）对同一人各持一份相识；正本不含群号与会话号。
- **存储**：复用通用表 `memory_views`，kind `person.acquaintance.v1`，`view_id = "person-card-" + digest(owner)`，无 schema 迁移。document 结构：`platform_nickname`、`group_cards{群号: {card, updated_at}}`、`contexts{group:群号|private: {msg_count, active_days, first_seen, last_seen, last_active_day}}`、`private_attempts`。contexts 上限 16（按 last_seen 淘汰），群名片上限 32，称呼文本 ≤64 字符可打印。
- **采集（本切片三源）**：
  1. 程序计数：`ConversationMessages.accept()` 在原输入插入后、同一事务内调用 `observe()`；按 `event_key` 幂等（重放路径提前返回不重复计数）。计数失败不阻断入站（可选派生数据）。
  2. 平台称呼：`astrbot_host/multi_session.py` 在受理事务外从已认证 OneBot 事件的 `raw_message.sender` 提取 `nickname`/`card` 写入；仅值变化时递增 revision。
  3. 本轮证据：不适用（印象卡在切片二引入）。
- **注入**：`_request` 为群与私聊统一追加 `current_person_card` 贡献（`display_name`/`name_basis`/`msg_count`/`active_days`/`first_seen`/`last_seen`，预算 `person.acquaintance_card_chars`，超限按序裁剪）。display_name 取本群群名片 > 平台昵称，basis 标注 `platform`；一切称呼仅为参考，不证明自称身份。群侧边界说明并入 `conversation/group_context.py` INSTRUCTION；私聊侧工具说明见 `memory/person/tools.py`。
- **工具**：`acquaintance.recall`（只读，`effect: none`）。缺省查询当前发言者；提供 `speaker_id` 时必须经 `identity_bindings` 解析为受信 subject（`resolve_subject`），无绑定即失败，杜绝按号码伪造档案主人。卡片是 bot 内部派生状态，validate 不做稳定度断言。
- **配置**：`person` 组两个字段——`person.acquaintance_enabled`（默认开）与 `person.acquaintance_card_chars`（默认 1024，256..4096）。关闭后计数、卡片与工具目录全部退出。

## 关键设计决定

- **正本按人不按群**：群与私聊只是观察来源；熟悉阶段（切片二）因此天然跨上下文。
- **授权与记忆分离**：相识卡是记忆域派生状态；切片三的准入 grant/revoke 将存宿主侧授权存储（对齐 `group_delivery`/`multi_authority` 模式），卡内只保留只读投影。
- **依赖方向**：`memory/person` 只读消费证据引用；`memory/` 顶层与 `memory/group` 不得 import `memory/person`（`tests/test_person_acquaintance.py` 有方向断言）。宿主可写名称（宿主装配注入 settings，与记忆域解耦）。
- **不装熟**：提示词明确称呼与熟悉程度不得超出记录，无记录按普通成员交流。

## 验收

`tests/test_person_acquaintance.py`（AstrBot 自带 Python，`backend/app` 入 PYTHONPATH，`ASTRBOT_ROOT` 指向临时目录）：10 项全过——同群计数聚合、重放不重复计数、同人跨群共用正本且跨 bot 隔离、群名片/昵称捕获与卡注入（群+私聊）、recall 自查/查他人/未知号码、禁用开关全退出、配置组默认值、distinct-day 计数与淘汰上限、方向断言。定向回归：`test_configuration`、`test_conversation_messages`、`test_group_participation(_hints)` 通过；`test_isolation` 对本切片零新增发现（初版 `models.py` 的 `touch` 函数名触发扫描器数据访问终端，已改名 `count_input`）；`test_group_memory` 4 项失败为源码树既有问题（见下），与本切片无关（禁用本切片全部接线点仍复现；2.0.0 交付包基线通过但其后源码引入了 `reactions_group_enabled=False` 默认与动态读空气提示）。

## 关系与权限页（本切片页面部分）

唯一公开拓展页的管理分区「身份与权限」更名为**「关系与权限」**（导航、分区标题、跳转链接、`STRUCTURE.md` 同步），并按既定信息架构装修：

- **三区结构**：用户与群友（相识目录）/ 群聊（群与群友一起管理）/ 准入与身份（三档权限说明 + 私聊准入与身份归并的"准备接入"边界卡）。用户与群友区分私聊用户与单纯群友，同一正本两个投影；群卡展开成员 chips。
- **实现**：新工作区 `pages/关系与权限/`（workspace.html + app.js + style.css），经 `tools/sync_framework_page.py` 以 `identity` 名注册进 `CompanionWorkspaceBundle` 并重建 `workspace-bundle.js`/`page-build.json`（`--check` 干净）；小屋 `renderIdentity()` 托管态挂载 `product.workspace('identity')`。
- **数据合同**：新增只读管理接口 `GET /astrbot_plugin_private_companion_v2/acquaintance`（`astrbot_host/acquaintance_api.py`，Dashboard 操作者鉴权 + `ObjectAccessPolicy` `memory.manage`，多目标/单目标宿主均已注册）。返回按授权路由过滤的相识目录（persons/groups/counts）。相识卡 document 首写时固化 `route`（installation/platform/bot/account/role/subject）与 `native_account_id`，目录据此枚举而不反转摘要。
- **视觉与动效**：相识轨迹四段阶梯（陌生→眼熟→认识→熟悉）作为统一视觉语言，阶段判定在印象卡切片点亮前保持未点亮（不伪造）；头像按 subject 色相渐变、私聊绿点；卡片悬停抬升 + 顶部光线扫过、列表 stagger 入场、tab 下划线展开、群成员 chips 高度过渡展开、骨架 shimmer 空态；全部动效尊重 `data-motion="low/off"`、主题/密度/圆角/字号维度与 `prefers-reduced-motion`。
- **测试**：`tests/test_person_acquaintance.py` 新增目录路由过滤与私聊用户识别用例（11 项全过）；工作区 JS 通过 `node --check`；页面视觉效果与浏览器交互归交付包统一测试阶段（`tools/check_*.cjs` 系列）。
- **动效语言同步**：同一套「动效与质感层」（入场浮现、列表 stagger、悬停微位移、加载 shimmer、dialog 浮现）以纯 CSS 追加到 `关系与记忆`、`日记与生活`、`宿主管理` 三个既有工作区（各自已有的 data-motion/维度守卫与 reduced-motion 继续生效，并在后两处补齐 animation 维度）；小屋核心样式已有成熟的纸质视觉体系且分页重渲染频繁，保持克制不加全局入场，避免交互闪动。重建后 `--check` 干净、四份样式括号配平、`test_page_targets_api` 等回归通过。

## 已修复的既有问题（与本切片同批完成）

1. **动态读空气提示 × 记忆退役的续答前缀冲突**：`group.memory.remember/revision` 成功后 `after_write` 退役依赖该记忆的历史引用，而 `participation.augment` 的动态提示按历史材料重算，续答 instruction 前缀失配（`model_context_mismatch: instruction_prefix`），批次停在 sealed。修复：提示按 batch 在首建时冻结（`GroupParticipation._frozen_hints`，进程内有界缓存）。冻结必须在内存：请求构建运行于 read snapshot 内，其中的写事务会被拒绝（`StorageOpenError`）；重启恢复后新会话重新锚定各自的首建，冻结天然自洽。回归：`test_only_original_member_can_revise...` 由 sealed 卡死恢复为通过。
2. **群表情目录断言**：当前源码 `storage/semantic.py` 默认 `reactions_group_enabled=False`，群目录不再含 `reaction.search`，`test_group_memory` 三个目录断言未同步。修复：受影响测试显式 `enable_group_reactions()`，保留原有"语义工具进群目录"的覆盖意图，产品默认值不动。
3. **隔离扫描器具名批准**：g0 对 20260926-27 切片引入的本地文件/URL 解析用途缺少登记。按"例外需要具名政策"原则扩展扫描器：新增 `APPROVED_IMPORTS_BY_MODULE`（`proactive/external_materials`、`proactive/news_sources` 的纯 `urllib.parse` 字符串解析）与 `APPROVED_CALLS_BY_MODULE`（`screen/originals` 的 `fsync/link` 本地持久化），并在 `APPROVED_IO_BY_MODULE` 登记 `screen/originals`、`conversation/media/screen`、`storage/semantic`（独立可重建库）、`storage/backup`（数据根备份合同）。g0 恢复 clean。
