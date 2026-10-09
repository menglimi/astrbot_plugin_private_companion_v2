# 冻结候选清单（等你说「冻结」时一次跑完）

**用途**：开发期零构建；本页记录"哪些已完成、哪些待定、冻结时跑哪几条命令"。冻结后所有验证结论只标注**同一个冻结号**（全树 SHA256 清单），冻结后再有改动则该包作废、不做增量补验。

---

## A. 已完成 / 可进冻结

| # | 切片 | 关键产物 | 证据 |
|---|---|---|---|
| A1 | QQ 空间「发空间」主题与场景策略 | `companion_v2/qzone/topics.py`、`topic_prompt.py`、`policy.py`、`service.py`、`capability.py`、`astrbot_host/qzone_api.py`（10 条路由）、行动页主题/场景下拉、`qzone` 组 47 字段 | `tests/test_qzone_extension.py` 54 项；覆盖审计 19 分区 335 字段；页面接线 8/8；落地文档 `docs/QZONE_EXTENSION_LANDING_20261002.md` |
| A2 | 求助结果反向影响日程 | `companion_v2/qzone/agenda_link.py`（pending 记录、模型可见材料、闭合需日历回执）、`POST …/agenda-suggestions/resolve`、行动页建议面板 | 同上测试集内含 6 项专项；文档同 A1 |
| A3 | 页面密度修复 | `workbench.css` 字段网格（auto-fit 多列 + 长控件通栏 + 窄屏回落）、`tests/test_workbench_field_layout.cjs`；维护页 218 处字号 + 430 间距 + 60 圆角令牌化；审计新增「不得低于最小档位字号」；`OTHERS` 清空 | `docs/PAGE_DENSITY_20261002.md`；`audit_page_scale.py` 通过、`audit_theme_tokens.py` 通过 |
| A4 | 事实与经历（改名与划界） | 活代码 33 处改名；归属横幅与配置卡片 `note` 明确区分 V2 事实 ↔ 外部记忆插件；治理页三处「外部记忆插件」 | `docs/FACTS_VS_MEMORY_PLUGIN_20261002.md`；`test_memory_page` 15/15、`tests.test_memory_ownership` 21/21 |
| A5 | 存储基线审计 | `tools/audit_storage_baseline.py`（只读；硬线：WAL 绝对 32 MiB、历史 5000/1000、`document_json` 64 KiB/4 KiB；WAL 比值仅提示）、`tests/test_storage_audit.py` 13 项、基线快照文档 | `docs/STORAGE_BASELINE_20261002.md`；真实数据根退出 0 |
| A6 | 三处产品缺陷 | 工作树已修：`date_context.py:120` 捕获 `NotImplementedError`；`onebot.py:197-200` 仅哨兵 `-1/0` 判 unknown；`delivery.py:137-139` 合并重复定义（真实拦路石是同 diff 的 `_sent_hash`） | 新增隔离用例 `tests/test_group_image_delivery_governance.py`；A/B 双树对照 HEAD 6 红 → 修复 6 绿 |
| A7 | 原件还原 | `tools/audit_storage.py`（303 行，sha `5398cf12…`）已还原，仓库内持久副本在 `tools/_archive/` | 哈希三份一致 |

---

## B. 待定（冻结前需拍板）

1. **有符号 `message_id` 口径**：现状＝只排 `-1`/`0`，其余接受（代价：翻转 `tests/test_astrbot_onebot.py` 一条旧断言）；严格＝恢复 `<=0`。另：`astrbot_host/pokes.py` 目前接受 `-1/0` 为 delivered，是否一并统一。
2. **基线口径**：使用者那条 `3478 / 18 失败 / 104 错误 / 1 跳过` 出自哪棵树、哪条命令？本树实测为 `4079 / 75 / 45 / 1`，差异已定位到 6 个 game 模块导入失败（−23 项）与 7 个未跟踪新测试模块（+41 项），其余归因不到。**没有共同基准，闸门结论无法验收。**
3. **回复链路日志**（规格已备、未实现）：9 项契约 + 每轮汇总行 + 新配置组 `diagnostics.reply_log`（`enabled`/`level`/`preview_chars`/`include_content`）。是否进本次冻结。
4. **事务内夹带 I/O 四处**：`memory/reflection.py:94`、`memory/query.py:206`、`diagnostics/service.py:240`、`storage/backup.py:197`（＋屏幕原件两处）。建议先做前两处里最易触发锁冲突的 `reflection.py:94` 与改动最小的 `service.py:240`。
5. **闸门 B 批**：F1(22)→F2(12)+F13→F3(32)→F4/F6/F7/F8(18)→F9，共消 87/120；含两条环境前提（`PYTHONPATH` 加插件目录、`TEMP` 可写 + `PYTHONIOENCODING=utf-8`/`PYTHONUTF8=1`）。
6. **主动消息端到端 + 外部资讯/检修**（进行中）：新用例、`tools/run_proactive_sim.py`、资讯链与诊断面核查结论。

---

## C. 冻结时一次跑完（按序）

1. `python -X utf8 -m compileall -q companion_v2 astrbot_host`
2. **全量回归一次**（约 100 分钟；固定环境）：`python -X utf8 -m unittest discover -s tests -t . -v` → 记录 `Ran / failures / errors / skipped`
3. 三个审计：`tools/audit_page_scale.py`、`tools/audit_theme_tokens.py`、`tools/audit_page_config_coverage.py`
4. 前端矩阵：`node tests/test_section_wiring.cjs`、`test_workbench_field_layout.cjs`、`test_config_editor.cjs`、`test_console_styles.cjs`、`test_page_scale.cjs`、`test_app_globals.cjs`、`test_theme_registry.cjs`、`test_memory_page.cjs`、`test_maintenance_page.cjs`
5. `python -X utf8 tools/sync_framework_page.py --check` → 必须 `{"changed": []}`
6. `python -X utf8 tools/audit_storage_baseline.py`（真实数据根）→ 退出 0 或列出越线项
7. **构建一次** + `tools/verify_v2_release.py --release … --extract-to … --host-check` → 唯一公开页、宿主停机、**路由注销**、模型/平台调用 0
8. 解包目录内复跑：`tests.test_qzone_extension`、`tests.test_storage_audit`、`tests.test_proactive_*`、包内前端矩阵
9. 归档：核心包 SHA256 + 全树 SHA256 清单 + 上述每条命令的输出尾部 → 写成当次冻结记录

---

## D. 冻结纪律

- 冻结后任何改动 → **该包作废**，重新冻结，不做增量补验。
- 同一目录单写者；写文件前查 mtime/内容哈希，发现他人在写就停手报告。
- 所有结论只挂冻结号；"构建那一刻的树"这类免责声明不再作为交付证据。
- 开发期只跑定向套件 + 相关审计；不跑全量、不构建。
