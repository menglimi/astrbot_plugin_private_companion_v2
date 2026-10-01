# CORE-ASTRBOT 试运行配置与首次初始化

日期：2026-09-22。在[受控试运行会话](CORE_ASTRBOT_STAGING_SLICE.md)之上，补齐可信本地装配使用的配置解析、首次身份初始化与只读加载。独立宿主可以从一份明确配置建立测试身份、人格和精确授权，再进入原有生命周期。此次没有注册插件、连接真实模型/平台或读取现役 V1 数据；内部数据库仍为 v14。

## 入口与边界

| 入口 | 执行内容 | 结果含义 |
| --- | --- | --- |
| [StagingConfiguration.parse](../companion_v2/adapters/astrbot/staging_config.py) | 纯解析，检查 UTF-8、版本、字段、引用、期限、预算和资源限制。 | 格式有效，不证明配置提供者有管理权限，也不证明宿主在线。 |
| [validate_staging_config.py](../tools/validate_staging_config.py) | 只读调用者明确指定的文件，输出脱敏校验摘要。 | `valid` 与配置指纹；`native_host_verified`、`initialized`、`started` 均为 false。 |
| [AstrBotStagingBootstrap.initialize](../companion_v2/adapters/astrbot/staging_bootstrap.py) | 可信本地管理入口；检查全新专用 V2 库及宿主映射，原子登记身份、人格、授权和初始化回执。 | 首次成功或原初始化回执的只读重放；尚未取得运行代，也没有模型调用或平台发送。 |
| `load(runtime_instance_id=...)` | 只读核对原配置、当前身份/人格/授权及 provider，创建未启动会话。 | 可供后续 `start` 使用的装配对象；不补建身份、不重新授权、不重新应用文件默认值。 |
| `session.start(...)` / `receive(...)` | 沿既有试运行会话核对人格、当前配置与运行代，随后受理认证事件。 | 只有受理后调度的任务才可能调用模型；是否发送取决于已固定的模式及实际回执。 |

`initialize` 是与持久身份目录相同信任级别的本地控制面接口，不能直接暴露为聊天工具或未鉴权 HTTP 路由。`authority_ref` 是审计引用，不是凭据。可信调用方先确定安装管理权限、独立数据根和测试目标，再提供宿主 context、SDK 类型及配置。模块自身不查找默认数据目录、不导入 AstrBot、不注册事件处理器、不创建平台连接。

## 配置契约

内部配置版本为 `companion-v2.astrbot-staging.v1`，不是公共 wire SDK。JSON 全字段显式，拒绝未知/重复/缺失字段、未知版本、NaN/Infinity、布尔冒充数值、错误路由和核心管理动作。文档最大 128 KiB，要求 UTF-8，拒绝孤立代理字符；错误不回显传入字段值或敏感内容。合法零预算/零费率/零等待及空任务提示保留原值。

配置固定一组完整私聊 scope：安装、平台、Bot、登录账号、原生发送者、AstrBot conversation 和 session。参与主体必须是同安装 HUMAN，人格角色必须是同安装 BOT；OneBot 账号为规范正整数文本。角色提示指纹由可信装配对 `persona_instruction(...)` 使用现有 `digest(...)` 计算，provider 指纹使用 `provider_fingerprint(native_provider)`。后者只返回摘要，不导出原生 provider 配置或凭据。实际原人格内容和凭据继续由宿主持有。

最低授权是 `text`、`conversation.reply`、`configuration.read`，其余可选动作必须显式列出，并属于当前公共 action registry 的非核心动作。初始化只签发该完整窗口的 STANDARD 授权，不创建 CORE/IMPORTANT 等级。配置写权限需另列 `configuration.write`；便签、提醒、外部能力等继续由对应 owner 做当前授权与可用性检查，列出动作不等于安装或启用能力。

配置还明确费率、安装/Bot/角色/窗口/后台五层额度、任务提示、输出上限、输入估算上限、输出 token 参数、合并/分段时间和队列容量。费率是估算，不是供应商账单。`preview` 只生成可预览草稿但仍可能调用选定模型；`onebot_private` 只用于已有明确投递授权的独立测试目标。文件中没有凭据、端点、数据路径或管理员等级字段。

## 原子初始化和恢复

首次初始化拒绝非空业务表和曾改变的权限元数据；已有会话、能力、资料和其他身份不能被此入口收编。先在事务外检查当前原生 provider 类型/配置、已连接账号、conversation 和原人格，再在写事务内重新核对库状态，提交如下同一批记录：

1. 固定配置指纹的 `host.staging.bootstrap` 操作。
2. 原账号到 HUMAN 的身份绑定、不可变会话参与者和 session 人格绑定。
3. 配置列出的精确 STANDARD 授权及有效期。
4. 由便签 owner 准备的对象注册迁移标记。
5. 完成态初始化回执。

任何中途失败一起回滚，包括 owner 准备记录；并发初始化在原生 await 后重新核对，相同配置只提交一次。取消预检不会留下记录。原生 provider 在相邻查询中换对象、在 await 中改配置，或账号离线/人格不匹配时均拒绝初始化。

相同配置的 `initialize` 重放只观察当前记录，不再访问原生人格解析器，也不重新补权；它不是宿主健康检查。`load` 在只读快照内创建会话，后续 owner 若需要写入准备数据会失败，不能偷偷修复。首次初始化已把既有便签构造器需要的标记放在初始化事务内，因此正常加载不写数据库。

