# 契约：绩效代理台账（Performance Proxy Ledger）

> 里程碑 **R4** · 版本 `v4.7.1` · 代码单点：
> `packages/research/src/stock_platform_research/performance_proxy.py`
> 相关 ADR：[0074](../architecture/0074-performance-proxy-ledger.md)（本轮）·
> [0059](../architecture/0059-picks-backtest-parity.md)（picks ↔ 回测同引擎）·
> [0068](../architecture/0068-performance-pnl-closed-loop.md)（绩效 PnL 闭环，汇总算术单点）·
> [0073](../architecture/0073-daily-loop-health-single-point.md)（把样本不足升格为裁决）

## 1. 目的

真实台账 `data/recommend_decisions.jsonl` 的 settled 样本受**日历硬约束**（每交易日 ≤ N 条 +
必须等持有窗口走完），长期停在个位数 = `MIN_MEANINGFUL_SAMPLE`(20) 的**噪音区**，
「这套选股逻辑赚不赚钱」无法回答。

本契约定义一个**代理台账**（proxy ledger）：把**回测引擎自己的成交**翻译成与真实台账
**逐字段同形状**的决策行，从而用一段 ≥1 年的历史就凑出 ≥20 条 settled 样本。

**代理 ≠ 真实。** 两者的差异是**故意的**，故本契约的核心条款是 **§4 禁止混算**。

## 2. 单点定义

| 环节 | 单点 | 说明 |
|---|---|---|
| 回测循环 | `book_replay.replay_book` | ADR 0059：选股回测与推荐回放**同一个循环** |
| 汇总算术 | `performance.performance_summary` → `compute_performance` | ADR 0068：两侧**同一把尺子** |
| 翻译口 | `performance_proxy.trades_to_decision_rows` | 回测 `trades` → 决策行（本契约新增） |
| 并排视图 | `performance_proxy.build_proxy_view` | 两侧各汇总一次，**不合并** |

新增的是**翻译与呈现**，**没有**第二份回测引擎，也**没有**第二套指标口径。

## 3. 代理行形状（冻结）

代理行与真实台账**共用同一个 JSONL schema**（见 `performance-pnl.md` §3），取值如下：

| 字段 | 代理取值 | 备注 |
|---|---|---|
| `date` | 建仓日 = `equity_curve[trade.entry_idx].date` | `entry_idx` 越界 → `""` |
| `symbol` | `trade.code` | 原样（含交易所后缀，如 `600079.SH`） |
| `rating` | `"Buy"` | 回测只做多 |
| `raw` | **扣费**净收益 `net_ret`（百分数 → `"+x.xx%"`） | 复用 `performance.format_pct` |
| `alpha` | **恒 `null`** | 代理侧无同窗口基准超额，**不编造** |
| `holding` | `f"{held_days}d"` | **真实持有天数**，非固定 `5d` |
| `pending` | **`false`** | 成交即已结算 |
| `source` | **`"backtest_proxy"`** | 数据层面杜绝误认 |
| `ledgerKind` | `"proxy"` | 与真实行区分 |

**附加审计键**（读取器会忽略，仅供审计/展示）：`exitReason` / `exitDate` /
`grossRetPct` / `netRetPct` / `assetClass`。

**丢弃规则**（fail-closed，不猜）：无 `code` 或 `net_ret` 不可解析的行**丢弃**。

## 4. 口径差异 ⇒ **禁止混算**（本契约的硬条款）

| 维度 | 真实台账（real） | 代理台账（proxy） |
|---|---|---|
| 信号源 | `brief.asof`（实时盘前 TopN） | 回测建仓日（历史回放） |
| 出场 | T+N 固定持有（默认 `5d`） | 引擎退出规则（止损/止盈/趋势/最长持有） |
| 收益口径 | `raw` 裸收益（**不含成本**） | `net_ret` 扣费净收益（**含佣金/印花税/滑点**） |
| 窗口关系 | 决策间**重叠**（非组合曲线） | 单账户序列（仓位上限 + 现金约束） |

**四维全不同 ⇒ 任何合计、平均、加权、相减都会产生无意义数字。**

强制性约束：

1. `build_proxy_view` 的返回**顶层不得**出现任何跨侧合并字段
   （`total` / `combined` / `merged` / `all` / `sum` 等一律禁止）；
2. 必须显式输出 `comparability.combinable = false` + 中文 `reason`；
3. 两侧必须**各自**携带 `ledgerKind`（`real` / `proxy`）与 `scale`（口径自述）；
4. 任何下游汇总（报告 / API / UI）必须**分栏**，把两侧标签打在**近处**。

单测 `test_build_proxy_view_is_never_combinable` 逐名断言第 1、2 条。

## 5. 台账文件（append-only? —— 否，**覆盖写**）

路径：CLI `--proxy-log`；代码可 `STOCK_PLATFORM_PERFORMANCE_PROXY_LOG`；
默认 `./data/performance_proxy.jsonl`。

- `write_proxy_ledger` **覆盖整表**（`rewrite_jsonl`），**不追加**——
  代理台账是「一次回测的完整派生」，追加会让同一窗口的样本重复计数。
- `load_proxy_ledger` 对缺失文件返回空表（**不抛**）。
- 代理台账是**派生件**，不是决策原始记录：与真实台账（`recommend_decisions.jsonl`）
  和 picks 账本（`picks_ledger.jsonl`）**三份文件、三种语义**，互不合并。

## 6. 出口

| 出口 | 用法 |
|---|---|
| CLI | `stock-platform-performance-proxy`（`--db` / `--years` / `--start` / `--end` / `--ledger` / `--briefs-dir` / `--universe` / `--real-log` / `--proxy-log` / `--out-dir` / `--no-write` / `--json`），只读 `market.db` |
| 代码 | `trades_to_decision_rows` / `build_proxy_view` / `render_proxy_markdown` |
| 产出 | 代理台账 `performance_proxy.jsonl`；报告 `data/performance/proxy_vs_real.{json,md,html}` |

引擎选择：给了 `--ledger` / `--briefs-dir` → 走 **picks 入口**（`run_picks_backtest`）；
否则走**选股侧**（`run_portfolio_backtest`）。**两条都经 `replay_book`**，故成交形状一致、
翻译口只有一份。

CLI 退出码：回测 `ok=False` → `2`（并**仍然**写出如实报告）；否则 `0`。

## 7. 非目标

- **不**替换或改写真实台账；真实台账仍是唯一「实时决策记录」。
- **不**把代理数字冒充前瞻绩效：代理是「同一引擎在历史上的选股侧表现」。
- **不**新增第二套指标口径（复用 ADR 0068）；**不**新增第二份回测循环（复用 ADR 0059）。
- **不**新增 Workbench 端点（UI 面留待后续里程碑）。
- **不**在代理侧编造 `alpha`（无基准即 `null`）。

## 8. 免责

研究口径、SIMULATE；`liveTradingEnabled=False`；真实与代理台账口径不同、**禁止混算**；
非投资建议。
