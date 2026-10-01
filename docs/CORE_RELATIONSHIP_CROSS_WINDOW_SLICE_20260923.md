# CORE-03 关系记忆跨私聊窗口投影

日期：2026-09-23。关系记忆由稳定 Bot/角色/人类关系拥有，因此普通对话现可在同一关系的不同私聊窗口读取已采用记录；记录来源仍由原来源治理规则控制。

`RelationshipContext` 不再要求记忆记录和每条 Source 与当前完整 scope 相等。它仍限定当前受众为本窗口唯一的人类，并校验 owner 的 installation、Bot、persona 和当前 actor。底层 `RelationshipMemoryService` 每次读取都重新确认当前私聊路由、当前 `relationship.memory.read` 授权，以及所有 Source 对当前人类的受众、撤回和过期状态。不同人、Bot、角色不能沿此投影共享。

封存快照继续只保存记忆 ID 和 revision。生成、草稿提交、分段投递和 sender 回调沿原链重读来源与版本；后续撤回或更正会阻止旧批次继续使用。没有数据库变更，不升级 schema，也没有复制来源正文。

使用 AstrBot 自带 Python 完成本轮关系消费者、服务及台账 **30 项定向测试**：

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_relationship_context tests.test_relationship_memory_service tests.test_relationship_memory -q
```

其中跨窗口用例验证同一人同一角色的另一私聊可读取已采用关系背景，而另一人和切换后的角色不获得该材料。没有调用真实模型或平台，未读取或修改 V1 数据。当前读取仍使用按 ID 排序的有限页，不是语义相关召回；用户客观事实、偏好与表达学习属于独立后续领域。
