# CORE-03：关系记忆接入普通对话

日期：2026-09-23。在[关系记忆存储与授权服务](CORE_RELATIONSHIP_MEMORY_SLICE.md)上补齐当前私聊的提示材料消费者。统一宿主已接线，普通对话在批次封存时读取已审阅、已采用的关系背景和情绪事件；没有可用关系材料时仍能继续对话。

## 实现

- `companion_v2/conversation/relationship_context.py` 通过 `RelationshipMemoryService` 获取和复核记录，不绕过领域服务直接读表。服务负责当前身份、关系读取权限、私聊参与者、角色及原来源状态/有效期/受众；消费者还要求当前完整 scope 和单一当前人类受众，所有来源也必须属于同一完整 scope。
- `ConversationMessages.seal` 在原事务中固定本轮记录的 ID 和 revision，写入现有 `conversation_batches.contributions_json`。该快照不复制关系解释或来源正文，不增加表或升级 schema；重复 seal 不追加新记忆，旧批次没有快照时也不补入。
- `_request` 按原 ID 重建提示材料，复用已有模型生成前、生成后、草稿提交前、逐段投递和 sender 最终回调的校验链。读权限撤销、来源失效、记忆更正或撤回会阻止旧草稿继续使用；不会自动换用新版本。未选中的记录变化不影响本轮。
- 提示材料标明类型、观察时间、情绪主体、采用状态和主观解释性质，不携带可用于 observed 声明的证据句柄。提示词要求尊重本轮表达，不把一次情绪当成稳定性格、当前情绪、心理诊断或权限依据，也不自动升级关系。人格提示保持原文。
- 已确认送出的部分保留原平台回执；关系材料随后失效时，后续部分被拦下，历史正文通过既有依赖复核隐藏，发送事实不被抹除。生成中失效的草稿被丢弃，实际模型用量继续记账。

## 有界读取和降级

首次封存最多向关系服务读取 32 条已采用候选，再选入最多 8 条、合计不超过 8192 个 JSON 字符的材料。中文直接序列化为 UTF-8 文本，不按 Unicode 转义膨胀后的长度计预算。超出预算的记录整条省略，不截断原解释；快照标记 `truncated`。

当前采用服务原有按 ID 排序的有限页，不是语义检索或按相关性召回。服务对整页执行来源复核，因此其中一条失效时本轮关系材料整体记为 unavailable，并保留失败原因，普通对话可以继续。已经选入的依赖在后续失效则拒绝旧草稿，不能再按可选材料静默丢掉依赖。

旧批次恢复后继续使用原引用；缺少关系服务时，带引用的批次不可投递。无效格式、其他上下文的快照和重复引用被拒绝。

## 验证

使用 AstrBot 自带 Python，共 **144 项定向测试通过**：新增关系消费者测试 20 项、关系服务/消息/宿主/工具/隔离回归 87 项、AstrBot 宿主与 bootstrap 回归 37 项。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_relationship_context -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_relationship_memory_service tests.test_relationship_memory tests.test_conversation_messages tests.test_host_application tests.test_host_recovery tests.test_role_tool_loop tests.test_isolation -q
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_astrbot_staging_host tests.test_astrbot_staging_bootstrap -q
```

新增测试覆盖采用状态与情绪主体、证据隔离、生成中更正/撤回及用量、发送前来源撤销/过期/撤权、多段发送回执、读取前可选降级、换人/换角色/跨 scope/受众扩张、数量和文本预算、封存重试、重开恢复、旧批次兼容、服务缺失、损坏快照，以及统一宿主自动入站到分段回执。SDK 测试覆盖入口装配、停机和路由注销，SDK 导入与各运行库均使用临时目录。

本轮未调用真实模型或平台，未重载在线插件，未读取或修改 V1 数据。上述结果验证框架调用链，不代表真实模型的记忆召回效果或表达质量已经验收。

## 后续边界

当前服务和消费者需要已有的可信审阅、采用记录。面向用户的提议/审阅/采用/更正/撤回交互、管理 API、自动提议与确认流程尚未接入；staging 仍需显式配置对应 `relationship.memory.*` 能力，没有为旧 profile 自动追加权限。

跨会话关系投影、相关性检索、用户客观事实/偏好、表达学习及其他衍生摘要的失效链属于后续切片。日记/梦境素材和每日/睡眠触发继续由对应角色生活切片推进。
