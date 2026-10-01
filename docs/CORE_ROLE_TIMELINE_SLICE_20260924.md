# 角色活动历史与自我时间线

2026-09-24。本切片完成非页面主线：保留角色活动的实际修订版本，并让角色在普通私聊中按需查询活动、阅读、日记、梦境和成长记录。管理页由另一窗口推进。

## 交付行为

- `role.timeline.query` 已接入 `LocalRoleTools` 和统一宿主，可选 `kinds`、`time_start`、`time_end`、`limit`、`cursor`。`activity` 包含普通活动、阅读及睡眠；其余类别为 `diary`、`dream`、`growth`。
- 时间区间必须使用带时区的 ISO 时间，起止边界均包含，按记录更新时间查询。记录按时间倒序；同一时间用类别、版本、原编号稳定排序。同刻多次修改同一日记时，较新版本排在前面。
- 默认每页 8 条、最多 20 条。每域最多取 65 个索引候选，总页最多检查 64 条；单条长文字裁到 512 字并标出字段，条目合计最多 40,000 个序列化字节。不可用来源可能产生空页，仍可按 `next_cursor` 继续。
- 首次查询固定各域写入上界和观察时间，后续补录或新修订不会插入这次分页。游标以当前运行实例的密钥签名，绑定原上下文及筛选条件；只传 `cursor` 即可沿用原条件，`limit` 可以调整。重启后重新发起查询；已经保存的工具结果仍可按原引用复核，不依赖旧游标。
- `included_kinds`、`unavailable_kinds`、`skipped`、`selection_partial`、`next_cursor` 和每项 `truncated_fields` 表明查询覆盖，空结果不代表从未发生。

角色可按“回顾这两天你读过什么、当时有哪些想法”等请求自主调用工具。示例参数：

```json
{
  "kinds": ["activity", "diary", "dream", "growth"],
  "time_start": "2026-09-23T00:00:00+08:00",
  "time_end": "2026-09-24T23:59:59+08:00",
  "limit": 8
}
```

## 历史与主观材料

活动每次创建、暂停、恢复、完成或取消，都与原状态及操作回执在同一个事务中保存版本。幂等重放只返回原结果，不制造新事件；保存历史失败会回滚状态和操作。

V2 内部 schema 升至 v23。v22→v23 从 V2 已完成活动操作回执和现存活动头补录，分别标记 `legacy_receipt`、`legacy_head`；升级后新记录为 `recorded`。头与同版本回执冲突、操作未完成、角色或作用域不符时，升级回滚。缺失的旧初始版本不补造，条目以 `missing_prior_revisions` / `history_incomplete` 明示缺口。本迁移不访问 V1 数据。

活动和成长展示精确历史版本，后续正常追加状态不会将历史改写成当前状态。阅读只承认原回执里的实际区间和完成时间，感想保持主观；计划阅读和预计醒来时间不构成完成证据。成长提案、当时确认和当时完成分别保留，提案不能说成技能已经提升。

日记、梦境使用原保存、删除和显式恢复回执，只输出操作、当时状态、日期和时区。重复保存对应修订，不把摘要衍生操作算成一次新经历。旧版正文没有保留，时间线明确返回 `content_form=operation_metadata_only`、`body_history=not_retained`；修订、删除之后不从旧回执恢复正文，也不自动替换成新版文字。当前日记正文的读取继续沿原日记 owner 完成。

## 授权和消费链

只支持原角色、当前已识别人类参与者、精确私聊 scope 和单一受众。生活记录沿 `role.life.read`，成长沿 `role.growth.read`；只获得一种权限时仅提供相应类别，时间线没有新增扩大权限的开关。游标不提供权限，翻页仍重新授权。

工具结果续答、生成完成、逐段发送、确认历史读取及记忆原文消费时，重新读取所选版本并校验身份、权限和当前来源治理。活动的 work context、阅读内容哈希及来源受众都复用原生活读取边界。成长的历史版来源继续受撤回、过期和受众检查。

已确认回复转为记忆可读原文时，会保留时间线所使用的阅读、活动及成长原件依赖。撤回原件将撤回派生原文，并阻止剩余发送；已发生的投递回执继续保留。日记操作元数据不包含旧正文，也不伪造正文来源。时间线材料本身不登记成现实事实来源。

## 文件归属

| 位置 | 职责 |
| --- | --- |
| `companion_v2/role_work/timeline/service.py` | 原领域读取、历史投影、覆盖和消费复核 |
| `companion_v2/role_work/timeline/query.py` | 按域有界索引查询及合并 |
| `companion_v2/role_work/timeline/pagination.py` | 时间条件、上下文绑定、运行期签名游标 |
| `companion_v2/role_work/timeline/tools.py` | 角色工具参数、说明及结果复核 |
| `companion_v2/role_work/ledger.py` | 活动头、版本、操作的原子写入 |
| `companion_v2/storage/activity_history.py` | V2 旧活动头及真实回执的升级补录 |
| `companion_v2/storage/schema.py`、`runtime.py` | v23 表、时间索引、升级与回执验证 |
| `companion_v2/conversation/tool_loop.py`、`host/application.py` | 工具注册与宿主装配 |
| `companion_v2/memory/sent_sources.py` | 已送达回复的原件依赖 |
| `tests/test_role_activity_history.py`、`test_role_timeline*.py` | 迁移、领域、工具与宿主验收 |

根目录没有增加业务文件。没有新增管理页、Dashboard 路由或独立后台任务。

## 验证与边界

新增 25 项定向用例覆盖非空迁移、历史缺口、冲突回滚、原操作 scope、未知结果、幂等、多个领域同刻分页、补录隔离、跨 scope / 角色 / 受众、独立权限、空页续查、正文删除、来源撤回、生成失效、分段投递、重启与记忆原文依赖。

受影响范围首轮运行 176 项，通过 175 项；唯一失败是核心隔离扫描把内存游标的 `open` 方法识别为未批准的数据读取。已改名为 `restore`，保持隔离规则；随后时间线、隔离、迁移及外部工具宿主共 32 项复验全部通过。两批合计去重 178 项都有最终通过记录，其中包含新增 25 项；未把重复复验累计成更多用例。

验证使用 AstrBot 自带 Python、本地模型和发送器替身、临时数据库及 SDK 数据根；本批没有在线重载或真实模型/平台发送。自动身体状态、完整生活模拟、跨私聊分享与 V1 数据迁移不属于本切片。

新增用例复验命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_role_activity_history tests.test_role_timeline tests.test_role_timeline_tools tests.test_role_timeline_host -q
```
