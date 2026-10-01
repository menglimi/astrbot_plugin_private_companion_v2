# Content 原生消费端完整切片

日期：2026-09-25。实现位于唯一 V2 本体 `astrbot_plugin_private_companion_v2`；Content 继续使用既有可选提供方登记，不增加插件注册或公开页面。

## 已接通的角色调用

原角色任务可调用 `content.work.create`、`save_candidate`、`adopt`、`retract`、`list`、`describe`、`read`。候选版本保存、采用及固定版本读取进入既有角色工具循环。读取结果作为受治理的原始材料继续交给原角色模型，模型草稿再通过原会话的发送队列投递。

验证中的完整版本链包含创建、保存候选、采用、读取旧版、读取新版、描述及列出作品，共七次工具调用；撤回动作由独立场景覆盖。旧版与新版正文分别按指定版本返回，保留 Unicode、换行和缩进。

Content 私域 owner 由可信任务解析：安装 ID、逻辑 Bot ID、角色主体 ID，加实际请求者主体的稳定关系标识。会话、任务与运行代次不进入 owner，因此获授权的另一会话可以访问同一关系的作品；Bot、人格或参与者改变则不能借用已有作品。contributor 由原角色及实际请求者生成。工具参数不接受模型提供的 owner、身份或来源句柄。

## 提供方接口与访问边界

宿主通过原生登记发现 `content.native`，不导入 Content 插件、不读取其数据库文件。所需端口为：

- 通用 `companion.native-provider.v1` 的 manifest、execute、lookup。
- `bind_content_context(request, target=..., check_access=...)`：单次 awaited 调用绑定原任务、可信 owner、contributor 及原始来源；退出即失效。
- `content_state(request, before_dispatch=...)`：同步查询特定作品或固定版本的当前治理状态。
- `content_events(request, before_dispatch=...)`：按安装 ID 和持久游标分页读取撤回事件。

提供方在实际 I/O 与提交处调用 AccessPort，宿主检查原任务、角色、Bot、参与者、受众、当前能力授权、来源版本及内容哈希。每次治理查询还核对当前加载的提供方实例，替换实例或卸载不能沿用旧租约。

生产组装：`astrbot_host/native_extensions/content.py`。身份、访问及来源归属：`companion_v2/conversation/content/`。对接的 Content 原生实现位于可选插件的 `companion/content_v2/`，不依赖 V1 主插件。

## 来源与撤回传播

固定版本读取生成 `content.governance` 作品根与版本锚点。版本锚点引用作品根和创建该版本的原始来源，公开工具结果再引用版本锚点；派生来源沿现有 `source_dependencies` 继续传播治理。固定版本返回页必须保留请求的 work/version/offset、正文区间与哈希，缺少哈希或与治理端不符时不能作为模型材料。

来源发布时，同一事务保存 owner 治理要求。宿主关闭或重启后尚未重新绑定 owner，历史引用不可读；重新组装只恢复检查能力，不把已撤回来源重新启用。原始输入撤回、当前读取授权撤销、角色变更及提供方失效都会使依赖正文不可再读。

Content 在撤回事务中写出事件。消费端通过 V2 既有 inbox 和 runtime_metadata 持久游标处理，撤回所有对应 owner/work 的锚点并传播到派生来源。单次最多四页、每页一百个；积压期间每次读仍检查提供方当前状态。重复消费不重复撤回，重启能补消费遗漏事件，无新增表。

模型网关在实际调用前及返回后重查缓存材料的显式来源。返回后先结算实际模型用量与回执，再丢弃因撤回失效的草稿。已发送段落的事实回执保留，尚未发送的旧正文不能继续发送。作品创建、保存、采用、撤回的控制回执不承载正文，也不因作品撤回被改写成操作未发生。

`ExternalToolResponse.dependencies` 将结果发布和依赖链接放在同一事务内，检查原作用域与每位受众。输入在返回后撤回时保留确认的操作结果，将正文来源直接标为 revoked；依赖存储失败会回滚来源发布。

