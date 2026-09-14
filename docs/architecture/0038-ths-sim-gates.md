# ADR 0038：外部模拟盘风控闸门

- 状态：Accepted
- 日期：2026-09-14

## 背景

`ths_sim` 仍属 SIMULATE 类路径，必须复用纸面 timing / freshness / window /
idempotency / admission，避免绕过 M6 安全模型。

## 决策

1. `ThsSimBroker` 建草稿/执行前走 `PaperLedger.assert_executable`（与 paper 同闸）。
2. workbench 对 `ths_sim` 包一层 `GatedBroker`（`assert_sim_gates` + admission）。
3. 闸门失败 → refuse；幂等回放仍抛 `IdempotentReplay`。
4. **不做** live 放行；`liveTradingEnabled` 恒 false。

## 后果

- 外部模拟与内部纸面同一安全口径；admission 通过 ≠ 收益已证明。
