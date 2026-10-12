# 0068 — 绩效 PnL 闭环（JSONL 决策台账 → 用户可见收益归因）

- **状态**：Accepted
- **日期**：2026-10-12
- **里程碑**：绩效 PnL 闭环（发布 `v4.3.0`）
- **相关**：ADR [`0033`](0033-recommend-performance.md)（推荐决策绩效统计，本轮**扩展**）·
  ADR [`0058`](0058-market-db-source-of-truth.md)（`market.db` 只读真相源）·
  ADR [`0064`](0064-live-trading-charter.md)（Phase 0 纯模拟盘）·
  契约 [`docs/contracts/performance-pnl.md`](../contracts/performance-pnl.md)

---

## 1. 背景：计数有了，收益没有

路线图上一块砖（`v4.2.0`：调度上线 + 用户可读日报）收官后，`docs/plans/handoff-v4.2.0.md`
把下一块砖定为 **"绩效 PnL 闭环（performance JSONL → 用户可见收益归因）"**，并点名两个未解问题：

> 1. **为什么全是 pending？** …可能是：结算窗口判定、market.db 缺该票该区间 bar、或 settle 路径未被实际触发过。
> 2. **`raw` / `alpha` 为何恒 null**：找到结算函数，确认它写不写这两个字段。
> 3. **收益归因**：现在没有任何地方回答"这套推荐逻辑赚不赚钱"。

修复前的实测状态：`data/recommend_decisions.jsonl` 3 行**全部 `pending: true`**，
`raw` / `alpha` 全 `null`；日报「绩效台账」只有 pending/settled **计数**。

## 2. 根因（实测定位，均已复现）

| # | 现象 | 根因 | 证据 |
|---|---|---|---|
| **R1** | 3 条 pending 不结算 | **结算路径从未被执行**（盘后任务刚注册、尚未自然运行）；**不是**窗口判定或数据缺失 | 手工跑 `performance_cli --settle-daily` → `settledNewly=3`：`600519 +0.38%` / `300760 +2.96%` / `000001 -1.76%`。`_holding_window` 对三条都能取到合法 entry/exit 对 |
| **R2** | `alpha` 结构性恒 null | `settle_pending_entries` **只在调用方传入 `alpha_returns` 映射时才写 alpha**，而**三个调用方（`daily_cli` / `performance_cli` / workbench 路由）从无一处构造基准** → 平台上**没有任何地方**能算出超额收益 | 全仓 grep `alpha_returns` 仅出现在 `performance.py` 定义与 workbench 路由的委派（均为默认 `None`） |
| **R3** | 记账口径漂移 | `daily_cli._settle_after_pipeline` 以 `holding="1d"` 记账，而 workbench / `brief_picks_to_pending` 默认 `5d` | 同一份 JSONL 里同时存在两种持有期语义 |

## 3. 决策

### 3.1 收益归因作为一等出口（`build_attribution`）

在 `packages/research/.../performance.py` 内新增**纯函数**归因单点，回答"赚不赚钱"：

| 函数 | 产出 |
|---|---|
| `bucket_by_rank` | 按推荐 `rank` 分组的胜率/均收益/均 alpha |
| `bucket_by_score` | 按综合分**等数量分桶**（低→高）的同上指标 |
| `bucket_by_date` | 按决策日聚合 |
| `equity_curve` | 决策序列**等权累计**曲线（`∏(1+raw)`） |
| `build_attribution` | 汇总：`winRate` / `avgReturn` / `medianReturn` / `avgAlpha` / `beatBenchmarkRate` / `best` / `worst` + 上述分桶 + `equityCurve` + `notes` |

`performance_summary` 增加 `"attribution"` 与 `"benchmarkSymbol"` 两个键，**原有键不变**（向后兼容）。

### 3.2 基准与 alpha（`alpha = raw − benchmark`）

- **基准可配**：`STOCK_PLATFORM_BENCHMARK_SYMBOL`，默认 **`000905`（中证500）**。
- **为什么不是沪深300**：`market.db` **没有** `000300`；仓库里的指数序列是
  `000905.SZ`（中证500）/ `000852.SZ`（中证1000）/ `000016.SZ`（上证50，止于 2026-09-30）。
  沪深300ETF（`510300.SH`）只有 65 行且止于 2026-09-08（C2 记录的 ETF 退化）。
  故取**中证500**作为小/中盘选股的代理基准，并保留环境变量覆盖位。
