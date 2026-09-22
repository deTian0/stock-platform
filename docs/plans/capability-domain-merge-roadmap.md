# 按能力域合并路线图（非整仓 merge）

> **状态**：Later 余量收口（v3.12.0；文档日：2026-09-22；初版 planned 2026-09-15）  
> **权威产品仓**：`stock-platform`  
> **输入**：用户合并原则 · [能力盘点](workspace-projects-capability-inventory.md) · [可用推荐计划](usable-recommend-review-milestones.md) · [`docs/upstream-archive.md`](../upstream-archive.md)  
> **本文件职责**：可执行的能力域里程碑与验收；**Now / Next / Later 余量（除 M-E4 门禁）已落地**。

---

## 1. 总则

1. **非整仓 merge**  
   按能力域增量吸收配方、契约、测试与可移植内核；禁止把 sibling 仓整仓并入、禁止 fork 出第二条产品主链。

2. **唯一权威**  
   - 数据：`packages/providers` + 能力矩阵（缺能力 **fail-closed**，典型 409）。  
   - 选股/简报/PIT：`packages/research`（lvrev + brief + PIT）。  
   - Agent：`packages/agents`（数据只经注入的 Provider，见 ADR 0009）。  
   - 执行：`packages/execution`（默认纸面 **SIMULATE**）。  
   - UI：现有 Workbench（FastAPI + Jinja2/原生 JS）为短期主链。

3. **SIMULATE / 安全**  
   默认纸面；`liveTradingEnabled=false`；同花顺真实 HTTP / 实盘 / Futu OpenD **延期**；禁止把 token 写入仓库或计划正文。

4. **fail-closed**  
   无能力、无 token、无宇宙、历史 asof 误注 realtime 等 → 显式失败或告警，禁止静默 fixtures 冒充 live（与 usable 线一致）。

5. **吸收顺序（通用）**  
   盘点缺口 →（必要时）新 ADR / 契约 → 扩能力矩阵或注册声明 → 接线实现 → 单测/回放 → 文档交叉链。**先扩矩阵再接线。**

6. **编号约定**  
   | 前缀 | 域 |
   |------|----|
   | **M-D*** | 数据 |
   | **M-R*** | 选股 / 回测 |
   | **M-A*** | Agent |
   | **M-U*** | UI |
   | **M-E*** | 执行 / 运维 |
   | **M-S*** | 文档技能仓治理 |

   量级：**S**（≤约 1～2 人日） / **M**（约 3～5 人日） / **L**（需拆子里程碑）。  
   档位：**Now** / **Next** / **Later**。

---

## 2. 数据域

### 2.1 目标

以 `packages/providers` + 能力矩阵为**唯一**运行时权威；从 Skill/引擎仓按端点增量吸收字段、限流、备胎；`market.db` 只读挂载；PIT 基本面表是否暴露由**新 ADR**决定（非整仓拷贝）。

### 2.2 源仓

| 源 | 吸收什么 | 不吸收什么 |
|----|----------|------------|
| `a-stock-data` | 端点配方（字段、`em_get` 限流、备胎） | pip 依赖、平行 HTTP、整 Skill 运行时 |
| `global-stock-data` | US/HK 字段与合规分级语义 | 期权 / SEC / FINRA 深水区（刻意不搬） |
| `a-stock-engine` | 只读 `market.db`；可选 PIT 基本面**表暴露方案** | westock 抓取链、冻结每日管线整仓 |
| TradingAgents `dataflows` | （对照用）未来函数/非 A 股防护思路 | **禁止**回灌 `a_stock.py` 进平台 |

### 2.3 吸收方式

1. 对照 Skill / 盘点「未接端点」→ 选 1 个能力进矩阵草案。  
2. 写/改 `docs/contracts/*` +（大能力）ADR。  
3. 注册矩阵项 → Provider 实现（优先 replay fixtures）→ live 适配走既有节流入口。  
4. Workbench 路由仅在矩阵声明后接线；缺能力 fail-closed。

### 2.4 明确不做

- 整仓 merge Skill 仓或引擎仓。  
- `pip install` a-stock-data / global-stock-data / finance-quant-skills。  
- 第二套东财客户端或裸 `requests.get` 打 eastmoney。  
- 把引擎 `selections` 历史管线恢复为平台双主链。

### 2.5 里程碑

