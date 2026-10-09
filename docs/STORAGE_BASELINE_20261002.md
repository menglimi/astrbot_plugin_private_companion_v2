# V2 存储基线（2026-10-02）

- 基线工具：`tools/audit_storage_baseline.py`（只读；598 行，sha256 `64e2d1cf…fdd6b`）
- 定向测试：`tests/test_storage_audit.py`（13 项，全绿；383 行，sha256 `7bf989fe…015cc8`）
- 实测快照时间：**2026-10-03 00:31**（WAL 比值降级为提示项后复跑于 00:39，数值逐字相同；
  文件名沿用使用者给的 `20261002`）
- 被测数据根：`C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2`，
  实际审计的是其中主库最近被写的 profile：`qq-v2-stream-20260926/runtime`
- 同目录另有**一个独立工具** `tools/audit_storage.py`（既有、非本次交付，303 行，
  sha256 `5398cf12…f19f5a`）。两者并存，互不依赖，**不要互相改名**——原委见 §6.3。

## 0. 这份记录是什么，不是什么

**是**：一次可复算的存储快照，加上一组**带触发条件的观察项**。每个数字都能用一条命令重跑出来，
每条线都写成一个具名常量并附了依据（见 `tools/audit_storage_baseline.py` 的模块 docstring）。

**不是**：待修清单。使用者已经明确：

- **暂不**加 WAL 自动维护／截断；
- **暂不**加新索引与历史保留策略。

这是有意的取舍，不是遗漏。代价是这几个量从此没有守卫，所以把它们变成观察项：**越线才动 schema**。
下面表格里任何一行"通过"都不代表这一项永远不会出问题，只代表**这一次实测**没到线。

判定分三种强度（`checks[].mode`），这一点决定了退出码：

| mode | 含义 | 越线后果 |
| --- | --- | --- |
| `hard` | 硬线 | 进 `violations`，**退出码非 0** |
| `advisory` | 提示线 | 只进 `notices`／打印 `! 提示`，**退出码不变** |
| `info` | 只报数 | 没有线 |

## 1. 基线快照（真实数据根实测）

### 1.1 文本输出（原样）

命令：`& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_storage_baseline.py`
退出码：**0**（无硬线越线；有 1 项提示，提示不影响退出码）

```text
==============================================================================
V2 存储基线审计（只读：不写库、不 checkpoint、不 VACUUM）
==============================================================================
  数据目录：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2
  审计数据根：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\qq-v2-stream-20260926\runtime
  profile：qq-v2-stream-20260926
  未审计：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\demo-preview-20260924\runtime（本次只审计主库最近被写的那个 profile）
  未审计：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\life-preview-20260923\runtime（本次只审计主库最近被写的那个 profile）
  未审计：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\sender-3\runtime（本次只审计主库最近被写的那个 profile）
  未审计：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\sender-2\runtime（本次只审计主库最近被写的那个 profile）
  未审计：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\sender-1\runtime（本次只审计主库最近被写的那个 profile）
  未审计：C:\Users\99505\.astrbot\data\plugin_data\astrbot_plugin_private_companion_v2\profiles\preview-1\runtime（本次只审计主库最近被写的那个 profile）

  库：companion-v2.sqlite3（journal_mode=wal，schema=companion-v2.storage.v47）
  旁库：memory-search.sqlite3 184320 B（180.0 KiB）  ← 整库可重建
  旁库：semantic-catalog.sqlite3 131072 B（128.0 KiB）  ← 含目录原始数据，不是可丢弃派生物（只有向量部分可再生成）

【实测 vs 阈值】
  检查项                  实测                              阈值                      判定
  --------------------------------------------------------------------------------------------
  主库大小                2338816 B（2.23 MiB）             —                         ·只报数
  WAL 常驻大小            729272 B（712.2 KiB）             > 33554432 B（32.00 MiB） ✓
  WAL／主库比值           31.2 %                            > 25 %                    ! 提示
  历史表合计行数          19 行（3 张 *_history 表）        > 5000 行                 ✓
  单域历史最大行数        15 行（role_state_history）       > 1000 行                 ✓
  document_json 最大长度  554 B，3 行                       > 65536 B（64.0 KiB）     ✓
  document_json 平均长度  268.0 B（3 行）                   > 4096 B（4.0 KiB）       ✓
  表数量                  125 张                            —                         ·只报数
  索引数量                74 个                             —                         ·只报数
  索引／表 比值           0.59                              —                         ·只报数

【各表行数 Top 10】
   1. execution_events                           195
   2. model_call_accounts                        137
   3. source_dependencies                        76
   4. configuration_values                       74
   5. schema_migrations                          46
   6. operations                                 37
   7. execution_attempts                         35
   8. execution_tasks                            35
   9. model_calls                                29
  10. model_rounds                               29

【提示 1 项（不参与退出码）】
  ! WAL／主库比值：31.2 %，提示线 > 25 %
      说明：小库的 WAL 比值天然偏高（主库才几 MiB 时，一次批量写入就能过半），同一条线在库长大后永远不会触发，所以只作观察、不判红。
      若确实要处理：先确认是不是活锁期的暂时膨胀；若确认常驻，只在停机窗口由维护流程显式 wal_checkpoint(TRUNCATE)，不启用自动维护（使用者已决定暂不加）。

结论：全部在观察线以内，本次没有需要动 schema 的越线项。
      另有 1 项提示（不参与退出码）：WAL／主库比值
```

