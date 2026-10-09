# 自我页重设计 · B「角色手帐」终稿（2026-10-07，已落地）

> **落地状态（2026-10-07）**：本稿已替换进源码。改动点：
> `workbench-page.js`（内核新增 date / chips / quotes / tags 四种轻结构文本控件，
> 真源始终是 `data-wb-field`，保存、草稿、层轨、幂等重试逻辑未动）；
> `workbench.css`（四种控件的样式）；`config-editor.js`（role_profile /
> relationship_profile 的 inputs / chipOptions / segmentedChoices 声明、
> rows/segmented/chipOptions 透传、完成度环的 stroke-dasharray 适配）；
> `app.js`（`renderGovernanceOriginal` 按本稿重排 + 「角色自述」词条委托，
> 页签方向键导航改查 `.deck-tabs`）；`role-profile-draft.js`（自述画布预填
> 补充稿、知识入口改查 `.deck-tabs`）；`self-page.css`（整页替换为手帐式套件，
> 保留 models 页、整理资料对话框与关系标题排版；内核模块侧栏在本页隐藏，
> 由章节词条条承担导航）。
> 定向检查：`tests/test_config_editor.cjs` 全绿（含 2 个新契约测试：
> 控件声明映射、五种控件渲染），reply/expression/decision/memory-workbench/
> section-wiring/css/shell 测试全绿；`node --check` 通过；真实页面离线态
> 浏览器渲染核对（封面/页签/词条/自述卡完整，无控制台错误）。
> `test_page_route.cjs` 的「真实 SDK 夹具断言 endpoint 是插件相对路径」
> 为**既有失败**（tools/check_host_management_page.cjs 在本工作树中被改为
> `assert(!endpoint.startsWith("/") && …)`，与本次改动无关）。
> 按仓库约定，交付包构建与统一测试（宿主加载、停机、路由注销）在全部页面
> 就绪后统一执行。
>
> **宿主截图反馈收敛（同日）**：与预览差距的三个来源已修复——①姓名/年龄感/
> 职业/外貌/时代/平台称呼等一行字段在 spec 声明为 `line` 单行输入，不再被
> 默认 textarea 顶成通栏（`:has(textarea)` 的通栏规则只留给真正的长文本）；
> ②档案与关系字段画成手帐小卡（surface-soft 底 + 圆角边框 + 两列排布），
> 八个分区面板带「01 / IDENTITY」式编号小标；③性别/种族词条不再独占通栏，
> 生日日期框限宽。词条快选从通栏列表移出后与相邻短字段成对。
> 验证方式：临时合成宿主页（`%TEMP%\self-kernel-check\index.html`，假桥返回
> 按 spec 现造的 46 字段契约）真实挂载内核，核对五种控件渲染、两列小卡、
> 章节小标，并实测词条交互全链路（点「男」→ 输入框/草稿/脏标记/词条态同步）。

页面：`manage/governance`「自我」（`renderGovernanceOriginal`，`pages/陪伴小屋/app.js`）。
本日先出 A 卷宗式 / B 手帐式 / C 舞台式三版创意稿对比，**已选定 B 手帐式**；
终稿为 [B-手帐式.html](B-手帐式.html)（自包含 HTML，浏览器直接打开；工具条可切
庭院/夜读主题、模拟 1366/900/650/390/320 五档宽度）。A、C 两份保留作对照。

示例数据为虚构角色「澄汐」，仅用于预览。

## 四条要求的落实（终稿已全部覆盖）

1. **配置项单独优化**：生日=日期选择 + 农历开关 + 「不确定年份」；性别/种族/自称/
   用户性别/关系/爱好/世界观适配模式=快捷词条（+自定义输入）；口吻示例=气泡编辑；
   标志性表达=可撕纸条；长文本=计字段落卡。后端合同不变：这些字段在注册表里仍是
   TEXT，控件形态由前端 spec 的 `inputs` 扩展（date / chips / quotes / tags）。
2. **适应页面大小**：1366 → 320 全覆盖；移动端单列化、词条条横向滚动、页签 2×2。
3. **切换不跳**：四页签与章节词条吸顶，切换只替换下方卡区；卡区保底高度
   （`.deck-panels` min-height）滚动条长度不突变；页签切换只在视口已越过页签区时
   吸附回页签顶部；章节切换完全不动滚动位置。
4. **创意表达**：字段级「✦ 灵感贴纸」（可换问法）+ 气泡台词 +
   「角色自述」第一人称画布；画布与「从人格底稿整理」双入口共用
   `role-profile-draft.js` 既有 dialog 与端点，草稿先过目再人工采纳。

## 终稿覆盖面（与后端 spec 逐字对应）

- `role_profile` 46 字段 = 8 章：identity 9 / appearance 6 / personality 2 /
  voice 7 / motivations 4 / boundaries 2 / world 8 / platform_names 8
- `relationship_profile` 7 字段（私聊限定；群聊空态文案见稿内注释）
- `knowledge` 14 字段 = import 7 / inject 3 / members 4
- 人格底稿 = `product.workspace("persona")` 嵌入工作区，位置不变

## 移植映射（四处改动点，稿内头部注释同此）

1. `app.js` `renderGovernanceOriginal` → 按终稿骨架重排；容器 id 不变：
   `roleProfileConfigWorkspace` / `relationshipProfileConfigWorkspace` /
   `knowledgeConfigWorkspace`；persona 页签保持嵌入 iframe。
2. `self-page.css` → 换成终稿 `<style>` 的「页面本体」段（保留 reduce-motion 与
   `data-motion` 覆盖）。
3. `workbench-page.js` → `inputs` 新增 date / chips / quotes / tags 形态；
   `role_profile`、`relationship_profile` spec 增加 inputs 声明；
   `world_adaptation_mode` 用 chips 单选呈现（已有 choices）。
4. `role-profile-draft.js` → 「角色自述」画布内容写入 supplement 后走原 generate
   端点；`data-role-profile-draft-open` 入口从横幅改到自述卡页脚。

汇报钩子（`updateRoleProfileSummary` 只改选择器）：`data-profile-name` /
`data-profile-emblem` / `data-profile-count` / `data-profile-progress` +
`data-profile-fill` / `data-profile-status`；速览贴纸对应原五条
`data-profile-signal` 信号（身份/识别点/性格/口吻/世界）。

已验证：桌面 1400px 首屏、章节切换（含角色自述）、世界知识页、夜读主题、
390px 窄屏（单列 + 词条横滚）。修复记录：章节卡与展示类同名时 `display:none`
会被后写的 `display:grid` 覆盖，已用 `.deck-panel:not(.active){display:none}` 锁定。

页头已按反馈瘦身为紧凑单行卡：头像 64px + 名字行（含连接徽标）+ 速览贴纸行 +
40px 完成环与计数，删除了 kicker 与简介行；页头下的灵感条也已按反馈整体删除，
页签同步压矮。≤650 贴纸改
横向滚动（`white-space:nowrap` + `flex:none` 防止被压缩），≤380 隐藏计数文字、
仅保留进度环的 aria 汇报。

视觉再收敛（同日反馈）：输入框安静化——常态只有底色，悬停浮现细边，聚焦才亮
描边，身份证卡内此前未接管的输入框一并统一；全部和纸胶带装饰移除，贴纸与
标志性表达纸条拉正为直排小片，主题变量补充 `color-scheme` 改善原生控件暗色观感。

实施仍按仓库约定：改完源码后从当前源码构建交付包，再统一跑宿主加载、停机、
路由注销与相关页面检查。
