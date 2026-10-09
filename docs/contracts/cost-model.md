# 契约：费用与摩擦模型口径

> 状态：**Accepted（B3，2026-10-09）**
> 实现：`packages/research/src/stock_platform_research/portfolio.py::CostModel`（**单点定义**）
> 消费方：`backtest.run_portfolio_backtest`（组合回测）、`backtest_cli`（命令行）
> 对齐基准：`a-stock-engine/local_backtest.py`（`COMMISSION_RATE` / `STAMP_SELL_RATE` / `_trade_cost` / `_is_etf`）
> 上游铁律：[backtest-baseline.md](../ops/backtest-baseline.md) §4 —— 报告任何数字都必须同时给出**费用口径**

本契约固化**交易费用与摩擦口径**。任何新增费用项或改口径都必须先改本文件，再改实现。

---

## 0. 为什么需要单点定义

`B5` 要求「回测与在线规则共用同一实现」。费用是这条链上最容易被两套代码悄悄分叉的部分：
回测按「佣金 + 印花税」算，实盘按券商实际流水算，两边差万分之一，长周期就是几个百分点。
因此费率与摩擦只在 `CostModel` 定义一次，`backtest.py` 通过顶部
`from .portfolio import CostModel` 使用（旧调用点 `backtest.trade_cost` 保持可用，且与
`portfolio.trade_cost` 是**同一对象**）。

---

## 1. 费率与开关

| 字段 | 默认值 | 单位/口径 | 说明 |
|---|---|---|---|
| `commission_rate` | `0.0000854` | 比例（**双边**） | 华宝证券 **万 0.854** |
| `stamp_sell_rate` | `0.0005` | 比例（**仅卖出**） | 印花税 **万 5**，**仅股票** |
| `slippage_bps` | `0.0` | 基点（**单边**，1 bp = 0.01%） | 默认 0 = 零摩擦基线 |
| `min_commission` | `0.0` | 货币（每笔） | `0` = **「免5」**（无 ¥5 最低门槛） |
| `etf_stamp_exempt` | `True` | 布尔 | ETF / 场内基金**免印花税** |

**「免5」的正确含义**：不是「5 元封顶」，而是**取消最低 5 元佣金门槛**，费用纯按比例计。
因此 `min_commission = 0.0`；该字段保留是为了将来换到「有 5 元最低」的券商时无需改结构
（见 §3）。

---

## 2. 两个 API：比率 vs 金额

| 方法 | 返回 | 用途 | 是否含 `min_commission` |
|---|---|---|---|
| `trade_cost(code, is_buy=)` | **比例** | 快速估算 / 向后兼容 | **不含**（比例无法表达货币下限） |
| `costs(notional, code, is_buy=)` | **货币金额** | 回测的现金收支（**权威口径**） | **含** |
| `fill_price(px, is_buy=)` | 成交价 | 滑点后的成交价 | — |

`min_commission == 0` 时二者等价：`costs == notional × trade_cost`（有断言测试锁定）。

模块级 `trade_cost(code, is_buy=, commission_rate=, stamp_sell_rate=)` 为 pre-B3 签名的
便利包装，委托给 `CostModel`，**返回比率**。

---

## 3. 成本构成（逐腿）

- **买入**：佣金 `max(名义 × commission_rate, min_commission)`；**无**印花税。
- **卖出**：佣金同上 ＋ 印花税 `名义 × stamp_sell_rate`（**仅股票**；ETF 免）。

```text
买入成本 = shares × fill_price(buy)                     # 名义
commission = max(名义 × commission_rate, min_commission)
卖出现金 = shares × fill_price(sell) − commission − 名义 × stamp_sell_rate
```

`min_commission = 5.0` 时的效果（仅作示例，**当前不使用**）：小额票 1,000 元买 → 佣金 `5.00`
（而非 `0.0854`）；大额票 100 万元买 → 佣金 `85.40`（比例生效）。

---

## 4. 滑点语义（**只改成交价，不改信号**）

> **`slippage_bps` 只作用于成交价：买入按 `px × (1+slip)` 成交，卖出按 `px × (1−slip)` 成交。**

**不作用于**：选股打分（`score_lvrev`）、入场闸门（`apply_entry_gates`）、L0 择时、
涨跌停判定、止损/目标/移动止损的**触发判定**（一律读**参考收盘价**）。

