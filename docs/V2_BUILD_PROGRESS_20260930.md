# V2 建设进度核对（2026-09-30）

口径沿用 [V2_BUILD_PROGRESS_PERCENT_20260927.md](V2_BUILD_PROGRESS_PERCENT_20260927.md) 的四层法：只采信工作区代码、可复跑的测试、交付包与文件清单；**不采信文档自评**；没有现场结论的能力不按"已接线"折算。
本文只更新数字与事实，权重与合成方式不变。

---

## 一、规模（09-27 → 09-30）

| 指标 | 09-27 | 09-30（实测） | 变化 |
| --- | --- | --- | --- |
| 生产代码 | 526 文件 / 79,069 行 | **539 文件 / 94,417 行**：`companion_v2` 462 文件 / 82,684 行 ＋ `astrbot_host` 77 文件 / 11,733 行 | +13 文件 / +15.3k 行 |
| 本体测试 | 328 文件 / 3,134 方法 / 59,634 行 | **356 文件 / 3,711 方法 / 74,319 行** | +28 文件 / +577 方法 |
| 页面契约（cjs） | — | **28 个文件** | 新增 |
| 页面 | — | 30 个 js / 24 个 css / 21,371 行 | 外壳重排 |
| 领域 | — | **29 个一级领域**（adapters…storage） | — |
| 文档 | — | 236 个（208 篇 md） | 文档面仍在膨胀 |

## 二、契约面（实测）

| 项 | 值 | 证据 |
| --- | --- | --- |
| 配置面 | **604 字段 / 38 组** | `tools/build_v2_inventory.py` 的账本 |
| 按层分布 | 窗口 202 / 安装·角色·窗口 186 / 四层 158 / 窗口·角色 25 / 角色 21 / 安装·角色 12 | 同上 |
| 页面可写分区 | **SECTIONS 17 ＝ SPEC 17 ＝ MOUNTED 17**（三方全绿） | `build/tmp/check_section_wiring.py` |
| 分区覆盖自检 | **17 分区 / 282 字段全过**（4 项有意不接） | `tools/audit_page_config_coverage.py` |
| 宿主路由 | 84 条字面量；注册的 API 模块 **单目标 18 / 多目标 20** | `astrbot_host/*_api.py` |
| 存储 schema | 代码 **v45**；运行档 `qq-v2-stream-20260926` 也是 **v45**；其余 6 个预览档 v14–v32（打开时迁移） | `schema.py` ＋ 7 个运行档库只读查询 |
| 页面产物 | 与源码一致（`--check` 空差异） | `tools/sync_framework_page.py` |

## 三、四个层次

### A. 缺口清单（T01–T54）

09-27 自评 **44/52 = 84.6%**（8 项搁置不计入分子但保留编号）。本轮又收口若干（见第四节），但**任务表自己的快照仍未重算**，所以这里保守沿用 84.6%。

### B. 真实验收

**0 / 86**（9 组 86 行，结果列全部「待测」）。其中 68 行标"已接线"、15 行"待补齐"——那是接线状态，不是验收结论。

### C. 七个拓展

09-27 自评 75.7%（7/7 源码齐备、5/7 领域级核对、9/16 能力面）。本轮在 Image（生图路线四个预置字段）与参考素材/衣柜上有推进，未重新测量，暂沿用。

### D. 交付与页面

