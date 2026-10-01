# V1 配置项 → V2 实现进度（2026-09-27 逐项核对完成）

问题：V1 本体那一千多项配置，V2 实现了多少（不含优化改动项）。

方法（可复跑）：
1. `tools/audit_v1_config_coverage.py` —— 从 V1 `_conf_schema.json` 取键（**去掉 691 个 legacy 镜像**）、与真实装配后的 V2 字段注册表（468 项）按字段名末段匹配、并与迁移台账的处置列连接；
2. `tools/build_config_verification_shards.py` —— 把仍未定级的键切成 82 个分片（每片约 16 项，带 V1 类型/默认值/描述）；
3. 82 个只读核对员逐项定级（判定词表固定 6 个值，每条必须给 `文件:行` 级证据与置信度）；
4. `tools/merge_config_verification.py` —— 合并判定，产出 `docs/V1_V2_CONFIG_VERIFIED_20260927.csv`（1010 行，逐项可查）。

## 一、总量（去镜像后的准确基线）

| 项 | 数 |
| --- | --- |
| V1 schema 原始标量键 | 1701 |
| **其中 legacy 镜像（不算）** | **691** |
| **V1 独立配置键（分母）** | **1010** |
| V2 字段注册表 | 468 |
| **V2 字段里 V1 没有对应项的** | **316（67.5%）** |
| 迁移台账行数 | 1010（**与去镜像后的键数完全一致**） |

> **镜像是什么**：V1 把每个 `basic_config.x` 又作为顶层裸键 `x` 存了一份用于旧配置兼容。顶层 701 个裸键里 **691 个是这种镜像**，只有 **10 个**（`_command_photo_quota_semantics_version`、`model_timeout_overrides`、`page_theme`、`weather_alert_api_key` 等）有自己的语义。不去镜像会把分母虚增 68%。

## 二、核对结果（1010 项全部定级，0 项未核对）

| 判定 | 键数 | 占比 | 含义 |
| --- | --- | --- | --- |
| **已接入 V2（同名落点）** | **156** | 15.4% | 有对应字段且被生产代码读取 |
| **改名/换域后已在 V2** | **296** | 29.3% | 功能在，名字或归属域不同 |
| **落到别的机制** | **168** | 16.6% | 不再是配置项（身份解析、能力授权、宿主设置、schema 迁移） |
| **按设计不迁** | **252** | 25.0% | V1 专有、架构差异、宿主接管、已废弃 |
| **不是可迁移语义** | **24** | 2.4% | 遗留兼容项、迁移版本戳、内部状态戳 |
| **真欠账** | **114** | **11.3%** | V2 应当有但目前没有 |

**三个关键数字**：

- **功能已覆盖 V2：620 项（61.4%）** = 156 + 296 + 168
- **已交代清楚（含按设计不迁）：896 项（88.7%）** = 620 + 252 + 24
- **真欠账：114 项（11.3%）**

> **名字匹配器严重低估**：只看同名落点只有 100 项（9.9%），逐项核对后发现另有 **520 项**其实已在 V2——296 项被改名/换域（如 `proactive.*` 一个域吸收了 V1 多个组），168 项落到了别的机制。**所以"V1 配置只迁了十分之一"是错的，真实覆盖率是 61.4%。**

## 三、114 项真欠账分布（可据此排期）

| V1 组 | 欠账数 | 说明 |
| --- | --- | --- |
| `photo_action_config` | 25 | 图片动作链（相册/衣柜/参考图的细粒度策略）——与 E04「相册、衣柜与每日穿搭」同一片缺口 |
| `experimental_motivation_config` | 14 | V1 实验性动机/激励层，V2 用情绪四轴 + 主动权重替代，残留细项无处落 |
| `reading_archive_config` | 13 | 阅读归档 |
| `wardrobe_config` | 8 | 衣柜 |
| `group_high_intensity_config` | 7 | 群高强度场景 |
| `reactive_poke_config` | 7 | 戳一戳反应 |
| `voice_playback_config` | 6 | 语音播放 |
| `model_assignment_config` | 5 | 例：拒答词表、DeepSeek 峰值时段按关键词识别 provider |
| `relay_bridge_config` | 5 | 跨群 relay 桥接 |
| 其余 10 组 | 24 | `group_slang_topic_config` 4、`auto_voice_config` 4、`qzone_config` 3（QQ 空间本就不在 Content 责任内）等 |

置信度：**high 68 项、medium 46 项**（无 low）——高置信项可直接排期；medium 项需人工复核后再定。

## 四、口径提醒

1. **61.4% 是"能力有没有落点"，不是"配置项能不能一一对应"**。V2 有意重建配置面：468 个字段里 **316 个是 V1 没有的新能力**，同时欠账 114 项尚未补。
2. **252 项「按设计不迁」不是欠账**：V1 存储后端、独立 WebUI、单/多用户架构差异、AstrBot 宿主接管项——属你说的"不含优化改动项"。
3. **不要做配置面的一对一还原**：V2 每个字段必须有真实消费者（仓库硬约束），按 V1 键逐条补齐会灌进大量无人读取的字段。
4. **台账已可结项**：`V1_V2_CONFIG_PROGRESS_20260926.csv` 里 949 行停在「待逐项核对」，其结论已被本次逐项定级取代——建议以 `V1_V2_CONFIG_VERIFIED_20260927.csv` 为准。

## 五、复跑

```powershell
$env:PYTHONPATH = "C:\Users\99505\.astrbot\backend\app;<plugin-root>"
python -X utf8 tools\audit_v1_config_coverage.py        # 基线：去镜像 + 名字匹配 + 台账连接
python -X utf8 tools\build_config_verification_shards.py # 切分片（.verify-shards/）
# 82 个分片由核对员逐项定级，结果写 .verify-shards/out-shard-NNN.json
python -X utf8 tools\merge_config_verification.py        # 合并为 docs/V1_V2_CONFIG_VERIFIED_20260927.csv
```

