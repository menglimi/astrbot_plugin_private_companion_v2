# 拓展能力定向检查（2026-09-30）

## 结论

七个可选提供方的本地原生执行切片通过定向测试，但当前产品还不能认定为“安装后即可在 V2 对话中正常使用”。主要缺口是小屋尚未接通通用的能力安装选择、按 Bot／人格启用、按用户／会话授权入口。

本记录检查当前工作区源码。测试使用临时 V2 数据根、合成身份和本地模型／平台／设备替身，不代表新交付包或真实外部环境验收。

## 已验证的执行范围

| 提供方 | 本次本地验证范围 | 结果 |
| --- | --- | --- |
| Content | 作品创建、固定版本读取、候选采用、续写锚点、撤回传播、跨 Bot／人格／用户隔离 | 通过 |
| Image | 生成／编辑结果采用、选中产物投递、未知结果不重放、撤权与重启恢复 | 通过 |
| Screen | 合成截图进入上下文、原件权限、篡改与撤回、禁止成为可发送图片、重启不重截 | 通过 |
| Together | 房间创建／读取／关闭、邀请范围、人格及 V2 模型绑定、停机与异常日志处理 | 通过 |
| Reality | 原生读取、设备操作回执、取消边界、未知结果不重发、范围隔离 | 通过 |
| Game | 井字棋、五子棋、贪心骰子、二十一点、象棋；对局隔离、持久恢复及相关终局／撤权场景 | 通过 |
| Live | 状态和事件读取、增量游标、会话隔离、配置过滤、原生目录注册 | 通过 |

提供方流程测试共 68 项，全部通过。这些结果只覆盖上述切片；Together 的真实邀请投递、Live 的开播／画面／语音呈现等不能由这些读取和回执测试推定成功。

## 当前使用链路的缺口

### 1. 加载提供方不会启用本体调用权限

`astrbot_host/native_extensions/__init__.py` 的 `register_catalog()` 登记包描述。单目标和多目标宿主在启动时调用它，不会同时执行 `acquire()`、`set_role_enabled()` 或 `set_authorization()`。

`tests/test_native_provider_sessions.py` 已验证：启动后能读到描述，但能力安装记录仍不存在。`companion_v2/conversation/external_tools.py` 的 `_admit()` 则要求：

1. 当前描述与已选择的安装包一致；
2. 该 Bot 的当前人格已启用此能力；
3. 当前用户在完整会话范围内具备能力同意和调用授权。

任一条件不满足，该能力就不会进入模型工具目录。因此“提供方插件已加载”不足以证明普通 V2 对话能够调用它。

### 2. 通用启用／授权入口尚未全部补齐

当前唯一专门准备入口是单目标 `web_api.py` 的 `/prepare-screen`，它调用 `staging_bootstrap.py` 为固定私聊目标准备 Screen。多目标宿主没有对应的 Screen 准备路由。

Content、Image、Together、Game、Live 的通用管理服务已经存在于 `companion_v2/capabilities/management.py`，公开的通用消费入口仍未补齐。Reality 的手机摘要已新增按所选私聊目标／Bot／人格管理的独立入口，见 [Reality 手机位置接线](REALITY_LOCATION_V2_ACCESS_20260930.md)；该入口开放原生摘要读取，设备控制与其他能力继续各自授权。

小屋 `app.js` 的 `capAction` 分支只更新页面本地预览状态，不调用能力管理 API。提供方自己的设置页可以修改提供方配置，但本体仍独立检查上述安装、角色启用与会话授权记录。

### 3. 状态目录没有表示本体的可调用性

`integration_registry.py` 的 `connected` 表示公开状态读取成功；`runtime_ready` 是提供方的自报状态；`execution_integrated` 当前固定为 `False`。这些字段没有给出选中目标／人格的本体授权结果。

小屋家具目录目前按 `integration_state === 'connected'` 将部分拓展归入“可用”组。这无法证明上述 `_admit()` 条件已满足，容易让用户高估实际可调用范围。

## 定向验证记录

宿主测试使用 AstrBot 自带 Python，并在 SDK 导入前设置临时 `ASTRBOT_ROOT`。以下各组有重复模块，不能直接相加为独立用例总数。

| 检查组 | 模块 | 结果 |
| --- | --- | --- |
| 目录、权限与配置 API | `test_capabilities`、`test_capability_configuration`、`test_product_integration`、`test_native_extensions_registry`、`test_native_provider_contract`、`test_perception_host_api`、`test_native_perception_host_api`、`test_model_provider_api` | 62 项通过 |
| SDK 页面发现和产品状态 | `test_page_targets_api`、`test_product_integration` | 15 项通过 |
| 宿主、生命周期与原生边界 | `test_native_provider_host`、`test_native_provider_sessions`、`test_native_tool_catalog`、`test_native_acceptance`、`test_native_acceptance_runner`、`test_native_provider_contract` | 40 项通过，1 项因 Windows 符号链接权限跳过 |
| 七类提供方执行切片 | `test_native_content_flow`、`test_native_image_flow`、`test_native_screen_flow`、`test_reality_together_native`、`test_live_native_provider`、`test_game_native_pig_dice`、`test_game_native_blackjack`、`test_game_native_xiangqi` | 68 项通过 |
| 前端状态、编辑器与接线 | `test_app_globals.cjs`、`test_section_wiring.cjs`、`test_models_page.cjs`、`test_native_perception_page.cjs`、`test_perception_page.cjs`、`test_home_styles.cjs` | 66 项通过 |
| 小屋工作区同步 | `tools/sync_framework_page.py --check` | 无待同步文件 |

## 本次修正

本轮修改四份测试，未新增生产授权行为：

- `test_product_integration.py`：用真实状态方法及原生元数据助手组成探针，补齐就绪状态夹具，检查原生端口消失后的降级。
- `test_page_targets_api.py`：移除已过期的缓存版本号断言，改为核对脚本入口和实际拓扑容器。
- `test_app_globals.cjs`：用 V8 全局声明实例化识别顶层函数，避免把不同嵌套作用域的 `finish()` 误报为全局覆盖；入口提前终止，不执行页面代码。
- `test_section_wiring.cjs`：只对当前已加载脚本使用的页面模块检查依赖，继续保留真实容器和挂载清单核对。未被当前入口使用的 `decision-page.js` 不代表活跃页面缺依赖。

上述文件均已检查 UTF-8、无 BOM、LF 和末尾换行。

## 尚未验证的环境

读取真实 Dashboard 时，浏览器工具返回 `unsupported Codex auth method: apikey`，未能取得在线提供方状态。本轮没有执行真实模型生成、屏幕采集、设备操作、平台消息发送、直播操作或运行插件重载；没有读写 V1 用户数据，也没有构建或验收新交付包。

## 后续接入顺序

先让小屋读取选中 Bot／人格／会话的能力投影，再通过既有管理服务接通安装选择、角色开关及显式同意操作；同时让家具状态显示本体可调用性。多目标 Screen 也需使用相同范围的管理入口。接线完成后按工程约定构建新包，再执行包内宿主加载、生命周期、路由注销和所选真实外部链路验收。
