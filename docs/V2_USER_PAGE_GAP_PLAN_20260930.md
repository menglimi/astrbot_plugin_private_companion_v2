# 用户/相识页：按 V2 实际情况该补哪些（2026-09-30）

承接 [V1_V2_USER_PAGE_COMPARISON_20260930.md](V1_V2_USER_PAGE_COMPARISON_20260930.md)。
那份只回答"差多少"，这份回答"**该补哪些**"——判断依据是 V2 自己的模型与已有接口，不是照抄 V1。

三条判据：
1. **数据/服务已经在 V2 里** → 只差投影或接线，优先做；
2. **V2 已用别的机制表达** → 不再造第二套开关（否则两处状态会打架）；
3. **V2 确实没有这个概念** → 先定口径，再谈实现。

## 本次追加（2026-09-30）

原稿按"V2 有什么数据"排优先级，会把力气花在群友目录上。**追加一条口径：这一页主要
服务私聊用户，尤其是同时授权了「对话」与「主动」的那几个**（见 §三）。据此：

- **新识别出最该补的一项**：这一页今天把"聊了多少"讲得很清楚，却完全没讲"他能不能被
  回复、你允不允许主动找他"——而后者才是管理员打开它要确认的事（D1/D2）；
- **A5（记忆归属）已完成**，且核实后**不该放进相识详情**——它是安装级的，放进详情
  会暗示"按人不同"（§A 档）；
- **A1/A2/A3 对纯私聊用户补了显示不出东西**——实测当前档该三项皆空（§A 档末）；
- **B 档有三条路由并不存在**（B1/B3/B4），原稿当成现成的，已逐条核实并修正（§B 档）；
- 落地顺序按新口径重排（§四）。

**本文档的性质**：截至本次核对，除 A5 外**其余各项都还是"待做"**，没有已完成的实现
混在里面。核对依据都写成了可复跑命令（§六）。

---

## 一、不该补的（V2 已经这样定了）

| V1 的做法 | V2 的机制 | 为什么不再补 |
| --- | --- | --- |
| 好感度数值、当前互动档直接编辑 | 关系记忆 + 印象卡切片 + 审阅链（`relationship.memory.*`） | 手工改数字会让"证据推导"失效；要调就调记忆条目 |
| 回复温度 / 安全温度 / 黑屋 / 人工审核（按人） | 表达与审核组、群成员风控（群级/角色级） | V2 的安全边界是群与角色，不是某个人；按人开洞会绕过群风控 |
| 用户级"主动权限"开关 | 投递授权（grant，按作用域与受众）＋ `proactive.contact` 四层配置 | 再造一个开关会出现"页面说关了、grant 还开着"这类双源状态 |
| 画像三档模式（关闭/仅用已有/持续学习） | `person` 组的 2 个字段（相识开关、印象卡字数） | 印象卡产出本来受审阅约束；除非确有需求，不新增档位 |
| 身份归并（两个平台账号合成同一人） | 无（身份由 scope/subject 派生） | 动到授权与记忆归属，**单独立项**，不在本页顺手做 |

## 二、该补的（按"V2 已经有什么"分三档）

### A 档：数据已经在库里、只是没投影出来（零新概念）

相识卡片文档 `person.acquaintance.v1` 里已经存着、而管理页今天没显示的东西。
**2026-09-30 核实**：`_person()`（`companion_v2/memory/person/management.py:63`）里
`private_attempts` / `nickname_updated_at` / `group_cards` 确实都没投影；`name_basis`
是写死的 `"platform"`，不是真来源。

| # | 补什么 | 现状 | 改法 | 状态 |
| --- | --- | --- | --- | --- |
| A1 | **尝试私聊次数与时间**（`private_attempts`） | 文档有，投影没给 | `_person` 加字段 + 详情显示 | 待做（**当前档该值为空，见 §三**） |
| A2 | **称呼更新时间**（`nickname_updated_at`） | 文档有 | 同上 | 待做（**当前档为空**） |
| A3 | **每个群的平台名片**（`group_cards[gid].card`） | 文档有；只拿第一个当名字 | 按群列出 | 待做（**只对群友有意义**） |
| A4 | **称呼来源**（`name_basis`） | 投影写死 `"platform"` | 显示"称呼来源：平台名片"；为管理员称呼预留 | 待做 |
| A5 | **记忆由谁提供**（`GET /page/ownership`） | **路由已实现并已接到记忆页** | 见下 | **已完成** |

**A5 已完成，且不该加到相识详情**：`GET /page/ownership` 已存在
（`astrbot_host/page_api.py:21`，`PageWebAPI.ownership`），记忆页已渲染它并带三种
兜底文案（让位 / 自己来 / 读不出来）。**它是安装级的**——判定读的是进程里别家插件
公开的声明，与"哪个人"无关。所以它只能放在**安装级的状态卡**上，放进相识详情反而
是在暗示"不同的人归属不同"，那是错的。

**成本**：只动一个投影函数 + 页面渲染；不新增表、不新增路由。

### A 档的实际价值：按用户类型分开算（2026-09-30 实测）

