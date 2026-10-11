# 契约：辩论车道（只读顾问侧车，`S5`）

> **状态**：Accepted（2026-10-11）　**里程碑**：`S5`（路线图 §3.3）　**目标 tag**：`v4.1.5`
> **上游**：`docs/plans/trading-system-roadmap.md` §3.3 ｜ ADR [`0065`](../architecture/0065-llm-debate-lane.md)
> **承接**：ADR [`0017`](../architecture/0017-light-debate.md)（确定性辩论）·
> ADR [`0034`](../architecture/0034-optional-llm-debate.md)（可选 LLM 辩论）·
> ADR [`0045`](../architecture/0045-llm-cost-quality.md)（LLM 成本 / 质量）

---

## 1. 一句话

把可选的 Bull/Bear/Risk 辩论作为**只读顾问侧车**挂到主链 brief 上：**默认 `off`（零 LLM）**，
可选 `deterministic` / `llm`（带**显式预算**与**非静默降级**），且**判决不进绩效** ——
picks 账本 / 命中周期 / 绩效 JSONL 与「不开辩论」时**逐位相同**。

---

## 2. 引擎与默认

| 引擎 | 含义 | 需要密钥 | 网络 |
|------|------|----------|------|
| **`off`**（默认） | 完全不调用辩论；返回空侧车 | 否 | 否 |
| `deterministic` | `build_debate_report`（ADR 0017） | 否 | 否 |
| `llm` | `build_llm_debate_report`（ADR 0034）+ 预算 / 截断 / 降级（ADR 0045） | 是 | 是 |

`normalize_lane_engine()` 接受 `off`/`none`/`disabled`、`deterministic`/`rules`/`m12`、
`llm`/`openai`；**其它一律抛 `AgentError`**（HTTP 层转 **400**）——**不静默回落默认值**。

---

## 3. 车道单点

`stock_platform_agents.attach_debate_lane(provider, brief, *, engine="off", max_picks=None,
budget=None, llm_call=None)` —— **只读** `brief`（只读 `asof` 与 `picks`），返回车道载荷：

| 字段 | 语义 |
|------|------|
| `enabled` | 引擎 ≠ `off` |
| `engine` | **事后**引擎（`llm` 降级后会变成 `deterministic`） |
| `requestedEngine` | 请求的引擎（降级前后不变） |
| `picksConsidered` | 参与辩论的 picks 数（`max_picks` 截断后） |
| `debates[]` | `{rank, symbol, debate}`；`debate` 为 `DebateReport.to_dict()` |
| `debateCount` | `len(debates)` |
| `degraded` | `llm` 请求但实际走了确定性 → `True` |
| `warnings[]` | 逐票失败 / 降级原因（**非静默**） |
| **`advisory`** | 恒 `True` —— 只读顾问，不是决策 |
| **`excludedFromPerformance`** | 恒 `True` —— 判决不进绩效账本 |
| `budget` | `{maxCalls, maxTokensSoft, callsUsed, tokensEst}` |
| `liveTradingEnabled` | 恒 `False` |

`debate_lane_summary()` 是给 manifest 的裁剪版（丢弃回合全文，保留计数与判决）。

---

## 4. 预算

`llm_debate.LlmBudget(max_calls=None, max_tokens_soft=None)`（公开）：

- 未传 → 回落环境变量 `STOCK_PLATFORM_LLM_MAX_CALLS`（默认 `6`）/
  `STOCK_PLATFORM_LLM_MAX_TOKENS`（软估计 `len/4`，未设则不设上限）。
- 显式传入 → **覆盖**环境变量（主链可为单次运行定预算，不必改环境）。
- 超预算 → `LlmBudgetExceeded`；随后按 `STOCK_PLATFORM_LLM_FALLBACK` 处理：
  `deterministic`（默认）**显式降级**并在 `warnings` 写明；其它值 **fail-closed** 抛错。

---

