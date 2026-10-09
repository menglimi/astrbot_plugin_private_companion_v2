# 生图拓展：实施状态与设计记录

设计基线日期 2026-09-27；实施状态更新于 2026-10-01。对象是 Image 能力提供方（当前版本 0.5.0）与 V2 本体。第 1—9 节保留实施前的问题分析与设计选择；后续实现状态与验收记录为当前口径。没有读取、迁移或修改 V1 用户数据。

口径来源：V1 设计稿 `astrbot_plugin_private_companion/docs/IMAGE_EXTENSION_DESIGN_PATH_V1.md` 及其八篇专题、`IMAGE_TASKS_ASSETS_AND_ALBUM_V0.md`、`IMAGE_USE_AND_GOVERNANCE_V1.md`；V2 侧 `docs/NATIVE_PROVIDER_CONTRACT_20260925.md`、`CORE_NATIVE_IMAGE_DELIVERY_20260925.md`、`V2_GAP_CLOSING_TASKS_20260927.md`、`DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md`、`COMPANION_PROVIDER_STATUS_20260927.md`；提供方侧 `docs/IMAGE_V2_NATIVE_PROVIDER_20260925.md`、`IMAGE_MASKED_EDIT_V2.md`、`IMAGE_REGION_PROCESSING_V3.md`、`IMAGE_NATIVE_EXECUTION_V1.md`。行号锚点按 2026-09-27 工作树实测。

---

## 0. 当前状态摘要

原先列出的 E03 技术缺口现已完成源码接线：本轮私聊/群聊图通过一次性宿主引用租约供 Image 读取，多参考用途按输入顺序绑定，角色参考素材按角色共享并由独立群聊开关控制，默认仅供私聊；`image.mask_edit` 在后端具备真实蒙版槽位时声明；V2 对产物实施蒙版外像素保护并将引用来源与哈希写入治理记录。群聊仍不开放蒙版局部编辑。E04 也已补齐首版角色级业务面：小屋读取角色范围的产出相册，图片必须显式登记参考用途，衣柜保存角色级衣物资料并支持关联穿搭参考图，每日穿搭写入当地日期记录。Content 等任意跨插件资产读取仍未开放；真实 SD/ComfyUI 与 QQ 效果待现场验收。

实现与验证以本节后的 2026-10-01 记录为准。第 1—9 节的「当前缺口」「下一步」「本轮不构建」等语句描述的是 2026-09-27 的实施前状态，不是现在的状态。

| 项目 | 当前状态 |
| --- | --- |
| 本轮参考与跨来源编辑 | 私聊、群聊 `image.edit` 均可精确选择当前轮图片；角色参考素材按角色共享，群聊默认关闭且可单独开启。一次性授权句柄每次读取重新核权，不接受模型伪造句柄 |
| 多参考 | 已接入；用途逐张绑定，后端槽位不匹配会明确失败，不截断 |
| 蒙版局部编辑 | 已接入 `image.mask_edit`；后端绑定检查、输入校验、V2 蒙版外像素保护已接入 |
| 群聊蒙版 | 不开放，宿主目录及执行准入均拒绝 |
| E04 相册 | 已接入角色级只读投影；游标分页、缩略图预算和当前角色隔离生效 |
| E04 参考登记 | 已接入显式用途登记、幂等操作键、撤回；关闭参考图时拒绝登记 |
| E04 衣柜/每日穿搭 | 已接入角色级衣柜、描述/标签、参考图关联、撤回和当地日期选择；关闭配置时拒绝使用 |
| 真实后端、平台投递 | 合成回归已覆盖；现场验收待进行 |

## 历史设计基线（2026-09-27）

本节及第 1—9 节保留实施前的分析，表中的「未接入」「待决」是当时的状态。当前实现以本节后的实施记录和上面的状态摘要为准。

生图拓展的执行主链已在位。缺的不是执行器，而是三类性质不同的东西：

