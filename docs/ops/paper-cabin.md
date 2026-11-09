# 本仓模拟舱（PaperBroker）

> **推荐主路径**：自建纸面模拟买卖。  
> **默认**：`STOCK_PLATFORM_BROKER=paper` + **SIMULATE**；`liveTradingEnabled=false`。  
> **禁止**：live 券商开关、伪造成交、宣称「已接同花顺」。

## 与 ths_sim 的关系

| 路径 | 用途 | 何时用 |
|------|------|--------|
| **模拟舱 / paper（本页）** | 内部 `PaperBroker` + `PaperLedger`；资金/持仓/成交落 `local/paper_cabin/` | **日用推荐**；演示闭环 |
| **ths_sim + mock** | 同花顺适配器的内存/fixtures 传输 | 仅演示 BrokerPort 端口；**非**真实券商 |
| **ths_sim + experimental** | HTTP 扩展点；缺凭据 fail-closed | 未接真实零售模拟盘；见 [`broker-port-honesty.md`](broker-port-honesty.md) |

用户决策（2026-11）：同花顺真实模拟盘**放弃**；本仓以模拟舱为模拟买卖主路径。`ths_sim` mock 保留作端口演示，不平行造第二套账本。

## 怎么用（CLI）

```powershell
# 一键冒烟（固定演示时钟 + 明示价格）
stock-platform-paper demo

# 开仓（须 --price，或 --db / STOCK_PLATFORM_ENGINE_MARKET_DB 取只读收盘）
stock-platform-paper buy --symbol 600519 --qty 100 --price 1800 `
  --signal-date 2026-09-04 --now 2026-09-07T09:40:00+08:00

# 查持仓 / 账户 / 最近成交
stock-platform-paper positions
stock-platform-paper account
stock-platform-paper fills --limit 10

# 平仓（--all 或 --qty；无行情时可 --use-avg 用持仓均价）
stock-platform-paper sell --symbol 600519 --all --price 1810 `
  --signal-date 2026-09-04 --now 2026-09-07T09:40:00+08:00
```

别名：`open`=`buy`，`close`=`sell`。仍保留底层 `draft` / `execute` / `status` / `ensure-default`。

闸门与纸面一致：信号日已完成、执行窗口 open、草稿新鲜度；演示请注入 `--now`（与既有 `demo` 相同）。

## 落盘

| 路径 | 内容 |
|------|------|
| `local/paper_cabin/state.json`（默认；可用 `--state` 覆盖） | cash / positions / fills / drafts / accepted / lifecycle |
| 整棵 `local/` | `.gitignore`，**不入库** |

`market.db` **只读**（`--db` 或 `STOCK_PLATFORM_ENGINE_MARKET_DB`）；成交价来源写入返回字段 `priceSource`（`cli:--price` / `market.db:close:YYYY-MM-DD` / `position:avg_price`）。

## Workbench

`GET /api/broker/status` 只读展示当前进程内 broker 的 positions / account（默认 paper）。CLI 落盘状态与 workbench 进程内存**不自动共享**；日用演示以 CLI 模拟舱为准。

## 交叉链

- WorkBuddy 操作员清单：[`workbuddy-runbook.md`](workbuddy-runbook.md) §3
- [`broker-port-honesty.md`](broker-port-honesty.md)
- ADR [0036](../architecture/0036-broker-port.md) / [0037](../architecture/0037-ths-sim-broker.md) / [0038](../architecture/0038-ths-sim-gates.md)
- [`cli-catalog.md`](cli-catalog.md)
- [`packages/execution/README.md`](../../packages/execution/README.md)
