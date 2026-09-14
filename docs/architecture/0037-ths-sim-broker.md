# ADR 0037：同花顺模拟盘适配器（mock / experimental）

- 状态：Accepted
- 日期：2026-09-14

## 背景

调研（2026-09）：同花顺**无**面向散户的稳定公开「模拟盘下单 OpenAPI」。
官方路径偏 iFinD（机构数据）与 SuperMind/MindGo（平台内策略），
不可作为可嵌入的 HTTP 柜台 API。逆向/进程 Hook 方案不采用。

## 决策

1. 实现 `ThsSimBroker`（`ExternalSimBroker`），默认 `STOCK_PLATFORM_THS_MODE=mock`。
2. `MockThsTransport` + fixtures：CI **零公网**，可完成 auth / place / positions / fills。
3. `ExperimentalThsHttpTransport`：缺 `STOCK_PLATFORM_THS_BASE_URL` /
   `STOCK_PLATFORM_THS_TOKEN` **fail-closed**；无注入 `get_json` 时明确
   `pending/experimental`，**不宣称生产就绪**。
4. 仅当 `STOCK_PLATFORM_BROKER=ths_sim` 时启用；不在 UI 提供「像实盘」的开关。
5. 密钥永不入库；`.env.example` 仅占位名。

## 后果

- 真实 THS HTTP wire-up 保持扩展点，待官方/合规 API 出现后再接。
- 优先交付可工作的 mock E2E，而非脆弱爬虫。
