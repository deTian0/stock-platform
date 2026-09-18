# a-stock-engine 本地日线（offline / 结算）

本仓**不拷贝**引擎数据。配置只读路径后，Workbench / CLI 可读 `daily_price`。

## 数据在哪

默认权威文件（本机已导入时）：

`D:\workspace\git\a-stock-engine\data_cache\market.db`

| 表 | 用途 | 规模（本机实测量级） |
|----|------|----------------------|
| `daily_price` | code/date/close/pct_chg/vol/amount | ~877 万行，2020-01-02～2026-09-08，~6974 码 |
| `fundamentals_pit` / `daily_basic_pit` | PIT 基本面（只读） | **已暴露**：`EngineSqliteProvider.get_*_pit` + `GET /api/research/pit/fundamentals`；见 [ADR 0050](../architecture/0050-engine-pit-fundamentals-readonly.md)（Accepted） |

另有 `a-stock-engine.db` / `selections.db`（选股/轮动/验证），**不**作为平台日线源。

## 配置

在 `stock-platform` 根 `.env`：

```text
STOCK_PLATFORM_ENGINE_MARKET_DB=D:/workspace/git/a-stock-engine/data_cache/market.db
```

可选预设（日线走 engine，其余仍 replay）：

```text
STOCK_PLATFORM_PROVIDER_PRESET=cn_engine_sqlite
```

## 验证命令

```powershell
# 读到行数（应 > 0）
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:/workspace/git/a-stock-engine/data_cache/market.db"
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
