# ADR 0018：US/HK 静态交易日历

- 状态：Accepted
- 日期：2026-09-14

## 背景

M10 仅固化 CN 休市日；US/HK 仍为 weekday stub，Independence Day / 港股农历新年会被误判为交易日。

## 决策

1. 新增 `us_closed_days.txt` / `hk_closed_days.txt`（仅工作日休市，2024–2027）。
2. `get_trading_calendar` 按市场加载对应文件；`MarketStrategy.is_trading_day` 继续委托日历。
3. 零公网；不改 execution 默认 CN timing。
4. 2026–2027 在交易所正式通知前为 curated provisional。

## 后果

- 美港假日口径与 CN 同机制维护（改 txt + patch）。
- 半日市 / 提前收盘不在本里程碑建模（全日闭市表即可）。