### 1.2 `--json` 输出（原样）

命令：`& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_storage_baseline.py --json`
退出码：**0**

```json
{
  "tool": "tools/audit_storage_baseline.py",
  "data_root": "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2",
  "data_root_exists": true,
  "runtime_root": "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\qq-v2-stream-20260926\\runtime",
  "profile": "qq-v2-stream-20260926",
  "unused_runtime_roots": [
    "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\demo-preview-20260924\\runtime",
    "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\life-preview-20260923\\runtime",
    "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\sender-3\\runtime",
    "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\sender-2\\runtime",
    "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\sender-1\\runtime",
    "C:\\Users\\99505\\.astrbot\\data\\plugin_data\\astrbot_plugin_private_companion_v2\\profiles\\preview-1\\runtime"
  ],
  "status": "OK",
  "schema_version": "companion-v2.storage.v47",
  "journal_mode": "wal",
  "database_bytes": 2338816,
  "wal_bytes": 729272,
  "sidecars": {
    "memory-search.sqlite3": 184320,
    "semantic-catalog.sqlite3": 131072
  },
  "checks": [
    {
      "key": "main_bytes",
      "item": "主库大小",
      "measured": "2338816 B（2.23 MiB）",
      "threshold": null,
      "mode": "info",
      "over_line": false,
      "violated": false,
      "basis": "只报数：绝对体积本身说明不了问题，它是 WAL／主库比值的分母。"
    },
    {
      "key": "wal_bytes",
      "item": "WAL 常驻大小",
      "measured": "729272 B（712.2 KiB）",
      "threshold": "> 33554432 B（32.00 MiB）",
      "mode": "hard",
      "over_line": false,
      "violated": false,
      "basis": "WAL 常驻不回收会让备份从「一个文件」变成「三个文件必须一起拿」。"
    },
    {
      "key": "wal_ratio",
      "item": "WAL／主库比值",
      "measured": "31.2 %",
      "threshold": "> 25 %",
      "mode": "advisory",
      "over_line": true,
      "violated": false,
      "basis": "小库的 WAL 比值天然偏高（主库才几 MiB 时，一次批量写入就能过半），同一条线在库长大后永远不会触发，所以只作观察、不判红。"
    },
    {
      "key": "history_total",
      "item": "历史表合计行数",
      "measured": "19 行（3 张 *_history 表）",
      "threshold": "> 5000 行",
      "mode": "hard",
      "over_line": false,
      "violated": false,
      "basis": "历史只增不减；超过这个量级它更像没人读的日志，而不是回滚凭据。"
    },
    {
      "key": "history_domain",
      "item": "单域历史最大行数",
      "measured": "15 行（role_state_history）",
      "threshold": "> 1000 行",
      "mode": "hard",
      "over_line": false,
      "violated": false,
      "basis": "单域线比合计线更早生效：涨的通常只有一个域。"
    },
    {
      "key": "document_max",
      "item": "document_json 最大长度",
      "measured": "554 B，3 行",
      "threshold": "> 65536 B（64.0 KiB）",
      "mode": "hard",
      "over_line": false,
      "violated": false,
      "basis": "视图本该是短文档；到这个量级已经不适合逐行读。"
    },
    {
      "key": "document_average",
      "item": "document_json 平均长度",
      "measured": "268.0 B（3 行）",
      "threshold": "> 4096 B（4.0 KiB）",
      "mode": "hard",
      "over_line": false,
      "violated": false,
      "basis": "平均一条到一整页 page 时，物化视图就不再是索引，而是把正文抄了一份。"
    },
    {
      "key": "table_count",
      "item": "表数量",
      "measured": "125 张",
      "threshold": null,
      "mode": "info",
      "over_line": false,
      "violated": false,
      "basis": "只报数：表数量本身不是缺陷，记下来供与上次对照。"
    },
    {
      "key": "index_count",
      "item": "索引数量",
      "measured": "74 个",
      "threshold": null,
      "mode": "info",
      "over_line": false,
      "violated": false,
      "basis": "只报数：索引不是缺陷，但它决定写入放大，需要与增长一起看。"
    },
    {
      "key": "index_table_ratio",
      "item": "索引／表 比值",
      "measured": "0.59",
      "threshold": null,
      "mode": "info",
      "over_line": false,
      "violated": false,
      "basis": "只报数：用来判断「再加索引」这件事还值不值得。"
    }
  ],
  "top_tables": [
    { "table": "execution_events", "rows": 195 },
    { "table": "model_call_accounts", "rows": 137 },
    { "table": "source_dependencies", "rows": 76 },
    { "table": "configuration_values", "rows": 74 },
    { "table": "schema_migrations", "rows": 46 },
    { "table": "operations", "rows": 37 },
    { "table": "execution_attempts", "rows": 35 },
    { "table": "execution_tasks", "rows": 35 },
    { "table": "model_calls", "rows": 29 },
    { "table": "model_rounds", "rows": 29 }
  ],
  "violations": [],
  "notices": [
    {
      "key": "wal_ratio",
      "item": "WAL／主库比值",
      "measured": "31.2 %",
      "threshold": "> 25 %",
      "mode": "advisory",
      "over_line": true,
      "violated": false,
      "basis": "小库的 WAL 比值天然偏高（主库才几 MiB 时，一次批量写入就能过半），同一条线在库长大后永远不会触发，所以只作观察、不判红。"
    }
  ],
  "notes": []
}
```

