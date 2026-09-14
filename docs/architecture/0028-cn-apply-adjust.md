# ADR 0028：CN 复权套价（apply_adjust）

- 状态：Accepted
- 日期：2026-09-14

## 背景

M21（ADR 0026）只交付 `adj_factor` 因子序列，明确不做套价。
不复权日 K 跨除权日直接比价必错。a-stock-data §1.4 已校准新浪
qfq/hfq 方向（前复权除、后复权乘）；空因子原样返回会把不复权价
伪装成复权价。

## 决策

1. **不新增**能力 id：套价是 `daily` + `adj_factor` 上的确定性函数。
2. `apply_adjust(bars, factors, kind="qfq"|"hfq")` 位于 providers；
   无 HTTP、无 pandas、CI 零公网。
3. 语义对齐 §1.4：
   - `qfq`：`adjusted = raw / ex_factor`
   - `hfq`：`adjusted = raw * ex_factor`
   - 阶梯：不晚于 K 线日的最近因子。
4. **fail-closed**：空因子、早于最早因子日、因子为 0、混标的却无
   `symbol` 的因子行 → 抛错，禁止返回未复权价。
5. 输出列名 **`ex_factor`** + `adjust_kind`；不新增并行 `adj_factor` 列。
6. 只缩放 `open/high/low/close/pre_close`；量额与 `change_pct` 不动。
7. workbench 薄出口 `GET /api/market/daily-adjusted`；默认 replay。
8. **不做** 分钟套价、新能力、默认 live、实盘、LLM/SPA。

## 后果

- 研究/工作台可得到确定性复权 OHLC；涨跌停判定仍须用不复权 raw。
- 新浪 hfq 与其它源后复权价可能差一个恒定倍数，不跨源比绝对值。
