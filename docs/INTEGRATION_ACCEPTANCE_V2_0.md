# V2.0 整合验收

当前版本：2.1.1。改造日期：2026-10-13。产品范围见 [发行说明](RELEASE_V2_0.md)，实际归属见 [原生拓展改造](NATIVE_EXTENSIONS_REWORK_20261011.md)。

## 当前单包改造

普通私聊和获准群聊使用 AstrBot 核心回复管线。Content、Image、Screen、Reality、Together、Game、Live 迁入同一个 V2 插件的原生内部模块，配置、网页及运行资产随唯一安装包交付，由 V2 管理生命周期。AstrBot 只注册 `astrbot_plugin_private_companion_v2` 的一个 Star，唯一公开 Dashboard Page 为「陪伴小屋」。

| 内部模块 | 随包领域/宿主目录 | 必须包含的资源 |
| --- | --- | --- |
| Content | `companion_v2/content/`、`astrbot_host/native_extensions/content.py` | 作品及版本服务、内部提供方 |
| Image | `astrbot_host/native_extensions/image_native/` | 后端、编辑、图片 API 及内部设置 |
| Screen | `astrbot_host/native_extensions/screen_provider.py`、`screens.py` | 单次采集及 V2 原件消费 |
| Reality | `companion_v2/reality/`、`astrbot_host/native_extensions/reality/` | 默认设置/schema、设备测试音频 |
| Together | `companion_v2/together/`、`astrbot_host/native_extensions/together/` | 默认设置/schema、房间网页、默认头像和图标库 |
| Game | `companion_v2/games/`、`astrbot_host/native_extensions/game/` | 原生规则、默认设置/schema、游戏网页和图标库 |
| Live | `companion_v2/live/`、`astrbot_host/native_extensions/live/` | 默认设置/schema、blivedm、SoulLink 桥接脚本、引擎及许可证 |

构建脚本只读取当前 V2 源码，默认发布 `astrbot_plugin_private_companion_v2-2.1.1.zip` 和清单。验包检查一个安装包、七项模块及资源、一个 Star、唯一插件身份和唯一公开页；运行代码不导入七个旧同级伴侣插件。模型、平台、设备和直播等真实外部服务的连接效果另按使用环境验收。

2.1.0 的自动升级范围为已有 V2 能力目录：旧提供方身份转换为内部模块身份，已有生命周期、授权、角色选择及历史保留。2.1.1 为七项原生能力增加了与发行版本绑定的运行时工件基线，防止同一版本的原生能力内容发生漂移。上述 V2 升级不读取 V1 数据；明确请求的 V1 正式迁移仍沿原流程验证。

本轮从最终源码统一构建新包，并从解包副本验收。对应包的哈希、通过项目及实际验证范围记录在交付目录的 `ACCEPTANCE_20261011.md` 和验收目录的 `package-verification.json`；历史核心回复包和 2026-09-25 八包套件的结果保留在下方历史记录中。

统一验收入口：

```powershell
python -X utf8 tools/sync_framework_page.py
python -X utf8 tools/sync_framework_page.py --check
python -X utf8 tools/build_v2_release.py --output <新的交付目录>
& '<AstrBot>/backend/python/python.exe' -X utf8 tools/verify_v2_release.py --release <新的交付目录> --extract-to <新的验收目录> --host-check
```

`--host-check` 使用 AstrBot 自带 Python，从解包副本执行真实 SDK 入口的加载、启停、路由注销及迁移合同检查；进程的 `ASTRBOT_ROOT` 指向临时目录，`PYTHONPATH` 仅使用候选包和 `backend/app`，模型与平台使用本地替身。更多领域测试由本轮新包统一验收覆盖。`package-verification.json` 保存在新的验收目录，`RELEASE_FILES.json` 在包内保存实际内容。

## 历史记录：2026-09-25 八包整合

以下为当时的源码和交付套件验收记录。七个独立伴侣的状态接口与八个 ZIP 均属于历史架构，保留原始验证范围供追溯。

## 本次变更

- 产品版本统一为 2.0.0，本体目录及最终注册 ID 为 `astrbot_plugin_private_companion_v2`。
- 唯一公开一级拓展页为「陪伴小屋」；宿主、日记生活、关系工作区保留源码并内嵌。
- 小屋目标/角色选择统一贯通生活、关系、记忆、状态、日历与成长。
- 多目标目录补充关系与成长的既有管理 API；能力目录支持初始化之前的已认证读取。
- 七个可选伴侣加入只读状态接口，执行器及配置继续归原插件。
- 修复实际 SDK 的已解包返回、嵌套工作区沙箱阻拦、群目标清空、日程错误跳转与状态工作区返回值兼容。
- Content 开发预览移出公开 pages；源码构建、浏览器检查及 Demo HTTP 页面映射同步更新。

