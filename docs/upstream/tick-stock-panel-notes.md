# tick-stock-panel：契约与回测边界摘要

> **只读归档** · 归档日：2026-09-22  
> **来源**：`../tick-stock-panel/CONTRIBUTING.md`、`docs/secondary-development.md`（只读参考）  
> **平台权威**：`docs/contracts/*`、Workbench fail-closed、ADR 0005/0007  
> **未迁入**：完整 React SPA、Polars/DuckDB 研究栈、分钟回测全链。

## 已吸收语义

- Provider 契约与能力矩阵七项起的 fail-closed 思想 → 本仓能力矩阵 + 409。  
- 「先理解调用链 / 不平行第二套数据源」→ CONTRIBUTING 红线。  
- 回测首刀选型（walk-forward 摘要，非整仓引擎）：[`../plans/m-r1-tsp-backtest-first-knife.md`](../plans/m-r1-tsp-backtest-first-knife.md)。  
- UI 子集范围：ADR 0052（accuracy sparkline），非整站前端。

## 明确不做

- 把 TSP 当第二产品主链或默认 UI。  
- 整仓搬 mining / optimizer / vectorbt 强制依赖。
