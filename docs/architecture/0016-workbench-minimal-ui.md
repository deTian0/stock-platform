# ADR 0016：Workbench 最小 UI

- 状态：Accepted
- 日期：2026-09-14

## 背景

workbench 仅有 FastAPI JSON API，肉眼验收矩阵 / 日 K / 纸面不便。

## 决策

1. `GET /` 返回 Jinja2 单页；静态资源 `/static`。
2. 浏览器用原生 `fetch` 调用既有 `/api/*`；**不改** API 契约。
3. 三区：能力矩阵、日 K、纸面 status（只读；无实盘开关）。
4. 不做 React/Vue SPA、登录、图表库、营销落地页。

## 后果

- UI 仅为验收壳；能力路由仍以矩阵为准，缺能力在页面展示 409 细节。
