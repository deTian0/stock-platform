# 契约：收益归因 / 负收益根因诊断（loss attribution）

- 里程碑：`Y3`（`v4.11.0`）
- 单点：`stock_platform_research.attribution`
- CLI：`stock-platform-attribution`
- ADR：[0078](../architecture/0078-loss-attribution.md)
- 状态：生效（SIMULATE / 只读 / 研究口径）

## 1. 目的与范围

回答一个此前无出口的问题：**这套选股逻辑为什么亏钱？**

把一段窗口的损失分解成**互不重叠、各自可处置**的少数几项原因，并给出**动作建议**。

**不做**：不改生产默认档、不写 brief / picks、不做参数寻优、不做择时/仓位归因、不落任何 API 或面板。

## 2. 术语

| 术语 | 含义 |
|---|---|
| **信号日** `signal_date` | 面板里的一行所对应的交易日（当日收盘截面打分） |
| **前瞻收益** `fwd_k` / `meanReturn` | 该 code 自信号日起 `k` 个**交易日**的简单收益（`close[t+k]/close[t] − 1`）——**绝对口径** |
| **超额** `excess_k` / `meanExcess` | `fwd_k − bench_fwd_k`（同一交易日历、同窗口）——**相对口径** |
| **gated** | 过闸（`gates.apply_entry_gates`）的全部标的 |
| **picks** | gated **且** `composite_score >= score_floor`（生产默认 `0.80`）⇒ **候选池**（实盘还会按持仓上限取当日头部） |
| **截尾** | 窗口末端 `k` 行没有 `t+k` ⇒ `fwd_k` 为 `NaN`。**按 horizon 剔除，不补零、不前向填充** |

### 2.1 两个口径各管一件事（真机教训，硬约定）

近一年实测出现过：**绝对收益**在 10 日见顶后转负，而**超额**只在 40 日为正。
后者是**熊市相对防守**（基准跌得更多）；拿它当「信号在长周期有效」去**延长持有**是**错的处方**。
因此：

| 问题 | 口径 | 字段 |
|---|---|---|
| 跑赢基准吗（有没有技能） | **超额** | `meanExcess` |
| 拿在手里赚钱吗 | **绝对** | `meanReturn` |

**边缘类**结论（`signal_*` / `edge_*`）只读 `meanExcess`；**持有期类**结论（`hold_*`）只读 `meanReturn`。

### 2.2 收益单位（硬约定）

- 面板/曲线的收益一律是**小数**（`+0.05` = +5%）。
- `book_replay` 的成交 `gross_ret` / `net_ret` 是**百分数**（`+5.0` = +5%）；
  :data:`attribution.TRADE_RET_SCALE = 0.01` 在 `cost_drag` / `payoff_profile` /
  `concentration` 内部归一为小数，产物带 `"unit": "fraction"`。

## 3. 输入

| 输入 | 说明 |
|---|---|
| `feats` | `backtest.prepare_book_frame` 的输出（`code` / `trade_date` / `close` / `pct_chg` / `ret1` / `vol20` / `rev_chg` / `ma20` / `ma60`） |
| `benchmark` | `DataFrame(date|trade_date, close)` 或 `Series`（`DatetimeIndex → close`）。**不可用时** `basis="raw"`，报告显式标注 |
| 成交 `trades` | `book_replay` 的 `trades`（`gross_ret` / `net_ret` / `held_days` / `reason` / `asset_class` / `exit_date`） |

`benchmark` 对齐规则：以**行情日历**为轴 `reindex(...).ffill()`——基准缺日**前向填充**而非剔除，
以保证与个股前瞻收益用同一条日历。基准行**永不**进入选股宇宙。

## 4. 函数契约

### 4.1 `attach_forward_returns(feats, *, horizons)` → `DataFrame`

在全跨度帧上按 `code` 分组 `shift(-k)`，产出 `fwd_{k}` 列。**必须在全跨度调用**，否则窗口末端整段缺失。

### 4.2 `prepare_benchmark(bench, calendar)` → `Series | None`

`None` / 空 → `None`；帧缺 `date|trade_date` 或 `close` → `ValueError`。

### 4.3 `build_signal_panel(feats, *, benchmark, horizons, score_floor, gate_params, neutralize, weights, value_factor)` → `dict`

```jsonc
{
  "panel": "DataFrame[code, trade_date, close, composite_score, passesFloor, fwd_k…, (bench_fwd_k…, excess_k…)]",
  "horizons": [1, 3, 5, 10, 20, 40],
  "basis": "excess" | "raw",
  "benchmarkAvailable": true,
  "nGated": 0, "nPicks": 0, "nDays": 0
}
```

打分**逐日**在当日截面上进行（与 `book_replay.screener_entry_provider` 同源）。空帧 → 全零结构，**不抛**。

### 4.4 `horizon_curve(panel, *, horizons, basis, which, min_sample)` → `list[dict]`

