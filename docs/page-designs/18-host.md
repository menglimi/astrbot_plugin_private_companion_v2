# 18 · 宿主管理（`manage/host`）

代码位置：`renderHostPage`（`pages/陪伴小屋/app.js:1327-1329`，分区「宿主与生命周期」）→ `renderHostWorkspace()` → `product.workspace('host')` iframe（`app.js:1267-1274`）。构建源 `pages/宿主管理/workspace.html` + 同目录 `app.js`（274 行）。

## 一、页面功能

宿主生命周期：探测、初始化、启动接管、停止接管。页头文案明确风险分级（`app.js:1328`）：**探测只检查账号、会话、人格与模型适配；启停会真实改变入站消息的处理方**——这是管理员操作，不与日常按钮混排（嵌入态下日记工作区的启停按钮甚至被隐藏，`embedded-bridge.js:54`）。

## 二、展示部分（host 工作区）

| 分区 | 内容 | 证据（构建源） |
| --- | --- | --- |
| 运行实例状态 · 当前实例 | 运行档 / 投递模式 / 运行状态 / 入站接管；安全注记「读取状态不会初始化运行档…」 | `pages/宿主管理/workspace.html:25-40` |
| 实例生命周期（四卡） | 连接探测（执行探测）、初始化运行档（初始化）、启动接管（启动）、停止接管（停止），各带确认对话框 | `workspace.html:42-90` |

数据端点：**双前缀自适应**——先探测 `astrbot_plugin_private_companion_v2/staging`（单目标）与 `.../host`（多目标）两个候选前缀（`pages/宿主管理/app.js:4-7,170-186`）；`GET {prefix}/status`、`POST {prefix}/probe|initialize|start|stop`（`:174,199,207`）；错误码本地化表 `:8-48`。

## 三、配置部分

**无配置组**；写的是**控制路由**：

| action | 后端方法 | 说明 |
| --- | --- | --- |
| `GET status` | `controller.status`（`astrbot_host/web_api.py:89,139`） | 只读 |
| `POST probe` | `controller.probe`（`controller.py:283`） | 探测原生目标 |
| `POST initialize` | `controller.initialize`（`controller.py:405`） | 初始化 staging 档案 |
| `POST start` / `POST stop` | `controller`（`controller.py:448,655`） | 启停 intake |
| `POST authorize-delivery` / `revoke-delivery` | `controller.authorize_delivery`（`controller.py:491,619`；TTL 见 `settings.py:38`） | 发送授权（正式入口；setup 向导走引导专用 TTL，见 [16-setup.md](16-setup.md)） |
| `POST prepare-screen` / `upgrade-screen` | `controller.py:545`、`web_api.py:154-177` | 原生 Screen 准备/升级（强制 dashboard 身份） |
| `GET inspect`、`GET preview` | `controller.py:841,854` | 证据/批次与预览草稿 |

iframe 桥白名单只放行 `status|probe|initialize|start|stop` 五个动作（`product-page.js:577-579`）——authorize-delivery 等不在工作区内触达。

## 四、边界与空态

- 多目标模式自动切 `host` 前缀；单目标失败会尝试另一前缀（`app.js:170-186`）。
- 启停类操作都有二次确认；`GET` 只允许 status（父页桥强制）。

## 五、后端情况

- 单目标：`/astrbot_plugin_private_companion_v2/staging/*`（`web_api.py:37` API_PREFIX，11 条路由 `:89-99`）→ `astrbot_host/controller.py`（`AstrBotStagingBootstrap`、`NativeProbe`、`StorageRuntime` 等，`controller.py:14-27`）。
- 多目标：`/astrbot_plugin_private_companion_v2/host/*`（`multi_api.py:29,156,162-167`）→ `multi_controller.py`（`MultiAuthority`、`MultiHostSession`，`multi_controller.py:10-28`）。
- 路由注册/注销：`StagingWebAPI.register()/unregister()`（`web_api.py:84-137`，按 `(route, id(handler))` 剔除）；鉴权 `request.username`（空或 `api_key:` 前缀即拒，`web_api.py:158-160`）。

## 六、相关设计稿与复核

- 引导式首次设置 → [16-setup.md](16-setup.md)；备份 → [19-data.md](19-data.md)。
- 复核：`grep -n "staging/" astrbot_host/web_api.py | head`；`sed -n '4,7p' pages/宿主管理/app.js`。
