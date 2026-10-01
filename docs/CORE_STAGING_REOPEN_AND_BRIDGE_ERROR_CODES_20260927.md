# 模型页宿主连接与桥接错误码修复

日期：2026-09-27。现象是拓展页「陪伴小屋 / 模型与连接」提示「无法读取任务配置，请检查宿主连接」，同时管理页顶部堆叠「子类统计」与「E2 模型分配」边界卡，与页面自身页头重复。本切片记录三条根因与修复；全部改动已通过文末定向检查。

## 根因一：策略字段后加导致固定 profile 无法重开（连接问题主因）

插件启动时 `load_existing()` 只读重开固定 profile，`AstrBotStagingBootstrap._marker()` 校验库内 `astrbot-staging-bootstrap` 收据的 `parameter_hash` 与当前 `StagingConfiguration.fingerprint` 一致。后续分段切片给 `SegmentationPolicy` 新增了 `split_words`、`match_width_variants`、`rule_regex` 三个字段，`document()` 用 `asdict` 全量序列化，同一份 `staging-config.json` 的指纹从初始化时的 `776ab56d…` 漂移为 `bc46daa4…`，重开抛出 `staging_bootstrap_conflict`，整个 V2 会话不再装配——所有需要会话的页面 API（含 `/model`）一并失败。

修复在 `companion_v2/adapters/astrbot/staging_config.py`：指纹文档引入演化规则——**v1 之后新增的策略字段在其值仍等于 schema 默认值时省略**。默认值代表作者未表达过选择，不应改变指纹；一旦显式配置即产生新指纹（符合「配置变更即新 profile」的既有语义）。`_segmentation_document()` 落地该规则。

验证：对真实数据根 `profiles/qq-v2-stream-20260926`（当前 pinned profile），修复后指纹复现库内收据 `776ab56d…`；实时配置中三个后加字段均为默认值，probe 两侧文档一致。其余 `sender-*`、`preview-*` 等旧开发 profile 的收据是更早代码形状产生，且未被当前执行配置固定，再次使用时需按设计重新显式初始化。

## 根因二：仪表盘桥接丢弃错误码，页面映射永远落空

真实仪表盘的页面桥（`PluginPagePage` 前端）对 `status:"error"` 的 Outcome 信封执行 `throw new Error(envelope.message)`，只把 `message` 文本回传给页面，`data.code` 全部丢失；所有页面 JS 的 `errors[err.code]` 映射在生产桥接下永远落空，一律显示误导性的「请检查宿主连接」兜底文案。

修复两处：

- `astrbot_host/web_api.py` `outcome_response`：失败信封的 `message` 改为携带机器错误码（唯一能穿过桥接的通道），原始可读原因保留在新增的 `reason` 字段。
- `pages/陪伴小屋/models-page.js`：新增 `fail(err, fallback)` 助手，`errors[err.code] || errors[err.message] || fallback` 同时覆盖 mock 桥（resolve 错误信封）与真实桥（reject 并以 message 携带码）两种形态；补齐 `model_provider_changed`、`model_voice_provider_changed`、`model_request_invalid`、`staging_profile_conflict` 的中文文案；Provider 探测失败回退同样读取 `err.message`。

合同测试 `tests/test_models_page.cjs` 新增「真实桥接以 Error.message 携带码」用例。其余工作区页面的同类映射待统一接入（见 BUILD_STATUS 后续项）。

## 根因三：管理页外壳在模型页堆叠冗余说明

`renderModelsPage()` 原先套用 `consoleSections`，生成「子类 1/已接入 1/…」统计块与「E2 模型分配」边界卡，而模型页自身已有页头、三页签与刷新控件，首屏被重复说明占据。修复后只保留分区卡片容器（`#modelWorkspace.console-section` + 自身 padding），移除统计与边界卡；「治理与维护」页的 E2 边界卡（含跳转）不受影响。

## 定向检查

- `node --test tests/test_models_page.cjs`：23 项通过（含新增桥接拒绝用例）。
- `tests.test_page_targets_api`、`tests.test_astrbot_staging_config`、`tests.test_astrbot_staging_bootstrap`：35 项通过。
- `tests.test_memory_host_api`、`tests.test_reply_web_api`、`tests.test_perception_host_api`：16 项通过（信封字段变更回归）。
- `tests.test_astrbot_staging_host`：50 项通过（含 fingerprint 跨 profile 一致性）。
- `tools/sync_framework_page.py` 重新生成清单后 `--check` 干净，65 项哈希逐一核对一致；`index.html` 对 `models-page.js/css`、`app.js`、`workspace-bundle.js` 的缓存版本统一升至 `model-bridge-fix-20260927`。

已构建的 2.0.0 交付包不含以上修复；插件重载后固定 profile 将自动只读重开，模型页即恢复读写。真实 Provider / QQ 现场验收仍按统一顺序另行安排。