| ID | 名称 | 档 | 量级 | 依赖 | 验收标准（摘要） |
|----|------|----|------|------|------------------|
| **M-D1** | 端点缺口对照表（矩阵 vs Skill） | **Now → done** | S | 盘点已完成 | [m-d1-capability-gap-matrix.md](m-d1-capability-gap-matrix.md)；下一刀候选 `concept_blocks` |
| **M-D2** | engine PIT 基本面暴露 ADR 草案 | **Now → done** | S | `EngineSqliteProvider`、ops 文档 | [ADR 0050](../architecture/0050-engine-pit-fundamentals-readonly.md) **Accepted**（M-D4 落地） |
| **M-D3** | 下一刀 CN 能力：扩矩阵再接线 | **Next → done** | M | M-D1 | `concept_blocks`：契约 ADR 0051 + 矩阵 + replay/astock_http + API；零公网测 |
| **M-D4** | `market.db` PIT 只读 Provider 切片 | **Next → done** | M | M-D2 Accepted | `get_*_pit` + HTTP；无未来函数；无 DB fail-closed；ADR 0050 Accepted |
| **M-D5** | global 薄补强（非深水区） | **Later → done（文档）** | M | M-D1 | [`docs/ops/m-d5-global-thin-gap.md`](../ops/m-d5-global-thin-gap.md)；期权/SEC/FINRA 仍排除 |
| **M-D6** | 批量端点配方回馈上游说明 | **Later → done** | S | M-D3+ | [`docs/ops/m-d6-batch-recipe-upstream-feedback.md`](../ops/m-d6-batch-recipe-upstream-feedback.md)；仍禁止平行运行时 |

---

## 3. 选股 / 回测域

### 3.1 目标

主链保持 **lvrev + brief + PIT**；更强回测/挖掘时对照 tick-stock-panel 契约与测试，**分里程碑**移植能力；`a-stock-engine/empirical` 仅作基线对照，**不恢复双管线**。

### 3.2 源仓

| 源 | 吸收什么 | 不吸收什么 |
|----|----------|------------|
| `tick-stock-panel` | 回测/筛选契约语义、测试矩阵、可移植算法口径 | React SPA、Polars/DuckDB 整栈、TickFlow 档位整仓 |
| `a-stock-engine` | empirical 结果作对照基线；已迁 lvrev 不再重搬 | `local_backtest` / 冻结脚本双主链 |
| usable 线（U7/U8） | Workbench 已有滚动复盘/策略对比切片 | 把完整 A/B 强行塞进每日推荐主路径 |

### 3.3 吸收方式

1. 对照 TSP `backtest/` / screener 契约与平台 `run_pit_long_only` / 滚动复盘差距。  
2. 每刀只移植**一种**能力（如 walk-forward 报告字段、因子 IC 表、分钟回测入口之一）。  
3. 实现落在 `packages/research`；数据仍经 providers。  
4. empirical JSON 只读比对脚本/文档，不并行调度引擎仓。

### 3.4 明确不做

- React/Polars/DuckDB 整仓迁入。  
- 恢复 a-stock-engine 每日脚本为第二推荐主链。  
- 全市场自动扫宇宙（仍属 Later / 非 DoD）。

### 3.5 里程碑

| ID | 名称 | 档 | 量级 | 依赖 | 验收标准（摘要） |
|----|------|----|------|------|------------------|
| **M-R1** | TSP 回测能力对照 + 首刀选型 | **Now → done** | S | inventory、U7/U8 现状 | [m-r1-tsp-backtest-first-knife.md](m-r1-tsp-backtest-first-knife.md)；首刀=walk-forward 摘要 |
| **M-R2** | 首刀回测能力移植（research 内） | **Next → done** | M–L | M-R1、providers 矩阵 | walk-forward 摘要内核 + API + `#backtest` 折叠；零公网；不进 brief 主路径 |
| **M-R3** | empirical 基线对照手册 | **Later → done** | S | M-R1 | [`docs/ops/empirical-baseline-compare.md`](../ops/empirical-baseline-compare.md) + compare helper；无双调度 |
| **M-R4** | 第二刀回测/挖掘（按需） | **Later → done（深刀）** | L | M-R2 稳定 | rank IC + **ICIR/std** + `summarize_factor_ic_from_rows` + `POST /backtest/factor-ic`；不进 lvrev 主路径 |
| **M-R5** | 策略 A/B 进日用主路径 | **Later → done** | L | usable Later、M-R2 | `STOCK_PLATFORM_STRATEGY_AB` / `strategyAb` 默认关闭；旁路摘要不替换 picks |

