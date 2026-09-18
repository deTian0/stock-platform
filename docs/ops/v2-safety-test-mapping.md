# V2 安全用例对照表（M-E1）

> **状态**：done（文档；2026-09-18）  
> **范围**：对照 only；**不恢复 Futu / OpenD**；缺口按优先级排队进 M-E2。  
> **源**：`V2-code-review-20260905/source/tests/`（只读快照）  
> **平台**：`packages/execution`（SIMULATE / PaperLedger / BrokerPort）

## 对照原则

1. 吸收**测试意图**（暂停、哈希、幂等、决策草稿、窗口、事务），不吸收 `futu-api`。  
2. 平台默认 `environment=SIMULATE`、`liveTradingEnabled=false`。  
3. 「纸面/草稿 ≠ 激活」须显式：`decisionOnly` / lifecycle stage。

## 映射表

| V2 测例（文件 / 意图） | 平台已有 | 缺口 / 备注 | 优先级 |
|------------------------|----------|-------------|--------|
| `test_execution_safety` · paused cycle 不进执行 | `GatedBroker` / profile 门禁；runner 未迁入 | 无独立「全局 pause」开关单测 | P2 |
| `test_execution_safety` · pause + hash mismatch 阻断 | `lifecycle` hash；`PaperLedger` strategyHash | 对齐良好；补「错哈希阻断」显式用例 | P1 |
| `test_execution_safety` · append-only 幂等 | `IdempotentReplay` / `execute_draft` 二次调用 | **已有** `test_paper_safety` | — |
| `test_execution_safety` · decision-only 草稿剥订单 | `decisionOnly` + `DraftBlocked` | **已有** | — |
| `test_execution_safety` · fee / min order 门槛 | `admission` / profile execution 字段部分 | 费用倍数门槛用例可加强 | P2 |
| `test_strategy_lifecycle_and_timing` · hash 稳定 / 改规则失效 | `strategy_hash` / `StrategyLifecycle` | **已有** lifecycle 测 | — |
| `test_strategy_lifecycle_and_timing` · 未收盘 bar + 执行窗 | `timing.execution_window_status` / `completed_bar` | **已有** `test_timing` | — |
| `test_transactional_execution` · pending rebalance / 事务态 | `transactional` 包 | **已有** `test_transactional`；语义对照即可 | P2 |
| `test_futu_paper_*` · Futu 纸面 / OpenD | **明确不做** | 不迁入；禁止依赖 | — |
| `test_v2_fee_upgrade` · 费用升级门槛 | 部分在 admission | 文档诚实性 + 补测 → M-E2 | P2 |
| `test_scheduler_reliability` · 调度可靠性 | 运维文档 / Task Scheduler | 非 execution 内核；ops 对照 | P3 |
| `test_performance_observability` | research `performance` | 口径已是 `direction_accuracy`；非券商 | — |

## 明确不迁

- `futu-api`、OpenD、双轨 `data_service`。  
- 真实同花顺 HTTP / 实盘开关（仍 Later / M-E4）。  
- 宣称 production 实盘。

## 下一步（M-E2）

1. P1：错哈希 / 错 strategyHash 阻断的轻量回归用例（若尚未覆盖边角）。**done** → `packages/execution/tests/test_me2_safety_gaps.py`  
2. P2：费用门槛与 pause 语义补测（仍 SIMULATE）— order_guards fail-closed 已补；全局 pause 仍 P2 余量。  
3. 保持 `docs/ops` 诚实：experimental ≠ 生产。
