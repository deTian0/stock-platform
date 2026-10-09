# 契约：交易规则（退出 / 冷静期 / 持仓偏差）

> 状态：**Accepted（B5，2026-10-09）**
> 实现：`packages/research/src/stock_platform_research/rules.py`（**单点定义**）
> 双路调用：`backtest.run_portfolio_backtest`（回测路径） · `position_review.review_positions` + `stock-platform-position-review`（在线路径）
> 上游依据：`V2-code-review-20260905` §检查重点 item 5 · [market-strategy.md](market-strategy.md)（涨跌停 / T+1 口径）
> 定位：`market-strategy.md` 是市场**抽象契约**（涨跌停/T+1/日历"存在且可配"），本文件是 CN 退出与交易限制判据的**具体实现层**。

本契约固化**退出条件、冷静期、持仓偏差、涨跌停判据**的口径。任何改动都必须先改本文件，再改 `rules.py`。

---

## 0. 为什么需要单点定义

`V2-code-review-20260905` 原文：

> 回测与在线规则是否一致；冷静期、退出条件和持仓偏差是否存在逻辑盲区。

`B5` 之前，整套退出判断（止损 / 止盈 / 目标 / 破位 / 移动止损 / 超时）**内联在 `run_portfolio_backtest` 里**——只有回测路径有。任何"在线持仓复核"都必须把它复刻一遍，两份实现必然分叉。这正是 `C` 域警告的**重复实现**风险，也是 `L` 域承接清单的第 5 条。

`rules.py` 是**唯一实现**，两条路径都调它。

---

## 1. 单点定义契约（可执行）

```python
backtest.evaluate_exit  is rules.evaluate_exit    # True
backtest.ExitPolicy     is rules.ExitPolicy       # True
backtest.CooldownPolicy is rules.CooldownPolicy   # True
backtest.limit_pct      is rules.limit_pct        # True
backtest.is_limit_up    is rules.is_limit_up      # True
backtest._Position      is rules.PositionState    # True（旧私有名是别名，不是第二个类）
```

由 `tests/test_rules.py::test_backtest_reexports_the_very_same_rule_objects` 锁定：**同一对象**，不是两份等价拷贝。

`rules.py` 只有纯函数 + frozen dataclass：无 pandas、无 I/O，两路调用传标量即可，天然可比。

---

## 2. 退出规则（顺序与字符串冻结）

`evaluate_exit(px, entry_price, target, peak, held_days, ma20, ma60, policy) -> ExitDecision | None`

| 序 | 规则 | 触发 | `reason` 字符串 | 受 `min_hold` 约束 |
|---|---|---|---|---|
| 1 | `stop_loss` | `ret% ≤ −stop_loss` | `stop_loss(-10.0%)` | **否**（保护性） |
| 2 | `take_profit` | `take_profit > 0` 且 `ret% ≥ take_profit` | `take_profit(+20.0%)` | **否**（保护性） |
| 3 | `target` | `px ≥ target` | `target(+6.0%)` | 是（相机性） |
| 4 | `trend_break` | `ma20 ≤ ma60`（二者均有效） | `trend_break(+1.0%)` | 是 |
| 5 | `trail_stop` | 持有 > `trail_min_held` 且 `peak_ret ≥ trail_min_peak_ret` 且自峰值回撤 `≥ trail_stop_pct` | `trail_stop(+0.0%)` | 是 |
| 6 | `max_hold` | `held_days ≥ max_hold_days` | `max_hold(61d)` | 是 |

- 命中即停（`if/elif` 链），返回第一个命中的规则；都不命中 → `None`（继续持有）。
- `ret%` / `peak_ret` 为**百分点**（`-8.0` = −8%），`held_days` 为**入场以来的会话数**（入场当日 = 0）。
- **`min_hold` 只拦相机性退出**：止损 / 止盈在任何持有期都生效（保护性优先）。
- **`peak` 必须已含当日收盘**——调用方先用 `advance_peak(peak, px)` 推进，再调 `evaluate_exit`（`peak` 只上不下）。
- `ma20` / `ma60` 缺失（`None` / `NaN`）视为**不可用**并跳过该分支，**绝不当作 0**（否则 `0 ≤ ma60` 会假触发破位）。
- `target` 只在 `ExitPolicy.target_price(entry)` 定义一次（`entry × (1 + target_base/100)`）。

---

## 3. 冷静期 `CooldownPolicy`