| 缺口 | 性质 | 本文怎么处理 |
| --- | --- | --- |
| **E03 剩余**：入站/跨来源编辑、多参考、蒙版与局部编辑 | 合同扩展 + 提供方改造，纯技术 | 第 1—4 节给完整路线与接口设计 |
| **E04**：相册、衣柜、每日穿搭 | 业务面，V2 无对应物 | 第 5 节给「读取投影优先」的取舍方案与一个待决项 |
| **小屋「产出」页** | 页面接入 | 第 6 节给按真实写入合同的分区方案 |

关键判断三条：

1. **入站图片不能塞进请求封套。** `invocation_request()`（`companion_v2/capabilities/native.py:136-141`）产出 11 键闭集，`parse_result()`（同文件 `:152-157`）按 `set(value) != keys` 全等校验。往里加 `references` 字段会同时打破请求与响应两侧的闭集，且 64 KiB 文档预算装不下图片字节。唯一站得住的通道是**宿主在 `before_dispatch` 窗口内向提供方显式投递参考字节**（第 2 节）。
2. **「恰好一个引用」是实现层常量，不是设计结论。** `image_companion/native_v2/types.py:109-110` 的 `edit_requires_one_reference` 是写死的；V1 设计稿本身是多参考的（`IMAGE_VISUAL_TASK_V1.md` 的用途枚举）。该约束应下移到按后端能力声明（第 3 节）。
3. **蒙版不需要新增公共任务版本。** V1 的 `image.preparation.task.v2/v3` 是「另一套本地可信装配」，在 V2 里等价的承接物就是「多一个 `edit_mask` 用途的参考 + 一条独立的保护契约」。V2 用一个具备 `edit_mask` 能力的 `image.mask_edit` action 表达，比照搬 v2/v3 版本号更贴合现有合同（第 4 节）。

不新增表、不升 schema、不改 `NATIVE_PROVIDER_CONTRACT` 的端口方法集。

---

## 1. E03 的三种缺口要分开对待

三者常被写在一行（E03「入站/跨来源、多参考、蒙版/局部编辑」），但难度和风险差一个量级：

| 子项 | 现在缺什么 | 风险 |
| --- | --- | --- |
| **入站/跨来源编辑** | 宿主无法把「本轮聊天里的图」「Content 作品插图」的字节交给 Image 提供方。提供方只认自己 store 里、同 scope 同 origin 的 `artifact_id`（`adapter.py:172-179`） | 高：这是授权与身份边界的改动，做错就是跨 scope 读图 |
| **多参考** | `types.py:109-110` 写死一个引用；`backends.py:96-99` 的 `len(images) != len(invocation.reference_ids)` 也是按此推导 | 低：纯放宽，不动授权 |
| **蒙版/局部编辑** | 提供方参数白名单（`adapter.py:91-93` 不接受）与 `backends.py:100-105` 显式拒绝 `mask` kind；V2 侧无保护契约 | 中：像素保护必须由 V2 侧强制，不能信后端 |

**实施顺序必须是：多参考 → 入站/跨来源 → 蒙版。** 理由：多参考是另外两项的前置（蒙版本身就是一个额外参考），且它风险最低、可先独立验收；入站通道一旦建立，蒙版才有「底图从聊天来」的真实场景。

---

## 2. 入站/跨来源：宿主投递参考字节的通道设计

### 2.1 为什么必须是「宿主投递」而不是别的

候选通道逐个否决：

| 通道 | 否决理由 |
| --- | --- |
| 请求封套内带 base64 | 破坏 11 键闭集与响应全等校验；64 KiB 预算不够；字节进模型上下文违反既有约定（`NATIVE_PROVIDER_CONTRACT:80`） |
| 传 URL / 本地路径 | 直接违反合同「`read_artifact` 不接收任意 URL/本地路径」，等于把路径遍历风险引给提供方 |
| 提供方直读共享磁盘 | 引入两个插件间的路径耦合与生命周期耦合，且绕过 V2 的 sources 授权 |
| 让提供方读自己 store | 入站图不在提供方 store 里，也不该在——它的 owner 是 V2 的 sources，不是 Image |

剩下唯一自洽的形态：**宿主持有字节，在提供方发起 I/O 前把字节交给它**，且这次交付本身受 `before_dispatch` 约束。这与合同里「所有真正 I/O 前再次调用该回调」是同一套时序，不需要新时序概念。

