# 角色计划管理页面闭环 · 2026-09-25

本批把角色计划创建、整组改期、单次例外、提醒及取消接入唯一公开页面「陪伴小屋 → 管理与设置 → 角色状态」。此前的 QQ 展示设置、日程公开文案、状态维护和生理期编辑仍可在原入口使用。

## 落盘范围

- 页面：新增 `pages/陪伴小屋/calendar-editor.js`；接入 `state-editor.js`、`state-page.js`、`state-page.css`、`index.html`。
- 后端：`companion_v2/role_work/state/management.py` 增加日程管理原请求的事务回执核验，修复提醒注册后旧视图无法核对原回执的问题。
- 测试：新增 `tests/test_role_calendar_api.py`、`tools/check_calendar_editor.cjs`；扩展 `tools/check_state_page.cjs` 合成桥，在 `tools/check_state_editor.cjs` 的权限撤销场景之前执行日程专项。
- 构建：用 `tools/sync_framework_page.py` 更新规范页面的 `page-build.json`。

没有变更日程领域服务的事件合同或来源继承规则，没有新增 API 路由、注册身份、schema、安装包或能力提供方。共享 `README.md` / `docs/BUILD_STATUS.md` 由统筹任务维护。本批不读取、迁移或修改 V1 用户数据，不在线重载，不调用真实 QQ 或模型。

## 操作合同

| 页面操作 | 命令 | 范围与结果 |
| --- | --- | --- |
| 创建角色计划 | `calendar.create` | 使用当前目标的 `create_token`、revision 0 和稳定请求键；只创建 `role_plan`，不代替用户确认约定。 |
| 修改整个日程 | `calendar.revise` | 一次事件直接改期；重复日程整体替换规则，显式携带原 `sources`，清除整组例外并取消原提醒。 |
| 仅改这次 | `calendar.exception` | 指定原发生次数，移动到新的时间或用 `start: null` 跳过；保留重复规则、来源及其他例外。 |
| 安排提醒 | `calendar.remind` | 指定一次发生；再次安排会替换原提醒。成功只表示本地排程，不表示消息已送达。 |
| 取消整组 | `calendar.cancel` | 取消整个安排及已有提醒；重复日程仅取消一次应使用“仅改这次 → 跳过这一次”。 |

单次例外也沿用既有服务行为，取消当前安排的提醒，即使提醒原来指向另一次发生；页面已明确提示需要重新安排。日程为 accepted 只表示安排被接受，不代表活动已完成。

核心操作者的管理权限与角色自动使用日程的开关分开处理：角色自动日程未开启时仍可整理计划；提醒仍要求原会话已有相应提醒授权。页面不自动添加这些授权。

时间按所选 IANA 时区输入，支持一次、每天、每周、每月、每年及间隔、次数、时长。夏令时重复时间可选择较早或较晚一次；不存在的本地时间可改选或顺延。修改标题等字段时，未修改的开始时间保留原始时间戳及秒/微秒精度。用户填写“第几次”从 1 开始，页面转换为 API 的 sequence。日程列表显示原开始时间、时区、重复规则、例外数量和提醒状态。

只有显式填写的最多 8 字短文案供 QQ 展示。标题、详情不会自动成为平台公开文案。

## 版本、来源与回执

日程编辑沿用当前目标、角色、操作者对应的 `revision` / `view_token`。冲突保留草稿并暂停保存，用户显式读取当前版本后再确认；整组编辑合并未被本次修改的最新字段。取消或不可读取的记录不会被强行覆盖。

每次提交先把完整原请求保存在当前会话的 `sessionStorage`，按 installation、操作者和目标 API 隔离。网络响应未知时允许刷新查看，但不自动 POST；“用原请求核对”使用相同 operation key、事件 ID、参数和版本。重载可恢复创建及提醒请求；“结束核对”只清除本地待核对记录，不撤销已经保存的安排。待核对摘要不展示标题或详情。角色切换后的迟到响应只清理原作用域回执，不把成功提示或草稿写入新角色。

真实 API 验证发现：第一次安排提醒会注册受管提醒对象并推进 object policy revision，因此原 view token 随即失效。仅依靠“先验证当前 token，再读取领域回执”会把已经成功的请求判为旧视图。

本批在同一事务内复用 `OperationRepository` 保存日程管理原请求的哈希和完成状态：

