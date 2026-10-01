# V2 功能与配置盘点（2026-09-28）

供审核用的现状清单。数据由脚本从代码库直接抽取，不是手工整理的。

**重新生成**：

```
python3 tools/build_v2_inventory.py        # 配置与路由
python3 tools/resolve_ledger_landings.py   # V1 账本落点回查
```

---

## 〇、这一版修正了什么

前两版的「320 个配置项」是错的，错在抽取器，不在代码。两个原因：

1. **按文件名找 provider。** 抽取器只认 `*.configuration.py`，但全库 25 个
   `configuration_fields()` 里有 9 个按「配置什么」命名，不按「注册表」命名——
   `reply_settings.py`、`participation.py`、`busy_gate.py`、`perception_settings.py`、
   `recall_settings.py`、`media/quota.py`、`media/review.py`、`content/authoring_service.py`、
   `model_gateway/budget.py`。
2. **跳过带参工厂。** `reply_configuration_fields(segmentation, streaming, gap, voice)` 和
   `routing_configuration_fields(profiles)` 需要参数才出字段，抽取器直接跳过了。
   `routing` 一家就是 **120 个**字段（15 个模型任务 × 8 项）。

修正后 **604**，不是 320。现在的抽取器按 `def configuration_fields` 全树发现，
两个带参工厂用生产环境同样的参数调用，并且**断言「磁盘上每个 provider 都被收进来了」**——
漏一个就报错退出，不再静默少算。

| | 前版 | 本版 |
|---|---:|---:|
| 注册表字段 | 320 | **604** |
| 插件配置叶子 | 未计 | **81** |
| 配置总面 | 320 | **685** |

## 一、总览

| 面 | 数量 | 来源 |
|---|---|---|
| 注册表字段 | 604 | 25 个 `configuration_fields()` 的并集 |
| 插件配置叶子 | 81 | `_conf_schema.json` |
| 配置总面 | 685 | 上两项之和（两套独立机制，见下） |
| HTTP 路由 | 71 | `astrbot_host/*.py` 的路由声明 |
| 存储表 | 30 | `companion_v2/storage/` 的建表语句 |
| V1 迁移来源 | 9 | `companion_v2/legacy/catalog.py` |
| V1 配置键判定 | 1010 | `docs/V1_V2_CONFIG_VERIFIED_20260927.csv` |
| 导航入口 | 17（4 组） | `pages/陪伴小屋/app.js` 的 `navGroups` |

### 两套配置机制不能合并成一张表

**注册表**（604）按 `installation → role → window` 分层，有种类、生效时机、
owner/consumer，运行时经配置服务读回。
**插件配置**（81）是 AstrBot 安装级设置，由 AstrBot 自己读，分 8 组：
`voice_reply` 20、`runtime` 16、`model` 13、`segmentation` 11、`multi_host` 8、
`target` 6、`poke` 4、`staging` 3。

同一件事常常两边都有（比如模型 provider 在 `model.*` 也在注册表里按任务分）。
**界面上要说清一个开关属于哪套机制**，否则用户改了一处以为改了两处。

## 二、配置项覆盖（注册表 604）

「已接」= 页面源码里以字段名或动态族形式出现。动态族（`"cycle_"+key+"_days"`）
已计入覆盖，这是手工 grep 最容易误判的一类。

| 状态 | 数量 |
|---|---:|
| 已接 | 443 |
| 待接 | 151 |
| 有意不接 | 10 |
| **合计** | **604** |

三类互斥，合计正好 604（构建脚本对此有断言）。
`cycle_*_mood` 六项在动态族正则里（只匹配 `_days`/`_energy`/`_prompt`）本就不命中，
所以「有意不接」优先的规则不会吃掉任何「已接」计数。

### 待接 151 项的分布

集中在两个分组，其余 35 个分组全是 0：

| 分组 | 待接 | 说明 |
|---|---:|---|
| `proactive.contact` | 92 | 主动与联系（14 个语义桶） |
| `conversation.presentation` | 54 | 回复呈现 + 群节奏 |
| `content.authoring` | 5 | 创作草稿/复核 |

**注意 `model.*` 全部已接**——15 个任务 × 8 项（provider / fallback / prompt /
max_output_tokens / replacement_rules / fallback_on_refusal / timeout_seconds /
replacement_scope）= 120 项都已有控件。我前版说「120 项待接」是错的，
那是我在旧口径下把 `routing` 整个漏掉时的推测，不是实测。

真正没接的是 `conversation.presentation` 那 54 项群节奏字段——
V1 叫「群唤醒增强」，V2 拆成了 `group_wakeup_*` / `group_air_guard_*` /
`group_safety_*` 三族。

### 有意不接（不是未做）

`role.state` 这 10 项在第 17 轮定过：

| 字段 | 理由 |
|---|---|
| `cycle_*_mood`（6 项） | 默认「疲惫/轻快/敏感」已够用。**但它们仍必须在页面的 `definitions` 里声明后端真正用的 80 字上限**——闭包检查会读它们。 |
| `mood_cross_window` | 跨窗口共享，与其它心情参数高度耦合，操作员调不明白。 |
| `mood_interest_window_minutes` | 同上。 |
| `mood_neutral_band` | 同上。 |
| `online_status_enabled` | **保存时会撤销对应 grant**（`configuration.py` 末尾的 `identity.revoke_grant`），与授权流程耦合，不能当普通开关平铺。 |

## 三、V1 配置键判定（权威账本）

