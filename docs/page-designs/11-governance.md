# 10 · 自我（`manage/governance`，E 段）

代码位置：`renderGovernance`（`pages/陪伴小屋/app.js:1167-1172`）。

## 一、页面功能

"角色是谁、权限怎么分、模型怎么指、资源花多少"的**导航与状态页**。本页自身只持一个小组（每日预算），其余分区是跳转。

## 二、展示与配置（四个分区）

| 分区 | 内容 | 性质 |
| --- | --- | --- |
| 关系与权限 | `renderIdentity()`：identity 工作区（相识目录与逐人授权），内部身份标识不展示 | 只读展示 + 跳转 → [05-identity-relationships.md](05-identity-relationships.md) |
| 模型分配 | 跳转卡「任务模型路由 → models 页」："和模型与连接页是同一份设置，改一处两边同步"（`app.js:1169`） | 跳转 |
| 资源与预算 | 挂载头「每日软限额：只决定可选的后台工作是否开始；达到限额后当天不再开始新的可选任务，已经在跑的会走完；交互回复不受它影响」（`app.js:1170`） | **`model.budget` 2 项** |
| 存储与部署 | 两张跳转卡：宿主运行状态 → host 页；资料与维护 → data 页（`app.js:1171`） | 跳转 |

### `model.budget`（每日 Token 软限额）— 2 项，installation+role，立即生效，通道 `/config`

| 字段 | 含义 |
| --- | --- |
| `enable_daily_token_soft_limit` | 启用每日软限额 |
| `daily_token_soft_limit` | 每日软限额（token） |

挂载 `configEditors('budgetConfigWorkspace',['budget'])`（`app.js:1170`，挂载点 `:1249`）。后端 `model_gateway/budget.py:40-42` → budget.py 软预算消费；`GroupEditor` 为 `ModelBudgetManagement`（`configuration_api.py` SECTIONS）。

## 三、边界与空态

- 本页**不持有** `role.state`（在决策 B3）、不持有身份/授权写入（在宿主与对象访问策略）、不持有存储备份（在资料与维护）。
- E3 内容风控：当前页面上**没有**风控分区（旧版 boundaryCard 已按"接不上就删"处理；风控护栏开关实际在表达 D1 的 `framework_error_guard_enabled`、群三条闸等，见 [10-expression.md](10-expression.md)）。
- 用量与余额没有聚合查询接口，本页无任何用量展示，不画费用曲线。

## 四、后端情况

本页只触达 `/config?sections=budget`（读）与 `POST /config/configure`（写）。预算在 `model_gateway` 内部被各任务消费。

## 五、相关设计稿与复核

- 身份与权限 → [05-identity-relationships.md](05-identity-relationships.md)；模型路由 → [14-models.md](14-models.md)；宿主与备份 → [18-host.md](18-host.md)、[19-data.md](19-data.md)。
- 复核：`sed -n '1167,1172p' pages/陪伴小屋/app.js`。
