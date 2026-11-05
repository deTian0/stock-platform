# 0093 — 多策略 Final Board 影子链（MVP）

- **状态**：Accepted
- **日期**：2026-11-05
- **相关**：计划 [`../plans/multi-strategy-final-board.md`](../plans/multi-strategy-final-board.md) · ADR [`0065`](0065-llm-debate-lane.md) · [`0077`](0077-strategy-adoption-gate.md) · [`0083`](0083-digest-pre-post-and-secondary-pick.md)  
  契约 [`../contracts/multi-strategy-shadow.md`](../contracts/multi-strategy-shadow.md)

---

## 背景

出厂 lvrev（`score_lvrev` + `W_DEFAULT` + 入口闸门 → brief / picks / 命中 / 主绩效）是日用主链。多策略「五校 → Round2 → Final Board」是**并行观察链**，不得静默覆盖出厂产物。升级唯一门：影子证据 → **Y1** 采纳闸门 → 人工签核 → **Y2** 落档。

## 决策

1. **Pipeline**：Round1 五校并行出候选 → Round2 **硬**闸（fail-closed，禁止 pad-to-N）→ Final Board（结构化理由）→ **仅**写影子账本。
2. **五校**：S1 宏观/择时 · S2 事件/主题 · S3 质量/防守（lvrev 谱系）· S4 短线动量 · S5 资金流/流动性。MVP 允许 S1/S2/S5 在数据缺失时 fail-closed 空池并记 `reason`；S3/S4 优先复用既有评分钩子。
3. **双轨仲裁**：
   - **集 A（硬）**：合规 / 流动性 / 涨停 / 集中度 / 学校优先级——唯一可收紧过闸的裁决者。
   - **集 B（顾问）**：贝叶斯 + LLM 估计胜率/期望——**advisory only**；不可放行未过硬闸的票；恒 `excludedFromPerformance`。MVP 可返回 `null` / 占位。
4. **影子落盘**：默认 `local/shadow/`（可用 `STOCK_PLATFORM_SHADOW_DIR` / Settings 覆盖）。**禁止**写生产 picks / hits / `recommend_decisions.jsonl` / 主绩效 JSONL。
5. **空板合法**：硬闸后 Final 可为空；不是缺陷。
6. **LLM**：理由须结构化（持有期 / 触发 / 可证伪预期 / 失效条件）；缺字段 degrade；**不能**覆盖硬闸；不进绩效。规则-only MVP 由规则填结构化字段。
7. **digest**：本 ADR **不**改盘前/盘后简报结构。

## 非目标

改出厂 `W_DEFAULT` / `min_pick_score`；写生产账本；开 live；默认开 LLM；Workbench UI；主题校绕过 `FACTOR_LIBRARY`。
