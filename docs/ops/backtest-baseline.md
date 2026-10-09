# 回测基线报告（B1）

> **状态**：done（2026-10-09）｜**目标 tag**：`v3.13.0`
> **引擎**：`packages/research/src/stock_platform_research/backtest.py`
> **数据**：`a-stock-engine/data_cache/market.db`（只读，3.14 GB）
> **命令**：`stock-platform-backtest --start 2020-01-01 --end 2026-09-08 --out curve.csv`
> **口径**：SIMULATE｜`liveTradingEnabled=false`｜非投资建议
> **性能补强（2026-10-09）**：加载器优化，全周期 **106 s → 65 s**，指标逐位不变（见 §5 #5）
> **指标补强 B2（2026-10-09，`v3.13.2`）**：指标单点化（`portfolio.py` 权威层）+ 成交额换手 / HHI 集中度，口径见 [`docs/contracts/portfolio-metrics.md`](../contracts/portfolio-metrics.md)
> **费用补强 B3（2026-10-09，`v3.13.3`）**：费用与摩擦单点化（`CostModel`）+ **新增滑点**（默认 0），口径见 [`docs/contracts/cost-model.md`](../contracts/cost-model.md)、敏感性见 §3.1
> **资产类型补强 B4（2026-10-09，`v3.13.4`）**：`asset_class` 单点定义 + `universe`（`stock`/`etf`/`all`）+ 分资产 `by_asset` 报告；口径见 [`docs/contracts/asset-classes.md`](../contracts/asset-classes.md)、实测见 §3.2
> **交易规则补强 B5（2026-10-09，`v3.13.5`）**：退出 / 冷静期 / 持仓偏差 / 涨跌停**单点定义**（`rules.py`），回测与在线路径**双路调用同一函数**；口径见 [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md)、冷静期对照见 §3.3

---

## 1. 为什么要做 B1

平台原有回测内核 `pit.run_pit_long_only` 是**每日全换仓**的骨架：每个交易日重新选 top-N、等权持有 **1 天**。
它能回答"信号排序有没有信息量"，但**回答不了"一个真实账户长什么样"**——没有持仓周期、没有费用、没有持仓状态。
`portfolio.py` 也只有 3 个指标（回撤 / 换手 / 终值）。

B1 在**同一套内核**（`lvrev.score_lvrev` + `gates.apply_entry_gates`）之上补齐了组合层与指标层。

---

## 2. 引擎能力（新增 `backtest.py`）

| 能力 | 说明 |
|---|---|
| 持仓状态 | 每仓 entry price / shares / running peak |
| 持有期 | `min_hold`（默认 45 天）约束主动卖出；`max_hold_days` 安全上限 |
| 风控 | 硬止损 `-8%`、目标止盈 `+5%`、趋势破位（MA20≤MA60）、移动止损（自高点 -6%，且曾盈利≥2%）——B5 起由 `rules.ExitPolicy` + `rules.evaluate_exit` **单点定义** |
| 仓位 | 最大并发 `15` 仓、等权、100 股取整 |
| 现实性约束 | **跌停卖不掉→顺延**；**涨停买不进→跳过**；停牌持有顺延 —— B5 起判定由 `rules.is_limit_down` / `rules.is_limit_up` **单点定义** |
| 冷静期 | 出场后 N 会话禁止同码再入场（`cooldown_days`，**默认 0 = 关闭**，B5 新增） |
| 持仓偏差 | 权重相对偏离超带即 `trim` / `add`（`drift_band`，**默认 None = 关闭**，B5 新增；仅在线复核使用） |
| 费用 | 佣金 **万0.854 双边**（免5）；印花税 **万5 仅卖出**；**ETF 免印花税**——B3 起由 `portfolio.CostModel` **单点定义**，与 `local_backtest.py` 逐值对齐 |
| 滑点 | **单边可配置**（`slippage_bps`，默认 `0` = 零摩擦）；**仅改成交价、不改信号**（B3 新增） |
| 指标 | 年化 / 最大回撤 / 夏普 / 索提诺 / Calmar / 换手 / 胜率 / 平均持有 |