### 2.2 接口形状

在端口方法集之外**新增一个可选方法**（合同允许「其余端口按能力实现」，见 `NATIVE_PROVIDER_CONTRACT:13`）：

```python
async def fetch_reference(request: dict, *, before_dispatch) -> bytes: ...
```

- `request` 复用原 invoke 的完整封套，另加两个宿主生成的字段：`reference_handle`（不透明句柄）与 `content_hash`（宿主已知的期望哈希）。
- 提供方**不解析句柄**，只做搬运；句柄的含义、绑定与生命周期全在宿主侧。

宿主侧行为：

1. 调用 `image.edit` 前，按 invocation 上下文解析本轮可用参考（`conversation/media/` 已有的受权图片集合与 `sources` 校验路径），为每个参考生成一次性句柄，绑定 `(invocation_id, scope, audience, asset_id, version, content_hash, 截止时间)`。
2. 提供方在 `_plan()` 之后、真正提交后端之前调用 `fetch_reference`；宿主重新校验当前授权后返回字节，并**立即消费该句柄**。
3. 第二次调用同一句柄一律拒绝（`reference_handle_consumed`），过期拒绝（`reference_handle_expired`），scope/audience 不符拒绝（`reference_binding_mismatch`）。
4. 选错的哈希在提供方侧仍按 `ReferenceImage.metadata()` 的既有逻辑拒绝（`reference_fingerprint_mismatch`，`types.py:59`），不新造校验。

单次使用的理由是**幂等重放安全**：提供方崩溃后按原 operation 恢复，若句柄可复用，恢复路径可能取到已撤权的图。一次性 + 恢复时重新签发，使「每次读字节都要当前授权」这条既有约束在参考路径上也成立。

### 2.3 owner 与留据

参考字节不改变 owner：图仍属原来的 owner（用户入站图属宿主 sources，Content 插图属 Content）。提供方只在本操作的 `request` 文档里记 `reference_id` 与哈希（`owner.py` 的 `store.begin(request)` 会把它纳入指纹），**不复制源、不建立第二个正本**。这与 `IMAGE_TASKS_ASSETS_AND_ALBUM_V0.md` 第 6 节「Image 结果 durable 后通知相册/Content，消费者按原意图幂等建立关联」的方向一致：谁产生谁负责，Image 只消费。

产物侧的链回显：成图仍是新产物（新 artifact_id、新 operation），但它的 `receipt` 里保留本次提交的参考引用清单与哈希——这正是 V1 设计稿 7.3 要求的「计划选中 → 读取成功 → 实际提交 → 后端确认」四级分开记录，V2 侧落在 `receipt.backend` 与 `submitted_inputs` 等价的字段里。

### 2.4 提供方实现要点

- `NativeTransportBackend.execute()`（`backends.py:106-125`）现在从 `references` 参数直接拿字节；入站参考走 `fetch_reference` 取字节后包成 `ReferenceImage`，与自有 store 的参考**在同一个数组里**——后续 plan、绑定与回执逻辑完全复用。
- `adapter._execute()`（`adapter.py:160-180`）现在对 `image.edit` 走 `self.owner.store.artifact(...)`；改为「先看 arguments 是否给了自有 artifact_id，没有则用宿主投递的句柄」。两条路径互斥，不允许同时出现（同时出现报 `invalid_image_arguments`）。
- `GuardedClient`（`backends.py:12-30`）已经在每个 GET/POST 前调 fence，参考解密不需要新增护栏点，但**取字节本身算一次 I/O**，必须在 `before_dispatch` 之后。

---

## 3. 多参考：把「恰好一个」下移到能力声明

### 3.1 现状

`types.py:109-110`：

```python
if self.operation == "edit" and len(references) != 1:
    raise NativeImageError("edit_requires_one_reference")
```

这条是全体 operation 共用类型上的硬约束，等于在类型层宣布「V2 的 Image 永不支持多参考」。它挡住了三件设计稿明确要求的事：双图加入角色（V1 原生执行稿已有真实样本）、独立身份图、以及蒙版（底图 + 蒙版 = 两个参考）。

### 3.2 改法

