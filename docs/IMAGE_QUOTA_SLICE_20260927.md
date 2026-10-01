# 生图张数额度四档切片（2026-09-27）

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) T01（用户批注定案：只做张数限制，四档默认 -1 不限；费用限制不做）。迁移 V1 `photo_generation_scope.py` 的四个生图范围每日上限，在 V2 框架约定下改造实现。

## 语义（对齐 V1）

- 四档范围与 V1 一致：`private_owner`（主要用户私聊）、`private_friend`（其他私聊）、`group`（群聊）、`proactive`（主动消息）；每档每日张数上限取值 -1（不限）、0（关闭）、1–100。
- 分类优先级对齐 V1 `_photo_generation_scope`：父任务为 `proactive.compose` 判为 proactive；群 scope 判为 group；私聊按身份权限层推导——`subject_access_tiers` 中 CORE 判为 private_owner，其余（含未登记，默认 standard）判为 private_friend。V1 的"关系角色 owner"由 V2 权限层 CORE 等价承担。
- 计数口径对齐 V1 attempt 语义：按（scope, 请求者）在本地日（会话时区，默认 Asia/Shanghai，同 `date_context`）内计数；生图与改图共用额度；主动范围的请求者为联系目标主体。
- 命中上限的调用在派发前被拒绝：上限 0 返回 `image_quota_closed`；额度用尽返回 `image_quota_exhausted`，不创建子任务、不调用提供方、不计费。
- 与 V1 的两处明确差异：① 计数来源改为派生自权威记录——`extension_tool_invocations` 行在其派发事务内落库，回执状态不影响计数，未知结果不会重复计数；② 历史行的 owner/friend 归类按当前权限层重算（权限层无历史版本），权限层变更会即时改变既有计数的归属档位。

## 实现与接线

- `companion_v2/conversation/media/quota.py`：`ImageQuotaGate`（分类 + 限额读取 + 计数查询，全部在调用方事务内完成）；`ImageQuotaConfigurationOwner`（SparseConfigurationOwner，owner `conversation.media_quota`）；`configuration_fields()` 注册四个 INTEGER 字段（默认 -1，边界 -1..100，安装/角色两层，owner 与消费方同组）。
- 计数不建新表、不升 schema：按 [主动联系预算](CORE_RELATIONSHIP_CONTACT_BUDGET_SLICE.md) 的派生口径，`SELECT COUNT(*)` 连接 `execution_tasks`（JSON 投影安装/Bot/角色/主体/受众）与 `subject_access_tiers`（owner/friend 档位），时间下界为本地日零点的 UTC 戳。
- 准入点：`conversation/external_tools.py` 的 `execute()` 在既有 `require_capacity`（本轮媒体容量闸）之后、写入 invocation 行之前调用 `image_quota.admit(...)`——与[原生 Image 切片](CORE_NATIVE_IMAGE_DELIVERY_20260925.md)"建立子任务之前停止新图片调用"的既有闸口同位。
- `conversation/messages.py` 装配 `self.image_quota`；`host/application.py` 将四个字段并入统一配置注册表并登记 owner（陪伴小屋页面接入属第②阶段，本片未做页面）。

## 验证

- 新增 `tests/test_image_quota.py` 8 项通过（AstrBot 自带 Python）：注册合同与默认不限、上限 0 关闭、按派发次数递增并在额度用尽时拒绝、本地日零点前的尝试不计入、CORE 与非 CORE 主体额度分档、proactive 父任务与私聊回复分别计数、群聊与私聊分别计数、运行时重启后计数仍生效。
- 受影响回归：`tests.test_conversation_messages` + `tests.test_external_tools` 53 项、`tests.test_native_image_flow` 8 项、`tests.test_native_group_image_flow` 2 项中 1 项、`tests.test_astrbot_staging` 24 项通过。
- 既有失败（与本片无关，已用临时回退三处改动复验确认在改动前即失败）：`test_native_group_image_flow.test_sdk_group_generation_delivery_history_and_confirmed_quote`（批次 `sealed != ready`）与 `tests.test_astrbot_group_delivery` 两项（`ModelWebAPI.tts_providers` 缺失、群配置指纹旧断言——属 BUILD_STATUS 记录的"群聊/分段配置指纹旧断言"类别）。

## 边界与后续

- 未把 quota scope 随调用传给 Image 提供方（DC-1 批注：本批只做 V2 端闸门）；提供方内部的 V1 残留 scope 检查与 V2 闸门相互独立。
- 费用限制按用户批注不做（T02 销账）。
- 未重载在线插件、未调用真实模型/QQ/生图后端、未构建交付包；页面接入随第②阶段统一进行。