**参数默认值逐一对齐 `a-stock-engine` v4.31**：`MAX_PICKS_PER_DAY=8`、`MAX_POSITIONS=15`、`MIN_HOLD=45`、`STOP_LOSS=8.0`、`TARGET_BASE=5.0`、`TRAIL_STOP_PCT=6.0`、`REVERSAL_Q=0.30`、`MIN_PICK_SCORE=0.80`。

---

## 3. 基线结果（2020-01-02 ～ 2026-09-03）

**样本**：1618 个交易日 / 6964 只标的（全市场，已排除北交所）/ 初始 50,000 元

| 指标 | 值 |
|---|---|
| 总收益 | **+90.24%** |
| 终值 | 95,117.64 |
| 年化（CAGR） | **+10.53%** |
| 最大回撤 | **-17.14%** |
| 夏普 | **0.751** |
| 索提诺 | 0.722 |
| Calmar | 0.615 |
| 交易笔数 | 630 |
| 胜率 | **46.2%** |
| 平均持有 | 35.4 天 |
| 年换手（笔/年） | 98.1 |
| 成交额换手（倍/年） | **11.28** |
| 平均持仓集中度（HHI） | 0.0865 |
| 平均最大单票权重 | 10.17% |
| 平均仓位（invested ratio） | 80.0% |
| 平均持仓数 / 最大并发 | 13.6 / 15 |

### 分年收益

| 年 | 收益 |
|---|---|
| 2020 | +29.35% |
| 2021 | +28.06% |
| 2022 | **-10.40%** |
| 2023 | +0.64% |
| 2024 | +14.77% |
| 2025 | +14.05% |
| 2026（至 9/3） | **-7.42%** |

### 卖出原因分布（630 笔）

| 原因 | 笔数 | 占比 |
|---|---|---|
| 止损 | 251 | 39.8% |
| 目标止盈 | 222 | 35.2% |
| 趋势破位 | 120 | 19.0% |
| 移动止损 | 34 | 5.4% |
| 持仓上限 | 3 | 0.5% |

单笔净收益区间 **-15.21% ～ +82.03%**；无 >100% 或无 <-20% 的离群值。

### 3.1 成本敏感性（B3，2026-10-09）

默认档 = 含佣金 + 印花税、**无滑点**。四档同区间同参数对比（1618 日 / 6964 码）：

| 档 | 总收益 | CAGR | 最大回撤 | 夏普 | 笔数 | 终值 | Δ 终值 vs 默认 |
|---|---|---|---|---|---|---|---|
| 零成本（`--zero-cost`） | +92.69% | 10.76% | -17.92% | 0.7605 | 634 | 96,344.57 | **+1,226.93** |
| **默认（含费）** | **+90.24%** | **10.53%** | **-17.14%** | **0.7511** | **630** | **95,117.64** | — |
| 滑点 5 bps | +89.41% | 10.46% | -17.55% | 0.7454 | 632 | 94,706.19 | −411.45 |
| 滑点 10 bps | +87.35% | 10.27% | -17.60% | 0.7374 | 634 | 93,674.91 | **−1,442.73** |

- **费率拖累** = 零成本 − 默认 = **1,226.93 元**（≈ 初始 5 万的 2.45% 收益）。
- **滑点拖累** 10 bps 单边 ≈ **1,442.73 元**（≈ 2.89% 收益），与费率**同级** —— 摩擦不可忽略。
- 笔数 630→634 的漂移源于滑点改变成交价 → 触及止损/目标的时点变化。
- **报告任何数字必须声明费用档**（费率 + 滑点），见 [`docs/contracts/cost-model.md`](../contracts/cost-model.md) §7。

复现：`stock-platform-backtest --start 2020-01-01 --end 2026-09-08 --slippage-bps 10`（或 `--zero-cost`）。

### 3.2 资产类型 / 宇宙对照（B4，2026-10-09）

`universe` 三档，同区间同参数（1618 日；`stock` 档为基线默认）：

