# 家具与拓展面板设计（2026-09-29）

对象：陪伴小屋首页的**家具 / 拓展入口**——场景里的家具、首页速览条、家具目录，以及它们打开的下方面板。
口径：现状以工作区代码为准，每条带 `文件:行号`；本文只做设计，不改代码。

配套阅读：`pages/陪伴小屋/STRUCTURE.md`（家具映射与导航）、`docs/PAGE_DISPLAY_AND_CONFIG_DESIGN_20260929.md`（呈现层）、`docs/V1_TO_V2_UI_AUDIT.md`（V1 家具业务对照）。

---

## 一、现状（可复核）

**四份清单，彼此不完全对齐：**

| 清单 | 内容 | 出处 |
| --- | --- | --- |
| 家具目录 | **14 项**：日记书桌 / 生活挂历 / 睡眠与梦境 / 阅读角 / 相框与相册 / 成长花架 / 见闻电台 / 创作书架 / 画面工作室 / 共处电话 / 游戏棋桌 / 屏幕台 / 现实设备台 / 直播与表演 | `app.js:735-750` |
| 首页速览条 | **7 项**：书桌 / 挂历 / 书架 / 床 / 电台 / 花架 / 衣柜陈设 | `app.js:322-330` |
| 体素包机位表 | **7 个有机位**（calendar/desk/shelf/wardrobe/bed/radio/garden）＋ **4 个只有 label 没有机位**（game/image/together/art） | `assets/voxel-source/panels/home-room-3d.source.js:10-20` |
| 外壳可选家具 | `STAGE_STATIONS` ＝ 与包一致的 **7 个** | `shell.js:30`；契约测试钉住同一集合 `tests/test_entrance.cjs:29-31` |

**两条打开路径，行为不一致：**

| 路径 | 代码 | 行为 |
| --- | --- | --- |
| 家具目录行「打开」 | `openFurniture`（`app.js:216`） | 有 `tab` → 走旧路由 `navigate('life', tab)`；否则 `showDetail(detail)` 弹窗 |
| 速览条 / 场景点选 | `chooseFurniture`（`app.js:558`）→ `shell.selectFurniture` → `renderShell` | 换下方面板（`renderFurniturePanel`） |

**面板出口四个**：`renderFurniturePanel`（`app.js:362`，**只按 `station` 找家具**）、`renderHomePanel`（`:404`）、`renderSectionPanel`（`:433`，renderer 表里**没有** growth/state/reply/preferences/base）、`renderViewPanel`（directory / observation / state / diary）。

**今天面板里有真实内容的只有 4 类**：日记书桌与睡眠与梦境（嵌 `life` 工作区的 archive/sleep 标签）、生活挂历（嵌状态工作台）、成长花架（嵌 `product.growthMarkup()`）；其余是「说明卡 ＋ 打开 / 相关配置 / 在房间里移动它」三个按钮。

---

## 二、缺口清单

| # | 缺口 | 证据 | 玩家感受 |
| --- | --- | --- | --- |
| G1 | **8 件家具没有机位**：阅读角 / 相框与相册 / 画面工作室 / 共处电话 / 游戏棋桌 / 屏幕台 / 现实设备台 / 直播与表演 | 目录里的 `station` 分别是 `lounge` / `art` / `image` / `together` / `game` / `ext-…001` / `ext-…002` / 无；前四个里后三个在包里只有 label、`lounge` 连 label 都没有；`ext-…` 两个**在包里不存在** | 速览条上没有它们；目录里点「定位」镜头静默回落到全景（`test_entrance.cjs:13-14` 明确这是既有语义） |
| G2 | **陈旧机位 id** | 目录写 `ext-000000000000000000000001/002`（`app.js:747-748`），包与外壳表里都没有 | 同上，点击无反应也不报错 |
| G3 | **面板只认机位** | `renderFurniturePanel` 用 `directory.find(item=>item.station===id)` 反查（`app.js:368`） | 没有机位的家具**永远没有面板**，只能弹一个通用对话框 |
| G4 | **见闻电台指向不存在的能力** | `detail:'discoveries'` → `cap='news'`（`app.js:1505`）→ `providerDetail('news')`；能力目录只有 8 项：legacy / content / image / reality / screen / together / game / live（`astrbot_host/integration_catalog.py`，`news` 零命中） | 点开是一个标题为「拓展能力」的弹窗，正文是「尚未读取此插件状态，请刷新能力目录。」——**刷新也修不好**，因为根本没有这个提供方 |
| G5 | **旧页签在详情路径上静默回落**（两处） | ①成长花架：`showDetail('growth')` → `navigate('manage','growth')`（`app.js:1500`）→ `manageTab='growth'` → `renderSectionPanel('growth')` 无 renderer → `return renderHomePanel()`（`:442`）；②生活挂历：目录行 `openFurniture` 走 `navigate('life','state')`，而 `lifeTabs` 只有 home/schedule/diary → `lifeTab='home'`（`app.js:112-114`） | 从目录点「打开」，面板回到小屋总览，看不出是"没做"还是"点错了" |
| G6 | **目录行与速览条走两套模型** | G1 的两条路径（`openFurniture` 走路由/弹窗，`chooseFurniture` 走外壳） | 同一件家具从目录进和从速览条进，落点不同 |
| G7 | **陈设与能力混在一条操作条上** | 速览条有「衣柜陈设」且 `wardrobe` 有机位，但它**不在家具目录**里；能力侧真正相关的是 `wardrobe` / `photo.reference` 两个配置组（产出 C1） | 用户分不清「衣柜」是房间陈设还是能力 |
| G8 | **5 件拓展家具只有通用状态弹窗** | `capabilitySurface` 只实现 `reality` / `together`（`app.js:1424-1425`）；content / image / game / screen / live 走 `providerDetail` 通用面板（`product-page.js:602-605`） | 点开只有「插件版本 / 配置开关 / 执行就绪」三行 |
| G9 | **直播与表演既无机位也无专属面** | 目录项无 `station`（`app.js:749`）；STRUCTURE.md 亦写「目录入口暂无场景家具」 | 只能从目录打开一个通用弹窗 |

