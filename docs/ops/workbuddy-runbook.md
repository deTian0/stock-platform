# WorkBuddy 操作员 / 自动化 runbook

> **给谁看**：本机 **WorkBuddy**（外部助手 / 自动化会话）操作员，以及按清单触发本仓 CLI 的人。  
> **WorkBuddy 是什么**：仓外助手环境（含 westock / MCP 桥、会话限额）。**不是**本仓业务组件。仓内相关：行情桥 `stock-platform-workbuddy-bridge`、LLM 默认 `workbuddy`（进程内不打商业模型）、限额见 [`workbuddy-runtime-limits.md`](workbuddy-runtime-limits.md)。  
> **SSOT**：各操作细节仍在下列专题文；**本文只汇总「何时跑 / 怎么跑 / 看哪」**，不写第二份长文。

## 总览

| # | 操作 | 何时 | 命令入口 | 专题 |
|---|------|------|----------|------|
| 1 | `trail_tp` 观察 | 生产日循环进程环境常开 | `$env:STOCK_PLATFORM_LVREV_TRAIL_TP='1'` | [`lvrev-trail-tp.md`](lvrev-trail-tp.md) |
| 2 | midday 简报 | 工作日 **11:30**（已自动化） | `stock-platform-digest --session midday` | [`midday-digest.md`](midday-digest.md) |
| 3 | 模拟买卖 | 演示 / 纸面闭环（随时） | `stock-platform-paper …` | [`paper-cabin.md`](paper-cabin.md) |
| 4 | aux 增量 | 定期（建议每周或盘后） | `stock-platform-aux-market` | [`aux-market.md`](aux-market.md) |
| 5 | 影子日结 | 盘后或与日循环配套；攒前向样本 | `-ShadowBoard` + `--settle-daily` | [`shadow-board.md`](shadow-board.md) |

工作目录一律仓库根：`D:\workspace\stock_trading\stock-platform`（或本机等价路径）。PowerShell 多句用 `;` 连接。优先 `.venv`：

```powershell
cd D:\workspace\stock_trading\stock-platform
$py = if (Test-Path .\.venv\Scripts\python.exe) { .\.venv\Scripts\python.exe } else { "python" }
```

## 禁止事项（硬）

| 禁止 | 说明 |
|------|------|
| live / 实盘开关 | 执行层默认 SIMULATE；`liveTradingEnabled=false`；不引入 live 券商 |
| 写 / 改 `market.db` | 引擎库只读；补数走引擎回补任务，平台不得写 |
| 同花顺真盘 / 真实模拟盘 | 已放弃；模拟买卖只用本仓 `stock-platform-paper` |
| 改出厂默认 | 不改 `ExitPolicy()`、不改影子库默认、不擅自改版本号 / 打 tag |
| 提交密钥与大数据 | 不提交 `.env`、行情缓存、`local/`、SQLite 大数据 |
| 用 `schtasks.exe` 装 midday | midday **不**进仓库调度 XML；WorkBuddy 沙箱也禁 `schtasks.exe`（见限额文） |

长命令（可能 >120s）：WorkBuddy 侧须 `run_in_background` **且**显式 `timeout`（PowerShell 上限 600000 ms），见 [`workbuddy-runtime-limits.md`](workbuddy-runtime-limits.md)。

---

## 1. 生产日循环设 `STOCK_PLATFORM_LVREV_TRAIL_TP=1`（观察）

**目的**：opt-in 开启 lvrev 峰值回撤止盈观察；**代码 / 库默认仍关**。

```powershell
# 当前会话（跑盘前/盘后流水线前）
$env:STOCK_PLATFORM_LVREV_TRAIL_TP = "1"

# 或写入 local/.env（勿提交）
# STOCK_PLATFORM_LVREV_TRAIL_TP=1
```

| 项 | 值 |
|----|-----|
| 真值 | `1` / `true` / `yes` / `on` |
| 回滚 | 删变量或设 `0`；无需改代码 |
| 影响 | 组合回测 + 有持仓时 ③B；**不**改选股 / 影子默认 / 执行层 |
| 失败怎么看 | ③B / 回测退出理由无 `trail_tp(...)` → 环境未生效；查进程是否继承 `.env` |

专题：[`lvrev-trail-tp.md`](lvrev-trail-tp.md) · 调度交叉：[`scheduler.md`](scheduler.md)。

---

## 2. 工作日 11:30 午间简报（自动化，可手跑）

**目的**：午间休盘简报（现价列）；**不**装仓库 schtask。

> **2026-11-09 起自动**：WorkBuddy 自动化「stock-platform 午间简报」每个工作日 11:30 触发，先查交易日历再跑 CLI。下列命令是等价手跑，用于补跑 / 排障。

```powershell
cd D:\workspace\stock_trading\stock-platform
$day = Get-Date -Format "yyyy-MM-dd"
stock-platform-digest --session midday --run-date $day
```

| 项 | 值 |
|----|-----|
| 何时 | CN 交易日 11:30（WorkBuddy 自动化触发）；休市自动跳过；需补跑时手跑 |
| 产物 | `local/digests/{day}-midday.md`（及 html / `latest-midday.*`；路径随本机 `local/` 配置） |
| 失败怎么看 | 缺 `--run-date` → 行情列 `—`；东财分钟失败 → 三列 `—` 但 digest 仍成功；非交易日可 skip |
| 禁止 | 不要用 `date.today()` 猜运行日；不要注册 midday 进 `Register-ScheduledTasks.ps1` |

专题：[`midday-digest.md`](midday-digest.md) · 计划 [`../plans/midday-session.md`](../plans/midday-session.md) §1.1。

---

