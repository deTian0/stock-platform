# 计划与路线图文档

> **现行快照**：[`../STATUS.md`](../STATUS.md)（`v4.13.7`）。本目录只放**仍有效**的计划。已落地的 v4.2–v4.4 交接在 [`../archive/`](../archive/README.md)。  
> **SSOT**：`docs/`。原 `.cursor/plans/*.md` 仅保留指向此处的短链索引。

| 文档 | 说明 | 状态（摘要） |
|------|------|----------------|
| [workspace-projects-capability-inventory.md](workspace-projects-capability-inventory.md) | 工作区八仓能力盘点（合并输入，不实施） | 盘点日 2026-09-15 |
| [capability-domain-merge-roadmap.md](capability-domain-merge-roadmap.md) | 按能力域合并路线图（非整仓） | Now/Next/Later 余量已 done；M-E4 实盘仍门禁 |
| [usable-recommend-review-milestones.md](usable-recommend-review-milestones.md) | 真实可用「选股推荐 + 复盘」U1–U8 | done |
| [market-report-dashboard-merge-milestones.md](market-report-dashboard-merge-milestones.md) | 情报看板 Skill 配方吸收（MR-1…） | **v3.12.5：MR-1…MR-5 done**；M-E4 仍门禁 |
| [m-d1-capability-gap-matrix.md](m-d1-capability-gap-matrix.md) | M-D1：能力矩阵 × Skill 端点缺口对照 | done |
| [m-r1-tsp-backtest-first-knife.md](m-r1-tsp-backtest-first-knife.md) | M-R1：TSP 回测首刀选型（walk-forward） | done |
| [m-a1-tradingagents-portability.md](m-a1-tradingagents-portability.md) | M-A1：TradingAgents 可移植清单 | done |
| [trading-system-roadmap.md](trading-system-roadmap.md) | 自有线路线图（G/B/S/X/L/C/R/T/Y 九域） | 现行开放项见 [`../STATUS.md`](../STATUS.md)：`T3` → `v4.14.0`；`R5` 等生产侧 ETF 回补；`Y2` 等人工签核。G/B/S/X/C 与 R1–R4、T1–T2、Y1、Y3、L1 已 done |
| [dual-line-responsibility.md](dual-line-responsibility.md) | 双线职责边界（引擎线 ↔ 平台线，`C1`） | done |
| [duplicate-implementation-convergence.md](duplicate-implementation-convergence.md) | `C3` 双线重复实现收敛清单（18 项，只定边界不删代码） | done（`v4.6.2`，由 `R2` 收口） |
| [b3-cost-model-milestone.md](b3-cost-model-milestone.md) | B3：费用与摩擦模型对齐（里程碑方案） | done（`v3.13.3`） |
| [../archive/README.md](../archive/README.md) | v4.2.0–v4.4.0 交接（下一块砖均已落地） | 归档 |
| [digest-pre-post-redesign.md](digest-pre-post-redesign.md) | 每日简报「盘前 / 盘后」重构（展示分线 + 运行日 OHLC + ②A/②B 双 profile 二次精选 + ③B 详解） | **done（`v4.13.0`）**；`T3` 顺延 `v4.14.0` |
| [opensource-sanitization.md](opensource-sanitization.md) | 开源化前的私密收束（脱敏、`local/`、配置、tag、历史身份）。平行准备线，不替代下一刀 `T3` | **本地收束 + 远端历史消毒已执行；公开开源发布仍延后** |
| [llm-vs-deterministic-boundary.md](llm-vs-deterministic-boundary.md) | LLM vs 确定性主链边界（实测路径 + 包/导入收口） | **第一刀 done**（ADR [`0088`](../architecture/0088-llm-sidecar-package-boundary.md)）；提供商见 ADR [`0089`](../architecture/0089-llm-provider-selection.md) |
| [next-milestones-t3-cli-y2-fix-r5.md](next-milestones-t3-cli-y2-fix-r5.md) | F1 · T3 · A1 · R5-P · Y2 | F1/T3/A1/R5-P 代码已落；**Y2** 等签核；全量 R5 等生产回补 |
| [multi-strategy-final-board.md](multi-strategy-final-board.md) | 多策略五校 → 硬 Round2 → Final Board → **仅影子账本**；双轨仲裁 A/B；升级走 Y1→Y2 | **MVP 已落**（ADR [`0093`](../architecture/0093-multi-strategy-shadow-board.md)；S1/S2/S5 stub；不改出厂） |

## 与其它文档的关系

- 现行快照：[`../STATUS.md`](../STATUS.md)  
- 历史里程碑叙事：[`../ROADMAP.md`](../ROADMAP.md)  
- 已落地交接：[`../archive/README.md`](../archive/README.md)  
- 上游红线：[`../upstream-archive.md`](../upstream-archive.md)  
- 上游配方摘要：[`../upstream/`](../upstream/)  
