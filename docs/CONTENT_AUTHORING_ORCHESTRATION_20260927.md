# Content 宿主侧编排：创作/续写、封面关联、主动分享（设计契约）

原始设计日期：2026-09-27；创作路径复核：2026-10-01。本文定义 Content 编排的边界与三段落点，并记录当前实现状态：

> 三段都在 V2 宿主侧编排，Content 只判权威。身份、授权、回执、撤回传播归 V2；作品正文与版本裁决归 Content。

因此本文所有新增逻辑默认落在 `companion_v2/`；`content_v2/` 只在必要时加动作声明。引用：[对照表](COMPANION_PROVIDER_STATUS_20260927.md)、[设计稿偏差审计](DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md)。

## 零、进度口径（2026-10-01）

| 部件 | 级别 | 生产调用点 |
| --- | --- | --- |
| 原生新作 | **端到端验证** | 专用 `content.authoring.draft` 模型任务生成标题、类型、正文，再由原始 V2 调用保存至 `content.work.create` |
| 原生续写候选 | **端到端验证** | 固定读取作品 head，生成续写正文，再以同一版本和修订号调用 `content.work.save_candidate`；不自动采用 |
| 写作边界 `ContentAccess.authoring` | **已接线** | 每次 Content 操作经 `bind_content_context(authoring=...)` 送达提供方 |
| 封面关联 `ContentCoverService` | **已实现，未接线** | 无生产实例化点；注入点待定（第三节末尾） |
| 分享材料 `from_content_work` | **已实现，未接线** | 无调用方，作品材料尚未进入主动候选 |
| `content.authoring.draft` | **生产使用** | 私聊创作工具启动专用后台模型任务；模型 profile 继承主模型路线的输出 token 配置 |

自动化验证使用合成模型、临时 V2 数据根和真实本地 Content provider；没有发送平台消息或采用候选稿。

## 一、三段与依赖

| 段 | 落点 | 状态 |
| --- | --- | --- |
| ① 创作 / 续写编排 | `conversation/content/authoring.py` + `authoring_service.py` | **已实现**（第二节） |
| ② 封面关联 | `conversation/content/cover_assets.py` | **已实现**（第三节） |
| ③ 主动分享候选 | `sharing/models.py` 的 `CONTENT_WORK` kind 与 `from_content_work()` | **已实现**（第四节） |

第①段现已从模型路由跑到原生 Content 写入并经模拟验证。第②、③段继续按本文件各自的实现状态维护；QQ 空间仍单独决策（第五节）。

## 二、续写编排的契约（已实现）

### 2.1 固定版本续写

V1 的 `creative.py` 是「立项 → 续写 → 审校」分步链；V2 不新增可写者，而是把这条链**翻译成一对手续**：

原生创作续写工具在同一父调用中依次执行 `content.work.describe`、固定 `version_id` 的分页 `content.work.read` 和 `content.work.save_candidate`。宿主保存每个原始子调用回执，并在返回成功前核对读取连续性、原章节 ID/标题/正文、`base_version`、`base_revision` 与候选稿回执；Content 的 CAS 再拒绝其间已变更的 head。Content 0.2.3 的读取页返回 `chapter_title`，V2 同时接受旧版响应形状；旧版提供方不返回章节标题时，续写仍可读写正文，但不能保留旧标题。

普通 Content 工具单独读取后再保存的路径仍由 `access.record_authoring_request` 记录固定版本；这条关系级记录与上面的单次创作工作流不同。

这条设计的用意是 W2-F03：模型读到 v3 之后、保存之前，人可能已经改出新版本；此时旧草稿**只属于 v3**，落在 v4 上就是覆盖人工修订。没有先读就保存的候选是全新候选，不受此约束（`recorded_authoring_request` 返回 None 即无义务）。

### 2.2 版本锚点携带请求

`ContentSources.anchor()` 新增可选 `request` 字段并封进载荷：封面关联与分享候选因此能知道"这一版是照着哪个固定版本写的"，不必回读对话。旧锚点没有该字段仍然可读（校验同时接受两种键集合）。

### 2.3 配置（`content.authoring` 组，已接入陪伴小屋）

| 字段 | 默认 | 层 | 含义 |
| --- | --- | --- | --- |
| `enabled` | true | 安装、角色 | 创作编排总开关 |
| `direction_prompt` | 空 | 安装、角色 | 该角色/安装的创作方向偏好（柔性参考，不覆盖原人格） |

整组共用 `(INSTALLATION, ROLE)`。V2 不另设正文字符数或候选稿数量上限；正文由所选模型路线和 Content 自身的作品合同处理。

**明确不迁**（设计差异，不是欠账）：`creative_chars_per_session` 那类「累计到目标字数就标记完成」——字数只是资源上限，完成由用途与作者判断；`creative_share_probability` 那类概率——分享时机不由字数比例、成熟度或概率决定。

### 2.4 当前创作动作

当前仅开放两条已接通原生 Content 的动作：新建会写入一部完整作品；续写会读取当前固定版本并保存候选稿。编辑既有作品、审阅修改和自动采用候选稿不由创作工具代办。

### 2.5 验证

`tests/test_content_authoring.py` 覆盖两种严格输出格式、长正文不受 V2 字符上限限制、方向/体裁提示和固定版本校验。`tests/test_native_authoring_flow.py` 使用合成模型和真实本地 Content provider，模拟创建、按标题查找、跨页读取 head 并保存候选稿，核对原角色人格、章节标题、专用模型路线和 head 未改变。V1/V2 能力差异与保留边界见[专项对照](CONTENT_AUTHORING_V1_PARITY_20261001.md)。

## 三、封面关联（已实现）