1. 每次仍先复查当前管理操作者、原参与者及角色绑定的授权。
2. 新请求仍验证当前 view token，并经过日程领域原有 CAS、来源与权限检查。
3. 已完成的管理原请求只有在完整参数、操作者绑定和目标身份一致时，才读取领域原回执；不会重建提醒或重复写入日程。
4. 改参数复用请求键返回冲突；用新请求键提交旧视图仍被拒绝。管理授权撤销后即使原请求相同也被拒绝。
5. 管理请求与领域写入一同提交或回滚，无新增表或迁移。状态、周期及配置命令不走这个分支。

核对的是本批已记录的原管理请求。不会为旧请求补造通过校验的记录，也不绕过已失效的管理授权。

## 定向验证

后端共 **15 项不同的定向用例通过**：新增日程 API 专项 5 项，既有日历服务 6 项，单目标状态 API 2 项，多目标状态 API 2 项。新增专项最后单独执行输出 `Ran 5 tests ... OK`；其余 10 项已在本次生产补丁后通过，不重复计数。

```powershell
$env:PYTHONPATH="$PWD;C:/Users/99505/.astrbot/backend/app"
$calendarCases = @(
  'tests.test_role_calendar_api',
  'tests.test_role_state.CalendarTests',
  'tests.test_role_state_api.StateAPITests.test_calendar_human_acceptance_and_new_view_after_revision',
  'tests.test_role_state_api.StateAPITests.test_calendar_public_wording_uses_original_version_and_exact_fields',
  'tests.test_astrbot_multi_state.MultiStateTests.test_public_wording_edit_stays_on_original_role_and_account',
  'tests.test_astrbot_multi_state.MultiStateTests.test_foreign_tokens_and_sources_cannot_change_another_target_or_persona'
)
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest @calendarCases
```

验证包含角色计划完整生命周期、原来源、提醒替换/取消、发生次数边界、缺失提醒授权、四类写入的 CAS 冲突、整组取消后的原创建回执不复活事件、原请求参数篡改、撤销管理权限，以及跨账号/角色的 token 和原请求隔离。修复后的生产管理文件 SHA-256 为 `1c06530d5071046ca969c46ff5a53ee200dd5284317c66f7bceea0669e649bd1`。

浏览器 `direct` / `envelope` / `nested` 三种返回模式的完整状态、周期及日程场景均通过，浏览器脚本错误为空。日程覆盖 weekly/once 创建、整组改期、移动/跳过一次、提醒、取消、三类冲突草稿、创建及提醒丢响应后重载核对、无自动 POST、迟到响应隔离、键盘提交、夏令时缺口/重复时间、未修改时间戳精度及 320/390/1366px 布局。已查看桌面和窄屏截图。

```powershell
$env:NODE_PATH = Join-Path $env:TEMP 'companion-calendar-playwright/node_modules'
$env:PLAYWRIGHT_EXECUTABLE_PATH = 'C:/Users/99505/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
foreach ($bridgeMode in @('direct', 'envelope', 'nested')) {
  $env:COMPANION_STATE_BRIDGE_MODE = $bridgeMode
  node tools/check_state_page.cjs
  if ($LASTEXITCODE -ne 0) { throw "State page verification failed: $bridgeMode" }
}
```

Playwright 依赖位于临时目录，插件没有新增 npm 依赖或安装包。上述路径为本机此次验证环境；其他环境设置为自己的 Playwright 模块和浏览器路径。

本次截图目录（临时验证产物）：

- direct：`C:/Users/99505/AppData/Local/Temp/state-page-YlNn8w`
- envelope：`C:/Users/99505/AppData/Local/Temp/state-page-itkSm9`
- nested：`C:/Users/99505/AppData/Local/Temp/state-page-QGkCee`

6 个相关 JS 文件语法、2 个 Python 文件语法及本批文本 UTF-8 / 无 BOM / LF / 末尾换行检查通过。规范页同步仅更新 `page-build.json`，随后检查输出 `{"mode": "check", "changed": []}`。

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/sync_framework_page.py
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/sync_framework_page.py --check
```

测试使用 AstrBot 自带 Python、临时 SDK/运行数据根、真实请求解析与本地平台/模型替身。浏览器合成桥负责验证交互和请求参数，真实服务测试负责验证来源、提醒状态、授权、CAS 和事务回执，二者不混称为真实平台验收。

## 下一步

将本批源码和证据纳入统筹任务的统一隔离验收与版本收口。之后安排日程驱动 QQ 短状态、提醒到期和连续输入提示的现场联调；以实际平台回执和客户端观察确认效果。本批没有执行现场调用或在线重载。
