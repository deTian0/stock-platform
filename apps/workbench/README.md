# apps/workbench

量化研究工作台应用（规划吸收 tick-stock-panel）。

## 状态

**占位（v0.0.x）** — 无可运行服务。

## 计划

- M2：最小可跑壳 + Provider 能力路由
- M3：选股 / 回测权威路径
- M4：研报 Agent 插槽
- M6：纸面执行（可选）

## 约束

- 遵循 `docs/contracts/`；通用功能不绑死单一数据源品牌
- 写路径注意缓存 / SSE / 前端 invalidation 一致性（迁入时对照 TSP CONTRIBUTING）
