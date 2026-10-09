# 主动消息端到端夹具

本目录只保存"真链路"端到端用例与 `tools/run_proactive_sim.py` 需要的外部资讯样本。
样本本身不是代码：它原样保存一次真实取回的 HTTP 响应体，让用例走**真的**解析器
（`astrbot_host.news_parsing.parse_rss_news`）和**真的**来源端口
（`astrbot_host.news.NewsRssPort`），只把网络这一跳换成"回放已录制的字节"。

## recorded/

| 文件 | 用途 |
| --- | --- |
| `news_feed_juya_20261004.xml` | 录制样本：一次真实 `GET https://daily.juya.uk/rss.xml` 的**原始响应体**，未做任何改写。 |
| `news_feed_sample.json` | 同一次录制的清单：录制时间、URL、HTTP 状态、字节数、sha256、`Content-Type`，以及按 `parse_news_response` 契约归一化后的条目（含 `published_at`）。 |

### 录制方式

`astrbot_host/news.py` 的 `NewsJsonPort._read` 用 `aiohttp` 且**不带** `User-Agent`
（`headers` 只放显式配置的鉴权头）。该站点对缺少 `User-Agent` 的请求返回 403，
因此录制脚本显式声明了一个标识性 `User-Agent`：

```powershell
C:/Users/99505/.astrbot/backend/python/python.exe tools/run_proactive_sim.py --record-fixture
```

**这是一个已知偏差**：录制用一个自报身份的 `User-Agent` 取回了真实响应体，但生产
路径发的是没有 `User-Agent` 的请求。也就是说，样本证明的是"真实响应体长什么样、
真实解析器把它变成什么"，**不**证明"默认 RSS 源在当前网络下可用"。后者由
`astrbot_host/news.py` 的默认请求头决定，是产品侧的既有行为，本夹具不改动它。

### 时效性

`NewsContactEvents.prepare` 只接受 `0 <= at - published_at <= 24h` 的条目，所以消费
这份样本的用例把时钟锚定在录制清单里的 `article.published_at`，而不是硬编码某个日期。
样本过期后不需要改用例，只需要重新跑一次 `--record-fixture`。

## synthetic/

`news_feed_synthetic.json` 是**手写近似样本，非录制**：它用相同的归一化契约描述一条
带有固定 `published_at` 的资讯，用于必须与真实录制解耦的断言（例如渲染态、分片顺序、
拒收条件）。它经过与录制样本相同的解析端口契约，但不来自任何真实站点。
