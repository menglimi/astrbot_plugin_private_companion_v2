# CORE-03 记忆事实与私聊跨会话召回

日期：2026-09-23。

V2 记忆的稳定 owner 由 installation、Bot、角色和已认证的人类主体组成，不包含会话 ID。durable 记忆因此可在同一用户与同一 Bot/角色的其他私聊窗口中被查询，并由普通对话的记忆消费者加入提示材料；`session` retention 仍绑定创建时的完整 scope。

跨窗口使用不会复制原始证据，也不绕过源授权。每次召回都沿当前会话重新校验身份与角色、当前记忆授权、私聊路由、源受众和来源状态；撤回、过期、权限变化或内容哈希不符会使对应记录不可用。管理视图和自动上下文都保存版本引用，并在读取时回到记忆正本及来源治理。检索 SQLite 仍是按 owner 分区的可重建投影。

本切片不把私聊记忆投影到群聊、转述对象或不同人，也不跨 Bot 或角色共享。短期记忆仍受有效期限制；本切片未读取或转换 V1 数据。

使用 AstrBot 自带 Python 完成隔离、记忆边界及真实普通对话装配 **15 项定向测试**：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_isolation tests.test_memory_boundaries tests.test_memory_conversation -q
```

新增覆盖包含：另一私聊窗口里的 durable 查询、同一用户切换角色后的隔离，以及第二私聊普通回复获得先前授权偏好；另一用户即使拥有自己窗口的 `memory.read` 授权，也只会读到自己的空 owner 分区。未调用真实模型或平台。