每项：`{horizon, n, adequate, mean, median, upRate, best, worst, meanReturn, meanExcess, basis, which}`。
**同一行同时携带 `meanReturn` 与 `meanExcess`**（§2.1 归属不同结论）。
某 horizon 的样本量 `< min_sample` ⇒ `adequate=false`（**不参与 `diagnose` 结论**）。

### 4.5 `score_curve(panel, *, horizon, buckets, basis, which, min_sample)` → `dict`

`{horizon, basis, which, n, adequate, spearman, direction, topMinusBottom, buckets[]}`；
`direction ∈ {increasing, decreasing, flat, unknown}`（阈值 `SPEARMAN_FLAT`）。

- Spearman = **秩的 Pearson 相关**（等价实现，避免引入 SciPy —— `research` 包只依赖 numpy/pandas）。
- 任一侧零方差 ⇒ `spearman=null`、`direction="flat"`。

### 4.6 `cost_drag(trades)` → `dict`

`{n, unit, meanGross, meanNet, meanCost, costShare, avgHoldDays, grossPositive, netPositive, signFlipped}`。
输入按 `TRADE_RET_SCALE` 归一（§2.2）。`costShare = meanCost / |meanGross|`（`meanGross = 0` 时 `null`）。
缺失该块的键 → `n=0` + 全 `null`。

### 4.7 `payoff_profile(trades)` → `dict`

`{n, unit, winRate, avgWin, avgLoss, payoffRatio, expectancy, best, worst}`。
`net_ret > 0` 记胜，`<= 0` 记负；`payoffRatio = avgWin / |avgLoss|`。

### 4.8 `concentration(trades, *, by, industry_map, value_field, value_scale)` → `dict`

`by ∈ {month, reason, assetClass, industry}`；
`reason` 按**规则名**分桶（取 `(` 之前的部分）——`stop_loss(-8.1%)` 与 `stop_loss(-9.5%)` 同桶，
否则一条退出规则会被碎成几十个桶；
`industry` 走行业表并以 `portfolio.norm_code` 归一（`600000.SH` → `600000`）。

返回 `{by, byZh, valueField, valueScale, n, groupCount, overallTotal, overallMean,
groups[], worst, best, maxLossShare, maxLossGroup}`，`groups[]` 每项
`{group, n, mean, median, total, winRate, lossShare}`，按 `total` **升序**。
`lossShare` = 该组亏损 / **全部亏损组的亏损质量之和**（无亏损组 ⇒ `null`）。

### 4.9 `diagnose(...)` → `dict`（**纯函数**）

输入全部为已算好的块，不碰 pandas / 引擎。参数多一个 `min_sample`（透传到集中度与 `notes`）。

```jsonc
{
  "verdict": "attributed" | "no_single_cause",
  "headline": "…",
  "basisSet": "picks" | "gated",
  "causes": [{"code": "…", "title": "…", "severity": "alert|warn|info",
              "severityZh": "…", "rank": 3, "impact": 0.0,
              "evidence": {}, "action": "…"}],
  "severityCounts": {"alert": 0, "warn": 0, "info": 0},
  "notes": [],
  "thresholds": {}
}
```

**排序键**：`严重度（alert > warn > info）→ rank（小者先，事前登记）→ |impact|`。
`impact` 的量纲在各原因之间不可比，故**只作三级键**；`rank` 由 :data:`_CAUSE_RANK` 固定。

`curve_picks` 无达标 horizon（`meanExcess` 与 `meanReturn` 双空）时**退用** `curve_gated`
（`basisSet="gated"` + `notes` 说明）；两者都无 ⇒ 只出一条 `no_single_cause` 并写 `notes`。

## 5. 事前登记的原因码与阈值

| `code` | 口径 | 触发条件 | 严重度 | 动作 |
|---|---|---|---|---|
| `signal_no_edge` | 超额 | 所有达标 horizon 的 `meanExcess <= 0` | `alert` | 信号需重做（方向/权重/换因子） |
| `no_absolute_edge` | 绝对 | 所有达标 horizon 的 `meanReturn <= 0` | `alert` | 任何持有期都亏 ⇒ 先解决绝对收益 |
| `hold_too_long` | 绝对 | 峰值 horizon < 最长达标 horizon、`meanReturn(峰值) > 0`、`meanReturn(最长) < 0` | `warn` | 缩短持有 / 收紧止盈 |
| `hold_too_short` | 绝对 | `meanReturn(最短) < 0`、峰值 **等于**最长达标 horizon、`meanReturn(峰值) > 0` | `warn` | 延长持有窗 |
| `edge_only_long_horizon` | 超额 | `meanExcess(ref) <= 0 < meanExcess(最长)` 且 `最长 > ref` | `warn` | **不要**据此延长持有（熊市相对防守）；先在实战窗内做出正超额 |
| `score_not_monotonic` | 评分 | `spearman <= -SPEARMAN_FLAT` | `alert` | 复核闸门方向与因子权重 |
| `score_weak` | 评分 | `\|spearman\| <= SPEARMAN_FLAT` | `warn` | 补强因子，而非继续调闸门 |
| `cost_erodes_edge` | 成本 | `meanGross > 0` 且 `meanNet <= 0` | `alert` | 降换手 / 抬高闸门 / 拉长持有 |
| `cost_erodes_edge` | 成本 | `meanGross > 0` 且 `costShare >= 0.30` | `warn` | 评估降低换手 |
| `payoff_unfavorable` | 赔率 | `winRate < 0.50` 且 `payoffRatio < 1.0` | `warn` | 收紧止损 / 让盈利单多跑 |
| `concentrated_loss` | 分组 | **组数 ≥ 2** 且 `n >= min_sample` 且 `lossShare >= 0.40` 且 `overallMean < 0` | `warn` | 定点排查该暴露，必要时加上限 |
| `no_single_cause` | — | 以上均未触发 | `info` | 组合改善（信号边缘 + 成本 + 赔率） |

