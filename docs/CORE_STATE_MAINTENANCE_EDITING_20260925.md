# 状态维护参数与周期校准页面

日期：2026-09-25

## 已落地

唯一公开入口“陪伴小屋 → 管理与设置 → 角色状态”新增身体与周期设置。当前会话可编辑后台维护开关、1–1440 分钟维护间隔及日程读写开关；同一 Bot 下的角色共享饥饿、健康与生理期模拟开关。页面明确区分会话配置和共享参数。

生理期参数包括基础三阶段/六阶段模式、周期时区、首次定位方式、六个阶段各 1–30 天的时长、不适感受开关、阶段轻微波动与最多 2048 字的表达偏好。基础模式合并中间四阶段为恢复期；轻微波动保持总周期时长不变。界面沿用现有周期语义：时长与波动调整由后续维护采纳后从下一轮应用，修改时区或首次定位方式不会自行改写已有起点。表达偏好继续用于提示词，不增加强制拒绝交流的规则。

周期校准是独立的显式操作，打开表单后必须选择指定周期日、不适用、尚未确定或交回角色判断。指定周期日按当前已保存周期长度校验；后三种方式提交 `day: null`。保存会重建定位并清除旧周期感受，其他身体感受沿用原服务规则；“交回角色判断”恢复后续维护的适用性决定。校准只描述角色模拟。

维护与周期表单复用上一批状态编辑器：只提交改动字段、保留原配置版本、冲突时保存草稿并显式读取新版本，未改动字段采用并发更新结果。原请求固定原会话/角色，结果不明时保留完整请求供显式核对；重新挂载或实际刷新页面不自动提交。尚未提交的草稿只保存在当前编辑器内，不提供关闭页面后的草稿恢复。

## 校准并发与回执

状态 API 新增只读 `cycle_settings_token`，`cycle.align` 接受可选的 `settings_token`；新页面始终提供。旧调用方继续沿用既有合同。令牌涵盖参与校准的共享身体/周期参数，QQ 展示与本会话维护频率不参与，避免无关设置更新阻止校准。原 state revision / view_token 仍核对角色、管理者、授权与状态版本。

实际写入前，在现有事务内复核参数令牌；其他会话改动共享参数时返回 `role_cycle_settings_conflict`，不写新状态。页面保留选择与周期日，读取新配置后重新展示时长和时区，再由操作者保存。

对携带令牌的校准，原始身体载荷与令牌纳入现有幂等指纹，在应用当前设置的显示过滤前固定。已完成回执可以在之后关闭饥饿开关或修改时区后核对，不重新定位，也不返回旧私人正文；同一 operation key 换令牌仍被拒绝。原来源与现行授权复核继续有效。

## 文件归属与协调

- `pages/陪伴小屋/state-maintenance.js`：维护/周期字段、表单、范围说明与校准请求。
- `state-editor.js`：复用草稿、版本冲突、原请求持有与作用域隔离。
- `state-page.css`、小屋 `index.html`：表单样式及增量脚本引用，保留整合任务对入口的调整。
- `companion_v2/role_work/state/management.py` / `service.py`：校准参数令牌、事务内复核和幂等指纹；`astrbot_host/state_api.py` 仅扩展既有命令字段白名单。
- `tools/check_state_maintenance.cjs`：由状态页验收链调用的身体与周期编辑场景。

状态页 `api()` 对 SDK 已解包对象、直接 envelope 和嵌套 envelope 的兼容由整合任务完成，本窗口保留该修复并扩展三种返回格式下的编辑验收。入口分工遵循 [注册统一记录](REGISTRATION_UNIFICATION_20260925.md)：三个工作区源码保持 `workspace.html`，小屋内部生成工作区保持 `index.html`，Content 仅为 `design-previews/companion-v2` 开发预览。本批没有修改注册身份、重建工作区旧入口或执行在线重载。

本批是已交付 V2.0 套件快照之后的源码增量，没有改写已有发行 ZIP；后续打包与在线重载继续由原分工协调。

## 验证

使用 AstrBot 自带 Python、临时测试数据根和本地模型/平台替身，共 **38 项定向测试通过，新增 3 项**。

```powershell
$env:PYTHONPATH="$PWD;C:\Users\99505\.astrbot\backend\app"
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 -m unittest tests.test_role_state_api tests.test_role_state_configuration tests.test_role_cycle tests.test_role_cycle_optimization.CycleProvenanceTests
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 -m unittest tests.test_role_body.RoleBodyTests.test_cycle_calibration_detects_settings_changed_from_another_window tests.test_role_body.RoleBodyTests.test_physical_settings_are_shared_but_presentation_and_enablement_remain_local
```

首组 36 项、共享范围 2 项均通过。收窄参数令牌到相关身体/周期设置后，受影响的校准 API 与跨会话校准两项单独复验通过，不重复计数。覆盖旧校准合同、参数与状态冲突、非字符串令牌拒绝、后来配置修改后的原回执、共享参数及本地设置隔离、周期来源复核、既有宿主启停和状态路由注销。没有重复运行协调方的注册盘点或四进程整合验收。

`tools/check_state_page.cjs` 默认使用 SDK 直接返回数据的合成桥；`COMPANION_STATE_BRIDGE_MODE=envelope` / `nested` 验证两种旧返回结构。三种模式的整条状态编辑浏览器场景均通过，包含原有 QQ 编辑和回执恢复，以及本次新增的最小字段更新、并发草稿、时区/表达长度校验、文本转义、参数和状态双重冲突、实际页面重载后原校准核对、交回角色判断和关闭周期后的操作状态。桌面、390px/320px 均覆盖，完整编辑流程在 320px 执行，已人工检查桌面与窄屏截图，浏览器错误为空。

相关 JS 语法、UTF-8 / 无 BOM / LF / 末尾换行及 V2 规范页面构建清单检查通过。无 schema 迁移、真实模型/QQ 调用或 V1 数据访问；真实 QQ 连续输入提示效果仍沿已有现场验收计划处理。

## 下一步

接入角色计划创建、改期和取消的页面操作，明确一次事件与重复日程的修改范围，继续保留原来源、提醒和版本回执，让随日程更新的 QQ 短状态拥有完整的管理入口。后续实际 QQ 验收和在线重载仍由协调任务统一安排。
