# M-D5：global 薄补缺口（合规分级）

> **状态**：done（文档薄补；2026-09-18）  
> **范围**：对照 + 明确暂缓项；**不**接线期权 / SEC / FINRA。  
> **权威**：`packages/providers` 矩阵；US/HK 不得套用 A 股 T+1/涨跌停。

## 1. 矩阵现状（薄）

| 能力 | CN | US/HK (`global_http` / `global_replay`) | 备注 |
|------|----|------------------------------------------|------|
| `daily` / `realtime` | 有 | **有** | Yahoo chart + Sina；preset `us_hk_global_http` |
| `financial` | 有（新浪三表） | **未声明** | 候选薄补；勿默用 CN 报表字段 |
| `fund_flow` / `lhb` / `unlock` / `concept_blocks` | 有 | **无**（candidates 不含 global_*） | A 股结构产品；美港勿硬套 |
| 期权 / SEC / FINRA | — | **明确不做** | 深水区 |

## 2. 本刀结论

1. **不扩矩阵新 id**（避免半成品 live）。  
2. 文档冻结：美港缺 `financial` 时角色/UI **fail-closed**，禁止用 CN `financial` 冒充。  
3. 下一刀若接线 US/HK `financial`：先契约 ADR + replay fixtures + 合规字段分级，再进矩阵。

## 3. 验收

- 本文与 M-D1 表一致；pytest 仍断言 global_http 不出现在 CN 专属能力 candidates。  
- 无平行 Skill 运行时 / 无 dataflows。

## 4. 交叉链

- [m-d1-capability-gap-matrix.md](../../.cursor/plans/m-d1-capability-gap-matrix.md)  
- [ADR 0014](../architecture/0014-global-http-live.md) · [capability-matrix](../contracts/capability-matrix.md)
