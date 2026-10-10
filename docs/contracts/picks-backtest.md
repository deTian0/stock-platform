# 契约：选股 ↔ 回测闭环（Picks Backtest）

> 里程碑 **X4** · 版本 `v4.0.4` · 代码单点：`packages/research/src/stock_platform_research/picks_backtest.py`
> 共享引擎：`packages/research/src/stock_platform_research/book_replay.py`
> 相关 ADR：[0059](../architecture/0059-picks-backtest-parity.md)
> 上游同源：`a-stock-engine` 的选股榜（②A/②B/③A）+ 本地回测引擎

## 1. 目的

把「每日推荐」与「回测绩效」拉进**同一套口径**，使推荐不再用一个独立的小尺子衡量。

在此之前，平台有两把尺子：

| 尺子 | 实现 | 回答的问题 |
|---|---|---|
| 推荐绩效（旧） | `performance.py` → `direction_accuracy`，T+N 固定持有、**无成本**、不复权 | 「这只票 T+N 后涨了吗」 |
| 回测绩效 | `backtest.run_portfolio_backtest`，共享退出规则 + 成本模型 + 组合指标 | 「按规则持有这只票，扣费后赚了吗」 |

两者都在，但**互不承认**：一只「涨了」的票未必能过止损/止盈/趋势/最大持有这一串规则，扣费后更是另一回事。
X4 的做法不是再写一把尺子，而是让推荐**进同一台引擎**。

**验收**（路线图 X4）：每日 picks 自动进回测对照；推荐绩效与回测口径同源（承接 B5）。

## 2. 单点定义：`book_replay.replay_book`

回测循环（逐日复盘 → 盯市 → 建仓）被抽成**唯一实现** `book_replay.replay_book(feats, entry_provider, params)`。
两条调用路径只有 **entry provider** 不同：

| 路径 | 包装函数 | entry provider |
|---|---|---|
| 选股回测 | `backtest.run_portfolio_backtest` | `book_replay.screener_entry_provider`（lvrev 打分 + 入场闸门 + 分数下限） |
| 推荐回放 | `picks_backtest.run_picks_backtest` | `picks_backtest.picks_entry_provider`（当日 picks 账本，按 `rank` 排序） |

循环内的一切**不区分来源**，一律复用单点：

- 退出判定 `rules.evaluate_exit`、峰值推进 `rules.advance_peak`
- 涨跌停封板 `rules.is_limit_up` / `rules.is_limit_down`
- 成本与滑点 `portfolio.CostModel`
- 指标口径 `portfolio.compute_metrics`（含 `by_asset` 分资产）
- 仓位上限 / 每日建仓上限 / 100 股整手 / 等权 slot 分仓 / `regime` 闸门

`tests/test_book_replay.py` 用**重构前**抓取的 8 个场景摘要（曲线与成交哈希 + 全部指标）钉住
`run_portfolio_backtest`，证明抽取是**纯重构**（逐位不变）。

## 3. picks 输入契约

**pick row**（冻结形状）：

| 字段 | 必填 | 含义 |
|---|---|---|
| `date` | ✅ | 信号交易日（brief 的 `asof`），`YYYY-MM-DD` |
| `code` | ✅ | 推荐标的代码；`600519` 与 `600519.SH` 均可 |
| `rank` | ❌ | 推荐内序号；同日按 `rank` 升序建仓，缺省排在有序项之后 |
| `score` | ❌ | 综合分（沿用 `composite_score` 别名） |

别名：`date`/`asof`、`code`/`symbol`、`score`/`composite_score`。缺 `date` 或缺 `code` 的行**丢弃**，
不猜；同 `(date, code)` 去重（保留首次）。

`picks_from_brief(brief, board=None)` 是官方提取口：

- `board=None` → `brief["picks"]`（②A 质量榜头部，语义自 X2 冻结）
- `board=<slug>` → `brief["rankings"]["boards"][slug]["items"]`（`quality` / `short_term` / `holdings` / `actions` / `watchlist`）

## 4. 账本（append-only JSONL）

