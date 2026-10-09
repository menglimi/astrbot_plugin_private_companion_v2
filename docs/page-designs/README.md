# 陪伴小屋 · 逐页设计稿（代码实查版）

日期：2026-09-29。本目录共 1 份总览 + 19 份逐页设计稿。**全部内容以当前工作区代码实查为准**（每条都带 `文件:行号`），不沿用 docs/ 下既有文档的结论；两份既有设计文档 `PAGE_DISPLAY_AND_CONFIG_DESIGN_20260928.md`（职责归属）与 `..._20260929.md`（呈现层）仍是设计目标口径，凡与代码现状不一致处，本文以代码为准并显式标注。

> **设计变更记录（2026-09-29）**：①「日程」页更名为「状态页」（`life/state`）——**已实施**：`lifeTabs`/`renderViewPanel`/`shell.js` VIEWS 更名、旧深链接别名；侧栏落位为**能力配置组第一项**（`shell.js` RAIL_GROUPS，按设计稿批注；同时专题配置上移且去组标题）。②首页改版**已实施**：左栏顶部穿搭图卡（画面能力接入后替换插件信息，**比例 1:1**）、镜头复位+布置收进场景右上角、家具速览条下移、点选家具直接承载工作区、右栏只留状态/生活安排两卡（见 [01-cottage-home.md](01-cottage-home.md)）。③**内容暂清（已实施）**：除首页与模型页外，所有页面正文清空为占位说明——原渲染函数以 `*Original` 整体保留在 `app.js`，页签/挂载链/页面模块不动；状态与日记两个 life 视图正文同清（首页的家具工作区保留，内容仍可达）；整目录备份于 `data/companion_v2_page_backups/20260929-before-page-clear/`（插件扫描目录之外，90 个文件校验一致）。④`role.state` 迁状态页、`role.life` 迁日记页——**未实施**，实施清单见 [02-state.md](02-state.md) 第六节。⑤并发新增的「人物设定工坊」（`manage/persona`）页签为在途工作，未纳入清空。

## 一、页面清单

唯一公开拓展页为「陪伴小屋」（`pages/陪伴小屋/`），其余四个目录的 `workspace.html` 由构建脚本嵌入。路由分三层：`life`（生活，3 个子视图）、`memories`（整页工作台）、`manage/<tab>`（16 个页签）。

| # | 页面 | 路由 / 页签 | 设计稿 |
| --- | --- | --- | --- |
| 1 | 小屋总览 | `life/home` | [01-cottage-home.md](01-cottage-home.md) |
| 2 | 状态 | `life` 视图 `state`（设计；现状 id 为 `schedule`） | [02-state.md](02-state.md) |
| 3 | 日记 | `life` 视图 `diary` | [03-diary.md](03-diary.md) |
| 4 | 事实与经历 | `memories` 整页 + `manage/memory` | [04-memories.md](04-memories.md) |
| 5 | 感知 | `manage/perception` | [06-perception.md](06-perception.md) |
| 6 | 决策 | `manage/decision` | [07-decision.md](07-decision.md) |
| 7 | 行动 | `manage/action` | [08-action.md](08-action.md) |
| 8 | 产出 | `manage/output` | [09-output.md](09-output.md) |
| 9 | 表达 | `manage/expression` | [10-expression.md](10-expression.md) |
| 10 | 自我 | `manage/governance` | [11-governance.md](11-governance.md) |
| 11 | 关系与权限 | `manage/identity` | [05-identity-relationships.md](05-identity-relationships.md) |
| 12 | 主动与联系 | `manage/contact` | [12-contact.md](12-contact.md) |
| 13 | 学习与反思 | `manage/learning` | [13-learning.md](13-learning.md) |
| 14 | 模型与连接 | `manage/models` | [14-models.md](14-models.md) |
| 15 | 治理与维护 | `manage/maintenance` | [15-maintenance.md](15-maintenance.md) |
| 16 | 开始使用 | `manage/setup` | [16-setup.md](16-setup.md) |
| 17 | 外观与设置 | `manage/appearance` | [17-appearance.md](17-appearance.md) |
| 18 | 宿主管理 | `manage/host` | [18-host.md](18-host.md) |
| 19 | 资料与维护 | `manage/data` | [19-data.md](19-data.md) |

