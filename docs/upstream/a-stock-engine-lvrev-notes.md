# a-stock-engine：分层选股 / 简报口径摘要

> **只读归档** · 归档日：2026-09-22  
> **来源**：`../a-stock-engine/README.md`  
> **平台权威**：`packages/research`（lvrev / 闸门 / PIT / brief）、[`../architecture/0008-research-lvrev-pit.md`](../architecture/0008-research-lvrev-pit.md)  
> **引擎仓**：冻结新功能；缺陷优先修平台。`market.db` 只读挂载见 [`../ops/engine-market-db.md`](../ops/engine-market-db.md)、ADR 0050。

## 上游分层（对照用）

上游 README 描述的过滤链（L0 环境 → L2 基础过滤 → L4 多因子评分 → 质量/短线榜与持仓建议）是**历史配方**。  
平台实现为可库化的 lvrev + 入场/风险闸门 + PIT 截面 + `stock-platform-brief` / daily 管道，**不是**整仓拷贝 `daily_brief.py`。

## 已吸收 / 对照点

| 上游概念 | 平台位置 |
|----------|----------|
| 盘前简报 | research brief / workbench 今日推荐 |
| T+N 验证思路 | recommend performance / rolling review（`direction_accuracy`） |
| SQLite 行情库 | `EngineSqliteProvider` 只读；与 brief SQLite 分离（ADR 0049） |
| PIT 基本面表 | ADR 0050 只读暴露 |

实证基线对照（无双调度）：[`../ops/empirical-baseline-compare.md`](../ops/empirical-baseline-compare.md)。
