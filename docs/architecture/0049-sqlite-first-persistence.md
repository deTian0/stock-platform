# ADR 0049：SQLite 先行持久化（PostgreSQL 为后续目标）

- 状态：Accepted（U2 已落地实现）
- 日期：2026-09-15

## 背景

Usable 线（U2 brief 落库、U3 复盘等）需要**真实可用**的持久化，不能只靠当次 HTTP 或仅 JSON 文件。本机日用优先零运维；后续再迁到 PostgreSQL。

## 决策

1. **现阶段默认存储：SQLite**。U2/U3 权威存档走 SQLite；连接串/路径用环境变量 `STOCK_PLATFORM_DB_URL`（例 `sqlite:///./data/stock_platform.db`）。
2. **PostgreSQL 为后续迁移目标**，不在本阶段上线。
3. **极薄存储接口（或单一 repository）**：业务 / 路由只调接口；SQLite 方言与连接细节留在适配层，便于日后换 PG 驱动而不改策略与 UI。
4. **JSON 文件**：可选导出或与 M40 目录兼容，**不是**权威真相源的唯一形态。
5. **Git**：不提交 `*.db` / `*.sqlite`（仓库 `.gitignore` 已覆盖）；密钥与 token 仍禁止入库。

## 实现（U2 / v3.10.2）

| 项 | 约定 |
|----|------|
| 模块 | `stock_platform_research.persistence`（`BriefRepository` / `SqliteBriefRepository`） |
| 表 | `daily_briefs`（`asof` UNIQUE；同日 regenerate **幂等覆盖**） |
| 字段 | asof、provider、universe_tier、symbols、picks JSON、soft_gates、gates_relaxed、data_note、generated_at、environment=SIMULATE、完整 payload |
| 入口 | Workbench：`GET /api/research/brief` 默认 `persist=true`；`GET/POST /api/research/briefs`；日批 `run_daily_pipeline(persist_db=True)` 共用同一 writer |
| 禁止 | payload 不得写入 token / apiKey |

## 非目标

- 不做完整迁移框架（Alembic 多后端、双写、自动 schema 漂移工具链）。
- 不做「现在就上 ORM + 多数据库抽象」的大搬家；表结构保持简单、可文档化即可。

## 后果

- U2/U3 实现与验收以 SQLite + repository 为准；单测用临时库/内存库。
- 将来切 PG 时优先替换适配层与连接串，业务语义与 schema 文档保持连续。
- 计划真相源：[`docs/plans/usable-recommend-review-milestones.md`](../plans/usable-recommend-review-milestones.md) §2.1。