导航分组见 `pages/陪伴小屋/app.js:50-59`（`navGroups`：首页 1 + 能力配置 6 + 专题配置 6 + 设置 4 = 17 项，渲染进「全部功能」对话框 `#navigationList`，`index.html:193`）；页签渲染分发表见 `app.js:1293`（`renderManage`）。常驻左侧栏是 `#shellNav`（`index.html:149`），内容来自 `shell.js` 的 `RAIL_GROUPS`（能力配置/专题配置/设置，`shell.js:127-150`）——设计变更后其头部新增「生活」组（小屋/状态/日记）。

## 二、嵌入工作区机制（四个 workspace 的来源与沙箱）

- 构建源：`pages/{宿主管理,日记与生活,关系与记忆,关系与权限}/workspace.html`，映射关系在 `pages/陪伴小屋/page-build.json:3-8` 与 `tools/sync_framework_page.py:15`（host/life/relationships/identity）。
- 构建产物：`tools/sync_framework_page.py:41-64` 把 `workspace.html + embedded-bridge.js + app.js + style.css` 内联成整页字符串，写入 `pages/陪伴小屋/workspace-bundle.js`（`window.CompanionWorkspaceBundle`）；同时产出独立副本 `workspaces/<name>/` 三件套并登记 SHA-256（`:66-73`）。
- 运行期：`product-page.js:547` 生成 `<iframe sandbox="allow-scripts allow-forms">`（无 allow-same-origin），`:558-562` 用 `frame.srcdoc` 注入，无网络请求。
- 桥接（父页 `product-page.js:563-589`）：iframe 内请求经 postMessage 代理，路径白名单——host 仅 `^(staging|host)/(status|probe|initialize|start|stop)$`（GET 只放行 /status），其余三个只允许 `<name>`(GET) 与 `<name>/command`(POST)，并映射到 `relative(role()[name+"_api"])`。
- 桥接（iframe 内 `embedded-bridge.js`）：暴露 `window.AstrBotPluginPage`，18 秒超时；应用主题/密度/圆角/字号/动效；在嵌入态隐藏 `#start-host,#stop-host`（日记与生活工作区的宿主启停按钮在小屋内不出现）；ResizeObserver 上报高度。

## 三、配置的三条接入通道

| 通道 | 适用组 | 前端 | 后端路由 |
| --- | --- | --- | --- |
| ① 统一配置编辑器 | 17 个组（下表标 `/config`） | `config-editor.js` 的 spec（字段中文标签/帮助/顺序）+ `app.js` 的 `configEditors(容器,[组名])` 声明 + `mountConfigEditor` 挂载（`app.js:1239-1265`） | `GET /config?sections=…`、`POST /config/configure`（`astrbot_host/configuration_api.py:74-75`），`SECTIONS` 映射 17 个 Management 类（`configuration_api.py:35-48`） |
| ② 专用工作台 | `conversation.presentation`（回复工作台 `/reply`）、`memory`（`/memory/settings`）、`model.*`（`/model`）、`conversation.perception`（`/perception-native`）、`expression.learning`（`/reply/expression`）、`role.state`（状态工作台 `/state/command`）、`role.life`（日记工作区 `/life/command`）、语义素材（`/semantic`）、屏幕/现实提供方（`/perception` 桥） | 各自的页面模块（reply-page.js、memory-settings-section.js、models-page.js、perception-native-page.js、expression-page.js、state-*.js、日记工作区） | 各领域专用 API（见逐页稿） |
| ③ 生命周期 / 合同类 | 无配置组 | setup-guide.js、host 工作区、backup-page.js、calendar-editor.js 等 | `/setup/*`、`/staging/*`、`/host/*`、`/backup/*`、`/legacy/*`、`/state/command` 的 `calendar.*` action |