- **生成不由 Content 负责**：走 Image 自己的 `image.generate`；本模块不生成、不发送、不披露任何东西。
- **关联形态**（`conversation/content/cover_assets.py` 的 `CoverAssociation`）：`作品 + 正文版本 + 用途/位置(cover|illustration) + asset + 依据 hash + 自己的 revision`，状态只可为 `active | historical | unavailable`。
- **存储决策（已按 T09 口径定）**：落 `runtime_metadata` 键前缀 `content.work.cover:<digest([VERSION, context.key, work_id])>`，**不升 v41**。
- **关键取舍：工作当前版本显式记录**。封面 store 不能从自己的历史推断 head——最后一张图退休并不说明正文停在哪。因此存储形如 `{"head": <当前版本或 null>, "items": [...]}`，`recheck` 与 `associate` 都据它判断"这张图是否还是当前版配图"。
- **三条行为规则（已实现并有测试）**：
  1. **仅改标题、配图依据仍成立时**：`recheck(head_basis=原依据)` 在同一依据下**不重画**，直接以当前版本建立**新关联修订**（`revision+1`、`version_id` 前移）；
  2. **内容实改影响画面时**：`head_basis` 变化 ⇒ 旧图转 `historical`，**保留在它自己的版本上**，`effective()` 返回空，绝不自动挂到新稿；
  3. **生成成功但晚到**：`record_late()` 把原图存成**原版本**的关联（`historical`），不回写新正文。
- **开关**：`content.authoring.cover_enabled`（默认 false，安装/角色层）+ `content.authoring.max_covers_per_work`（默认 2，1–8）。没有封面不等于作品不存在——`effective()` 对无封面作品返回 `None`，`ShareMaterial` 的 asset 也始终可选。

## 四、主动分享候选（已实现）

- **Content 只做一件事**：把作品或版本包成一个 `ShareMaterial`，时机、额度、投递全归既有主动与 Delivery 链。`sharing/planner.py` 的 `SharePlanner.prepare()` 照旧复核来源与素材可读性。
- **决策（已定）：新增 `ShareMaterialKind.CONTENT_WORK`**，与 `ROLE_ARTIFACT` 同属 `ROLE_OWNED_KINDS`（都要 `role_owner` 且必须与来源同 installation/bot），但保持可区分，便于将来按来源分别限流与展示。
- **构造**：`ShareMaterial.from_content_work(source=..., role_owner=..., work_id=..., version_id=..., created_at=..., asset=None)`。材料 ID 为 `work-material-<work>-<version>`，**指向一个固定版本**——所以"你之前写的那段"永远能回到当时的原文，作品后来更新也不会偷换已分享的原话。
- **必须守住的边界（已写进契约与测试）**：候选 `accepted` 只证明候选被接纳，**不等于已披露**；只发引子不结清正文；平台无可靠回执记 `uncertain` 且不重复发送；分享时机不由字数比例、成熟度或概率决定，因此**不迁 `creative_share_probability`**。构造材料本身不写任何记录（测试断言 `runtime_metadata` 不变）。

## 五、QQ 空间：单独决策，不混进这批

按 V2 现有口径 `qzone_*` 属「v1 专有/范围待定」；提供方文档 `COMPANION_STORY_CONTRACT` 亦明确 QQ 空间是陪伴核心的外部平台能力，Content 不能当它的数据所有者。若要做，落点在 Delivery / 平台能力侧，Content 只提供工作区调用适配。**建议单独立项。**

## 六、模型任务注册（已实现）

`conversation/content/authoring_tasks.py` 注册一条后台任务，`ModelRouter` 将其纳入模型路线：

| 任务键 | Lane | 默认输出上限 | 提示词定位 |
| --- | --- | --- | --- |
| `content.authoring.draft` | BACKGROUND | 继承主模型路线，不单独配置 | 按当前角色和本次要求创作；续写读取固定版本 |

已接入单目标（`adapters/astrbot/staging.py`）与多目标（`astrbot_host/multi_session.py`）两处装配。作者任务继承主模型路线输出 token 配置，不另设 V2 正文字数或候选数配置。

## 七、页面与验收同步

「陪伴小屋」的「产出 → 创作与作品」展示 Content 作品库、专用创作模型入口和角色创作方向配置。

验收口径更新：[对照表](COMPANION_PROVIDER_STATUS_20260927.md) 的 Content 行与 E06 已同步——E06 现为「**创作/续写编排、封面关联、主动分享已实现**；独立创作批处理与 QQ 空间待补齐」，E05 不变。

## 八、验证

| 套件 | 项数 | 覆盖 |
| --- | --- | --- |
| `tests/test_content_authoring.py` | 当前源码测试 | 严格新作/续写输出、正文无插件自设字符上限、固定版本和配置层级 |
| `tests/test_native_authoring_flow.py` | 当前源码测试 | 合成模型到本地 Content provider 的新作及候选续写闭环 |
| `tests/test_content_cover_and_share.py` | 10 | 开关默认关、关联自带依据与修订、实改转 historical、标题改不重画、晚到归原版本、无封面作品仍成立、active 上限、作品材料指向固定版本、owner 必填、构造不写记录 |
| `tests/test_native_content_flow.py` | 12 | 真实角色工具循环端到端（含读固定版本后握手落库、锚点封存请求） |

统一批跑（含模型矩阵与 staging 回归）：`test_content_authoring`、`test_content_cover_and_share`、`test_native_content_flow`、`test_model_gateway`、`test_astrbot_staging`、`test_native_provider_sessions`、`test_proactive_sharing`、`test_multibot_scope` 共 **120 项通过**；两个新增套件单独批跑 **30 项通过**。
