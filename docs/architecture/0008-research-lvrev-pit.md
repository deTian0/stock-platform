# ADR 0008：research 包 — lvrev / PIT / 批处理

- 状态：Accepted
- 日期：2026-09-13

## 背景

a-stock-engine 的 lvrev 与回测需迁入单一产品仓，避免双内核漂移。

## 决策

1. 新建 `packages/research`（`stock-platform-research`）。
2. `score_lvrev` / `apply_entry_gates` 从 engine 迁入并保持权重与闸门语义。
3. `run_pit_long_only`：信号日 T 评分，T+1 open 成交；禁止 fwd/next 特征列。
4. `score_cross_section_csv` + CLI `stock-platform-score` 对接盘前批处理。
5. engine 旧路径标记为参考实现，后续发 ADR 废弃说明（不在本里程碑删仓）。

## 后果

- 工作台 / 简报应依赖本包，不再复制评分公式。