## 四、统一配置机制（companion_v2/configuration/）

- **注册表**：`FieldRegistry` 在 `companion_v2/adapters/astrbot/staging.py:219` 组装（含 model.* 字段），`astrbot_host/application.py:180-196` 并入各领域组；memory 由 `memory/configuration.py:84` 的 `extend_registry` 合并，contact 由 `proactive/configuration.py:351-357` 的 `with_contact_fields` 补齐。**合计 38 组 / 604 字段**（账本 `docs/V2_CONFIG_SURFACE_20260928.csv`，由 `tools/build_v2_inventory.py` 从代码重新生成：covered 535 / missing 59 / intended 10）。
- **服务**：`ConfigurationService`（`companion_v2/configuration/service.py:34`）：`read()` / `patch()`（原子稀疏补丁）/ `preview_changes()` / `receipt()` / `report_application()`。仪表盘侧封装 `GroupEditor.status()/configure()`（`configuration/management.py:55,134,150`）。
- **作用域层**：`ConfigLayer = installation / role / relationship / window / scope`（`models.py:32-37`）；继承链 `installation → role → relationship → window`（`models.py:115-126`）。字段声明 `FieldDefinition.layers`（默认 installation+role+window，`registry.py:29`）。
- **读写与幂等**：`edit_token = fingerprint(解析结果 + owner revision + 操作者绑定 + 策略 revision)`（`service.py:106-110`），不匹配报 `configuration_revision_conflict`；页面传 `operation_key` 生成 `op_id`，命中重放直接从 `configuration_changes` 台账返回原结果 `replayed=true`（`service.py:156-161`，`management.py:162`）。
- **生效方式**：`ApplyMode = IMMEDIATE / NEXT_TASK / RESTART`，逐字段声明（`models.py:40-43`，默认 NEXT_TASK）；未生效前状态报 `pending/next_task/restart_required`（`service.py:330`）。
- **继承与恢复**：读取沿 `target.chain()` 逐层回退，最内层显式值覆盖外层（`owners.py:70-79`）；`reset_to_inherit` 删除当前层该字段的行使读取回落（`owners.py:107-109`）。跨窗口共享字段用 `RoleSharedSettingsOwner`（实际写 role 层，首次写会把窗口旧值提升到 role，`role_settings.py:24-62`）——`role.life` 的作息与 `role.growth.skills` 用它。
- **已知例外**：`proactive.contact` 的两个关系级配额 `max_relationship_*_24h` 在窗口层禁写（`proactive/configuration.py:369-373`），编辑器字段合同同步去掉 window 节点（`configuration/management.py:404-413`）。

## 五、配置组总表（归属页 × 通道 × 后端）

字段数与生效方式由实查注册表得出；「通道」见第三节编号。

