# 契约：绩效 PnL 闭环（Performance PnL / 收益归因）

> 里程碑 **绩效 PnL 闭环** · 版本 `v4.3.0` · 代码单点：
> `packages/research/src/stock_platform_research/performance.py`
> 相关 ADR：[0068](../architecture/0068-performance-pnl-closed-loop.md)（本轮）·
> [0033](../architecture/0033-recommend-performance.md)（原始绩效口径）·
> [0058](../architecture/0058-market-db-source-of-truth.md)（`market.db` 只读真相源）

## 1. 目的

把盘前简报 TopN（决策台账 JSONL）从"计数"推进到**用户可见的收益归因**：
回答"这套推荐逻辑赚不赚钱" —— 胜率、平均收益、超额（alpha）、分桶、累计曲线。

**验收**（路线图）：`performance` JSONL 的 pending 可结算；`raw`/`alpha` 有值；
日报显示真实收益数字。

## 2. 数据流

```
brief.json (TopN)
   │  brief_picks_to_pending / log_brief_decisions        （holding = DEFAULT_HOLDING）
   ▼
data/recommend_decisions.jsonl  …… pending:true, raw:null, alpha:null
   │  settle_performance_log(get_daily, benchmark_get_daily, benchmark_symbol)
   ▼
   ├─ raw   = exit_close / entry_close − 1     （同一 _holding_window）
   └─ alpha = raw − benchmark_return            （同一 entry/exit 日期取基准收盘）
   ▼
performance_summary()  →  metrics + attribution + benchmarkSymbol
   ├─ CLI   stock-platform-performance（含 --settle-daily / --benchmark / --no-benchmark）
   ├─ API   GET /api/research/performance · POST /api/research/performance/settle
   └─ 日报  daily_digest.performance_summary().returns → 「绩效台账」收益概览
```

## 3. 台账字段（JSONL，逐行）

| 字段 | 语义 |
|---|---|
| `date` | 决策日（asof，`YYYY-MM-DD`） |
| `symbol` | 代码（6 位核） |
| `rating` | `Buy` / `Sell` / `Hold`（方向口径见 §5） |
| `raw` | 持有期绝对收益，**百分数字符串**（如 `"+0.38%"`），未结算为 `null` |
| `alpha` | 超额收益（`raw − benchmark`），百分数字符串或 `null`（无基准时） |
| `holding` | 持有期标签（默认 `5d`；`parse_holding_days` 取数字） |
| `pending` | `true`=未结算；结算即置 `false` |
| `source` | 来源（`brief` / `paper_fill` / …） |
| `rank` | 推荐名次（可空） |
| `score` | 综合分（可空） |

## 4. 结算规则

- **entry**＝首个 `date ≥ asof` 的 bar；**exit**＝其后 `holding_days` 个**交易日**的 bar；
  `exit` 越界或任一 close 缺失 → **保持 pending**（`_holding_window` 返回 `None`）。
- 结算窗口的日历缓冲 `end_buffer_calendar_days = 40`（跨长假足够）。
- **绝不编造**：取不到 bar/close → 不写 `raw`，行留 pending。
- **alpha 窗口与 raw 同一**：基准只按 entry/exit **日期**取最近收盘（`_close_on_or_before`）。
- **回填**：已结算但 `alpha` 为 `null` 的行，在**下一次带基准的结算**中补齐（不改 `raw`）。
- 结算只在有新值（`settledNewly > 0` 或 `alphaSettledNewly > 0`）时才重写 JSONL。

## 5. 指标口径（承接 ADR 0033，不改）

| 指标 | 口径 |
|---|---|
| `direction_accuracy` | 方向评级（`Buy`/`Sell`/`Overweight`/`Underweight`，**`Hold` 不计**）中 `sign(return)×direction>0` 占比；**prefer alpha** |
| `up_rate` / `winRate` | `raw > 0` 占比（描述标的路径，**与判断对错无关**） |
| `outperform_rate` / `beatBenchmarkRate` | `alpha > 0` 占比（有 alpha 时） |
| `avg_return` / `avgReturn` | 持有期绝对收益均值 |
| `avg_alpha` / `avgAlpha` | 超额均值（有 alpha 时） |

**不算**夏普/年化；样本 `< MIN_MEANINGFUL_SAMPLE`(20) 标 `sample_note`/`notes` 噪音提示。

## 6. 归因出口（`build_attribution`）

`performance_summary(...)["attribution"]`：

| 键 | 含义 |
|---|---|
| `count` / `winRate` / `avgReturn` / `medianReturn` / `avgAlpha` / `beatBenchmarkRate` / `best` / `worst` | 汇总 |
| `byRank[]` | `{rank|null, label, count, up_rate, avg_return, avg_alpha, outperform_rate, best, worst}` |
| `byScore[]` | 同上 + `bucket` / `label` / `minScore` / `maxScore`（**等数量**分桶，默认 3 桶，低→高） |
| `byDate[]` | `{date, ...同汇总}` |
| `equityCurve[]` | `{date, symbol, cumulative}` —— 逐决策 `∏(1+raw)` |
| `benchmarkSymbol` / `notes[]` | 基准符号 / 口径与噪音提示 |

**⚠️ `equityCurve` 不是可交易组合曲线**：决策层持有窗口**重叠**、**不含成本**；与 PIT 组合回测
（B 域）**刻意分离**。它答"判断赚不赚"，不答"账户长什么样"。

## 7. 基准（benchmark）

| 项 | 值 |
|---|---|
| 默认 | `000905`（中证500，`market.db` 存为 `000905.SZ`） |
| 覆盖 | 环境变量 `STOCK_PLATFORM_BENCHMARK_SYMBOL`（CLI 另有 `--benchmark`，优先） |
| 为何不是沪深300 | `market.db` **无** `000300`；`000905`/`000852` 完整，`000016` 止于 2026-09-30，`510300.SH`（沪深300ETF）仅 65 行（C2 ETF 退化） |
| 关闭 | CLI `--no-benchmark`；或结算时不传 `benchmark_get_daily` |
| 换基准的历史重算 | **不自动** —— 历史 `alpha` 不会重算，须重新结算（已知边界） |

## 8. 出口

| 出口 | 用法 |
|---|---|
| CLI | `stock-platform-performance`（`--settle-daily` / `--benchmark SYM` / `--no-benchmark` / `--json-out` / `--settle-fixture` / `--align-fills`） |
| 调度 | 盘后 `stock-platform-postmarket`（`-SettleAfter`）→ `_settle_after_pipeline` 带基准结算；`meta.alphaSettledNewly` 计数 |
| API | `GET /api/research/performance?autoSettle=true`；`POST /api/research/performance/settle`（均带基准） |
| 日报 | `daily_digest.performance_summary().returns`（复用本模块单点 口径） |

## 9. 非目标

- 不做可交易组合曲线 / 净值回撤 / 夏普（那是 B 域回测）。
- 不代抓行情：基准与个股 bar 均来自 `market.db`（ADR 0058，只读）。
- 不触碰 `liveTradingEnabled`；全程 SIMULATE（ADR 0064）。

## 10. 免责

研究口径、SIMULATE；非投资建议；持有窗口重叠、不含成本。
