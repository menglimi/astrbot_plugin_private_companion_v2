# 每日 Token 软限额配置化切片（2026-09-27）

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) T53 与用户批注「先处理没有窗口处理的任务」——即作用域落在安装/角色层、不随会话窗口变化的配置项。

## 现状核实（本批之前）

V2 已经有软限额的**机制**，但**没接配置，且默认关闭**：

- `model_gateway/budget.py` 的 `BudgetSoftPolicy(enabled=False, tokens=0, kinds=())` 是软上限策略，`DEFAULT_SOFT_DEFER_KINDS` 已列出可延后的可选后台任务（`role.calendar.plan`、`role.growth.progress`、`conversation.group.review`）；
- `BudgetLedger._soft_refusal` 的注释写的是「只读安装账户、窗口与角色都不能放宽上限」，但代码读的是**装配时固定的** `self.soft`，没有任何配置字段；
- `astrbot_host/settings.py` 从 `runtime.enable_daily_token_soft_limit` / `runtime.daily_token_soft_limit` 读进 `BudgetSoftPolicy`，默认 `False` / `0`。

而 V1 是**有配置且默认开启**的：`enable_daily_token_soft_limit` 默认 True、`daily_token_soft_limit` 默认 800000、硬上限 `daily_token_limit` 默认 1000000。

## 本片落地

| 关注点 | 落点 |
| --- | --- |
| 两个配置字段与校验 | [model_gateway/budget.py](../companion_v2/model_gateway/budget.py) 的 `configuration_fields()` / `SOFT_FIELDS` |
| 生效值解析 | 同文件 `effective_soft(runtime, context, fallback=None)` |
| 延后判定改用生效值 | 同文件 `BudgetLedger._soft_refusal` |
| 字段注册 | [host/application.py](../companion_v2/host/application.py) 的 `extra` 合并（`budget_configuration_fields()`） |

| 字段 | 类型 | 默认 | 作用域 |
| --- | --- | --- | --- |
| `model.budget.enable_daily_token_soft_limit` | BOOLEAN | `True`（同 V1） | 安装 / 角色，**无窗口层** |
| `model.budget.daily_token_soft_limit` | INTEGER | `800000`（同 V1），0–10¹² | 安装 / 角色，**无窗口层** |

三点按 V2 要求的处理：

1. **不加窗口层**：单个会话不能抬高或压低整天的可选工作预算，字段只有 `(INSTALLATION, ROLE)`，`apply_mode=IMMEDIATE`，`owner_id="configuration"`（沿用既有默认 owner，不需要新 owner）。
2. **生效值实时读取，不写 pinned 账户**：`_soft_refusal` 只决定可选后台调用**是否开始**，命中即抛 `model_budget_soft_deferred` 且**不落任何预留**，因此不会触碰 `model_budget_accounts` 里按 `policy_hash` 固定的日账户，也就不会触发 `model_budget_policy_changed`。这与硬上限必须 pinned 的设计相反，因此**硬上限本片不做成实时可变字段**（见边界）。
3. **既有安装不被静默改动**：`effective_soft` 在「该 role 下两个字段都非显式」时返回装配方给的 `fallback`，所以本项目自带宿主提供的策略保持不变；只有管理员显式写过值才覆盖。
4. **判定读两个账户**：`_soft_refusal` 现在同时读**安装账户与该角色账户**当天用量之和再比上限，因此角色层写下的上限对那个角色真实生效，而窗口依旧无法参与。

## P5/T53 收口（本批补完）

上一片把软限额接通为安装/角色字段，本批把它作为 P5 的最后一项收尾，并补上三处缺口：

1. **开关真的生效**：`_soft_refusal` 原先只判断 `tokens <= 0`，`enabled=False` 而 `tokens > 0` 时仍会延后。现在先判 `not settings.enabled`，与 `BudgetSoftPolicy` 的语义一致。
2. **延后清单可继承**：`effective_soft` 构造生效策略时保留装配档位给的 `kinds`，因此 `runtime.daily_token_soft_deferred_kinds` 在实时改阈值后仍然有效（配置字段只覆盖开关与阈值，清单属于装配决策）。
3. **插件默认值与注册表对齐**：`_conf_schema.json` 的 `runtime.enable_daily_token_soft_limit` / `daily_token_soft_limit` 改为 V1 默认 `true` / `800000`（此前是 `false` / `0`，两套默认值会互相矛盾）。这三项只决定装配默认值，运行中改阈值用治理设置里的实时字段。

顺带修复两处「字段先加、序列化没跟上」的既有缺陷：

- `staging_config.py` 的 `policy` 允许列缺少 `defer_seconds`，而 `ConversationPolicy` 已有该字段 ⇒ 任何 staging 配置都解析失败（`policy: missing, unknown or inapplicable fields`）；现已补上。
- `_segmentation_document()` 原只对 `SEGMENTATION_LATE_FIELDS` 过滤默认值，导致默认分段策略也写进指纹文档；现改为「只有偏离默认值的字段进文档」，与其它 late field 同口径。`MultiHostSettings.fingerprint` 同时忽略未启用的软限额，避免多目标档位因新增字段改指纹。

延后清单（内置）保持不变：`role.calendar.plan`、`role.growth.progress`、`conversation.group.review`。私聊回复、记忆反思、日记写作与角色状态维护**永不延后**——前两者是产品本身，后两者是解释配额如何被用掉的维护通道（与 V1 豁免 `daily_review` 的理由一致）。硬上限仍然先于软限额判定，因此软限额只会减少可选工作，不会影响本体是否回应。

## 验证

- 软限额用例集中在 `tests/test_daily_token_soft_limit.py`（不再新建平行文件）：字段只有安装/角色两层（断言没有窗口层）、V1 默认值与边界、`is_deferrable` 只按 kind、策略拒绝无界声明、无存值时保留装配默认、存入后覆盖且非可选任务不受影响、角色层解析不落到安装层；本批追加 **7 项延后门用例**：命中的后台 kind 被延后、开关关闭与阈值 0 都不延后、前台与未列 kind 不受影响、延后被拒时**不产生任何预留与 held**、跨日与跨作用域用量不误判、安装账户达到阈值即延后、硬上限优先于软限额。
- 本批统一批跑 **171 项通过**：`test_astrbot_staging_config`、`test_daily_token_soft_limit`、`test_segmentation_host_settings`、`test_astrbot_staging`、`test_model_gateway`、`test_model_failures`、`test_model_replacement_routing`、`test_astrbot_staging_host`、`test_conversation_messages`、`test_tool_catalog`、`test_role_tool_loop`。
- 既有失败未触碰：`test_busy_reply_gate` 的宿主延迟接线（`flow.accept(defer_seconds=...)` 尚未接线，文件内已注明）、`test_role_cycle_variation` 的 `phase_expression` 投影、`test_expression_style` 的轮换顺序用例。

## 边界与后续

- **硬上限 `daily_token_limit` 未做成配置字段**：`model_budget_accounts` 的 `token_limit` 在首次预留时按 `policy_hash` 固化，当天改值会让既有账户报 `model_budget_policy_changed`（这是「需要显式迁移」的既有设计，不是缺陷）。要让它可配，必须同时定义「变更日如何处理既有账户」的迁移语义，属于需要单独决策的改动；本片只把已存在、且天然安全的软限额接通。
- 未接小屋页面；未调用真实模型；未重载在线插件；未构建交付包。
