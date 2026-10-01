# V2.0 整合验收

日期：2026-09-25。产品范围见 [发行说明](RELEASE_V2_0.md)。

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
