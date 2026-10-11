# 调度运维包：Task Scheduler / cron

> Phase E / M42 · ADR [0044](../architecture/0044-calendar-2028-scheduler.md)  
> 取数吞吐与 `.env` 加载契约：[`refresh-throughput.md`](../contracts/refresh-throughput.md) · [`dotenv-loading.md`](../contracts/dotenv-loading.md)（`v4.1.6`）  
> 流水线手跑与产物：[`daily-pipeline.md`](daily-pipeline.md)  
> 日历维护清单：[`calendar-maintenance.md`](calendar-maintenance.md)

默认 **paper + SIMULATE**；样例不启用 liveTrading，不入库密钥。

## 两条路径

| 路径 | provider | 取数 | 端到端实测 | 用途 |
|---|---|---|---|---|
| **快路径（推荐）** | `market_db` | 本机 `market.db` 一趟 SQL（**零 HTTP**） | **14.78 s**（`-MarketDb`） | 每日盘前/盘后自动化 |
| **replay 路径** | `replay` | fixtures（跳过 refresh） | 秒级 | 离线排障 / CI / 无本机库 |

> `v4.1.6` 之前 `run_refresh` 走**串行 HTTP**，全市场外推约 **3 小时** → 08:30 盘前窗口不可行。快路径把取数降为一次 `bulk_daily` SQL（契约 [`refresh-throughput.md`](../contracts/refresh-throughput.md)）。

## 包装脚本

`scripts/ops/Invoke-DailyPipeline.ps1`：

1. **venv 优先**：若 `<repo>\.venv\Scripts\python.exe` 存在则用它，否则回落到 PATH 上的 `python`。
2. 解析 `-Asof`（默认本机今天）。
3. 用 `TradingCalendar`（默认 CN）判断是否交易日。
4. **非交易日**：打印 `SKIP`，**退出码 0**（调度器不算失败）。
5. **交易日**：调用 `stock-platform-daily`。
   - **`-MarketDb`**（推荐）：`--provider market_db` + `--universe-source market_db` + `--no-refresh-persist`，需 `STOCK_PLATFORM_ENGINE_MARKET_DB`（或 CLI 的 `--market-db`）。
   - 否则：默认 `--provider replay` + fixtures。

| 参数 / 环境变量 | 说明 |
|-----------------|------|
| `-Asof` | `YYYY-MM-DD`；省略则用今天 |
| `-Market` | `CN` / `US` / `HK`（默认 CN） |
| `-MarketDb` | **切到快路径**：`provider=market_db`、`universe-source=market_db`、`--no-refresh-persist` |
| `-Provider` | 显式 provider；缺省读 `STOCK_PLATFORM_DAILY_PROVIDER`，再缺省 `replay` |
| `-Universe` | `--universe`（显式宇宙文件） |
| `-Fixtures` / `STOCK_PLATFORM_FIXTURES` | replay fixtures；默认 `packages/providers/tests/fixtures` |
| `-Out` / `STOCK_PLATFORM_REFRESH_DIR` | 落盘根；默认 `%TEMP%\stock-platform-daily` |
| `-SkipRefresh` / `-SettleAfter` / `-LiveDay` | 传给 CLI（`-LiveDay` = tushare + `-SkipRefresh` + `-SettleAfter`） |
| `-Force` | 休市日仍跑（仅排障） |

> **快路径需要 `STOCK_PLATFORM_ENGINE_MARKET_DB`**：`-MarketDb` 让 CLI 用 `--provider market_db`，而 `market_db` provider 要求 `--market-db` 或该环境变量指向 `market.db` 绝对路径。CLI 会自动从仓库根 `.env` 读到它（`P0-2`）。

> **`.env` 自动加载（`P0-2`）**：CLI 会自行加载仓库根 `.env`，**不需要**调度器 `export` 环境变量（契约 [`dotenv-loading.md`](../contracts/dotenv-loading.md)）。若调度器**显式**注入 `STOCK_PLATFORM_*`，以注入值为准（`override=False`）。

手跑示例：

```powershell
cd D:\workspace\stock_trading\stock-platform
.\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-03
# → SKIP（元旦调休工作日休市）exit 0

# 快路径（真机每日自动化；~15 s）
.\scripts\ops\Invoke-DailyPipeline.ps1 -MarketDb

# 离线排障
.\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-05 -SkipRefresh
```

## Windows Task Scheduler

1. `scripts/ops/stock-platform-daily.xml` 已含 `-MarketDb` 快路径、`WorkingDirectory`、`ExecutionTimeLimit=PT15M`、每日 08:30 触发；按需改 `WorkingDirectory` 为你的仓库绝对路径。
2. 确认 `.env` 里有 `STOCK_PLATFORM_ENGINE_MARKET_DB`（指向 `market.db` 绝对路径）。
3. 导入（管理员或当前用户）：

```powershell
cd D:\workspace\stock_trading\stock-platform
$xml = Get-Content -Raw .\scripts\ops\stock-platform-daily.xml
Register-ScheduledTask -TaskName 'stock-platform-daily' -Xml $xml
```

或：任务计划程序 → 导入任务 → 选该 XML。

样例触发：每日 08:30；真正是否执行由包装脚本读日历决定（周末/法定休市跳过）。

## cron

见 `scripts/ops/cron-daily.example`。推荐每日调用包装脚本，由日历决定 skip：

```text
30 8 * * * cd /path/to/stock-platform && pwsh -NoProfile -File ./scripts/ops/Invoke-DailyPipeline.ps1 -MarketDb
```

（cron 行里的 `&&` 仅出现在 Linux crontab 示例中；Windows PowerShell 运维脚本本身不使用 `&&`。）

## 健康观察

调度失败或产物过期时，可用：

```powershell
Invoke-RestMethod http://127.0.0.1:3018/api/ops/health
```

关注 `marketDb` 覆盖裁决（`ok` / `thin` / `stale` / `empty` / `missing_table`，见 ADR [`0058`](../architecture/0058-market-db-source-of-truth.md)）以及 brief 指针文件：

`{out}/briefs/latest.json`（见 [daily-pipeline.md](daily-pipeline.md)）。

`liveTradingEnabled` 恒为 false。
