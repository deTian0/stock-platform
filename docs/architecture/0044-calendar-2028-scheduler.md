# ADR 0044：日历 2028+ 与调度运维包

- 状态：Accepted
- 日期：2026-09-14

## 背景

静态休市表止于 2027；M40 日流水线已有 CLI，但缺少可复制的 Task Scheduler / cron
运维包，以及非交易日跳过逻辑。

## 决策

1. **日历格式不变**：继续 `packages/providers/.../data/{cn,us,hk}_closed_days.txt`
   （`#` 注释 + `YYYY-MM-DD` 工作日休市一行一个；周末由 `TradingCalendar` 排除）。
2. **覆盖延伸**：CN/US/HK 休市表追加 **2028 全年 + 2029 初** curated provisional
   条目；国务院 / 交易所正式通知发布后只改 txt。
3. **运维包**：`scripts/ops/Invoke-DailyPipeline.ps1` 读日历，非交易日 exit 0；
   Task Scheduler XML + cron 示例调度该包装脚本，默认 **replay**。
4. **文档**：`docs/ops/scheduler.md` + `docs/ops/calendar-maintenance.md`；
   健康观察继续用 `/api/ops/health` 与 `briefs/latest.json`。
5. **不做**：改加载 API、默认 live、入库密钥、后台守护进程。

## 后果

- 加载路径与 ADR 0015 / 0018 兼容；发版前核对 provisional 年份即可。
- M40 CLI 保持不变；调度层负责 skip。
