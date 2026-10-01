# 群成图安全审核与私聊回退切片（2026-09-27）

依据 [V2 缺口补全任务清单](V2_GAP_CLOSING_TASKS_20260927.md) T09。迁移 V1 `photo_action_config` 的 8 项群成图审核配置（`enable_group_nsfw_private_fallback` + `group_nsfw_image_review_*`），在 V2 框架约定下改造实现：审核在 V2 端、产物链沿用既有 owner，失败按配置阻止发群或降级到请求者自己的私聊。

用户批注（本轮）：私聊回退本批一起做（选项 B）。

## V1 语义与 V2 改造点

- 八个配置项名称与取值域对齐 V1：开关（默认关闭）、审核模式 `single/dual`、严格度 `relaxed/balanced/strict`、最低置信度 0–1（默认 0.7）、单次超时秒数 3–30（默认 8）、审核图片最长边 0–4096（默认 1280，0 表示不缩放）、失败处理 `private/block`（默认 private）、审核补充规则（≤1200 字）。
- V1 的开关语义原样保留：**关闭时不审核，群图直接发群**；开启后只有"确实跑过、且结论是 safe"的图才可能进群。
- 三条 V2 改造：
  1. **V1 在发送前临时调用识图模型并临时保存缩放副本**；V2 把审核做成受监督的后台任务（`conversation.image_review` 任务类型 + 模型计划档位 `image_review`），结论先落库、投递再读，因此重启后不需要重跑审核，也不会重复计费。
  2. **V1 的"改发私聊"是在同一个群任务里换目标发送**；V2 的投递信封按原始受众密封（`ImageDeliveryEnvelope` 要求 `context.audience` 就是当前群），框架内没有"群任务改发私聊"的通道。本片改为：群侧只发文字（图片项被扣除），图片走**独立的私聊投递请求**——不同受众、不同授权、不同回执。
  3. **V1 的失败处理只区分"审核没做完"**；V2 明确成三值决策：`allow_image`（进群）、`withhold_image`（不进群，图片转私聊）、`block`（不进群，也不转私聊）。`uncertain`/不可用按 `failure_action` 决定后两者，明确违规一律 `withhold_image`。

## 决策与治理

- **私聊通道必须显式且当前有效**。只有当同一个账号下该成员本身已经是一个已配置的**私聊 target**、且该 target 有当前生效的私聊投递授权时，回退才成立；否则原群投递保持阻止（`image_review_fallback_unauthorized`），不会退化成广播，也不会把群受众复用成私聊受众。宿主端口为 `astrbot_host/multi_session.py` 的 `ReviewFallbackRoutes`。
- **回退目标与产物在排队时冻结**，写进审核投递记录；每次读取都重新解析当前授权并比对，因此撤权、目标变更、成员权限变化都会让整条投递按既有来源依赖复核失败。
- **不新增表、不升 schema**：判定与替换记录写进既有 `runtime_metadata`（与 `sources/privacy.py`、`expression/style_service.py`、`proactive/news_events.py` 等 V2 持久值同一机制），键前缀 `conversation.image_review.v1:`、`conversation.image_review.delivery.v1:`、`conversation.image_review.fallback.v1:`。因此本片对既有数据根是**纯增量**：没有判定记录的数据根行为与改动前完全一致。
- **不复制像素**：判定只保存"这一段回复当时密封的那份 manifest"，不保存图片字节。撤回或撤权后，私聊回退读原件同样失败，判定记录无法让失效产物复活。
- **不改密封数据**：群侧那一段的 `conversation_parts` 行、`payload_hash`、批次 manifest 一律不动。被扣图的投递使用一个**记录在案的替换哈希**，`conversation_delivery_receipts` 用它核对回执——回执仍然证明"发出去的正是审核决定的那一份"，而不是事后被改写的内容。
- **审核未决则挂起投递**：`flow._advance_one` 在待发分段存在未决审核时推迟本批次（`reason=image_review_pending`），审核任务完成即唤醒；批次因此既不会抢跑，也不会被 halt 成失败。

## 文件归属

