# 已完成项核实记录（2026-09-27）

口径与第二轮复核一致：只看工作区实际代码、切片文档与可复跑的定向测试，不采信自评结论。

## 一、声明落点核对（53 处文件引用）

用脚本从任务清单「**已完成**」行的全部反引号文件引用中提取 53 个路径并逐个检查存在性：

- **结论：全部成立**。相对路径写法（`conversation/media/review.py`、`journal/prompts.py` 这类省略 `companion_v2/` 前缀的写法）全部能在对应目录找到实际文件；
- 标记为"缺失"的 6 处（`helpers.py`、`event_dispatch.py`、`group_member_safety.py`、`photo_generation_scope.py`、`proactive/silence.py`）经核对**都是"来源（V1）"列里的 V1 侧参考文件**，不是 V2 落点声明，不构成缺失。

## 二、切片文档引用的测试模块核对（40 个）

从 16 份本批切片记录中提取全部 `tests.test_*` 引用并逐个检查：**40/40 存在**，无笔误、无指向不存在模块的引用。

## 三、定向测试统一实跑（32 模块，350 项）

`PYTHONPATH=backend/app` + AstrBot 自带 Python：

```
Ran 350 tests in 438.326s
FAILED (failures=8, errors=1)
```

即 **341 通过 / 9 未通过**。逐项定性如下。

### 3.1 真实失败（1 项，与并发改动相关）

`tests.test_reply_segmentation.ReplySegmentationTests.test_fences_quotes_lists_tables_links_and_lazy_lines_stay_atomic`
子用例失败：`block='- 列表。\n  <<PRIVATE_COMPANION_SPLIT>>\n  后续。'`

- **单独运行同样失败**（9 项中 1 项），不是批次污染；
- 期望语义：列表项的**懒续行**（第二行以两个空格缩进）必须保持原子，不能被切分；
- 该模块属于回复分段这一基础原语，且本轮有并发进程在改分段/组件顺序相关配置（`SegmentationPolicy`、`component_order`），**建议按回归优先处理**：确认是懒续行判定被削弱，还是该用例期望本身需要更新。

### 3.2 批次污染（12 项：4 + 8）

| 模块 | 单独运行 | 批次内 |
| --- | --- | --- |
| `tests.test_busy_reply_gate`（T52） | **21 项 OK** | 4 项失败/错误 |
| `tests.test_daily_token_soft_limit`（T53） | **15 项 OK** | 3 项失败 |
| `tests.test_busy_reply_gate` + `test_daily_token_soft_limit` 两模块同跑 | **36 项 OK** | — |
| 其余 5 项失败 | 需更大批次才复现 | — |

- **两者单独与两两同跑均全绿**，说明 T52 与 T53 的功能本身没有失败证据；
- 但 32 模块大批次下只剩 341/350，属**测试隔离/状态泄漏**问题：需要定位是哪一个模块留下了全局状态（配置快照、预算策略、`BudgetSoftPolicy` 装配默认、日程/时钟等），否则"整批全绿"这一验收口径无法成立。
- 已排除：不是 T53 的实现问题——其 `effective_soft` 在"两字段都非显式"时返回装配方 fallback，单模块行为可复现且稳定。

## 四、抽查：T28 的"分布问题"声明与 V1 对照

切片声明"照抄 v1 `dreaming.py:325/442` 的 `pow(0.72, 天)` 衰减 + 加权无重复抽样"。实测：

- V1 [`dreaming.py:330`](../../astrbot_plugin_private_companion/dreaming.py)：`decay = pow(0.72, age_hours / 24.0)`，`effective weight = base_weight * decay`（`base_weight` 限幅 0.2–6.0）；
- V2 [style_rotation.py:106](.../companion_v2/expression/style_rotation.py)：`pow(DECAY_PER_DAY, waited_hours / 24.0) * max(FREQUENCY_FLOOR, frequency)`，`DECAY_PER_DAY = 0.72`；`sample()` 用 `random.Random(digest([...seed]))` 做**加权无重复**抽样，`MIN_EFFECTIVE_WEIGHT = 0.0`（用得多只降概率、不淘汰）。
- **结论：声明成立**，衰减常数与形状同 V1，且额外做了"定种可复现"（抽样写进封存快照）这一 V2 要求。

## 五、建议

1. **优先修 3.1 的分段真实失败**（基础原语，影响面最大）。
2. **定位 3.2 的状态泄漏**：建议以"逐模块累加"方式二分，找出把全局状态带进后续模块的用例；在定位前，验收结论应写"分模块全绿"，不要把大批次结果当作整体通过。
3. 并发写入仍在进行（本记录生成期间 `docs/V2_GAP_CLOSING_TASKS_20260927.md`、`companion_v2/host/application.py` 等多次报"文件在读取后被修改"），核对结论以本记录截取时的源码为准。
