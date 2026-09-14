# packages/execution

纸面执行安全内核 + SIMULATE broker 端口。安装名：`stock-platform-execution`。

## 状态

| 版本 | 能力 |
|------|------|
| **M6.1 / v0.6.1** | 信号窗口、事务态、paper-only 闸门、草稿/激活 |
| **M6.2** | Paper ledger：建草稿 / 提交 / 幂等 |
| **M6.3** | workbench `/api/paper/*` |
| **M35 / v2.7+** | `BrokerPort` / `PaperBroker` / `resolve_broker` |
| **M36 / v2.8+** | `ThsSimBroker`（默认 mock；HTTP experimental） |
| **M37 / v2.9+** | `GatedBroker` + admission 接到 ths_sim |

## Broker 选择

```text
STOCK_PLATFORM_BROKER=paper          # 默认：内部 PaperLedger
STOCK_PLATFORM_BROKER=ths_sim        # 显式 opt-in：同花顺模拟路径
STOCK_PLATFORM_THS_MODE=mock         # 默认：内存/fixtures，CI 零公网
STOCK_PLATFORM_THS_MODE=experimental # 需 STOCK_PLATFORM_THS_BASE_URL + TOKEN；非生产就绪
```

真实同花顺零售模拟盘 **无稳定公开 HTTP API**；experimental 仅为扩展点（ADR 0037）。

## 硬规则

1. 默认仅 `SIMULATE`；`liveTradingEnabled` 必须为 `false`。
2. 市场态可推进；执行态仅在纸面/模拟接受订单后 commit。
3. 草稿 ≠ 激活；激活需显式调用且哈希一致。
4. 窗口外 / `decision_only` → 零订单，禁止补单。
5. **禁止**接入实盘券商 SDK / 凭据。
6. 纸面 timing / ledger 可选 `market`（CN/US/HK，默认 CN）；见 ADR 0019。
7. 默认 broker=`paper`；`ths_sim` 仅环境变量开启，无「实盘」UI 开关。

吸收自 V2 审查快照的结论，非整仓拷贝 Futu 路径。
