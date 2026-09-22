# TradingAgents-astock：多角色研报思路摘要

> **只读归档** · 归档日：2026-09-22  
> **来源**：`../TradingAgents-astock/CLAUDE.md`（约 v0.5.17）  
> **平台权威**：`packages/agents`、ADR 0009 / 0017 / 0034；可移植清单 [`../plans/m-a1-tradingagents-portability.md`](../plans/m-a1-tradingagents-portability.md)  
> **禁止**：并入 `tradingagents/dataflows`；Agent 内嵌 HTTP；默认完整 LangGraph / Streamlit 第二 UI。

## 角色（上游 7 Analyst）

原版 4（市场 / 情绪 / 新闻 / 基本面）+ A 股特化 3（政策 / 游资 / 解禁），经 Bull/Bear + 三方风险辩论出报告。

平台：默认确定性 Bull/Bear/Risk；可选 LLM；更深多角色图仅显式开关（非默认）。数据一律经注入的 Provider / 能力矩阵 resolve。

## 上游数据层注意（对照，勿照搬）

- 东财须限流（上游亦强调 `_em_get`）；本仓统一 `em_get`。  
- 未来函数 / 非 A 股代码防护思路已写入平台 Provider 与矩阵 fail-closed。  
- 评级边界「词边界」规则：平台有独立矩阵测（见 agents `rating`）。
