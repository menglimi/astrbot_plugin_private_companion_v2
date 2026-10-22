# 模型页配置体验：现状核查与重设计方案（2026-10-19）

范围：公开拓展页「陪伴小屋」的「模型与连接」页（`pages/陪伴小屋/models-page.js`，约 1800 行）
与其宿主接口（`astrbot_host/model_api.py`、`astrbot_host/model_settings.py`）。

本轮只做**核查与设计**，没有改运行代码。

## 一、现状核查（读代码得出，附行号）

| 维度 | 现状 | 证据 |
| --- | --- | --- |
| 作用域层 | 只有 `role`（角色默认）/ `window`（当前私聊微调）两层；**没有群聊层** | `model_api.py:371` `if layer not in ("role", "window")`；页面开关 `models-page.js:244` |
| 层默认值 | 后端默认 `role`，页面 pending patch 默认 `window` | `model_api.py:403`、`models-page.js:128` |
| TTS 提供商字段 | **已按 provider 分组声明**：`api_base`/`api_key`/`proxy`/`timeout`/`appid`/`minimax-group-id` 归一组，元数据来自 `CONFIG_METADATA_2.provider_group` | `model_api.py:96,100-102,241,933,1041` |
| 生图提供商字段 | 仍是「草稿 + 基线条 + 文本」三件套自由编辑（`configDraft`/`configBase`/`configText`），provider 专属参数靠文本表达 | `models-page.js` 的 `image` 子状态、`imageConfigDirty` |
| 生图方式 | 只有两种：`文生图(generate)` / `改图(edit, image.edit + image.mask_edit)` | `models-page.js:990` `IMAGE_VIEWS` |
| 生图本地 provider | 只认 `comfyui` / `sd_webui` | `models-page.js:992` `IMAGE_LOCAL_LABELS` |
| 折叠状态 | 只有内存态 `state.expOpen`（全页 5 处引用），刷新即丢 | `models-page.js:1807` |

**结论**：任务维度（fn/voice/image/search/laya）已齐；**作用域缺群聊层（后端限制）**、**生图 provider 缺 schema 驱动**、**方式维度只有两档**、**展开状态无记忆**。

## 二、重设计方案（四块）

### 1. 展开策略：三段式卡片 + 记忆（纯前端）

每个任务固定三段，默认只展开第 ① 段：

1. **当前生效**：一行摘要（服务 / 模型 / 作用域 / 来源：继承还是单独设置）
2. **服务与连接**：provider、端点、密钥引用、测试按钮
3. **生成参数**：按 provider 与方式切换的字段组

折叠状态按 `task + section` 存 localStorage，刷新与切任务后保持；「全部收起」作为页头操作。

### 2. 私聊 / 群聊 / 角色三层（**依赖后端**）

目标：作用域开关从两项扩到 `角色默认 / 私聊微调 / 群聊微调`，每项显示“已覆盖 N 项”。

**阻塞点**：`model_api.py:371` 只接受 `role|window`。要做群聊层必须先补后端合同：
窗口层的 scope 来自当前会话，群聊需要一个新的 `layer="group"`（或 `window` + 群会话 scope）与相应的 patch 校验、授权与审计。这是一次跨 `model_api` + `configuration` 的改动，不是 UI 工作量。

建议：先按“只有私聊”发布，把层做成可扩展的三项占位（群聊项显示“即将支持”），等后端补完再打开。

### 3. 提供商专属配置：复用 TTS 的 schema 模式（半天~一天）

TTS 已经有 `_tts_field_group()` + `CONFIG_METADATA_2.provider_group` 这套“按 provider 声明字段组”的做法，生图照搬即可：

- **ComfyUI**：工作流 JSON、节点映射、分辨率/步数、超时
- **SD WebUI**：端点、模型名、采样器、步数、CFG
- **OpenAI 兼容生图**：model、size、quality、参考图上限

前端只渲染与校验，不再让用户填自由文本；旧的文本编辑保留为“高级模式”折叠入口，避免迁移期丢配置。

### 4. 生图方式：拆参数、拆草稿（纯前端）

共享「服务与连接」，参数分组按方式区分：

- 文生图：尺寸/比例、风格、负面词
- 改图：参考图槽位与字节上限、蒙版策略、保真度、允许动作（`image.edit` / `image.mask_edit`）

每种方式独立草稿、独立校验、独立保存——现在共用一套 `configDraft`，切视图会把改图参数带进文生图。

## 二·补 已落地（同日晚）

| 项 | 改动 | 验证 |
| --- | --- | --- |
| ① 展开记忆 | `models-page.js` 新增 `companion-model-expanded.v1:<对象>` 存储，`restoreExpanded/rememberExpanded`；刷新、切任务、切页都保持上次展开 | `test_models_page` 40/40 |
| ② 生图双草稿 | 切视图前 `stashImageDraft`、切回 `restoreImageDraft`，两个视图各留一份 `configDraft/base/text/textBase`；有未保存改动时先确认再切 | 同上 |
| ③ 字段声明 | `astrbot_host/model_api.py` 新增 `IMAGE_PROVIDER_GROUP`（comfyui 4 项 / sd_webui 6 项 / openai_images 6 项，含 kind、group、默认值、范围、选项）与 `GET /model/image-schema` | `test_model_provider_api` 22/22 |
| ③ 字段速查 | `models-page.js` 新增 `loadImageSchema/imageSchemaKinds/imageSchemaBlock`：按当前功能的模型顺序聚焦对应服务，其余折叠；只读，不改保存路径 | 40/40、尺度审计通过、`sync --check` 无差异 |

### 仍未做

- **③-b 表单化**：把速查升级为 connection / workflow / sampling 三段输入控件，未知键收进「高级模式」文本框；需同步改保存序列化与 `imageConfigDirty` 判定，并补“渲染 + 保存往返”用例。
- **④ 群聊作用域**：`model_api.py:371` 的 `role|window` 扩成三值之前，先补群会话 scope 解析、授权与审计；否则只加白名单会静默写错作用域。

## 三、实施顺序

| 步骤 | 内容 | 依赖 | 风险 |
| --- | --- | --- | --- |
| 1 | 展开策略 + 当前生效摘要 | 无（纯前端） | 低 |
| 2 | 生图方式拆分（草稿/校验/保存） | 无（纯前端） | 中（同文件大，需回归 `test_models_page`） |
| 3 | 生图 provider schema 驱动 + 高级文本模式 | 需后端补字段声明 | 中 |
| 4 | 群聊作用域 | **需先补后端 `layer="group"` 合同** | 高 |

第 1、2 步先做；第 3 步要加后端声明（照 TTS 的 `provider_group` 结构）；第 4 步在补完后端前只能做占位。

## 四、验收基线

- `node tests/test_models_page.cjs`（现有 25+ 项）
- `node tests/test_model_provider_api.py`（宿主侧 provider 合同）
- `python tools/audit_page_scale.py` / `tools/sync_framework_page.py --check`
- 真机：模型页三任务切换、保存、重启后生效