- **同一个窗口定义**：`raw` 与 `alpha` 用**同一个** `_holding_window`（入场=首个 ≥ asof 的 bar，
  出场=其后 `holding_days` 个交易日）；基准只按**入场/出场日期**取最近收盘（`_close_on_or_before`），
  因此两者**必然是同一会话窗口**，不存在"股票用 A 窗、基准用 B 窗"的口径错配。
- **缺失即留空，绝不编造**：基准取不到 bar → `alpha` 保持 `null`（与 ADR 0033 的 fail-closed 一致）。

### 3.3 结算会话回填（back-fill）

`settle_pending_entries` / `settle_performance_log` 新增 `benchmark_get_daily` / `benchmark_symbol`：

- 对**新结算**的行，同一趟算出 `alpha`；
- 对**已经结算但 `alpha` 仍为 null** 的行（即本轮之前写下的历史台账），**在下一次结算时回填 alpha**，
  无需重建 JSONL。实测：3 条历史行 `alphaSettledNewly=3`。

### 3.4 持有期单点（消除 R3）

新增 `DEFAULT_HOLDING = "5d"` 单点，`brief_picks_to_pending` / `log_brief_decisions` /
`align_fills_to_performance` 默认值统一引用它；`daily_cli` 不再硬写 `"1d"`。
**记账口径 = 结算口径 = 日报口径**，三处不可能再漂移。

### 3.5 日报显示真数字

`daily_digest.performance_summary` 从"计数"升级为"计数 + 收益概览"：

- **计数**仍走宽容逐行解析（坏行跳过、不致命），键 `available/total/pending/settled/asofPending` **不变**；
- 新增 `returns` 键 = `build_attribution(settled_records(rows))` —— **直接复用 research 单点 口径**，
  日报数字与 `stock-platform-performance` CLI 不可能分叉；
- 日报正文「绩效台账」新增一行：`收益概览（已结算 N 条 / 基准 000905）：胜率 …，平均收益 …，跑赢基准 …，最好 …、最差 …`。

## 4. 后果

### 正面

- **"赚不赚钱"第一次有确定答案**：日报与 CLI 都能给出胜率 / 平均收益 / 跑赢基准率 / 分桶 / 累计曲线；
- **alpha 从结构性 null 变为真实超额**（含历史行回填），口径单点、窗口对齐；
- **记账/结算/日报三口径统一**为 `DEFAULT_HOLDING`；
- 全部为**只读 + 纯函数**：不改 `market.db`、不碰 `liveTradingEnabled`、无新依赖。

### 负面 / 边界

- **不是可交易组合曲线**：`equityCurve` 是决策序列等权累计，持有窗口**重叠**、**不含成本**
  （`notes` 每次都写明），与 PIT 组合回测（B 域）**刻意分离** —— 前者答"判断准不准/赚不赚"，
  后者答"账户会长什么样"；
- **样本极小**：当前 3 条 → 比率噪音大（`MIN_MEANINGFUL_SAMPLE=20` 标注照旧）；
- **基准是代理**：中证500 ≠ 沪深300；换基准只需改环境变量，但历史 alpha **不会**自动重算
  （须重新结算；已在契约写明）。

## 5. 实测证据（2026-10-12，本机，真 `.env` + 真 `market.db`）

| 项 | 结果 |
|---|---|
| 手工结算 3 条 pending | `settledNewly=3`：`600519 +0.38%` / `300760 +2.96%` / `000001 -1.76%` |
| alpha 回填（同一台账再次结算） | `alphaSettledNewly=3`：`+2.41%` / `+4.99%` / `-7.72%`（基准 中证500） |
| 汇总 | `direction_accuracy` 0.667；`avgReturn` +0.53%；`avgAlpha` −0.11%；`beatBenchmarkRate` 0.667 |
| 日报渲染 | `data/digests/2026-10-12.md`「绩效台账」出现「收益概览（已结算 3 条 / 基准 000905）…」 |
| 全量测试 | `pytest packages apps`（replay）**988 passed / 0 failed**（980 → 988，**+8**） |