把数量的判定从 `ImageInvocation.__post_init__` 移到**后端能力**上：

| 层 | 判定 | 依据 |
| --- | --- | --- |
| 类型层 | 只判引用 id 合法、去重、非空 | 已有逻辑保留 |
| 后端层 | 按 `operations` 与 `reference_slots` 声明本后端能收几个、各是什么用途 | 新增，替代硬常量 |
| 路线层 | 路线的 `reference_bindings` 与后端声明必须一致，否则 `native_workflow_bindings_invalid` | `backends.py:96-99` 已有雏形，扩为按用途匹配 |
| 宿主层 | 参考数超过后端声明的上限时，**不盲目截断**，返回明确缺口 | 设计稿 7.2 第 4 条：「后端只支持一张图时，不盲目截断参考数组，也不假称多主体身份都已保留」 |

### 3.3 用途词汇

沿用 V1 设计稿已有的用途枚举，不新造词：`identity`、`outfit`、`pose`、`style`、`background`、`continuity`、`edit_source`、`edit_mask`。V1 的 `edit_mask` 由 `IMAGE_MASKED_EDIT_V2.md` 定义，`IMAGE_VISUAL_TASK_V1.md` 的 7.1 节是权威枚举点。

同一张图可承担多个用途，但**必须显式列出**——这条是设计稿 7.1 的明确要求（「身份图里的衣服、风景和另一人物不会因为『用了这张图』而自动成为本次要求」）。V2 侧的落点是宿主在投递参考时一并声明用途，提供方按用途匹配到工作流的槽位。

### 3.4 副作用清单

- `manifest()` 的工具声明需要能表达「可带 N 个参考」。现有参数 schema 是闭合的（`additionalProperties: false`，`adapter.py:71-79`），多参考应作为**宿主侧投递**而非模型参数——模型只表达画面要求，选图由宿主按授权解析。这保持了「目标身份不从模型 arguments 取值」的既有原则。
- 群聊分支要独立确认：群图作为编辑底图目前不在允许集内（`docs/CORE_GROUP_IMAGE_DELIVERY_20260925.md` 只开两个动作）。多参考放开后需重新过一遍群受众判定，不要顺手把群图加进来。

---

## 4. 蒙版与局部编辑：V2 化设计

### 4.1 为什么不搬 v2/v3 版本号

V1 的 `image.preparation.task.v2`/`v3` 是本地可信装配里的任务版本演进。V2 没有这条任务链——`ScreenProcessingPipeline` 那类「有类型无生产入口」的情况不适用于 Image（这里连类型都没建）。在 V2 里，蒙版的语义增量只有两点：**①多一个 `edit_mask` 用途的参考；②产物必须做区域外像素保护**。这两点用一个 action 就能表达，不需要版本号体系。

### 4.2 接口

新增可选 action `image.mask_edit`（与 `image.generate`/`image.edit` 并列，同样只在后端声明了蒙版能力时出现）：

- 参数：`prompt`、`negative_prompt`、`artifact_id`（底图，自有或宿主投递）、`mask`（参考句柄）。
- 前提：底图与蒙版**同尺寸**。尺寸不符在提交后端之前失败（`mask_dimension_mismatch`），不隐式缩放、不裁剪、不猜选区——照抄 `IMAGE_MASKED_EDIT_V2.md` 的边界。

### 4.3 像素保护必须由提供方执行

这是本片最重要的一条。设计稿的硬要求是「原始蒙版值为 0 的像素严格保持原图 RGB」（`IMAGE_MASKED_EDIT_V2.md` 与 `IMAGE_REGION_PROCESSING_V3.md` 一致）。实现要点：

1. 执行前读取冻结版本的底图与蒙版，核对哈希、模式、尺寸、有效选区（非全黑、非全白）。
2. 后端返回后检查**输出与底图同尺寸**；不符则拒绝发布，**不能退回未保护的后端图片**。
3. 合成 `generated × mask + source × (1-mask)`，只混一次。V3 的裁剪放大路径额外记录实际缩放尺寸、偏移与变换标识，从后端原始输出还原后再贴回原图坐标。
4. 证据记录底图哈希、蒙版哈希、每张输出的后端原件哈希、最终哈希与合成标识（V1 用 `source-mask.v1`/`crop-fit.v1`）。
5. 恢复路径：重核权限、读原版本素材、查同一后端任务、**从后端原始输出重新合成**——绝不对已合成结果再叠一次灰度蒙版（V1 明确踩过这条）。