用真实运行档 `qq-v2-stream-20260926` 核过：`memory_views` 里 `person.acquaintance.v1`
**只有 1 行**，就是那个唯一被授权私聊的用户，它的文档是：

```
contexts            : ['private']                      ← 只有私聊，没有群
private_attempts    : {'count': 0, 'last_at': None}    ← 空
nickname_updated_at : None                             ← 空
group_cards         : []                               ← 空
```

**结论：A1 / A2 / A3 对纯私聊用户补了也显示不出东西。** 它们服务的是群友目录——
那张表里的"尝试私聊次数"有值时才有意义，"每个群的名片"对没有群记录的人更是空转。
真正需要它们的页是群列表（`renderGroups`），不是私聊用户详情。

所以 A 档的优先级按用户类型分：**群友视图先做 A3，私聊用户视图先做 A4**（A4 是唯一
对私聊用户恒有意义的——它回答"这个名字是哪来的"），A1/A2 等有数据了再说。

### B 档：V2 已有服务与路由，只差接线

**2026-09-30 逐条核实过路由是否存在**（原表有两处不准，已修正）：

| # | 补什么 | V2 已有的东西 | 改法 | 核实 |
| --- | --- | --- | --- | --- |
| B1 | 相识详情的「**关系记忆/印象卡**」页签 | **只有** `MANAGEMENT_PREFIX + "/command"`（POST，审阅用） | **缺一条按 subject 过滤的只读列表路由**——原表说"`GET /relationships` 列表已存在"是不对的 | ✗ 需新增读路由 |
| B2 | 相识详情的「**记忆**」页签 | `/memory/query`（**POST**）、`/memory/reflections`（GET）、`/memory/export`（GET）、`/memory/detail`（POST）、`/memory/source`（POST） | 调用既有路由，只读展示；不新增概念 | ✓ 全部存在 |
| B3 | 相识详情的「**未完话头**」页签 | `conversation` 域的 open-items 概念 | **`open_items` 没有任何宿主路由**——原表当成现成的，实际要新开一条 | ✗ 需新增读路由 |
| B4 | 相识详情的「**诊断**」页签 | `diagnostics` 域（自检/事故/解释） | **`astrbot_host/` 下没有 diagnostics 路由文件**，要从零加一条按角色+对象过滤的路由 | ✗ 需新增 |

**成本修正**：原表说"B1–B3 是纯接线（1–2 天）"，按核实结果，**只有 B2 是纯接线**；
B1/B3/B4 各要新增一条读路由，合计比原估多。

### C 档：需要新增字段或接口（按价值排序）

| # | 补什么 | 依据 | 成本 |
| --- | --- | --- | --- |
| C1 | **管理员称呼** | `models.py:82` 的注释已经写明"later slices add administrator and self-stated sources above them"，且 `name_basis` 已在 → 优先级：管理员 > 群名片 > 平台昵称 | 文档加一个来源 + 一个写路由（走操作账本）+ 页面输入框；1–2 天。**这是最值得补的一项** |
| C2 | 语气/风格（按人） | V2 没有按人存的风格位 | 先只读显示"当前生效的表达来源"；真要写，需先定它属于配置（哪一层）还是名片字段 |
| C3 | 身份归并 | V2 无合并入口 | 单独立项：口径（何时算同一人）、范围（记忆/关系/授权）、可否解绑 |

## 三、重点：已授权的私聊用户（2026-09-30 追加）

前两档是按"V2 有什么数据"排的，会把力气花在群友目录上。**但这一页真正要服务的是
私聊用户，尤其是同时授权了「对话」与「主动」的那几个**——他们才是这个插件在陪的人。
按这个口径重核一遍，优先级与 A/B 档不同。

### 3.1 哪些人算"已授权的私聊用户"

授权写在 `identity_grants`（`companion_v2/storage/schema.py:428`），真实运行档里
`subject_kind='human'` 的**全部 11 行都属于同一个人**：

```
onebot-user:995051631   conversation.reply    private 995051631   ← 对话权限
                        message.delivery ×5   private 995051631   ← 主动权限
                        text / screen.read / screen.process
                        extension.tool.invoke / configuration.read
```

**口径：`conversation.reply` + `message.delivery` 两项都在，才算"陪伴对象"。**
只有 `text` 只能收话不能回；只有 `message.delivery` 是能推不能聊。

### 3.2 这一页今天对他显示了什么

`workspaces/identity/app.js` 的详情卡（`:140-163`）已经区分了三类身份——这一条
**已经做对了**，不用再补：

```js
row("身份", person.private_chat && person.group_member ? `私聊用户 · 群友（${n} 个群）`
  : person.private_chat ? "私聊用户（没有群记录）"
  : person.group_member ? `群友（只在群里，${n} 个群）` : "暂无往来记录");
```

再加上首次见到 / 最近出现 / 累计消息 / 活跃天数 / 私聊互动 / 出现过的窗口。

