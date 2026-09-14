# ADR 0043：组合 PIT 指标 + 纸面成交对齐绩效

- 状态：Accepted
- 日期：2026-09-14

## 背景

M34 提供了策略配置对比与 `run_pit_long_only`，但缺少组合级回撤/换手视图。
推荐绩效（ADR 0033）与纸面成交仍需手工 JSONL，日用复盘摩擦大。

## 决策

1. **薄范围冻结**（非全量化平台）：
   - `portfolio_metrics` / `run_portfolio_pit`：在现有等权日收益曲线上报告
     `max_drawdown`、`turnover`（由 `|Δ n_picks|` 近似）、`n_trades`、
     `final_equity`，并注明 equal-weight。
   - **不做**：成本模型、夏普/年化主指标、权重优化、多空组合会计。
2. **纸面成交 → 绩效**：`align_fills_to_performance(fills, holding=..., log_path=...)`
   - 接受 Fill-like dict 或 duck-type 对象（`symbol` / `side` / `qty` / `price` /
     `ts|date|filled_at`）；软类型，不硬依赖 execution 包。
   - Buy→`Buy`、Sell→`Sell`；无收益则 pending，有 `raw`/`return` 则已结算。
   - 经现有 `append_jsonl` 写入；CLI `stock-platform-performance --align-fills`。
3. **`direction_accuracy` 口径不变**（ADR 0033）：Hold 不计；看多要涨、看空要跌；
   有 alpha 优先 alpha。本路径只负责落行，不改指标定义。
4. 默认仍 **SIMULATE**；CI 仅 fixtures。

## 后果

- 组合视图与决策绩效职责仍分离：前者是 PIT 曲线摘要，后者是离散推荐点统计。
- 纸面 fills 可自动进绩效日志，减少手工维护。
