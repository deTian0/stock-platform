# ADR 0015：CN 静态交易日历

- 状态：Accepted
- 日期：2026-09-14

## 背景

`MarketStrategy.is_trading_day` 与纸面 `timing.next_weekday` 仅跳过周末，国庆/春节等休市日会把 T+1 执行日算错。

## 决策

1. providers 提供 `TradingCalendar` / `get_trading_calendar(market)`。
2. CN：静态文件 `data/cn_closed_days.txt`（仅工作日休市；周末由代码排除），覆盖 2024–2027。
3. US/HK：weekday stub（本里程碑不引入 NYSE/HKEX 假日表）。
4. 零公网：不拉取 Tushare/交易所 API；后续年份靠人工更新 txt。
5. execution 依赖 providers，共用同一日历，禁止再复制休市表。

## 后果

- 2026–2027 在国务院正式通知发布前为 curated provisional，发版后可只改 txt + patch。
- `completed_bar_cutoff` / `planned_execution_date` 与 `MarketStrategy.is_trading_day` 口径一致。
