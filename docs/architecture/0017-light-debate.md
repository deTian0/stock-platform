# ADR 0017：轻量确定性辩论（无 LLM）

- 状态：Accepted
- 日期：2026-09-14

## 背景

TradingAgents 完整辩论图依赖 LLM/LangGraph；平台 research/review 仅为角色占位。需要可 CI 验证的 Bull/Bear/Risk 结构，且不引入密钥与内嵌抓取。

## 决策

1. `build_debate_report`：仅消费注入的 `MarketDataProvider` 日 K（历史 asof 跳过 realtime）。
2. 确定性计分：收益 / 均线 / 回撤 / 阴线占比 / 波动 → Bull/Bear/Risk → `Buy|Hold|Sell`。
3. 输出含 `rounds`、`score`、`disclaimer`（标明模板、非投资建议、未调用 LLM）。
4. workbench 暴露 `/api/debate/report`；UI 可选挂载。
5. **不**引入 LangGraph、LLM SDK、东财 URL。

## 后果

- 完整多角色 LLM 辩论仍属上游参考；平台权威路径为本确定性插件。