> `top_tables` 的对象做了单行化排版（字段与取值原样，仅去掉换行），其余与工具输出逐字一致。

### 1.3 快照要点

| 量 | 实测 | 线 | 判定 |
| --- | --- | --- | --- |
| schema | `companion-v2.storage.v47` | — | 与使用者给的口径一致 |
| journal_mode | `wal` | — | 与使用者给的口径一致 |
| 主库大小 | 2338816 B（2.23 MiB） | 只报数 | · |
| WAL 常驻大小 | 729272 B（712.2 KiB） | 硬线 > 32 MiB | ✓ |
| WAL／主库比值 | 31.2 % | **提示线** > 25 % | `! 提示`（不影响退出码） |
| `*_history` 合计 | 19 行（3 张表） | 硬线 > 5000 行 | ✓ |
| 单域历史最大 | 15 行（`role_state_history`） | 硬线 > 1000 行 | ✓ |
| `document_json` 最大 | 554 B（3 行） | 硬线 > 64 KiB | ✓ |
| `document_json` 平均 | 268.0 B | 硬线 > 4 KiB | ✓ |
| 表 / 索引 | 125 / 74（比值 0.59） | 只报数 | · |
| `memory-search.sqlite3` | 184320 B（180.0 KiB） | 只报数 | 可整库重建 |
| `semantic-catalog.sqlite3` | 131072 B（128.0 KiB） | 只报数 | **不可丢弃**（见 §4） |

逐域历史明细（同一 profile，同一时刻）：`role_state_history` 15、`conversation_sent_history` 4、
`calendar_history` 0。`memory_views` 3 行。

**本次结论：没有任何硬线越线，退出码 0。** 唯一的越线是 WAL／主库比值（31.2% > 25%），而它按 §2
的口径是**提示项**：比值对库的大小极敏感，主库才 2.23 MiB 时 712 KiB 的 WAL 就是 31.2%，可这么大的
WAL 对磁盘与备份几乎没有影响；同一条线放到大库上又永远不会触发。所以它照常打印、只作观察，
**不参与退出码**，也不需要因此动手。真要到 32 MiB 的绝对线，`WAL 常驻大小` 那一行才会判红。

## 2. 阈值与理由（逐条）

线全部写在 `tools/audit_storage_baseline.py` 的具名常量里，一处定义、一处判定，不散落在函数中间。
**改动阈值必须同时改常量上的注释**，否则下一个人只能看到一个没有依据的数字。

