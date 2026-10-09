# 04 · 事实与经历（`memories` 整页 + `manage/memory`）

代码位置：`manage/memory` 页签 `renderMemoryPage`（`pages/陪伴小屋/app.js:1196-1198`）；`memories` 整页路由复用同一 `renderMemories()`（`app.js:613` 的 `fullPage` 分支，`#main` 承载）；挂载点 `#memoryWorkspace`（`app.js:893` 产出，`app.js:466,618` 挂 `CompanionMemoryPage`）。核心模块：`memory-page.js`（769 行，记忆治理工作台）、`memory-settings-section.js`（决策 B1 的策略编辑器，见 [07-decision.md](07-decision.md)）。

## 一、页面功能

事实、经历、原文与来源、修订与遗忘的**治理工作台**：整理进度监督、事实纠错、来源复核、冷归档、跨安装迁移、按范围清理。策略类设置不在此页（在决策 B1）。

## 二、展示部分（六个视图，`memory-page.js:280` 页签定义）

| 视图 | 内容 | 端点（均相对 `{memory_api}`） | 证据 |
| --- | --- | --- | --- |
| 整理与修复 | 待处理整理批次列表（每 8 秒轮询，仅 facts/reflections 两视图）、批次详情（状态机标签、指标/回执/待处理原因）、排队继续 | `GET /reflections?limit=20&after_id`、`GET /reflections?batch_id`、`POST /reflections/queue` | `memory-page.js:320-341,612,157-163` |
| 事实治理 | 事实卡片与详情（属性/来源/修订）、版本历史、变更操作 | `GET /`（列表）、`POST /detail`（atom_id+revision）、`GET /revisions?limit=64`、`POST /command`（action=pin/unpin/retract/forget/correct） | `:321,360,373,425-452,658-697` |
| 来源与经历 | 按类型检索 facts/sources/experiences/all，游标渐进；来源原文有界片段（≤4000 字） | `POST /query`、`POST /source` | `:391-424` |
| 冷归档 | 长期闲置事实归档预览（idle_days 30–3650）→ 确认（可逆）→ 移回工作集 | `GET /archive/preview`、`POST /archive`（expected_archive_token）、`POST /archive/restore`（atom_ids ≤512） | `:455-516` |
| 迁移 | 便携包导出（复制/下载，include_archived）→ 导入先校验预览再落地 | `GET /export`、`POST /import/preview`、`POST /import`（expected_import_token） | `:518-582` |
| 范围清理 | 按范围清理预览 → 确认（逻辑遗忘） | `GET /clear/preview`（revision_token）、`POST /clear` | `:380-390,583-601` |

目录：`GET page/targets`（`:297`）；pending/mutation 存 localStorage 供跨刷新核对（`:95-135`）。

## 三、配置部分

**本页不持配置组。** 相关配置都在决策 B1（R1：同一组只一处可写）：

- `memory` 34 项（`memory/configuration.py` 30 项 + `memory/episode_settings.py:30` 4 项）：决策 B1 的 `#memorySettingsHost`，经 `GET /memory/settings` + `POST /memory/settings/command` 读写（`memory-settings-section.js:120-121`），内部分四段 core「记忆与注入」/ reflection「定时整理」/ episode「经历整理」/ habit「习惯与推荐」（`:52-67`）。
- `person` 2 项：决策 B1 的 `configEditors('personConfigWorkspace',['person'])`（`app.js:1139`）。

本页与 B1 之间是**回流关系**：治理工作台里的纠错/钉选会改变 B1 所述"记忆"的 contents，而不是改配置。

## 四、边界与空态

- 群聊目标进入时整页说明「群聊记忆独立管理」（`memory-page.js:280`；群记忆有独立 API 族 `group_memory_api.py`）。
- 各面板空态文案：「尚未生成归档预览/尚未校验记忆包/尚未生成范围预览」（`:246,259,263`）；查询「索引正在准备…」（`:267`）。
- 桥等待 10 秒超时报 `bridge_unavailable`，不再伪装预览数据（`:699-755`）；错误码→文案表 `:7-48`。

## 五、后端情况

`astrbot_host/memory_api.py:26-44` 共 **19 条路由** → 服务映射：

| 路由族 | 服务 |
| --- | --- |
| 事实/修订/清理/详情/查询/来源 | `companion_v2/memory/management.py` `MemoryManagement`、`memory/query.py` `MemoryQuery`、`memory/codec.py`（`memory_api.py:10-13,125`） |
| 整理与修复 | `memory/reflection_management.py` `ReflectionManagement`（`:14,57`） |
| 冷归档 | `memory/archive.py` `MemoryArchive`（`:9,151`） |
| 设置 | 统一 memory 组 owner（经 `/settings` 路由） |

多目标模式：per-target `/host/targets/{id}/roles/<digest>/memory`（`multi_api.py:83-100`）。

## 六、相关设计稿与复核

- 策略编辑 → [07-decision.md](07-decision.md) B1；群记忆 → `astrbot_host/group_memory_api.py`（本目录暂无独立页稿）。
- 复核视图清单：`grep -n "id:'reflections'\|id:'facts'\|id:'query'\|id:'archive'\|id:'migrate'\|id:'clear'" pages/陪伴小屋/memory-page.js`。
