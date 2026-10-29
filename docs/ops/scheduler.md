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
| `-PrevSession` | asof 解析为**前一交易日**（T-1 收盘截面；见下「为什么 asof 是前一交易日」） |
| `-Digest` | 流水线成功后渲染人读日报（`data/digests/` **Markdown + HTML**），并产出同花顺导入 `data/ths_import/latest.txt` |
| `-Session pre\|post` | 展示用会话。08:30 用 `pre`，15:30 用 `post`。不改变 asof（仍是 T-1）。digest 另收显式运行日，不猜今天 |
| `-StrictCoverage` | 覆盖率不可用时**不回退**、直接失败（验收 / 取证用） |
| `-Holdings <path>` / `-NoHoldings` | 持仓 JSON（③A 持仓 / ③B 操作建议）；**默认自动探测** `data\holdings.json`，`-NoHoldings` 显式跳过 |

> **供数覆盖率守卫（`v4.4.0`，ADR [`0070`](../architecture/0070-daily-loop-self-sufficiency.md)）**：
> 跑流水线**之前**复用 C2 单点 `EngineSqliteProvider.coverage_snapshot()` 校验解析出的 `asof`
> ——**可用** → 照常；**不可用** → **回落到 `latestTradeDate` 并 WARN**（用一份更旧但真实的截面）；
> **回落目标也不可用**（或库里没有任何可用交易日）→ **退出 1，拒绝写 brief**；`-StrictCoverage`
> → 不回退、直接失败。守卫只防「静默写空」：空 brief 的 asof 最新，会**遮蔽**上一份真 brief，
> 让日报显示「当日无推荐」而真相是「数据没到」。守卫让 asof **不再是严格 T-1**（供数滞后时更旧）
> —— 报表里的 asof 就是真 asof，不撒谎。

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

1. `scripts/ops/stock-platform-daily.xml` 已含 `-MarketDb -PrevSession -SettleAfter -Digest -Session pre` 快路径、`WorkingDirectory`、`ExecutionTimeLimit=PT15M`、每日 08:30 触发；按需改 `WorkingDirectory` 为你的仓库绝对路径。`-SettleAfter` 与盘后任务**同一个** T-1 `asof`、写入幂等 ⇒ 两处都有是**冗余**，任一成功即入账（ADR [`0079`](../architecture/0079-settle-after-on-premarket.md)）。`-Session` 只区分展示，不改 asof（ADR [`0083`](../architecture/0083-digest-pre-post-and-secondary-pick.md)）。
2. `scripts/ops/stock-platform-postmarket.xml` 是盘后 15:30 任务（`-MarketDb -PrevSession -SettleAfter -Digest -Session post`，`ExecutionTimeLimit=PT30M`）。
3. `scripts/ops/stock-platform-marketdb-backfill.xml` 是**行情回补**任务（每日 **18:30**，`ExecutionTimeLimit=PT20M`）：调用 `Invoke-MarketDbBackfill.ps1`，包一层**引擎自己的** `empirical/backfill_market_daily.py`（幂等：只补行数 < 3000 的交易日，`INSERT OR REPLACE`，严格顺序 + 调用间隔，CPU-safe）。**边界不变**：写库的是引擎脚本、平台仅只读（ADR [`0058`](../architecture/0058-market-db-source-of-truth.md)）。
4. 确认 `.env` 里有 `STOCK_PLATFORM_ENGINE_MARKET_DB`（指向 `market.db` 绝对路径）。
5. 注册（**推荐用包装脚本**，幂等可重跑，无需管理员）：

```powershell
cd D:\workspace\stock_trading\stock-platform
.\scripts\ops\Register-ScheduledTasks.ps1            # 注册三个任务（daily / postmarket / backfill）
.\scripts\ops\Register-ScheduledTasks.ps1 -Status    # 查看注册状态 / 上次运行结果
.\scripts\ops\Register-ScheduledTasks.ps1 -RunNow    # 注册后立即触发（验证用）
.\scripts\ops\Register-ScheduledTasks.ps1 -Backfill  # 只注册 / 触发回补任务
.\scripts\ops\Register-ScheduledTasks.ps1 -Unregister
```

