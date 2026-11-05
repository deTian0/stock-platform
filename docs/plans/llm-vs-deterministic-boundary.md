# LLM vs 确定性主链边界

> **状态**：第一刀已落地（ADR [`0088`](../architecture/0088-llm-sidecar-package-boundary.md)）  
> **日期**：2026-11-04  
> **前提**：公开开源仍延后；S5 / ADR 0065 已把辩论做成只读顾问侧车。本文把**实测**边界写清，并记录本轮包级收口。

## 1. 结论（先读这）

| 层 | 有 LLM？ | 说明 |
|----|----------|------|
| `packages/research` 主链 | **否** | 选股 / digest / 回测 / attribution / adoption / loop_health / performance **零 LLM SDK**；`pyproject` 无 agents / openai |
| `packages/agents` 确定性槽 | **否** | `debate` / `report` / `plugin`（默认）/ `rating` / `role_prompts` |
| `packages/agents` LLM 侧车 | **是（可选）** | `llm_debate` / `deep_llm_graph`；经 `stock_platform_agents.llm` 入口；`[llm]` extra = `openai` |
| 辩论车道 `debate_lane` | **默认否** | `engine=off`（默认）零调用；`deterministic` 只走 ADR 0017；`llm` 才进侧车 |
| `apps/workbench` | **入口可选** | 确定性研报/复盘/辩论默认路径无 key；`engine=llm`、`/api/debate/status`、`/deep-graph` 才碰 LLM |
| 执行 / providers | **否** | SIMULATE；行情经能力矩阵 / `em_get` |

**不变量（已有测试）**：辩论判决不进 brief / picks 账本 / 命中 / 绩效（`test_daily_debate_lane`）。

## 2. 运行时路径（实测）

```
stock-platform-daily / run_daily_pipeline
  └─ brief + hits + ledger (+ 可选 picks_replay)     ← 纯 research，无 LLM
  └─ 仅当 --debate-engine ∉ {off,none,""}
       └─ DI: debate_runner → soft-import agents.attach_debate_lane
            ├─ off           → 空侧车
            ├─ deterministic → build_debate_report
            └─ llm           → build_llm_debate_report（预算/降级）→ debates.json

Workbench
  /api/research/report · /api/review/report          ← 确定性
  /api/debate/report?engine=deterministic            ← 确定性
  /api/debate/report?engine=llm                      ← LLM 侧车
  /api/research/brief/debate                         ← 默认定性；engine=llm 可选
  /api/research/daily/debate                         ← 默 off；侧车
  /api/debate/status · /api/debate/deep-graph*       ← LLM 状态 / M-A4
```

环境开关（全默认关或降级确定性）：

| 变量 | 作用 |
|------|------|
| `STOCK_PLATFORM_LLM_PROVIDER` | `workbuddy`（默认，进程内关）/ `deepseek` / `openai`（ADR 0089） |
| `STOCK_PLATFORM_LLM_DEBATE` | 显式 opt-in LLM 辩论 |
| `DEEPSEEK_*` | DeepSeek：key / base_url / model / vision / timeout / max_tokens |
| `STOCK_PLATFORM_LLM_API_KEY` / `OPENAI_*` | 仅 `PROVIDER=openai` |
| `STOCK_PLATFORM_LLM_FALLBACK` | 默认 `deterministic`；可 `fail-closed` |
| `STOCK_PLATFORM_LLM_MAX_CALLS` / `_MAX_TOKENS` | 平台预算（与提供商无关） |
| `STOCK_PLATFORM_DEEP_LLM_GRAPH` | M-A4 更深图（另需上面 opt-in + 可用提供商） |
| CLI `--debate-engine` / API `engine` | 车道 / 报告引擎 |

## 3. 本轮第一刀（已做）

1. **agents 包内急切导入收口**：`debate_lane` / `DebateAgentPlugin` 在 `deterministic|off` 路径**不** import `llm_debate`；`llm` 引擎才懒加载。
2. **显式 LLM 子面**：`stock_platform_agents.llm` 集中再导出预算 / 辩论 / deep graph；包根 `__init__` 对 LLM 符号用 `__getattr__` 懒加载，避免 `import stock_platform_agents` 即拉齐 LLM 模块。
3. **Workbench 路由拆分**：确定性 agent 槽留在 `routes/agents.py`；LLM 状态 / deep-graph 迁到 `routes/agents_llm.py`。
4. **research 维持**：仍不对 agents 硬依赖；仅 `daily_cli` 在显式开车道时 soft-import。

## 4. 刻意不做（避免大扫除）

- 不把 `llm_debate.py` 物理搬进子目录（兼容旧 import 路径）。
- 不改 OpenAPI 路径、不改绩效 / 命中契约。
- 不默认打开任何 LLM 开关；不解禁实盘。

## 5. 后续（可选）

- 若要「无 agents 包也能装 workbench」：再把 research 路由里的 `attach_debate_lane` 改成按端点 soft-import（今日 workbench 仍声明依赖 agents）。
- 物理迁文件到 `agents/llm/` 仅在发 major / 破坏窗口时考虑。