| # | 检查项 | 线（常量） | mode | 为什么定在这里 |
| --- | --- | --- | --- | --- |
| 1 | 主库大小 | 无（只报数） | `info` | 绝对体积本身说明不了问题：2 MiB 的库配上 700 KiB 的 WAL 才值得看。它是第 2 项的分母。**使用者没有给这条线，工具就不替使用者发明**——一条没有依据的上限会让人以为这里已经有守卫。 |
| 2 | WAL 常驻大小 | `WAL_ABSOLUTE_LIMIT_BYTES` = 32 MiB | `hard` | WAL 常驻不回收会把备份从「一个文件」变成「三个文件必须一起拿」（少拿 `-wal` 会静默丢掉最近写入），还会让只读分析工具读到旧快照。32 MiB 是"单个 `-wal` 已经大到不该再靠下次启动兜底"的量级。**这是 WAL 唯一的硬线。** |
| 3 | WAL／主库比值 | `WAL_RATIO_NOTICE_LIMIT` = 25% | `advisory` | **提示项，不判红**（见下面「为什么降级」）。25% 是"WAL 已经开始与主库同量级"的位置，值得看一眼，但不值得按它动 schema。 |
| 4 | `*_history` 合计行数 | `HISTORY_TOTAL_LIMIT` = 5000 | `hard` | 历史表只增不减（删了就没有第二次机会），依据是"这张表还有没有人会去读"：几百行是查证，几万行只是一份没人读的日志。 |
| 5 | 单域历史最大行数 | `HISTORY_DOMAIN_LIMIT` = 1000 | `hard` | 比合计线更早生效：涨的通常只有一个域。等合计线越线时，那个域已经堆了很久。 |
| 6 | `document_json` 最大长度 | `DOCUMENT_MAX_LIMIT_BYTES` = 64 KiB | `hard` | `memory_views` 是"为读优化的物化视图"，本该是短文档。到 64 KiB 这条记录已经不适合逐行读；一旦有人把整份会话塞进来，读放大、写放大与 WAL 增长会一起变坏，而且从外面看不出来。 |
| 7 | `document_json` 平均长度 | `DOCUMENT_AVERAGE_LIMIT_BYTES` = 4 KiB | `hard` | 4 KiB = 一整页 SQLite page。平均值到这里，视图表就不再是索引，而是把正文抄了一份。 |
| 8 | 表 / 索引数量与比值 | 无（只报数） | `info` | 索引数量本身不是缺陷，但它决定写入放大。记下来是为了给"要不要再加索引"提供对照（见 §4）。 |
| 9 | 各表行数 Top 10 | 无（只报数） | `info` | 观察增长用：哪个域在长、比上次快多少，先要有个可比的数字。 |

### 为什么 WAL 比值从"越线"降级成"提示"

这是使用者口径的直接推论，不是为了让输出好看：

- 它是一条**常驻**阈值，而**比值对库的大小极敏感**。实测就是例子：主库 2.23 MiB、`-wal` 712 KiB
  → 31.2%，越线；可这个绝对量对磁盘和备份几乎没有影响。
- 反过来，**大库永远不会触发同一条线**：库长到几百 MiB 时，同样的 25% 要几百 MiB 的 WAL 才够。
- 一条"小库必然误报、大库永不触发"的线，判红的净效果是让人开始无视告警——那时真正的越线也没人看。
- 所以：**比值照常打印**（含"小库比值天然偏高，仅作观察"的说明），越线以 `! 提示` 出现、
  只进 `notices`、**退出码不变**；WAL 的硬线只保留绝对大小 32 MiB。

**再强调一次：以上都是观察线，不是当前必须修的问题。** 本次没有任何硬线越线（退出码 0），唯一的
提示项也已经写明处置路径（先确认、必要时停机窗口 checkpoint），不涉及改 schema、不加索引、不加清理任务。

## 3. 权威回归基线

全量 unittest（由使用者用 AstrBot 自带 Python 跑出）：

```
3478 项 / 18 失败 / 104 错误 / 1 跳过
```

**这一组是唯一可采信的全量口径。**

早先那次"3984 项 / 227 非通过"的记录**不可采信**，三个理由各自都足以作废它：

1. 它跑在**沙箱受限期**；
2. 它用了**替换 `mkdtemp` 的临时引导脚本**（等于换掉了测试的运行环境）；
3. 它运行时**工作树正在被并行改动**（测得的是移动靶）。

