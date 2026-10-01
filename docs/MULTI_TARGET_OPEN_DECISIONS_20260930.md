# 多目标模式：需要先定的口径（2026-09-30）

为什么单列一份：下面这些**不是接线遗漏**，是产品与安全口径。没定之前，页面在这两处只给说明、不给入口
（`docs/MULTI_TARGET_PAGE_GUARDS_20260930.md`）。每条都写清「现状事实 → 待定问题 → 选项 → 代价 → 建议」。

先记一条已经定下的总规则：**页面按 `product.targetsMode()`（= `page/targets` 的 `mode`）分支，全页只此一个判据。**

---

## 一、备份（`BackupWebAPI`，只在单目标注册）

### 现状事实

1. 快照是**整棵 V2 数据根**的镜像，格式 `companion-v2.installation-backup.v1`，元数据必须带
   `installation_id` 与 `schema_version`；换安装或换结构版本一律拒收（`companion_v2/storage/backup.py:1,32,43,124-127`）。
2. 还原是**两阶段**：先暂存，宿主重启时才替换数据库文件（`storage/backup.py:16`）。
3. 授权是**安装级**：要 operator、不需要 target（`astrbot_host/backup_api.py:58`），且要求已有运行档
   （`session` 与 `runtime` 都得在，`:68-70`）。多目标控制器**两个都有**（`multi_controller.py:38,131`），
   所以这一条不是障碍。
4. 六条路由：列表 / 创建 / 校验 / 还原预览 / 暂存还原 / 待生效（`backup_api.py:28-34`）。

### A1 覆盖范围怎么算

「整安装」实际指的是**当前运行档正在用的那棵数据根**：

| 模式 | 数据根 | 出处 |
| --- | --- | --- |
| 单目标 | `<plugin_data>/<plugin>/profiles/<profile_id>/runtime` | `controller.py:340,347-349` |
| 多目标 | `<plugin_data>/<plugin>/installations/<installation_key>/runtime` | `multi_controller.py:65,119` |

- **选项①（建议）**：沿用"当前运行档的整棵根"。多目标下它就是那个安装键下的全部资料，
  快照格式与归属校验都不用动。
- 选项②：按目标/角色分区快照（"只备份某个目标的资料"）——需要新的快照格式、分区导出与按目标还原，
  成本高，且与"还原=整根替换"的现有实现冲突。

### A2 生效路径必须先补（**开放的硬前提**）

暂存还原只在**单目标控制器**的加载路径里被执行：`controller.py:347` 调 `apply_staged_restore(...)`。
多目标控制器**没有这一步**。所以直接把 `BackupWebAPI` 挂进多目标注册表的话，结果是
**"快照能建、还原能暂存、重启永远不生效"**——比按钮点不动更糟。

- 定：多目标加载路径是否补 `apply_staged_restore(<installation runtime root>, installation_id=...)`。
  **建议补**（同一处、同一个函数，语义相同：开库之前换文件）。
- 不补的替代：多目标下只开放"创建与校验快照"，明确写"还原请在单目标模式下做"。

### A3 授权口径

沿用现在的安装级判定（operator，不需要 target）即可；若要更严，可新增一个安装级 action
（如 `installation.backup`）并写进统一动作目录——多一项权限目录维护。

### A4 还原的影响面要不要写出来

还原会**替换当前数据根的全部资料**，多目标下这意味着同时影响该安装下的所有目标与角色。
- 建议：`restore/preview` 的文案里列出"这一步会影响 N 个目标 / M 个角色"，
  并在确认前显示快照时间与结构版本。用户最可能的误解是"只还原我当前看的这个角色"。

---

## 二、V1 迁移（`LegacyMigrationWebAPI`，只在单目标注册）

### 现状事实

1. 迁移产出的是 `ConfigIntent`：作用域（如 `role.state`、`proactive.contact`）+ 分组 + 字段改动
   （`companion_v2/legacy/migration.py:95-99,382`）。
2. 执行时要求**当前运行档里存在那些作用域**，否则报 `legacy_scope_unavailable`
   （`astrbot_host/legacy_api.py:235`）。多目标下有多个目标与角色，所以"用哪一个"必须先说清。
3. 幂等由 `plan_token`（V1 根指纹）保护：看到的那份与写入的那份必须一致（`legacy_api.py:164-172`）。
   记账按作用域逐条写进操作账本；**没有**"这份 V1 已经迁过"的安装级标记。
4. 迁移只读 V1、单向写 V2；V1 路径来自插件配置 `legacy.v1_root`（留空则同级目录自动寻找）——与模式无关。

### B1 落到哪个目标与角色

- **选项①（建议）**：迁移块里**显式选一次**目标与角色（`setup/targets` 已返回 targets 与 personas，
  页面直接可用），选完再侦察/试算/执行。
- 选项②：沿用页面当前选中的作用域（少一次点击，但"当前选择"会随用户在小屋里的浏览变化，
  迁移这种一次性动作不该跟着漂）。
