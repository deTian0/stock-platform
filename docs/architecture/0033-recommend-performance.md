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

## 修订

- **2026-10-12（ADR [0068](0068-performance-pnl-closed-loop.md)）**：本 ADR 的
  **指标口径不变**，新增的是**闭环**：① 基准 alpha（`alpha = raw − benchmark`，
  默认中证500 `000905`，可环境变量覆盖）；② 收益归因 `build_attribution`
  （`byRank`/`byScore`/`byDate`/`equityCurve`）；③ 持有期单点 `DEFAULT_HOLDING`
  （消除 `daily_cli` 的 `1d` 与其它处 `5d` 漂移）；④ 日报显示真实收益数字。
  `alpha` 字段此前因**无任何调用方构造基准**而结构性恒 `null`，本轮打通（含历史行回填）。
  退出该 ADR 的红线仍然有效：**不算夏普/年化、样本 < 20 标噪音、SIMULATE 不接实盘**。
