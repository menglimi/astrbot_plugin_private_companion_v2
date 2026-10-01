# 11 · 关系与权限（`manage/identity`，含关系与情感）

代码位置：`renderIdentityPage`（`pages/陪伴小屋/app.js:1173-1176`）：分区一「关系与权限」= `renderIdentity()`（`product.identityMarkup()` 身份与范围卡 + identity 工作区 iframe）；分区二「关系与情感」= `product.workspace('relationships')`（关系与记忆工作区 iframe）。首页快捷项「人物与关系」也跳到本页（`app.js:1486`），没有独立的 people 路由。

构建源：`pages/关系与权限/workspace.html`（→ `workspaces/identity`）与 `pages/关系与记忆/workspace.html`（→ `workspaces/relationships`），嵌入机制见 [README.md](README.md) 第二节。

## 一、页面功能

两个工作区合在一页回答"她认得谁、谁被授权、她对你和对别人的理解"：相识目录按人沉淀（跨群与私聊同一人）；关系理解先过审才生效。

## 二、展示部分

### identity 工作区（关系与权限，只读）

| 分区 | 内容 | 证据（构建源） |
| --- | --- | --- |
| 范围条 | 运行档 / 操作人 / 相识人数 / 私聊用户与群友 | `pages/关系与权限/workspace.html:18-23` |
| 用户与群友页签 | 筛选 chips（全部/私聊用户/单纯群友）+ 人物卡（相识轨迹四档：陌生/眼熟/认识/熟悉）+ 详情 | `workspace.html:32-45` |
| 群聊页签 | 群列表 | `workspace.html:46-48` |
| 准入与身份页签 | 静态政策卡：「三档权限」「私聊准入(准备接入)」「身份归并(准备接入)」 | `workspace.html:49-72` |

端点：仅 `GET …/acquaintance`（`pages/关系与权限/app.js:4,197`；`astrbot_host/acquaintance_api.py:29`），无 command——**整页只读**。

### relationships 工作区（关系与情感）

| 分区 | 内容 | 证据 |
| --- | --- | --- |
| 范围条 | 当前角色 / 关系对象 / 当前会话 / 操作人 | `pages/关系与记忆/workspace.html:18-23` |
| 关系记录列表 | 状态筛选（待审阅/已审阅/已采用/已撤回）+ 分页 | `workspace.html:27-35` |
| 详情与更正 | 记录详情；更正对话框（填写理解修订） | `workspace.html:36-54` |

端点：`GET …/relationships`（`pages/关系与记忆/app.js:4,77`）；另 `GET …/staging/status` 判断可用性（`:85`）。

## 三、配置部分

**本页无配置组**（身份与授权写入由宿主/对象访问策略承担；`person` 2 项在决策 B1）。可写部分是**关系记录命令**：

按每条记录的 `item.actions` 渲染操作（`pages/关系与记忆/app.js:6,156-162,201-222`）：

| action | 行为 |
| --- | --- |
| `review` | 审阅通过 |
| `adopt` | 采用到对话 |
| `revise` | 更正理解（表单填 interpretation） |
| `retract` | 撤回记录 |

提交：`POST …/relationships/command`，body `{memory_id, action, expected_revision, view_token, operation_key, interpretation}`（`app.js:206-214`）——幂等 + 乐观锁与日历/状态命令同一套约定。

## 四、边界与空态

- 「私聊准入」「身份归并」是**准备接入**的静态卡，没有控件——旧身份归并需要单独协议。
- 首页/自我页/决策 B2 都只跳转到本页，不在各自页面重复渲染目录（R1）。

## 五、后端情况

| 路由 | 服务 |
| --- | --- |
| `GET /acquaintance`（`acquaintance_api.py:29`） | `companion_v2/memory/person/management.py` `PersonAcquaintanceDirectory`（`acquaintance_api.py:16,59`） |
| `GET /relationships`、`POST /relationships/command`（`relationships_api.py:25-26`） | `companion_v2/relationships/management.py` `RelationshipMemoryManagement`（`relationships_api.py:11`） |

多目标模式：per-target 路由 `/host/targets/{id}/roles/<digest>/relationships`（`multi_api.py:83-100`）。

## 六、相关设计稿与复核

- 决策 B2 的引用卡 → [07-decision.md](07-decision.md)；相识卡的配置 → [07-decision.md](07-decision.md) B1（person 组）。
- 复核：`sed -n '1173,1176p' pages/陪伴小屋/app.js`；`grep -n "item.actions\|review\|adopt\|revise\|retract" pages/关系与记忆/app.js`。
