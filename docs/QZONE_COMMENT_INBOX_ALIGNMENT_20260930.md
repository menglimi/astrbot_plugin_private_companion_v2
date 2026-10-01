# 空间评论收件箱：V1 规则 → V2 存储模型对齐（2026-09-30）

目标：把 V1 的**评论识别与幂等规则**接到 V2 已有的模型上，再依次做后台扫描、图片与来源参数扩展。
本文只做对齐与决策，不含实现；所有引用都是本轮实测的 `文件:行号`。

---

## 一、两边现状

### V1（`astrbot_plugin_private_companion`，规则最全的地方）

`qzone_comments.py`（895 行）+ `companion/contracts/qzone_contract.py`（394 行）：

| 规则 | 位置 | 具体做法 |
| --- | --- | --- |
| 文本归一化 | `qzone_comments.py:34` `_qzone_normalized_comment_text` | 去 HTML 标签、HTML 实体反转义、压缩空白、转小写、去中英标点，截 160 字 |
| 评论者身份 | `:40` `_qzone_comment_author_key` | 有 `uin` 用 `uin:<uin>`；否则 `name:<归一化名字>`；都没有则 `unknown` |
| 帖子×作者键 | `:47` `_qzone_comment_author_post_key` | `<post_tid>\|<author_key>` |
| 记录形状与裁剪 | `:51` `_qzone_trim_comment_records` | 记录含 `key/post_tid/author_key/text_norm/text/ts`；按 `key` 去重；**已发评论保留 7 天、作者回复保留 24 小时**；上限 160 条 |
| 幂等判据 | `:109` `_qzone_comment_matches_recent_sent` | 同帖内，评论正文归一化后命中"最近已发"即视为重复，不再回复 |
| 不回复自己 | `:119` `_qzone_comment_is_self` | 用自己的 uin + 最近发送记录判定 |
| 作者节流 | `:129` `_qzone_author_post_recently_replied` | 同一作者在同一帖上刚被回过就不再回 |
| 记账 | `:138` `_qzone_note_comment_inbox_sent` | 回复成功后写入"最近已发" |
| 隐私护栏 | `:175` `_qzone_comment_reply_leaks_private` | 回复文本若夹带私聊信息则拦下 |
| 模糊匹配 | `:417` `_qzone_comment_fuzzy_score` | 把评论与"提示"对齐打分（用于绑定上下文） |
| 标识提取 | `:435` `_qzone_comment_identifiers` | 产出 `(post_tid, comment_id, 备用标识列表)` |
| 开关 | `contracts/qzone_contract.py:291` | `comment_inbox_enabled` |

### V2（已经具备的东西）

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| **相册** | `companion_v2/conversation/media/generated.py:125` `album_page()`、`:170` `album_image()` | "accepted Image output 的角色域、非占有投影"，带游标分页 |
| **空间动作** | `companion_v2/qzone/`（11 个模块：`service/protocol/feed/policy/topics/references/configuration/capability/...`）+ 宿主 `astrbot_host/qzone_{api,client,transport}.py` + `capabilities/qzone_access.py` | 发布与授权链路已通 |
| **入站幂等原语** | `companion_v2/storage/repositories.py` `InboxRepository.accept(consumer, event_id, payload_hash, observed_at)` | `(consumer, event_id)` 唯一；同一事件但载荷变了直接判失败——**评论事件天生适合用它** |
| **出站幂等与账本** | `companion_v2/qzone/service.py:214/225/229` `_reserve/_complete/_unknown` | 用 `operation_key` 预留—完成—未知三态；回复评论应走同一条 |
| **分享规划（连接点）** | `companion_v2/sharing/planner.py:36` `SharePlanner.prepare/follow_up_material` + `models.py:33` `ShareMaterial` | 候选带 source 与可选 asset 正本——**相册图与空间动作该在这里接上** |

**缺的正是**：评论事件的身份/幂等规则、收件箱状态、以及后台扫描。

---

## 二、对齐表（V1 规则 → V2 落点）

| V1 规则 | V2 落点 | 说明 |
| --- | --- | --- |
| 评论者身份（uin → name → unknown） | `companion_v2/qzone/comments.py`（新增）里的纯函数 | **不要**为评论者编造 `SubjectRef`：只保留平台标识，与"运行时档案只对已绑定的人"以及刚做的陌生号口径一致。若确实已绑定，再额外记 subject 引用 |
| 文本归一化 | 同一套规则原样移植，作为 `payload_hash` 的输入 | 归一化必须是**幂等且无副作用**的纯函数 |
| `(consumer, event_id)` 幂等 | `InboxRepository.accept(consumer="qzone.comment", event_id=..., payload_hash=digest(归一化载荷))` | `event_id = digest([platform, login, post_tid, comment_id 或 author_key+text_norm])`；**不新增表** |
| 已发 7 天 / 作者回复 24 小时 / 上限 160 | 域内状态文档 | 见下方决策 A |
| 自我评论、作者节流、隐私泄漏、模糊匹配 | `qzone/policy.py` 扩展 | 这些是**判定**，不是存储；测试按行为断言（不复制 V1 的实现细节） |
| 收件箱开关 | `qzone/configuration.py` 加一个布尔字段 | 不新建配置组（该域已有组），保持 schema 版本不变 |

