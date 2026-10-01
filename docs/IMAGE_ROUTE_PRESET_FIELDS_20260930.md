# 生图路线的四个预置字段：谁可编辑、谁只读（2026-09-30）

对象：陪伴小屋 → 模型与连接 → 生图模型 → 路线队列里的**一条路线**。
背景：路线配置的读取端一直带着四个字段（`parameters`、`guidance`、`reference_bindings`、`masked_edit`），
页面既不显示也不编辑，只在保存时整条路线原样透传。本文记录补齐它们时的分工与依据。

范围：`pages/陪伴小屋/models-page.js`（路线编辑器）、`astrbot_host/model_api.py`（传输上限）、
`tests/test_models_page.cjs`、`tests/test_model_provider_api.py`。语义与边界仍**只由生图扩展声明**。

---

## 一、结论

| 字段 | 谁可编辑 | 依据 |
| --- | --- | --- |
| `parameters` | **页面给控件** | 有真实运行时效果；扩展已把键表与边界全量下发（`limits.parameters.{common,sd_webui,float,text}`），`image_config_limits.py` 的模块说明本就要求管理面照它写 min/max |
| `guidance` | **页面给控件** | 六键说明（`image_route_guidance.FIELDS`），是选路线的参考；上限随 `limits.guidance` 下发（16 条 / 4000 字）。其中 `edit_method` 是枚举且受约束 |
| `reference_bindings` | **只读** | 三键（`slot`/`role`/`subject_ids`）与八种用途必须和工作流的图槽位一致，不一致就是 `native_workflow_bindings_invalid`（`image_native_plan.py:146-160`）。**槽位表只有扩展看得到**，扩展没有下发，页面无法在提交前判断一条绑定是否成立 |
| `masked_edit` | **只读** | 按 `docs/IMAGE_EXTENSION_GAP_DESIGN_20260927.md:154`，它是**派生值**：等于绑定里是否存在 `edit_mask` 槽位；"管理员在配置里声明 `masked_edit=true` 本身不增加能力"。做成开关会让用户以为打开就能用蒙版 |

判定口径：**能不能改由语义决定，不由实现成本决定**——可编辑的两个是真设置，只读的两个一个是校验面、一个是派生事实。

---

## 二、可编辑的两个：边界从哪来

- 参数：`PARAMETER_LIMITS`（宽/高/种子）、`PARAMETER_LIMITS["sd_webui"]`（步数/每批张数）、
  `PARAMETER_FLOAT_LIMITS`（提示词强度/重绘幅度）、`PARAMETER_TEXT_LIMITS`（采样器）→ 经 `public_limits()`
  进 `limits.parameters`。页面按路线的 `backend` 决定显示哪几个键，ComfyUI 只有前三个。
- 说明：`limits.guidance` 的 `max_items` / `max_chars`。两个列表字段（`suitable_for`、`limitations`）按行拆分，
  其余按文本存。
- **空值语义**：参数框留空表示"未声明"，保存时**删掉该键**（提交空串会被扩展的参数类型校验拒掉，
  与"保留原值"的密钥框不是一回事）；说明字段同理。
- **不静默改写**：若某条路线的 `edit_method` 在当前操作/后端下不被接受，页面在下拉框里补一条
  「（当前不接受，保存会被拒）」并在提交前挡下，而不是替用户改掉已写入扩展的配置。

约束只描述、不复制：`edit_method` 的可选集合按 `operation` / `backend` / `masked_edit` 现算，
与扩展的 `validate_guidance` 保持一致；扩展那边仍然是唯一的判定者。

---

## 三、只读的两个：页面上给什么

- 参考图绑定：按「用途 ← 槽位」列出已声明的绑定（用途用中文：身份/服装/姿态/风格/背景/延续/底图/蒙版），
  未声明时写明"由工作流里的图输入自动绑定"；并说明槽位与用途必须与工作流一致、编辑要在生图扩展配置里做。
- 蒙版改图：显示是否已声明，并写明它是派生值、`masked_edit=true` 本身不增加能力。

---

## 四、传输闸门（本轮新增的一处宿主改动）

路线说明是可长文本（单键 4000 字），而保存提交的是**整份路线数组**：32 条路线写满说明时请求体能到几百 KB，
原来的 64 KB 会在扩展允许的内容之内先失败，用户只会看到宿主那句 `model request is too large`。

- `astrbot_host/model_api.py` 的 `image/config/save` 上限：64 KB → **256 KB**（传输闸门，不是业务规则；
  业务边界仍然只有 `image_config_limits.py` 一处）。
- 页面用同一个数字（`models-page.js` 的 `IMAGE_SAVE_LIMIT`）在提交前挡一次，并报出**最占地方的那条路线**
  与它的大小，让用户知道该缩短谁。两处注释互相指向，改一处要一起改。

---

## 五、后续（需要另一个仓库配合）

要给 `reference_bindings` 做编辑器，先得让 Image 提供方在配置接口里**公开每个后端/工作流的图槽位用途表**
（槽位名、是否蒙版、可承担的用途）。没有它，编辑器只能写出"保存成功、生成时才失败"的绑定——
这正是 `IMAGE_EXTENSION_GAP_DESIGN_20260927.md` 第 3.2 节要求按用途匹配、并在不一致时报
`native_workflow_bindings_invalid` 的原因。

---

## 六、验证

```powershell
node tests\test_models_page.cjs            # 41 项（新增 11 项）
python -m unittest tests.test_model_provider_api   # 4 项（新增 1 项：旧上限之上的一次保存）
python tools\sync_framework_page.py --check        # 空差异
```
