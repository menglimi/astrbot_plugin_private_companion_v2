# 多目标模式下的页面入口：哪些接口不存在、页面怎么分支（2026-09-30）

> **2026-09-30 晚些时候的更新**：备份与 V1 迁移都已补进多目标注册表
> （见 [MULTI_TARGET_OPEN_DECISIONS_20260930.md](MULTI_TARGET_OPEN_DECISIONS_20260930.md) 第五节），
> 所以本文第二节的「不给入口」已经改成「两种模式都给，且按角色选作用域」；
> 第一节的差异表只剩**多目标专属**那一列（`GroupMemoryWebAPI`、`GroupReplyWebAPI`）。
> 下面保留当时的判断与依据，作为「为什么当时要分支」的记录。

对象：陪伴小屋在**多目标宿主**（`multi_host.enabled = true`，`AstrBotMultiController`）下的入口。
口径：后端只认代码，页面只认 `page/targets` 返回的 `mode`（页面侧 `product.targetsMode()`）。

---

## 一、两种模式注册的接口不是同一套

`StagingWebAPI.register()`（单目标）挂 18 个 `*WebAPI`；`MultiHostWebAPI.register()`（多目标）只挂
`host/status`、页面目录、几条安装级路由，以及**按角色重挂**的域路由
（memory / state / reply / model / perception-native / life / relationships / growth / persona /
configuration / group-memory / group-reply）。

把两边的注册集合相减（`tests/test_multi_target_page_guards.cjs` 第一条用例锁住这个前提）：

| 只在单目标注册 | 只在多目标注册 |
| --- | --- |
| `BackupWebAPI`（备份六条）、`LegacyMigrationWebAPI`（V1 迁移三条） | `GroupMemoryWebAPI`、`GroupReplyWebAPI` |

`semantic`、`setup`、`perception`（非 native）在两处都注册，因此**不需要**分支——
这一条容易凭印象判断错，要按实际注册表看。

---

## 二、页面上的两个入口，各自的处理

| 入口 | 页面 | 多目标模式下的表现 |
| --- | --- | --- |
| 资料与维护 → **备份与还原** | `app.js` `renderDataOriginal()` | 不渲染 `#backupWorkspace`（`backup-page.js` 因此不被挂载），改为一句说明：备份以整个安装为单位、该模式没有注册接口、切回单目标配置后入口会回来 |
| 宿主管理 → 宿主运行状态里的备份说明 | `app.js` `renderHostWorkspace()` | 同一模式的说明，不放入口 |
| 开始使用 → **从 V1 带数据过来** | `setup-guide.js` | 整块换成说明（`isMulti()` 早退）；**自动侦察不发**；`legacy-scan / legacy-plan / legacy-apply` 三个动作在点击入口再挡一次 |

三处都遵循同一条规则：**后端在该模式下不注册的接口，页面不给按钮**——给了就是"点一次失败一次"，
而失败信息（路由未找到）对用户没有任何意义。

判据只此一处：`product.targetsMode()`。页面不自己猜，也不读别的字段。

---

## 三、为什么不是"把接口也注册到多目标模式"

`BackupWebAPI` 与 `LegacyMigrationWebAPI` 都可以做成安装级（备份本来就是整个安装为单位；
迁移写的是角色设置）。要让它们在多目标下可用，需要后端先决定：

- 备份：多目标下"整个安装"包含多个目标的资料，快照与还原的目标范围要重新定义；
- 迁移：V1 的角色设置要落到哪一个角色上，需要目标选择（`setup/targets` 已有 `multi` 字段可用）。

这两件事是**产品决定**，不是接线遗漏，所以本轮只做页面侧的分支，把后端注册留作后续。

---

## 四、另一处相关实现（不改）

嵌入的「宿主管理」工作区（`pages/宿主管理/app.js`）面对同一问题时用了另一种办法：
候选前缀表 `[{mode:"single",prefix:"staging"},{mode:"multi",prefix:"host"}]`，逐个试 `status` 路由，
哪个有响应就用哪个。它在**独立 bundle** 里、拿不到 `CompanionProduct`，因此按"探测"而不是按"模式"分支——
两种做法都成立，也都不会留下死按钮，所以保持原样。

---

## 五、护栏

`tests/test_multi_target_page_guards.cjs`（5 条）：

1. 两种模式的注册集合之差 = 上表（前提变了就回来改页面）；
2. 备份挂载点必须落在 `multi ? 说明 : 工作区` 的分支里，且同一渲染函数先读模式；
3. 宿主运行状态页在多目标下给出说明；
4. V1 迁移块按模式早退、自动侦察被跳过、三个动作在点击入口再挡一次；
5. 页面一旦消费多目标专属接口（`group_memory` / `group_reply`），必须同时出现模式判据。

`tests/test_setup_guide.cjs` 另加 2 条行为用例（多目标下不发侦察、旧按钮点不动），共 36 条。

---

## 六、验证

```powershell
node tests\test_multi_target_page_guards.cjs   # 5 项
node tests\test_setup_guide.cjs                # 36 项
python tools\sync_framework_page.py --check    # 空差异
```
