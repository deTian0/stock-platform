# 契约：当日行情台账（day quote）

- 里程碑：`A6`（`v4.12.0`）
- 单点：`stock_platform_research.day_quote`
- CLI：`stock-platform-day-quote`
- ADR：[0082](../architecture/0082-day-quote-attribution.md)
- 状态：生效（SIMULATE / 只读 / 研究口径）

## 1. 目的与范围

回答**逐只标的的当日行情**：开盘 / 最高 / 最低 / 收盘、涨跌幅，以及**可复算的量化归因**。

**不做**：不写库、不做消息面归因、不做实时行情、不改 `A4` 的基准口径。

## 2. 字段口径（全部为当日**单根 K 线**）

| 字段 | 定义 | 缺失时 |
|---|---|---|
| `prevClose` | asof 的**紧邻上一交易日**收盘 | `null` |
| `open` / `high` / `low` | 外部日线（引擎库无此三列） | `null` + `ohlcSource="missing"` |
| `close` | 引擎 `daily_price.close`（与主链同一截面） | `null` |
| `pct` | `close / prevClose − 1`（**自算**，不读 `pct_chg`） | `null` |
| `gap` | `open / prevClose − 1` | `null`（无 open） |
| `intraday` | `close / open − 1` | `null`（无 open） |
| `amplitude` | `(high − low) / prevClose` | `null` |
| `volRatio` | `volume / mean(volume[t−20 .. t−1])`，**分母不含当日** | `null` |
| `ma20` | 含当日的 20 根收盘均值（需满 20 根） | `null` |
| `vsMa20` | `close / ma20 − 1` | `null` |
| `dayAlpha` | `pct − 基准当日 pct`（百分点差以小数表示） | `null` |
| `staleBars` | asof 当日无 K 线（停牌/未到）→ `1` | 恒存在 |

**只有 `close` 存在且 `prevClose` 存在**时才会产出 `pct`；`null` 一律表示「算不出」，
**任何时候都不补 0**。

## 3. 归因（`attributionKind="quantitative"`）

固定四轴、固定顺序输出 `tags[]`，再把 `tags` 拼成 `reason` 一句人话。

| 轴 | 阈值常量 | 取值 |
|---|---|---|
| 形态 | `GAP_MATERIAL=0.8` / `INTRADAY_MATERIAL=0.8` / `BAND_FLAT=0.5`（百分点） | 高开低走 / 低开高走 / 冲高回落 / 探底回升 / 窄幅整理 / 单边走强 / 单边走弱 |
| 量价 | `VOL_HEAVY=1.5` / `VOL_LIGHT=0.7` | 放量上涨 / 放量下跌 / 放量滞涨 / 缩量上涨 / 缩量下跌 / 缩量整理 / 量能常态 |
| 相对基准 | `ALPHA_MATERIAL=1.0`（百分点） | 强于基准 / 随基准 / 弱于基准 |
| 位置 | `MA_WINDOW=20` | 站上20日线 / 20日线下方 |

`冲高回落` / `探底回升` 需要 `high`/`low`：判据为影线 ≥ 1%（对 `prevClose`）且收盘落在
全天区间的下 35% / 上 65%。**无 OHLC 时两标签不产生**，形态轴退化为 `gap/intraday` 或无。

`reason` 的结论从句由「涨跌方向 × 量能」优先决定，其次用「相对基准」，两者都缺则省略 `⇒` 从句。

## 4. 覆盖与汇总

- `bucket`：`pick`（asof 归档 brief 的 picks）/ `holding`（`data/holdings.json`）/ `benchmark`。
- 同一 `(symbol, bucket)` 去重；`summary` **只统计非 benchmark 行**且 `pct != null` 的行。
- `summary`：`counted` / `upCount` / `downCount` / `flatCount` / `avgPct` / `medianPct` /
  `best` / `worst` / `tagCounts` / `missingOhlc`。

## 5. 数据源与缓存

| 数据 | 来源 | 备注 |
|---|---|---|
| 日线（close/volume 序列） | 引擎 `market.db`（只读） | `STOCK_PLATFORM_ENGINE_MARKET_DB` 或 `--market-db` |
| 开/高/低 | 东财 `kline/get`（经 `em_get`） | `--no-ohlc` 可完全禁用 |
| 开/高/低缓存 | `data/quotes/ohlc-<asof>.json` | 同日复跑零网络；坏缓存视作无缓存 |

`ohlc` 段：`requested` / `filled` / `source`（`none|cache|provider|cache+provider`）/
`missing[]` / `degraded`（降级原因，非空即在报告顶部提示）。

## 6. 已知缺陷（硬约定）

平台基准 `000905` 在引擎库中解析为**厦门港务（个股）**，非中证500指数。
`dayAlpha` 因此是**相对该个股**的超额，**不得**读作指数超额。
`benchmarkWarning` 非空时报告顶部**强制**打印该提醒；`A4` 的 `avgAlpha` 同源同病。
修复需 provider 支持强制市场后缀（`000905.SH` 当前会被回落成深市个股）+ 基准口径迁移，
另立里程碑。

## 7. 出口

- 报告项 `A6_day_quote`（`data/reports/<asof>/A6_day_quote.{md,html}`）；
- CLI `stock-platform-day-quote`（`--asof/--market-db/--holdings/--benchmark/--cache-dir/--no-ohlc/--json-out/--out`）；
- payload `--json-out` 为机器契约。
