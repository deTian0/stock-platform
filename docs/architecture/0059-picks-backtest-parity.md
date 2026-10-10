# ADR 0059：选股与回测同引擎（picks ↔ backtest parity）

- **状态**：Accepted（里程碑 `X4`，2026-10-10）
- **日期**：2026-10-10
- **相关**：ADR 0043（组合指标单点）· ADR 0057（命中追踪）· ADR 0058（行情真相源）· [`docs/contracts/picks-backtest.md`](../contracts/picks-backtest.md) · [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md)

## 背景

路线图 `X4` 的原文是：**「每日 picks 自动进回测对照；推荐绩效与回测口径同源（承接 B5）」**。前置 `B5`（回测↔在线规则统一）与 `X3`（命中追踪）均已就位。

当时的实际状态是**两把尺子并存、互不承认**：

| 尺子 | 实现 | 口径 | 回答 |
|---|---|---|---|
| 推荐绩效 | `performance.performance_summary` → `direction_accuracy` | T+N 固定持有、**无成本**、不复权、窗口重叠 | 「这只票 T+N 涨了吗」 |
| 回测绩效 | `backtest.run_portfolio_backtest` | 共享退出规则 + 成本模型 + 组合指标 | 「按规则持有、扣费后赚了吗」 |

两者都对，但**不可比**：`B5` 已经把「退出判定/冷静期/持仓偏差/涨跌停」收敛成 `rules.py` 单点，可推荐侧
从没进过那台引擎。要「推荐绩效与回测口径同源」，只有两条路：

1. 把 `performance` 的算法改成组合口径 —— 但方向命中率是运营信号，改了就是丢信息；
2. 让**推荐进同一台引擎**，用同一套规则算一遍 —— 保留旧指标，新增同源对照。

`B5` 的教训（`docs/contracts/trading-rules.md`）说得很清楚：**多一条调用路径就多一份漂移风险**，
单点定义必须真的只有一个实现。所以路 2 的前提是先把回测循环抽出来。

## 决策

### 1. 抽出唯一回测循环 `book_replay.replay_book`

「逐日复盘 → 盯市 → 建仓」循环从 `backtest.run_portfolio_backtest` 内部搬到
`book_replay.replay_book(feats, entry_provider, params)`。两条路径只有 **entry provider** 不同：

| 路径 | 包装 | provider |
|---|---|---|
| 选股回测 | `backtest.run_portfolio_backtest` | `screener_entry_provider`（lvrev + 闸门 + 分数下限） |
| 推荐回放 | `picks_backtest.run_picks_backtest` | `picks_entry_provider`（当日 picks 账本，按 rank） |

循环内**不区分来源**的一切都是单点：`rules.evaluate_exit` / `advance_peak` / `is_limit_up` /
`is_limit_down`、`portfolio.CostModel`、`portfolio.compute_metrics`、仓位/整手/等权 slot/`regime` 闸门。

**抽取必须是纯重构**，因此从重构前的引擎抓了 8 个场景（股票 / ETF / 混合 / 滑点 / 零费 / 冷静期 /
旧 `verbatim` 百分比尺度）的**曲线与成交哈希 + 全部指标**存为
`packages/research/tests/fixtures/book_replay_baseline.json`，`tests/test_book_replay.py` 逐位比对。
抽取后实测：**8/8 场景逐位一致**。

### 2. 推荐走账本 + 回放

- **picks 账本**：`{out}/picks_ledger.jsonl`，append-only，以 `(date, code)` 去重；流水线每次会话
  自动把 ②A 头部写入（`track_picks_ledger=True` 默认开）。这是「每日 picks 自动进回测对照」的进料口。
- **回放**：`run_picks_backtest(picks, bars, ...)` 用**共享循环**跑账本，返回与选股回测**同键**的结果块
  （`equity_curve` / `trades` / `open_positions` / `metrics` / `params`）。
- **对照**：`compare_picks_vs_screener` 同一堆 bars 跑两侧，`delta` 为逐键相减（因两侧同口径，
  无需二次归一），并附 `sameDefinition` 身份证明。

### 3. 新增 `open_positions` 出口

窗口结束仍持有的仓位**从不出现在 `trades`**（没卖就没有成交记录）。这既让回放无法重建完整日程，
也让「我到底还拿着什么」这个问题没有答案。故 `replay_book` 新增 `open_positions[]`
（`code` / `entry_idx` / `entry_price` / `shares` / `target` / `peak` / `held_days`），两条路径都透出。
该字段是**纯新增**，不影响既有键与指标。

### 4. 默认宇宙各自保留

推荐侧默认 `universe="all"`（推荐了 ETF 就按 ETF 回放，不被股票过滤静默吃掉）；
对照的选股侧保留自身 `stock` 基线。实际口径在 `params.universe` 回显 —— **不让默认值偷走可比性**，
而是让差异显式可见。

### 5. 旧指标不删、不合并

`performance` 的 `direction_accuracy` 与 `portfolio.compute_metrics` 回答不同问题
（命中次数/方向 vs 组合规则盈亏），**刻意并存**。契约「非目标」一节写明，防后人「统一口径」时误删。

## 非目标

- 不回填历史推荐官（账本从启用日起累计；用 `--briefs-dir` 可把已存 brief 一次性喂进对照）。
- 不做 T+1 开盘价成交、不引入真实复权因子（沿用 B1 的 `pct_chg` 重建序列）。
- 不新增 Workbench 端点 / 前端面板 —— 本轮出口为**流水线 + CLI**，UI 面留待后续里程碑。
- 不做参数寻优 / walk-forward（属 S 域与既有 `/backtest/walk-forward`）。

## 后果

- 「推荐涨了」与「按规则持有赚了」首次可用**同一台引擎**并排看；`delta` 直接是两者差。
- `backtest.run_portfolio_backtest` 变成薄封装（只喂 provider），回归风险集中在 `book_replay`，
  且有逐位基线钉住。
- `run_daily_pipeline` 新增账本与回放两个 best-effort 阶段：失败落 `report.picksReplay["error"]`，
  **绝不**中断 brief（与 X3 命中追踪同一策略）。
- 每个会话多一次小体量 JSONL 追加（≤ 20 行），对 08:30 路径影响可忽略。

## 风险

| 风险 | 缓解 |
|---|---|
| 抽取循环时悄悄挪动基线 | 8 场景逐位哈希 fixture（`test_book_replay.py`） |
| 推荐侧与选股侧宇宙不同导致误读 | `params.universe` 双侧回显 + `sameDefinition` 证明块 |
| 账本无限增长 | append-only + `(date, code)` 去重；按会话约 ≤20 行，年约 5k 行 |
| 回放拖慢日常路径 | `replay_picks` 默认 **关**（需显式传 `replay_bars`）；账本写入是常数级 |
| 未平仓仓位被当成「没买过」 | `open_positions` 出口 + 契约写明 |

## 参考

- 共享循环：`packages/research/src/stock_platform_research/book_replay.py`
- 推荐回放：`packages/research/src/stock_platform_research/picks_backtest.py`
- CLI：`packages/research/src/stock_platform_research/picks_backtest_cli.py`（`stock-platform-picks-backtest`）
- 流水线：`packages/research/src/stock_platform_research/daily_pipeline.py`
- 测试：`packages/research/tests/test_book_replay.py` · `test_picks_backtest.py` · `test_daily_pipeline.py`
- 基线 fixture：`packages/research/tests/fixtures/book_replay_baseline.json`
