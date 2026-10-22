# V1 开放 issue / PR 的 V2 覆盖核对（2026-10-19）

范围：`menglimi/astrbot_plugin_private_companion` 当日的 11 个开放 issue 与 3 个开放 PR。这里的“V2 覆盖”只指当前工作树，不等于 V2 已发布，也不代表仍在运行的 V1 已修复。只有发布包、迁移数据和真实宿主路径通过后，才可用“由 V2 取代”结案。

| Issue | V2 现状 | GitHub 处置条件 |
| --- | --- | --- |
| [#296](https://github.com/menglimi/astrbot_plugin_private_companion/issues/296) 主动追问反复出现 | `proactive/scheduling.py` 的未完话头认领只发起一次；未确认用户自然回复后的语义收尾及残留清理，部分覆盖。 | 保持开放；与 PR #297 一起核对已送达时间、回复关联、`resolved/cancelled/keep` 及过期清理。 |
| [#295](https://github.com/menglimi/astrbot_plugin_private_companion/issues/295) 群聊续接 | 本次让机器人发送后的首位跨成员回答进入 `reply_follow_up` 候选，保留同一成员短连发与静默旁听后的续接；其他成员介入及窗口过期会终止续接。AstrBot 宿主路径回归通过。话题线、语义接话、冷却及中止仍未等价证明，部分覆盖。 | 保持开放；用多成员真实群事件覆盖完整话题生命周期后再结案。 |
| [#294](https://github.com/menglimi/astrbot_plugin_private_companion/issues/294) 余额感知 | V2 有 NewAPI/JSON 查询端口及小屋配置、测试入口；未配置有效 HTTPS 地址与有 `profile:read` 权限的令牌时，本来就不可查询。 | 先让受影响实例填真实服务参数并执行入口测试；不能把“默认未配置”说成故障已修。 |
| [#293](https://github.com/menglimi/astrbot_plugin_private_companion/issues/293) 生图 trace 未 await | V2 原生图片链路不走 V1 报错的 `pc_generate_photo` trace 调用，属于实现差异；未证实 V1 警告消失。 | V1 若继续维护须单独修；V2 须验证真实生成、发送及回执。 |
| [#292](https://github.com/menglimi/astrbot_plugin_private_companion/issues/292) 绝对日期召回 | 本次将中文、数字和 ISO 绝对日期接入 V2 核心回复的本体记忆时间窗口查询；尚未证明外部 MemoryCompanion 历史库或 V1 导入材料的自动召回。 | 保持开放；迁移后用原提问和真实历史资料验证，区分本体与外部插件路径。 |
| [#291](https://github.com/menglimi/astrbot_plugin_private_companion/issues/291) 单人格外部记忆 | V2 自有记忆以可信角色绑定；未证实事件向 MemoryCompanion 提供 `private_companion_persona_id`。 | 保持开放；在单人格与多人格、迁移记忆的真实宿主链上核对外部插件兼容。 |
| [#289](https://github.com/menglimi/astrbot_plugin_private_companion/issues/289) ComfyUI 路由 | V2 自带 ComfyUI、在线端点和可排序 `operation_routes`；V1/图像扩展的联动改动仍独立。 | 先验证 V2 工作流、尺寸缺省、回退和穿搭；PR #290 依赖图像仓库 PR #13，不能先行合并或按 V2 代码关闭 V1 issue。 |
| [#285](https://github.com/menglimi/astrbot_plugin_private_companion/issues/285) 群好感度 | V2 有群成员资料及关系观察，但未发现等价的数值群好感度准入和结算；未覆盖。 | 保持开放。不要将 `migration_replay_registry_missing` 误写为零好感度的直接真因，也不要伪造备份清单越过恢复门。 |
| [#283](https://github.com/menglimi/astrbot_plugin_private_companion/issues/283) REQ-041 迁移停滞 | V2 使用独立数据根与事务迁移，不复用该 V1 回放链；不能修复运行中的 V1。 | 保持开放；V1 按更正后的 `migration_replay_registry_missing` 排查，不将旧 `revision_gap` 或 fresh-v1 空备份列为当前根因。 |
| [#278](https://github.com/menglimi/astrbot_plugin_private_companion/issues/278) 本地人格重置 | V2 有窗口重置及本地身份管理，但尚未验证无 scoped Memory 桥接时的人格清理和统一人物归档等价路径。 | 保持开放；以有/无外部桥接两套数据做定向验收。 |
| [#254](https://github.com/menglimi/astrbot_plugin_private_companion/issues/254) 私聊记忆 hash 并发 | V2 没有 V1 `_req041_private_memory` 写入/回放路径；这是架构隔离，不是对 V1 并发写入故障的修复。 | 保持开放；V1 需独立修复或在正式停用 V1 时明确归档。 |

| PR | 审核结论 | 下一步 |
| --- | --- | --- |
| [#297](https://github.com/menglimi/astrbot_plugin_private_companion/pull/297) | 针对 #296 的 V1 实现；V2 尚未等价，公开审查和合并验证不足。 | 保持开放，按送达后的回复语义与失败重试验证；不因 V2 一次认领而合并/关闭。 |
| [#290](https://github.com/menglimi/astrbot_plugin_private_companion/pull/290) | 针对 #289；依赖图像仓库仍开放的 PR #13。 | 保持开放，先解决依赖和 V1/图像扩展联动测试；V2 原生实现不自动替代 V1 PR。 |
| [#284](https://github.com/menglimi/astrbot_plugin_private_companion/pull/284) | 提交者已在正文写明当前 head 仅有部分补丁，缺结算等路径。 | 保持草稿/不合并；补齐真因与 dead-letter 后重新审查。 |

## 本次 V2 代码与验证

- `companion_v2/memory/time_intent.py` 与 `astrbot_host/core_reply_context.py`：从用户明确日期产生本地日历日的 `[start, end)` 查询条件；不覆盖未来日期或泛化的“明天”。
- `companion_v2/conversation/group_admission.py`：在同一群、同一角色、宿主发送调用已返回的机器人回复后，允许第一条其他成员消息进入续接候选，并保持该成员的短连发；修复静默旁听消息被误判为他人介入的问题。未送达、未知送达及正在处理的轮次继续保持原身份边界。
- 从本次交付包解压后的源码执行 `tests.test_v1_issue_v2_regressions` 与 `tests.test_group_reply_admission`，33 项全部通过；不是从工作树借用源码。覆盖跨成员首条接话、旁听后的续接、他人介入、窗口过期及未知发送结果不重放。测试使用宿主接口和合成事件/模型，不等于真实 QQ 群现场验收。
- 同包迁移验收 75 项通过；宿主加载、停机、4 条生活路由注销通过。单一插件注册、七项内置能力、唯一公开小屋页面、文件哈希及 Python 语法检查均通过。宿主使用 AstrBot 自带 Python、`backend/app` 及临时数据根；Laya 处于 disabled，未运行本地权重。

## 线上处置与交付

11 个开放 issue 与 3 个开放 PR 均已提交逐项核查评论。缺乏等价验证、仍有外部依赖或补丁不完整的条目继续开放；PR #284 保持草稿，三个 PR 均未合并。GitHub CLI 的令牌请求曾遇到连接 EOF，线上评论通过仓库所有者已登录页面完成，无需再次提供令牌。

交付包位于 `D:/codex/workspaces/companion-v2-release-20261019-issues-final/astrbot_plugin_private_companion-7.0.0.zip`，SHA-256 为 `399856fb63b3d8242bbcb2b3d377888c9a386e01bc1c55514a94e1b12aa93589`。验收证据为同级 `companion-v2-release-20261019-issues-final-verify/package-verification.json` 与 `issue-regressions.log`。交付包及解压验收目录均在插件一级扫描目录之外。

真实外部 MemoryCompanion 召回、受影响用户的 V1 历史数据迁移后召回、真实生图投递及完整多成员话题生命周期仍未取得现场证据。自动迁移验收使用临时合成数据，不能代替这些结案条件。

当前工作树含大量已有未提交改动；本次没有修改 V1 用户数据，也没有在线重载或替换运行中的插件。
