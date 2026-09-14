# ADR 0046：Workbench IA + 一键日用向导

- 状态：Accepted
- 日期：2026-09-14

## 背景

工作台面板过多，日用路径不直观。需要分区导航与一键「刷新→推荐→纸面」向导，
仍保持 Jinja/静态页，不做 SPA，不默认 live。

## 决策

1. **IA**：顶栏锚点 — 日用向导 / 推荐 / 纸面 / 运维 / 能力矩阵；辩论等标为实验。
2. **向导 API**：`POST /api/research/wizard/daily` — 分步 `steps[]`（refresh / brief / to_paper）；
   每步失败可见；`liveTradingEnabled=false`；默认 `skipRefresh=true`（本地 demo）。
3. **UI**：`#wizard` + `#ops`；按钮文案不含「实盘」。
4. **不做**：SPA、默认 live、真实券商、同花顺真实 transport。

## 后果

- 日用路径与 M40 CLI 对齐语义；调度仍走 ops 脚本。