---

## 三、两个必须先定的口径

**决策 A：收件箱状态存哪**
1. **`memory_views` 文档**（推荐先走这条）：零 DDL、不动 schema 版本、与相识卡片/权限书签同一套写法；代价是没有 SQL 索引，只能整档读写（160 条上限本来就适合整档）。
2. **新表 + schema v46 迁移**：可索引、可查询、可审计，但要升存储版本并写迁移，且已有 7 份运行档都要跑一遍。

按 V1 的量级（上限 160 条、7 天窗口），**方案 1 足够**；等真要按帖/按人做统计查询时再升表。

**决策 B：评论者要不要有 V2 身份**
- 建议**不建**（只在空间域内用平台标识）。理由与本次刚确立的口径一致：V2 的身份只来自宿主认证过的绑定；为一个空间评论者造 subject 会让"这个人是谁"出现第二个答案。
- 若某评论者本来就在绑定表里（私聊过的同一个人），可以顺手记下 subject 引用——这是**读取**，不是创建。

---

## 四、建议的切片顺序（与你的计划一致，补上验收口径）

1. **识别 + 幂等契约**（不扫描、不发布）
   - 新增 `companion_v2/qzone/comments.py`：身份键、归一化、去重判据、标识提取（纯函数）。
   - 接 `InboxRepository`：把一条评论折成 `(consumer, event_id, payload_hash)`。
   - 测试：同一评论重复投递只受理一次；载荷变了（正文被改）判为冲突；不同帖子的同文评论不互相吞；自我评论/作者节流各一条。
2. **后台扫描**
   - 游标（上次读到哪条）、频率与退避、失败不重放未知结果；每次扫描的产出仍走 `InboxRepository` 幂等。
   - 验收：连跑两次扫描不产生第二条回复；平台报错时状态记"未知"而不是"已发"。
3. **图片与来源参数**
   - 在 `SharePlanner` 里把候选与 `album_page()` 的图片接上（候选已带 source + 可选 asset 正本）。
   - 扩展发布参数（图片张数/来源标注），沿用 `qzone/service.py` 的 `_reserve(parameters=...)`。

---

## 五、进度

### 切片 1 已完成（2026-09-30）：识别与幂等规则 + 接到存储

| 件 | 落点 | 证据 |
| --- | --- | --- |
| 身份键（uin → name → unknown）、`帖子\|作者` 键 | `companion_v2/qzone/comments.py` | `tests/test_qzone_comments.py` **24/24** |
| 文本归一化（去标签/实体/空白/标点、小写、160 有界、幂等） | 同上 `normalized_text` | 同上 |
| 指纹与备用标识（`<tid>:fp:<sha256[:20]>`、`<tid>:sha1:<…>`） | 同上 `fingerprint / legacy_id / identifiers` | 同上 |
| 账本裁剪（按 key 去重、已发 7 天、作者回复 24 小时、上限 160） | 同上 `trim_records / note_sent` | 同上 |
| 幂等判据、自我判定、作者冷却（6 小时）、模糊打分、隐私护栏 | 同上 `matches_recent_sent / is_self / author_post_recently_replied / fuzzy_score / leaks_internal` | 同上 |
| **接到 V2 存储**：一条评论折成 `(consumer="qzone.comment", event_id, payload_hash)` 交给 `InboxRepository`；两份账本存成 `memory_views` 文档（按空间账号分档） | `companion_v2/qzone/inbox.py` | `tests/test_qzone_inbox.py` **13/13**（真库、真幂等表） |
| 不新增表、不动 schema 版本 | — | 上述用例全部走既有 `StorageRuntime`，无迁移 |

实现时被测试纠正的两处（值得记住）：

1. **`matches_recent_sent` 的语义**：它比的是**评论正文**，回答"这条评论是不是我自己发出去的"
   （V1 `_qzone_comment_is_self` 的第三个条件），**不是**"我回过这条没有"。我一开始把它当成后者，
   测试立刻指出"回过的评论仍会被判成可回"。现在：**"回过了没有"由幂等表永久保证**（比 V1 的
   6 小时冷却更强），冷却只负责"同一个人同一帖别连着回"。
2. **身份里必须带作者**：平台的评论 id 只保证帖内唯一，两个人各有一条 `c-1` 是可能的；
   不带作者就会把别人的评论当成自己那一条（V1 的指纹里同样带作者）。用例
   `test_two_people_using_the_same_comment_id_do_not_collide` 锁住了这一点。