- 选项③：安装级设置写安装层、角色级设置按选中角色写（最贴合语义，但要在 intent 上拆分作用域归属，
  改迁移器本身）。

### B2 同一份 V1 能不能迁到第二个角色

- 选项①（建议）：**允许，按"复制一份"处理**，执行前多一句确认（"这会把同一份 V1 设置再写进
  角色 X，已有的角色不会被覆盖"）。
- 选项②：默认拦下，需要显式解锁——要新增安装级"已迁移"标记（新表或查询操作账本），
  并定义"标记属于安装还是属于角色"。

### B3 作用域缺失怎么暴露

现在是执行到才报 `legacy_scope_unavailable`。
- 建议：页面在**侦察/试算阶段**就判断（选中的目标与角色上有没有这些作用域），
  缺什么列什么，别让用户点了"执行"才看到失败。

### B4 部分失败算不算失败

现状是逐条写、失败逐条列（`legacy_apply_failed` + 作用域）。
- 建议保持逐条：试算已经能看出会写哪些，逐条失败能让用户知道哪一组没写进去。
- 若要求"整批原子"，需要跨作用域事务，成本高且与现有账本逐条记账的形状冲突。

---

## 三、反向口径（多目标专属的接口）

`GroupMemoryWebAPI` 与 `GroupReplyWebAPI` **只在多目标注册**。页面今天没有消费它们，
所以单目标下没有反向的死按钮。将来接「群公共记忆」管理页时，同样按 `targetsMode()` 分支——
`tests/test_multi_target_page_guards.cjs` 的最后一条用例会提醒这件事。

---

## 四、定完之后各自动哪里

| 口径 | 改动点 |
| --- | --- |
| A1 沿用整根 | 无（只改文案） |
| A2 补生效路径 | `multi_controller.py` 的加载路径 + `MultiHostWebAPI.register()` 加 `BackupWebAPI` |
| A3 授权 | 无（沿用）／新增动作则改 `identity_policy/object_access.py` 的目录 |
| A4 影响面文案 | `backup-page.js` 的还原预览块 |
| B1 显式选目标角色 | `setup-guide.js` 的迁移块 + `legacy_api.py` 接受目标选择（现已支持 `target_id` 形式的分派） |
| B2 允许复制 | `setup-guide.js` 一句确认；拦下则要新增安装级标记 |
| B3 提前判断 | `setup-guide.js` 侦察结果的呈现（复用试算返回的作用域清单） |
| B4 逐条 | 无 |

---

## 五、推荐组合（已按它实现，2026-09-30）

> A1 沿用整根、**A2 先补多目标的暂存还原**、A3 沿用安装级授权、A4 列出受影响目标；
> B1 迁移块里显式选一次目标与角色、B2 允许复制但要确认、B3 在侦察阶段就说清缺哪些作用域、B4 保持逐条。

### 实现落点

| 口径 | 落点 |
| --- | --- |
| A1 | 不改格式；文案在还原预览里 |
| A2 | `multi_controller._open()` 在开库前调 `apply_staged_restore(root / "runtime", installation_id=…)`；`MultiHostWebAPI.register()` 挂一次 `BackupWebAPI` |
| A3 | 沿用（`backup_api.py` 的安装级判定，需 operator、不需要 target） |
| A4 | `backup_api._installation_scope()` 随预览与执行下发 `scope`；`backup-page.js` 渲染「影响范围」那一行 |
| B1 | `target_inventory()` 每角色生成 `legacy_api`；页面在迁移块里先选目标与角色（默认当前作用域，可换） |
| B2 | 执行前一句确认：再迁给别的角色等于复制一份，已写入的不被覆盖 |
| B3 | 侦察与试算都带 `scope_status`（含 `available` 与 `reason`），缺的当场列出 |
| B4 | 逐条不变（失败逐条进 `errors`） |

### 实现时发现并修掉的四个真缺陷

迁移的**执行**路径此前没有任何测试走到，四处错误叠加的结果是「点了执行，一条都写不进去」，
界面只会显示 `legacy_apply_failed`：

1. 目标推导传的是**宿主上下文**（`controller.context`）而不是**管线上下文** → 改 `session.profile.target`；
2. `OperationRef` 从 `companion_v2.execution.models` 导入（该模块没有这个名字）→ 改 `foundation.refs`；
3. `VersionRef` 从 `companion_v2.foundation.version` 导入（不存在）→ 同一个模块；
4. operation 的属主写成分组名，而 `configuration/service.py` 比的是分组声明的 `owner_id`。

回归护栏：`tests/test_multi_target_install_apis.py`（8 项，含单目标与多目标各一次真实迁移）。

按这个组合，备份在多目标下**需要动两处代码**（注册 + 生效路径），迁移**只需要页面加一步选择**；
两者都不改快照格式、不改账本形状、不新增权限动作。
