# V1 开放 Issue 与 PR 对照

核对日期：2026-10-12。来源：[`menglimi/astrbot_plugin_private_companion`](https://github.com/menglimi/astrbot_plugin_private_companion)。处理前有 11 个开放 Issue、7 个开放 PR。逐项检查了正文、状态和可合并性；对 #271、#275、#280 复核了完整 diff，并在 AstrBot 自带 Python 环境运行对应回归测试。此记录用于判断 V2 是否重现 V1 的问题，不把 V2 的实现当作 V1 已修复，也不把 Issue/PR 的开放状态当作 V2 缺陷证据。

已在 V1 使用普通 merge commit 合并 PR #271、#275、#280，并分别附修复说明关闭 Issue #270、#281。随后将 PR #277 的运行期修复更新到最新 `main`，通过 PR #286 合入；#272、#273、#274 已关闭，GitHub 因 #286 保留 #277 的提交历史也将 #277 标记为已合并。PR #287 合并 #279/#282 的性能改进，PR #288 合并 #278 的本地重置部分修复。#262/#276 已说明与 V2 架构重复且大规模冲突后关闭；#284 退回草案，Issue #285 保持开放。未绕过检查。当前仍有 4 个开放 Issue（#254、#278、#283、#285）和 1 个开放 PR（#284）。

## Issues 状态

| Issue | V1 问题 | V2 对照与结论 |
| --- | --- | --- |
| [#254](https://github.com/menglimi/astrbot_plugin_private_companion/issues/254) | 并发写入时记忆正文与 `content_hash` 不一致 | V1 PR #286 增加同一 snapshot 的进程内读写锁并拒绝修改已有哈希损坏记录；原报告的哈希错配根因仍未确认，所以保持开放。V2 MemoryWriter 在事务中提交正文与哈希同源；既有 V1 数据未读取、修复或迁移。 |
| [#270](https://github.com/menglimi/astrbot_plugin_private_companion/issues/270)（已关闭） | 持久化清理改写记忆正文但未更新哈希 | 已由 PR #271 合并修复；V2 的记忆清理通过逻辑遗忘/归档管理状态，不原地改写来源正文。 |
| [#272](https://github.com/menglimi/astrbot_plugin_private_companion/issues/272)（已关闭） | 启动时群社交事实清洗重复计算，造成同步阻塞 | PR #286 在单次树遍历中复用关系上下文，未使用跨调用缓存；新增调用次数回归测试通过。V2 仍需独立的大数据冷启动验收。 |
| [#273](https://github.com/menglimi/astrbot_plugin_private_companion/issues/273)（已关闭） | REQ-041 迁移清单缺失人格库时反复失败 | PR #286 将冻结源文件缺失映射为明确的 `migration_source_file_missing`，满足 Issue 所列的明确错误结果；不伪造备份，也不自动恢复已删除人格。V2 使用独立数据根和显式迁移流程，未修改 V1 用户数据。 |
| [#274](https://github.com/menglimi/astrbot_plugin_private_companion/issues/274)（已关闭） | 衣柜聊天命令添加图片后草稿队列卡住 | PR #286 仅在识图成功且衣柜状态持久化成功后推进素材状态。V2 通过角色隔离的图片素材/衣柜管理接口工作，不复用该聊天命令队列。 |
| [#278](https://github.com/menglimi/astrbot_plugin_private_companion/issues/278) | 缺少 scoped Memory 桥时阻断本地人格重置和人物管理 | V1 PR #288 在元数据确认从未检测到远端 Memory、且 `ever_bound` 为 false 时允许备份后本地重置；记录过远端绑定仍 fail-closed。统一人物归档仍要求 registry 的远端作用域回执，Issue 保持开放。V2 由自己的角色 API 管理。 |
| [#279](https://github.com/menglimi/astrbot_plugin_private_companion/issues/279)（已关闭） | 事件循环上 deepcopy 整份 legacy snapshot 导致周期卡顿 | V1 PR #287 在持有 `_data_lock` 时把快照 deepcopy 放入工作线程；同一份快照仍受锁保护。包括运行期同步与启动回填路径，并有线程和锁状态回归测试。 |
| [#281](https://github.com/menglimi/astrbot_plugin_private_companion/issues/281)（已关闭） | QQ 官方通道群成员角色始终为 unknown | 已由 PR #280 合并修复。V2 仍只接入 OneBot `aiocqhttp`，尚未支持 `qq_official`。 |
| [#282](https://github.com/menglimi/astrbot_plugin_private_companion/issues/282)（已关闭） | 保存时重复清洗整份数据造成大文件阻塞 | V1 PR #287 对单次清洗过程中的重复短文本使用有界 LRU（最长 400 字符、最多 30,000 项），长文本不缓存，遍历结束即释放；避免跨保存周期保留用户文本。PR 采用报告中的缓存优化建议。 |
| [#283](https://github.com/menglimi/astrbot_plugin_private_companion/issues/283) | REQ-041 迁移身份反复回滚、长时间停滞 | 正文更正称当前错误码是 `migration_replay_registry_missing`，更早的 `revision_gap` 已被覆盖；所述实例是无 legacy 源的新实例，空备份清单符合设计，生产代码没有 `resume()` 调用点。V2 有独立的显式迁移、身份复核和恢复测试，但不运行这条 V1 自动迁移账本。 |
| [#285](https://github.com/menglimi/astrbot_plugin_private_companion/issues/285) | 群聊好感度无法覆盖未建档群成员 | 正文更正明确指出迁移暂停和空备份清单不是群好感度准入为零的原因。V2 按设计不维护可归属到单个群成员的群好感度账本；群侧记录是无成员关系归属的群级观察，未把该 V1 机制直接迁入 V2。 |

## PR 状态

| PR | 主题 | V2 处理 |
| --- | --- | --- |
| [#262](https://github.com/menglimi/astrbot_plugin_private_companion/pull/262)（已关闭）与 [#276](https://github.com/menglimi/astrbot_plugin_private_companion/pull/276)（已关闭） | 将超大模块按业务域拆分并解决集成冲突 | 两者涉及约 895 个文件并与当前 `main` 冲突；V2 已按 `companion_v2/<domain>/` 与 `astrbot_host/` 分层。已留言说明 V2 架构已取代 V1 巨型拆分 PR，并关闭这两个重复、不可安全合入的候选。 |
| [#271](https://github.com/menglimi/astrbot_plugin_private_companion/pull/271)（已合并） | 持久化清理时豁免 REQ-041 私聊记忆 | Merge commit `5d840dbc63df1ca32f936928206bff3852068d3a`。新增的 5 项哈希回归测试在 AstrBot Python 环境通过。 |
| [#275](https://github.com/menglimi/astrbot_plugin_private_companion/pull/275)（已合并） | 修复 AstrBot Page 沙箱内人格重置按钮无响应 | Merge commit `66c177854e67effe082762c85dbfdc170e49e4ed`。确认/取消、目标锁和失败释放测试共 15 项通过。V2 同类风险已在页内 `<dialog>` 确认流程修复。 |
| [#277](https://github.com/menglimi/astrbot_plugin_private_companion/pull/277)（已合并） | 集成 #271/#275、#272 清洗性能、#274 衣柜状态、#273 迁移源及 #254 并发修复 | 原 head 与最新 `main` 冲突；其变更经更新后的 PR #286 合入。#254 的根因仍未确认，因此该 Issue 保持开放。 |
| [#286](https://github.com/menglimi/astrbot_plugin_private_companion/pull/286)（已合并） | 基于最新 `main` 更新 #277 的运行期修复 | Merge commit `4e556d9e862a0cf0a8503a2b46b1dc553fa303a8`。GitHub Actions 的 core-only、contracts-and-migrations、pending-runtime-regressions、architecture-and-artifact 四类检查均通过；push 与 pull request 两次触发均通过。 |
| [#280](https://github.com/menglimi/astrbot_plugin_private_companion/pull/280)（已合并） | 从 `raw_data.author.member_role` 识别 QQ 官方群角色 | Merge commit `9486a8d8a5bce0d4bd31653b4ee6e895c16ba2ff`。AstrBot Python 环境中的群角色回归测试 13 项通过；V2 仍不支持 `qq_official`。 |
| [#287](https://github.com/menglimi/astrbot_plugin_private_companion/pull/287)（已合并） | 修复快照复制阻塞事件循环、减少重复清洗 | Merge commit `10864d7eb53135d3298ed66a024b84d41327cd0b`。core-only、contracts-and-migrations、pending-runtime-regressions、architecture-and-artifact 四类 GitHub 检查均通过。关闭 #279/#282。 |
| [#288](https://github.com/menglimi/astrbot_plugin_private_companion/pull/288)（已合并） | 无远端作用域历史时允许本地人格重置 | Merge commit `1cdce640db3a0f50b2e1055315ba7cd83d30018b`。无外部绑定历史时仍备份本地数据；有 `ever_bound` 或来源不明时仍拒绝。只解决 #278 的本地重置部分。 |
| [#284](https://github.com/menglimi/astrbot_plugin_private_companion/pull/284)（开放草案） | 修复群好感度闸门与缺失账户问题 | PR 正文明示当前 head 只含部分根因修复，直接合并仍不能让群好感度完成结算。已退回草案；Issue #285 保持开放，等待完整 diff 和 CI。V2 不保存成员级群好感度账本，不移植这套账户同步和结算路径。 |

## 修复与验证

对照 PR #275 后，V2 原生浏览器确认框已替换为可取消的页内对话框。记忆归档、导入、撤回、遗忘在等待确认后还会复核页面代次和预览版本；异步离页确认完成前不会卸载天气编辑器。关系工作区在自身文档内显示对话框，避免跨 iframe 沙箱调用父页面对象。

V1 原三项合并后，相关用例共 33 项通过、7 个子测试通过。PR #286 在 AstrBot 自带 Python 环境完成 91 项本地定向测试；一个符号链接测试受 Windows 权限限制未能本地创建链接，但 Linux GitHub Actions 全套通过。PR #287 的 85 项性能回归测试和 PR #288 的 43 项重置/身份测试（7 个子测试）通过；两个 PR 的四类 GitHub 检查均通过。V2 定向测试 130 项通过，追加确认框与天气页测试 4 项通过；`git diff --check` 与 `tools/sync_framework_page.py --check` 通过。