## 定向验证

1. 首轮后端组合 56 项通过，覆盖产品目录、目标目录、隔离、单/多目标宿主、成长与关系管理；收尾增加不可读插件页面目录场景，相关 15 项复验通过。数目含重复覆盖，不相加。
2. 真实 SDK 插件入口的多目标生活独立进程通过：4 个生活路由、停机与路由注销成功，模型/平台调用为 0。
3. 小屋浏览器 10 项验收通过：真实 SDK 消息桥、opaque-origin 沙箱、目标选择、真实总览、日程/状态入口、非模态布置、生活配置、关系、成长命令、群目标清空、初始化前目录、撤权清空与 1440/390/320px 布局。浏览器及服务端错误为 0；两次写入仅针对合成夹具。
4. 记忆浏览器 22 项通过：检索、来源、历史、修订、设置、遗忘预览、丢回执、原操作恢复、目标隔离、键盘及窄屏；所有数据为合成夹具。
5. 状态与编辑器定向浏览器通过：状态/作息、QQ 展示诊断、原请求回执、设置最小差异、公开文案、分页、冲突、丢回执、目标切换、撤权和 390/320px。
6. 内部页面入口收敛后，宿主管理原 7 项、生活和关系原浏览器检查全部通过；真实 SDK 页面发现只返回「陪伴小屋」，内部宿主资产仍可解析。
7. 首轮 8 个 ZIP 的逐文件 SHA-256、路径与源码语法校验通过；本体解压到独立目录后，实际 SDK 主入口的多目标生活启停与路由注销通过，4 个生活路由可用，模型/平台调用均为 0。默认两个宿主开关为关闭；正式投递固定为 `onebot_private`，旧 `preview` 只做兼容读取归一化。
8. 注册协调窗口另完成最终页面/产品 12 项及四进程真实 SDK/浏览器 30 项，覆盖单/多目标首次初始化与重启恢复、HTTP 工作区、启停和清理；临时数据已回收，真实模型和平台消息均为 0。此处引用已有证据，不重复计入本窗口测试总数。

核心测试使用 AstrBot 自带 Python，SDK 数据根在导入前改为临时目录。自动验收未发送真实平台消息，未调用真实模型或读取 V1 用户数据。

## 本机只读接入

已登录 AstrBot 的插件列表显示产品名「我会永远陪着你 V2.0」和版本 2.0.0；小屋显示「已连接」，可进入真实宿主管理。历史 preview 运行档仅用于核对旧配置归一化，不代表当前正式模式；本次没有启用 start，也没有连接真实 QQ/OneBot。

注册协调任务已核对在线只保留一个 V2 本体和唯一 Page「陪伴小屋」，Content 不再公开旧预览。图片重复实例已由协调任务移出扫描目录；本任务刷新正式小屋后，图片能力显示 0.4.5「状态已接入」。其他未重载的旧实例显示「待加载适配器」，停用插件保持停用状态。本任务没有额外在线重载。

## 可重现命令

```powershell
$env:PYTHONPATH = '<AstrBot>/backend/app'
& '<AstrBot>/backend/python/python.exe' -X utf8 -m unittest tests.test_product_integration tests.test_page_targets_api tests.test_isolation -q
& '<AstrBot>/backend/python/python.exe' -X utf8 -m tests.multi_life_entry_process
python -X utf8 tools/sync_framework_page.py --check
python -X utf8 tools/build_v2_release.py --output <交付目录>
& '<AstrBot>/backend/python/python.exe' -X utf8 tools/verify_v2_release.py --release <交付目录> --extract-to <新的验收目录> --host-check
```

浏览器检查脚本位于 `tools/check_product_page.cjs`、`check_framework_memory_page.cjs`、`check_state_page.cjs`；使用本机 Playwright 与 Chrome，桥接脚本取自已安装 AstrBot。独立宿主/生活/关系检查仍可直接验证内部源码 `workspace.html`。

各包的确切内容以交付目录的 `release-manifest.json` 及包内 `RELEASE_FILES.json` 为准。打包从已验收的解压快照收尾；其他窗口仍在开发的状态维护/周期编辑不提前进入本轮快照。