---

## 4. Agent 域

### 4.1 目标

默认**确定性** Bull/Bear/Risk 辩论 + **可选** LLM；更深投研时从 TradingAgents 移植**角色提示 / 工具清单 / 评级边界**；数据强制走 providers（[ADR 0009](../architecture/0009-agent-plugins.md)）。

### 4.2 源仓

| 源 | 吸收什么 | 不吸收什么 |
|----|----------|------------|
| TradingAgents-astock | 角色 system 提示要点、工具名清单语义、`rating` 边界规则、绩效命名口径 | `dataflows/a_stock.py`、完整 LangGraph 默认化、Streamlit 第二 UI 主链 |

### 4.3 吸收方式

1. 抽取提示/评级规则为平台文档或 `packages/agents` 内配置（无 URL）。  
2. 工具调用只解析为「要哪类矩阵能力」→ `resolve(cap)`。  
3. 评级边界变更必须跑全矩阵测试（对齐上游血泪：边界正则）。  
4. LLM 路径保持可选、预算降级、缺密钥 fail-closed。

### 4.4 明确不做

- agents 包内嵌 HTTP / mootdx。  
- 默认切换为完整 7 Analyst LangGraph。  
- 并入 Streamlit 为第二前端主链。

### 4.5 里程碑

| ID | 名称 | 档 | 量级 | 依赖 | 验收标准（摘要） |
|----|------|----|------|------|------------------|
| **M-A1** | TA 可移植清单（提示/工具/评级） | **Now → done** | S | ADR 0009 | [m-a1-tradingagents-portability.md](m-a1-tradingagents-portability.md)；禁 dataflows |
| **M-A2** | 评级边界对齐 + 矩阵测 | **Next → done** | M | M-A1 | `rating.py` + 边界矩阵测；LLM 回退接线；误判不进绩效 |
| **M-A3** | 角色提示增量（政策/游资/解禁等按需） | **Later → done** | M | M-A2、对应数据能力 | `role_prompts`；每角色声明 capabilities；无能力 fail-closed |
| **M-A4** | 可选更深 LLM 图（非默认） | **Later → done** | L | M-A3、成本控制 | `deep_llm_graph` + `STOCK_PLATFORM_DEEP_LLM_GRAPH`；默认确定性；数据仅 providers |

---

## 5. UI 域

### 5.1 目标

短期强化现有 Workbench **向导与可读性**；专业图表/监控另开「**TSP UI 子集**」里程碑；避免同时维护两套前端主链。

### 5.2 源仓

| 源 | 吸收什么 | 不吸收什么 |
|----|----------|------------|
| 现有 Workbench | IA、向导、中文文案、渐进披露 | — |
| tick-stock-panel frontend | 图表/监控**交互语义**与验收用例 | 整套 React+Vite+ECharts 并行主链 |
| V2 Next.js / TA Streamlit | 布局启发（可选） | 第二发行前端 |

### 5.3 吸收方式

1. Now：只改 Jinja/static 与 API 展示字段。  
2. 若开 TSP UI 子集：先 ADR「子集范围 + 仍单一入口端口习惯」→ 再嵌只读组件或独立路由，**不**分裂产品定位。  
3. usable Next（近 N 日 accuracy 迷你图、复盘空态）优先于新 SPA。

### 5.4 明确不做

- 同时维护 Workbench 与完整 TSP SPA 为双主链。  
- 为合并而重写前端栈。

### 5.5 里程碑

| ID | 名称 | 档 | 量级 | 依赖 | 验收标准（摘要） |
|----|------|----|------|------|------------------|
| **M-U1** | Workbench 向导/推荐/复盘可读性 | **Now → done** | S | usable Next 项 | v3.10.7：导航三步、空态/中文 tip、交叉锚点；无新框架 |
| **M-U2** | 近 N 日 accuracy 迷你展示 | **Next → done** | S–M | U3/绩效 API | `#recommend` 绩效条 `recentDays` chips；口径=`direction_accuracy` |
| **M-U3** | 「TSP UI 子集」范围 ADR | **Later → done** | S | M-U1 稳定、真实需求 | [ADR 0052](../architecture/0052-tsp-ui-subset.md) **Accepted** |
| **M-U4** | TSP UI 子集首刀（图表或监控之一） | **Later → done** | L | M-U3 | `#tsp-subset` accuracy SVG sparkline；数据经 performance API |

