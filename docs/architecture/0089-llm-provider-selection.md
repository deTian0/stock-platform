# 0089 — LLM 提供商选择（workbuddy 默认 / DeepSeek 正式接入）

- **状态**：Accepted
- **日期**：2026-11-05
- **相关**：ADR [`0088`](0088-llm-sidecar-package-boundary.md) · [`0065`](0065-llm-debate-lane.md) · [`0045`](0045-llm-cost-quality.md)  
  运维 [`docs/ops/llm-providers.md`](../ops/llm-providers.md)

---

## 背景

`llm_debate._default_openai_call` 原先只做 `OpenAI(api_key=...)`，**不传 `base_url`**，默认模型 `gpt-4o-mini`。第三方（如 DeepSeek）只能靠 SDK 隐式读 `OPENAI_BASE_URL`，不是正式配置。本机日用数据走 workbuddy，LLM 只有 DeepSeek key —— 需要可切换的提供商单点。

---

## 决策

1. **单点** `stock_platform_agents.llm_provider`：所有 in-process LLM HTTP 调用（辩论、deep-graph）只经此模块。
2. **`STOCK_PLATFORM_LLM_PROVIDER`**（默认 **`workbuddy`**）：
   - `workbuddy`：进程内商业 LLM **关闭**；行情/缓存应走 workbuddy bridge；Workbench/CLI 状态给出切换指引。
   - `deepseek`：只用 **`DEEPSEEK_*`**（key / base_url / model / vision / timeout / max_tokens），**不**回落 `OPENAI_*`。
   - `openai`：OpenAI 兼容（`OPENAI_*` / `STOCK_PLATFORM_LLM_*`）。
3. 仍需 **`STOCK_PLATFORM_LLM_DEBATE=1`** 才允许辩论/deep-graph 真正打网。
4. 视觉：`DEEPSEEK_VISION_ENABLED` + `DEEPSEEK_VISION_MODEL` 写入 status；当前辩论链路仍是纯文本，视觉留给后续多模态入口，但配置面先齐。
5. 数据 provider 与 LLM provider **正交**：选 `deepseek` 不强制改行情源；日用仍建议 `--provider workbuddy`。

---

## 后果

**正面**：DeepSeek 成为一等公民；默认 workbuddy 不会误打外部 LLM；状态接口可审计 provider/model/baseUrl（无密钥）。

**代价**：旧「只设 `OPENAI_API_KEY` + 隐式 `OPENAI_BASE_URL`」在默认 `workbuddy` 下不再可用，必须显式 `STOCK_PLATFORM_LLM_PROVIDER=deepseek|openai`。
