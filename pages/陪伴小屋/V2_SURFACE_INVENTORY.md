# V2 功能与配置盘点（2026-09-28）

供审核用的现状清单。数据由脚本从代码库直接抽取，不是手工整理的。

**重新生成**：`python3 tools/build_v2_inventory.py`（脚本见文末说明）。

---

## 一、总览

**正式运行口径（2026-10-01）**：V2 的正式投递固定使用 `onebot_private`，不再提供正式的
`preview`/草稿投递模式，也不要求另行申请一份投递授权。旧配置里的 `delivery_mode: preview`
只在读取时归一化为 `onebot_private`，不会把历史档案重新解释成当前可选模式。真实发送仍受已绑定
的账号、平台、私聊对象、人格、按人权限和 admission 检查约束；模型参数变化不会使固定运行实例
失去连接资格。

| 面 | 数量 | 来源 |
|---|---|---|
| 已注册配置项 | 320 | 各 `configuration.py` 的 `configuration_fields()` |
| HTTP 路由 | 71 | `astrbot_host/*.py` 的路由声明 |
| 存储表 | 30 | `companion_v2/storage/` 的建表语句 |
| V1 迁移来源 | 9 | `companion_v2/legacy/catalog.py` |
| V1 配置键判定 | 1010 | `docs/V1_V2_CONFIG_VERIFIED_20260927.csv` |
| 导航入口 | 17（4 组） | `pages/陪伴小屋/app.js` 的 `navGroups` |

## 二、配置项覆盖

「已接」= 页面源码里以字段名或动态族形式出现。动态族（`"cycle_"+key+"_days"`）
已计入覆盖，这是手工 grep 最容易误判的一类。

**更新（2026-09-30）**：`cycle_*_mood` 六项现已在正式状态页配置表单中接入，并由浏览器验收覆盖保存和回读；旧的「有意不接」结论已过期。
两者不能都算，本表让「有意不接」优先，否则合计加不平。

| 分组 | 已接 | 待接 | 有意不接 | 合计 | 生效层 | 生效时机 |
|---|---:|---:|---:|---:|---|---|
| `proactive.contact` | 66 | 92 | 0 | 158 | installation/role/relationship/window | immediate |
| `role.state` | 51 | 0 | 10 | 61 | window | immediate |
| `memory` | 30 | 0 | 0 | 30 | installation/role/window | immediate |
| `role.life` | 23 | 0 | 0 | 23 | window/role | immediate |
| `knowledge` | 14 | 0 | 0 | 14 | installation/role/window | immediate |
| `library` | 12 | 0 | 0 | 12 | role | next_task |
| `expression.learning` | 10 | 0 | 0 | 10 | window | immediate |
| `role.growth` | 4 | 0 | 0 | 4 | window | immediate |
| `photo.reference` | 4 | 0 | 0 | 4 | role | next_task |
| `screen` | 3 | 0 | 0 | 3 | window | next_task |
| `person` | 2 | 0 | 0 | 2 | installation/role/window | immediate |
| **合计** | **218** | **92** | **10** | **320** | | |

净缺口 **92** 项，全在 `proactive.contact`（主动与联系页）。

另有 `role.state` 的 10 项**有意不接**——不是未做，见下。三类互斥且合计 320：
已接 218 + 待接 92 + 有意不接 10。

### 有意不接（不是未做）

`role.state` 这 10 项在第 17 轮定过：

| 字段 | 理由 |
|---|---|
| `cycle_*_mood`（6 项） | 周期设置表单已提供各阶段氛围词输入，最多 80 字；与该阶段能量偏移、表达引导一起保存。 |
| `mood_cross_window` | 跨窗口共享，与其它心情参数高度耦合，操作员调不明白。 |
| `mood_interest_window_minutes` | 同上。 |
| `mood_neutral_band` | 同上。 |
| `online_status_enabled` | **保存时会撤销对应 grant**（`configuration.py` 末尾的 `identity.revoke_grant`），与授权流程耦合，不能当普通开关平铺。 |

### `proactive.contact` 的 92 项缺口，按语义分 14 桶

| 桶 | 数量 | 归属页 | 消费端证据 |
|---|---:|---|---|
| 强度与节奏 | 16 | 主动与联系 | `proactive/configuration.py` |
| 问候与作息 | 10 | 主动与联系 | 同上 |
| 外部资讯与预警 | 10 | 主动与联系 | `proactive/configuration.py`（`news_daily_hot_read_enabled` 等） |
| 余额感知 | 9 | 主动与联系 | `proactive/balance_events.py:69` |
| 去重与抑制 | 8 | 主动与联系 | `proactive/configuration.py` |
| 屏幕与设备 | 8 | 主动与联系 | `proactive/screen_events.py:117` |
| 动作类联系 | 6 | 主动与联系 | `proactive/configuration.py` |
| 纪念日 | 4 | 主动与联系 | 同上 |
| 配额与上下文 | 4 | 主动与联系 | 同上 |
| 三餐 | 4 | 主动与联系 | 同上 |
| 天气 | 4 | 主动与联系 | `proactive/weather_events.py:48` |
| 约会预约 | 3 | 主动与联系 | `proactive/configuration.py` |
| 事件自关联 | 3 | 主动与联系 | 同上 |
| 未回应降速 | 3 | 主动与联系 | 同上 |