---

## 6. 执行 / 运维域

### 6.1 目标

纸面 + `BrokerPort` 继续演进；同花顺真实 HTTP / 实盘仍延期；V2 快照仅作**安全回归用例**参考，**不恢复 Futu**。

### 6.2 源仓

| 源 | 吸收什么 | 不吸收什么 |
|----|----------|------------|
| V2-code-review-20260905 | 时机/事务/草稿激活/费用门槛等**测试意图** | `futu-api`、OpenD、双轨 `data_service` |
| 已有 execution | PaperLedger、ThsSim mock/experimental | 宣称 production 实盘 |

### 6.3 吸收方式

1. 从 V2 tests 提炼用例名与断言意图 → 映射到现有 timing/transactional/lifecycle。  
2. BrokerPort 演进保持 SIMULATE 默认。  
3. 运维：health / 日批 / Task Scheduler 文档与 usable 运维项对齐。

### 6.4 明确不做

- 恢复 Futu / 真实同花顺实盘开关。  
- 引入第二执行 HTTP 服务与 Workbench 并行。

### 6.5 里程碑

| ID | 名称 | 档 | 量级 | 依赖 | 验收标准（摘要） |
|----|------|----|------|------|------------------|
| **M-E1** | V2 安全用例对照表 | **Next → done** | S | packages/execution | [`docs/ops/v2-safety-test-mapping.md`](../ops/v2-safety-test-mapping.md)；无 Futu |
| **M-E2** | 缺口安全回归补测 | **Next → done** | M | M-E1 | `test_me2_safety_gaps`：错哈希 / admission / order_guards；仍 SIMULATE |
| **M-E3** | BrokerPort / ths_sim 文档诚实性 | **Later → done** | S | Phase D 现状 | [`docs/ops/broker-port-honesty.md`](../ops/broker-port-honesty.md)；experimental ≠ 生产 |
| **M-E4** | 实盘 / 真实券商 HTTP | **Later（门禁，未开工）** | L | 产品显式决策 | **未立项前禁止开工** |

---

## 7. 文档技能仓

### 7.1 目标

`finance-quant-skills` 及 a-stock-data / global-stock-data 的 **Skill 形态**保持 Cursor/Claude Skills **软链或只读引用**；不假装已是运行时模块。

### 7.2 源仓

| 源 | 吸收什么 | 不吸收什么 |
|----|----------|------------|
| finance-quant-skills | 文档镜像、策略 API 说明 | pip 进产品依赖、平行抓取脚本当主链 |
| a-stock-data / global-stock-data | 同上（Skill） | 运行时模块化 |

### 7.3 吸收方式

- CONTRIBUTING / AGENTS / upstream-archive 写清「软链路径、只读、非依赖」。  
- 配方变更：先改平台 providers，再可选回馈 Skill 文档（双写说明）。

### 7.4 明确不做

- `pip install` 进 `pyproject` 产品依赖。  
- 平行抓取第二条数据链。  
- 在计划或 UI 中宣称「已接入某某 Skill 运行时」。

### 7.5 里程碑

| ID | 名称 | 档 | 量级 | 依赖 | 验收标准（摘要） |
|----|------|----|------|------|------------------|
| **M-S1** | Skills 软链/只读治理说明落地 | **Now → done** | S | upstream-archive | [`docs/ops/skills-governance.md`](../ops/skills-governance.md)；禁止 pip/平行抓取 |
| **M-S2** | 配方回馈检查清单 | **Later → done** | S | M-D3 | [`docs/ops/skill-recipe-feedback-checklist.md`](../ops/skill-recipe-feedback-checklist.md) |

---

## 8. 跨域依赖图（文字）

