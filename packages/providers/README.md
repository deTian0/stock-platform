# packages/providers

统一行情 / 基本面 Vendor。安装名：`stock-platform-providers`；导入名：`stock_platform_providers`。

## 状态

| 版本 | 能力 |
|------|------|
| M1.1 / v0.1.1 | `normalize_symbol` / `exchange_prefix` |
| M1.2 / v0.1.2 | `ReplayProvider` daily + realtime 录制回放 |
| **M1.3 / v0.1.3** | `em_get` 东财限流单点 + `build_capability_matrix` |
| **M1 / v0.2.0** | 大里程碑收口（上列能力齐备） |
| **M5.1+ / v0.5.1** | `MarketStrategy` CN/US/HK；`normalize_symbol(market=)`；`GlobalReplayProvider` |
| **M8.1 / v1.0.1** | `AStockHttpProvider` live daily/realtime（经 `em_get`） |
| **M9.1 / v1.1.1** | `GlobalHttpProvider` / `GlobalHttpRouter`（Yahoo + 新浪） |
| **M10.1 / v1.2.1** | `TradingCalendar` + 静态 CN 休市日 |
| 包版本随仓 | 与根 `VERSION` 对齐（当前随发版 bump） |

## 安装

```powershell
cd D:\workspace\git\stock-platform\packages\providers
python -m pip install -e ".[dev]"
python -m pytest -q
```

Live 东财 HTTP（可选）：

```powershell
python -m pip install -e ".[http]"
```

## 公开 API（当前）

| 符号 | 作用 |
|------|------|
| `normalize_symbol` / `exchange_prefix` / `is_bse_symbol` | CN / US / HK 代码（`market=`） |
| `get_market_strategy` / `MarketStrategy` | 市场策略表（settle / limit / 时区） |
| `get_trading_calendar` / `TradingCalendar` | CN 静态休市日；US/HK weekday stub |
| `ReplayTransport` / `ReplayProvider` | CN fixtures 回放 |
| `GlobalReplayTransport` / `GlobalReplayProvider` | US/HK fixtures 回放 |
| `AStockHttpProvider` | A 股 live（经 `em_get`） |
| `GlobalHttpProvider` / `GlobalHttpRouter` | 美港 live（Yahoo + 新浪；不经 `em_get`） |
| `em_get` / `EastmoneyClient` | **唯一**东财 HTTP 入口 |
| `build_capability_matrix` / `register_builtin_providers` | 能力路由 |
| `SymbolError` | 非法代码 |

## 硬约束

- **新代码禁止直连东财 URL** — 见 [`docs/contracts/eastmoney-http.md`](../../docs/contracts/eastmoney-http.md)
- 对外字段遵循 [`docs/contracts/datasets.md`](../../docs/contracts/datasets.md)
- 缺能力 fail-closed（矩阵 `usable=false`）