## 3. `stock-platform-paper` 模拟买卖

**目的**：本仓纸面买卖闭环（推荐模拟主路径）。

```powershell
stock-platform-paper demo
stock-platform-paper buy --symbol 600519 --qty 100 --price 1800 `
  --signal-date 2026-09-04 --now 2026-09-07T09:40:00+08:00
stock-platform-paper positions
stock-platform-paper account
stock-platform-paper fills --limit 10
stock-platform-paper sell --symbol 600519 --all --price 1810 `
  --signal-date 2026-09-04 --now 2026-09-07T09:40:00+08:00
```

| 项 | 值 |
|----|-----|
| 产物 | `local/paper_cabin/state.json`（可用 `--state` 覆盖） |
| 行情 | `--price` 或只读 `--db` / `STOCK_PLATFORM_ENGINE_MARKET_DB` |
| 失败怎么看 | 闸门拒绝（信号日未完成 / 窗口未开 / 草稿过期）→ 注入合法 `--now`；无 live 开关可开 |
| 禁止 | `STOCK_PLATFORM_BROKER=ths_sim` 当真盘；伪造成交 |

专题：[`paper-cabin.md`](paper-cabin.md)。

---

## 4. 定期 `stock-platform-aux-market` 增量

**目的**：刷新平台补充库指数日线（超额可算）；**不**写 `market.db`。日循环 settle **不**读此库。

```powershell
# 默认 5 指数；幂等 upsert；建议定期增量（--start 可收到近窗）
stock-platform-aux-market --start 2020-01-01
# 先看计划（零网络）
stock-platform-aux-market --dry-run --json
```

| 项 | 值 |
|----|-----|
| 何时 | 建议每周或盘后；超额报告前必须较新 |
| 产物 | `local/aux_market/aux_market.db`（`STOCK_PLATFORM_AUX_MARKET_DB`） |
| 预算 | 默认日预算 60（`STOCK_PLATFORM_AUX_MARKET_EM_BUDGET`）；超限记 `budget_exceeded` |
| 失败怎么看 | 单代码失败 fail-soft（看 stdout `status`/`reason`）；名称不匹配拒写；`--db` 不得指向 `market.db` |
| 禁止 | 全市场乱扫；把路径指到引擎 `market.db` |

专题：[`aux-market.md`](aux-market.md) · ADR [`0095`](../architecture/0095-aux-market-store.md)。

---

## 5. 保持影子板日结（`-ShadowBoard`）攒前向样本

**目的**：生产盘前/盘后已带 `-ShadowBoard` 写终榜 + pending；定期结算前向账本，攒够 `MIN_MEANINGFUL_SAMPLE` 再谈采纳。

> **2026-11-09 起自动**（ADR [`0097`](../architecture/0097-holdings-single-source-and-post-close.md)）：18:30 回补任务在 `-Mode apply` 成功后自动跑 `--settle-daily`（及 `loop-health`），所以本节通常**无需手跑**；手跑只用于补历史或排障。

```powershell
# A) 确认调度预设仍含 -ShadowBoard（盘前 08:30 / 盘后 15:30）
#    见 scripts/ops/stock-platform-daily.xml · postmarket.xml
#    手跑等价：
.\scripts\ops\Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Digest -ShadowBoard -Session post

# B) 日结影子前向账本（pending → settled；只读 market.db）
stock-platform-shadow-board --settle-daily
stock-platform-shadow-board --perf-summary
```

| 项 | 值 |
|----|-----|
| 产物 | `local/shadow/final_board_*.json`、`shadow_decisions.jsonl`、S2 快照等 |
| 回滚影子链 | 预设去掉 `-ShadowBoard`，或单次 `-NoShadowBoard`（库默认本就关） |
| 失败怎么看 | 主链 brief 仍应成功（影子异常只 warn）；`loop_health.shadowBoard`；账本无新行 → 查当日是否空榜 / 未开 `-ShadowBoard` |
| 禁止 | 把影子账本混进主绩效 JSONL；未 `adopt` 改出厂 lvrev |

专题：[`shadow-board.md`](shadow-board.md) · [`scheduler.md`](scheduler.md) · 契约 [`../contracts/multi-strategy-shadow.md`](../contracts/multi-strategy-shadow.md)。

---

## 环境变量速查

| 变量 | 用途 | 默认 |
|------|------|------|
| `STOCK_PLATFORM_LVREV_TRAIL_TP` | trail_tp 观察 | 关 |
| `STOCK_PLATFORM_ENGINE_MARKET_DB` | 只读引擎库 | （本机 `.env`） |
| `STOCK_PLATFORM_SHADOW_BOARD` / `-ShadowBoard` | 日循环影子链 | 库关；生产调度已开 |
| `STOCK_PLATFORM_SHADOW_DIR` | 影子根 | `local/shadow` |
| `STOCK_PLATFORM_AUX_MARKET_DB` | 补充库路径 | `local/aux_market/aux_market.db` |
| `STOCK_PLATFORM_LLM_PROVIDER` | LLM；日用 `workbuddy` | `workbuddy` |

dotenv：优先 `local/.env`，见 [`../contracts/dotenv-loading.md`](../contracts/dotenv-loading.md)。

## 交叉链

- CLI 一览：[`cli-catalog.md`](cli-catalog.md)  
- 日流水线 / 调度：[`daily-pipeline.md`](daily-pipeline.md) · [`scheduler.md`](scheduler.md)  
- LLM / 行情桥：[`llm-providers.md`](llm-providers.md) · ADR [`0067`](../architecture/0067-workbuddy-mcp-bridge.md)  
- 现行快照：[`../STATUS.md`](../STATUS.md)