---

## 三、设计原则

- **P1 每件家具都有面板。** 面板由**家具 id** 驱动，不从 `station` 反查——机位只是"能不能飞过去"。
- **P2 机位与面板解耦。** 没有机位不导致没有面板：目录行、速览条、场景点选三条路都通向同一个面板。
- **P3 面板三段式**（沿用全局规则）：**展示**（只读合同）→ **可配置**（组/字段/作用域/入口）→ **边界**（没有合同的由谁保存、去哪儿做）。
- **P4 目录与场景共用一份 `directory`**：机位表是它的子集（`station` 有值即有机位），不再维护第二份"能选的家具"清单。
- **P5 速览条只放「能飞且常用」的**：现状 7 项保留；其余 7 件从目录或面板进入，等机位补齐后再进速览条。
- **P6 提供方自持的一律只给口径 + 入口**（现有 `capabilitySurface` 的做法），不在本页造设备/房间/作品的假值。

---

## 四、逐件规格

> 「机位」列：`有` = 包里有相机；`仅摆件` = 包里有模型与 label 但无相机；`无` = 需要新增或明确不做。
> 「面板」列写展示 / 可配置两段；「入口」写面板之外的出口。

### 基础生活（7 件）

| 家具 | 机位 | 面板展示 | 面板可配置 | 入口 / 边界 |
| --- | --- | --- | --- | --- |
| **日记书桌** desk | 有 | 最近一篇日记（标题＋日期）、便签与提醒计数、今日是否已写 | `role.life` 写作段（日记风格、梦境题材）｜入口：日记页 | 已实现（嵌 `life/archive`）；把设置段从自我页挪来即可 |
| **生活挂历** calendar | 有 | 今日安排、进行中活动、下一次提醒 | 日程与提醒的新增/改期走日历编辑器 | 已实现（嵌状态工作台）；补一个「打开完整日程」按钮 |
| **睡眠与梦境** bed | 有 | 最近睡眠记录、梦境条数、当前休息判定是否生效 | `role.life` 作息段（睡眠开关/时刻/时长、休息判定、补看材料） | 已实现（嵌 `life/sleep`） |
| **阅读角** lounge | **无**（建议补：`BASE_CATALOG` 已有「阅读扶手椅」） | 在读作品、进度、最近片段、评分 | `library` 12 项（书架开关、偏好、低频触发） | 入口：学习与反思 L3；补机位后进速览条 |
| **相框与相册** album | 仅摆件（`art`，含「植物装饰画」挂画模型） | 已保存照片（原件缩略）、最近采纳的生成图 | `conversation.media_quota` / `image_review`（在产出 C1） | 入口：产出 C1；补机位 |
| **成长花架** garden | 有 | 目标/技能列表、待确认提案数、来源数 | 成长读取/建议/技能/日程影响（`role.growth`） | 已实现；**修 G5**：详情路径改走外壳分区而不是没有 renderer 的旧页签 |
| **见闻电台** radio | 有 | 订阅来源与开关、最近读取状态（**没有读取合同，只给口径**） | 资讯配置（感知 A4 的 `nativeNewsWorkspace` 字段） | **修 G4**：`detail` 改指感知 A4，不要指向不存在的 `news` 能力 |

### 可选拓展（7 件）