| `universe` | 总收益 | CAGR | 最大回撤 | 夏普 | 笔数 | 胜率 | 终值 | 耗时 | 分资产笔数 |
|---|---|---|---|---|---|---|---|---|---|
| **`stock`（默认）** | **+90.24%** | **10.53%** | **-17.14%** | **0.7511** | **630** | **46.19%** | **95,117.64** | 47.6 s | stock 630 |
| `all`（股票+ETF 混池） | +102.58% | 11.60% | -20.61% | 0.8547 | 609 | 45.98% | 101,288.29 | 48.1 s | **stock 609 · etf 0** |
| `etf`（仅 ETF） | **-16.31%** | -2.83% | -42.05% | -0.0604 | 9 | 0.0% | 41,844.97 | 20.0 s | etf 9 |
| `all` + 关闭打分门槛※ | +9.79% | 1.51% | — | — | 752 | 35.8% | — | 47.1 s | stock 644 · **etf 103** · fund 5 |

※「机制演示档」：`min_pick_score=0.0`，**非默认配置**，只用于证实混池与免税路径确实通。

**三条必须写进结论的发现**（口径见 [`docs/contracts/asset-classes.md`](../contracts/asset-classes.md) §6）：

1. **默认门槛下混池不会买 ETF。** 全周期 1428 个 ETF 码中日均 **15.3** 只可过闸门（股票 156.3 只），但 ETF 的 lvrev 合成分中位上限仅 **0.50**（股票 **0.86**）→ `min_pick_score=0.80` 把 ETF 全部挡在门外。**混池 ≠ ETF 配置。**
2. **混池数字不可横比股票基线。** 入场闸门的 `vol20` 中位 / `rev_chg` 分位取自当日入选帧，加入 ETF 会改变分位 → 股票入选集合变化。`all` 的 +102.58% 是**宇宙变化**，不是策略改进。
3. **ETF 名册含脏数据。** `--universe etf` 出现 -99.9992% 级别的极端值，avg_net_ret 有 +56% / -39% 离群 → 原始 ETF 池需先做代码规范 + 流动性筛（属 X 域，B4 不实现）。

**免税路径实测**：对混池中的真实 ETF 成交通道验算 —— `515250` 卖出成本率 = `8.54e-05`（**仅佣金**），股票参照 `600519.SH` 卖出 = `5.854e-04`（佣金 + 万5 印花税）。豁免按 `is_etf` 前缀表生效，与分类同源。

复现：`stock-platform-backtest --start 2020-01-01 --end 2026-09-08 --universe all`（或 `etf`）。

### 3.3 退出策略与冷静期对照（B5，2026-10-09）

`exit_policy` 默认档与 B1–B4 完全同值（`stop_loss=8` / `take_profit=0` / `target_base=5` / `trail_stop_pct=6` / `trail_min_peak_ret=2` / `min_hold=45` / `max_hold_days=60`）。新增的 `cooldown_days` 默认 `0`（关闭）；本档仅演示口径：

| 指标 | `cooldown_days=0`（默认） | `cooldown_days=10` | Δ |
|---|---|---|---|
| 总收益 | **+90.24%**（0.902353） | +89.83%（0.898259） | −0.41 pp |
| CAGR | **10.53%** | 10.50% | −0.04 pp |
| 最大回撤 | **-17.14%** | -17.14% | ~0 |
| 夏普 | **0.7511** | 0.7508 | −0.0003 |
| 索提诺 / Calmar | 0.7223 / 0.6145 | 0.7177 / 0.6124 | −0.0046 / −0.0021 |
| 笔数 | **630** | 631 | +1 |
| 胜率 | **46.19%** | 45.96% | −0.23 pp |
| 终值 | **95,117.64** | 94,912.95 | **−204.69** |
| 成交额换手（倍/年） | 11.28 | 11.29 | +0.01 |
| 平均 HHI | 0.086483 | 0.086447 | −0.00004 |

