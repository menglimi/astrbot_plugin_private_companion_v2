# V2 群旁听与选择性参与

日期：2026-09-25

已授权群的新消息先按现有原生入口保存，再由当前原角色根据本轮材料、各成员发言和历史判断是否接话。无需插话时可安静旁听；后续成员继续聊天时，先前旁听的原话仍可进入同群、同会话、同角色的上下文。

## 角色决定

`companion_v2/conversation/participation.py` 拥有群参与提示词与内部工具 `group.participation.choose`。仅对拥有原群文本权限的上下文开放，参数为 `mode: reply | skip`，可选一句简短 `reason`。原人格指令保持原样，参与提示说明成员之间的对话不需要每条回应、旁听是一种正常选择；没有固定触发词、回复配额或强制疲劳阈值。

- 直接生成正常最终回复：表示决定参与，沿已有生成和投递链路继续，只需原来的一次模型调用。
- 首次调用普通群业务工具：表示本轮决定参与，保留该调用的真实结果及后续回复。
- 显式 `reply`：保存原角色选择后继续本轮工具和回复。
- 单独 `skip`：保存决定后结束本轮，保留已授权输入，不创建 `conversation_parts`、投递任务、平台消息或机器人已发送历史。

已经开始业务操作或选择参与后，再请求 `skip` 会得到 `group_participation_fixed`，不会抹掉已发生的效果。同轮把 `skip` 与其他工具混用会得到 `group_participation_mixed`；模型仍能读取各业务工具真实回执并完成回复。这些约束只保证控制结果与实际效果一致，是否接话由角色判断。

## 持久状态与恢复

本片复用已有 `model_rounds`、`conversation_tool_calls` 和 `conversation_flows`，没有新 schema，也没有新的持久化数据根。

显式选择必须来自原模型轮次真实请求，工具回执绑定原 `task_id`、`batch_id`、原角色上下文与精确参数。直接最终回复和首次业务调用分别通过既有模型轮次、工具记录证明参与决定。

静默完成时，flow 为 `complete`、reason 为 `group_participation_skipped`；batch 保持 `sealed`，generation task 正常完成，消息原件仍可供后续群上下文读取。`sealed` 在这里表示已固定输入，不表示待发送消息；是否完成以 flow 和原任务记录为准。静默不会伪造一个零长度回复清单。

选择回执已提交但宿主随即停止时，恢复通过原回执完成静默收尾。输入重放仍返回原 batch，已完成选择和确认发送不会重做；模型结果未知时仍使用原任务的未知结果处理，不再生成一次选择。恢复期间材料已失效则阻止采用，不另找替代材料。

## 材料与投递

旁听继续使用 `ConversationMessages`、`GroupConversationContext` 和媒体原件 owner。当前图片、语音、视频、引用和转发沿原授权读取路径提供；后续历史附件仍按既有规则提供元数据，不会把历史附件占位解释为本轮再次看过、听过。

历史原话保留成员归因。原消息撤回、来源撤销、原成员文本授权撤销、人格或会话变更，会在原路径上使材料不可采用。已经封存并使用失效材料的回复被阻止；新一轮只捕获仍可用的上下文。静默决定不是跨群、跨账号或读取私聊材料的授权。

`skip` 不调用发送端；`reply` 继续通过原图文发送、发送前复核和持久回执。原 `preview` 参与决定即使经历配置切换、重启和后来授权，也不会升级成真实群投递。

## 接线

- `conversation/tool_loop.py`：群工具目录、提示词、执行与回执复核接入 `GroupParticipation`。
- `conversation/generation.py`：工具返回静默后结束本轮；最终回复提交前复核参与状态。
- `conversation/flow.py`：从已保存的静默回执恢复完成，不重新决策。
- AstrBot 继续使用现有 `MultiHostSession`、群旁听输入、原角色捕获和群 sender，无新增入口注册。

内部诊断可读取 `application.tools.group_participation.decision(context, batch_id)`，返回 `mode`、决定依据与原模型调用 ID；现有工具观察记录保留显式选择的状态。本片没有修改管理页展示。

## 验证

使用 AstrBot 自带 Python，`ASTRBOT_ROOT` 指向临时目录；模型与 OneBot 均为合成宿主夹具，没有操作现场 QQ、运行数据或 V1 数据。

专项 `tests/test_group_participation.py` 覆盖静默无发送、旁听后续上下文、原人格提示、直接回复无需额外模型轮次、显式 reply、业务后拒绝改为 skip、混合工具调用、撤回与成员撤权传播、跨群/私聊隔离、选择回执被改动、静默与回复重放、选择提交后停机恢复、未知模型结果、preview 配置切换，以及 SDK 图片旁听与后续历史元数据。

受影响回归包括群上下文、群记忆工具、原生群图片工具、原生群宿主、群投递、会话消息和宿主任务生命周期。旧测试中写死的群工具集合已加入参与工具；撤销群记忆读取权时仍可按原群文本权限选择旁听。

最终定向验证：8 个模块共 **123 项通过**，用时 **171.493 秒**；其中本片新增 14 项。执行模块为 `test_group_participation`、`test_group_conversation_context`、`test_group_memory`、`test_group_native_image_tools`、`test_astrbot_group_host`、`test_astrbot_group_delivery`、`test_conversation_messages`、`test_host_application`。本片 9 个文件的 UTF-8、无 BOM、LF、末尾换行及 Python AST 检查通过。

## 范围与下一步

本片完成“新群消息 → 旁听上下文 → 原角色选择回复或跳过 → 原群回复”。没有新消息时自行找话题、定时插话的群主动参与不在本片内。下一步可将参与状态接入既有管理观察入口，并在后续现场验收中检查真实角色对不同群话题的参与质量；现场参数应依据角色表现调整提示词。
