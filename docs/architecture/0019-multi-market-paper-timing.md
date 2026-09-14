# ADR 0019：多市场纸面 timing

- 状态：Accepted
- 日期：2026-09-14

## 背景

M13 已提供 CN/US/HK 静态日历，但 `timing.py` / `PaperLedger` 仍写死 CN 时区与 `15:05` 日 K 收盘缓冲，美港假日与本地墙钟无法用于纸面执行计划。

## 决策

1. 所有 timing 助手增加 `market: str = "CN"`（经 `get_market_strategy` 校验）；缺省仍 CN。
2. `market_now` 使用 `zoneinfo.ZoneInfo(strategy.timezone)`（US 正确处理夏令时）；`china_now` / `CHINA_TZ` 保留为 CN 别名。
3. `daily_bar_final_at(market)` = 该市场会话**最后一段 end** + 5 分钟（CN `15:05`；US/HK `16:05` 本地）。半日市不建模。
4. `planned_execution_date` / `next_weekday` / `completed_bar_cutoff` / `execution_window_status` / `signal_bar_is_completed` 一律按 `market` 取日历与本地钟。
5. 默认交易窗仍 `09:35-10:00`（市场本地时）；不改 SIMULATE / 禁实盘闸门。

## 后果

- 纸面调用方可显式传 `market="US"|"HK"`；未传则行为与 M13 前一致。
- 半日市 / 提前收盘 / 实盘仍不在本里程碑范围。