| 项 | 口径 |
|---|---|
| 语义 | 出场后 **N 个会话内禁止同码再入场** |
| 判定 | 出场在索引 `E`；`current_idx − E < cooldown_days` → 阻断 |
| 边界 | `cooldown_days = 1` 即阻断**同日**再入场（出场与入场都按收盘价，同一 `di`） |
| 默认 | `0` = **关闭** ⇒ 与 `B1`–`B4` 基线逐位一致 |
| 报告 | `remaining(last_exit_idx, current_idx)` 返回剩余阻断会话数；仅用于展示 |

回测侧：出场时记账 `last_exit_idx[code] = di`，入场候选时 `cooldown_policy.blocks(...)` 为真则跳过。默认档该分支永不命中。

---

## 4. 持仓偏差 `DriftPolicy`

| 项 | 口径 |
|---|---|
| 语义 | 单只权重相对目标偏离超过 `band` 即动作 |
| 判定 | `dev = (weight − target_weight) / target_weight`；`dev > band` → `trim`；`dev < −band` → `add`；否则 `hold` |
| 默认 | `band = None` = **关闭** ⇒ 不回测调仓，基线不动 |
| 缺失输入 | `weight` / `target_weight` 缺失或 `target_weight ≤ 0` → `hold` + `deviation = None`（**不编造指令**） |

---

## 5. 涨跌停与交易限制

```python
limit_pct(code, is_st=False)  # 主板 10% / 创业板·科创板（30·68）20% / ST 5%
is_limit_up(code, pct_chg)    # 涨停封板 → 买单无法成交
is_limit_down(code, pct_chg)  # 跌停封板 → 卖单无法成交
```

- 判定阈值 `= ±limit_pct × 100`（百分点），容差 `LIMIT_EPS = 0.01`——**与 B1 引擎逐字一致**（`tests/test_rules.py::test_limit_up_down_boundaries_match_the_b1_engine` 锁边界）。
- **判据价**：用引擎日收益 `pct_chg`（**不复权**口径），符合 [market-strategy.md](market-strategy.md) §CN「涨跌停判据价 = 不复权原始价」。回测**不**用前复权 `close` 判涨跌停。
- 行为：涨停 → 跳过该买入候选；跌停 → 出场顺延至下一会话（在线路径标 `deferred=true`）。
- **T+1**：回测循环顺序为 **①出场复核 → ②盯市 → ③建仓**，故 `di` 日建仓的持仓最早只能在 `di+1` 出场 → 等价 T+1（符合 `market-strategy` 硬约束 2）。

---

## 6. 在线路径（`position_review`）

`review_positions(holdings, exit_policy=..., cooldown_policy=..., drift_policy=..., current_idx=..., asof=...)`

| 输入键 | 说明 |
|---|---|
| `code` / `entry_price` / `price` | 必填（`price` 别名：`close` / `current_price` / `last` / `ref_close`） |
| `held_days` | 可选；缺失时按 0 处理**并标注** `held_days_unknown=true` |
| `peak` / `ma20` / `ma60` / `pct_chg` / `target` | 可选（`target` 缺省由 `ExitPolicy.target_price` 推出） |
| `weight` / `target_weight` | 仅持仓偏差规则需要 |
| `last_exit_idx` + `current_idx` | 仅冷静期规则需要 |

| 动作 | 含义 |
|---|---|
| `exit` | 有规则命中，`reason` 即 §2 的共享字符串 |
| `trim` / `add` / `hold` | 持仓偏差结果（`band` 关闭时恒为 `hold`） |
| `pending` | 缺 `entry_price` 或 `price` → **不表态**，绝不臆测 |

另有：`deferred`（跌停顺延）、`in_cooldown`（冷静期内）、`held_days_unknown`、`asset_class`。
**空持仓 fail-closed**（`ok=false`，不生成任何行）。

CLI `stock-platform-position-review`：

- **自包含模式**：holdings JSON 自带 `price` / `ma20` / `ma60`。
- **富化模式**（`--db` + `--asof`）：只读 `market.db`，用 `backtest.compute_features` 重建**与回测同源的复权序列**取 `price`/`ma20`/`ma60`/`pct_chg`；`held_days` 由 `entry_date` 在**全量**会话序列中定位（早于库覆盖时标 `held_days_unresolved`，不猜 0）。
- ⚠️ 富化模式下 `entry_price` **必须同复权口径**，否则收益不可比（见 §7 局限 4）。
- holdings JSON 以 `utf-8-sig` 读取，兼容 Windows PowerShell `Set-Content -Encoding UTF8` 写的 BOM。

