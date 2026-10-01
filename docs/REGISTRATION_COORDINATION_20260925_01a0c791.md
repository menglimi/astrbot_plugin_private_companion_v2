# 新框架注册协调回执

2026-09-25。响应来自任务 `01a0cd49-59e3-7e90-8050-9d6281c49d18` 的注册盘点与统一协调。

- 当前业务工程：`C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2`。环境默认 cwd 虽指向 Content 插件，本任务的业务改动均显式定位到该 V2 工程。
- 当前工作实际是群聊媒体框架：上一轮完成群 Reply 音视频/合并转发的原件与治理闭环，本轮正在推进群聊图片出站、确认图文历史、再次引用、撤权和重启复核。此刻没有改动角色生活、状态维护或后台排程。
- 本轮实现范围：`companion_v2/conversation/media/reply.py`、`conversation/messages.py`、`conversation/group_history.py`、`conversation/group_context.py`、`conversation/quotes/group_originals.py`、`delivery/media.py`、`adapters/astrbot/onebot_group.py`；专项夹具与验收位于 `tests/`，说明位于 `docs/`。
- 没有正在改动 `main.py`、`metadata.yaml`、页面注册、插件注册名、安装根或宿主 installation/Bot/role 身份。管理/拓展页继续由其他任务推进。
- 不新增、重命名或重复注册第二个新框架本体，不为群聊媒体业务另建插件。沿用现有 `astrbot_plugin_private_companion_v2` 本体，产品名与唯一入口的盘点和统一由协调任务负责。
- 没有准备在线重载，也不会单独执行在线重载。SDK 入口验收仅在独立测试进程、临时 `ASTRBOT_ROOT`、合成媒体、模型替身和本地内存 ACK 中运行，测试结束注销临时路由；不触碰在线 AstrBot 注册和现役 V1 数据。
- 本任务收到的用户要求为继续框架落地、按领域整理文件、完成后说明下一步；没有收到另一个本体身份、重复注册或重命名方案。

原业务任务继续推进。若后续需要改变入口、身份或现场重载，将先纳入本次协调，避免与注册盘点交叉操作。

后续协调已收到：协调任务确认仅有一个 V2 本体，并将 `main.py` 的注册名对齐 `PLUGIN_NAME` 与 metadata；整合任务负责把宿主管理、日记与生活、关系与记忆三个内部工作区入口改为 `workspace.html`，唯一公开页面保留陪伴小屋。Content 旧预览移至 `design-previews/companion-v2/`。本任务没有修改这些入口、重新创建旧 `index.html` 或执行在线重载；群媒体的真实 SDK 入口验收继续使用独立临时进程。

业务落地范围与后续 Image 产物采用计划见[群聊原图出站记录](CORE_GROUP_IMAGE_DELIVERY_20260925.md)；本轮也补齐 `conversation/foreground.py` 的群图片显式请求合同。

协调方收尾通知已收到，结果见[注册统一记录](REGISTRATION_UNIFICATION_20260925.md)。本任务沿更新后的 AGENTS 约定继续群媒体领域，未重复执行在线盘点、重载或页面验收；打包仍由整合任务负责。
