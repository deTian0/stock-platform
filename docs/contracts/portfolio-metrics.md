# 契约：组合绩效指标口径

> 状态：**Accepted（B2，2026-10-09）**
> 实现：`packages/research/src/stock_platform_research/portfolio.py`（**单点定义**）
> 消费方：`backtest.run_portfolio_backtest`（组合回测）、`portfolio_metrics` / `run_portfolio_pit`（PIT 薄包装）
> 上游铁律：[backtest-baseline.md](../ops/backtest-baseline.md) §4 —— 「同策略 + 同样本 + 同权重 + 同持有期」才可横比

本契约固化**指标口径**。任何新增指标或改口径都必须先改本文件，再改实现。

---

## 0. 为什么需要单点定义

`B5` 要求「回测与在线规则共用同一实现」。绩效指标是这条链的第一节：
若回测、日报、实盘对账各算一套夏普，三者永远对不上。因此 `compute_metrics`
只在 `portfolio.py` 定义一次，`backtest.py` 通过顶部 `from .portfolio import
compute_metrics` **re-export**（旧调用点 `from .backtest import compute_metrics`
保持可用，且与 `portfolio.compute_metrics` 是**同一对象**）。

---

## 1. 通用约定（所有指标共用）

| 约定 | 取值 | 说明 |
|---|---|---|
| 收益表述 | **小数** | `0.1024` = +10.24%；不混用百分数 |
| 年化基数 | **252** | 交易日/年（`TRADING_DAYS_PER_YEAR`） |
| 无风险利率 | **0** | 夏普 / 索提诺的 `rf`；不引入国债收益率曲线 |
| 最大回撤符号 | **≤ 0** | 峰谷跌落的负小数 |
| 空输入 | **全零 / `None`** | `n_days=0`；**绝不编造**指标值 |
| 环境 | **SIMULATE** | `liveTradingEnabled=false`；非投资建议 |

---

## 2. 指标定义

| 字段 | 定义 | 备注 |
|---|---|---|
| `n_days` | 净值曲线点数 | = 交易日数（有 bar 的日） |
| `total_return` | `final / initial − 1` | 分数字 |
| `cagr` | `(final/initial)^(1/years) − 1`，`years = n_days/252` | 几何年化；`final ≤ 0` 时置 `−1` |
| `max_drawdown` | 峰到谷最大回撤 | 逐点维护 running peak |
| `sharpe` | `mean(日收益)/std(日收益) × √252` | `std=0` → `0` |
| `sortino` | `mean(日收益)/下行标准差 × √252` | 下行 = **负日收益**，目标收益 0 |
| `calmar` | `cagr / |max_drawdown|` | 无回撤 → `0` |
| `n_trades` | 已平仓笔数 | 组合引擎为完整 round-trip |
| `win_rate` | `净收益>0 的笔数 / n_trades` | 按 `net_ret`（扣费后） |
| `avg_hold_days` | 平均持有天数 | `held_days` 均值 |
| `final_equity` | 期末权益 | 货币单位 |

> **`total_return` / `cagr` / `max_drawdown` 为分数**；汇率无关，不涉及跨币种。

---

## 3. 换手率：**双口径**（都要报，不可互替）

| 字段 | 公式 | 口径 | 何时为 `None` |
|---|---|---|---|
| `turnover_per_year` | `n_trades / years` | **笔数/年**（廉价代理） | 从不为 `None`（无成交→`0`） |
| `turnover_notional_per_year` | `Σ(entry_value+exit_value) / mean(equity) / years` | **成交额倍数/年**（真实口径） | trades 无 `entry_value`/`exit_value` |

**为什么两个都留**：`turnover_per_year` 是 v3.13.0 基线报告已发布的口径（98.1 笔/年），
为兼容不改值；`turnover_notional_per_year` 才是可与外部组合横比的成交额口径。
**禁止**拿笔数口径去和他人成交额口径比较。

组合引擎的 `trades` 每条带 `entry_value` / `exit_value`（成交额），故两条口径都可得；
PIT 薄包装（每日全换仓）不产 `entry_value`，其 `turnover_notional_per_year` 为 `None`。

---

## 4. 集中度与暴露

| 字段 | 定义 | 备注 |
|---|---|---|
| `avg_hhi` | 逐日持仓市值 **HHI** 的均值 | HHI = Σ(归一化权重²)，`1/n`–`1` |
| `avg_top_weight` | 逐日**最大单票权重**均值 | ≤ 1 |
| `avg_invested_ratio` | 逐日 `持仓市值/总权益` 均值 | 含现金；反映真实暴露 |
| `avg_positions` | 逐日持仓数均值 | |
| `max_positions` | 期间最大并发持仓数 | 整数 |

**HHI 口径**：`hhi(weights)` 先对入参**归一化**再平方求和，因此对原始市值与权重
**同值**（scale-free）。组合引擎按**当日持仓市值、剔除现金**归一化 —— 度量「持仓内分散度」；
现金占比由 `avg_invested_ratio` **单独**表达。二者组合给出完整图像。

极值：单票 = `1.0`；n 只等权 = `1/n`；空仓 = `0.0`。

**缺失即 `None`**：若净值曲线点不带 `hhi`/`top_weight`/`invested_ratio`/`n_positions`
（如未扩展的旧曲线），对应字段为 `None`，绝不填 `0` 冒充。

---

## 5. 不可横比铁律（承接 BASELINE §5）

> **比较任何两个回测，必须先对齐：策略 + 样本区间 + 权重方案 + 持有期。**

违反示例（真实踩过）：把本平台 `min_hold=45`（平均持有 35.4 天）的 +90.24%，
与 `a-stock-engine` OOS（平均持有 5.1 天）的 +53.24% 直接比 —— 持有期与换手差一个量级，
**数字不可比**（见 [backtest-baseline.md](../ops/backtest-baseline.md) §4 逐条归因）。

因此报告任何数字时**必须**同时给出：区间 / 宇宙 / 持有期（或换手）/ 费用口径 / 是否启用 L0 闸门。

---

## 6. 相关

- 实现与用法：[backtest-baseline.md](../ops/backtest-baseline.md)（B1 基线）
- 组合层来源：[ADR 0043](../architecture/0043-portfolio-paper-performance.md)
- 策略与涨跌停口径：[market-strategy.md](market-strategy.md)
- 路线图（B2 条目）：[trading-system-roadmap.md](../plans/trading-system-roadmap.md)
- 费用模型对齐（B3 待办）：佣金万0.854 免5 双边 / 印花税万5 仅卖出 / ETF 免
