# V2 原生能力提供方宿主装配切片

日期：2026-09-25。范围：原生能力提供方合同、AstrBot 发现与装配、原回执和产物读取、单/多目标宿主接线。本记录只列本切片；Image owner、图片采用与发送、无 V1 独立验收由对应任务记录。

## 实现

- `NATIVE_PROVIDER_CONTRACT_20260925.md` 固定 `companion.native-provider.v1` 的 manifest、JSON 请求/响应、`execute`、可选只读 `lookup`、`read_artifact` 和领域采用边界。宿主没有自动 lookup 或重放流程。
- `companion_v2/capabilities/native.py` 校验普通有限 JSON、完整原始回执和制品元数据；原始 bytes 通过大小和 SHA-256 复核后才交给采用器。制品标识不用于推断路径或下载地址。
- `astrbot_host/native_extensions/discovery.py` 仅从唯一启用且 `root_dir_name` 精确匹配的 Star 读取稳定 `extension_api.companion_v2_native()`。不导入可选插件业务模块、不发现或读取其数据目录；`companion_v2_status()` 不升级为执行权限。
- 注册表固定 Star、插件实例、extension_api、port 四层对象身份和完整声明。包/后端配置世代在正常重启时稳定；旧对象或运行租约失效后，必须通过新 session 创建新的注册表。
- `NativeExtensionRegistry.attach(application)` 绑定一个原 V2 runtime；声明目录的登记事务会再次复核当前提供方，任一冲突全部回滚。登记不 acquire、不启用角色、不授予权限。
- 单目标 controller/bootstrap 和多目标 controller/session 均接入注册表。初始化及 `load_existing` 不写能力目录；显式 `start` 登记声明，再启动 application。stop/terminate 关闭旧注册表；无提供方时仍能启动，且不创建空 ExternalToolExecutor。
- `ExternalToolInvocation.before_dispatch` 沿用原 child/parent task 与能力授权；提供方每次真实 I/O 前调用宿主发放的同步回调，该回调在本次 awaited 调用返回时失效。原生角色由 bridge 在异步边界复核。
- `result_handlers` 默认包含 Image 领域采用器，验证后的原件进入现有 V2 来源、图片和 sender 流程；平台发送不交给原生能力端口。

## 回执与采用失败

`execute` 返回后先校验原始请求与回执，再复核当前权限和实例。回执合法且后端已经成功时，随后撤权、换实例、角色变化、取消、制品损坏、遗漏 dispatch 检查或采用失败都不会将已确认成功改写为 unknown。

该路径原样保留 state/effect/operation/receipt，返回 `images=()` 和 `GovernanceState.REVOKED` 的 SourceRecord。Source 正文保留原 native metadata，另附 `adoption.state=unavailable` 与原因码；该材料不能用于模型或投递。已撤权时不再读取制品或调用采用器。失败和未知回执没有成功 Source；收到回执前的取消仍传播；错绑、格式错误或效果合同不合法的响应仍视为无法确认。

核心回执持久化与图片采用的事务调整，以及 Image provider 在后端结果落库后返回控制回执的调整，分别由对应任务维护。最终冻结副本已通过无 V1 独立验收，包括真实 Image 原生执行链在后端成功后撤权时的回执保留；证据见下方交接补记。

## 定向验证

本次回执修复后使用 AstrBot 自带 Python，4 个模块共 **39 项通过**：

| 模块 | 数量 | 重点 |
| --- | ---: | --- |
| `tests.test_native_provider_contract` | 3 | manifest 版本、artifact 哈希、回执绑定与 effect |
| `tests.test_native_extensions_registry` | 21 | I/O 前护栏、对象替换、旧回调失效、结果后撤权/角色变化/取消、制品损坏、采用器篡改、未知无材料 |
| `tests.test_native_provider_host` | 11 | 真实核心授权与 child task、目录原子性、成功回执持久化、撤权/实例更换后无发送、损坏制品不可采用、错绑结果保持未知 |
| `tests.test_native_provider_sessions` | 4 | 单/多目标只读加载、显式启动登记但不授权、停机换实例重建、无可选提供方启动 |

报告：`D:/codex/workspaces/v2-native-providers-20260925/provider-tests-receipts.json`。详细日志：同目录 `provider-tests-receipts.log`。

此前接线批次还通过 staging/bootstrap 46 项、既有 external tools/host tools 33 项。Image 私聊首次联合批次本身为 8 项；此前记录的 14 是当时原生专项 6 项加 Image 8 项的合计，不能作为 Image 模块数量。群主链已落地，统筹任务报告其 2 项通过。本轮 Image/群聊最终联合和独立快照验收由统筹任务与验收任务另行记录，未并入上面的 39 项。

以上本窗口测试使用临时 ASTRBOT_ROOT、独立 V2 数据库、合成 Star/后端及本地 sender；没有真实模型、网络后端或平台发送，也没有操作 V1 数据或重载在线插件。

## 独立验收交接补记

验收任务已完成最终冻结副本的「仅本体」及「V2 + Image」两份全新隔离进程。两份均 `passed=true`、`worker_exit=0`、`violations=[]`，临时安装已清理。相同的本体 6 项检查只计一次；联合安装另验证 Image 11 个场景及整体清理，均独立记录，不与本窗口 39 项累加。

新增场景确认：Image 后端已 dispatch，撤权后才返回成功时，V2 与 owner 保留相同 operation_id、receipt_ref 和 committed effect；没有生成图片 payload、模型图片材料或图片投递。仍获授权的普通文本不在该撤权范围内。

完整证据和边界见 [NATIVE_INDEPENDENCE_ACCEPTANCE_20260925.md](NATIVE_INDEPENDENCE_ACCEPTANCE_20260925.md)。被测源码清单摘要：V2 600 文件为 `4e7569586eb90ef651aa2a392d01807accf3fbab0d35adc0b7dada8083ed3a11`，Image 19 文件为 `e446c5be1c6669dbe1378ab26591cd2b795193ace124da90b28aac2e0e6db630`。本补记只更新文档，没有改动已冻结的生产代码。

## 下一步

独立验收已完成，由统筹任务汇总私聊、群聊及本轮冻结源码的最终证据，再据该快照更新构建状态和安装包。现有发行 ZIP 早于本批原生实现，不能用作本轮验收产物；真实图片后端和平台发送仍需另行现场验证。
