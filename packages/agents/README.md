# packages/agents

轻量投研 Agent 插件。安装名：`stock-platform-agents`。

## 状态

| 版本 | 能力 |
|------|------|
| **M4.1 / v0.4.1** | `ResearchAgentPlugin` / `ReviewAgentPlugin`；数据仅经 providers |
| **M4.2 / v0.4.2** | workbench `/api/research/report`、`/api/review/report` |
| **M12 / v1.5.0** | 确定性辩论 `build_debate_report` |
| **M33 / v2.5.0** | 可选 LLM 辩论（`[llm]` extra；默认仍 deterministic） |
| **M44** | LLM 预算 / 截断告警 / `STOCK_PLATFORM_LLM_FALLBACK`（默认降级确定性） |
| **M-A4 / v3.12+** | 可选更深多角色图（`STOCK_PLATFORM_DEEP_LLM_GRAPH`；默认关；禁 dataflows） |

## 硬规则

1. **禁止**包内直连东财/腾讯/新浪等 HTTP。
2. 历史 `asof` 不得注入 realtime；须告警。
3. ticker 经 `normalize_symbol`（拒港美）。
4. LLM 路径：`[llm]` 仍可选。缺依赖/密钥/超预算时：
   - 默认 `STOCK_PLATFORM_LLM_FALLBACK=deterministic` → 显式降级确定性辩论（写 warnings）；
   - `fail-closed` → 抛 `LlmUnavailableError` / `LlmBudgetExceeded`。
5. 费用护栏：`STOCK_PLATFORM_LLM_MAX_CALLS`（默认 6）、可选
   `STOCK_PLATFORM_LLM_MAX_TOKENS`（软估计）；截断见 `warn_if_truncated`（ADR 0045）。

## 安装

```powershell
pip install -e ".\packages\providers[dev]"
pip install -e ".\packages\agents[dev]"
# 可选 LLM：
pip install -e ".\packages\agents[llm]"
# 并设置 STOCK_PLATFORM_LLM_DEBATE=1 与 OPENAI_API_KEY（或 STOCK_PLATFORM_LLM_API_KEY）
# 可选：STOCK_PLATFORM_LLM_MAX_CALLS=6 STOCK_PLATFORM_LLM_FALLBACK=deterministic
pytest packages\agents -q
```

完整 LangGraph 多 Agent 辩论仍参考 TradingAgents-astock；本包是平台槽位适配层。
