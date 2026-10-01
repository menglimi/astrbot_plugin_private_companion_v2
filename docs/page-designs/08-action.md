# 07 · 行动（`manage/action`，C 段）

代码位置：`renderAction`（`pages/陪伴小屋/app.js:1153-1155`）；能力卡渲染 `providerSummary` → `product-page.js` 的 `providersMarkup`（`:590-594`）。

## 一、页面功能

回答"除回复以外的行为"：共处（Together）、游玩（Game）、现实设备（Reality），以及**可安装的创作拓展**（QQ 空间）。前三个分区仍是**接入状态总览**，不持有配置；QQ 空间分区是该页第一个可写面，安装后在这里刷空间、点赞、回复、发说说，并编辑它自己的角色级配置组。

## 二、展示部分

| 分区 | 内容 | 数据来源 |
| --- | --- | --- |
| 生活行为 · 共处、游玩与现实设备 | 三张能力卡：各提供方的 `integration_state`（接入状态）、runtime 就绪情况与不可用原因；点开有提供方详情（`product-page.js:602-605`） | `GET integration/manifest`（`product-page.js:382`）→ `manifest.providers` 按 capability_id 过滤（`:590-594`） |
| QQ 空间拓展 | 安装前：说明 + 「安装并启用」；安装后：凭据状态、熔断提示、四项授权标记、能力开关、刷空间列表（每条带点赞/回复）、发说说、刷新凭据、停用 | `GET/POST …/qzone-extension/{status,configure,feed,like,comment,publish,refresh-credentials}`（`astrbot_host/qzone_api.py`） |

能力→页签映射：content → 产出页，其余（together/game/reality/live…）→ 行动页（`app.js:339-340`）。

## 三、配置部分

- Together/Game/Reality 三个分区**无自有配置**（`app.js:1154` 仅 `providerSummary`）：各能力提供方自持配置，V2 只读接入状态；现实触及的设置表单可在感知页 A3 经 `/perception` 桥修改（见 [06-perception.md](06-perception.md) 第五节）。
- QQ 空间分区持有一组**角色级配置** `qzone`（总开关 + 三项动作开关 + 读取条数 + 动作间隔 + 单轮上限 + 扫描条数 + 每日上限），经 `configEditors('qzoneConfigWorkspace',['qzone'],'QQ 空间设置')` 渲染；后端编辑器 `QzoneManagement` 注册在 `astrbot_host/configuration_api.py` 的 `SECTIONS`，前端声明在 `config-editor.js`，三方对账由 `tests/test_section_wiring.cjs` 守住。安装/逐会话同意**不在**这里，归能力安装路由（`…/qzone-extension/configure`）。

## 四、边界与空态

- 能力未接入时显示提供方自报 reason；不可用与"配置里关了"是两种状态，页面按 `integration_state` 区分（`app.js:711-725` 只认 `missing`/removed/planned）。
- QQ 空间未安装时不给四项操作，只给安装入口；未安装、未启用、未同意时后端一律拒绝，页面据此禁用按钮并说明原因（判断顺序与后端一致：总开关 → 熔断 → 这一项开关）。
- 「已受理」与「已确认」是两种结果：`accepted` 只说等待同步，`unknown` 明确不说成功且不自动重发。

## 五、后端情况

- `GET /integration/manifest`（`astrbot_host/integration_api.py:25`，只读、需 dashboard 身份 + ObjectAccessPolicy）。
- QQ 空间：`astrbot_host/qzone_api.py`（`…/qzone-extension/*`，单目标在 `web_api.py` 挂载，多目标按角色前缀在 `multi_api.py` 挂载），全部要求 dashboard 身份与固定私聊目标，不接受请求参数指定他人身份。

## 六、相关设计稿与复核

- 现实触及设置 → [06-perception.md](06-perception.md)；生图（另一个"产出类能力"）→ [09-output.md](09-output.md)；QQ 空间落地记录 → [QZONE_EXTENSION_LANDING_20261002.md](../QZONE_EXTENSION_LANDING_20261002.md)。

