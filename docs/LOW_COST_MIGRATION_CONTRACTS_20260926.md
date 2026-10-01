# 低成本迁移合同切片

更新时间：2026-09-26。此切片覆盖功能差距清单中输入输出明确、可用合成数据独立验收的工作。它完成的是领域纯逻辑合同；不等同于生产数据接入、授权决策、持久化、任务调度、真实模型调用或平台发送。

## 交付范围

| 任务 | V2 归属 | 本切片交付 | 定向验收 |
| --- | --- | --- | --- |
| 本地日期、星期、时段、固定公历节日与农历 | `conversation/date_context.py` | 按明确 IANA 时区投影当前日期材料；可选 `lunardate`/`lunarcalendar`，超出库范围或依赖不可用时只省略农历，不猜测。材料明确不是用户事实证据。 | `tests/test_conversation_date_context.py` |
| 记忆 MMR 多样化 | `memory/mmr.py` | 仅对已由既有流程筛选、授权并复核的候选做稳定 MMR 排序；接受相关度及向量或相似度函数，不改写候选。 | `tests/test_memory_mmr.py` |
| 井字棋、五子棋、骰子、二十一点规则 | `games/` | 纯状态/规则算法与原有规则测试；不建立房间、席位、QQ 路由或持久执行链。 | `tests/test_games_tictactoe.py`、`test_games_gomoku.py`、`test_games_pig_dice.py`、`test_games_blackjack.py` |
| 世界书与角色知识格式解析 | `knowledge/parsing.py` | 解析世界书条目和 AstrBot 知识库行，逐行报告无效数据；不决定检索资格、授权或对话注入。 | `tests/test_low_cost_contracts.py` |
| 自我复盘与表达学习 | `role_work/journal/self_review.py`、`expression/learning.py` | 提供带来源引用的临时指导/表达观察提示和输出校验；复盘指导有显式过期时间。结果不自动保存、不改变角色提示词。 | `tests/test_low_cost_contracts.py` |
| 选择性 TTS | `conversation/voice_reply.py`、`delivery/`、`adapters/astrbot/` | 复用已有被动回复选择、图文/语音 ACK 与失败退化链。默认关闭；不包含 V1 专用语音后端、主动语音或本机播放。 | `tests/test_voice_reply.py`、`tests/test_astrbot_voice_reply.py` |
| Content 创作输出合同 | `conversation/content/authoring.py` | 为合成草稿提供提示词和严格输出/来源句柄校验；不采用、保存、审核、发布或发送作品。 | `tests/test_low_cost_contracts.py` |
| 逐年节假日、调休及节气数据 | `agenda/annual_calendar.py` | 解析版本化年度 JSON，展开节日日期并验证年份、重叠和重复；不选数据源、不抓取、不调度。 | `tests/test_low_cost_contracts.py` |
| 天气、预警及新闻响应 | `proactive/external_materials.py` | 归一化 provider-neutral JSON，校验时间/数值/URL 并去重；不发网络请求、不选择城市或来源、不判断新鲜度。 | `tests/test_low_cost_contracts.py` |
| NovelAI 参数映射 | `integration/nai_image.py` | 将已给定的意图和允许参数映射为请求体，验证参数白名单及范围；不读取密钥、不连接 NAI、不选择资源所有者。 | `tests/test_low_cost_contracts.py` |
| 关键词、正则及时段换模规则 | `model_gateway/replacement_rules.py` | 按优先级匹配关键词及显式时区/星期/跨午夜窗口，返回候选 provider/model；不调用 provider、不改变现有路由配置或余额策略。 | `tests/test_low_cost_contracts.py` |

## 共同边界

- 日期和年度日历合同仅负责本地投影/解析；节假日数据的来源、准确性、逐年更新和缺失回执仍需由主线确定。固定公历节日不代表法定放假安排。
- 角色所在地的当前天气、已接受私人约定及饭点已另行接入主动联系；天气变化检测、官方预警、新闻和其他外部事件仍需各自完成来源、时效、去重与原目标授权接线。
- 知识片段与 MMR 候选继续经过 V2 现有授权、来源筛选和正本复核。排序器和解析器不得扩大候选可见范围。
- 自我复盘、表达学习及 Content 的模型输出均为可审阅草稿；持久化、提示词采用、发布和发送需要各自 owner 的显式流程。
- NAI 和模型路由合同不得接收或暴露凭据；真实 backend/provider 适配与失败/未知回执处理另行实现。
- 页面管理由并行页面工作负责，本切片不修改管理页。

## 生产接线增量

本轮将 MMR 从纯排序合同接入现有向量召回页：`memory/recall_query.py` 先通过 `RecallObjects.read` 做当前正本、授权、撤回和过滤复核，再从同一 owner、文档 hash、模型和维度匹配的派生向量缓存读取向量，最后以默认 `lambda_mult=0.7` 排列有限候选窗口。候选窗口超过单页 `limit` 时，游标保存剩余的已排序 ID；后续页重新读取正本，缓存缺失或向量无效只退化为相关度顺序。该接线不扩大候选范围、不绕过来源授权、不执行全局图遍历。

接线回归覆盖 `tests/test_memory_mixed_incremental.py::MixedMemoryTests::test_hybrid_recall_uses_mmr_after_authority_and_keeps_cursor_order`，并与记忆 MMR、查询、增量、混合增量和选择测试一起通过（79 passed，3 subtests passed）。

## 验收

先运行本切片与对应既有规则测试：

```powershell
python -m pytest -q tests/test_low_cost_contracts.py tests/test_conversation_date_context.py tests/test_memory_mmr.py tests/test_games_tictactoe.py tests/test_games_gomoku.py tests/test_games_pig_dice.py tests/test_games_blackjack.py tests/test_voice_reply.py tests/test_astrbot_voice_reply.py
```

合成测试只证明合同和退化行为，不证明真实天气/资讯源、农历库安装组合、模型 provider、NovelAI 或 QQ 的现场可用性。生产接线应作为后续独立切片，沿用各领域现有 owner 和授权/来源复核流程。