### 4.4 接受度边界要写进能力声明

`IMAGE_NATIVE_EXECUTION_V1.md` 有一条容易越界的说明：**管理员在配置里声明 `masked_edit=true` 本身不增加能力**，必须由目录的 `masked_edit`、任务版本与实际绑定共同确认。V2 的对应做法：`image.mask_edit` 的**出现与否只取决于后端能否真实绑定 `edit_mask` 槽位**（ComfyUI 要求存在独立的蒙版加载节点且其输出接入影响最终图像的支路；SD WebUI 要求路线声明支持蒙版），而不是配置里写了一个开关。测试要专门覆盖「配置声明但绑定不成立 → action 不出现」。

---

## 5. E04（相册/衣柜/每日穿搭）：先做读取投影

### 5.1 决策口径

`COMPANION_PROVIDER_STATUS_20260927.md` 第四节已给出判断：**Image 是唯一「缺的不是接线而是业务面」的一家**，排期前应先决定是否整体迁移。设计稿这边也明说：`IMAGE_USE_AND_GOVERNANCE_V1.md` 第 8 节把「现有相册删除链」标为不可直接复用（「新增『仅移除条目』须独立实现，不能直接复用该删除入口」）。

### 5.2 历史建议：读取投影，不建新正本

理由：V2 侧的相册语义其实**已经存在**——`CORE_VOXEL_HOME_MEMORY_PAGE_20260924.md` 那条小屋陈设/相册线。再造一个 Image 专属相册正本会立刻撞上多方引用与治理问题（设计稿 7.3 要求「同一图被相册/作品/相框使用」时多方持有有回执、物理去重不合并权限）。投影方案的具体形态：

- Image 提供方**只暴露已保存产物的只读列表**（按 scope + origin 过滤，复用 `store` 的 `artifacts` 表），不新建相册表。
- 小屋侧把投影与既有陈设/相框引用拼起来显示，图仍是同一个 asset，不产生第二份字节。
- 删除语义分两级：**仅移除引用**（小屋页动作，只解关联）与**删除原件**（走已有的治理路径，先关读取再清理派生）。这条正好对应设计稿第 7 节「移除、删除、取消、丢弃是不同操作」。
- 衣柜与每日穿搭本质上也是「参考图的用途索引 + 一条按日选择记录」，投影方案同样成立；真要做成可写正本，应作为一个独立领域提案，而不是挂在 Image 提供方里。

### 5.3 历史待决项

**衣柜是否需要「实际写入」的语义？** 即：用户能否在小屋里把某张图显式标成「今天是这套衣服」，并让后续生成默认引用它。若需要，它是一条新的、有状态的角色日更记录，属独立领域；若只需要「看过往穿搭」，投影方案就够了。该问题已在 2026-10-01 采用折中实现：衣物资料和每日选择写入 V2 参考素材域的角色正本，只有启用相关开关时才会进入提示词；原件相册仍保持只读投影，不复制图片字节。

### 5.4 2026-10-01 当前实现

- `GET /image-materials/album` 只读取当前私聊角色已经治理过的生成图，使用游标分页和受限 JPEG 缩略图，不把 V1 相册数据迁入 V2。
- `POST /image-materials/references` 要求从当前角色相册选择图片并显式列出用途；登记和撤回分别记账，撤回只停止该用途，不删除原产出。
- `POST /image-materials/wardrobe` 写入角色级衣物名称、描述、标签及可选的穿搭参考图；衣柜管理和提示词使用开关分开，服务层允许先维护资料。
- `POST /image-materials/daily-outfit` 按角色当地日期写入当天选择；配置关闭、上下文变化、角色重绑定和跨角色资产均在宿主/核心两侧拒绝。

---

## 6. 小屋「产出」页：按真实写入合同分区

### 6.1 设计稿要求 vs 可用合同