| 项 | 状态 |
| --- | --- |
| 页面接线 | ✅ 17 分区三方全绿；外壳（左栏／小屋／面板）已重排 |
| 交付包 | ✅ **今天 19:07 构建**：`dist/companion-v2-connection-20260930/astrbot_plugin_private_companion_v2-2.0.0.zip`，45.95 MB / 1,417 文件 / `sha256 59cd09ee…`，`release-manifest.json` ＋ `SHA256SUMS.txt` 齐备 |
| 包内容范围 | ⚠️ 清单里**只有本体一个包**（09-27 是 8 包）；七个提供方不在包内 |
| 随包测试 | ❌ `host-tests.log`：**80 项、4 个错误**（全部是 `ModuleNotFoundError: astrbot_plugin_screen_companion`，因为包里没有提供方）；`page-tests.log`：**60 项、1 失败**（`a delivery receipt cannot stand in for a reviewed draft`，期望的回执态文案在当前工作区页面里是有的，包内页面取到了等待态） |
| 包与工作区的一致性 | 抽查 7 个文件：5 个逐字一致（含 `models-page.js`、`multi_api.py`、`backup_api.py`）；`legacy_api.py` 只差一个末尾空行；`app.js` 与 `index.html` 在打包之后（19:12 / 19:14）又被改动 → **需要重打包** |
| 缺陷台账 | 09-27 的 18 条里，B9/B10/B11/B12 已修；B1/B2/B3/B4/B5/B13/B15/B16/B17 **仍成立**；另有 09-29 新记录的"群公共记忆无前端入口""主动识屏开关缺控件" |

## 四、09-27 以来落地的

1. **页面**：外壳重排（左栏导航／小屋常驻／下方面板）、17 个配置分区接入且三方对账全绿、多页"清空后接回"、家具与拓展面板设计定稿。
2. **能力链**：识屏生产链（B9/B10 修复）、群图审核、表达学习、参考素材与衣柜闭环、书架二期、语义与黑话链。
3. **宿主**：固定档改为"只看身份"三道关 ＋ 收据规范化；页面桥三处缺陷修复（页面连不上宿主）；`proactive.contact`（158 字段）接入页面并纳入覆盖自检。
4. **生图路线**：`parameters` 与 `guidance` 可编辑（边界从扩展下发的 limits 读），`reference_bindings` 与 `masked_edit` 保持只读并说明原因；保存上限提到 256 KB 并在页面预挡。
5. **多目标**：备份接口注册 ＋ 加载路径补暂存还原；V1 迁移按角色挂载、试算阶段报缺作用域；顺带修掉迁移执行的四个真缺陷（目标推导用错上下文、两个模块导入错误、operation 属主取成分组名）。
6. **V1 插件**：`main.py` 两处把换行写成字面量 `` `n `` 导致的 `SyntaxError` 已修（备份在 `_private_companion_backups\20260930-before-syntax-fix\`），宿主加载路径导入通过。
7. **交付流水线**：`tools/build_v2_release.py` ＋ `verify_v2_release.py` 跑通，随包测试日志落地。

## 五、仍然卡住的

| 级 | 事 | 证据 |
| --- | --- | --- |
| **P0** | **核心隔离门仍是红的**：`tests/test_isolation.py` 的 G0 断言失败（`legacy/migration.py:159/171/188` 的 `read_text`／`rglob`／`sqlite3.connect` 没有登记命名策略） | 本轮复跑：1 失败 |
| **P0** | **交付包需要重打且随包测试未绿**：只含本体、打包后源码又变、4 错 1 失败 | 第三节 D |
| P1 | **真实验收 0/86**：需要最终 ZIP ＋ AstrBot 4.27.2 ＋ 真实 OneBot/NapCat ＋ 真实模型与设备 | 验收表自身口径 |
| P1 | **待决策缺陷 11 条**：B1/B2/B3/B4/B5/B13/B15/B16/B17 ＋ 群公共记忆无前端入口 ＋ 主动识屏开关缺控件 | `docs/DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md` ＋ 09-29 复核 |
| P2 | 文档滞后：任务表快照未重算、四份导航设计稿无现行版本链、Content 预览与源码差 23/31 文件、两处审计工具仍是手写清单 | `docs/FRAMEWORK_VS_DESIGN_GAPS_20260929.md` |

## 六、全量回归实测（2026-09-30）

命令：`build/tmp/run_full_suite.py`（`unittest discover` 全树，`ASTRBOT_ROOT` 指向临时目录，`PYTHONPATH` 含 AstrBot `backend/app`）。

| 指标 | 09-27 | 09-30 |
| --- | --- | --- |
| 执行用例 | 3,135 | **3,730** |
| 失败 | 16（11 FAIL ＋ 5 ERROR） | **24（12 FAIL ＋ 12 ERROR）** |
| 跳过 | 1 | 1 |
| 通过率 | 99.49% | **99.36%** |
| 用时 | — | 3,353 秒（约 56 分钟） |

**逐条抽样定性**（单独跑复现的算真实失败，只有全量跑才失败的算用例互相影响）：

| 结论 | 用例 |
| --- | --- |
| 真实失败（单独跑同样失败） | 群工具目录与成员归属（`test_astrbot_group_host` ×2）、群投递指纹（`test_astrbot_group_delivery`）、群上下文归属（`test_group_conversation_context`）、群图生成与回执（`test_native_group_image_flow`）、群成员风控建表（`test_group_member_safety`）、群公共记忆宿主（`test_group_memory_host_api`）、存储迁移链（`test_expression_style` 的 v39→…、`test_proactive_news_events` 的 v37→…）、新闻事件日期新鲜度、周期变化时钟、记忆活动摄取 |
| 只在全量顺序下失败 | `test_page_targets_api` 的 SDK 发现与桥注入、`test_product_integration` 的提供方包装器 |
| 已知硬缺口 | `test_isolation` 的 G0（隔离门，见 P0） |

两条值得单独说：

- 抽样 10 条里 **9 条单独跑仍失败**，集中在**别的窗口正在重建的面**（群工具目录／群成员归属／群投递、存储迁移链、新闻事件、周期变化、记忆活动摄取）——与本轮改动（生图路线、多目标备份与迁移、V1 语法修复）无交集。
- `test_product_integration.test_distributed_provider_wrappers_are_metadata_only` **单独跑已通过**：09-27 的进度文档把它的失败归因于 V1 `main.py` 的 `` `n `` 语法错误，今天修掉之后这条不再复现——V1 修复的直接效果。

