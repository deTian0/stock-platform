# ADR 0033：推荐决策绩效统计

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase A 已有盘前简报 TopN 与纸面草稿，但缺少「推荐事后准不准」的可复盘统计。
上游 TradingAgents 用记忆日志 + `direction_accuracy` 口径；本仓无等价物。

## 决策

1. 新增本地 **JSONL** 决策日志（默认 `STOCK_PLATFORM_PERFORMANCE_LOG` 或
   `./data/recommend_decisions.jsonl`），字段对齐记忆日志语义：
   `date | symbol | rating | raw | alpha | holding | pending`，并扩展
   `source` / `rank` / `score`。
2. 指标命名即口径（与 TradingAgents 一致）：
   - **`direction_accuracy`**：衡量判断对错；Hold 不计入；看多要涨、看空要跌。
   - **`up_rate` / `outperform_rate`**：描述标的路径，**与判断对错无关**。
   - **`avg_return`**：持有期绝对收益均值（holding-period return）。
3. CLI `stock-platform-performance` + `GET /api/research/performance`；
   工作台 `#performance` 只读展示。
4. **不算**夏普/年化；样本 &lt; 20 时标注噪音。
5. 仍 SIMULATE；不接实盘。

## 后果

- 可用 fixtures 确定性验收；生产可把 brief TopN 落 pending 后再结算。
- 与 PIT 组合回测（M34）分离：本 ADR 是离散决策点统计，不是可交易组合曲线。
