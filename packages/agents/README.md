# packages/agents

轻量投研 Agent 插件。安装名：`stock-platform-agents`。

> 包版本与根 [`VERSION`](../../VERSION) 对齐（现行 **4.13.7**）。全仓快照见 [`docs/STATUS.md`](../../docs/STATUS.md)。下表只保留早期里程碑锚点。辩论进主路径仍默认 `off`（ADR 0065）。包/导入边界见 ADR [`0088`](../../docs/architecture/0088-llm-sidecar-package-boundary.md)。

## 两面边界

| 面 | 模块 / 入口 | 默认 | 需要 key？ |
|----|-------------|------|------------|
| **确定性** | `debate` / `report` / `plugin` / `rating` / `debate_lane(engine=off\|deterministic)` | 是 | 否 |
| **LLM 侧车** | `stock_platform_agents.llm`（`llm_provider` / `llm_debate` / `deep_llm_graph`）；`engine=llm` | 关 | 是（+ `[llm]` extra） |

`import stock_platform_agents` **不**急切加载 LLM 模块；显式 `import stock_platform_agents.llm` 或访问 `llm_debate_status` 等符号时才加载。

**提供商**（ADR 0089）：`STOCK_PLATFORM_LLM_PROVIDER` 默认 `workbuddy`（进程内不调用）。生产 LLM 用 `deepseek` + `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`（及可选 vision）。详见 [`docs/ops/llm-providers.md`](../../docs/ops/llm-providers.md)。

## 状态

| 版本 | 能力 |
|------|------|
| **M4.1 / v0.4.1** | `ResearchAgentPlugin` / `ReviewAgentPlugin`；数据仅经 providers |
| **M4.2 / v0.4.2** | workbench `/api/research/report`、`/api/review/report` |
| **M12 / v1.5.0** | 确定性辩论 `build_debate_report` |
| **M33 / v2.5.0** | 可选 LLM 辩论（`[llm]` extra；默认仍 deterministic） |
| **M44** | LLM 预算 / 截断告警 / `STOCK_PLATFORM_LLM_FALLBACK`（默认降级确定性） |
| **M-A4 / v3.12+** | 可选更深多角色图（`STOCK_PLATFORM_DEEP_LLM_GRAPH`；默认关；禁 dataflows） |
| **ADR 0088** | LLM 子面 + 确定性路径懒加载（无 key 默认可跑） |

## 硬规则

1. **禁止**包内直连东财/腾讯/新浪等 HTTP。
2. 历史 `asof` 不得注入 realtime；须告警。
3. ticker 经 `normalize_symbol`（拒港美）。
4. LLM 路径：`[llm]` 仍可选。缺依赖/密钥/超预算时：
   - 默认 `STOCK_PLATFORM_LLM_FALLBACK=deterministic` → 显式降级确定性辩论（写 warnings）；
   - `fail-closed` → 抛 `LlmUnavailableError` / `LlmBudgetExceeded`。
5. 费用护栏：`STOCK_PLATFORM_LLM_MAX_CALLS`（默认 6）、可选
   `STOCK_PLATFORM_LLM_MAX_TOKENS`（软估计）；截断见 `warn_if_truncated`（ADR 0045）。
6. 辩论车道判决 **不进** brief / picks 账本 / 命中 / 绩效（ADR 0065）。

## 安装

```powershell
pip install -e ".\packages\providers[dev]"
pip install -e ".\packages\agents[dev]"
# 可选 LLM：
pip install -e ".\packages\agents[llm]"
# STOCK_PLATFORM_LLM_PROVIDER=deepseek
# STOCK_PLATFORM_LLM_DEBATE=1
# DEEPSEEK_API_KEY=...
# 可选：DEEPSEEK_BASE_URL DEEPSEEK_MODEL STOCK_PLATFORM_LLM_MAX_CALLS FALLBACK
# 主链车道：stock-platform-daily --debate-engine llm
pytest packages\agents -q
```

完整 LangGraph 多 Agent 辩论仍参考 TradingAgents-astock；本包是平台槽位适配层。
