# 契约：资产类型与宇宙口径

> 状态：**Accepted（B4，2026-10-09）**
> 实现：`packages/research/src/stock_platform_research/portfolio.py`（`asset_class` / `is_etf` / `is_fund` / `_ETF_PREFIXES`，**单点定义**）
> 消费方：`backtest.run_portfolio_backtest`（`universe=`）、`backtest_cli`（`--universe`）、`CostModel`（印花税豁免）、`compute_metrics`（`by_asset`）
> 对齐基准：`a-stock-engine/local_backtest.py`（`_is_fund` / `_is_etf`）
> 上游铁律：[backtest-baseline.md](../ops/backtest-baseline.md) §4、[cost-model.md](cost-model.md) §7

本契约固化**资产类型判定与回测宇宙口径**。任何新增资产类型、改前缀表或改 `universe` 语义，都必须先改本文件，再改实现。

---

## 0. 为什么需要单点定义

印花税豁免（[cost-model.md](cost-model.md)）与「哪些标的能进回测」是同一件事的两面：**判定一旦分叉，就会出现"回测按 ETF 免印花税、选股却把它当股票"这类静默错误**。因此分类只在 `portfolio.asset_class` 定义一次，费用侧与宇宙侧都调它。

---

## 1. 三分类定义

```python
asset_class(code) → "etf" | "fund" | "stock"
```

| 类 | 判定 | 印花税 | 典型代码 |
|---|---|---|---|
| `etf` | 归一化后命中 `_ETF_PREFIXES`（30 项） | **免征** | `510300.SH`、`159915.SZ` |
| `fund` | 其余 `1xxxxx` / `5xxxxx`（未进前缀表：债券 / LOF / 其它场内基金） | 按股票征（**保守**） | `123456.SZ`、`110000.SH` |
| `stock` | 其余全部 | 卖出征万 5 | `600519.SH`、`300750.SZ` |

- **归一化**：`norm_code` 去点取前 6 位（`'600519.SH'` / `'600519'` → `'600519'`）。
- **判定顺序固定**：先 `is_etf` → 再 `is_fund` → 否则 `stock`。`fund` 是「非股票的兜底」，**不**向 `etf` 借语义。
- `"fund"` 类**不免**印花税是**故意的保守选择**：无法确证豁免的，一律按应税处理，宁可高估成本。

---

## 2. `universe` 三档语义

`run_portfolio_backtest(..., universe=...)` / CLI `--universe`：

| 档 | 入选 | 说明 |
|---|---|---|
| `stock`（**默认**） | `not is_fund` | 与引擎 `_compute_survivors` 一致（引擎整体排除基金），**即 B1/B2/B3 基线宇宙** |
| `etf` | `is_etf` | 仅场内 ETF / 场内基金（前缀表命中） |
| `all` | 全部（不做 1/5 前缀过滤） | 股票 + ETF 混池 |

**向后兼容**：旧参数 `exclude_funds` 仍可用，显式传入时**覆盖** `universe`（`True` → `stock`，`False` → `all`）。默认档 `universe="stock"` 与旧默认 `exclude_funds=True` **完全等价**（断言锁定：全周期逐位一致）。

非法档位立即 `ValueError`（fail-closed，不静默降级）。

---

## 3. 与印花税豁免的绑定

`CostModel.trade_cost` / `costs` 的卖出腿调用 `is_etf(code)`：命中前缀表 → 只收佣金；否则再加万 5 印花税。**同一张前缀表**同时驱动分类与豁免，因此二者不可能不一致（`test_asset_class.py::test_asset_class_is_consistent_with_prefix_tables` 锁定）。

---

## 4. 分资产报告（`by_asset`）

`compute_metrics(...)["by_asset"]` 按类拆交易日志：

```json
{
  "stock": {"n_trades": 644, "win_rate": 0.4255, "avg_net_ret": 1.9664, "turnover_notional": 4787604.08},
  "etf":   {"n_trades": 103, "win_rate": 0.0097, "avg_net_ret": 56.2997, "turnover_notional": 685378.15}
}
```