把口径记在这里，是为了让下一个人**不要**拿 3984 那一组来对比、也不要拿它当"必须修回去"的目标。
**本节不是要你去修回归**；当前的 18 失败 / 104 错误是另一件事，需要单独一轮来定性，本记录不做判断。

## 4. 逐条核对结论（使用者已核实）

以下每条都是使用者已经核实过的结论，**不是待办**：

- **WAL 治理：暂不加。** 不做自动维护、不做自动截断。WAL 的判红线只保留绝对大小 32 MiB，
  比值降级为提示项（§2 的推论）。
- **索引：暂不加。** 理由已经查过：
  - 群记忆与经历目录的查询**命中既有复合索引**，不需要新索引；
  - 人物目录会扫描并排序，按 owner 列 active 记忆时用的是**临时 B-tree 排序**——这本来是新索引的候选，
    但 `memory_views` 目前**只有 3 行**，为 3 行加一条索引再加上一次 schema 迁移与随之而来的写放大，不值得。
- **备份：无需改 `VACUUM INTO`。** 现有备份已经使用 **SQLite 在线 backup API**，它天然处理 `-wal`，
  不需要换成 `VACUUM INTO`。
- **并发口径：保持 `synchronous=FULL` + `busy_timeout=5000`，并且不宣称支持多写者。**
  这是当前的能力声明边界，不因为"看起来更宽松"而改。
- **历史与大字段：暂无拆分依据。** 实测合计 19 行、`document_json` 平均 268 B／最大 554 B，
  这个量级不支持"把历史或大字段拆出去"的结论；等观察线越线再说。
- **`semantic-catalog.sqlite3` 不能当可丢弃派生物。** 它**含目录原始数据**，只有向量部分可以再生成。
  因此将来若真的要做"重建"命令，**范围只能限向量部分**，不能整库删掉重建。
  （对照：`memory-search.sqlite3` 整库可重建。）

## 5. 复现

```bash
# 文本输出（硬线越线时退出码非 0；提示项不影响退出码）
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_storage_baseline.py

# 机器可读输出
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_storage_baseline.py --json

# 定向测试（13 项）
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_storage_audit -v

# 同目录那个既有工具（独立、与本工具无关）也能跑：
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 tools/audit_storage.py --help
```

基线工具只用标准库，不导入 `companion_v2` 或 `astrbot_host`，**AstrBot 没在跑也能审计**。
`--data-root` 可以给插件数据目录（其下是 `profiles/<名>/runtime`），也可以直接给含三库的 `runtime` 目录；
不给则按 AstrBot 的目录约定自动发现，发现不到就打印一句说明并以 0 退出（**不刷栈、不当失败**）。
库不存在或为空按「未初始化」处理，同样**不算失败**。

**只读的准确边界**（实测，不是推测）：

- 主库与 `-wal`：审计前后**字节、mtime、大小都不变**——不写入、不 checkpoint、不截断、不 VACUUM；
- `-shm`：字节**会**变，大小不变。这是 SQLite 的 wal-index 共享内存，**任何**一次只读打开
  （哪怕只跑一句 `SELECT COUNT(*)`）都会更新里面的读标记，不是本工具多做的事。
  `tests/test_storage_audit.py` 里有一条对照用例专门把这条边界钉住，所以"只读"的可证伪说法是
  "主库与 `-wal` 不变"，而不是"三个文件一个字节都不变"。

## 6. 溯源与待确认（没把握的地方）

### 6.1 表/索引数量的两种口径：**已定性，以活库实测为准**

使用者给的「91 张表 / 43 个索引」与我实测的「125 张表 / 74 个索引」**不是同一件事**，两者都对：

- **91 / 43** = `companion_v2/storage/schema.py` **源文件里** `CREATE TABLE` / `CREATE INDEX` 的条数
  （本次逐条复核：该文件里确实**正好**是 91 个 `CREATE TABLE`、43 个 `CREATE INDEX`）。
- **125 / 74** = **活库实测**的对象数。

差在哪里（本次核到的证据）：

- 主库的 DDL 不止 `schema.py` 一个文件：`companion_v2/storage/` 下还有 16 个 `*_schema.py`
  （`memory_schema.py` 11 张、`state_schema.py` 5 张、`reading_archive_schema.py` 5 张、
  `reference_asset_schema.py` 3 张……）。
