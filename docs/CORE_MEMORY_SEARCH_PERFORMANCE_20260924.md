# V2 记忆索引性能与锁竞争

本切片接续[启动后自动接续](CORE_MEMORY_STARTUP_RECOVERY_20260924.md)，先处理默认事实召回路径中已经复现的性能问题。代码已经落入 V2 主树；不修改正式记忆表、来源和权限合同，不增加主库 schema 迁移。

## 问题与修正

1. **冷建索引随着库增大反复扫描。** `FactIndex._put()` 原先不论记录是否存在，都执行 `DELETE FROM fact_lexical WHERE owner = ? AND id = ?`。FTS5 的 owner / id 为 UNINDEXED 字段，新增事实也会扫描已有语料，累计开销随库大小快速增长。现在先复用已有的事实投影主键查询：确实有旧投影时才删除旧词项，新项直接插入。更正和撤回仍删除原项，索引检查点与词项继续在同一事务内提交。
2. **索引已同步，查询仍申请写锁。** 现在先在一致读事务内核对 owner 原子变更锚点、同步位置、bootstrap 状态和语料 epoch。完全同步时返回只读快照；只有首次构建或存在增量才争用写锁。取得写锁后重新读取持久检查点，避免使用争锁前的旧状态。外层回滚后序号复用、忘记、其他分区 BM25 变化与结果游标失效仍由原见证令牌和 epoch 校验。
3. **缓存锁等待阻塞宿主。** 可重建索引的 SQLite 连接从最长等待 10 秒改为不等待。已同步数据可在另一连接持有 RESERVED 写锁时正常查询；需要更新且锁不可用、或者提交被读锁阻止时返回 `memory_index_busy`。不返回旧版本或空结果冒充成功，也不在事件循环内自动重试。
4. **普通初始化把忙或 I/O 错误当作损坏。** 只对 SQLite 明确报告 `SQLITE_CORRUPT` / `SQLITE_NOTADB` 的文件保留损坏副本并重建。忙、只读、磁盘或 I/O 错误不改名健康文件。初始化遇到忙时延后到实际查询再试，不因可选索引而阻止宿主对象装配。
5. **每次构造查询服务都完整检查缓存。** 已初始化的缓存通过 `PRAGMA user_version` 标记识别，正常重开不执行全库 quick_check 或建表写事务。旧布局首次初始化与标记原子提交，保留已有分区和向量。该标记只属于可丢弃的搜索缓存。未被实际读取的页损坏不再于每次构造时全面探测；查询发现不可读索引仍报告 unavailable，不绕过原件核验。
6. **模型可能把检索失败当作没有记忆。** 保留原有置顶记忆与当前消息来源，并追加覆盖说明：“本次记忆检索暂不可用，未完成往事查找；只依据当前可见材料回答，不把未返回当作没有或已经忘记。”公共 `memory.query.v1` 将 busy 分类为 `unavailable`，同一请求可在锁释放后再查。

不等待仅用于派生缓存。正式主库仍使用原事务与锁配置；缓存清理失败不会撤销已提交的遗忘回执，后续重放可以完成清理。索引只缩小候选集，每个返回项仍由原记忆 writer 复核当前身份、来源、事实版本和时间。

## 一万条合成事实实测

同一台机器、同一份由公开 writer 写入的临时 V2 合成库，原版与新版分别从只读种子复制一份正式记录，搜索缓存均从空库开始。原版代码在独立评测目录保留，不回滚共享工作树。每页构建上限仍为 256 条，共 40 页；测试没有通过缩小输入或降低记忆量换取改善。

| 指标 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 冷建索引全部 40 页 | 10,461.52 ms | 688.68 ms |
| 单批最慢耗时 | 982.60 ms | 22.49 ms |
| 构建期间同循环等待任务的最大延迟 | 982.64 ms | 22.53 ms |
| 索引就绪后的查询中位数，5 次 | 9.54 ms | 5.81 ms |
| 重建查询服务对象中位数，3 次 | 38.33 ms | 0.45 ms |
| 另一连接持有 350 ms 写锁时的就绪查询 | 460.80 ms | 5.69 ms |