- 类来源：交易记录里的 `asset_class` 字段（回测引擎写入）；缺失时按 `code` 现算（单点定义）。
- **既无 `code` 也无 `asset_class` 的交易被跳过**，不塞进任何伪桶；无交易时 `by_asset = {}`（空输入同样是 `{}`，不编造）。

---

## 5. 与 `a-stock-engine` 的对齐与互测

| 项 | 平台 | 引擎 | 判定 |
|---|---|---|---|
| `is_fund` 前缀 | `("1", "5")` | `_is_fund` 同 | 一致 |
| `is_etf` 前缀表 | `_ETF_PREFIXES`（30 项） | `_is_etf` 同 30 项 | 一致 |
| 引擎是否有 `all` / `etf` 宇宙 | **有**（本里程碑新增） | **无**（引擎整体排除基金） | **平台先行** |
| 引擎是否有滑点 | 有（B3） | 无 | 平台先行 |

互测方式：`packages/research/tests/test_asset_class.py` **静态解析**引擎源码取前缀表，逐码比对分类；引擎文件缺失时**跳过**（CI / 他机不阻塞）。

---

## 6. 实测发现（全周期 2020-01-02～2026-09-08 / 1618 日 / 6964 码）

**默认档 `stock` 与 B3 基线逐位一致**：

`total_return 0.902353` · `cagr 0.105348` · `max_drawdown -0.171435` · `sharpe 0.7511` · `n_trades 630` · `win_rate 0.4619` · `final_equity 95117.64`

三条必须写进结论的事实：

1. **未受约束的 `all` 混池不会买 ETF。** 全周期 1428 个 ETF 码中，日均 **15.3** 只可过入场闸门（股票为 156.3 只），但 ETF 的 lvrev 合成分**中位上限仅 0.50**，股票为 **0.86**；默认门槛 `min_pick_score=0.80` 把 ETF **全部**挡在门外（ETF 达标天数占比 **15.9%**，但排序永远进不了 top-8）。→ **混池 ≠ ETF 配置**，ETF 需独立信号（属 S 域议题）。
2. **混池会经截面分位"污染"股票选择。** `apply_entry_gates` 的 `vol20` 中位与 `rev_chg` 分位取自**当日入选帧**；加入 ETF 后分位变化 → 股票入选集合改变 → `all` 档 +102.58% 与 `stock` 档 +90.24% **不可直接横比**（不是策略改进，是宇宙变化）。
3. **原始 ETF 池含脏数据。** 1428 个"ETF"码里含 `151.SZ`、`159001` 等非标准/流动性枯竭条目；`--universe etf` 全周期收益 **-99.9992%**，avg_net_ret 出现 +56% 与 -39% 的极端离群 —— 说明 ETF 名册**必须先做代码规范 + 流动性筛**，才能作为回测宇宙（属 X 域议题，本里程碑不实现）。

> 结论：B4 交付的是**能力与口径**（可选宇宙 + 免税贯通 + 分资产报告），**不是**一个"ETF 策略"。混池数字**不得**作为 ETF 配置依据。

---

## 7. 不可横比铁律（扩展 cost-model §7）

> **比较任何两个回测，除策略 / 样本 / 权重 / 持有期 / 费用档外，还必须对齐 `universe`。**

违反示例：把 `stock` 档 +90.24% 与 `all` 档 +102.58% 并列而不声明宇宙 —— 会被误读为"加入 ETF 提升了收益"，实际只是把 ETF 塞进了截面分位，改变了股票入选。

因此报告任何数字时**必须**同时给出：区间 / **宇宙（`universe`）** / 持有期（或换手）/ 费用档 / 是否启用 L0。

---

## 8. 相关

- 费用与摩擦口径：[cost-model.md](cost-model.md)
- 指标口径：[portfolio-metrics.md](portfolio-metrics.md)
- 回测基线与分资产实测表：[backtest-baseline.md](../ops/backtest-baseline.md)
- 策略与涨跌停口径：[market-strategy.md](market-strategy.md)
- 路线图（B4 / B5 条目）：[trading-system-roadmap.md](../plans/trading-system-roadmap.md)
