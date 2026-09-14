# ADR 0006：工作台最小壳与能力路由

- 状态：Accepted
- 日期：2026-09-13

## 背景

M2 需要可运行入口，但不能过早整仓迁入 tick-stock-panel。

## 决策

1. `apps/workbench` 以 FastAPI 最小壳落地，端口默认 3018（与 TSP 习惯对齐，可改）。
2. 行情路由只通过 `WorkbenchState.resolve(capability)` 取 Provider；缺能力返回 **409** + 矩阵细节。
3. 默认注册 `replay`；不在通用路径出现 TickFlow 等品牌硬编码。
4. 前端与完整服务拆分延后；本阶段以后端契约为准（M11 起另见 ADR 0016 最小 UI）。

## 后果

- M2.2/M2.3 可在此壳上扩展 preferences 与口径对齐，而不推翻路由模型。
- M11 单页 UI 只消费既有 `/api/*`，不改变能力矩阵权威。