### 切片 2 已完成（节奏层）：扫描的"什么时候扫、这轮回哪几条、失败怎么退避"

`companion_v2/qzone/comment_scan.py` + `tests/test_qzone_comment_scan.py` **9/9**。

| 纪律 | 做法 | 用例 |
| --- | --- | --- |
| **先问路再受理** | 总闸、回复开关、动作间隔都在**受理之前**判断；被挡时**不写幂等表**（否则这条评论以后永远回不了） | `test_a_disabled_switch_never_touches_the_inbox`、`test_a_spacing_block_defers_without_accepting_the_comment` |
| **预算之外完全不碰** | `max_actions_per_tick` 之外的新评论这一轮既不受理也不判定，下一轮仍然是新的（新增只读的 `CommentInbox.seen`） | `test_the_budget_defers_the_rest_without_accepting_them` |
| **失败退避、成功清零** | 连续失败 5 分钟起指数增长、封顶 6 小时；成功回到常规间隔 | `test_failures_back_off_exponentially_and_cap` |
| **未知结果不重放** | 回复键 = `qzone.comment.reply:<event_id>`，**只由评论身份决定**；结果未知时不换键、评论保持已受理 | `test_an_unknown_result_keeps_the_same_reply_key` |
| 游标按角色分档、重启后仍在 | `memory_views` 文档（`qzone.comment_scan.v1`），按 `owner_key(context)` 分档 | `test_the_cursor_is_per_owner_and_survives_a_restart` |

扫描节奏**复用这个域既有的字段**（`comment_enabled` / `comment_recent_posts` /
`action_min_interval_minutes` / `max_actions_per_tick`），不新增配置、不动 schema 版本。

### 切片 2 已完成（含宿主侧）：扫描接出来了

`astrbot_host/qzone_api.py` 新增两条路由（现有 7 条 → 9 条）：

| 路由 | 作用 |
| --- | --- |
| `GET /qzone-extension/scan-comments` | 只读回报：这一轮该回哪几条（含**确定的 operation_key**）、哪些被跳过及理由、下次可扫时间、连续失败次数。不发送、不调模型 |
| `POST /qzone-extension/reply-comment` | 回一条并落账。候选**在宿主这边按请求字段重新折叠**（`candidate_for`），所以回复用的键永远由评论身份决定，页面伪造不出能绕过"同键拒重放"的键 |

发送与记账的顺序收在一处（`CommentScanner.reply`）：**先发后记**——发送没成功就不动账本。
**投递结果未知**记 `unknown` 并退避（该评论保持已受理，不再重试）；普通失败记 `failed`
（账本不动，下一轮还能再试）。三条用例分别锁住这三种走向。

账号来源：扫描器从**凭据本身**（`credential.uin`）取空间账号，不接受页面指定——账本按账号
分档，认错账号就会把别人的回复算到这个号头上。

### 切片 3 前半已完成（相册 → 分享素材的桥）

| 件 | 落点 | 证据 |
| --- | --- | --- |
| 一条相册图 → **三个引用**（父产出、图片自身的 source、它的 asset） | `GeneratedImages.album_refs(item, context)` | `tests/test_generated_album_share.py` **14/14** |
| 相册图 → **分享素材**（`ROLE_ARTIFACT`，带 `RoleOwnerRef`） | `GeneratedImages.album_share_material(item, context)` | 同上 |
| 相册图 → **分享候选**（**经 `SharePlanner` 复检**：真的去读源仓库与素材仓库） | `GeneratedImages.album_share_candidate(item, context, planner=…, capability=…, at=…, authorizer=…)` | 同上（含"读不到就不给候选"两条） |
| **来源参数**：发说说可以带 `share_image_id`（当场折来源）或 `share_candidate_id`（**发布前再复检一次**） | `astrbot_host/qzone_api.py` 的 `publish` → `_share_source(...)` / `_recheck_share(...)` | 同上（含"备好之后被撤销 → 当场拒绝"） |

复检用的能力刻意是**公开发布**那一项：要公开引用一张图，就得先持有公开说话的授权——
这一点由 `SharePlanner` 读源仓库时真实校验（`SourceRepository.read` 会调身份端口做授权），
不是宿主自己声明的。

**图片本体不上传**：这里只做来源标注（`publish` 本来就收 `source_refs`），图片留在相册里。

### 待办（明确留着，不属于上面三条）

- **上传**（外部效果）：V1 的上传链在 `qzone_media.py`（769 行）。要做就必须按"结果未知不重放"的纪律。
- **切片 2 剩余（页面）**：行动页的评论收件箱一节（要等回复文案策略；回复文案本身也仍属
  "发空间内容策略 / 模型工具接线"，在空间拓展落地记录里明确列为未做）。
