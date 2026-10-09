# 19 · 资料与维护（`manage/data`）

代码位置：`renderData`（`pages/陪伴小屋/app.js:1326-1345`）；备份工作区 `#backupWorkspace`（`app.js:1339`）挂 `CompanionBackupPage`（`backup-page.js`，438 行）。入口注释（`app.js:1310-1324`）：备份块曾是 boundaryCard，但 `backup_api.py` 有六条真实路由与两阶段状态机，属「能接却没接」，已接上。

## 一、页面功能

资料与维护页提供存储位置与清理策略、各处记录的**入口汇集**、**备份与还原**（安装级合同）以及 **V1 数据迁移**四个子页。

## 二、展示部分

| 分区 | 内容 | 证据 |
| --- | --- | --- |
| 记忆与生活 | 三行入口卡：记忆整理与遗忘 → memories 页；日记与生活 → life 视图；宿主运行状态 → host 页 | `app.js:1338` |
| 备份与还原 · 快照列表 | 创建时间倒序、备注、byte_size、schema_version、content_hash 前 12 位 | `backup-page.js:239-258` |
| 备份与还原 · 还原预览 | 当前库三表行数：memory_atoms 记忆条目 / operations 操作记录 / configuration_values 配置项 + 确认摘要（哈希取自后端 manifest.content_hash，页面不自算） | `:262-289,81-85,186-188` |
| 备份与还原 · 等待重启 | pending 块（含安全副本 id） | `:291-301` |
| V1 数据迁移 | 独立的配置与运行数据工作区，不读取首次设置状态；迁移目标与人格由用户显式选择 | `app.js` 的 `renderDataOriginal` / `mountPanelWorkspaces`；`setup-guide.js` 的 `mountMigration` |

## 三、配置部分

**无配置组**；可写部分是备份命令（两阶段状态机）：

| 操作 | 端点 | 要点 | 证据 |
| --- | --- | --- | --- |
| 创建快照 | `POST backup/create {note≤200}` | 后端要求键集恰为 {note} | `backup-page.js:168-184` |
| 校验快照 | `GET backup/inspect?snapshot_id` | 校验而不恢复 | `backup_api.py:31` |
| 还原预览 | `GET backup/restore/preview?snapshot_id` | 展示将被替换的内容 | `:32`；`backup-page.js:189-212` |
| 暂存还原 | `POST backup/restore {snapshot_id, confirmed_hash}` | **成功话术是「已暂存、等重启」而非「已还原」**；暂存前自动留安全副本 | `backup-page.js:216-237`；`app.js:1336` 文案 |
| 待恢复查询 | `GET backup/pending` | pending 失败不拖垮列表 | `backup-page.js:150-154` |

二次确认：`data-backup-stage` 只切确认态，再点 `data-backup-confirm` 才发请求（`:421-426`）。

## 四、边界与空态

- **多目标模式下后端不注册 BackupWebAPI**：页面按 `product.targetsMode()` 分支，只渲染说明「切换到单目标宿主配置后，创建与还原入口会出现在这里」，不给必然失败的按钮（`app.js:1329-1341`；代码注释明说这是真实约束）。
- 宿主目录未读到时给「重新读取 + 去宿主管理」而非预览数据管理（`app.js:1330-1334`）。
- 无快照空态文案；读取失败给带「重新读取」的错误态，不渲染假空表（`backup-page.js:309-320`）；错误码→人话表 `:43-71`。
- 备份以整个安装为单位，不针对单个角色或关系（V2 独立数据根，不与 V1 共用）。

## 五、后端情况

- 路由（`astrbot_host/backup_api.py:29-34`）：`GET /backup`、`POST /backup/create`、`GET /backup/inspect`、`GET /backup/restore/preview`、`POST /backup/restore`、`GET /backup/pending`。
- 服务：`companion_v2/storage/backup.py` `InstallationBackup`、`apply_pending`（`backup_api.py:13-15`）；重启后由宿主应用 pending 恢复。
- V1 迁移入口位于本页「V1 数据迁移」子页（`#manage/data/migration`）；`app.js` 将该路由挂到 `#legacyMigrationWorkspace`，并以迁移专用模式调用 `CompanionSetup.mountMigration`。发现、试算、配置应用以及运行数据试算/导入均由 `astrbot_host/legacy_api.py` 提供，用户逐步确认后才会写入 V2。

## 六、相关设计稿与复核

- 治理与维护页是本页 + 宿主管理的合集视图 → [15-maintenance.md](15-maintenance.md)。
- 复核：`grep -n "restore/preview\|apply_pending" astrbot_host/backup_api.py companion_v2/storage/backup.py | head`。
