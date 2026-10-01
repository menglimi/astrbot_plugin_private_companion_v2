# 陪伴小屋 · 页面「展示什么 / 怎么展示 / 可配置什么 / 怎么配置」

> 现行配置归属已由 [CONFIG_ALLOCATION_20261001.md](CONFIG_ALLOCATION_20261001.md) 更新；本文保留为 2026-09-29 的历史设计依据。

日期：2026-09-29。对象：唯一公开拓展页「陪伴小屋」（`pages/陪伴小屋/`）与其宿主合同（`astrbot_host/`）。

与前一份文档的关系：`PAGE_DISPLAY_AND_CONFIG_DESIGN_20260928.md` 定的是**职责与归属**
（哪个配置组归哪一页、A/B/C/D/E/L 分区编号怎么收敛）。本文不重复那部分，只补两件它没覆盖的：

1. **参考 V1 的实际结构**——V1 做对了什么、哪些结构性问题必须不继承。
2. **呈现层**——每页「怎么展示」：用什么控件、显示哪些状态、如何表达作用域与生效方式。

口径：现状一律以工作区代码为准，且**每个数字都能在本仓复核**（复核命令见 §7）。
本文描述设计目标，不代表已实现。

---

## 一、V1 的实际结构（从 `V1_PAGE_INVENTORY.json` 读出的）

来源：`pages/陪伴小屋/V1_PAGE_INVENTORY.json`（由 V1 的 `pages/陪伴面板/index.html`
静态提取，不读生产数据）。

| 事实 | 数值 |
| --- | --- |
| 导航项 | 17 个，其中 3 个默认隐藏（创作 / 生图 / 现实触及） |
| 面板 | 19 个 |
| 字段总数 | 172（`panel-roleplay` 最多 56，`panel-config` 33，`panel-learning` 22） |
| 按钮总数 | 176（`panel-home` 单一面板 39 个） |

导航到面板基本是 1:1（`dashboard / home / roleplay / private / group / learning /
memory / proactive / creative / tokens / troubleshooting / config / image / models /
qzone / experimental / prompts / reality`）。

### 1.1 V1 做对、应当继承的三件事

1. **面板内先分组再平铺。** `panel-config` 有 18 个标题把 33 个字段切成
   「通用设置 / 外部主动能力 / 群聊名单 / 配置迁移 / 存储方式 / 资源配额 / 功能开关…」。
   字段不是一长条，而是先有语义段落。V2 内核的 `sections` 就是这个思路的正式化。
2. **危险动作与日常动作分开。** 导出快照、重新检查、配置、查看排障在同一行但语义不同；
   `panel-home` 的 39 个按钮里混着「逛小屋」这类纯浏览与「布置房间」这类写操作。
   V2 要把它变成显式的按钮等级（普通 / 主要 / 危险）。
3. **只读视图与表单并存。** `panel-dashboard` 有 17 个标题、6 个按钮、**0 个字段**——
   它是一个纯展示面板。说明 V1 已经区分「看」与「改」，只是没有形成规则。

### 1.2 V1 的结构性问题（V2 必须偏离）

| 问题 | 表现 | V2 的对策 |
| --- | --- | --- |
| 平面导航 | 17 项平铺，私聊/群聊/学习/主动/创作互相平级，用户不知道「先看哪个」 | 三层：小屋（看）→ 能力配置（改）→ 专题配置（管）；见 §3 |
| 字段与按钮混排 | 同一面板既是表单又是工具栏（39 按钮 + 12 字段） | 每页三段式：展示 / 可配置 / 边界（R2） |
| 空面板 | `panel-experimental` 与 `panel-reality` 是 0 字段 0 按钮的空壳，仍占导航 | 无合同就不建页；有页必说明「为什么现在没有」 |
| 无作用域概念 | 单安装单目标，字段不标作用范围 | `layers` 由后端下发，窗口级必须先选对象+角色（R3） |
| 配置双入口 | 同一设置在 `config` 与专题面板各有一份 | 一个组只有一个「可写归属页」（R1） |

**结论：V1 的分组方法论可继承，导航与页面骨架不可继承。**

---

## 二、V2 的分层（为什么这样分）

