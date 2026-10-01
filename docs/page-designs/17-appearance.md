# 17 · 外观与设置（`manage/appearance`）

代码位置：`renderAppearancePage`（`pages/陪伴小屋/app.js:1276-1278`）+ `appearancePanel`（`app.js:914-930`）；主题注册表 `theme.js`；维度存取 `product-page.js:53-59,262-272`。

## 一、页面功能

拓展页**自身的显示方式**：主题、显示维度、文字辅助。页面自带「仅影响拓展页」chip 与「不修改插件业务配置」说明（`app.js:1276-1278`）。

## 二、展示部分

外观面板（`appearancePanel`，`app.js:914-930`）：

| 维度 | 选项 | 证据 |
| --- | --- | --- |
| 主题 | 六套：courtyard 庭院 / dawn 晨雾 / dusk 暮色 / night 夜读 / walnut 深林 / contrast 高对比；浅/深两组色卡（`data-theme` 真实渲染）+「跟随小屋光照」开关 | `theme.js:19-26`；`app.js:924-926`；色值在 `tokens.css` |
| density 密度 | 紧凑/标准/宽松 | `app.js:915`（appearanceGroups `:914-919`） |
| radius 圆角 | 方正/标准/圆润 | 同上 |
| typeScale 字号 | s/m/l/xl | 同上 |
| motion 动效 | 完整/减弱/关闭 | 同上 |
| 文字辅助 | 放大辅助文字（state.largeText）；「系统减少动效」只读 pill | `app.js:929` |

## 三、配置部分

**无业务配置组**——全部浏览器本地：

| 项 | 存储 |
| --- | --- |
| 主题/密度/圆角/字号/动效 | localStorage `companion-v2-theme` / `-density` / `-radius` / `-type-scale` / `-motion`；跟随光照 `companion-v2-theme-follow-light`（`product-page.js:47,53-59`） |
| largeText / reduceMotion | localStorage 键 `companion-framework-ui-preview-v2-config-20260924`（`app.js:20,79-80,1540`） |

写入 `setAppearance`（`product-page.js:262-272`）；主题切换整页叠化 crossfade，并 postMessage 同步到 iframe 工作区（`:233-261,269-270,297-299`）；iframe 内由 `embedded-bridge.js:12-40` 应用到 `documentElement.dataset` 并派发 `companion-appearance-change`/`companion-theme-change`。动效维度取「用户设置」与「系统偏好」中更严格的一方（`app.js:84-89`）。

旧主题名自动迁移：mist→dawn、grove→courtyard、coral→dusk、light→dawn、dark→night（`theme.js:33-50`）。

## 四、边界与空态

不写角色资料、不影响消息发送；工作区（iframe）内的外观跟随父页下发，不在工作区内单独配置。

## 五、后端情况

**无任何后端依赖**（纯前端 + localStorage）。

## 六、相关设计稿与复核

- 工作区嵌入与桥接 → [README.md](README.md) 第二节。
- 复核：`grep -n "companion-v2-theme" pages/陪伴小屋/product-page.js`。
