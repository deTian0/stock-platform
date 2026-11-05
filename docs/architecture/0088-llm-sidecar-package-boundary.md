# 0088 — LLM 顾问侧车：包 / 导入边界收口

- **状态**：Accepted
- **日期**：2026-11-04
- **相关**：ADR [`0017`](0017-light-debate.md) · [`0034`](0034-optional-llm-debate.md) · [`0045`](0045-llm-cost-quality.md) · [`0065`](0065-llm-debate-lane.md)  
  计划 [`docs/plans/llm-vs-deterministic-boundary.md`](../plans/llm-vs-deterministic-boundary.md)  
  契约 [`docs/contracts/debate-lane.md`](../contracts/debate-lane.md)

---

## 背景

S5（ADR 0065）已把辩论挂成主链**只读顾问侧车**，且 `stock-platform-research` **不**依赖 `stock-platform-agents`。  
实测仍有一层模糊：

1. `debate_lane` / `DebateAgentPlugin` **顶层** import `llm_debate.run_debate`，即使 `engine=off|deterministic` 也会加载 LLM 模块（`openai` 虽仍 soft-import，但包边界不清晰）。
2. 包根 `__init__.py` 急切再导出 `llm_debate` / `deep_llm_graph`，`import stock_platform_agents` 即绑定 LLM 面。
3. Workbench `routes/agents.py` 把确定性研报槽与 LLM status / deep-graph 混在同一文件，入口阅读成本高。

产品要求不变：**默认路径零 LLM、无 API key 可跑通**；LLM 集中在明确模块。

---

## 决策

1. **确定性路径不得顶层依赖 LLM 模块**  
   - `debate_lane.attach_debate_lane`：`off` 早退；`deterministic` 直接 `build_debate_report`；仅 `llm` 懒加载 `llm_debate`。  
   - `DebateAgentPlugin.run`：同理按 `engine` 分派。
2. **LLM 子面** `stock_platform_agents.llm`：再导出 `LlmBudget` / `run_debate` / `debate_brief_picks` / `llm_debate_status` / `run_deep_llm_graph` 等；物理文件暂留原路径以兼容。
3. **包根懒加载**：LLM 相关名经 `__getattr__` 延迟导入；确定性符号仍可直接 `from stock_platform_agents import build_debate_report`。
4. **Workbench**：`routes/agents_llm.py` 承载 `/api/debate/status` 与 deep-graph；`agents.py` 只保留研报 / 复盘 / 默认定性辩论报告（`engine=llm` 仍走同一报告端点，内部懒加载）。
5. **不变量保留**：`excludedFromPerformance`、开/关车道 brief/ledger/hits 字节相等；执行层 SIMULATE；东财仍 `em_get`。

---

## 后果

**正面**：无 key 环境导入 / 跑确定性辩论与日更主链时，不再隐式加载 LLM 模块面；文档与包入口对齐「主链 vs 侧车」。

**代价**：包根对 LLM 符号改为懒加载后，`from stock_platform_agents import *` 不会带出 LLM 名（本仓几乎不用 star-import）；静态类型检查若依赖急切绑定，可改为 `import stock_platform_agents.llm`。

---

## 备选方案

| 方案 | 为何不选 |
|------|----------|
| 立刻把 `llm_*.py` 迁入子包并删旧路径 | 破坏面大，超出「最小清晰边界」 |
| research 硬依赖 agents | 违反既有分层（0065） |
| 默认 `engine=deterministic` 开车道 | 与路线图「本轮明确不做默认开辩论」冲突 |
