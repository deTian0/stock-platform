# 0065 — LLM 辩论进主路径：只读顾问侧车（`S5`）

- **状态**：Accepted
- **日期**：2026-10-11
- **里程碑**：`S5`（目标 tag `v4.1.5`，路线图 §3.3）
- **相关**：ADR [`0017`](0017-light-debate.md)（轻量确定性辩论，无 LLM）·
  ADR [`0034`](0034-optional-llm-debate.md)（可选 LLM 辩论，默认仍确定性）·
  ADR [`0045`](0045-llm-cost-quality.md)（LLM 成本 / 质量控制）·
  契约 [`docs/contracts/debate-lane.md`](../contracts/debate-lane.md)
- **承接的上游约定**：`packages/agents` —— `debate.build_debate_report`（确定性 Bull/Bear/Risk）·
  `llm_debate.build_llm_debate_report` / `run_debate`（预算 / 截断 / 降级）·
  `rating.parse_rating` / `to_ternary_verdict`（**M-A2 五档评级边界**解析）

---

## 背景

ADR `0017` / `0034` / `0045` 已经给了「确定性辩论 + 可选 LLM 辩论 + 预算/截断/降级」三件套，
但它们都挂在**侧路**：`POST /api/research/brief/debate` 与 `GET /api/debate/report?engine=llm`。
三条缺口：

1. **主链看不见辩论**：日常主链 `run_daily_pipeline`（`stock-platform-daily` 驱动）只产 brief /
   命中 / picks 账本，**没有任何挂载点**，LLM 辩论进不了日用路径。
2. **预算不可显式控制**：`_LlmBudget` 只读环境变量，调用方无法为「这一次主链运行」指定预算上限。
3. **「误判不进绩效」只是口头约束**：ADR `0034` 写「不污染 brief 默认路径」，但**没有可断言的不变量** ——
   没有任何测试或契约锁死「辩论判决不得进入 picks 账本 / 命中周期 / 绩效 JSONL」。

路线图 §3.3 的 `S5` 验收标准即：*「保持默认确定性；可选路径带预算控制与降级；误判不进绩效
（对齐 M-A2 口径）」*。

---

## 决策

1. **新增单点模块 `agents.debate_lane`**，把「把辩论挂到 brief 上」做成**只读侧车**：
   - `DEBATE_LANE_ENGINES = ("off", "deterministic", "llm")`；`normalize_lane_engine()` 对未知名
     **抛 `AgentError`**（调用方转 400，**不允许静默回落默认值**）。
   - `attach_debate_lane(provider, brief, *, engine="off", max_picks=None, budget=None, llm_call=None)`
     **只读** `brief`，返回**车道载荷**（不是 brief）：`enabled/engine/debates/debateCount/degraded/
     warnings/advisory/excludedFromPerformance/budget`。
   - `debate_lane_summary()`：给 manifest 用的裁剪（丢回合全文，留计数 + 判决）。
2. **默认 `off`（零 LLM、零副作用）**：引擎 `off` 时车道**不调用任何辩论函数**，直接返回空侧车。
   `deterministic` 无需密钥；`llm` 复用 `run_debate` 的预算 / 截断 / 降级（ADR `0045` 语义不变）。
3. **预算提为一等公民**：`llm_debate._LlmBudget` 提为公开 **`LlmBudget`**，构造函数接受显式
   `max_calls` / `max_tokens_soft`（缺省回落环境变量）；`debate_brief_picks` 增 `budget` 形参；
   车道把实参预算写进载荷 `budget`（`maxCalls/maxTokensSoft/callsUsed/tokensEst`）。
4. **主链挂载走依赖注入**：`run_daily_pipeline(..., debate_runner=None, debate_engine=None,
   debate_max_picks=None)`；`debate_runner` 由调用方注入（`daily_cli` 软导入 agents 构造），
   **`stock-platform-research` 不新增对 `stock-platform-agents` 的依赖**（保持 providers 只做 I/O、
   research 算法纯净的既有分层）。产出 `{asof}/debates.json` + manifest `debates`；**best-effort** ——
   异常落在 `report.debates["error"]`，绝不破坏 brief。
5. **`off` = 不触发**：主链只有在 `debate_engine ∉ {off, none, ""}` 时才调用 runner。
6. **「误判不进绩效」写成不变量**：车道载荷恒带 `advisory=True` / `excludedFromPerformance=True`；
   辩论判决**不是评级**、**不写 picks 账本 / 命中周期 / 绩效 JSONL**；由测试对「开/关辩论两轮」的
   brief JSON、`picks_ledger.jsonl` 与命中块**逐位相等**做断言（见契约 §5）。
7. **本轮不新增手动 UI 面板**：车道是**主链自动化**特性，已由 `stock-platform-daily` 的
   `--debate-engine` 与 `POST /api/research/daily/debate` 暴露；再加一个手动面板会与既有
   `TopN 辩论` 面板重复（`C` 域警告的重复实现）。

---

## 后果

**正面**

- 主链获得**可选的、可预算的、可降级**的辩论侧车，且**默认关闭**（零回归）。
- 「误判不进绩效」从口头约束升级为**可断言不变量** + 契约条款（对齐 M-A2 评级边界口径）。
- 分层不被破坏：research 仍不依赖 agents；agents 仍只经 `MarketDataProvider` 取数。
- 与 `S1`–`S4` 形成一致的「单点 + 默认关 + 契约/ADR + 测试锁定」四件套。

**代价 / 风险**

- **注入式 runner 有认知成本**：主链不直接 import agents，读者要跟一层 `debate_runner` 才到实现 ——
  用注释与契约写明理由（保持 research 无 agents 依赖）。
- **LLM 判决对用户仍可能「看起来像建议」**：车道刻意不与 picks 并列展示为「结论」，并在载荷与
  disclaimer 里写明「只读顾问侧车」。若未来要让判决影响选股，那将是**另一个里程碑**（且需解决
  「误判进绩效」的自相矛盾）。
- **预算只覆盖辩论调用**，不覆盖 `deep_llm_graph`（`M-A4`，仍默认关，不在 `S5` 边界内）。

---

## 备选方案

| 方案 | 为何不选 |
|------|----------|
| 让 research 直接 `import stock_platform_agents` | 打破既有分层（research 目前只依赖 numpy/pandas）；provider/算法层应保持可独立测试 |
| 把辩论判决接进 picks（过滤 / 调序） | 直接违反「误判不进绩效」验收；也会让 LLM 变成选股决策的一部分，合规与可复现性双输 |
| 默认开 `engine=deterministic` | 与路线图「本轮明确不做：默认开启 LLM 辩论」冲突；且默认开会让每次日常运行都多跑辩论，噪音与耗时无收益 |
| 在 `daily_pipeline` 内复制一份辩论调度 | 正是 `C` 域警告的重复实现；`debate_brief_picks` 已存在，车道只做**只读封装** |
| 手动 UI 面板 | 与既有 `TopN 辩论`（`/api/research/brief/debate`）重复；车道定位是主链自动化 |