## 七、结论

- **代码与功能建设 ≈ 79%**（沿用 09-27 权重：A 84.6%×45% ＋ C 75.7%×35% ＋ D 70%×20% ＝ 78.6%）。本轮 A 与 D 各有推进（页面全绿、多目标补齐、交付包跑通），但**同时新增两处硬门槛**（隔离门仍红、随包测试未绿），D 的"打包"分被"包内容不全 ＋ 需重打"抵掉，所以整体仍在 **78–80%** 区间。
- **含真实验收的总进度 ≈ 63%**，与 09-27 相同——差额全部来自 B 层（86 行验收一条结论都没有）。**代码规模长了 15k 行、用例多了 595 个，但这个数字不动**：卡点不是写代码，而是隔离门、打包范围与真机验收。
- 质量面同步在动：全量回归 **3,730 项 / 24 个问题 / 99.36%**（09-27：3,135 / 16 / 99.49%）。用例基数涨了 19%，问题数涨了 8 个，且抽样确认集中在**别的窗口在建的群聊与存储迁移面**，不是本轮引入。
- 下一步按价值排序：① 清隔离门（登记命名策略或把 V1 读取移出核心，二选一）；② 重打交付包并把随包测试跑绿（含把测试所需的提供方纳入测试环境）；③ 开真实验收（先 S、C 私聊主链）；④ 收 P1 缺陷；⑤ 重算任务表快照与文档数字。

## 八、可复跑

```powershell
$py = "E:\astrbot\backend\python\python.exe"
$env:PYTHONPATH = "E:\astrbot\backend\app;C:\Users\99505\.astrbot\data\plugins\astrbot_plugin_private_companion_v2"
& $py -X utf8 build\tmp\check_section_wiring.py            # 分区三方对账
& $py -X utf8 tools\audit_page_config_coverage.py          # 分区覆盖
& $py -X utf8 tools\build_v2_inventory.py                  # 配置账本
& $py -X utf8 build\tmp\run_focused_suite.py tests.test_isolation   # 隔离门（会失败）
& $py -X utf8 build\tmp\run_full_suite.py                  # 全量回归（耗时）
node tests\test_models_page.cjs ; node tests\test_setup_guide.cjs
```
