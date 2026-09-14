# packages/execution

纸面执行安全内核。安装名：`stock-platform-execution`。

## 状态

| 版本 | 能力 |
|------|------|
| **M6.1 / v0.6.1** | 信号窗口、事务态、paper-only 闸门、草稿/激活 |
| **M6.2** | Paper ledger：建草稿 / 提交 / 幂等 |
| **M6.3** | workbench `/api/paper/*` |

## 硬规则

1. 默认仅 `SIMULATE`；`liveTradingEnabled` 必须为 `false`。
2. 市场态可推进；执行态仅在纸面接受订单后 commit。
3. 草稿 ≠ 激活；激活需显式调用且哈希一致。
4. 窗口外 / `decision_only` → 零订单，禁止补单。
5. **禁止**接入实盘券商 SDK / 凭据。
6. 纸面 timing / ledger 可选 `market`（CN/US/HK，默认 CN）；见 ADR 0019。

吸收自 V2 审查快照的结论，非整仓拷贝 Futu 路径。