- **默认档逐位不变** ⇒ `evaluate_exit` 的抽取代换是**纯重构**，不是策略变更。
- **冷静期是风险约束，不是收益工具**：低频组合（1618 会话 / 630 笔）里同码快速再入场本就罕见，故影响仅 −0.22%；笔数 +1 属**级联效应**（某日被阻断的再入场让位给另一标的，后续链路偏移）。
- **报告任何数字必须声明 `exit_policy` / `cooldown_days` / `drift_band`**，见 [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md) §9。

复现：`stock-platform-backtest --start 2020-01-01 --end 2026-09-08`（默认档）；冷静期档需脚本调 `run_portfolio_backtest(..., cooldown_days=10)`（CLI 暂未暴露该参数）。

### 3.4 在线持仓复核（B5）

`stock-platform-position-review --holdings book.json [--db market.db --asof YYYY-MM-DD]` —— 对当前账本逐只给出 `hold` / `exit` / `trim` / `add`，**调用与回测相同的规则函数**。富化模式经 `compute_features` 取同源复权价与 `ma20`/`ma60`，`held_days` 由 `entry_date` 在全量会话序列定位。口径见 [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md) §6。

### 3.5 可视化端点与耗时（B6，2026-10-09）

Workbench `#backtest` 面板「组合净值曲线」区块 = `POST /api/research/backtest/portfolio`，走**与本节 CLI 相同的代码路径**（`load_engine_bars` → `filter_universe` → `run_portfolio_backtest`），只读 `STOCK_PLATFORM_ENGINE_MARKET_DB`。返回的 `daily[]` 同时驱动**净值曲线、回撤带与逐日表**（索引即交易日），因此 `metrics.max_drawdown` 与图上最深回撤**逐位相等**（[`portfolio-metrics.md`](../contracts/portfolio-metrics.md) §2.1）。

实测耗时（`market.db` 3.14 GB / 877 万行，只读）：

| 窗口 | 交易日 | 笔数 | 耗时 | 结果 |
|---|---|---|---|---|
| 全周期 2020-01-02～2026-09-03 | 1618 | 630 | 加载 13.4 s + 回测 49.3 s ≈ **63 s** | `total_return` +90.24% · `max_drawdown` −17.14% |
| **1 年** 2025-09-01～2026-09-03 | **245** | **85** | **18.5 s**（HTTP 200） | `total_return` −7.00% · `max_drawdown` **−0.193254** == `min(daily[].drawdown)` |

> **耗时瓶颈是加载 + 全帧特征**（与窗口长度弱相关，~13 s + ~5 s 固定），回测循环才随窗口增长。故面板默认填**近 1 年**，多年窗口需数十秒；长跑请勿在 120 s 工具超时内前台等待。

---

## 4. 与 `a-stock-engine` 的一致性对照

| 项目 | 本基线（平台） | 引擎 `local_backtest.py` |
|---|---|---|
| 打分内核 | `lvrev` W_DEFAULT（vol 0.5 / rev 0.5） | 同（v4.29 canonical） |
| 闸门 | `apply_entry_gates` | 同源 |
| 费用 | 万0.854 / 万5 / ETF 免 | 同 |
| 退出 / 冷静期 / 涨跌停规则 | `rules.py` **单点定义**，回测与在线复核**双路共用** | 内联在 `local_backtest.py`（无在线路径、无冷静期） |
| 持仓偏差 | `DriftPolicy`（默认关闭，仅在线复核） | 无 |
| 资产类型 | `universe` `stock`/`etf`/`all`（默认 `stock` = 排除基金） | **整体排除基金**（无 `etf`/`all` 档） |
| 持有期 | min_hold 45 | MIN_HOLD=45 |
| 宇宙 | 全市场 6964 码（排除 BSE） | 全市场（含 survivors/ST 过滤） |
| 区间 | 2020-01 ～ 2026-09（6.7 年） | 样本内全期 |
| **总收益** | **+90.24%** | **+23.05%**（lvrev mh45 样本内） |
| 夏普 | 0.751 | 0.34 |
| 最大回撤 | -17.14% | 11.2% |

**对照锚点（引自 `empirical/BASELINE.md` 与 `walk_forward_oos_result.json`）**：

