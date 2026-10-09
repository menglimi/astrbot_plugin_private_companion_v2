# AstrBot 宿主与迁移实测计划

日期：2026-10-09。用于当前 V2 源码构建后的交付包验收，以及获批的 V1 配置和运行数据迁移。本文是测试计划，不代表已执行生产迁移、已修改运行配置或已连接 QQ。

## 测试边界

验收报告分开记录三种证据：

1. **合成测试**：临时夹具、FakeEvent、FakeProvider 和 FakeReverseApi。它验证转换、路由和失败语义，不证明当前 AstrBot 实例或 QQ 可用。
2. **AstrBot 本机宿主测试**：AstrBot 自带 Python、真实 SDK/插件管理器和真实路由注册机制，数据根指向临时目录；平台、模型仍由本机替身提供。它证明交付包能被宿主加载和停机，不证明外部平台收发成功。
3. **外部 QQ/OneBot 测试**：接入指定的真实账号、真实 OneBot 连接并观察外部消息送达。只有记录实际账号、消息 ID、时间及回执的测试才可称为外部实测。当前计划没有发出外部测试消息的授权；完成本地阶段后另行安排。

本次已确认的群目标范围是当前 OneBot 账号下四个同号群：`1097283005`、`145326153`、`555551401`、`915052038`，并启用这四项。验收时逐项核对平台、登录账号和群号，`*` 不可代替该清单。测试计划本身不执行这些配置变更。

V1 数据只读。任何测试副本都放在插件扫描目录之外；不得对真实 V1 源做写入。测试日志和报告只保留必要的 ID、计数、哈希与错误码，不输出令牌、正文、提示词或用户个人内容。

## 1. 构建当前交付包

每轮构建使用新的输出目录和空的解包目录；输出目录必须在已安装插件目录之外。不要复用旧包的验收报告。完整套件构建需要所有可选提供方目录和元数据齐全；若当前只构建本体，报告必须明确标成 core-only。

```powershell
$Repo = (Get-Location).Path
$AstrBot = 'C:\Users\99505\.astrbot'
$Python = Join-Path $AstrBot 'backend\python\python.exe'
$RunId = Get-Date -Format 'yyyyMMdd-HHmmss'
$Release = Join-Path $env:TEMP "companion-v2-release-$RunId"
$Extracted = Join-Path $env:TEMP "companion-v2-verified-$RunId"

& $Python -X utf8 tools/sync_framework_page.py --check
if ($LASTEXITCODE -ne 0) { throw 'Workspace resources are stale; sync and rebuild before packaging.' }

& $Python -X utf8 tools/build_v2_release.py --output $Release
if ($LASTEXITCODE -ne 0) { throw 'Release build failed; record the failing package and stop acceptance.' }

& $Python -X utf8 tools/verify_v2_release.py `
  --release $Release `
  --extract-to $Extracted `
  --host-check
