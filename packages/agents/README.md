# packages/agents

轻量投研 Agent 插件。安装名：`stock-platform-agents`。

## 状态

| 版本 | 能力 |
|------|------|
| **M4.1 / v0.4.1** | `ResearchAgentPlugin` / `ReviewAgentPlugin`；数据仅经 providers |
| **M4.2 / v0.4.2** | workbench `/api/research/report`、`/api/review/report` |

## 硬规则

1. **禁止**包内直连东财/腾讯/新浪等 HTTP。
2. 历史 `asof` 不得注入 realtime；须告警。
3. ticker 经 `normalize_symbol`（拒港美）。

## 安装

```powershell
pip install -e ".\packages\providers[dev]"
pip install -e ".\packages\agents[dev]"
pytest packages\agents -q
```

完整 LangGraph 多 Agent 辩论仍参考 TradingAgents-astock；本包是平台槽位适配层。
