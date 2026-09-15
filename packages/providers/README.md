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
| **M13.1 / v1.5.1** | US/HK 静态休市日（`us_closed_days.txt` / `hk_closed_days.txt`） |
| **M15.1 / v1.7.1** | CN 日级资金流 `get_fund_flow`（replay + `astock_http` / `em_get`） |
| **M16.1 / v1.8.1** | CN 龙虎榜 `get_lhb`（replay + datacenter-web / `em_get`） |
| **M17.1 / v1.9.1** | CN 限售解禁 `get_unlock`（replay + datacenter-web / `em_get`） |
| **M18.1 / v1.10.1** | CN 分钟 K `get_minute`（replay + push2his kline / `em_get`） |
| **M19.1 / v1.11.1** | CN 五档盘口 `get_depth5`（replay + push2 stock/get / `em_get`） |
| **M20.1 / v1.12.1** | CN 财务报表 `get_financial`（replay + 新浪三表；非 em_get） |
| **M21.1 / v1.13.1** | CN 复权因子 `get_adj_factor`（replay + 新浪 qfq/hfq；非 em_get） |
| **M23.1 / v1.15.1** | `apply_adjust` 确定性套价（qfq 除 / hfq 乘；非独立能力） |
| **v3.10.0** | `TushareHttpProvider` 补充 CN daily（raw POST；预设 `cn_tushare_http`） |
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
| `get_trading_calendar` / `TradingCalendar` | CN/US/HK 静态休市日（2024–early 2029）；周末由代码排除 |
| `ReplayTransport` / `ReplayProvider` | CN fixtures 回放 |
| `GlobalReplayTransport` / `GlobalReplayProvider` | US/HK fixtures 回放 |
| `AStockHttpProvider` | A 股 live（经 `em_get`） |
| `GlobalHttpProvider` / `GlobalHttpRouter` | 美港 live（Yahoo + 新浪；不经 `em_get`） |
| `TushareHttpProvider` | A 股补充日 K（Tushare 兼容 POST；token 环境变量） |
| `em_get` / `EastmoneyClient` | **唯一**东财 HTTP 入口（节流 + 熔断） |
| `PREFERENCE_PRESETS` / `list_preference_presets` | 文档化偏好模板（含 `cn_tushare_http`） |
| `build_capability_matrix` / `register_builtin_providers` | 能力路由 |
| `apply_adjust` | 用 `adj_factor` 套不复权 OHLC（qfq 除 / hfq 乘） |

## Tushare 补充源（可选）

```powershell
$env:STOCK_PLATFORM_TUSHARE_TOKEN = "<token>"   # 勿提交
# $env:STOCK_PLATFORM_TUSHARE_URL = "https://t.xiaodefa.top/"
# Workbench：应用预设 cn_tushare_http，或偏好 daily=tushare_http
```

详见 [`docs/architecture/0048-tushare-http-provider.md`](../../docs/architecture/0048-tushare-http-provider.md) 与 [`docs/ops/live-startup.md`](../../docs/ops/live-startup.md)。

## 硬约束

- **新代码禁止直连东财 URL** — 见 [`docs/contracts/eastmoney-http.md`](../../docs/contracts/eastmoney-http.md)
- 对外字段遵循 [`docs/contracts/datasets.md`](../../docs/contracts/datasets.md)
- 缺能力 fail-closed（矩阵 `usable=false`）