| 家具 | 机位 | 面板展示 | 面板可配置 | 入口 / 边界 |
| --- | --- | --- | --- | --- |
| **创作书架** content | 有（`shelf`） | 提供方状态（已安装/版本/就绪）、作品与原稿入口 | 创作模型档（模型与连接页） | 边界：原稿与作品由提供方持有，本页只给入口 |
| **画面工作室** image | 仅摆件（`image`：三脚架相机 / 拍立得展台 / 照片挂架） | 能力状态、今日张数阈值（**无用量聚合接口，只给上限**）、参考图与衣柜总闸 | `media_quota` / `image_review` / `photo.reference` / `wardrobe`（产出 C1 已接） | 补机位；不再只给"插件版本"三行 |
| **共处电话** together | 仅摆件（`together`：电话柜 / 壁挂电话） | 口径卡：当前房间、可用模式、参与者**均在提供方页面** | 无（提供方自持） | 已有 `capabilitySurface('together')` ＋ 页面地址；补机位 |
| **游戏棋桌** game | 仅摆件（`game`：棋桌 / 街机 / 挂屏） | 五种玩法与对局入口（提供方页面）、对局记忆沉淀是否启用 | 对局记忆相关模型档 / 开关（`memory/game_ingestion`） | 补机位；面板补「哪些玩法在跑」的只读状态 |
| **屏幕台** screen | **无**（目录写的 `ext-…001` 不存在） | 识屏解读与日记素材开关状态、**最近一次解读结果**（`/perception-native` 有数据）、被拒与失败原因 | `screen` 3 项（感知 A3 已接） | 二选一：补一个空位机位（STRUCTURE.md 的"三维空位"），或把 `station` 置空并注明"仅目录项" |
| **现实设备台** reality | **无**（`ext-…002` 不存在） | 口径卡：设备目录 / 场所 / 镜头与声音覆盖 / 最近动作**均在现实触及页面** | 无（提供方自持） | 已有 `capabilitySurface('reality')` ＋ 页面地址；机位同上二选一 |
| **直播与表演** live | 无 | Live 提供方状态与已有配置（脱敏快照）、节目/场景入口 | 无（提供方自持） | 明确"无场景家具"（STRUCTURE.md 已这样写）；面板要补，不能只有三行状态 |

### 房间陈设

| 物件 | 机位 | 说法 | 决定 |
| --- | --- | --- | --- |
| **衣柜** wardrobe | 有 | 房间陈设；能力侧对应的是 `photo.reference`（每日穿搭）与 `wardrobe`（衣物进提示词与识图）两个配置组 | **从速览条移出**：陈设归「布置房间」，能力开关留在产出 C1；速览条腾出的位置给阅读角或相框（等机位补齐） |

---

## 五、机位补全（最小改动）

1. **补 4 个已有摆件的机位**：`game` / `image` / `together` / `art` 在包里已有 label 条目（`home-room-3d.source.js:18-19`），只需补 `target / position / fov` 三个数；`lounge` 需新增条目（摆件在 `BASE_CATALOG:23` 有"阅读扶手椅"）。
2. **屏幕台 / 现实设备台二选一**：要么在包里新增两个空位机位（沿用 STRUCTURE.md 的"三维空位与碰撞避让"），要么把目录里的 `station` 置空并注明"仅目录项"——**不能保留一个指向不存在机位的 id**。
3. **三处表必须同步改**：包 `BASE_STATIONS` → `shell.js:30` 的 `STAGE_STATIONS` → `app.js:322-330` 的 `STAGE_BAR_ITEMS`；同时改契约测试里的常量 `tests/test_entrance.cjs:31`（否则那条"对表"断言会红）。
4. **速览条扩容要克制**：先补机位，再按"是否每天会点"决定进不进速览条；衣柜移出后建议先补阅读角。

---

## 六、实现优先级

| 级 | 事项 | 理由 |
| --- | --- | --- |
| **P0** | 修 G4（见闻电台指向不存在的能力）、G5（成长花架与生活挂历的详情路径静默回落）、G2（陈旧机位 id） | 都是"点了没反应或去错地方"，用户直接感知 |
| **P0** | 面板与机位解耦（P1/P2）：`renderFurniturePanel` 改按家具 id 取内容，目录行也走同一个面板 | 一次改动让 8 件家具都能有面板 |
| **P1** | 补 5 个机位（game/image/together/art/lounge）＋ 三表同步＋改测试常量 | 让"能飞"的家具有 12 件 |
| **P1** | 衣柜移出速览条，陈设与能力分开（G7） | 消掉一个语义混淆 |
| **P2** | 按 §四 逐件补面板内容：优先 screen（有真实解读数据）、image（配置已接）、game、content、live | 从"有数据可展示"的开始 |
| **P3** | 阅读角 / 相框的阅读与相册视图（依赖 library 与 assets 的读取合同） | 数据侧已具备，属展示层工作 |

---

## 七、验收

- **既有契约**：`tests/test_entrance.cjs`（机位对表，32 项）、`tests/test_shell.cjs`（外壳选择模型）、`tests/test_home_styles.cjs`。
- **新增契约（建议）**：
  1. **每件家具都要有出口**：遍历 `directory` 的 14 项，断言每项都能得到一个面板（`renderFurniturePanel` 或 view），没有落到兜底文案的；
  2. **机位一致性**：`STAGE_STATIONS ⊆ 包 BASE_STATIONS 且都有相机坐标`，`STAGE_BAR_ITEMS ⊆ STAGE_STATIONS`；
  3. **能力入口一致性**：`directory` 里带 `cap` 的项，其 `detail` 必须能解析到已注册的能力或明确的基础设施入口（防 G4 复发）。
