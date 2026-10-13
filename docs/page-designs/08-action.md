# 行动页（`manage/action`）

代码位置：`renderActionOriginal`、`renderQzoneSection`，位于 `pages/陪伴小屋/app.js`；样式由 `action-page.css` 提供。

## 页面定位

行动页承载主动发起的生活、游玩、设备与空间互动。QQ 空间是页内主要工作区，V2 内置拓展作为状态清单展示。

## 页面结构

- QQ 空间置于首位，提供状态读取、安装与授权、动态浏览、点赞、回复、发布、建议处理和角色级设置。状态与操作继续使用 `#actionQzoneBody` 局部刷新。
- 共处、游玩、现实设备以三条状态行呈现，显示内置拓展状态、详情及对应设置页入口；只读展示拓展状态，不在此复制其配置。
- 窄屏将状态与操作入口分行排列，能力名称保持完整，不产生横向溢出。

## 数据与边界

- V2 内置能力状态来自 `GET integration/manifest` 的 `manifest.extensions`；真正由其他插件提供的兼容入口才来自 `manifest.providers`。详情使用 `product-page.js` 提供的状态及原因。
- QQ 空间调用 `astrbot_host/qzone_api.py` 的状态、安装配置、动态、点赞、回复、发布和凭据路由。安装、对象授权及角色级开关继续由宿主与服务端校验。
- 对外操作的受理、确认、结果未知等状态按服务端回执显示；结果未知时不自动重发。
- Together、Game、Reality 不在行动页持有配置；这些能力由 V2 本体拓展装配和启停，现实设备映射与授权由感知页管理。

后端路由的挂载与身份要求见 `astrbot_host/qzone_api.py`、`web_api.py` 和 `multi_api.py`。页面同步由 `tools/sync_framework_page.py` 维护。