- 引擎生产基线 = **path-C 行业轮动 tilt，OOS 几何 +53.24%**
- 引擎 walk-forward OOS calibration：+57.47% / CAGR 7.66% / MDD 19.72% / 夏普 0.52 / 胜率 34.4% / 平均持有 **5.1 天**
- **`BASELINE.md` §5 方法论铁律**：比较回测必须"同策略 + 同样本 + 同权重 + 同持有期"，跨口径横比是误读。

### 差异解释（逐条，不对齐处不掩盖）

1. **持有期口径不同（主因）**：本基线 `min_hold=45` → 平均持有 35.4 天、年换手 98 笔；引擎 OOS 台平均持有 **5.1 天**、6.2 年 10280 笔（≈1658 笔/年）。低换手 = 少成本 + 让盈利跑久，两者收益不可直接比。
2. **区间不同**：本基线 2020-01 起；引擎 calibration 为 6.2 年（约 2020-05 起）。
3. **L0 市场闸门**：引擎有宽基 MA200 + 估值分位的熊市闸门，本基线未启用（`regime=None`）→ 未做系统性回撤压制。
4. **ST / 生存者偏差**：引擎有 ST 黑名单与 `_compute_survivors`（排除上市<1 年新股）；本基线仅有 BSE 与基金前缀过滤。
5. **复权处理（本基线更干净）**：引擎用未复权 `close` 计算盈亏，**除权日会产生假亏损**；本基线用 `pct_chg` 重建复权价。

> **结论**：方向一致（低波反转 long-only、正收益、夏普 0.3–0.75 量级），**差异全部可归因于口径**。不宣称"复现引擎数字"。

---

## 5. 过程中发现并修复的数据 / 性能问题

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| 1 | **`close` 未复权** | `600551.SH` 单日 close 跳变 **-32.6%**，而同日 `pct_chg` 仅 -10%（涨跌停内）→ 该笔被记为 -36.24% 止损 | `compute_features` 用 `pct_chg` 重建复权价贯穿特征与盈亏；修复后极端值归零 |
| 2 | **`pct_chg` 标度混用** | 主流记录为小数（`0.1006` = 10.06%），异常记录为百分数（`99.SZ` = `-1.37`） | 按中位数量级自动判标度；`|pct|` 截断 ±60% |
| 3 | **闸门 `iterrows` 过慢** | 全市场 1621 天 × ~5400 码 ≈ **880 万次** `iterrows`，全周期回测 >120 s 被命令超时 kill | `apply_entry_gates` **向量化**（逐行循环每个分支都是"拒绝"，等价于"任一条件命中即拒绝"）；全周期回测 **200 s → 106 s** |
| 4 | **脏 code** | 6974 个 code 中 **1520 个**非标准（`159001`、`99.SZ`、`1.SZ`） | 基金/ETF 前缀（1/5）过滤；BSE（`.BJ` / 4/8 前缀）过滤 |
| 5 | **加载器 `WHERE date BETWEEN` 反而更慢** | 同一全周期窗口实测：`WHERE` + `ORDER BY code,date` **54.9 s**；`ORDER BY date`（走索引）50.6 s；不排序 + pandas 排序 52.8 s；**全表流式读 + 内存过滤仅 12.5 s** | `load_engine_bars` 改为**全表 `SELECT` + 内存内过滤/排序**（表只有 `idx_dp_date`，投影列迫使回表，索引帮不上忙）。全周期回测 **106 s → 65 s**（load 11.5 s + 回测 48.6 s），指标逐位不变；语义由 `tests/test_backtest_cli.py` 锁定 |

**向量化等价性**由 `packages/research/tests/test_gates.py` 用原逐行实现作为 oracle 证明（12 组随机数据 + 缺列场景，逐一比对）。

---

## 6. 已知限制（未做，不掩盖）