---

## 7. 已知局限（显式声明，不在 B5 修）

1. **`pct_chg` 标度混用 → 涨跌停判定实际极少触发。** 引擎 dump 的 `pct_chg` 多数行是小数（`0.005`）、少数是百分点（`0.5`），而阈值是百分点（`10.0 − 0.01`）；于是只有少数"百分点"行可能触发涨跌停约束。这是 **B1 既有行为**，B5 **刻意不改**——修它会让全周期基线移动（属策略变更，应单独立项）。列为后续项（建议并入 `B7` 或 `X` 域代码/数据规范）。
2. **ETF 的涨跌停档位未接入**：`limit_pct` 只给股票三档，ETF 按主板 10% 处理；ETF 实际无涨跌停（或按产品规则）这一假设**尚未声明**，属后续项。
3. **成交价 = 当日收盘价**：`market.db` 无 open/high/low，与引擎 `get_price_on_date` 同口径；**非** T+1 开盘成交。
4. **富化模式的复权基期**：`compute_features` 的复权序列以加载窗口首价为基准，**比例**与全历史一致但**绝对价位**不同；故 `entry_price` 与 `price` 必须同一口径。
5. **在线路径不含 L0 市场闸门 / ST 黑名单 / 生存者偏差校正**——与回测模块同（见 `backtest.py` 模块 docstring 的 Known deltas）。

---

## 8. 实测（全周期 2020-01-02～2026-09-08 / 1618 交易日 / 6964 码）

加载 13.3 s；单次回测 ≈ 47 s。

| 指标 | 默认档（`cooldown_days=0`） | 冷静期档（`cooldown_days=10`） | Δ |
|---|---|---|---|
| `total_return` | **0.902353** | 0.898259 | −0.0041 |
| `cagr` | **0.105348** | 0.104977 | −0.0004 |
| `max_drawdown` | **−0.171435** | −0.171416 | +0.00002 |
| `sharpe` | **0.7511** | 0.7508 | −0.0003 |
| `sortino` | 0.7223 | 0.7177 | −0.0046 |
| `calmar` | 0.6145 | 0.6124 | −0.0021 |
| `n_trades` | **630** | 631 | +1 |
| `win_rate` | **0.4619** | 0.4596 | −0.0023 |
| `final_equity` | **95117.64** | 94912.95 | −204.69 |
| `turnover_notional_per_year` | 11.28 | 11.29 | +0.01 |
| `avg_hhi` | 0.086483 | 0.086447 | −0.00004 |

**默认档与 B4 基线逐位一致**（`0.902353 / 0.105348 / −0.171435 / 0.7511 / 630 / 0.4619 / 95117.64`）——`evaluate_exit` 抽取代换是**纯重构**。

冷静期档：收益 −0.41 pp、终值 −204.69（≈ −0.22%）。低频组合（1618 会话 630 笔）里同码快速再入场本就罕见，故影响小；`n_trades` 反增 1 属**级联效应**（某日被阻断的再入场让位给另一标的，后续出场/再入场链随之偏移）。→ **冷静期是风险约束，不是收益工具**；本档仅为口径演示，不构成策略建议。

---

## 9. 不可横比铁律（扩展 [asset-classes.md](asset-classes.md) §7）

> 比较任何两个回测，除 区间 / 宇宙 / 持有期 / 费用档 / L0 外，还必须对齐 **退出策略档（`exit_policy`）· `cooldown_days` · `drift_band`**。

违反示例：把 `cooldown_days=0` 与 `cooldown_days=10` 的终值并列而不声明冷静期 —— 会被误读为"冷静期降低了收益"，实际是一次**参数变更**。`run_portfolio_backtest` 的 `params` 已回显 `exit_policy` / `cooldown_days` / `drift_band`，报告数字时**必须**一并给出。

---

## 10. 相关

- 费用与摩擦：[cost-model.md](cost-model.md)
- 资产类型与宇宙：[asset-classes.md](asset-classes.md)
- 指标口径：[portfolio-metrics.md](portfolio-metrics.md)
- 市场抽象（涨跌停 / T+1 / 日历）：[market-strategy.md](market-strategy.md)
- 回测基线与实测表：[backtest-baseline.md](../ops/backtest-baseline.md)
- 路线图（B5 条目 / 关键路径）：[trading-system-roadmap.md](../plans/trading-system-roadmap.md)
