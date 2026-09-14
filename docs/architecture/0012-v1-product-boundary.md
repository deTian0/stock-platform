# ADR 0012：v1.0 产品边界

- 状态：Accepted
- 日期：2026-09-14

## 背景

M0–M6 已将数据、研究、Agent、纸面执行收敛进单一仓。需要冻结「何为 v1.0 可发布」与「何为明确不做」。

## 决策

1. **v1.0 交付面**：可安装的 `providers` / `research` / `agents` / `execution` + FastAPI `workbench`；契约与 ADR 齐全；CI 绿；上游归档说明齐全。
2. **默认运行时**：CN/US/HK replay fixtures；东财 live 与全球 live 保持 pending。
3. **执行**：仅纸面 SIMULATE；无 live 配置面。
4. **版本**：自 `1.0.0` 起，破坏契约必须 MAJOR，并写迁移说明（见 `versioning.md`）。
5. **上游**：`docs/upstream-archive.md` 为权威；禁止把参考仓当第二产品主链。

## 后果

- v1.0 不是「全市场 live 行情 SaaS」；是可扩展研究与纸面决策平台骨架。
- live Vendor、完整 Agent 辩论图、实盘适配可作为 1.x minor 规划，不阻塞 1.0。
