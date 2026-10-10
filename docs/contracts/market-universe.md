# 全市场宇宙契约（X1）

> 状态：Accepted｜目标 tag：`v4.0.0`（2026-10-10）
> 关联：`docs/architecture/0055-market-universe.md`、实测 `docs/ops/market-universe-benchmark.md`

`X1` 之前，日线宇宙来自一个小 JSON fixture（`core` / `watch` / `full` 分层，几百个代码）。`X1` 把它扩到 **market.db 全市场**（约 5.2k 可交易代码，排除 BSE）。

宇宙解析只有**一个入口** `research.market_universe.resolve_universe`，两个来源：

| source | 含义 | 规模 | 默认 |
|---|---|---|---|
| `config` | JSON fixture（`core` / `watch` / `full`） | 数十 ~ 数百 | **是**（X1 前行为不变） |
| `market_db` | engine `market.db` 全市场派生 | ~5.2k | 否（显式启用） |

---

## 1. 职责切分（规则不写两遍）

| 规则 | 归属 | 单点位置 |
|---|---|---|
| 「仓库里的 code 怎么变成代码列表」：窗口、`min_bars`、BSE 排除、6 位归一、裸码合并 | **providers** | `EngineSqliteProvider.list_symbols` |
| 资产类别过滤（stock / etf / fund / all）、`limit`、顺序、空宇宙 fail-closed、耗时内存度量 | **research** | `market_universe.resolve_market_universe` |
| 资产类别判据本身 | **B4 单点** | `portfolio.asset_class` |
| BSE 判据本身 | **providers 单点** | `symbol.is_bse_symbol` |

research **不重复实现** BSE 前缀表，也**不重新排序** provider 结果 —— 顺序即来源顺序（provider 返回已排序）。

### 1.1 providers：`list_symbols`

```python
EngineSqliteProvider.list_symbols(
    asof=None,            # 默认 = daily_price 里 MAX(date)
    lookback_days=120,    # 窗口长度（自然日）
    min_bars=1,           # 窗口内最少 bar 数
    include_bse=False,    # 默认排除北交所
    limit=None,
) -> list[str]            # 6 位裸码，已排序
```

- SQL 只走 `date` 窗口（`idx_dp_date`）：`SELECT code, COUNT(*) ... WHERE date BETWEEN ? AND ? GROUP BY code`。**不对 `code` 做任何表达式**（`SUBSTR(code,-2)` 这类全表扫描实测 5.1s，窗口聚合 0.15s）。
- 归一化：去 `.SH` / `.SZ` / `.BJ` 后缀；**bar 数在归一之后合并**（仓库里 `600519.SH` 与历史遗留的裸 `600519` 是同一只股票，必须合并计数）。
- 非 6 位纯数字的残留码（实测存在 `"42"` / `"8"` 等脏数据）**一律丢弃**。
- 空结果返回 `[]`（**不抛错**）—— fail-closed 是调用方的职责，见下。

### 1.2 research：`resolve_market_universe`

```python
resolve_market_universe(
    source,               # 任何带 list_symbols(...) 的对象
    asof=None, lookback_days=120, min_bars=1, include_bse=False,
    asset_type="stock",   # stock | etf | fund | all
    limit=None, measure_memory=False,
) -> MarketUniverse
```

`MarketUniverse` 携带 `symbols` + `counts`（`source` / `normalized` / `asset_matched` / `final`）+ `elapsed_s` + `peak_memory_mb`，即**出处与代价都随结果返回**，不留"事后回忆"。

---

## 2. Fail-closed 清单

| 情形 | 行为 |
|---|---|
| 解析结果为空 | 抛 `UniverseEmptyError`（中文，附 `counts`）——**绝不静默退化成"0 只股票的一天"** |
| `market_db` 但没注入 source | 抛 `UniverseEmptyError`（提示需注入 `list_symbols` 对象） |
| 未知 `source` / `asset_type` | 抛 `UniverseEmptyError` |
| `daily_price` 为空 | provider 返回 `[]` → research 抛 `UniverseEmptyError` |
| DB 文件缺失 | `FileNotFoundError`（中文，提示 `STOCK_PLATFORM_ENGINE_MARKET_DB`） |

**禁止**：空宇宙回落到样例 fixture。那会伪装成"选股跑通了"——实际只跑了个位数代码。

---

## 3. 调用点

- **CLI**：`stock-platform-market-universe --db <market.db> --asof YYYY-MM-DD [--asset-type all] [--probe-panel]`
- **日线流水线**：`run_daily_pipeline(universe_source="market_db", market_symbol_source=<provider>, market_universe_kwargs={...})`；流水线自动注入本次的 `asof` 与 `lookback_days`，报告里多一个 `universe{source,size}` 字段。
- 显式 `symbols=` 仍然优先于两个来源（X1 不改变既有行为）。

---

## 4. 实测

见 `docs/ops/market-universe-benchmark.md`。摘要（market.db 3.14 GB / 877 万行，asof 2026-09-03）：

| 项 | 数字 |
|---|---|
| 全市场枚举（stock / 排除 BSE） | **5227** 只 |
| 枚举耗时 / 峰值内存 | **0.21 s** / **1.04 MB** |
| `asset_type=all` | 5241 只 |
| `min_bars=60` | 5194 只 |
| 单日 PIT panel（500 只） | 499 行 / 2.0 s / 47.4 MB |
