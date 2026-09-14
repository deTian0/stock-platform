# ADR 0034：可选 LLM 辩论（默认仍确定性）

- 状态：Accepted
- 日期：2026-09-14

## 背景

M12 / ADR 0017 提供了可 CI 验证的确定性 Bull/Bear/Risk。部分场景希望在
TopN 之后挂可选 LLM 辩论，但不能破坏默认 brief、也不能把 LLM SDK 钉进基础
`pip install`。

## 决策

1. **默认**仍为 `build_debate_report`（`engine=deterministic`）。
2. **可选** `engine=llm`：`STOCK_PLATFORM_LLM_DEBATE=1` + API key +
   `pip install 'stock-platform-agents[llm]'`（soft import `openai`）。
3. 缺依赖 / 缺密钥 / 调用失败 → **`LlmUnavailableError` fail-closed**，明文原因；
   **不**静默回退、不污染 brief 默认路径。
4. 行情数据仅经注入的 `MarketDataProvider`；agents 包内禁止裸东财 URL。
5. TopN 挂载：`POST /api/research/brief/debate`；单票
   `GET /api/debate/report?engine=llm`。
6. 单测用注入 `llm_call` mock；CI 零公网、零密钥。

## 后果

- 无 LLM 用户体验不变。
- 有密钥用户可显式开启；失败时知道缺什么，而不是拿到假的确定性结论。
