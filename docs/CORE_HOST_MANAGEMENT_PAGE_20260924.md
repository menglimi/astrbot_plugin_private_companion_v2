# Companion V2 账号与会话页

2026-09-24。为没有开发者控制台的运行环境补齐一个普通 AstrBot Dashboard 页面：管理员从插件 Page 打开“账号与会话”后，可以读取当前运行状态、执行只读 `probe`，并在确认后依次初始化、启动或停止单目标 staging / 多目标 shared host。

页面沿用 AstrBot 的 `plugin_page_bridge`，所有请求使用插件相对路径；宿主仍由 Dashboard 的认证入口提供 `request.username`，页面不接受账号、角色或操作者的查询参数覆盖。初始化和启动保持显式操作，默认 preview 模式在状态说明中标明不会向平台发送回复；OneBot 投递模式会提示已有有限授权才决定实际发送。

页面文件位于 `pages/宿主管理/`，包含状态面板、Bot 账号 → 人格 → 会话窗口的三列只读拓扑、确认对话框、错误/空闲/禁用状态、窄屏布局和键盘焦点样式。拓扑直接读取多目标状态中的 `targets`，点击节点只高亮关联路径，不绕过配置写入和身份授权；拓扑关系会逐步绘制，异步操作提供按钮加载态，Esc 可取消节点高亮。会话窗口按每页 5 个展示，第三列同时限制列表高度并提供分页，避免大量目标撑爆页面。单目标使用 `/staging/*`，多目标使用 `/host/*`；页面先探测 `/staging/status`，只有路由不存在时才尝试共享宿主路径，不把另一套宿主当作回退数据源。

## 验证

使用本机安装的 Playwright、AstrBot `plugin_page_bridge.js` 和合成 API，不连接运行中的 AstrBot，不调用真实模型或 QQ：

```powershell
$env:NODE_PATH = 'D:/codex/workspaces/v2-memory-page-20260924/node_modules'
$env:HOST_PAGE_CHROMIUM = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
node tools/check_host_management_page.cjs `
  D:/codex/workspaces/v2-host-management-20260924/evidence `
  C:/Users/99505/.astrbot/backend/app/astrbot/dashboard/plugin_page_bridge.js
```

结果为 **8 个浏览器场景通过，页面和模拟服务错误均为 0**：初始只读状态、探测前置、初始化/启动/停止确认、多目标路由、拓扑分页、未授权账号拒绝以及 320px/键盘焦点检查。桌面和 320px 截图保存在输出目录的 `host-management-desktop.png` 与 `host-management-mobile-320.png`。宿主定向回归使用 AstrBot 自带 Python，`tests/test_astrbot_staging_host.py` 与 `tests/test_astrbot_multi_host.py` 为 **28 项通过、3 个 subtest 通过**；页面目录和记忆宿主回归为 **15 项通过**。

真实账号在线、真实模型、真实投递及生产替换发行仍需在已登录的 AstrBot Dashboard 中由管理员执行一次页面操作；本轮没有替用户初始化新 profile 或发送消息。

## 2026-09-25 真实宿主联调补验

已进一步用实际插件入口、已安装 SDK 的 HTTP 插件分发、真实请求上下文和 V2 SQLite 替换上述模拟 API，完成单目标/多目标各自首次启动与独立进程恢复的 **30 项浏览器与宿主检查**。真实 SDK 查询参数兼容、重启后只读预览和失效草稿隐藏已修复，相关 **85 项定向回归通过**。整个过程由本地验收脚本执行，无需用户控制台；登录身份、模型和平台仍为合成替身。复现命令、证据和下一步见[核心 Demo 验收记录](CORE_DEMO_HOST_ACCEPTANCE_20260925.md)。

## 2026-10-05 产品口径与启动路径

“单目标/多目标”是历史控制器和数据目录的实现分支，不是产品运行模式。管理页统一使用账号、人格和会话窗口映射；一账号与多账号场景都走共享宿主管理接口。旧 `/staging/*` 与 `/initialize` 路由保留给兼容客户端。

首次启动不再要求用户单独初始化：连接探测通过后，启动操作会在需要时准备 V2 运行数据并开始接管。账号和人格绑定校验、探测以及启动确认继续保留。当前浏览器检查覆盖探测后直接启动及一账号/多账号映射，共 **14 项通过**；控制器首次启动定向测试 **2 项通过**。
