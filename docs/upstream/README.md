# 上游配方归档（只读）

> **状态**：只读归档副本 / 摘要。  
> **归档日期**：2026-09-22  
> **权威清单**：[`../upstream-archive.md`](../upstream-archive.md)  
> **禁止**：把本文当运行时依赖；禁止 `pip install` 兄弟仓；禁止平行第二数据主链。

本目录存放**与本仓已吸收能力相关**的说明摘要，便于无兄弟仓时也能对照配方来源。完整 Skill / 引擎 / 审查快照仍在 sibling 路径（见总表）。

| 文档 | 来源（典型本地路径） | 吸收进平台的内容 |
|------|----------------------|------------------|
| [a-stock-data-em-get-recipe.md](a-stock-data-em-get-recipe.md) | `../a-stock-data/SKILL.md` | 东财优先级、`em_get` 限流铁律 |
| [global-stock-symbol-semantics.md](global-stock-symbol-semantics.md) | `../global-stock-data/SKILL.md` | US/HK 符号与 Yahoo/新浪格式 |
| [a-stock-engine-lvrev-notes.md](a-stock-engine-lvrev-notes.md) | `../a-stock-engine/README.md` | 分层选股 / 简报口径对照 |
| [tick-stock-panel-notes.md](tick-stock-panel-notes.md) | `../tick-stock-panel/CONTRIBUTING.md` 等 | Provider/能力矩阵语义、回测边界 |
| [tradingagents-roles-notes.md](tradingagents-roles-notes.md) | `../TradingAgents-astock/CLAUDE.md` | 多角色研报思路（禁 dataflows） |
| [v2-execution-safety-notes.md](v2-execution-safety-notes.md) | `../V2-code-review-20260905/README.md` | 纸面执行安全结论（无 Futu） |
| [market-report-dashboard-capability-report.md](market-report-dashboard-capability-report.md) | `../market-report-dashboard/SKILL.md` | 三类 HTML 情报看板 Skill（WebSearch；非运行时） |
| [market-report-templates/](market-report-templates/) | 同上 `templates/` | 三类 HTML **只读配方副本**（Workbench `#intel-report` 可预览） |

Skills 软链治理见 [`../ops/skills-governance.md`](../ops/skills-governance.md)。  
合并里程碑：[`../plans/market-report-dashboard-merge-milestones.md`](../plans/market-report-dashboard-merge-milestones.md)。
