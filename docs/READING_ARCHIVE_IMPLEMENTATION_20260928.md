# 书架（reading_archive）实装记录（2026-09-28）

按用户决定推进 A 类。两条关键选择由用户拍定：
**「先立合同与存储」**（首版不做内置提供方）、**「提供方登记 + 页面手工添加」**（两种写入源并存）。

## 一、合同设计：纯提供方

书架是 **provider contract**，不是内容仓库。V2 本体只持有三样：

1. **书目条目**——稳定标识、类型、标题、作者、元数据（`reading_archive_entries`）
2. **来源引用**——`AssetReference(provider_id, provider_version, asset_ref)`，
   指向提供方持有的资产；**正文与图片从不落进本库**
3. **治理与阅读状态**——每条目同意状态、阅读位置与进度、书评

因此**小说与漫画走同一套列**：加漫画只需新提供方，不改表。漫画图片后续接既有
Image originals 链时，本条目不参与，只提供 `asset_ref`。

### 复用 `ReadProviderRegistry`，不新造治理层

项目自己的架构审计（`docs/NATIVE_REFACTOR_DEPENDENCY_AUDIT_20260925.md:128`）写明：
「优先扩展现有合同所缺的端口，避免每个提供方各造一套权限、通用任务和来源系统」。
该注册表已提供发现、显式绑定、租约、授权围栏、预算与结果复核，书架只新增能力描述符。
样板：`companion_v2/memory/provider.py`。

### 优先级：提供方条目 > 手工条目

手工写**不能创建也不能覆盖**提供方条目（抛 `archive_entry_provider_owned`）；
提供方写可以覆盖手工条目。避免两个写入源互相打架。

## 二、两个只读能力

`companion_v2/library/provider.py`：

- **`library.catalog`**（`library.catalog` 权限，feature `catalog.list`）：
  `list` / `get` 两种操作，返回条目的**投影**——含 `asset_ref`，**不含正文**。
- **`library.read`**（`library.read` 权限，feature `asset.excerpt`）：
  复核条目可读（非手工、未撤回、同意未撤销）后返回来源引用 + 当前
  `reading_excerpt_chars`；**字节由提供方自己取**。

两者在 `CompanionApplication.__init__` 内、`runtime_identity` 存在的分支里注册
（`companion_v2/host/application.py`）。未提供 runtime identity 时不注册，与 memory 同口径。

## 三、配置组 `library`（ROLE 层）

`companion_v2/library/configuration.py`，五项，**默认关**：
`enabled=False`、`reviews_enabled=True`、`reading_excerpt_chars=1200`(200–8000)、
`manual_entries_enabled=True`、`max_entries_per_page=64`(1–200)。

层为 `ConfigLayer.ROLE`（书架属于人设，不随单个会话窗口分裂），与 `content.authoring` 同口径；
`GroupEditor._target()` 据此返回 ROLE target，页面标签显示「安装与角色」。

## 四、管理页

- 后端：`companion_v2/configuration/management.py` 的 `LibraryManagement(GroupEditor)`，
  注册进 `astrbot_host/configuration_api.py` 的 `SECTIONS`（键 `library`）。
- 前端：`pages/陪伴小屋/config-editor.js` 的 `spec.library`（含 `sections` 两段：
  能力开关 / 读取与列出上限）、`app.js` 的「书架与阅读」分区与 `renderConfigEditors` 挂载。
- 四件套：语法通过；缓存串沿用并行会话已改的 `new-config-sections-20260928`；
  `page-build.json` 已同步且 `--check` 干净；`tests/test_config_editor.cjs` 加 `NEW_KINDS.library` 与专条用例。

## 五、装配中必须同时做的事（易漏）

新能力不只是加描述符，**还要登记访问动作**，否则授权直接失败：

- `companion_v2/identity_policy/object_access.py` 的 `DEFAULT_ACTIONS` 增加
  `library.catalog`、`library.read`。漏了会得到 `unknown_access_action`。
- 读取该角色的书架设置需要调用方持有该 ROLE target 的 **`configuration.read`**。
  这不是夹具问题，是真实的授权依赖：书架读取隐含配置读取权限。

## 六、本次踩的坑（值得记住）

1. **provider 收到的是整个信封**，业务字段在 `request["payload"]` 内。
   最初直接 `request.get("operation")` 一律落到 `library_request_invalid`。
   参照 `memory/wire.py:316` 的 `call["payload"].get(...)`。
2. **`TaskError` 没有 `.reason` 属性**（原因在 `args[0]`）。我写了 `error.reason`，
   导致 provider 内部 AttributeError，被注册表包成 `provider_invocation_failed`
   （"private error details omitted"），真因被吞掉。改用 `str(error)`。
3. **`ReadProviderRegistry` 三个公开方法都带 `@outcome`**：返回 Outcome 而不抛异常。
   测试必须 `.unwrap()` 才能拿到 raise。
4. **请求预算不得高于绑定协商上限**（`budget.max_input_bytes` ≤ `binding.limits.*`），
   否则 `provider_budget_exceeds_binding`。测试改为按 `binding.limits` 取值。
5. **配置 patch 的 operation owner 必须是该组的 owner_id**（书架是 `library`，
   不是 `configuration`），且 `operation.scope` 必须等于 `target.authorization_scope`。
   任一不符都抛同一个 `operation_scope_mismatch`，从错误文本分不出是哪一条。
6. **`ConfigTarget.authorization_scope` 是 property**，不要当方法调用。

## 七、验证

- `python3 -m compileall -q companion_v2 astrbot_host tests` 退出 0。
- 新增 `tests/test_library_provider.py` **17 项通过**（走真实注册表）：
  目录列表不含正文、按 id 查询、不支持的操作/缺失条目的拒绝码、feature 校验、
  读取返回引用与字数上限、手工条目无可读资产、撤回不可读、同意撤销不可读、
  信封逐字段回显、代际不符与越权 scope 被拒、两项能力各自可发现；
  以及「关闭时四个入口全部拒绝」「默认关」「手工开关可单独关」「书评开关可单独关」。
- 新增 `tests/test_reading_archive.py` **28 项通过**（上一阶段）。
- 页面契约 `node --test tests/test_config_editor.cjs tests/test_semantic_page.cjs` **36 项通过**，
  含 library 分区两组渲染与「按角色显示为安装与角色」断言；已做反向验证（改错层会失败）。
- 定向回归 **156 项全过**（书架/存储/配置/provider 注册/管理访问/宿主存储/备份）。
- 跑不到的：依赖 `aiocqhttp` 的用例（沙箱环境缺口，非本轮引入）。

## 八、仍未做

- 条目列表、阅读进度与书评的**页面审阅控件**（当前只有配置面）。
- 内置文本提供方（用户定为后续）；漫画图片走 Image originals 链。
- 与 `RoleReadingService`（`role.reading.record`，角色读完某来源登记回执）的衔接：
  两者语义不同（单次活动完成回执 vs 长期书目与进度），未合并，也未接输入。
- C 类迁移范围待划。