- **成交价基准 = 当日收盘价**：`market.db` 无 open/high/low，与引擎 `get_price_on_date` 同口径；**非 T+1 开盘成交**。B3 起可经 `slippage_bps` 施加单边滑点（默认 0）。
- **未启用 L0 熊市闸门**：需要宽基指数序列 + 估值分位，`regime` 参数已预留（调用方可注入）。
- **无 ST / 退市黑名单**：`fundamentals.name` 未接入。
- **无生存者偏差校正**：未按"上市满 1 年"过滤。
- **ETF 名册未清洗**（B4 起可选入宇宙，但默认不选）：`market.db` 的 1/5 前缀池含 `151.SZ` 等非标准 / 流动性枯竭条目，`--universe etf` 会出现极端离群；作为可交易宇宙前须先做代码规范 + 流动性筛（X 域议题）。
- **涨跌停判定实际极少触发**（B5 起显式声明）：判据用 `pct_chg`，而该列**标度混用**（多数行是小数 `0.10`，少数是百分点 `10.0`）；阈值是百分点，故只有百分点行可能命中。属**既有 B1 行为**，B5 刻意不改（改则基线移动，属策略变更）；详见 [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md) §7。
- **ETF 涨跌停档位未接入**：`limit_pct` 只提供股票三档，ETF 按主板 10% 处理；ETF 无涨跌停这一假设尚未声明（后续项）。
- **无 T+1 开盘成交**：虽然回测循环顺序（出场复核 → 建仓）已等价 T+1，但成交仍在**当日收盘价**，不是次日开盘。
- **单进程 Python 循环**：1618 天 **65 s**（加载 11.5 s + 回测 48.6 s，2026-10-09 优化后）；扩到分钟级或大批量参数扫描仍需再优化或拆批。

---

## 7. 复现

```powershell
cd D:\workspace\stock_trading\stock-platform
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:/workspace/stock_trading/a-stock-engine/data_cache/market.db"

# 全周期基线
.\.venv\Scripts\stock-platform-backtest.exe --start 2020-01-01 --end 2026-09-08 --out curve.csv

# 测试（引擎 + 闸门等价性）
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
.\.venv\Scripts\python.exe -m pytest packages/research/tests/test_backtest.py packages/research/tests/test_gates.py -q
```

---

## 8. 下一步

- ~~**B2 组合指标补全**~~：**done（`v3.13.2`，2026-10-09）** —— 指标单点化（`portfolio.py` 权威 + `backtest.py` re-export）+ 成交额换手 / HHI 集中度 / 暴露；口径见 [`docs/contracts/portfolio-metrics.md`](../contracts/portfolio-metrics.md)
- ~~**B3 费用与摩擦模型对齐**~~：**done（`v3.13.3`，2026-10-09）** —— `CostModel` 单点定义 + **新增滑点** + 修买入侧计费不对称 + CLI 四参数（`--commission-rate` / `--stamp-sell-rate` / `--slippage-bps` / `--zero-cost`）；与 `local_backtest.py` 跨线互测；口径与敏感性见 [`docs/contracts/cost-model.md`](../contracts/cost-model.md) 与 §3.1
- ~~**B4 ETF 支持**~~：**done（`v3.13.4`，2026-10-09）** —— `asset_class` 单点定义 + `universe`（`stock`/`etf`/`all`）+ CLI `--universe` + 分资产 `by_asset` 报告 + ETF 卖免印花税贯通；跨线互测前缀表；口径见 [`docs/contracts/asset-classes.md`](../contracts/asset-classes.md)，实测见 §3.2
- ~~**B5 回测↔在线规则统一层**~~：**done（`v3.13.5`，2026-10-09）** —— `rules.py` 单点定义（退出 / 冷静期 / 持仓偏差 / 涨跌停）+ 在线路径 `position_review` / CLI；回测委派全部交易判断；单点定义与差分一致断言齐备；口径见 [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md)，冷静期对照见 §3.3
- **B6 可视化**：`#backtest` 面板净值曲线 + 回撤带 + 逐日表联动（仍 Jinja + static）
- **（B5 派生）涨跌停判据标度**：`pct_chg` 混用标度使涨跌停约束近乎失效 —— 需单独立项（建议并入 B7 或 X 域数据规范），修前须重定基线