if ($LASTEXITCODE -ne 0) { throw 'Extracted-package verification or host check failed.' }
```

`verify_v2_release.py` 检查归档校验和、文件清单哈希、Python 语法、配置默认值及迁移合同；`--host-check` 从解包后的本体运行 `tests.multi_life_entry_process` 和迁移验收模块，并写出 `package-verification.json`。该迁移验收模块创建的是合成 V1 数据，不会读取现役 V1。

复核 `release-manifest.json`、`SHA256SUMS.txt`、`package-verification.json` 和本体 ZIP 的 SHA-256，确保报告指向本轮产物。若完整套件因某个可选提供方而构建失败，先记录失败；core-only 结果不得替代完整套件结果。

## 2. AstrBot 本机 Python 与隔离数据根

AstrBot SDK 测试使用随 AstrBot 安装的解释器。宿主导入需要 `backend\app`；从解包目录运行测试时，将解包根也加入 `PYTHONPATH`，以免误导入已安装的旧本体或工作树源码。SDK 导入前设置临时 `ASTRBOT_ROOT`；`tests/astrbot_data_root.py` 也会在相关进程导入 SDK 前建立临时根并检查数据库路径。

```powershell
$Core = Join-Path $Extracted 'astrbot_plugin_private_companion_v2'
$TestRoot = Join-Path $env:TEMP "companion-v2-astrbot-root-$RunId"
New-Item -ItemType Directory -Path $TestRoot -Force | Out-Null
$env:ASTRBOT_ROOT = $TestRoot
$env:PYTHONPATH = "$Extracted;$AstrBot\backend\app"
Push-Location $Core
try {
  & $Python -X utf8 -c "import sys; print(sys.executable); import astrbot; print(astrbot.__file__)"
  if ($LASTEXITCODE -ne 0) { throw 'AstrBot SDK import failed.' }
} finally {
  Pop-Location
}
```

如果当前 SDK 版本没有顶层 `astrbot` 包名，使用 `from astrbot.core import db_helper` 做导入检查。以 `db_helper.db_path` 位于 `$TestRoot` 下作为隔离证据；路径落到正式 `.astrbot` 数据根时立即停止，不运行后续会写入的测试。

## 3. 宿主加载、停机、路由注册

先运行完整交付包的 `--host-check`。再从同一个解包目录启动真实 `PluginManager` 生命周期回归；该测试通过 AstrBot 插件管理器执行停用、启用和热重载，检查重复 handler、重复 API 路由和跨插件模块是否被误卸载：

```powershell
$env:ASTRBOT_ROOT = $TestRoot
$env:PYTHONPATH = "$Extracted;$AstrBot\backend\app"
Push-Location $Core
try {
  & $Python -X utf8 -m unittest tests.test_astrbot_plugin_reload -q
  if ($LASTEXITCODE -ne 0) { throw 'AstrBot PluginManager reload test failed.' }
} finally {
  Pop-Location
}
```

验收记录至少包括：插件注册名 `astrbot_plugin_private_companion_v2`；启动后运行态可用；停机后 handler 和 web API 路由全部注销；重载后配置可读、路由只注册一份；数据库仍在临时根；模型调用与平台发送均为 0。`tests.multi_life_entry_process` 额外检查四个角色生活路由、命令路由、天气读写路由及停机清理。该用例的宿主 SDK/插件入口是真实的，事件、模型与平台端口是替身。

## 4. 配置保存与变更回读

先在本轮解包包上运行定向 API 回归。不要连接生产插件页面来做写入测试。

```powershell
$env:ASTRBOT_ROOT = $TestRoot
$env:PYTHONPATH = "$Extracted;$AstrBot\backend\app"
Push-Location $Core
try {
  & $Python -X utf8 -m unittest `
    tests.test_account_target_sync `
    tests.test_session_topology `
    tests.test_configuration_api -q
  if ($LASTEXITCODE -ne 0) { throw 'Configuration save/readback tests failed.' }
} finally {
  Pop-Location
}
```

覆盖点：保存一个配置字段后 GET 回读；写入只影响指定 persona/window；无关字段保持原值；检查保存回执；重启宿主后仍可回读；未知账号、未选账号的目标、畸形列表和无效 persona 被拒绝且不留下半份配置；保存失败时旧配置继续可用。会话目录超时、读失败、路由冲突和回执后的读取失败分别确认错误阶段清楚，且不重复写入。

若需要核对真实页面交互，在独立 AstrBot 测试实例中安装本轮解包件，使用测试管理员登录唯一公开页「陪伴小屋」，经页面自己的认证桥保存夹具配置，并验证保存后回读和重启恢复。不得伪造 Dashboard 身份、直接写运行配置文件，或在生产数据根进行试写。群清单测试使用四个明确目标，保存和重启后仍是这四项且均启用；不得退化为通配目标。

## 5. 模拟 OneBot/QQ 收发链路

下列测试经过 AstrBot 消息事件或 OneBot 适配器合同，但不连接真实 QQ：

```powershell
$env:ASTRBOT_ROOT = $TestRoot
$env:PYTHONPATH = "$Extracted;$AstrBot\backend\app"
Push-Location $Core
try {
  & $Python -X utf8 -m unittest `
    tests.test_plugin_event_routing `
    tests.test_astrbot_onebot `
    tests.test_astrbot_inbound_adapter `
    tests.test_astrbot_plugin_reload -q
  if ($LASTEXITCODE -ne 0) { throw 'Simulated AstrBot/OneBot message path failed.' }
} finally {
  Pop-Location
}
```

本地事件应覆盖私聊、群聊、被提及、未被认领、静默、插件命令及其他监听器先后执行；核对 persona 和账号路由来自事件证据。发送端使用本地 reverse API 替身，分别验证有确认的回执、账号断开、无消息 ID、超时和发送失败。发送结果未知时不得标成已送达、写入确认历史或自动重放。测试报告分别列出“事件注入数、处理结果、已确认发送数、未知发送数、真实平台发送数”；此阶段真实平台发送数必须为 0。

## 6. 故障注入

故障注入只在合成夹具或隔离 AstrBot 实例进行，并保存输入指纹和预期/实际结果：

- **配置保存**：无效字段、未发现的账号/群、并发版本变化、持久化失败、保存成功但紧接着目录读取失败。预期是明确失败/冲突，旧值保持，或返回可核对的保存回执；不能出现误报成功。
- **收件**：重复事件 ID、缺少群/账号身份、其他插件先行消费、未提及群消息、静默策略。预期是不跨账号或 persona 路由、不重复触发、不吞掉其他插件应处理的事件。
- **发件**：原始登录离线、API 抛错、超时、无可确认消息 ID、错误收件人。预期是结果保持未知或失败，不换用另一个登录，也不重放真实发送。
- **迁移**：预览之后修改合成源、目标拓扑版本变化、重复执行同一批、群知识写入失败、归档源缺失/损坏。预期是过期计划被拒绝、重复执行幂等、失败批次不留下部分关系图，并保留源数据。

现成重点用例包括 `tests.test_account_target_sync`、`tests.test_session_topology`、`tests.test_astrbot_onebot`、`tests.test_legacy_data_host`、`tests.test_legacy_group_data_host` 和 `tests.test_legacy_data_acceptance_process`。必要时在此基础上补用例；不要通过修改被测生产配置来制造故障。

## 7. V1 正式迁移与收据核验

正式迁移必须在当前交付包通过第 1 至 6 节后进行，使用宿主公开迁移页/API 的计划、确认和执行流程；不允许以手工 SQL、复制数据库表或测试脚本代替真实迁移功能。

1. 先保存可恢复的 V2 备份，并单独备份插件配置文件；V2 数据备份不包含宿主插件配置。记录 V1 源文件清单/哈希和 V2 迁移前快照标识。V1 保持只读。
2. 对每个来源平台、账号、V1 persona 到 V2 role 的映射分别生成计划。检查未映射 persona、平台/账号冲突、分组归属、重复项、拒绝项及所有 `needs_input`。身份不明确时暂停该映射，不猜测单平台或单人格。
3. 配置迁移和运行数据迁移分开预览、分开执行。运行数据至少核对表情素材、日记/梦境、角色关系、群成员/边、群知识/worldbook、归档以及独立记忆数据库的计划和结果。四个已确认群按精确群号映射到当前 OneBot 账号；空群 `145326153` 的计划为零条时应记录为空结果，不编造记录。
4. 执行前确认计划 token 对应本次未变化的源和目标。只使用官方 UI/API 的正式 `apply`/`data-apply`；保存响应中的批次/操作 ID、写入/跳过/冲突计数、来源哈希、目标角色和群映射、归档校验结果及错误码。将正文、提示词和凭证从报告中剔除。
5. 执行后重新生成计划并读取目标页面/服务；用计数、稳定 ID/内容哈希及拒绝/跳过清单对账。重启 AstrBot 后再读一次。对允许重试的来源重复预览/执行，确认不产生重复素材、日记、边或记忆。
6. 复算 V1 源文件哈希，必须和迁移前一致。V2 的迁移收据和重启后读取结果都通过，才算该来源完成；单有计划、归档 ZIP 或成功 HTTP 状态不算完成。

独立 `memory_companion.db` 必须单独验收其实际可恢复、可查询数据与治理状态；仅生成或校验快照/归档，不代表时间线和治理数据已迁入并在 V2 中可用。须检查删除墓碑、撤回、捕获关闭、拒绝/撤销规则、ACL/策略、审核队列等治理信息，不能把待审或拒绝数据激活，也不能把旧授权扩成跨窗口访问。若交付包尚无正式的主动恢复/读取路径，该项明确记为未完成，不能以归档收据关闭迁移。

上一轮只读清点可用于对账参考（不是本次计划的成功断言）：表情 116 项、日记/梦境 15 项；世界书为 2 条通用、17 条成员线索、3 条群资料。群网络历史清点为 `1097283005` 375 名成员/80 条边/1 条知识，`555551401` 285/80/2，`915052038` 39/80，`145326153` 无记录。正式计划重新读取并生成当前数字；若有变化，以当前计划和收据为准并解释差异。

## 完成标准与报告格式

每个阶段单独记录命令、开始/结束时间、交付包哈希、测试根、用例总数/失败数、路由数、配置回读结果、迁移操作 ID 和计数、V1 前后哈希，以及模型调用/真实平台发送数量。失败保留原始错误码和最小脱敏上下文。

完成“AstrBot 本机宿主验证”只表示当前包被本机 AstrBot SDK/插件管理器正确加载并通过隔离测试；完成“V1 迁移”要求所有获批映射都有正式收据、重启后读取和来源对账；完成“外部 QQ 实测”另要求真实 OneBot 连接及平台消息回执。三个状态不可互相代替。
