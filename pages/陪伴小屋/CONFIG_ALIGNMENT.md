# V2.0 配置与真实状态

更新：2026-09-25。

正式小屋通过 AstrBot Page SDK 获取 `page/targets` 与 `integration/manifest`。目标/角色和业务入口来自已认证的 V2 宿主目录；生活、状态、关系、记忆、成长按选中入口读取和提交，原版本、权限与操作回执保持有效。

Content、Image、Screen、Reality、Together、Game、Live 七项能力都是
`astrbot_plugin_private_companion` 包内的 native extension。它们由 V2
自己的 native extension registry 装配、启停、授权和执行，不要求安装或加载
七个同名伴侣插件，也不通过外部插件对象转发对话、设备或活动状态。

页面中的“V2 内置拓展”来自 `integration/manifest` 的 `extensions` 数组：

- `unassembled`：能力数据仍由 V2 保留，但尚未装配当前内置版本；
- `disabled`：已装配但在 V2 能力目录中暂停；
- `connected`：内置模块已启用并由 V2 native service 执行；
- `degraded` / `stopped`：当前模块需要检查设置、重载或等待宿主启动。

`providers` 只用于真正的外部兼容状态入口（当前仅保留 V1 核心的只读状态
观察）。这类状态不会被 V2 用作对话、设备或拓展执行，也不会读取旧版用户
数据库。配置开启、状态可读和 native 执行就绪分别表达，页面不以开关代替
在线设备检查，也不把未读取理解为没有资料。

分发的 `config-snapshot.js` 只含通用默认值，不再保存本机旧版用户配置。独立静态预览可以展示明确标注的设计样例；正式宿主页面始终以真实 API 为准。预览中的暂停、移除、便签编辑和天气仅影响浏览器样例，不能修改插件配置。

当前发布范围、入口和限制见 [V2.0 发行说明](../../docs/RELEASE_V2_0.md)。