或手动导入（管理员或当前用户）：

```powershell
cd D:\workspace\stock_trading\stock-platform
Register-ScheduledTask -TaskName 'stock-platform-daily' `
  -Xml ([System.IO.File]::ReadAllText('.\scripts\ops\stock-platform-daily.xml') -replace '^\s*<\?xml[^>]*\?>\s*','') -Force
```

或：任务计划程序 → 导入任务 → 选该 XML。

样例触发：每日 08:30 / 15:30；真正是否执行由包装脚本读日历决定（周末/法定休市跳过）。

### 两个注册坑（2026-10-12 实测）

| 坑 | 现象 | 规避 |
|----|------|------|
| PS 5.1 编码 | `Get-Content -Raw` 把 UTF-8 无 BOM 的 XML 按 ANSI(GBK) 解码，中文 Description 乱码 → `任务 XML 格式错误` | 用 `[System.IO.File]::ReadAllText()`（`Register-ScheduledTasks.ps1` 已内置） |
| `-Xml` 参数拒绝编码声明 | `(1,40)::错误: 无法切换编码` | 注册前剥掉 `<?xml … ?>` 声明（文件里保留，供 GUI 导入） |

### PrevSession：为什么 asof 是前一交易日

market.db 由生产侧**晚间**回补，08:30 / 15:30 时点**绝无当日 bar**——直接用今天会得到空面板
（实测 asof=2026-10-12 brief `panelSize=0` 的废档即此因）。`-PrevSession` 让包装脚本用
`TradingCalendar` 把 asof 解析为**前一交易日**（T-1 收盘截面 = 正确的 PIT 选股时点）。

> **「今天跑出来的日报还是昨天的日期」不是故障**（`v4.11.2`）。asof = **数据基准日**（该日收盘截面），
> 不是运行日；10-16 08:30 跑出来的 `asof=2026-10-15` 正是当日选股要用的 T-1 截面。为免误读，digest
> 现在会在标题下自证口径（数据基准日 + 生成时刻，本机时区），HTML 抬头同步显示 —— 见下「用户可读日报」。
> 想要 **asof=当天** 的简报，需等 18:30 回补完成后另跑一次（不带 `-PrevSession`）。

## 用户可读日报（digest）

每日流水线成功后自动渲染人读版日报（`-Digest`），**Markdown + 同主题 HTML 双份**（ADR [`0071`](../architecture/0071-report-html-theme.md)）：

- CLI：`stock-platform-digest [--asof YYYY-MM-DD] [--session pre|post] [--run-date YYYY-MM-DD] [--out-dir ...] [--no-html] [--no-ths] [--ths-dir ...] [--no-ohlc]`。`--run-date` 必须显式传入；不传则不猜今天，盘前/缺运行日时开盘、收盘、涨跌为 `—`。
- 产物：`data/digests/{reportDay}-pre.md` 与 `{reportDay}-post.md` **都保留**（html 同理）。`{reportDay}.md` / `{reportDay}.html` 与 `latest.md` / `latest.html` 是**最后一次成功渲染的别名**（拷贝，不是第三套正文）。另有 `latest-pre.*` / `latest-post.*`。主题对齐 `static/report-templates/`，深色 + A 股红涨绿跌；`--no-html` 可只留 Markdown。同花顺文件名同样是 `{reportDay}.txt`（**生产榜**）；另有 `{reportDay}_quality_sec.txt` / `{reportDay}_short_sec.txt` 导出二次精选（ADR [0084](../architecture/0084-secondary-pick-import-blocks.md)）。
- 内容：环境/数据源/宇宙概览、**长线 + 短线双代码块**（见下）、当日推荐表（**代码/名称**/综合分/收盘/理由）、五榜概览、命中追踪（X3 单点渲染）、绩效台账计数
  - **口径自证行（`v4.11.2`）**：标题下固定输出一行 `> **口径**：数据基准日（asof）YYYY-MM-DD —— 取该交易日收盘截面；本简报生成于 YYYY-MM-DD HH:MM:SS +08:00 …`，把「数据日」与「运行日」并列写出，避免 asof 被误读成「报告过期」。`生成时间` 也改按**本机时区**渲染（UTC 存档值保留在括号内）
  - **同花顺导入行（`v4.5.1`；`v4.11.1` 起双线各一块）**：**长线**（当日推荐 / ②A 质量榜）与**短线**（②B 短线榜）**各给一块可整块复制**的 6 位代码行，直接粘进同花顺手机版「自选 → 导入」。**手机版一次仅支持导入 5 只**，故按 5 只/行分组（`THS_IMPORT_PER_LINE = 5`）；代码归一化为 6 位裸码（去 `.SZ` / `.SH`）、按推荐序去重、仅保留合法 6 位码；某条线无有效代码则该块整块省略（fail-closed）。`v4.13.3` 起**二次精选另出两块**：`同花顺导入 · 二次精选（长线）` / `（短线）`（ADR [0084](../architecture/0084-secondary-pick-import-blocks.md)）
  - **同花顺导入文件（`v4.5.2`；`v4.11.1` 起双文件；`v4.13.3` 起四文件）**：生产榜两条线各落一份 —— 长线 `data/ths_import/{reportDay}.txt` + `latest.txt`，短线 `data/ths_import/{reportDay}_short.txt` + `latest_short.txt`；二次精选另落 `{reportDay}_quality_sec.txt` + `latest_quality_sec.txt`、`{reportDay}_short_sec.txt` + `latest_short_sec.txt`（每行 1 个 6 位码、无表头无名称），供同花顺「导入自选 → 选择文件」直接导入（用户实测 txt 通道可用）。目录默认取 digest 目录的**同级** `ths_import`（`--ths-dir` 可覆盖）；某条线无代码则不产出该文件（fail-closed），并顺带清理目录内遗留的 `*.sel`（项目已统一只用 txt）
  - **名称（`v4.4.0`）**：读 `fundamentals.name`（`load_engine_names`，**fail-open**），key 归一到 6 位核；**装饰性、可缺省** —— 取不到名就不写 `name` 键（brief / ledger / 命中 / 绩效 JSONL 逐字节不变）
- 数据源：**权威 SQLite brief 仓库**（ADR 0049），绝不并行解析 JSON 导出；查无 brief 时 fail-closed 输出占位说明，不编造数字

## cron

见 `scripts/ops/cron-daily.example`。推荐每日调用包装脚本，由日历决定 skip：

```text
# 30 8 * * * cd /path/to/stock-platform && pwsh -NoProfile -File ./scripts/ops/Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Digest -Session pre

# 30 15 * * * cd /path/to/stock-platform && pwsh -NoProfile -File ./scripts/ops/Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Digest -Session post
```

（cron 行里的 `&&` 仅出现在 Linux crontab 示例中；Windows PowerShell 运维脚本本身不使用 `&&`。）

## 健康观察

调度失败或产物过期时，可用：

```powershell
Invoke-RestMethod http://127.0.0.1:3018/api/ops/health
```

关注 `marketDb` 覆盖裁决（`ok` / `thin` / `stale` / `empty` / `missing_table`，见 ADR [`0058`](../architecture/0058-market-db-source-of-truth.md)）、brief 指针文件 `{out}/briefs/latest.json`（见 [daily-pipeline.md](daily-pipeline.md)）与 `Register-ScheduledTasks.ps1 -Status` 的 `lastResult`。

`liveTradingEnabled` 恒为 false。