## 5. 「误判不进绩效」不变量（可断言）

**判决不是评级。** 车位产出**只**落在 `{asof}/debates.json` 与 manifest `debates` 字段，
**绝不**写入：

- `brief.json` / `brief["picks"]`（车道不注入、不调序、不过滤）
- `{out}/picks_ledger.jsonl`（X4 picks 账本）
- 命中周期（X3 `hit_tracking`）
- 绩效 JSONL（`performance.log_brief_decisions` 产出的 decision 行）

由测试锁定（`test_daily_debate_lane.py::test_lane_leaves_brief_ledger_and_hits_identical`）：
**开辩论**与**关辩论**两轮运行，`brief.json` 字节、`picks_ledger.jsonl` 字节与命中块**逐位相等**，
唯一差异是多了 `debates.json`。

对齐 **M-A2**：车道内的判决经 `rating.parse_rating` / `to_ternary_verdict`（五档边界解析）
归一为 `Buy|Hold|Sell`，但**不再往下走**——不转成 decision 行的 `rating` 字段。

---

## 6. 主链挂载

### 6.1 流水线（`stock-platform-research`）

`run_daily_pipeline(..., debate_runner=None, debate_engine=None, debate_max_picks=None)`：

- `debate_runner` 由调用方**注入**（research **不**依赖 agents）；签名
  `runner(*, provider, brief, engine, max_picks) -> lane dict`。
- 仅当 `debate_engine ∉ {off, none, ""}` **且** `debate_runner is not None` 时调用。
- 产出 `{asof}/debates.json`（全文）+ `DailyPipelineReport.debates`（裁剪）+ `manifest.debates`。
- **best-effort**：异常 → `report.debates = {"ok": False, "engine": ..., "error": ...}`，brief 不受影响。

### 6.2 CLI（`stock-platform-daily`）

`--debate-engine {off,deterministic,llm}`（默认 `off`）＋ `--debate-max-picks N`。
`off` 时**不构造 runner、不导入 agents**；`deterministic|llm` 时软导入
`stock_platform_agents.attach_debate_lane`（缺包 `SystemExit` 明示安装命令）。

### 6.3 API（Workbench）

`POST /api/research/daily/debate`：

| 入参 | 默认 | 说明 |
|------|------|------|
| `asof` / `symbols` / `topN` / `adjustKind` / `softGates` / `universeTier` | — | 复用 `_build_brief_for_request` |
| `engine` | `off` | `off` \| `deterministic` \| `llm` |
| `maxPicks` | — | 参与辩论的 picks 上限 |

- **校验先于面板探测**：坏引擎 → **400**（不是 503）。
- 响应含 `ok / engine / requestedEngine / picks / debates / verdicts / advisory /
  excludedFromPerformance / degraded / warnings / budget`，`liveTradingEnabled` 恒 `false`。

---

## 7. 与既有侧路的关系

| 路径 | 用途 | 是否进绩效 |
|------|------|------------|
| `POST /api/research/brief/debate`（既有，`M33`） | TopN 手动辩论（探索） | 否 |
| `GET /api/debate/report?engine=llm`（既有，`M33`） | 单票辩论 | 否 |
| **`POST /api/research/daily/debate`（`S5`）** | **主链车道**（顾问侧车） | 否 |
| `stock-platform-daily --debate-engine`（`S5`） | **主链自动化** | 否 |

`S5` 车道是对既有 `debate_brief_picks` 的**只读封装**（不复制辩论实现）。

---

## 8. 铁律

1. **默认 `off`** —— 任何默认开 LLM 辩论的改动都违反路线图「本轮明确不做」。
2. **车道只读** —— 不得修改 `brief` / picks / 账本 / 命中 / 绩效。
3. **不静默** —— 降级与逐票失败必须写进 `warnings`。
4. **坏引擎 = 400** —— 不得静默回落。
5. **research 不依赖 agents** —— 主链挂载只走注入。