| 文件 | 职责 |
| --- | --- |
| [conversation/media/review.py](../companion_v2/conversation/media/review.py) | 配置字段与校验、标签归一、提示词、判定文档校验、三值决策、判定/替换/回退台账 |
| [conversation/media/review_service.py](../companion_v2/conversation/media/review_service.py) | 审核任务类型与执行：从受治理的 blob 读原件、按模式调用视觉档位、落判定 |
| [conversation/media/fallback.py](../companion_v2/conversation/media/fallback.py) | 私聊回退的排队、目标解析与逐次复核、投递 owner 的读取合同 |
| [conversation/delivery.py](../companion_v2/conversation/delivery.py) | 群出站闸门：待审挂起、扣图发送、回执哈希核对、回执后排队回退 |
| [conversation/flow.py](../companion_v2/conversation/flow.py) | 审核未决时的批次推迟 |
| [conversation/generation.py](../companion_v2/conversation/generation.py) | 成稿时按同一事务登记待审分段 |
| [host/application.py](../companion_v2/host/application.py) | 组装：字段注册、owner、审核任务注册、投递 owner、后台规划器、生命周期 |
| [astrbot_host/multi_session.py](../astrbot_host/multi_session.py) | 审核档位注册与 `ReviewFallbackRoutes` 宿主端口 |

## 验证

- 新增 `tests/test_group_image_review.py` **18 项通过**（AstrBot 自带 Python）：配置注册合同与默认值、区间按声明生效、字段类型声明、标签归一（不安全表述不会被读成 safe）、结构化置信度解析、双模型取更严标签与更低置信度、严格度与补充规则进提示词、关闭开关是唯一"未审核进群"路径、只有 confident safe 进群、不可用按配置分派、判定文档合法/损坏用例、以及台账的待审发现、已判状态、单段单替换、未审段无记录。
- 受影响域统一回归 **196 项通过**：本片 18 项加 `test_conversation_messages`、`test_host_application`、`test_image_quota`、`test_conversation_image_delivery`、`test_generated_image_sources`、`test_generated_image_adoption`、`test_generated_image_continuation`、`test_storage_migrations`、`test_state_storage_migrations`、`test_group_member_safety`、`test_configuration`、`test_configuration_storage`、`test_group_safety_guards`、`test_reply_text_processing`。
- 另跑 `test_group_media`、`test_group_conversation_context`、`test_group_image_delivery`、`test_group_image_delivery_governance` 共 56 项，其中 2 项失败（见下）。
- `python -m compileall companion_v2 astrbot_host tests` 通过；全部 `.py` 与 `docs/*.md` 通过 UTF-8/无 BOM/LF/末尾换行检查（唯一命中 `docs/V1_CONFIG_TAXONOMY_20260925.md` 缺末尾换行，为本批之前的既有文件）。

## 本轮顺带修掉的既有缺陷

1. **`multi_controller.preview` 打不开预览**：`preview()` 给 `reply_images.project_parts` 的分段行缺少 `part_id`，而 `read_binding` 按 `part_id` 归位图片 → `KeyError: 'part_id'`，被 `_failure` 包成 `host_control_failed`。已把 `part_id` 加进 SELECT，群图预览恢复（`test_group_image_delivery` 3 项由 error 转通过）。
2. **存储迁移 v40→v41 守卫在 v41 成为当前版本后误判**：`_initialize_schema` 里 `"... or group_member_safety_hits in existing_tables"` 是为"当前版本 = v41"写的；v41 落地为当前版本后，任何"先同步到 v41、再退回 v40 再打开"的用例都会走进 `_migrate_v40_to_v41` 并对已存在的表执行 `CREATE TABLE` → `StorageOpenError`。该守卫已改为只判 v40 必需表缺失（迁移是纯增量，降级副本不该被当成半完成升级），并给 `tests/execution_support.py` 补上 `remove_v41` 让历史夹具走真正的降级链。修复前 38 项中 14 项 error，修复后全绿。

## 边界与后续

- 未接小程序/页面：审核留据、替换记录与回退状态的展示随第②阶段统一接入「陪伴小屋」。
- 未跑真实视觉模型、未发送真实 QQ 消息、未重载在线插件、未构建交付包。
- 两份既有失败与本片无关（用"仅关闭审核闸门、其余改动保留"的对照复验确认改动前即失败）：`test_group_media.test_known_member_quote_links_original_and_withdrawal_stops_derivatives` 与 `test_group_conversation_context.test_members_keep_speaker_attribution_and_do_not_gain_raw_source_access`。
- 本批未把 `review_provider` / `review_dual_provider` 做成页面可编辑控件（字段已注册、有默认值与校验），页面接入同第②阶段。
