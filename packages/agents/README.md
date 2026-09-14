# packages/agents

轻量投研 Agent 插件。安装名：`stock-platform-agents`。

## 状态

| 版本 | 能力 |
|------|------|
| **M4.1 / v0.4.1** | `ResearchAgentPlugin` / `ReviewAgentPlugin`；数据仅经 providers |
| **M4.2 / v0.4.2** | workbench `/api/research/report`、`/api/review/report` |
| **M12 / v1.5.0** | 确定性辩论 `build_debate_report` |
| **M33 / v2.5.0** | 可选 LLM 辩论（`[llm]` extra；默认仍 deterministic） |

## 硬规则

1. **禁止**包内直连东财/腾讯/新浪等 HTTP。
2. 历史 `asof` 不得注入 realtime；须告警。
3. ticker 经 `normalize_symbol`（拒港美）。
4. LLM 路径缺依赖/密钥 **fail-closed**，不得静默回退成假确定性结论。

## 安装

```powershell
pip install -e ".\packages\providers[dev]"
pip install -e ".\packages\agents[dev]"
# 可选 LLM：
pip install -e ".\packages\agents[llm]"
# 并设置 STOCK_PLATFORM_LLM_DEBATE=1 与 OPENAI_API_KEY（或 STOCK_PLATFORM_LLM_API_KEY）
pytest packages\agents -q
```

完整 LangGraph 多 Agent 辩论仍参考 TradingAgents-astock；本包是平台槽位适配层。