`PAGE_UI_UX_DESIGN_20260926.html` 的 P4 页要求三 Tab（图像生成 / 创作与作品 / 素材与参考图）、左表单右预览并排、范围授权单独成块并二次确认。但 V2 侧对 Image 的**真实可写合同**只有三类：扩展自持的路线与连接（已在模型页）、`conversation.media_quota` 四档（T01）、`conversation.image_review` 十一项（T09）。所以：

| 页签 | 可写 | 只读 | 未接入时 |
| --- | --- | --- | --- |
| **图像生成** | 额度四档、审核十一项（真实 FieldDefinition） | 模型页的默认路线与后端连接（跳转）、Native 动作开关状态 | 生图参数（默认尺寸/步数/批量/负向/并发/水印）**不显示假控件**，标注「归生图扩展」并给跳转 |
| **创作与作品** | — | Content 侧作品投影 | 未接入时整 Tab 不显示（沿用设计稿「能力驱动显隐」，同 V1 `hidden` 页口径） |
| **素材与参考图** | 产出相册读取、参考用途登记/撤回、角色级衣柜、每日穿搭 | — | 未绑定私聊角色时显示等待绑定；配置关闭时控件禁用并显示状态 |

### 6.2 范围授权成块

设计稿要求「谁能让她生图」单独成块并二次确认。V2 的对应物是配额四档（`private_owner`/`private_friend`/`group`/`proactive`）与逐次授权，不是 V1 的 `operation_access` 三档。这一块应复用决策页的 `state-contact` 工作区形态（T52 已建立的先例），危险项加二次确认，不与普通参数混排。

### 6.3 顺带清掉的三处小账

审计 `DESIGN_VS_IMPLEMENTATION_AUDIT_20260927.md` 已定位，都是同一片页面/契约工作里的顺带项：

- **B11**：小屋无法清除已存的 Image 密钥。`models-page.js:716` 只在非空时提交 `api_key`；后端本可接受空串（`image_native_configuration.py:61-62`）。补一个「清除已保存的密钥」复选项，勾选时提交 `api_key: ""`。V1 面板有现成形态（`native-image.js:160,383-384`）。
- **B12**：生图额度日界时区与 `date_context` 不同源。`conversation/media/quota.py:48,107-112` 用 `messages.timezone_name` 且装配从不传参；`date_context` 用可配置的 `calendar_timezone`。统一到同一处解析，否则非默认时区下配额零点与角色当地日错位。
- **B13**：`image.edit` 的 provider generation 检查是自反比较、恒真（`adapter.py:149-152` → `owner.py:133`）。期望值改取 operation 行，与 `store.py:153-155` 的回执校验对齐。

---

## 7. 验证路线

按项目既有约定：开发期只做阻断性最小检查，交付包统一测试。定向测试的落点与要覆盖的反例：

| 范围 | 模块 | 必须覆盖的反例 |
| --- | --- | --- |
| 参考投递 | 提供方 `test_native_v2_provider` + V2 `native_extensions` | 句柄二次使用、过期、跨 scope/audience、哈希不符、撤权后恢复路径重签发、模型 arguments 伪造参考 |
| 多参考 | `types` / `backends` / 路线绑定 | 后端声明 1 个时收 2 个（明确缺口，不截断）、用途重复与冲突、群聊分支不被顺手放开 |
| 蒙版 | 提供方蒙版专项 | 尺寸不符、全黑/全白蒙版、输出尺寸错误拒绝发布、蒙版外像素严格相等、恢复不二次合成、配置声明但绑定不成立时 action 不出现 |
| 页面 | `tests/test_models_page.cjs` 等页面合同 | 未接入项不出现假控件、密钥清除与留空的区别、二次确认生效 |
| 额度时区 | `tests.test_image_quota` | 非默认时区下的日界 |

命令（AstrBot 自带 Python）：

```powershell
$env:PYTHONPATH='C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -X utf8 -m unittest tests.test_image_quota tests.test_native_image_flow tests.test_native_image_result_handler tests.test_group_image_review
node --check "pages/陪伴小屋/models-page.js"
node tests/test_models_page.cjs
```

