# E5 整库备份与恢复切片记录（2026-09-26）

## 为什么做这一片

V1/V2 配置校准报告的第四节把"整库备份与恢复"列为第 1 项待办，理由是它是唯一一个**功能已完整但交付有风险**的缺口：其余缺口都只是能力不全，而这一项一旦缺，独立数据根上的数据损坏就没有恢复路径。

当时的证据是：`companion_v2/` 全树对 `backup|restore` 的匹配没有一处是数据库备份或恢复（`restore()` 全是 dataclass 反序列化或身份校验），`companion_v2/diagnostics/service.py` 把 `backup_verification` 直接写死为 `"not_run"`。现有可用的只有 `memory/archive.py` 的单关系记忆冷归档，以及 `tools/build_v2_release.py` 的发布包构建——两者都与运行时数据备份无关。

## 两个关键设计决定

### 一、快照用 SQLite 在线备份 API，不用拷文件，也不用 `VACUUM INTO`

`StorageRuntime._open_connection` 设了 `PRAGMA journal_mode = WAL` 与 `synchronous = FULL`。在 WAL 模式下，**已提交的事务帧可能仍留在 `-wal` 边车文件里，尚未 checkpoint 回主库**。因此：

- 只拷 `companion-v2.sqlite3` 会静默丢掉最近的提交。这与 C11 那个"裸插能写不能读"属于同一类错误——写的时候不报错，错在别处才暴露。
- `VACUUM INTO` 本是理想选择（在一个读事务里产出压缩单文件），但**它是写操作**。运行时的 `read_only_snapshot()` 会设 `PRAGMA query_only = ON`，VACUUM 会被直接拒绝。

所以最终用 `sqlite3.Connection.backup()`：它在运行时自己的读快照里取流，写到一个独立的目标连接，产出无 `-wal`/`-shm` 旁挂的自包含单文件。该 API 就是为"活动库在线备份"设计的。

还有一个细节：`backup()` 的目标连接**不能**复用运行时的连接，因为那会污染运行时的快照；也不能让 `fastapi`/`aiosqlite` 之类的异步封装介入，保持同步即可（快照本身是本地磁盘 I/O）。

### 二、恢复是两段式，绝不热重建连接

`StorageRuntime` 的连接在插件加载时打开一次，`_ensure_assembly` 里建好之后，全树每个 repository、service、task 都借这一个连接。**运行期关掉它换文件，会让所有已持有引用的对象指向一个关闭的连接。**

因此恢复分两段：

1. **挂起**（API 调用）：验证候选快照 → 自动留一份"替换前安全副本" → 写 `restore-pending.json` → 返回 `effect: "restart_required"`。此时数据根**完全没变**。
2. **应用**（宿主装配时）：`_ensure_assembly` 在 `StorageRuntime.open` **之前**调用 `apply_staged_restore(root / "runtime", installation_id=...)`。这是唯一没有活动连接的时刻。

第 2 步的应用顺序：只读打开候选快照验证安装标识 / schema 版本 / `quick_check` / 外键 → 复核哈希与挂起请求一致 → 把现有主库原子改名为 `companion-v2.sqlite3.replaced` → 删除属于旧库的 `-wal`/`-shm` → 原子改名候选快照为正式库 → 删除挂起文件。

改名在同一文件系统内是原子的，所以中途崩溃的结果是"旧库"或"新库"，不会是半个文件。旧库保留为 `.replaced`，配合自动安全副本，恢复失败不会不可逆。

### 三、`apply_staged_restore` 只能读文件，不能读运行时

这里犯过一次错并已修正。第一版写成接收 `controller`、从 `controller.runtime.read_one(...)` 取 schema 版本——但它在 `StorageRuntime.open` 之前被调用，那时 `controller.runtime` 还是 `None`。现在改为直接接收数据根路径，用新增的 `current_schema_version(data_root)` 以**只读 URI** 打开主库读 `runtime_metadata.schema_version`。这一点很重要：用读写模式打开会创建文件并对即将被替换的数据根跑迁移。

## 拒绝条件

- 快照声称属于另一个安装（`backup_snapshot_foreign`）
- 快照 schema 版本与当前数据根不同（`backup_snapshot_schema_mismatch`）
- `quick_check` 失败（`backup_snapshot_corrupt`）或外键断裂（`backup_snapshot_broken_references`）
- 确认哈希与实际字节不符（`backup_confirmation_mismatch`）
- 已有挂起请求（`backup_restore_pending`）
- 快照尺寸为 0 或超过 1 GiB（`backup_snapshot_size_invalid`）
- 挂起请求损坏（`backup_pending_unreadable` / `backup_pending_invalid`）——**返回文档而不抛异常**，避免一条坏请求把启动路径带崩

## 文件清单

| 文件 | 改动 |
|---|---|
| `companion_v2/storage/backup.py` | 新增。`InstallationBackup`（create / listing / inspect / preview_restore / restore / pending）、`apply_pending`、`current_schema_version`、`SnapshotManifest` |
| `astrbot_host/backup_api.py` | 新增。六条路由 + `apply_staged_restore` |
| `astrbot_host/controller.py` | `_ensure_assembly` 在 open 前应用挂起恢复；新增 `last_restore` 字段 |
| `astrbot_host/web_api.py` | 注册 `BackupWebAPI` |
| `astrbot_host/page_api.py` | 目录暴露 `backup_api`（安装级，不挂在角色下） |
| `companion_v2/diagnostics/service.py` | `backup_verification` 改为真实状态 + `snapshot_count` |
| `tests/test_storage_backup.py` | 新增。10 项 |

`diagnostics` 这一项单独说明：原先写死 `"not_run"` 会把"没有任何备份"和"有备份但没校验过"压成同一个值。现在 `_backups()` 统计完整快照数并校验最新一份，返回 `verified` / `failed` / `no_snapshot` / `unreadable`。

## 明确未做

- **小屋备份面板未接**。后端端点齐了（列表 / 创建 / 校验 / 预览 / 恢复 / 挂起查询），`page_api` 也已暴露路径，但前端还没做。
- **快照轮转 / 保留策略未做**。目前只写不删，会持续占盘。在磁盘上限、保留份数确定前不动，避免做出会删掉用户数据的策略。
- **无加密与异地副本**。快照是明文 SQLite 文件。
- **`synchronous = FULL` 下未测大库耗时**。1 GiB 上限是保守值，未实测。

## 验证状态

**全部改动未经运行验证。** 本会话沙箱工作区（`mcp__workspace__bash`）全程返回 "Workspace still starting"，编译、`tests/test_storage_backup.py`、迁移链路回归均未执行。所有结论来自源码阅读与静态核对。

待环境恢复后至少补跑：

```bash
python -m compileall -q companion_v2 astrbot_host
python -m unittest tests.test_storage_backup -v
python -m unittest tests.test_storage_runtime tests.test_storage_migrations -v
```

其中 `test_apply_pending_swaps_the_database_only_with_no_live_connection` 需要**真正的文件替换权限**——若在 Windows 上因文件句柄未释放而失败，那是环境问题而非逻辑问题，应在 Linux 数据根上复跑确认。

## 下一步

按校准报告第四节，第 1 项已完成。下一个真实缺口是第 2 项**群聊唤醒与插话**（B4 约 28 项），或第 4 项**发送前复核与智能沉默**（E3 约 11 项）——后者更贴近"陪伴角色乱说话"的实际风险。