路径：流水线默认 `{out}/picks_ledger.jsonl`；CLI 可 `--ledger` 指定；代码可 `STOCK_PLATFORM_PICKS_LEDGER`。

- **只追加**，以 `(date, code)` 去重 —— 同一天重复生成 brief 不会重复计数。
- `append_picks_ledger(path, picks, skip_existing=True)` 返回**实际写入**的行，便于流水线回显。
- 账本是「推荐原始记录」，不是绩效库：**不与** `performance` JSONL（T+N 方向命中）合并。

## 5. 口放规则

- **建仓价**：picks 当日的**参考收盘价**（与引擎一致，无 T+1 开盘价）。provider 从**当日行情帧**
  读 `close`，不读 pick 里存的价，保证与选股回测同价。
- **无行情的 pick**：该 `(date, code)` 当日无 bar → **丢弃并计数**（`droppedPicks`），**不造价格**。
- **窗口外 pick**：`date` 不在行情帧交易日内 → 计入 `picksOutsideWindow`。
- **默认宇宙**：推荐侧 `universe="all"`（推荐了 ETF 就照 ETF 回放，不被股票过滤静默吃掉）；
  对照的选股侧保留自身 `stock` 基线。实际宇宙在 `params.universe` 回显。
- **fail-closed**：空账本 / 无行情 → `ok=False` + 中文 `reason`，**不返回零填充曲线**。
- **`ok` 判据**：只要推荐形成了**至少一个持仓**即 `ok=True` —— 含窗口结束仍持有的仓位
  （`open_positions`）。只看已平仓成交会把「还拿着的推荐」误判成「没成交」。
  `enteredCodes` 同样合并已平仓与未平仓。

## 6. 出口

| 出口 | 用法 |
|---|---|
| 流水线 | `run_daily_pipeline(..., track_picks_ledger=True)`（默认开）每次会话自动把 ②A 头部追加进账本；`replay_picks=True` + `replay_bars=<DataFrame>` 时额外回放账本并写 `{asof}/picks_replay.json`；`replay_against_screener=True` 时返回选股侧与 `delta`。两个阶段均 **best-effort**，失败落 `report.picksReplay["error"]`，**绝不**中断 brief |
| CLI | `stock-platform-picks-backtest`（`--ledger` / `--briefs-dir` / `--compare` / `--start` / `--end` / `--json`），只读 `market.db` |
| 代码 | `run_picks_backtest(picks, bars, ...)`；`compare_picks_vs_screener(picks, bars, ...)` |

`replay_against_screener=True` 时，`replay_kwargs` 的形状变为
`{"picks_kwargs": {...}, "screener_kwargs": {...}}`（非对照模式为扁平参数）。

`report.picksReplay` 是**裁剪摘要**（去掉 `equity_curve` / `trades`，加 `tradeCount` / `curvePoints`）——
完整载荷只在 `{asof}/picks_replay.json`，避免长回放撑爆 `manifest.json`。

## 7. 对照（`compare_picks_vs_screener`）

同一堆 bars 分别跑推荐回放与选股回测，返回：

| 键 | 内容 |
|---|---|
| `picks` | 推荐侧完整结果 |
| `screener` | 选股侧完整结果 |
| `delta` | `picks 指标 − screener 指标`，逐键相减，**不做二次归一** |
| `deltaKeys` | 参与相减的指标键清单 |
| `sameDefinition` | 身份证明块：`singleLoopDefinition` / `singleExitDefinition` 为**对象同一性**断言（非等价） |

## 8. 非目标

- 不替换 `performance.direction_accuracy`。两者回答不同问题（命中次数/方向 vs 组合规则盈亏），
  **刻意并存**，不合并成一套表。
- 不实现 T+1 开盘价成交、不做真实复权因子对齐（沿用 `pct_chg` 重建复权序列，见 B1 说明）。
- 不做参数寻优 / walk-forward（那是 `backtest/walk-forward` 与 S 域的职责）。
- 不新增 Workbench 端点；本轮出口为流水线 + CLI（UI 面留待后续里程碑）。

## 9. 免责

研究口径、SIMULATE；`liveTradingEnabled=False`；非投资建议。
