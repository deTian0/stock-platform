# 契约：市场策略

> 状态：**Accepted（M0.2）** — A 股表定稿；美港为 M5 占位  
> 市场差异必须走 **策略对象/表**，禁止在 UI/回测里散落无文档的 `if market == ...`。

## 策略标识

```text
market_id ∈ { "CN", "US", "HK" }
```

每个 `market_id` 提供只读策略：日历、时区、会话、交收、涨跌停、代码空间。

---

## CN（A 股）— v0.0.2 初稿 / 合并期权威

| 项 | 规则 |
|----|------|
| `market_id` | `CN` |
| 交易所 | SSE / SZSE；北交所可选宇宙 |
| 交易日历 | 沪深交易日（非自然日）；数据源：未来 providers 日历或深交所官方日历 |
| 时区 | `Asia/Shanghai` |
| 会话（简表） | 09:30–11:30、13:00–15:00；集合竞价细节 M2+ 补全 |
| 股票交收 | **T+1**（当日买次日方可卖）；回测必须建模 |
| ETF | 交收规则以产品配置为准，**不得** silently 套用股票 T+1 假设而不声明 |
| 涨跌停 | **存在**；主板/创业板/科创板/ST 幅度不同，由规则表配置，不写死单一 10% |
| 涨跌停判据价 | **不复权原始价**（`raw_*`），禁止用前复权 OHLC |
| 一字板 / 不可成交 | 回测在涨跌停价上不可成交（对齐 TSP 回测红线） |
| 代码空间 | 6 位数字；归一化见 `datasets.md` |
| 分钟 K 时间 | **naive 北京墙钟**；禁止 UTC aware 入库 |
| 实时 `asof_ts` | Unix 毫秒 UTC，展示转上海 |
| 费用 / 滑点 | 回测可配；不得用「零费用」当默认生产口径而不声明 |
| 语言/披露 | 中文为主 |

### CN 回测硬约束（迁入后不可被选项绕过）

1. 信号时间与可成交时间分离（防未来函数）。
2. 股票 T+1。
3. 涨跌停不可成交（按 raw 价）。
4. 交易日对齐日历，禁止用自然日填充停牌日当可交易。

### 北交所

- 代码可归一化成功。
- 默认选股宇宙是否包含：由配置 `universe.include_bse` 控制（默认建议 `false`，与部分旧 engine 行为接近，可在 M3 再议）。

---

## US / HK — 占位（M5 展开）

| 项 | US | HK |
|----|----|-----|
| `market_id` | `US` | `HK` |
| 时区 | `America/New_York` | `Asia/Hong_Kong` |
| A 股式涨跌停 | **无** | **无** |
| A 股 T+1 | **不套用** | **不套用** |
| 进入 CN `normalize_symbol` | 必须失败 | 必须失败 |

---

## 策略接口（文字契约，M1 实现）

```text
MarketStrategy:
  market_id: str
  timezone: str
  is_trading_day(date) -> bool
  session_segments(date) -> list[interval]
  settle_rule(asset_type) -> SettleRule   # e.g. T+1
  limit_rules(symbol, asset_type) -> LimitRule | None
  validate_symbol(symbol) -> SymbolRef | raises
```

工作台与回测只依赖 `MarketStrategy`，不依赖字符串国家名散落判断。

## 已关闭的原 TBD

| 原问题 | 决定 |
|--------|------|
| 北交所是否进 v1 | 可解析；默认宇宙 **可选排除**（`include_bse`） |
| ETF / 指数是否共用股票规则 | **否**；经 `asset_type` + `settle_rule` / `limit_rules` 分支 |
| 美港何时写细表 | M5；本文件仅冻结「不得套用 CN 假设」 |

## 参考

- tick-stock-panel：`CONTRIBUTING.md` 回测与金融口径
- TradingAgents-astock：非 A 股拒绝、未来函数防护
- V2 审查：信号新鲜度与交易日调度（执行层 M6）
