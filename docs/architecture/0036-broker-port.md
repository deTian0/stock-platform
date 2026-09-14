# ADR 0036：执行 Broker 端口抽象（SIMULATE）

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase D 需要把推荐执行从「唯一 PaperLedger」扩展到可选外部**模拟**盘，
同时默认行为与纸面安全模型不得回退。

## 决策

1. 引入 `BrokerPort`：`build_draft` / `execute_draft` / `status` /
   `get_positions` / `get_orders` / `get_account` / `get_fills`。
2. 契约：`OrderIntent` / `Fill` / `Position` / `AccountSnapshot`。
3. `PaperBroker` 包装既有 `PaperLedger`；为默认路径。
4. `ExternalSimBroker` 为外部模拟 Protocol（仍 `environment=SIMULATE`）。
5. 工厂 `resolve_broker()` 读取 `STOCK_PLATFORM_BROKER=paper|ths_sim`（默认 `paper`）。
6. **禁止** `liveTradingEnabled=true`；不引入实盘券商 / OpenD / Futu。

## 后果

- workbench 经 `PaperRuntime.broker` 调用；`ledger` 属性仍可访问（兼容）。
- 同花顺适配见 ADR 0037。