```
小屋 life/home            她怎么样、今天发生了什么        ← 只读总览
日程 life/schedule        已定下的事与进展                ← 少数写操作（日历）
日记 life/diary           日记/阅读/睡眠/执行 + 生活例程    ← 写作与作息配置
人物 people               认得谁、关系怎样                ← 只读 + 跳转工作区
记忆 memories             事实与来源治理                  ← 只读工作台

能力配置（六个，各持自己的配置组）
感知 perception          能得到什么信息
决策 decision            怎么判断
行动 action              除回复外的行为
产出 output              产出什么
表达 expression          怎么说话
自我 governance          她是谁、权限怎么分

专题配置（六个，管理视图 + 跳转）
关系与权限 / 主动与联系 / 记忆与经历 / 学习与反思 / 模型与连接 / 治理与维护

设置（四个）
开始使用 / 外观与设置 / 宿主管理 / 资料与维护
```

**分层依据是操作意图，不是模块归属**：V1 按「私聊面板 / 群聊面板」分，用户得先知道
功能属于哪个模块才能找到它。V2 按「我想看 / 我想改它怎么想 / 我想管它」分。

---

## 三、每页展示什么、怎么展示

### 3.1 三段式骨架（R2 的落地形态）

每页按固定顺序渲染三段，**缺哪段就说清为什么缺**：

| 段 | 内容 | 数据来源要求 |
| --- | --- | --- |
| ① 展示 | 只读状态、证据、回执、来源 | 必须有真实查询合同；没有就进边界段 |
| ② 可配置 | 组 → 字段 → 控件 | 走工作台内核，有 `layers` 与生效方式 |
| ③ 边界 | 没有合同的部分：谁保存 / 现在能做什么 / 下一步 | `boundaryCard`，不放假控件 |

### 3.2 撑起全站的五个可复用呈现件

这些是「怎么展示」的核心，各页按需引用，**不各写一份**：

1. **继承轨迹（`wb-rail` + `wb-chip` + `wb-ghost`/`wb-live`）**
   字段被上层覆盖时，标签同时显示「被覆盖的值（幽灵）」与「实际生效的值（实值）」，
   右侧 chip 写明「继承自安装/角色」，并给「恢复继承」按钮。
   依据：`workbench-page.js` 的 `fieldMarkup`（继承态分支）。这是 V1 完全没有的能力——
   V1 单层，看不见值从哪来。

2. **生效方式标记**
   控件旁明写 `立即生效` 或 `下一轮生效`（R6）。窗口级设置切换对象时不携带草稿。
   反例：V1 的 `<input type=checkbox>` 不带任何时机说明，用户改完不知道什么时候起作用。

3. **边界卡（`boundaryCard`）**
   三段固定文案：由谁保存 / 现在能做什么 / 下一步去哪。用于「后端确实没有合同」的地方，
   避免 V1 那种「空面板照常占位」或「放个点了没反应的开关」。

4. **分区锚点 + 引用卡**
   有控件的页显示 `A1/B3/…` 锚点；引用页只显示状态卡并注明「控件在 X 页」。
   解决 V1 的「配置双入口」与 V2 现状的「同一编号在多个页面各出现一次」。

5. **回执与幂等提示**
   保存走 `ConfigurationService.patch`，成功给回执，`edit_token` 冲突给明确提示，
   失败一律翻译成人话（错误码表在 `workbench-page.js` 的 `errors`）。

### 3.3 逐页：展示 / 控件 / 边界

> 「控件」列写**用什么形态**，不是字段清单（字段清单在既有文档 §1.2 与账本里）。

