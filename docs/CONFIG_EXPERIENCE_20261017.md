# 配置编辑体验整改记录

日期：2026-10-17。范围：唯一公开拓展页「陪伴小屋」里的**配置编辑**体验——保存、校验、离开、键盘与串读。功能合同（API 路径、令牌、鉴权、作用范围）一条没动。

上一轮（[拓展页外壳设计整改](SHELL_DESIGN_PASS_20261017.md)）修的是外壳几何与主题对比度；这一轮的入口是「改配置时到底哪里别扭」。

## 一、先量出来

配置表单在无宿主时只显示「角色与会话目录暂未读到」，所以看不到真实编辑态。为此搭了一个台架（`build/config-harness/`，**不进交付包**）：真实 `workbench-page.js` 内核 + 合成字段（25 个字段、3 个模块），并用真实 `tokens.css / console.css / workbench.css / shell.css` 渲染，外层套真实的 `.shell-panel` 与 `#homeShell[data-away=true]`。

整改前在 1440×900 上实测：

| 观察点 | 结果 |
| --- | --- |
| 动作条位置 | `position: static`，位于 1191px 文档的 y=1121；改中间字段要滚到底才能保存 |
| 非法值保存 | 提示条画在**卡片顶部**，`noticeInViewport: false`；焦点丢到 `body`；`aria-invalid` 数量 0（重绘抹掉）；字段无任何变化 |
| 字段说明与错误的关联 | `aria-describedby` 0 处，错误槽 0 个 |
| Ctrl/⌘+S | 无处理，触发浏览器「保存网页」对话框 |
| 切走未保存的草稿 | 无提示、无痕迹（`unmount()` 直接清空） |
| 窄屏 | `console.css` 用 650px，而外壳在 760px 已经切成手机布局 |

最要命的是第二行：**按了保存，界面看起来什么也没发生**。提示条在顶部、用户在底部、光标也被重绘冲掉。

## 二、改了什么

### 1. 吸底动作条（`workbench.css` + `shell.css`）

`.wb-actions` 改成 `position: sticky; bottom: 0`，带不透明背景与上缘投影。保存按钮、`使用已保存配置`、`有未保存的改动` 从此始终在视口下缘。

配套两处 `overflow`：`.wb-card` 与 `.shell-panel` 从 `hidden` 改为 `clip`。`hidden` 会把元素变成「不可滚动的滚动容器」，sticky 的参照盒就变成它自己，吸底永远不生效；`clip` 只裁剪、不建立滚动容器，圆角裁切效果一致。窄屏卡片有 16px 内边距，动作条用负边距重新贴到卡片两边。

面板右下角有那间小屋子（画中画），动作条在 `#homeShell[data-away="true"]` 下把右侧让开 `--shell-pip-w`，按钮与提示都不会被压住（实测 `padding-right: 192px`）。

### 2. 字段级错误 + 跳到出错项（`workbench-page.js`）

- 每个字段渲染一个 `<p class="wb-field-error" data-wb-field-error id=…>` 错误槽；说明文字也带上 id。
- `paint()` 之后统一 `wireFieldDescriptions()`：把说明与错误的 id 挂到控件 `aria-describedby` 上（数字框、文本、多行、枚举、开关、日期、词条七种控件共用一处逻辑，不逐分支插属性）。
- 校验失败时不再只写一句通用文案：`explainInvalid()` 按字段类型分情形生成——超字数说「已超过 N 字上限（当前 M 字）」、开关说「只能是开或关」、数字类型错说「要填数字（当前填的不是数字）」、越界说「要填 X 到 Y 之间的数」。然后 `markInvalid()` 给该行加 `.is-invalid`（左侧红条 + 控件红边）、写入错误文本、`scrollIntoView` 并聚焦控件。
- 已标红的字段在输入过程中自动复核：改对了立即撤掉标记，还不对就更新提示（字数从 340 降到 330 时提示要跟着变）。没标红的字段不在打字时报红。
- 提示文案尾部补一句「改动还在，改好这一项就能保存。」——避免用户以为保存已经生效。

### 3. Ctrl/⌘+S（`workbench-page.js`）

并进已有的 `onSectionKeydown`，`preventDefault()` 后保存当前分区。**没有再挂一个 keydown 监听器**：同一根元素上两个 keydown 在真实浏览器里没事，但在只存单个监听器表的宿主/测试环境里会互相覆盖（本轮就是这么踩到的：`test_memory_settings_workbench` 里方向键切换模块突然失效）。

### 4. 离开前拦截未保存的草稿（`app.js` + `workbench-page.js`）

- 内核维护 `LIVE` 实例集，导出 `dirtyEditors()`；`mount()` 登记、`unmount()` 注销。
- `app.js` 新增 `guardUnsaved(run)`：有未保存草稿时用页面自己的确认框问一次（「放弃改动」/「回去保存」），确认后才执行原导航。挂在五个入口上：左栏分区、家具、整页视图、回到小屋、标题栏的 `data-manage` 跳转。没有草稿时零摩擦（直接执行，不弹窗）。
- 另外挂了 `beforeunload`：刷新/关页签同样会丢草稿，浏览器只允许用原生提示拦。

