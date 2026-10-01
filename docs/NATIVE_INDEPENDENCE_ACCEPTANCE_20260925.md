# V2 原生独立性验收

日期：2026-09-25。本记录只描述 `native_acceptance` 实际运行的证据，不替代发布或在线安装验收。

最终状态：主线确认 Image 原生相关生产源码稳定后，重新创建的「仅本体」和「本体 + Image」两份独立安装均通过。两份安装的 V2 源码清单完全一致，终验后逐文件复核与当时工作区也完全一致。

## 隔离方式

- 使用 AstrBot 自带 Python，以 `-I -X utf8` 启动全新子进程；清除该子进程的 `PYTHONPATH`。
- 在 AstrBot 一级插件扫描目录之外创建临时安装。只复制明确选择的源码，不复制 V1 核心、用户配置、数据库、缓存、日志或其他插件目录。
- AstrBot SDK 首次导入前设置临时 `ASTRBOT_ROOT`，并验证 SDK 实际数据目录属于该临时根。
- V2 复制 `main.py`、必要元数据以及 `astrbot_host`、`companion_v2`、`tests`、`tools` 下的 Python 文件。Image 复制 `image_companion/native_v2`、命名空间初始化文件、合成后端夹具，以及包摘要引用的纯传输/验证源码；不复制 Image 旧 `main.py`。
- 静态 AST 检查生产源码中的 V1 导入、动态导入、旧插件发现与明显旧数据路径；运行时拦截直接/动态/缓存导入、旧模块来源、插件发现、文件与 SQLite 访问。
- 运行时拒绝访问实际安装的 AstrBot 数据与插件树。只允许读取临时根和已指定的 SDK/Python 运行环境；写入只允许临时根。路径会解析 junction/symlink 和 SQLite URI。
- 拒绝真实网络和子进程回退；Windows asyncio 内部的唤醒 socketpair 为限定例外。可信运行库引导阶段只允许 `kernel32`、`shell32` DLL，加载 loguru/click 后立即关闭该例外，再导入被测插件。
- 被捕获或吞掉的越界异常仍留在审计记录中，最终 `assert_clean()` 会失败。子进程失败、无报告、超时或临时目录未清理均不能报告成功。

这是可信 Python 代码的依赖审计和执行隔离验收，不是针对任意恶意原生机器码的操作系统沙箱。允许的 SDK/运行库会加载本地扩展，不能据此声称覆盖所有本地调用绕过方式。

## 已通过范围

| 范围 | 实际检查 |
| --- | --- |
| 本体入口 | 在临时副本导入真实 `main.py`，实例化 V2 插件；仅本体运行时副本没有 V1 或 Image 源码，合成宿主只发现 V2，不自动启动 |
| 授权 | 显式初始化后未授权启动失败，没有模型或平台发送；授权后通过实际插件事件入口完成合成对话并记录本地 ACK |
| 撤权 | 模型等待期间撤销发送授权，迟到生成不发送，也不再接收后续事件 |
| 停机 | 停止后重启仍拒绝已撤销授权；terminate 关闭运行库，32 条所属管理路由全部注销，挂起句柄为 0 |
| 原生发现 | Image 真实声明通过 `NativeExtensionRegistry` 发现；显式 `register_catalog` 只登记包声明，不自动取得包、启用角色或授权 |
| 生成与编辑 | 真实 `NativeImageOwner` / `NativeImageProvider` 执行，生成原图保存、经真实 registry 与 `image_result_handler` 采用，由 V2 合成 sender 发送；编辑只使用同来源保存的原图，只发送最终选定产物 |
| 未采用与未知 | 未被选中的图片保留但不自动发送；后端返回未知时不产生可用图片、不自动重新提交 |
| 原图读取 | 实际调用 `lookup` 和 `read_artifact`，核对操作号、回执、字节与 SHA-256；错误摘要被拒绝；关闭后的端口不可读，重开后读取原操作不重新生成 |
| 授权失效 | 最终采用前撤权阻止整条发送；等待中撤权阻止下一次后端调用；撤权后回执和原图读取均被拒绝 |
| 撤权后的已发生操作 | 后端 dispatch 已完成、授权撤销后才返回成功时，Image 原操作仍为成功；V2 保留相同 operation_id、receipt_ref 与 committed effect，但不创建图片材料，不向模型暴露该图片或 Image 原始材料，也不投递图片。此场景不额外禁止仍获授权的普通文本 |
| 重启 | 保存图的后续发送能恢复并保留原回执；未知发送重启后仍为未知，不重新发送 |
| 清理 | 所有场景的应用、后端、owner 任务、数据库与临时根完成清理 |