新版在 5 次查询中每次仅读取 1 条匹配事实，没有批量读取全部 memory_atoms 或 memory_changes。查询前已经完成全部一万条事实的索引构建，未在排名前截取最近 N 条候选。

这些数字是本机模拟数据的测量，不是所有查询或生产设备的延迟保证。冷建数据为短文本事实；密集匹配、长文本、超大库、真实磁盘争用仍可能更慢。正式记录的种子写入和副本初始化耗时单独记录，不计入索引指标；不能把这组数据解释为一万条真实记忆的完整写入耗时。

复测工具：`tools/benchmark_memory_recall.py`。从项目根使用 AstrBot 自带 Python 执行：

```powershell
& 'C:\Users\99505\.astrbot\backend\python\python.exe' -X utf8 -m tools.benchmark_memory_recall --facts 10000 --output 'D:\codex\workspaces\memory-benchmark.json'
```

工具只创建临时测试根并使用合成输入；`--seed-from` 用于本工具已生成的合成数据库快照，输入以只读方式打开，所有查询在新副本中执行。测试夹具和搜索实现没有 SDK、模型或平台 I/O。

## 定向验证

最终同批 **128 项全部通过，其中新增 11 项**。新增 `test_memory_search_performance` 10 项，公共查询协议增加 1 项。首批 6 个故障用例均先在原版失败，再验证修正；后续补实际双连接读写锁、投影提交回滚、遗忘清理回放和撤回检查。

覆盖范围：`test_memory_search_performance`、`test_memory_incremental`、`test_memory_query`、`test_memory_wire`、`test_memory_boundaries`、`test_memory_polish`、`test_memory_writer`、`test_memory_experiences`、`test_memory_conversation`、`test_memory_provider_host`、`test_memory_startup_recovery`、`test_astrbot_staging_host`、`test_isolation`。包含旧坏索引重建、外层事务回滚后的序号复用、跨分区游标、更正/撤回/遗忘、置顶上下文，以及 SDK 加载、停机和路由注销。此前 69 项回归与后续新增锁测试不重复累计。

测试使用 AstrBot 自带 Python。SDK 进程设置 `PYTHONPATH=C:/Users/99505/.astrbot/backend/app`，SDK 导入数据根由夹具指向临时目录。没有在线重载、真实模型调用、QQ 发消息、鼠标操作或 V1 用户数据访问。

证据目录：`D:/codex/workspaces/v2-memory-performance-xjbzl3kc/`。包括 `reproduction.log`、`focused-regression.log`、`contention-validation.log`、`regression-final.log`、可比基线 `baseline-comparable.json`、最终测量 `optimized-final.json`、合成种子、局部修改前备份和文件校验清单。最初基线脚本出现过临时库清理错误，已修正其测试基类并从相同种子复验；对照副本首次导入碰到其他窗口正在拆分的角色状态模块，刷新其已完成依赖后复验通过，没有修改该窗口的功能代码。

## 后续范围

后续进展：同日的[来源、经历与混合增量召回](CORE_MEMORY_MIXED_RECALL_20260924.md)已补齐公共 sources / experiences / all / vector 查询，下列清单保留本切片交付时状态；后台反思准备和主库锁等待仍未完成优化。

- `sources / experiences / all / vector` 查询仍调用完整候选读取与同步；反思准备也仍读取全部可见来源。这部分需要独立的分批投影和增量变更合同，不能以截取最近记录替代完整搜索。
- 已有词项的批量更正、撤回和 owner 清理仍可能扫描 FTS 的 UNINDEXED 字段；本批先去掉每个新增项的无意义全量删除。
- 正式主库的写锁等待、同步存储初始化、来源治理与大规模批量写入仍需独立验收；没有声称整个数据库路径已经异步化。