### 5. 断点对齐（`console.css`）

配置控制台的窄屏断点从 650px 改为 760px，与外壳栅格的切换点一致。此前 651–760 之间外壳已是手机布局，控制台仍是两列并排。

## 三、验证

整改前后各跑一次**同一套台架脚本**（台架 HTML 相同，只换 `pages/陪伴小屋/` 下的真实文件）：

| 指标 | 整改前 | 整改后 |
| --- | --- | --- |
| 动作条 `position` / 是否在视野内 | `static`，桌面在 981px 文档的 y=894；停在表单顶部时**视野里没有保存按钮** | `sticky`，始终贴在视口下缘（桌面 900 / 平板 1112 / 手机 844） |
| 非法值保存后 | 顶部一句通用文案「请核对数值类型与范围。」；出错字段毫无变化；焦点落到 `body`；`aria-invalid` 0 处 | 跳到出错字段、标红、行下写明「每轮最多条数要填 1 到 60 之间的数。」；焦点落在 `input[quota]`；`aria-invalid` 1 处 |
| `aria-describedby` / 错误槽 | 0 / 0 | 25 / 25 |
| 字段说明与错误的关联 | 无 | 控件的 `aria-describedby` 指向说明与错误两个 id |
| Ctrl/⌘+S | 不生效（`saved:false`，触发浏览器保存网页） | 保存成功（`wb-save is-saved`，提示「与已保存一致」） |
| `dirtyEditors()` | 不存在 | 编辑后返回 `[{group:"harness",title:"台架分区"}]`，保存后清空 |
| 面板内吸底（真实 `.shell-panel` 包裹） | — | 仍生效（`shell-panel` 的 `overflow: clip` 不破坏 sticky） |
| 吸底条与画中画的避让 | — | `padding-right: 192px`（176 + 16），按钮与提示都不被小屋子压住 |

注意「提示是否在视野内」这一项：短表单上整改前的顶部提示恰好也在视野里，所以**真正的差别不是"看不看得见提示"，而是"看不看得出是哪个字段、下一步点哪里"**——整改前只能靠人自己在一屏字段里找，整改后直接落在那一项上。

页面测试：`tests/test_config_editor.cjs` 75 项、`tests/test_expression_page.cjs` 7 项、`tests/test_memory_settings_workbench.cjs` 6 项、`tests/test_reply_page.cjs` 34 项、`tests/test_shell.cjs` 15 项、`tests/test_theme_registry.cjs` 16 项全部通过。

其中两条断言随文案一起更新（它们断言的是旧文案，行为主张没变）：

- `test_config_editor.cjs`「life audit blocks a malformed clock or timezone」：由断言通用句 `/数值类型与范围/` 改为断言标签与区间（`/自然浮动上限/`、`/0 到 120/`、`/改动还在/`），「不发请求」的原断言保留。
- `test_expression_page.cjs`「a value with the wrong field type never dispatches」：由 `/范围/` 改为 `/只能是开或关/`（开关填错类型的合理提示），「不发请求」的原断言保留。

另有一条测试的**取选择器方式**收紧了：`test_product_workspaces.cjs` 原来用 `\.stage-role\s*\{` 找基础规则，本轮新加的缩略态规则（`#homeShell[data-away="true"] .stage-role{display:none}`）排在它前面，于是断言取到了另一条规则。改成锚定行首后，实测 40 项通过。

`tests/` 全量 `*.cjs` 对照（同一套跑法，本工作树 vs `HEAD` 干净工作树）：两边失败集合一致——`test_learning_hub`（断言 config-editor 源码里的一段字面量）、`test_native_extension_panel`（缺模块，导入即失败）、`test_room_editor`、`test_section_wiring`（`groupInterjectionConfigWorkspace` 不在面板挂载清单里）。这四项在 `HEAD` 上同样失败，属既有问题，未在本轮处理。

## 四、没做 / 待定

1. **草稿不跨实例保留**：「切走再切回来草稿还在」需要把每个分区的草稿与基线版本一起持久化，并处理「草稿比服务端旧」的冲突。现在的选择是**拦一次**而不是**留一份**——前者不会产生过期草稿被误保存的风险。内核里那条注释（「草稿由工作台自行从 sessionStorage 恢复」）实际只对「未确认的保存请求」成立，注释与实现不一致，已在本文记录，未改注释以外的行为。
2. **`wb-actions` 在超长表格/日志类分区**（治理与维护的排行、诊断表）会盖住最后一行的一部分，靠底部内边距让开；这些页自己有内层滚动容器，未逐页核对。
3. **字段错误只在保存时标注**：输入过程中不主动报错（避免噪声），所以「一开始就非法」的字段要等第一次保存才亮。
4. **`data-manage` 跳转已拦**，但页面里还有一些直接调用 `navigate()` 的按钮（例如空状态里的「前往账号与会话」）没走 `guardUnsaved`；这些按钮所在的分区通常没有草稿，风险低，未逐个接。
5. **保存成功的回执仍只在卡片顶部与按钮内**：短表单没问题，长表单吸底动作条上的「已保存」勾是主要反馈，未再加 toast。