**一个必须纠正的判断。** 我最初打算把「天气」「外部资讯与预警」「余额」「屏幕与设备」
这 31 项划给感知页——因为名字听起来像「角色能看到的信息」。查消费端之后推翻了：

它们全部由 `companion_v2/proactive/` 消费，是**主动联系的触发事件源**
（`balance_events.py` 判余额、`weather_events.py` 判天气、`screen_events.py` 判屏幕），
不是感知的输入通道。**归属仍是主动与联系页**，92 项都在这一页。

感知页确实也有天气与新闻端口（`perception-native-page.js`），但那是**环境信息注入**，
与这里的「什么时候因为天气去说一句话」是两回事。同一份数据、两个用途、两个页面，
页面上要能看出区别，否则用户会以为改一处等于改两处。

## 三、V1 配置键判定（权威账本）

| 判定 | 数量 | 占比 |
|---|---:|---:|
| renamed-equivalent | 317 | 31.4% |
| not-migrated-by-design | 316 | 31.3% |
| implemented-elsewhere | 168 | 16.6% |
| already-in-v2 | 156 | 15.4% |
| owed | 29 | 2.9% |
| not-applicable | 24 | 2.4% |

`disposition = owed` 的 107 行，按 V1 分组：

- `balance_awareness_config` — 18 项
- `weather_config` — 18 项
- `photo_action_config` — 12 项
- `web_exploration_config` — 11 项
- `basic_config` — 10 项
- `news_config` — 10 项
- `qzone_config` — 6 项
- `experimental_motivation_config` — 6 项
- `reading_archive_config` — 5 项
- `model_assignment_config` — 4 项
- `bilibili_config` — 3 项
- `group_slang_topic_config` — 3 项
- `weather_alert_api_key` — 1 项

**与缺口的对应关系**：`balance_awareness_config`(18) + `weather_config`(18) +
`news_config`(10) + `web_exploration_config`(11) + `experimental_motivation_config`(6) = 63 项，
是主动页那 92 项缺口在 V1 侧的来源。`photo_action_config`(12) 属于行动页。

## 四、V1 → V2 数据迁移来源

`companion_v2/legacy/catalog.py` 声明的 9 条来源。当前只有 `private.host_configuration` 的天气
字段转换器真正接入；核心人格、工作/投递和世界资源仍只有目录记录，没有自动转换器。

| 来源 | 处置 | handler（未实现） | V1 路径 |
|---|---|---|---|
| `private.host_configuration` | converted（仅天气字段） | `v2.private-config-converter` | `host-config:astrbot_plugin_private_companion` |
| `private.core_profiles` | no_handler | `v2.private-core-converter` | `companions.json; persona_profiles` |
| `memory.timeline_and_governance` | compat_readable | `v2.memory-snapshot-adapter` | `memory_companion.db` |
| `private.work_and_delivery` | no_handler | `v2.work-delivery-converter` | `framework_work/work.db; framework_work/delivery.db` |
| `private.world_assets` | no_handler | `v2.world-asset-converter` | `framework_world/album.db; framework_world/resources` |
| `content.creative_projects` | retained_external | `v2.content-owner-adapter` | `creative_state.json` |
| `image.generation_state` | retained_external | `v2.image-owner-adapter` | `image_generation_state.json` |
| `reality.device_and_observations` | retained_external | `v2.reality-owner-adapter` | `reality_companion.json; device-side-material` |
| `extensions.session_and_media` | held | `v2.extension-owner-inventory` | `together; live; game; extension-owned-media` |

处置含义：`converted` 会转成 V2 结构；当前只覆盖宿主配置中的天气字段；`no_handler` 只做发现并明确告知暂缺转换器；`compat_readable` 保持可读；
`retained_external` 留给对应插件；`held` 暂缓。

迁移是只读探测、试算、再写入 V2 的单向流程。V1 原目录不会被修改；记忆、Content、Image、
Reality 和扩展数据按兼容读取、对应插件负责或暂缓处理，不会被 V2 偷拷贝成第二份正本。

## 五、下一步

1. **先补感知页**（31 项）：天气、外部资讯与预警、余额、屏幕与设备。这四处已有端口，只是没有控件。
2. **再做主动页**（61 项）：强度与节奏、去重、问候、三餐、纪念日、动作、预约、自关联、降速。
3. 补齐核心人格、工作/投递、世界资源转换器；在此之前只能迁移天气字段，其他来源必须显示为无转换器或外部负责。
