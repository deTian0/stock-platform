# ADR 0045：可选 LLM 成本 / 质量控制

- 状态：Accepted
- 日期：2026-09-14

## 背景

ADR 0034 引入可选 LLM 辩论后，批量 TopN 易放大调用次数与截断静默失败。
需要可测的预算、截断告警与失败策略，且默认产品路径仍为确定性辩论。

> 编号说明：ADR 0044 已用于日历 2028+ / 调度运维包（M42）；本决策为 M44，取 **0045**。

## 决策

1. **预算**（环境变量，无网络探测）：
   - `STOCK_PLATFORM_LLM_MAX_CALLS`（默认 `6`）
   - `STOCK_PLATFORM_LLM_MAX_TOKENS`：软估计（`len/4`）；未设置则不设软上限
2. **截断检测** `warn_if_truncated(response_meta)` 覆盖：
   - Anthropic `stop_reason=max_tokens`
   - OpenAI Chat `finish_reason=length`
   - Gemini `finish_reason=MAX_TOKENS`
   - OpenAI Responses `status=incomplete` +
     `incomplete_details.reason=max_output_tokens`
3. **失败 / 超预算策略**：
   - `STOCK_PLATFORM_LLM_FALLBACK=deterministic`（**默认**）→ 降级
     `build_debate_report`，并在 `warnings` 写明原因（非静默）。
   - 其他值（如 `fail-closed`）→ 仍抛 `LlmUnavailableError` /
     `LlmBudgetExceeded`。
4. 默认 engine 仍为 **deterministic**；`[llm]` extra 保持可选。
5. 单测用 mock `llm_call`；CI 零公网。

## 后果

- 相对 ADR 0034：engine=`llm` 且缺密钥时，默认不再直接失败，而是显式降级；
  需要硬失败时设 `STOCK_PLATFORM_LLM_FALLBACK=fail-closed`。
- 费用护栏与截断告警可在不引入真实 LLM SDK 的情况下单测。