页面改动另有四件必查（语法、`index.html` 的 `?v=` 缓存串、`tools/sync_framework_page.py` 更新 `page-build.json`、测试夹具的 `data-*` 属性名对账）。

---

## 8. 本片边界（历史基线）

不新增表、不升内部 schema、不改 `companion.native-provider.v1` 的端口方法集（`fetch_reference` 属合同已允许的「按能力实现」的可选端口，但需在合同文档补一句说明）。当时不给 E04 业务面造假控件，不用只读说明冒充可写。本轮历史记录中的「不构建交付包」已由 2026-10-01 的交付步骤覆盖；真实 SD/ComfyUI、模型与 QQ 现场验收仍未完成。

---

## 9. 历史待决项（已处理项保留作决策记录）

1. **衣柜是否需要写入语义**：已按第 5.4 节落为角色级衣物资料和当地日期选择；不会复制相册原件。
2. **入站参考是否对群聊开放**：仍不开放，沿用现有群图边界。
3. **`fetch_reference` 落在合同里还是落在提供方扩展里**：当前采用可选 `host_references` / `fetch_reference` 执行参数，未扩大公共请求/响应 schema。

## 10. 2026-10-01 实施记录

- Image 提供方升级为 `0.5.0`，声明 `image.generate`、`image.edit` 及后端实际支持时的 `image.mask_edit`。
- V2 通过可选执行参数传递本轮私聊/群聊图片 offer；一次性句柄与原调用、来源、受众和哈希绑定，每次读取前由宿主重新核权。句柄不写入操作请求或可恢复状态。
- `image.edit` 可按私聊输入图片位置接收多参考用途。ComfyUI 工作流按实际槽位分配用途，参考数与槽位不匹配时失败，不静默截断。
- 角色参考库仍按角色共享；新增角色级 `photo.reference.group_enabled`，默认关闭。开启后群聊 `image.edit` 可按已登记用途读取角色素材，群聊提示只注入参考目录，不注入衣柜或每日穿搭；未开启时后端读取和提示注入均拒绝。
- `image.mask_edit` 在 ComfyUI 的蒙版加载输出确实接入有效图像支路，或 SD WebUI 路线真实声明蒙版输入时才加入目录。底图与蒙版提交前检查；V2 采用结果时严格保护区域外像素并留存来源哈希。
- 群聊工具目录与执行准入继续只允许 `image.generate` / `image.edit`，模型不能通过伪造动作绕过。
- E04 相册、参考登记、衣柜和每日穿搭已经接入「陪伴小屋」产出工作区：相册是只读投影，参考用途/衣柜/每日选择是明确写入；Content 等任意跨插件素材读取仍未开放。
- 页面端补齐未绑定、未初始化、配置关闭、空态、错误态、分页、撤回、角色切换丢弃旧请求和窄屏单列布局；核心和宿主同时复核私聊角色、绑定版本、操作键及每日日期。
- 当前合同为可选 `host_references` / `fetch_reference` 执行参数，不新增公共端口方法或变更请求/响应 schema。
- V1/V2 对比结论：V1 的相册/衣柜入口偏向提供方内资料与隐式复用，V2 保留其用途覆盖能力但把相册读取、参考登记和衣物资料拆成角色级合同；V2 不接受模型自行指定路径，引用用途必须登记且可撤回；角色参考素材按角色共享，但群聊使用默认关闭并可独立授权。未知结果不重放。V1 的群聊蒙版、跨插件任意素材直读和真实平台效果没有迁入。
- 2026-10-01 定向回归：Image 提供方原生 provider/transport **21 项通过**；V2 Image/额度/门禁/目录合同集 **63 项通过、16 个子用例通过**；新增素材工作区 Node 契约 **5/5 通过**。`test_native_group_image_flow.test_sdk_group_generation_delivery_history_and_confirmed_quote` 仍失败于续轮提示前缀校验（`conversation_task_failed`），同一失败已在本轮以前的工作记录中出现；该用例未进入其群聊历史/引用断言。蒙版群聊拒绝、一次性参考、哈希与用途绑定、蒙版外像素保护均有通过的定向用例覆盖。