| 页面 | 展示什么（只读） | 用什么控件 | 边界（不放什么） |
| --- | --- | --- | --- |
| 小屋 `life/home` | 体素小屋、当前状态六项、今日日程、记录四视图、能力接入状态 | 无表单；「布置房间」是浏览器本地偏好，明标不写业务配置 | 主动候选池、用量余额（无查询合同）→ 空态 + 跳转 |
| 日程 `life/schedule` | 计划 / 已接受约定 / 提醒 / 进行中活动，计划与进展分列 | 日历编辑器（新增/改期/取消），每条带状态 | 重复规则与改期回执（合同未定） |
| 日记 `life/diary` | 四视图 + 原文与来源范围 + 失败重试 | **`role.life` 23 项**：时刻用 `input[type=time]`、时区用 `input + datalist`、时长用数字、"休息时段回复判定"用四段 `sections` | 梦境≠事实，执行记录不推算 |
| 人物 `people` | 关系审阅队列、相识目录（跨群私聊同一人） | 本页只读；`person` 2 项在决策 B1 | 身份归并需单独协议 |
| 记忆 `memories` | 六视图治理台（事实/经历/来源/修订/冷归档/迁移） | 本页无配置；策略在决策 B1 | 跨主体不共享 |
| 感知 `perception` | A1 环境 / A2 消息内信息 / A3 屏幕设备 / A4 资讯 | `conversation.perception` 9、`knowledge` 14、`screen` 3；语义与黑话走 `/semantic` | 识屏是否进对话以能力目录为准 |
| 决策 `decision` | B1 记忆策略 / B2 关系审阅 / B3 状态 / B5 群参与 | `memory` 30、`person` 2、`role.state` 61、`group_participation` 20 | B4 只放引用卡（控件在主动与联系） |
| 行动 `action` | 提供方接入状态与原因 | 无自有组（提供方自持） | 不放生图参数 |
| 产出 `output` | C1 生图与相册 / C2 作品与版本 | `media_quota` 4、`image_review` 11、`photo.reference` 3、`wardrobe` 6 | 生图参数归提供方 |
| 表达 `expression` | D1 分段预演（不调模型）/ D2 语音 / D3 表情 / D4 撤回 | `presentation` 已接 32、`reaction` 9、`recall` 4 | 戳一戳与群投递无动作开关 |
| 自我 `governance` | E1–E5 导航与状态 | **本页不持配置组** | E3 风控刻意不给开关 |
| 关系与权限 `identity` | 身份工作区、三档权限、相识目录 | 无自有组（只读） | 旧身份归并 |
| 主动与联系 `contact` | 联系节奏 13 类、免打扰、沉默门槛 | `proactive.contact` 158（已接 74）、**`busy_gate` 7（待挂载）** | 候选池无查询合同 |
| 记忆设置 `memory` | 策略工作台 | 只放引用卡（控件在决策 B1） | 事实正文不在本页编辑 |
| 学习与反思 `learning` | L1 表达学习 / L2 黑话 / L3 书架 / L4 反思 / L5 梦境压实 | `expression.learning` 10、`library` 12、`role.growth` 2 | 梦境压实仍是设计稿，不标可用 |
| 模型与连接 `models` | 15 个任务档的路由矩阵 + Provider 测试 | `model.*` 全部已接；测试与保存分离 | 凭据不回显 |
| 治理与维护 `maintenance` | 预算、宿主状态、用量（只说明）、诊断（未接） | `model.budget` 2 | 不画编造的费用曲线 |
| 开始使用 `setup` | 四步状态与阻断原因；草稿只读预览 | 无配置组；写授权与生命周期 | 没看过回复不许开真实发送 |
| 外观与设置 `appearance` | 主题、五维显示、房间布置 | 浏览器本地 | 不写角色资料 |
| 宿主管理 `host` | 运行状态、会话与投递授权、最近失败 | 无配置组；写 `staging/*` 11 条 | 启停是管理员操作，不与日常按钮混排 |
| 资料与维护 `data` | 备份预览 → 确认 → 回执 | 无配置组 | 备份是安装级合同 |

---

## 四、控件类型映射（怎么配置）

控件形态由后端下发的契约决定（`contract_of`），页面不硬编码。现有映射
（依据 `workbench-page.js` 的 `controlMarkup`）：

| 契约 | 渲染 | 备注 |
| --- | --- | --- |
| `kind=bool` | 开关 + 「已开启/已关闭」文字 | 不只靠颜色 |
| 有 `choices` | `<select>` | 空值合法（表示「跟随上级」），不自动补选中项 |
| 有 `catalog`（读取后才知道选项） | `<select>` | 当前值不在目录里时补「暂不可用」，避免静默改写 |
| `kind=text` + `input=time` | `<input type=time>` | 时刻 |
| `kind=text` + `input=line` | `<input type=text>`（可带 `datalist`） | 单行、时区名等 |
| `kind=text` 默认 | `<textarea>` | 长文本 |
| `kind=int/float` | `<input type=number>` + 范围提示 | 0–1 的 float 自动加 % |

**契约表达不了的规则归 owner。** `contract_of` 不发字符串长度，所以「≤80 字、单行、
无控制字符」这类约束由 owner 在 `preview_set` 与 `write` 两处把关
（`participation.py` 的 `validate_interrupt_text` 是范例）。页面**不得**为了好看
自行放宽或收紧，否则会出现「页面放行、后端拒收」。

### 4.1 需要前端补兜的两类形状

注册表只给 `kind` 与数值范围，以下两类形状必须由页面兜住，否则值会走到后端才被拒：

1. **`HH:MM` 时刻**（如 `diary_time` / `sleep_time`）：用 `input=time` +
   一个 `audit` 校验 `/^([01]\d|2[0-3]):[0-5]\d$/`。