> 单组（`groupCount < 2`）**永不**构成「集中」——真机教训：`assetClass=stock` 恒占 100%，
> 这类退化分组必须显式跳过。

**`rank`（同严重度下的决定性顺序）**：
`signal_no_edge` 1 → `no_absolute_edge` 2 → `hold_too_long` 3 → `hold_too_short` 4 →
`edge_only_long_horizon` 5 → `score_not_monotonic` 6 → `cost_erodes_edge` 7 →
`payoff_unfavorable` 8 → `score_weak` 9 → `concentrated_loss` 10 → `no_single_cause` 99。

| 常量 | 值 |
|---|---|
| `MIN_MEANINGFUL_SAMPLE` | 20 |
| `TRADE_RET_SCALE` | 0.01 |
| `COST_SHARE_WARN` | 0.30 |
| `LOSS_CONCENTRATION_WARN` | 0.40 |
| `SPEARMAN_FLAT` | 0.05 |
| `PAYOFF_RATIO_WARN` | 1.0 |
| `WINRATE_WARN` | 0.50 |
| `DEFAULT_HORIZONS` | `(1, 3, 5, 10, 20, 40)` |
| `DEFAULT_SCORE_FLOOR` | 0.80 |
| `DEFAULT_SCORE_BUCKETS` | 5 |
| `DEFAULT_REFERENCE_HORIZON` | 5 |

## 6. 报告载荷（`attribution.json`）

必含：`ok` · `generatedAt` · `environment` · `liveTradingEnabled`（恒 `false`）· `db` · `universe` ·
`start` · `end` · `nDays` · `benchmarkSymbol` · `benchmarkAvailable` · `scoreFloor` ·
`scoreFloorReplay` · `horizons` · `basis` · `nGated` · `nPicks` · `referenceHorizon` ·
`curvePicks` · `curveGated` · `score` · `cost` · `payoff` · `concentrations` · `diagnosis` ·
`metricNote` · `attributionNote` · `disclaimer`。

`data/strategy/attribution.{json,md,html}`；`.md` 分六节（信号有效性曲线 / 评分单调性 / 成本拖累 /
赔率结构 / 亏损集中度 / 根因裁决），曲线表**同时列出平均超额与平均收益**；
`.html` 走 `report_html` 单点（ADR 0071）。

## 7. CLI

```
stock-platform-attribution [--db PATH] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--years N]
                           [--universe stock|etf|all] [--benchmark CODE] [--no-benchmark]
                           [--score-floor F] [--horizons 1,3,5,10,20,40] [--buckets N]
                           [--reference-horizon K] [--min-sample N]
                           [--initial-capital F] [--max-positions N] [--no-replay]
                           [--out-dir DIR] [--json] [--json-out P] [--out P] [--html-out P] [--no-write]
```

退出码：`0` 出报告 · `2` 无 bars / 无可评估面板 · `1` 参数/配置错误（`SystemExit`）。
基准默认 `STOCK_PLATFORM_BENCHMARK_SYMBOL`（否则 `000905`）**自动补 `.SZ` 后缀**（引擎库口径）；
基准不在 `daily_price` 中 ⇒ 打 `[warn]` 并退用裸收益（`--no-benchmark` 同效）。

## 8. 硬约束

- **只读 / 零网络**：`market.db` 以 `mode=ro` 打开，只 `SELECT`；**不写库**。
- **不写交易面**：不写 brief / picks / holdings；唯一产物在平台自有 `data/strategy/`。
- **fail-closed**：缺件标 `None` / `n=0`，**不编造**数字；样本不足**不给结论**。
- **fail-open 的装饰**：HTML 渲染失败不影响 md/json 落盘。
- **零新依赖**：仅 numpy / pandas（Spearman 自实现，见 §4.5）。
- **无 API / 无面板**：决策前离线评估（见 ADR 0078 备选方案）。
