# 调度运维包：Task Scheduler / cron

> Phase E / M42 · ADR [0044](../architecture/0044-calendar-2028-scheduler.md)  
> 流水线手跑与产物：[`daily-pipeline.md`](daily-pipeline.md)  
> 日历维护清单：[`calendar-maintenance.md`](calendar-maintenance.md)

默认 **paper + replay + SIMULATE**；样例不启用 liveTrading，不入库密钥。

## 包装脚本

`scripts/ops/Invoke-DailyPipeline.ps1`：

1. 解析 `--asof`（默认本机今天，或 `-Asof`）。
2. 用 `TradingCalendar`（默认 CN）判断是否交易日。
3. **非交易日**：打印 `SKIP`，**退出码 0**（调度器不算失败）。
4. **交易日**：调用 `stock-platform-daily`（默认 `--provider replay` + fixtures）。

| 参数 / 环境变量 | 说明 |
|-----------------|------|
| `-Asof` | `YYYY-MM-DD`；省略则用今天 |
| `-Market` | `CN` / `US` / `HK`（默认 CN） |
| `-Fixtures` / `STOCK_PLATFORM_FIXTURES` | replay fixtures；默认 `packages/providers/tests/fixtures` |
| `-Out` / `STOCK_PLATFORM_REFRESH_DIR` | 落盘根；默认 `%TEMP%\stock-platform-daily` |
| `-SkipRefresh` | 传给 CLI |
| `-Force` | 休市日仍跑（仅排障） |

手跑示例：

```powershell
cd D:\workspace\git\stock-platform
python -m pip install -e .\packages\providers -e .\packages\research
.\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-03
# → SKIP（元旦调休工作日休市）exit 0

.\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-05 -SkipRefresh
# → 交易日则跑 stock-platform-daily
```

## Windows Task Scheduler

1. 编辑 `scripts/ops/stock-platform-daily.xml` 里的 `WorkingDirectory` 为你的仓库绝对路径。
2. 可选：`Command` 用 `powershell.exe`（已默认）或 `pwsh.exe`；确认 PATH 含 `python` 与 `stock-platform-daily`。
3. 导入（管理员或当前用户）：

```powershell
cd D:\workspace\git\stock-platform
$xml = Get-Content -Raw .\scripts\ops\stock-platform-daily.xml
Register-ScheduledTask -TaskName 'stock-platform-daily' -Xml $xml
```

或：任务计划程序 → 导入任务 → 选该 XML。

样例触发：每日 08:30；真正是否执行由包装脚本读日历决定（周末/法定休市跳过）。

## cron

见 `scripts/ops/cron-daily.example`。推荐每日调用包装脚本，由日历决定 skip：

```text
30 8 * * * cd /path/to/stock-platform && pwsh -NoProfile -File ./scripts/ops/Invoke-DailyPipeline.ps1 -SkipRefresh
```

（cron 行里的 `&&` 仅出现在 Linux crontab 示例中；Windows PowerShell 运维脚本本身不使用 `&&`。）

## 健康观察

调度失败或产物过期时，可用：

```powershell
Invoke-RestMethod http://127.0.0.1:3018/api/ops/health
```

关注 `lastRefresh`（若配置了 refresh 落盘）以及 brief 指针文件：

`{out}/briefs/latest.json`（见 [daily-pipeline.md](daily-pipeline.md)）。

`liveTradingEnabled` 恒为 false；默认 `defaultReplay=true`。
