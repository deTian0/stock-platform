# ADR 0010：MarketStrategy 与美港 Vendor

- 状态：Accepted
- 日期：2026-09-13

## 背景

美港不得套用 A 股 T+1 交易限制与涨跌停板。global-stock-data 为技能文档参考，平台内需可测的策略表与离线 Vendor。

## 决策

1. `MarketStrategy` 表驱动：`CN` / `US` / `HK`（时区、会话、settle、limit）。
2. `normalize_symbol(..., market=)` 分市场；CN 路径继续拒绝港美形态。
3. `GlobalReplayProvider` 仅读 fixtures；`global_http` 注册为 pending。
4. 工作台/回测只依赖 `get_market_strategy`，禁止散落 `if market ==`。

## 后果

- 节假日日历仍为工作日 stub，live 日历随 Vendor 后续补。
- 完整全球 HTTP 抓取不进本里程碑。