两份最终运行均为 `passed=true`、`worker_exit=0`、`violations=[]`、`temporary_installation_removed=true`。两份安装都完成相同的本体 6 项检查，不重复累计；联合安装另完成 Image 11 个场景，加 1 项整体清理检查。仅本体报告的 `optional_sources_present=false`，联合报告为 `true`。

Image 场景共 10 次合成后端提交、19 次合成模型调用、8 次合成 sender 尝试（其中包含未知回执，不能全部算确认发送）。每份安装的核心场景各为 2 次合成模型调用、1 次本地平台 ACK。真实模型请求、真实平台发送均为 0。

新增的隔离/runner 定向测试共 19 项：18 通过、1 跳过。唯一跳过项为 Windows 当前权限下无法创建 symlink；不能把它记为已验证。其他对抗性场景覆盖直接/动态/嵌套/缓存别名导入、吞异常、旧插件发现、文件/SQLite URI、允许父目录下的禁读数据、目录穿越、网络与子进程回退、传输源码静态依赖，以及模拟子进程超时/缺报告/非零退出时的清理和失败报告路径。

## 终验快照

V2 共复制 600 个文件；Image 共复制 19 个文件，静态旧版可执行依赖发现均为空。下列 inventory 摘要使用逐文件路径与摘要映射的规范 JSON 计算；报告同时保留完整逐文件清单。

| 对象 | SHA-256 |
| --- | --- |
| V2 inventory | `4e7569586eb90ef651aa2a392d01807accf3fbab0d35adc0b7dada8083ed3a11` |
| Image inventory | `e446c5be1c6669dbe1378ab26591cd2b795193ace124da90b28aac2e0e6db630` |
| 联合报告文件 | `d72f48359ca7066ecb1f6fb9e7a5866492026f4d6bd03fd11688c677ffb9916f` |
| 完整源码清单文件 | `6e0522d4d180c0f74a8a8696ecc3f6901bafde6ab86c9416f2cd4db4b84133e2` |

核心两处冻结文件已与主线提供值核对：`companion_v2/conversation/media/generated.py` 为 `a20e93537b81a3920cf4d537edd18b25e6aa577977b50313a8d8e882883a301a`；`companion_v2/conversation/external_tools.py` 为 `e3918389469b5b11d3d72037284dfd401b2fc6608b210ea7d7c488ba9de20fec`。其他任务之后的新修改不自动获得本次通过结论。

## 复现

在 V2 源码目录使用 PowerShell：

```powershell
$env:PYTHONIOENCODING='utf-8'
& C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 -m unittest tests.test_native_acceptance tests.test_native_acceptance_runner -v

& C:/Users/99505/.astrbot/backend/python/python.exe -X utf8 -m tools.native_acceptance `
  --host-source C:/Users/99505/.astrbot/backend/app `
  --image-source C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_image_companion `
  --output D:/codex/workspaces/v2-native-acceptance-20260925
```

省略 `--image-source` 时只验证本体，并明确报告 `provider_execution=not_run`。当前 SDK 路径会经 junction 解析至 `E:/astrbot/backend/app`。

证据文件：

- `D:/codex/workspaces/v2-native-acceptance-20260925/native-acceptance.json`：联合报告。
- 同目录 `native-source-files.json`：实际被测副本的逐文件 SHA-256，区分 V2 和 Image 源码。
- 同目录 `native-acceptance-process.log`：子进程本地输出。
- 同目录 `native-acceptance-unit.log`：19 项隔离/runner 测试的实际输出。
- `D:/codex/workspaces/v2-native-acceptance-20260925-core/native-acceptance.json`：仅本体的独立运行报告。

工具/场景位于 `tools/native_acceptance*.py`、`tests/native_acceptance*.py`；对抗性测试为 `tests/test_native_acceptance.py` 和 `tests/test_native_acceptance_runner.py`。

## 尚未由本记录验证

- 本体使用真实 AstrBot SDK，但由测试导入入口并注入合成宿主；未启动完整 Dashboard、插件扫描器或平台服务。
- Image 验收边界是原生模块、合成 Star 和真实 V2 执行/采用链路；未装载其旧插件入口，也未测试真实外部 SD/ComfyUI 服务。
- 合成 sender 的调用和 ACK 不等于真实平台已收到消息。群 SDK、其他提供方、迟到平台 ACK，以及并行角色计划/日历/管理页的主线测试，不纳入本记录的独立隔离通过数。
- 未在在线 AstrBot 中安装、启停或重载插件，未读取、迁移或修改 V1 用户数据。
- 已发布的 2.0.0 ZIP 保持原有内容，本次仅新增验收工具与记录。发布新包需使用最终验证的源码快照另行构建，不能以本报告替代发布包验收。
