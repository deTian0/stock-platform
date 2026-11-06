# CLI 一览（agent / 人日用）

> SSOT：各包 `pyproject.toml` 的 `[project.scripts]`。本表防漂移；改脚本名须同步改这里。  
> dotenv：优先 `local/.env`，见 [`../contracts/dotenv-loading.md`](../contracts/dotenv-loading.md)。

## research（`stock-platform-research`）

| 命令 | 用途 | 读 local/.env |
|------|------|---------------|
| `stock-platform-init` | 初始化 `local/` 运行时配置行 | 是 |
| `stock-platform-shadow-board` | 多策略影子 Final Board（五校→硬 Round2→只写 `local/shadow/`；不改出厂；`--perf-summary` / `--settle-daily` 前向账本；`--backtest` 历史对照 lvrev） | 是（`--universe` JSON；`--backtest` 读 market.db） |
| `stock-platform-daily` | 日更流水线 | 是 |
| `stock-platform-brief` | 只建 brief | 是 |
| `stock-platform-digest` | 盘前/盘后/午间简报（`--session pre|post|midday`） | 是 |
| `stock-platform-day-quote` | 当日行情台账 | 是 |
| `stock-platform-sameday` | 选股→次日收盘战绩 | 是 |
| `stock-platform-performance` | 绩效 JSONL / settle | 是 |
| `stock-platform-performance-proxy` | 代理台账 | 是 |
| `stock-platform-loop-health` | 日用循环体检 | 是 |
| `stock-platform-data-quality` | market.db 数据质量（T3） | 是 |
| `stock-platform-aux-market` | 平台自有补充库 `local/aux_market/aux_market.db`（指数日线名称校验 + `--codes` 个股 OHLC；经 `em_get`；`--indices/--codes/--start/--end/--dry-run`；不写 market.db；ADR 0095） | 是 |
| `stock-platform-ops-ledger` | 调度执行台账 | 是 |
| `stock-platform-attribution` | 收益归因 | 是 |
| `stock-platform-strategy-adoption` | 采纳闸门 | 是 |
| `stock-platform-backtest` / `picks-backtest` / `strategy-ab` | 回测族 | 是 |
| `stock-platform-factor-ic` / `strategy-sensitivity` / `strategy-neutralization` | 因子/敏感度/中性化 | 是 |
| `stock-platform-refresh` / `score` / `rankings` / `hits` / `symbol-master` / `market-universe` / `position-review` | 供数与研究辅助 | 是 |
| `stock-platform-workbuddy-bridge` | workbuddy 行情桥 | 是 |
| `stock-platform-report-html` | Markdown→HTML | 否（路径参数） |

## agents

| 命令 | 用途 | 读 local/.env |
|------|------|---------------|
| `stock-platform-debate` | 顾问辩论（`--engine off\|deterministic\|llm`）；**不写** picks/绩效 | 是（LLM 提供商） |

例：

```text
stock-platform-debate --engine deterministic --symbol 600519 --asof 2026-10-07 --summary
```

## execution

| 命令 | 用途 | 读 local/.env |
|------|------|---------------|
| `stock-platform-paper` | 纸面 SIMULATE：`status` / `ensure-default` / `draft` / `execute` / `demo`；**无 live 开关** | 否（状态默认 `local/paper_session.json`） |

例：

```text
stock-platform-paper demo
stock-platform-paper status
```

## workbench

| 命令 | 用途 |
|------|------|
| `stock-platform-workbench` | 本地 API + UI |

## 仍主要走 API（无对等 CLI）

- intel-report / 分钟 / 深度盘口等 `/api/market/*` 扩展面  
- deep-graph（默认关；见 ADR 0088/0089）  
- Workbench 向导多步状态机的完整 UI 流

Agent 编排优先本表 CLI；缺能力再开 workbench API。
