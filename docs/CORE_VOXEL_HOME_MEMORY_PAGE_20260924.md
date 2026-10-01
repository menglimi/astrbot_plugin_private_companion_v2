# 体素小屋拓展页接入 V2 记忆

2026-09-24。本轮复用以三维体素小屋为首页的整合拓展页，在原“记忆与经历”导航及首页记忆入口中接入实际记录。没有修改现有独立“关系与记忆”页面的业务范围。

## 页面来源与发布

- 唯一可编辑页面源码仍在相邻 Content 仓库的 `pages/framework-preview-v1/`。历史目录名不代表 V1 运行时。
- 新增 `memory-page.js`、`memory-page.css`；原壳只增加资源引用、工作区挂载和路由退出清理。体素小屋、小屋布置、导航和其他预览内容保留。
- `tools/sync_framework_page.py` 将同一套源码、体素资产及许可证发布到本插件的 `pages/陪伴小屋/`，记录文件 SHA-256；`--check` 检查发布副本与源文件一致。副本不要单独编辑。
- AstrBot 的页面 bridge 自动添加所属插件名前缀，不能从 Content 页跨插件读取 V2 API。正式入口应为 **V2 插件 → 拓展页 → 陪伴小屋 → 记忆与经历**。无需前端 Token、跨域直连或从 UMO 猜测身份。
- 静态打开或在 Content 中打开，仍明确展示示例；V2 发布页若桥接/鉴权失败，只显示错误，不退回示例记录冒充成功。首页与其他未接入区域仍保留设计预览标识。

新增路由需由 V2 宿主在下次正常加载时注册。本轮未在线重载、启用 profile、调用真实模型或 QQ，也未读取 V1 用户数据。

## 已接入的行为

| 页面操作 | 实际接口及行为 |
| --- | --- |
| 选择会话对象与角色 | `GET page/targets`；宿主返回单目标/多目标目录、安装和管理员标识及固定 `memory_api`。操作者必须具有当前核心管理权限。 |
| 查看已保存事实 | `GET <memory_api>`，游标分页。无法读取的来源正文隐藏；无伪造时间线、原文或修订操作。 |
| 查看待处理整理 | `GET <memory_api>/reflections`，游标分页；单独按 `batch_id` 读取所选详情。 |
| 继续、修复 | 明确点击后 `POST <memory_api>/reflections/queue`，正文只有 `batch_id`、`operation_key`。沿用既有后台任务和模型预算。 |
| 跟踪修复进度 | 追踪 queue 返回的实际子批次，展示来源检查、剩余/暂缓/不可用数量、处理回执、失败原因和后台状态。未知数量显示“尚未统计”。 |
| 重新打开页面 | 浏览器只保留提交标识，不缓存记忆正文；按安装、当前管理员和目标接口隔离。通过详情 API 继续查看已经从未完成列表消失的完成批次。 |
| 提交回执丢失 | 保留原操作键；只在点击“核对上次提交”时再查原请求。不会自动生成新修复请求。 |
| 原模型结果未知 | 展示待核对原因，没有重复执行按钮。已知失败可显式发起新修复，使用新的操作键。 |

浏览器每 8 秒只读刷新，在隐藏/离开页面时停止。刷新、轮询、重新打开页面都不会提交模型任务。切目标/角色后旧异步响应被忽略；已经发出的提交仍归属原目标，原请求标识可在切回后核对。撤销核心权限后清空记录、目录和当前提交标识。

群聊目录项不提供私人 `memory_api`。页面明确提示群聊记忆独立管理，不能借群入口读取成员私聊。群公共记忆本身已有单独领域实现，本轮没有接它的管理页面。

## 定向验证

使用 AstrBot 自带 Python，测试导入 SDK 前设置临时数据根：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m pytest -q tests/test_page_targets_api.py tests/test_memory_host_api.py tests/test_memory_jobs_multi_host.py tests/test_astrbot_staging_host.py tests/test_astrbot_multi_host.py
```

结果：**41 项通过，另有 3 个 subtest 通过**，包含新增的 4 项页面目录/SDK 发现检查。覆盖当前身份与核心权限、单/多目标、同一原生账号在不同 Bot/角色下的隔离、群无私聊入口、原后台请求和插件停机路由注销。宿主仅有既有 `audioop` 弃用警告。

`tools/check_framework_memory_page.cjs` 使用真实安装的 `plugin_page_bridge.js`，通过本地父页面/iframe 消息桥与合成 API 验证，不连接运行中的 AstrBot。Playwright 在独立无头 Chromium 中运行，不使用桌面鼠标。**17 个浏览器场景全部通过，页面和模拟服务错误均为 0**；包括提交过程中切角色、受阻后的只读轮询、再次显式修复、丢回执恢复、完成批次重开、权限撤销和未知结果不重放。桌面 1366px、手机 390px/320px；检查结果及截图在本机 `D:/codex/workspaces/v2-memory-page-20260924/evidence/`。

复验入口（`playwright` 为独立开发依赖；第三个参数是当前 AstrBot 安装的 bridge SDK 文件）：

```powershell
node tools/check_framework_memory_page.cjs <截图与报告目录> <AstrBot源码根>/astrbot/dashboard/plugin_page_bridge.js
```

初次浏览器检查的隐藏 `<details>` 文本断言已改为检查 DOM 正文；另发现原壳 `body` 最小宽度 360px 导致 320px 截断，现仅在接入记忆工作区时覆盖为 320px，并使标题与工具栏换行。未对其他预览区域批量改版。

发布后执行 `tools/sync_framework_page.py --check`；新增文本按 UTF-8、无 BOM、LF 保存。独立测试依赖安装在临时工作目录，不写入插件生产依赖。

## 下一步

在同一页面接入事实更正、置顶/取消置顶、修订历史及遗忘预览/确认，复用已实现的版本令牌与幂等管理接口；随后接入原文/经历查询和群公共记忆工作台。当前完成的是事实读取与整理续接，不能视为整页、整套小屋或整个 V2 框架已全部接入。