重放/加载要求原身份绑定、原人格选择及各原授权仍有效，不能用新建授权替代已撤销的那一条；撤权、过期、绑定或角色版本变化会明确失败。重新编辑配置文件，包括把预览改为真实发送、换目标/模型或改默认提示，均与原初始化指纹冲突。改变固定试运行条件应另建专用测试库；正在使用的提示/输出配置通过 `application.configuration` 的正式授权、差异提交和采用回执修改，重启保留这些值。

独立进程用合成 OneBot 超时写下 unknown 后直接退出，不调用会话关闭或 SQLite 关闭。另一个进程重建装配、取得新运行代，重复输入仍返回原批次，原投递 operation、unknown 回执和实际用量保留，新增模型/发送次数都是 0。随后撤销授权，再开第三个进程，初始化重放和加载都拒绝且库内容不变。这个证据限定于 unknown 已提交后的进程退出，不代表所有网络/断电时序已经覆盖。

## 示例与调用

[示例 JSON](../fixtures/astrbot_staging.example.json)全部来自合成夹具，账号、原人格/provider 指纹和预算不对应真实宿主。校验示例：

```powershell
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 tools/validate_staging_config.py fixtures/astrbot_staging.example.json
```

成功退出码为 0，格式/读取失败为 2。命令不初始化数据库、不连接模型或平台。摘要包含格式校验结果、配置指纹、模式和授权条数，不输出提示词、账号或 provider 配置。

可信宿主装配中的调用顺序如下。`staging_runtime` 由外部 owner 显式打开，`configuration_text` 已通过受信任本地入口取得；正常重启调用 `load` 即可，无须再次调用 `initialize`。

```python
from companion_v2.adapters.astrbot.staging_config import StagingConfiguration
from companion_v2.adapters.astrbot.staging_bootstrap import AstrBotStagingBootstrap

configuration = StagingConfiguration.parse(configuration_text)
bootstrap = AstrBotStagingBootstrap(
    staging_runtime, staging_context,
    configuration=configuration, native_types=native_types,
)
(await bootstrap.initialize()).unwrap()  # 仅显式首次配置流程需要。
session = bootstrap.load(runtime_instance_id="test-host-process-1").unwrap()
(await session.start(
    expected_task_generation=expected_task_generation,
    expected_model_generation=expected_model_generation,
)).unwrap()
# 由独立宿主显式转交已认证的原生事件，再沿 staging API 查看结果。
```

完整可执行合成装配见 [bootstrap 测试](../tests/test_astrbot_staging_bootstrap.py)、[独立进程夹具](../tests/staging_bootstrap_process.py)及[原生类型契约](../tools/native_contract_cases.py)。会话关闭与借用数据库/宿主客户端的责任沿上一切片，不在 `load` 中取得外部资源所有权。

## 实际验证

最终使用 AstrBot 自带 Python 3.12.12，测试范围为本切片及受影响的适配器、身份/人格、配置、便签权限和宿主恢复：

```powershell
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 -m unittest tests.test_astrbot_staging_config tests.test_astrbot_staging_bootstrap tests.test_astrbot_staging tests.test_astrbot_native tests.test_astrbot_onebot tests.test_isolation tests.test_persistent_identity tests.test_persona_resolution tests.test_configuration tests.test_agenda_access tests.test_host_application tests.test_host_recovery -q

& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 tools/run_native_contracts.py --host-source 'C:\Users\99505\.astrbot\archive\astrbot-4.27.2-audit'
```

- **131 项定向测试通过，22.000 秒**。本轮新增 24 项：配置解析/命令、原子初始化、只读加载、并发和取消、撤权/过期、provider 更换、配置重开及独立进程恢复。未将历史全量结果作为当前全量通过证明。
- **12 项原生契约通过，4.249 秒，网络尝试 0 次**。新增 2 项覆盖从配置/新库启动至原生 SDK 模拟生成、预览/明确投递及撤权。HTTP 使用 `httpx.MockTransport`，WebSocket 使用内存 peer，AstrBot 导入数据根重定向至临时目录。
- 示例命令实际运行成功，输出 `valid=true`，其余三个宿主/初始化/启动标志均为 false。
- 本轮涉及的 17 个文件通过 UTF-8 无 BOM、LF、末尾换行及空白检查；10 个 Python 文件通过 Python 3.10 AST 语法与编译检查，64 个本地 Markdown 链接可解析。
- 开发首轮 23 项中 3 个断言失败、1 个错误：其中两处揭示加载时便签 owner 写入迁移标记的问题，已把该准备移入首次事务并加只读快照；另外两处分别是测试误用配置字段名和撤权错误码。下一轮还有一处预览结果层级写错，已修正。最终用实际 owner 字段与结果复验，未删除或跳过失败用例。

## 后续

配置与身份装配入口已有隔离和原生类型证据；真实宿主的本地管理入口、凭据托管接线、账号/路由现场核对、生产模型/平台回执和旧 sender 围栏仍需专门切片及环境。群聊/媒体、完整角色生活、关系记忆、跨域 owner 投影、兼容选模和 V1 迁移继续按路线推进，本切片不改变 G8–G10 或替换发行资格。