持仓的盈亏与止损**基线**使用**真实成交价**（含滑点）——因此滑点会通过「成本更高」这一
真实摩擦路径影响触发时点，这是**摩擦效应**，不是信号污染。

**默认 `0.0` 时**：`fill_price == 参考价`，回测与 B1 / B2 基线**逐位一致**（§6 已实测）。

---

## 5. 与 `a-stock-engine` 的对齐与互测

| 项 | 平台 | 引擎 | 判定 |
|---|---|---|---|
| 佣金 | `0.0000854` | `COMMISSION_RATE = 0.0000854` | 一致 |
| 印花税 | `0.0005` | `STAMP_SELL_RATE = 0.0005` | 一致 |
| ETF 前缀表 | `_ETF_PREFIXES`（30 项） | `_is_etf`（同 30 项） | 一致 |
| 免5 | `min_commission = 0` | 纯比例 | 一致 |
| 滑点 | `slippage_bps` | **无**（顺延为 B4+ 议题） | 平台先行 |

互测方式：`packages/research/tests/test_cost_model.py` **静态解析**引擎源码（正则取常量与
ETF 前缀），在 股票/ETF × 买/卖 四象限逐项比对；引擎文件缺失时**跳过**（CI / 他机不阻塞）。

---

## 6. 实测：零回归 + 成本敏感性（全周期 2020-01-02～2026-09-08 / 1618 日 / 6964 码）

**默认档（滑点 0）与 B2 基线逐位一致** —— 证明 B3 未改变既有数字：

`total_return 0.902353` · `cagr 0.105348` · `max_drawdown -0.171435` · `sharpe 0.7511` ·
`n_trades 630` · `win_rate 0.4619` · `final_equity 95117.64` · `turnover_notional_per_year 11.28` ·
`avg_hhi 0.086483`

| 档 | total_return | CAGR | MDD | Sharpe | 笔数 | final_equity | Δ 权益 vs 默认 |
|---|---|---|---|---|---|---|---|
| 零成本（`--zero-cost`） | 0.926891 | 10.76% | −17.92% | 0.7605 | 634 | 96 344.57 | **+1 226.93** |
| **默认（含佣金 + 印花税）** | **0.902353** | **10.53%** | **−17.14%** | **0.7511** | **630** | **95 117.64** | — |
| 滑点 5 bps | 0.894124 | 10.46% | −17.55% | 0.7454 | 632 | 94 706.19 | −411.45 |
| 滑点 10 bps | 0.873498 | 10.27% | −17.60% | 0.7374 | 634 | 93 674.91 | −1 442.73 |

**读法**：
- **费率拖累** = 零成本 − 默认 = **1 226.93 元**（≈ 初始 5 万的 2.45% 收益）。
- **滑点拖累**：10 bps 单边 ≈ **1 442.73 元**（≈ 2.89% 收益），已与费率同级 —— 摩擦不可忽略。
- 各档笔数 630→634 略有漂移：滑点改变成交价 → 触及止损/目标的时点变化。**报告数字必须声明档位**。

---

## 7. 不可横比铁律（承接 §5 与 BASELINE §4）

> **比较任何两个回测，除策略 / 样本 / 权重 / 持有期外，还必须对齐：费率 / 滑点 / 是否零成本。**

违反示例：把本契约 **默认档（含费无滑点）** 的 +90.24% 与 **零成本档** 的 +92.69% 并列，
却不声明费用口径 —— 会被误读为策略改进，实际只是关掉了摩擦。

因此报告任何数字时**必须**同时给出：区间 / 宇宙 / 持有期（或换手）/ **费用档（费率 + 滑点）** / 是否启用 L0。

---

## 8. 相关

- 指标口径：[portfolio-metrics.md](portfolio-metrics.md)
- 回测基线与敏感性表：[backtest-baseline.md](../ops/backtest-baseline.md)
- 策略与涨跌停口径：[market-strategy.md](market-strategy.md)
- 路线图（B3 / B4 / B5 条目）：[trading-system-roadmap.md](../plans/trading-system-roadmap.md)
- 里程碑方案：[b3-cost-model-milestone.md](../plans/b3-cost-model-milestone.md)
