# 统一测试与构建步骤（C09 / C10 / C11 批次）

日期：2026-09-26
适用：`astrbot_plugin_private_companion_v2`，内部 schema 已升至 **v40**

## 一、前置条件

V2 用独立数据根，**不读取、不迁移、不修改 V1 用户数据**。测试全部使用临时目录，不会触碰任何已有数据。

本批使用的解释器与路径（与既有批次一致）：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app;C:/Users/99505/.astrbot/data/plugins'
cd 'C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2'
$py = 'C:/Users/99505/.astrbot/backend/python/python.exe'
```

`PYTHONPATH` 必须同时包含 plugins 目录：`tests/test_game_native_*.py` 与 `tests/test_game_memory_ingestion.py` 顶层导入可选提供方插件 `astrbot_plugin_game_companion.native_v2`，缺这一条会在收集阶段直接失败。

## 二、第一步：编译检查

先确认语法与导入，能最快暴露本次静态改动的问题（例如新增导入缺失、`_bounded_body` 调用点不匹配）。

```powershell
& $py -X utf8 -m compileall -q companion_v2 astrbot_host tests
```

## 三、第二步：本批新增模块的定向测试

```powershell
& $py -X utf8 -m unittest `
  tests.test_self_review `
  tests.test_expression_style `
  tests.test_memory_archive -q
```

对应关系：`test_self_review.py`（C09）、`test_expression_style.py`（C10）、`test_memory_archive.py`（C11）。

## 四、第三步：存储迁移链路回归

C09 把 schema 从 v38 推到 v39，C10 从 v39 推到 v40。这一组验证：

- v38 老库能升到 v40，且既有 `runtime_metadata` 数据保留；
- 部分迁移（表存在但迁移记录缺失）必须被拒绝，而不是静默继续；
- 两处原先硬编码 `SCHEMA_VERSION_V38` 的既有测试改用 `SCHEMA_VERSION` 后仍然通过。

```powershell
& $py -X utf8 -m unittest `
  tests.test_storage_runtime `
  tests.test_storage_migrations `
  tests.test_proactive_balance_events `
  tests.test_proactive_news_events -q
```

`tests.test_storage_migrations` 是迁移链的主回归模块；`tests.test_storage_runtime`、`tests.test_state_storage_migrations` 分别覆盖运行时打开与状态域迁移，若第一条命令有失败，连带跑这两个定位。

```powershell
& $py -X utf8 -m unittest tests.test_state_storage_migrations -q
```

## 五、第四步：受影响的既有领域回归

本批改动触碰了记忆写入/读取边界（`record_json` 结构、来源发布、`Proposal` 校验）与会话上下文注入（`conversation/messages.py` 新增两个 contribution 分支），因此要连带跑记忆与对话两类：

```powershell
& $py -X utf8 -m unittest `
  tests.test_memory_writer `
  tests.test_memory_management `
  tests.test_memory_conversation `
  tests.test_memory_query `
  tests.test_foreground_conversation `
  tests.test_conversation_storage -q
```

## 六、第五步：全量回归（可选，耗时较长）

381 个顶层测试模块（连同支持模块共 419 个文件）。若要在本批改动后做一次完整确认：

```powershell
& $py -X utf8 -m unittest discover -s tests -t . -q
```

## 七、第六步：构建发布包

构建工具按目录整包收源码（`CORE_DIRS = companion_v2, astrbot_host, pages, docs, tests, fixtures, tools`），所以本次新增的领域文件、测试与文档会被自动纳入，**无需手工登记**。工具内不含任何 schema 版本常量，v40 不影响构建。

```powershell
& $py -X utf8 tools/build_v2_release.py --output D:/tmp/companion-v2-release-20260926
```

仅构建本体（不含可选提供方包）：

```powershell
& $py -X utf8 tools/build_v2_release.py --output D:/tmp/companion-v2-release-20260926 --core-only
```

## 八、第七步：校验发布包

校验会逐包核对 SHA-256、拒绝重复归档条目，并断言 `_conf_schema.json` 中 `staging.enabled`、`multi_host.enabled` 默认关闭，且 `delivery_mode` 的默认值为 `onebot_private`（2026-10-01 起：`preview` 仅作为旧配置的可读值，正式宿主固定原生发送）。这些断言不涉及本批改动，但仍是交付前的必备检查。

```powershell
& $py -X utf8 tools/verify_v2_release.py `
  --release D:/tmp/companion-v2-release-20260926 `
  --destination D:/tmp/companion-v2-verify-20260926
```

目标目录必须不存在或为空，否则工具会直接报错。

## 九、本批已知风险与预期失败点

按重要性排序，若测试失败请优先看这几处：

1. **`MemoryArchive.commit_import` 的来源发布**。导入依赖 `context.audience`、`context.scope` 与 `SourceRef` 三者自洽；若 `prepare_message` 的脱敏改写使 payload 变化，`content_hash` 与实际发布内容会不一致，随后 `MemoryAccess.evidence()` 的 `content_hash`/`span_hash` 校验会失败，表现为导入成功但事实读不出来。
2. **共享 `representation` 的两条原子**。它们的 `content_hash` 相同但 `source_id` 不同，预期无害，未做去重；若出现来源版本冲突，需在导入前按 `digest(payload)` 去重。
3. **`_bounded_body` 的 `json.loads` 重复键检测**。它是本次新增的通用小工具，四个 handler 共用；`import_commit` 的 body 上限是 `MAX_BUNDLE_BYTES + 8192`，大 bundle 可能触发 `len(raw)` 上限而非契约校验，届时调大上限即可。
4. **`EligibilityTests` 夹具用 `no_op` 操作**。`Proposal` 要求非 `no_op` 必须有 evidence，而夹具只测归档资格、不需要真实证据，因此用 `no_op` 绕过该约束。若后续把 `codec.proposal` 的校验收紧到拒绝 `no_op`，此夹具需连带调整。

## 十、沙箱状态说明

本次开发全程处于**沙箱工作区不可用**状态（隔离 Linux 环境启动失败），因此上列命令在本会话中一次也没有执行过。C09 / C10 / C11 三个领域的源码均为静态核对（逐文件比对真实 schema 列定义、`Proposal`/`Evidence` 校验规则、来源发布契约）后写出，**未经编译、未经测试、未经回归验证**。

请在本地按顺序执行第二至第八步，把失败项的完整输出回传，我再据此修正。
