# a-stock-engine 本地日线（offline / 结算）

本仓**不拷贝**引擎数据。配置只读路径后，Workbench / CLI 可读 `daily_price`。

## 数据在哪

默认权威文件（本机已导入时）：

`D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`

| 表 | 用途 | 规模（本机实测量级） |
|----|------|----------------------|
| `daily_price` | code/date/close/pct_chg/vol/amount | ~877 万行，2020-01-02～2026-09-08，~6974 码 |
| `fundamentals_pit` / `daily_basic_pit` | PIT 基本面（只读） | **已暴露**：`EngineSqliteProvider.get_*_pit` + `GET /api/research/pit/fundamentals`；见 [ADR 0050](../architecture/0050-engine-pit-fundamentals-readonly.md)（Accepted） |

另有 `a-stock-engine.db` / `selections.db`（选股/轮动/验证），**不**作为平台日线源。

## 配置

在 `stock-platform` 根 `.env`：

```text
STOCK_PLATFORM_ENGINE_MARKET_DB=D:/workspace/stock_trading/a-stock-engine/data_cache/market.db
```

可选预设（日线走 engine，其余仍 replay）：

```text
STOCK_PLATFORM_PROVIDER_PRESET=cn_engine_sqlite
```

## 验证命令

```powershell
# 读到行数（应 > 0）
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:/workspace/stock_trading/a-stock-engine/data_cache/market.db"
python -c "from datetime import date; from stock_platform_providers import EngineSqliteProvider; p=EngineSqliteProvider(); print(len(p.get_daily(['600519'], start=date(2026,1,1), end=date(2026,9,8))))"

# PIT 财务（ann_date <= asof）
python -c "from datetime import date; from stock_platform_providers import EngineSqliteProvider; p=EngineSqliteProvider(); print(p.get_fundamentals_pit(['600519'], asof=date(2024,6,30)))"

# 结算绩效 pending（有足够后续交易日时写入 JSONL）
stock-platform-performance --settle-daily
```

Workbench：刷新「推荐绩效」默认 `autoSettle=true`；有 engine db 时优先用其结算。

「回测」区（`#backtest` / `POST /api/research/backtest/rolling-review`）：对 watch 宇宙最近 N 日滚动推荐复盘，汇总 `direction_accuracy`（与 U3/绩效同口径）。未配置本变量且无其它日线时 **503 fail-closed**，不静默假数据。点表中 asof →「今日推荐」加载该日 picks。

「策略对比」区（`#strategy-compare` / `POST /api/research/strategy/compare`）：有本变量时默认用 engine 多日 PIT 面板；否则回退演示 fixture 并标注 `panelSource=fixture`。勾选「强制 engine」则无 DB 时 503。

## 限制

- 只读；不写引擎库、不把 DB 提交进 git。
- 仅 `daily`；无 realtime / 分钟 / 财务矩阵能力。
- 数据截止以引擎导入日为准，**不是** live。
- OHLC 仅可靠 close（引擎表无 open/high/low 时为 null）；结算用收盘价即可。
- `daily_price.code` 为 `600519.SH` / `000001.SZ` 形态；适配器会从 6 位码自动映射。

## 摄取与覆盖自检（C2）

**摄取归生产侧**：写 `daily_price` 是 `a-stock-engine` 的职责，平台**只读**（ADR 0050 / [ADR 0058](../architecture/0058-market-db-source-of-truth.md)）。平台不代抓、不补写；发现问题只报警不改库。

### 刷新全市场日线（引擎侧）

```powershell
cd D:\workspace\stock_trading\a-stock-engine
# 1) 单位口径实测校准（拿最新全市场日与存量重叠代码比对，四字段比值应≈1.0）
.\.venv\Scripts\python.exe empirical\backfill_market_daily.py --validate
# 2) 看缺口（<3000 行/日的交易日都会列出）
.\.venv\Scripts\python.exe empirical\backfill_market_daily.py --start 2026-09-04 --end 2026-10-09 --dry-run
# 3) 执行回补（顺序 + sleep，CPU-safe）
.\.venv\Scripts\python.exe empirical\backfill_market_daily.py --start 2026-09-04 --end 2026-10-09 --apply
```

单位口径（tushare → 引擎 `daily_price`）：`pct_chg` **÷100**（存量是小数制）、`vol` **×100**（手→股）、`amount` **×1000**（千元→元）、剔除 `.BJ`。脚本只写「带后缀股票行」，与存量 720 万行一致。

### 覆盖自检（平台侧，只读）

`GET /api/ops/health` 的 `marketDb` 块给出裁决（不 500、不改库）：

| status | 含义 |
|--------|------|
| `ok` | 窗口内交易日齐全，且每日 ≥ `minRowsPerDay`（默认 3000） |
| `thin` | 存在低于行数下限的交易日 → 部分导入 |
| `stale` | 存在缺失交易日 / `lagTradingDays > 0` → 摄取已中断 |
| `empty` / `missing_table` | 窗口无数据 / 表缺失 |
| `unconfigured` | 未设 `STOCK_PLATFORM_ENGINE_MARKET_DB` |

`thin` / `stale` / `empty` / `missing_table` / `error` 会把整体 `status` 降级为 `degraded`。

### 已知的坑（改摄取前先读）

- `multifactor.refresh_etf_daily_prices` **每日只写 14 只 ETF**（`WELL_KNOWN_ETFS`）且 `pct_chg` 写 0 —— 它是"当日行数=14"的唯一来源，不代表全市场正常。
- ⚠️ **且它会摧毁这 14 只 ETF 的长历史**：函数先 `delete_prices_for_codes(ok_codes)`（模式含裸码 / `.SZ` / `.SH`，即删掉**全部历史**）再写入 `LocalPriceLoader` 的 65 根 K 线。2026-10-10 实测：这 14 只各只剩 `2026-06-09 ~ 2026-09-08` 共 **65 行**、`pct_chg` **全为 0**；而同一张表里非 `WELL_KNOWN_ETFS` 的 ETF（如裸码 `518880`）仍有 **1499 行**长历史。
  - 修复路径（已实测可用）：`pro.fund_daily(ts_code=..., start_date=..., end_date=...)` 返回未复权日线且 `pct_chg` 正确（如 `510300.SH` 2026 年内 183 行），**14 次调用**即可重建。**未在本轮执行**——需要用显式决策定夺复权口径（`fund_daily` 为未复权，存量 ETF 行为裸码 + 未知复权），避免引入口径混用。
- `import_local_data.py` 的断点续传按**日期是否存在**判定（`SELECT DISTINCT date FROM daily_price`），**部分覆盖日会被永久跳过**；修复部分日只能用 `empirical/backfill_market_daily.py`（`INSERT OR REPLACE`）。
- 该库**不含北交所**（无 `.BJ` 后缀码），`include_bse=True` 与默认结果一致。
