# 交易日历维护清单

> Phase E / M42 · 与 ADR [0015](../architecture/0015-cn-trading-calendar.md) /
> [0018](../architecture/0018-us-hk-trading-calendar.md) /
> [0044](../architecture/0044-calendar-2028-scheduler.md) 对齐。

## 文件

| 市场 | 路径 |
|------|------|
| CN | `packages/providers/src/stock_platform_providers/data/cn_closed_days.txt` |
| US | `packages/providers/src/stock_platform_providers/data/us_closed_days.txt` |
| HK | `packages/providers/src/stock_platform_providers/data/hk_closed_days.txt` |

格式：一行一个 `YYYY-MM-DD`；仅列 **周一～周五** 休市；`#` 行为注释。周末不必写。

## 每年 checklist

1. 等国务院放假安排 / SSE·SZSE / NYSE / HKEX 正式公告。
2. 把 provisional 年份改成正式日期；**只保留工作日**（用 Python 校验 `weekday() < 5`）。
3. 追加下一两年 provisional（至少覆盖调度窗口）。
4. 更新文件头注释（哪些年 provisional）。
5. 在 `packages/providers/tests/test_calendar.py` 加/改样例闭市日 + 一个交易日。
6. 跑：`python -m pytest packages/providers/tests/test_calendar.py -q`
7. 不改文件格式或加载逻辑时，无需新 ADR；格式变更走 ADR（见 0044）。

## 调度联动

非交易日跳过逻辑见 [`scheduler.md`](scheduler.md)（`Invoke-DailyPipeline.ps1`）。
日历漏更会导致休市日误跑或交易日误 skip——发版前对一下当年春节/国庆窗口。