| 判定 | 数量 | 占比 |
|---|---:|---:|
| renamed-equivalent | 317 | 31.4% |
| not-migrated-by-design | 316 | 31.3% |
| implemented-elsewhere | 168 | 16.6% |
| already-in-v2 | 156 | 15.4% |
| owed | 29 | 2.9% |
| not-applicable | 24 | 2.4% |

### 落点回查（新增）

账本只有 100 行填了 `v2_field`，其余是散文。散文没法比较、没法迁移，
所以 `tools/resolve_ledger_landings.py` 把每行的 `verified_landing` 降到具体落点：

| 落点类型 | 数量 | 占比 | 含义 |
|---|---:|---:|---|
| `registry` | 380 | 37.6% | 指向注册表真字段（310 个不同字段） |
| `external` | 366 | 36.2% | 落在别的插件／模块／文件 |
| `unresolved` | 196 | 19.4% | **抽不出落点，需要人工** |
| `plugin-config` | 68 | 6.7% | 指向 `_conf_schema.json` 叶子 |

按判定 × 落点交叉：

| 判定 | registry | external | unresolved | plugin-config |
|---|---:|---:|---:|---:|
| renamed-equivalent | 229 | 26 | 25 | 37 |
| not-migrated-by-design | 12 | 210 | 90 | 4 |
| implemented-elsewhere | 16 | 85 | 60 | 7 |
| already-in-v2 | 122 | 17 | 0 | 17 |
| owed | 0 | 17 | 9 | 3 |
| not-applicable | 1 | 11 | 12 | 0 |

**196 行 `unresolved` 里，`not-migrated-by-design` 占 90、`implemented-elsewhere` 占 60。**
也就是说未定位的绝大多数本来就是「不打算迁」或「在别处实现了」——
它们对迁移不构成阻塞。真正要盯的是欠账行（见下）。

`v2_field` 与 landing 指向不一致：**0 行**——已填的 100 行没有自相矛盾。

**两个 `owed` 不要混淆**（我自己上一版就混了）：

| 字段 | 含义 | 数量 | 其中未定位 |
|---|---|---:|---:|
| `disposition = owed` | 记账口径：还没销号 | 107 | 20 |
| `verified_verdict = owed` | 判定口径：确实欠着 | 29 | 9 |

`disposition` 的三个值是 `recorded-other` 873、`decided-not-migrated` 30、`owed` 107。

### 迁移真正卡住的 20 行

这 20 行**既是欠账、又定位不到落点**，是唯一会阻塞迁移的部分。它们聚成三个问题：

| V1 分组 | 行数 | 账本写的落点 | 问题 |
|---|---:|---|---|
| `weather_config` | 12 | 8 行 landing 完全为空；`weather_lat/lon` 指向 `planning_weather_location.*`；预警指向 `proactive.official_alert_*` | 落点空缺最多 |
| `web_exploration_config` | 3 | `news.search_url` / `news.auth` / `proactive.compose` | **`news.*` 分组在注册表里不存在** |
| `model_assignment_config` | 2 | `time_window.start` / `time_window.timezone` | `time_window.*` 不存在 |
| `photo_action_config` | 2 | `preparation.retention_days` / `preparation.max_storage_mb` | `preparation.*` 不存在 |
| `basic_config` | 1 | `conversation.perception` | 组名没写成字段名 |

20 行里 **8 行 landing 完全空白、12 行候选 token 定位不到**。

**关键发现**：账本里有 `news.*`、`time_window.*`、`preparation.*`、
`planning_weather_location.*` 这些前缀，**604 个注册表字段里一个都没有匹配**。
说明账本写作时用了一套 V2 规划期的命名，那套命名后来没有落地（或被改成别的组名）。
这 20 行必须人工定夺：要么现在补注册表字段，要么改判 `not-migrated-by-design`。

### 解读：为什么账本和清单对不上

账本的主键是 **V1 键**（1010 行），清单的主键是 **V2 字段**（604 + 81）。
两者是多对一，且账本写的时候还没有完整注册表（`conversation.presentation.*`
在账本里出现时，注册表抽取器还漏着这一家）。

要点：**380 行指向 310 个注册表字段，意味着 604 个注册表字段里有 294 个
从来没被任何 V1 键指过**——它们是 V2 新增的能力，不是从 V1 迁来的。
迁移时这 294 个的安全默认值只能来自 V2 自己的 schema default，不能从 V1 推。

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

## 五、发现的代码问题

`companion_v2/memory/episode_settings.py` 和 `companion_v2/memory/configuration.py`
把同样 4 个字段各注册了一遍（`group_episode_memory_enabled`、
`group_episode_refresh_minutes`、`group_episode_min_messages`、`max_group_episodes`），
默认值一致（`True / 180 / 12 / 10`）。构建脚本会打印 `DUPLICATE` 提示，不当计数错误。
**两处默认值一旦改动不一致，就会出现「改了不生效」**——建议合并到一处。

## 六、下一步

1. **定夺那 20 行欠账**（见三节末）。`weather_config` 的 10 行最急——
   它们决定天气能力到底还做不做，做的话要补注册表字段。
2. **补 `conversation.presentation` 的 54 项群节奏控件**——它是最大的净缺口，
   且 V1 有对应的「群唤醒增强」页可参照。
3. **迁移仍只覆盖天气字段**——核心人格、工作/投递、世界资源转换器尚未实现；其余来源按目录的兼容读取、外部负责或暂缓处理。
   294 个「V1 没指过」的字段要用 schema default 初始化，不能从 V1 推。
4. **合并 `memory/episode_settings.py` 的重复注册**，避免两处默认值漂移。
5. **`news.*` / `time_window.*` / `preparation.*` 三套名字要么补进注册表，
   要么从账本里销号**——留着会让以后每次回查都重复踩一遍。
