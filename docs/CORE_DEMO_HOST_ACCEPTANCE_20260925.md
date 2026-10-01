# Companion V2 核心 Demo 宿主验收

2026-09-25。已在本地把实际插件入口、已安装的 AstrBot 4.27.2 SDK、宿主管理页、HTTP 插件路由、V2 SQLite 和独立进程重载连成可重复的验收链。无需用户打开控制台执行请求。单目标、多目标共 **30 项浏览器与宿主检查通过**，受影响范围 **85 项定向测试通过**。

本轮证明源码树中的核心 Demo 可以初始化、启动、接收 SDK 事件、生成并读取预览、停止和恢复。模型、账号、登录身份及平台连接使用合成替身；这不代表真实模型效果、真实 QQ 投递、安装包或生产替换发行已验收。

## 修复与运行行为

- 真实 SDK 的 `PluginMultiDict` 提供 `keys()`，没有字典的迭代协议。原多目标控制、预览和批次列表在读取查询参数时可能触发 `KeyError: 0`，成为 HTTP 500。现按 SDK 接口枚举键，仍拒绝重复、缺失和额外参数；回归直接使用已安装的类型。
- 加载已有运行档之后、显式启动之前，任务监督器尚无执行代。原预览在重建材料时误要求执行权限，返回 `supervisor_fenced`。现只在同步只读投影内复核原账号、Bot、角色、会话、授权和来源；不会领取、续期或冒认执行代。
- 只读投影由 SQLite `query_only` 与不可提升的读快照共同约束，不能借用已有写事务。嵌套、异常退出后恢复原数据库状态；复制的上下文不能在投影结束后保留例外权限。已有执行代被替换时仍拒绝读取，投影期间不能提交、领取任务或附着执行器。
- 多目标图片预览复用已复核的请求材料，避免在只读范围外重新重建。多目标同时核对批次 `origin_key`，已撤回或失效的批次不再返回保存的草稿正文；单目标与多目标均覆盖图片重启恢复。

本轮没有新增数据库迁移，运行实现仍分别位于 `astrbot_host/`、`companion_v2/`；根级 Python 仍仅 `main.py`。

## 验收方法与结果

`tools/verify_demo_host.py` 依次运行四个子进程。每种宿主的首次运行与恢复进程共用一份临时数据库；恢复时重新导入插件，避免用同一进程的内存状态代替持久恢复。

`tests/demo_host_process.py` 在 SDK 导入前将 `ASTRBOT_ROOT` 指向临时目录，真实加载 `main.py`，托管实际的 `pages/宿主管理/` 和已安装的页面桥，并调用 SDK 的 `_call_plugin_extension`。HTTP 请求因此使用真实的 `PluginRequest`、`PluginMultiDict` 和请求上下文；Dashboard 登录身份由夹具提供，不验证生产登录流程。消息使用已安装 SDK 的原生事件类型，模型和 OneBot 为本地替身。

| 宿主 | 阶段 | 浏览器/宿主检查 | 替身模型调用 | 平台发送 |
| --- | --- | ---: | ---: | ---: |
| 单目标 | 首次初始化 | 9 | 1 | 0 |
| 单目标 | 独立进程恢复 | 6 | 0 | 0 |
| 多目标、两个 Bot | 首次初始化 | 9 | 2 | 0 |
| 多目标、两个 Bot | 独立进程恢复 | 6 | 0 | 0 |

检查覆盖页面初始只读、探测前置、确认/取消、确认后再按 Escape、初始化、账号断线导致启动失败及恢复重试、启动接管、消息预览、Bot 隔离、停止后不再接管、已有预览恢复和 320px 布局。四个进程的服务异常、浏览器异常及意外浏览器网络请求均为 **0**；停机后数据库关闭、路由注销及核心模块卸载均通过。验收结束后临时数据根已删除。

定向回归为以下十个模块，共 **85 个唯一测试 ID，122.734 秒，0 失败、0 错误、0 跳过**：

```text
tests.test_execution
tests.test_execution_read_only
tests.test_storage_runtime
tests.test_astrbot_preview_recovery
tests.test_astrbot_multi_preview_recovery
tests.test_astrbot_multi_query
tests.test_astrbot_staging_host
tests.test_astrbot_multi_host
tests.test_astrbot_image_delivery_host
tests.test_astrbot_group_forwards
```

其中预览恢复、只读执行边界与真实 SDK 查询对象共 **18 项**。测试期间其他窗口为 `multi_api.py` 新增群记忆路由；保留该改动后，额外复验两项查询合同与一项路由注册/注销测试，**3 项通过且该次源码哈希未变化**。这三项包含在上述 85 项内，不重复累计。随后四进程 Demo 使用更新后的共享源码完成验收。更早的群转发 123 项及管理页模拟 API 7 场景仍保留各自历史记录，不与本轮数量相加。

## 复现与证据

在 V2 工程目录使用 AstrBot 自带 Python；验收入口自动隔离 SDK 数据根和 V2 数据库：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
$env:NODE_PATH = 'D:/codex/workspaces/v2-memory-page-20260924/node_modules'
$env:HOST_PAGE_CHROMIUM = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/verify_demo_host.py `
  --output 'D:/codex/workspaces/v2-demo-acceptance-20260925'
```

入口重新运行时先将汇总状态标为未完成，失败或超时保留子进程日志，避免沿用旧的成功结论。该脚本不会要求控制台手动输入，也不会向运行中的 AstrBot 注册测试端点。

本机证据目录为 `D:/codex/workspaces/v2-demo-acceptance-20260925/`：

- `demo-acceptance-results.json`：四进程、30 项检查及停机汇总。
- `regression-results.json`、`final-regression.log`：85 项测试 ID、结果及所核对源码哈希。
- `route-recheck-results.json`、`route-recheck.log`：并行路由改动后的三项复验。
- `single-fresh/`、`single-recovered/`、`multi-fresh/`、`multi-recovered/`：各自的 `process.log`、`result.json`、`browser-results.json`、桌面与 320px 截图。

未在线重载或重置真实插件，未调用真实模型或 QQ，未读取 V1 用户数据。本地 HTTP 只监听随机回环端口，夹具端点不进入产品路由。

## 下一步

整理可安装 Demo 包，明确源码和页面资源的打包清单、默认配置与 AstrBot 版本要求，再用独立干净目录验证从解包到初始化、启动、停止和保留数据重载的流程。当前验收覆盖源码树，不能替代安装包验收。群媒体、群记忆页面和 QQ 展示由各自功能切片继续推进，避免重复其他窗口的工作。