**也就是说：它把"这个人跟我们聊了多少"讲得很清楚，却完全没讲"他能不能被回复、
你允不允许主动找他"。** 而后者才是管理员打开这一页要确认的事——数据统计回答不了
"为什么机器人不回他"这个真问题。

### 3.3 该补的（按这个口径排序，取代 A 档的位置）

| # | 补什么 | 数据来源 | 为什么优先 |
| --- | --- | --- | --- |
| **D1** | **能力授权清单**：`conversation.reply` / `message.delivery` / `text` / `screen.*` / `extension.tool.invoke`，各自"有/无"与作用域 | `identity_grants` 按 `subject_id` 过滤 | 直接回答"他能不能被回、能不能被主动找"。**当前完全没有** |
| **D2** | **陪伴对象标记**：`conversation.reply` + `message.delivery` 同时具备时，在列表与详情上标出来 | 同上，两条授权求交 | 一屏看出"哪些是真在陪的人"，不必逐个点开 |
| **D3** | **主动联系状态**：这个人现在会不会被主动找（免打扰 / 强度档 / 最近一次主动时间） | `proactive` 域的既有投影 | 归属与开关都已存在，只差按人投影；答"为什么他没收到主动消息" |
| **D4** | **记忆归属**（原 A5） | `GET /page/ownership` | **安装级，不进详情**。放安装状态卡；放进详情会暗示"按人不同"，那是错的 |
| D5 | 称呼来源（原 A4） | `name_basis` | 仍值得做，但要先把投影里写死的 `"platform"` 换成真来源 |
| D6 | 群名片逐群列出（原 A3） | `group_cards` | **只对群友有意义**，放群视图，不放私聊用户详情 |
| D7 | 尝试私聊次数 / 称呼更新时间（原 A1/A2） | `private_attempts` / `nickname_updated_at` | **当前档两者皆空**，等有数据再做 |

### 3.4 一个需要先定的口径

D1/D2 只读展示没问题；**"能不能在这里改授权"是另一个问题**——第十五行已经否掉了
"用户级主动权限开关"（会与 grant 出现双源状态）。所以本页对授权的定位应当是
**只读的事实陈述**，改授权仍走它原来的入口。真要在这里改，得先回答"页面改了
grant、那 grant 的来源账本怎么记"。

## 四、建议的落地顺序（按 §三 口径重排）

1. **D1 + D2**（1 天）：授权清单与陪伴对象标记——这是这一页最该回答、而今天完全没回答的问题；
2. **D3 主动联系状态**（半天）：接线即可，答"为什么他没被主动找"；
3. **D4 记忆归属放状态卡**（已完成，只差摆放位置）；
4. **B1 + B2**（1–2 天）：印象卡与记忆两个页签——V2 的强项，页面上完全看不到；
5. **C1 管理员称呼**（1–2 天）：先把 `name_basis` 换成真来源，再做写入口；
6. **D5–D7 + B3 + B4 + C2**：有数据或有需求时再做；
7. **C3 身份归并**：单独立项，先出半页口径文档。

## 五、验收口径

- 相识详情保持"**默认只读**"，唯一新增的写入口是 C1（管理员称呼），且必须走操作账本（可审计、可回退）；
- 每个新页签都要能显示真实数据（不许出现"暂不可用"的占位）；
- 不再新增与 grant / 审阅链并行的用户级开关。

## 六、可复跑

```powershell
# 投影里已经有什么（person.acquaintance.v1 文档结构）
python -X utf8 -c "import json,pathlib;print(pathlib.Path('companion_v2/memory/person/models.py').read_text(encoding='utf-8')[:1200])"
# 既有只读路由
Select-String -Path astrbot_host\memory_api.py,astrbot_host\relationships_api.py -Pattern 'PREFIX \+ "'
```

### 复核本页结论用的命令（2026-09-30 实测过）

```powershell
$py='C:/Users/99505/.astrbot/backend/python/python.exe'
$db='C:/Users/99505/.astrbot/data/plugin_data/astrbot_plugin_private_companion_v2/profiles/qq-v2-stream-20260926/runtime/companion-v2.sqlite3'

# ① 谁被授权了什么（§3.1 的数据来源）
& $py -X utf8 -c "import sqlite3;db=sqlite3.connect(r'file:$db?mode=ro',uri=True);[print(r) for r in db.execute('SELECT subject_id,capability,COUNT(*) FROM identity_grants WHERE subject_kind=''human'' GROUP BY 1,2')]"

# ② 相识文档里到底有什么（§A 档"值为空"的判据）
& $py -X utf8 -c "import sqlite3,json;db=sqlite3.connect(r'file:$db?mode=ro',uri=True);d=json.loads(db.execute('SELECT document_json FROM memory_views WHERE kind LIKE ''%acquaint%''').fetchone()[0]);print(sorted(d));print('private_attempts',d['private_attempts']);print('group_cards',d['group_cards'])"

# ③ 归属路由是否还在（§A5 的判据）
Select-String -Path astrbot_host\page_api.py -Pattern 'page/ownership'
```

**数据根随配置变化**：上例是当前唯一运行档；换档时改 `profiles/<档名>` 那一段。