2. **IANA 时区名**（如 `timezone` / `sleep_timezone`）：用 `input=line`，用
   `Intl.DateTimeFormat` 试构造来判有效性。
   `audit` 返回**单个错误码字符串**，不是数组（内核约定）。

---

## 五、编号与归属的唯一性规则

- **R5**：一个分区编号只有一个「持有控件的主页面」，引用页只显示状态卡。
- 归属唯一映射表见既有文档 §四（不在此重复）。
- **R1**：同一配置组不允许在两页各有一份控件。现状靠约定维持的几处（`life`、`recall`、
  `screen`）必须收敛。

---

## 六、当前必须修的三处（可复核）

1. **`busy_gate` 无挂载点（今天点不到）。**
   后端 `SECTIONS` 有它（`configuration_api.py:32`），前端 spec 有它，
   `app.js` **没有任何 `mountConfigEditor(..., ['busy_gate'])`**。
   复核：三方对账脚本给出「spec 有 / 未挂载 = `busy_gate`」，其余 15 项都有挂载点。
   修法：补一个容器 + 一行挂载，落主动与联系页 B4。

2. **5 个无入口页签**（`growth`/`base`/`state`/`reply`/`preferences`）内容已在别处，
   但深链接仍会打开一张重复页。按下表并入后删除：

   | 页签 | 并入 |
   | --- | --- |
   | `state` | 决策 B3 |
   | `reply` | 表达 D1 |
   | `preferences` | 主动与联系 |
   | `base` | 日记页 |
   | `growth` | 学习与反思 L1 |

3. **`L3` 重号**：书架与阅读 `L3`、每日反思 `L4`、片段记忆 `L5`、梦境压实 `L6`、
   拟人状态与巡视 `L7`。

---

## 七、复核命令（每条断言都能自己验）

```bash
# 注册面：全部配置组与字段
python3 tools/build_v2_inventory.py

# 声明覆盖：spec ↔ 注册表字段一一对应（含有意不接的豁免）
python3 tools/audit_page_config_coverage.py

# 三方对账：SECTIONS ↔ spec ↔ app.js 挂载（发现 busy_gate 空档的那一步）
#   期望输出：后端 16 / spec 16 / 挂载 15，差值 = busy_gate
python3 - <<'PY'
import re, subprocess, json
src = open("astrbot_host/configuration_api.py", encoding="utf-8").read()
body = re.search(r"SECTIONS = \{(.*?)\n\n", src, re.S).group(1)
print("后端:", len(re.findall(r"[A-Za-z]+Management", body)))
spec = subprocess.run(["node","-e","""
const fs=require('fs'),vm=require('vm');
const c=vm.createContext({window:{},document:{},sessionStorage:{},Intl,Date,Object});
vm.runInContext(fs.readFileSync('pages/陪伴小屋/workbench-page.js','utf8'),c);
vm.runInContext(fs.readFileSync('pages/陪伴小屋/config-editor.js','utf8'),c);
process.stdout.write(JSON.stringify(Object.keys(c.window.CompanionConfigEditors.spec)));
"""], capture_output=True, text=True).stdout
spec = json.loads(spec)
app = open("pages/陪伴小屋/app.js", encoding="utf-8").read()
mounted = set()
for group in re.findall(r"mountConfigEditor\('[^']+',\[([^\]]*)\]", app):
    mounted |= set(re.findall(r"'([^']+)'", group))
print("spec:", len(spec), "挂载:", len(mounted))
print("spec 有但未挂载:", sorted(set(spec) - mounted))
PY

# V1 结构事实（本文 §一 的来源）
python3 -c "import json;d=json.load(open('pages/陪伴小屋/V1_PAGE_INVENTORY.json',encoding='utf-8-sig'));print(len(d['navigation']),len(d['panels']),sum(len(p.get('fields') or []) for p in d['panels']),sum(len(p.get('buttons') or []) for p in d['panels']))"

# 页面契约测试
node --test tests/test_setup_guide.cjs tests/test_config_editor.cjs
```

---

## 八、验收口径（每页通用）

- **可达**：控件真实渲染，且不在两页各有一份（R1/R5）。
- **准确**：`scope` 与 `layers` 由后端下发，页面不写死范围；窗口级设置切对象后不带旧草稿。
- **可写**：保存有回执、有幂等、有版本冲突提示。
- **可读**：保存后立即回读一致；只读展示必须来自真实合同。
- **无裸码**：新分区必须同时补 `workbench-page.js` 的 `errors` 表（已踩过两次）。
- **不放假控件**：没有合同就进边界段，说清由谁保存、现在能做什么、下一步去哪。
