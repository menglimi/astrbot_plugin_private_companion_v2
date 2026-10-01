# 新框架注册协调回执

日期：2026-09-25

接收来源任务：`01a0cd49-59e3-7e90-8050-9d6281c49d18`。

本窗口当前负责角色状态、共享作息及 QQ 展示管理链，本轮为角色状态页的展示配置和日程公开文案编辑，并非群媒体/记忆主线。业务继续在 `C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2` 内推进。

本轮涉及目录与文件：

- `companion_v2/agenda/calendar.py`：增加仅修改已有角色计划公开文案的命令。
- `astrbot_host/state_api.py`：在既有状态命令入口增加 `calendar.presence` 字段白名单；未增加独立宿主或本体注册。
- `pages/陪伴小屋/state-editor.js`、`state-page.js`、`state-page.css`、`index.html`：接入编辑表单、冲突保留草稿和原请求核对；`index.html` 仅增加编辑器脚本及状态资源版本。
- `tests/`、`tools/check_state_page.cjs`、`tools/check_state_editor.cjs`、`docs/` 与导航文档：定向测试及落地记录。收尾运行已有 `tools/sync_framework_page.py`，更新本体页面构建清单。

本窗口未修改 `main.py`、`metadata.yaml`、页面发现/注册机制、宿主插件身份或在线注册表，也未新增、改名或重复注册第二个新框架本体。当前磁盘元数据为 `astrbot_plugin_private_companion_v2`，产品名为“我会永远陪着你 V2.0”；本轮状态页 API host 继续使用这一身份。没有收到与此不同的身份或注册方案指示。

页面以该目录的 `pages/陪伴小屋/` 为规范源，Content 仅为可选预览。本轮不发布 Content 镜像，不将 Content 旧外壳覆盖回本体，不为展示入口新注册插件。

没有准备或执行在线重载；本轮仅使用临时数据根、合成浏览器桥与本地平台/模型替身进行验证。后续保持本体注册统一工作由来源任务协调，不单独进行在线重载。本文所述仅为本窗口操作范围，不代表已盘点其他窗口或 AstrBot 在线注册状态。

本轮编辑能力收尾后，下一步拟接状态维护参数、饥饿/健康/生理期设置与周期校准页面，继续复用同一本体与既有状态 API。

## 协调方后续确认

来源任务已回报在线仅有一个 V2 本体；此为协调方核验结果，本窗口不重复操作在线注册。

唯一公开 Dashboard 主入口统一为“陪伴小屋”，宿主管理、日记与生活、关系与记忆保留为内部工作区，功能继续可用。入口与构建调整由任务“整理打包目前所有的设计稿内容”（`01a0b900-c7a3-71f0-b95e-f05c7c40eda8`）负责。本窗口继续维护 `state-editor.js` / `state-page.js`，共享 `index.html` 只做增量保留，不接管或覆盖入口调整。

协调方已将 `main.py` 的注册名改为 `PLUGIN_NAME`，与 `metadata.name` 对齐；本窗口沿用这一结果。在线重载继续由来源任务最后统一协调。

## 状态领域后续批次

已读取更新后的 `AGENTS.md` 和 `docs/REGISTRATION_UNIFICATION_20260925.md`。沿用协调方“在线一个 V2 本体、唯一公开陪伴小屋”的结果，不重复盘点或改动在线注册。三个工作区源码入口为 `workspace.html`；Content 预览位置为 `design-previews/companion-v2`。

状态维护参数与周期校准已完成，详情见 [本批记录](CORE_STATE_MAINTENANCE_EDITING_20260925.md)。新增 `pages/陪伴小屋/state-maintenance.js`，对共享小屋 `index.html` 只增加该脚本及更新三处状态资源版本；保留整合任务的 `state-page.js` SDK 返回值兼容修复。原状态 API 增加参数令牌及校准字段，没有新路由或注册入口。38 项定向测试、三种桥格式浏览器验收通过；本窗口仍未在线重载，没有改写已交付套件 ZIP。
