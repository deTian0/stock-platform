# ADR 0009：Agent 插件无内嵌抓取

- 状态：Accepted
- 日期：2026-09-13

## 背景

TradingAgents 内嵌 a_stock HTTP 与平台 providers 双维护。M4 要求研报槽位只消费统一 Vendor。

## 决策

1. `packages/agents` 为薄插件：`ResearchAgentPlugin` / `ReviewAgentPlugin`。
2. 唯一数据入口：注入的 `MarketDataProvider`（经 workbench `resolve("daily")`）。
3. 历史 `asof` 禁止注入 realtime，并写入 warnings。
4. workbench 暴露 `/api/research/report` 与 `/api/review/report`。
5. 完整 LangGraph 辩论仍可后续接入；不得把东财 URL 写回 agents 包。

## 后果

- TradingAgents 作为可选上游参考；平台路径以本插件为准。