| 配置组 | 字段 | 作用域层 | 生效 | 归属页（唯一可写） | 通道 | 后端定义 → 消费 |
| --- | ---: | --- | --- | --- | --- | --- |
| `conversation.presentation` | 86 | window | next_task | 表达 D1 | ② `/reply` | conversation/reply_settings.py:226 → 分句/语音/群唤醒 |
| `conversation.perception` | 9 | window | next_task | 感知 A1/A4 | ② `/perception-native` | conversation/perception_settings.py:11 → 感知服务 |
| `conversation.image_review` | 11 | window | immediate | 产出 C1 | ① | conversation/media/review.py:100 → media/review_service.py |
| `conversation.media_quota` | 4 | installation+role | next_task | 产出 C1 | ① | conversation/media/quota.py:26 → media/quota.py |
| `conversation.recall` | 4 | window | next_task | 表达 D4 | ① | conversation/recall_settings.py:16 → 撤回读取 |
| `conversation.group_participation` | 20 | installation+role+window | immediate | 决策 B5 | ① | conversation/participation.py:49 → participation.py、group_interjection.py |
| `conversation.busy_gate` | 7 | window | immediate | 主动与联系 | ① | conversation/busy_gate.py:146 → busy_gate.py |
| `proactive.contact` | 160 | installation+role+relationship+window | immediate | 主动与联系 | ① | proactive/configuration.py:220 → proactive/service.py、scheduling.py |
| `role.state` | 61 | window | immediate | 状态页（设计变更；现状决策 B3） | ② 状态工作台 | role_work/state/configuration.py:18 → state/maintenance.py、humanized.py |
| `role.life` | 23 | window+role(共享) | immediate | 日记页（设计变更；现状决策 B3 编辑器 + 工作区表单双入口） | ① | role_work/life/configuration.py:27 → life/rest_gate.py、journal |
| `role.growth` | 2 | window | immediate | 学习与反思 L1 | ① | role_work/growth/configuration.py:41 → growth/progress.py |
| `role.growth.skills` | 2 | window+role(共享) | immediate | 学习与反思 L1 | ① | role_work/growth/configuration.py:47 |
| `memory` | 30（含 8 个 episode 相关字段） | installation+role+window | immediate | 决策 B1 | ② `/memory/settings` | memory/configuration.py → reflection.py、habits、episodes |
| `person` | 2 | installation+role+window | immediate | 决策 B1 | ① | memory/person/configuration.py:8 → memory/person/* |
| `knowledge` | 14 | installation+role+window | immediate | 感知 A1 | ① | knowledge/configuration.py:34 → knowledge/* |
| `library` | 12 | role | next_task | 学习与反思 L3 | ① | library/configuration.py:14 → role_work/reader.py |
| `expression.learning` | 10 | window | immediate | 学习与反思 L1 | ② `/reply/expression` | expression/configuration.py:21 → expression/style_service.py |
| `expression.reaction` | 9 | window | immediate | 表达 D3 | ① | expression/reaction_configuration.py:42 |
| `screen` | 3 | window | next_task | 感知 A3 | ① | screen/configuration.py:15 → screen/interpretation.py、peek.py |
| `photo.reference` | 3 | role | next_task | 产出 C1 | ① | references/configuration.py:20 |
| `wardrobe` | 6 | role | next_task | 产出 C1 | ① | references/wardrobe.py:21 |
| `content.authoring` | 6 | installation+role | immediate | **无挂载（待接）** | — | conversation/content/authoring_service.py:31、content/cover_assets.py:49 |
| `model.*`（15 任务档 × 8 字段） | 120 | installation+role+window | next_task | 模型与连接 | ② `/model` | model_gateway/routing.py:22 → ModelRouter(routing.py:51) |
| `model.budget` | 2 | installation+role | immediate | 自我 E4 | ① | model_gateway/budget.py:40 → budget.py 软预算 |

前端 spec（`config-editor.js` 的 `CompanionConfigEditors.spec`）当前覆盖上表标 ① 的 17 组、282 字段；`conversation.presentation` 的 86 项由 reply-page.js 内的独立字段声明承载，`model.*` 由 models-page.js 自带表单承载。导出命令：

```bash
node -e "const fs=require('fs'),vm=require('vm');const c=vm.createContext({window:{},document:{},sessionStorage:{},Intl,Date,Object,console});vm.runInContext(fs.readFileSync('pages/陪伴小屋/workbench-page.js','utf8'),c);vm.runInContext(fs.readFileSync('pages/陪伴小屋/config-editor.js','utf8'),c);console.log(JSON.stringify(c.window.CompanionConfigEditors.spec,null,1))" > /tmp/spec.json
```

## 六、通用验收口径（逐页稿共用）

- 控件真实渲染且一个组只在一页可写（R1）；无对象/角色时整页一条引导（`pageNeedsTarget`，`app.js:1235-1238`），不让每个挂载点各渲染空态。
- 保存有回执、有幂等（operation_key）、有版本冲突提示（edit_token/stale + rebase）。
- 失败一律翻译成人话：各页面模块自带错误码→文案表（如 memory-page.js:7-48、models-page.js:17-37）。
- 只读展示必须来自真实合同；没有合同的部分给空态/说明，不放假控件。