- 有一部分表是**运行时/模板生成**的，源码里没有字面量 `CREATE TABLE`：例如 `state_schema.py`
  用 `CREATE TABLE {name}` 模板建表，所以 `role_state_records/receipts/history` 三张表在活库里存在，
  却在任何源文件里都搜不到对应的字面 DDL；`calendar_records` 等同理。
- 还有**迁移留下的改名残留**：`model_accounts_saved`、`model_calls_saved`、`model_call_failures_v36`
  这三个名字出现在源码 DDL 里、活库里却没有（典型的新表建好、旧表改名存档）。
- `companion_v2/storage/semantic.py` 的 14 张表属于 **`semantic-catalog.sqlite3`**（另一个库），
  不进主库计数；`companion_v2/memory/recall_index.py` 与 `memory/search.py` 的 DDL 同理属于
  `memory-search.sqlite3`。
- 当天工作树还在被并行改动（落新域的表）。

**结论：以活库实测为准（本次 125 表 / 74 索引）；源文件计数只当"schema 文件规模"参考**，
它既不含模板生成的表，也会把迁移残留算进去，不适合当对象数用。

### 6.2 WAL 数字是活的

使用者记录过 1.22 MB 与 2.02 MB，本次实测主库 2.23 MiB / WAL 712.2 KiB / 比值 31.2%。
WAL 随写入活动涨落，单次测量只能当快照，不能当趋势；要谈趋势得连续采几次。

### 6.3 `tools/audit_storage.py` 与 `tools/audit_storage_baseline.py` 是两个工具（并存，最终状态）

**事实经过**：会话开始时 `tools/audit_storage.py` 上已经有一个**未跟踪**的、用途不同的英文工具
（303 行；显式传 `--database` / `--profiles-root`，在临时目录里对快照做 `StorageRuntime.open()`、
量启动耗时与锁形态；不自动发现数据根、不判 WAL 比值）。第一轮交付时按"新增该文件"的要求把它
**覆盖**了；使用者确认**覆盖不是本意**，随即收口：

- 原文已**还原**回 `tools/audit_storage.py`（13079 字节，sha256 `5398cf12aff77462a8a3ab183d82079e0193c5d9fe38e395b6398337f0f19f5a`，
  与备份逐字节一致）；
- 同一份原文又存了一份**仓库内持久副本**：`tools/_archive/audit_storage_preexisting_20261003.py.bak`
  （同 sha256）。放在仓库内是因为原来那份备份在系统临时目录里，随时可能被清掉——它是**别人的未跟踪工作**，
  不能只留一份在 `%TEMP%`。目录名 `_archive` 表明这里只存放档件，不参与运行、不被导入，
  与 `tools/` 下的可执行脚本区分开；
- 本次交付的基线审计工具改用 **`tools/audit_storage_baseline.py`**，与前者并存。

两个工具**互不依赖、不要互相改名**：`audit_storage.py` 会打开 `StorageRuntime` 并迁移临时快照，
本文件则是纯只读的阈值审计。若要判断"该跑哪个"，看问题：量启动耗时/锁形态 → `audit_storage.py`；
量增长与观察线 → `audit_storage_baseline.py`。

### 6.4 工具刻意不打时间戳

这样 `--json` 的输出可以逐次直接 diff（只有实测值会变）。基线的时间戳由这份记录承担（2026-10-03 00:31）。

### 6.5 只审计一个 profile

默认规则是"主库最近被写的那个"，其余 6 个 profile 会被列在输出里但**不审计**。
如果哪天要在 CI 里守住全部 profile，需要另外决定"多 profile 怎么汇总成一次判定"——现在没做。

### 6.6 本次的文件影响面

新增／改动仅限本次交付涉及的路径：

| 路径 | 说明 |
| --- | --- |
| `tools/audit_storage_baseline.py` | 新增（基线审计工具，598 行） |
| `tests/test_storage_audit.py` | 新增（定向测试，13 项） |
| `docs/STORAGE_BASELINE_20261002.md` | 新增（本文件） |
| `tools/_archive/audit_storage_preexisting_20261003.py.bak` | 新增（既有工具的持久副本，13079 字节） |
| `tools/audit_storage.py` | **还原**为会话开始时的内容（不是新增；哈希与原文一致） |

未改动 `companion_v2/`、`astrbot_host/`、`pages/`。运行副产物只有 `__pycache__/*.pyc`
（仓库本来就有这些目录，且被 `.gitignore` 覆盖）。