协调任务补充了单次同步校验内的依赖遍历去重，Content 来源读取贯穿同一 observed_at，版本锚点先建立根再取得创建时刻。去重状态不跨顶层调用、线程或异步任务复用，不跳过每次来源读取的身份、受众与哈希检查。递增时钟下 24 层版本链实测仅 25 次状态核验、24 次身份授权，避免版本链增长导致重复递归检查。

## 验证方式

使用 AstrBot 自带 Python `C:/Users/99505/.astrbot/backend/python/python.exe`，宿主 SDK 来自 `C:/Users/99505/.astrbot/backend/app`，SDK 数据根指向临时目录。

定向测试模块：`tests.test_native_content_flow`、`tests.test_external_source_dependencies`、`tests.test_source_owner_governance`、`tests.test_model_source_fence`。最终运行记录写入 `D:/codex/workspaces/v2-content-consumer-20260925/`。

最终结果：

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 本地定向测试 | 26/26，通过，无跳过 | `final-tests.json`、`final-tests.log` |
| 复制源码、全新 `-I` 进程 | 同一组 26/26，通过，无跳过 | `isolated/content-consumer-acceptance.json`、`isolated/content-consumer-process.log` |
| 24 层来源链、每次调用递增时钟 | 1/1，通过 | `clock-chain-test.json`、`clock-chain-test.log` |
| 关键源码与隔离验收快照一致性 | 18 个 V2 文件与 7 个 Content 原生文件全部一致 | `consumer-source-hashes.json` |

26 项由 Content 端到端 15 项、外部结果依赖 5 项、owner 治理 3 项及模型来源检查 3 项组成。本地与隔离进程执行的是同一组场景，不累计成 52 个独立用例；来源链单项也不与协调任务的同项回归重复计数。

隔离审计 `violations=[]`，V1 与 Content 旧入口均未加载，真实模型请求和平台消息均为 0，worker 退出码为 0，临时安装已回收。完整复制清单见 `isolated/content-source-files.json`；其 V2 清单摘要为 `16cb8d03ece056a2f72f15c8383014beee965943b181766eec6039c4d1173d79`，Content 原生清单摘要为 `edb59bca5d3065fb5443dab4327317ccff4367e580fcab69c2edd19157823022`。较早的 `flow-development`、`shared-regression`、`additional-tests` 文件是开发中失败记录，最终结论以上述最终报告为准。

可复现的独立验收命令（在 V2 项目根执行）：

```powershell
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m tools.content_consumer_acceptance `
  --content-source 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_content_companion' `
  --host-source 'C:/Users/99505/.astrbot/backend/app' `
  --output 'D:/codex/workspaces/v2-content-consumer-20260925/isolated' `
  --scratch-parent 'D:/codex/workspaces/v2-content-consumer-20260925/scratch'
```

脚本只复制选定源码，临时安装位于插件扫描目录之外，通过全新 `-I` 进程执行。读取真实 SDK，但使用合成 Star、模型及发送器；Content 加载的是实际原生 provider 与本地事务实现。既有 NativeAcceptanceGuard 在 SDK 和复制插件导入前启用，审计 V1 导入、生产插件及数据访问、真实网络、子进程和越界写入。报告包含逐项结果、审计记录、复制源码哈希与临时安装回收结果。

此验收覆盖 Content 原生模块和 V2 消费端，不把合成 Star 的加载描述为真实 Content main 入口加载。提供方入口的独立验证由 Content 窗口记录在 `CONTENT_NATIVE_HOST_SLICE_20260925.md`。本切片只启用获授权的私聊作品访问，不包含群聊 Content、真实模型、真实平台投递、在线重载或新版发布包。

## 下一步

协调任务汇总本切片与 Image、关系及其他功能域的原生验收，之后从一致源码快照构建更新包。2026-09-25 较早生成的 ZIP 早于本次原生消费端变更，不能用于宣称此切片已打包交付。