```
M-D1（缺口表）
  ├─→ M-D3（扩矩阵接线）─→ M-A3（新角色所需能力）
  ├─→ M-D5（global 薄补）
  └─→ M-R* / M-U*（展示新能力时依赖矩阵已声明）

M-D2（PIT ADR）─→ M-D4（只读暴露）─→（可选）M-R 实证/基本面因子

M-R1（TSP 选型）─→ M-R2（首刀移植）─→ M-R4/M-R5
                 └─→ M-R3（empirical 对照）

M-A1（可移植清单）─→ M-A2（评级边界）─→ M-A3/M-A4

M-U1（Workbench 可读）─→ M-U2 →（需求驱动）M-U3 → M-U4

M-E1 → M-E2；M-E4 独立门禁

M-S1 约束所有域：禁止 Skill pip / 平行抓取

usable 线（U1–U8）：日用推荐/复盘真相源；本路线图不改写其 done 叙事。
本路线图提供「上游能力增量」轨道；与 usable Next/Later 可并行，冲突时日用可用优先。
```

---

## 9. 与 inventory / usable-recommend 的关系

| 文档 | 关系 |
|------|------|
| [workspace-projects-capability-inventory.md](workspace-projects-capability-inventory.md) | **输入盘点**（有/部分/未接）；本文件是其「下一步建议」的**可执行展开** |
| [usable-recommend-review-milestones.md](usable-recommend-review-milestones.md) | **日用可用**轨道（U1–U8）；本文件不替换 U 编号；重叠时（如 UI 可读性）可复用验收口径 |
| [`docs/ROADMAP.md`](../ROADMAP.md) | 历史 M0–M47 / Phase 叙事仍有效；本文件是收敛后的**跨仓能力域**增量轨 |
| [`docs/upstream-archive.md`](../upstream-archive.md) | 红线与未迁入清单；本文件里程碑不得突破其红线 |
| ADR 0009 / 0049 | Agent 无内嵌抓取；brief SQLite 与 engine `market.db` 分离——数据/Agent/研究里程碑须遵守 |

---

## 10. 第一批 Now（可执行，3～6 项）

| # | ID | 动作 | 量级 | 完成定义 | 状态 |
|---|-----|------|------|----------|------|
| 1 | **M-D1** | 写「能力矩阵 × Skill 端点」缺口对照表（CN 优先，附 US/HK 暂缓项） | S | [m-d1-capability-gap-matrix.md](m-d1-capability-gap-matrix.md) | **done** |
| 2 | **M-D2** | 起草 engine PIT 基本面只读暴露 ADR（Accepted 前不写 Provider 业务） | S | [ADR 0050](../architecture/0050-engine-pit-fundamentals-readonly.md) Proposed | **done** |
| 3 | **M-R1** | TSP 回测对照 + **唯一**首刀选型纪要 | S | [m-r1-tsp-backtest-first-knife.md](m-r1-tsp-backtest-first-knife.md)（walk-forward 摘要） | **done** |
| 4 | **M-A1** | TradingAgents 提示/工具/评级可移植清单（禁 dataflows） | S | [m-a1-tradingagents-portability.md](m-a1-tradingagents-portability.md) | **done** |
| 5 | **M-U1** | Workbench 向导与推荐/复盘扫读抛光 | S | v3.10.7 UI 文案/结构；pytest 静态断言 | **done** |
| 6 | **M-S1** | Skills 软链与「非运行时」治理说明写入平台文档 SSOT | S | [`docs/ops/skills-governance.md`](../ops/skills-governance.md) | **done** |

**并行建议**：1+2+3+4+6 可文档并行；5 可与 usable Next 合并排期。  
**故意未进 Now**：M-D3 接线、M-R2 移植、M-U3 SPA、M-E4 实盘——均依赖上表选型/ADR。

**余量状态（v3.12.0）**：M-R5 · M-U3/U4 · M-A4 · M-E3 · M-D6 · M-R4 深刀 → **done**；**M-E4 仍 Later 门禁（未开工）**。

---

## 11. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-09-15 | 初版：按用户能力域原则展开里程碑、依赖、Now 清单 |
| 2026-09-17 | Now 六项全部收口：对照表/ADR/选型/清单/UI/Skills 治理；状态 Now→done |
| 2026-09-18 | Next 六项收口（v3.11.0）：concept_blocks / PIT / walk-forward / 评级边界 / 近N日 accuracy / V2 安全对照 |
| 2026-09-18 | Later 首批（v3.11.1）：M-R3/R4 薄刀 / M-A3 / M-E2 / M-D5 / M-S2 + concept_blocks/PIT 面板 |
| 2026-09-22 | Later 余量（v3.12.0）：M-R5 A/B / M-U3–U4 / M-A4 / M-D6 / M-E3 / M-R4 深刀；**M-E4 仍门禁** |
