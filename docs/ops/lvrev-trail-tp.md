# lvrev `trail_tp` 生产 opt-in（ADR 0094）

> **状态**：Accepted（opt-in，**出厂默认关**）  
> **ADR**：[`../architecture/0094-lvrev-trail-tp-exit.md`](../architecture/0094-lvrev-trail-tp-exit.md)  
> **证据**：[`../plans/lvrev-enhancement.md`](../plans/lvrev-enhancement.md)（四条预登记标准全过；N=5 有多重比较偏差）  
> **红线**：不改库 `ExitPolicy()` 默认；不引入 live；改出厂默认须**另开 ADR + 全量回测**。

## 规则（白话）

峰值收益 ≥ **+8%** 后，自峰值回撤 ≥ **5%** 即离场；**不受** `min_hold` 限制。理由串 `trail_tp(...)`。出厂硬止损 −8% 与其余分支顺序不变。

## 推荐启用（生产日循环）

在跑盘前/盘后流水线的**同一进程环境**设：

```powershell
$env:STOCK_PLATFORM_LVREV_TRAIL_TP = "1"
```

或写入仓库根 `.env`（**勿提交**；CLI 会按 dotenv 契约加载）：

```text
STOCK_PLATFORM_LVREV_TRAIL_TP=1
```

真值：`1` / `true` / `yes` / `on`（大小写不敏感）。显式 API 参数优先于环境变量。

### 调度任务怎么开

Task Scheduler 任务本身不内置该开关。任选其一：

1. **用户环境变量**（当前用户或系统）：`STOCK_PLATFORM_LVREV_TRAIL_TP=1`，然后照常跑已注册的 `stock-platform-daily` / `postmarket`。  
2. **包装一层**：在调用 `Invoke-ScheduledRun.ps1` / `Invoke-DailyPipeline.ps1` 前先 `$env:STOCK_PLATFORM_LVREV_TRAIL_TP='1'`。  
3. **回测 / 研究 CLI**：`run_portfolio_backtest(..., trail_tp=True)` 或设同一环境变量后跑 `stock-platform-lvrev-enhancement` 等。

不改 `scripts/ops/*-daily.xml` 预设、不改 `TASK_PRESETS` 默认参数——保持「库默认关、生产显式开」可回滚。

### 开启后影响什么

| 路径 | 是否读 `STOCK_PLATFORM_LVREV_TRAIL_TP` |
|------|----------------------------------------|
| `run_portfolio_backtest`（lvrev 组合回测） | **是**（`resolve_trail_tp`） |
| 日循环 ③B `holdingsReview`（有持仓 JSON 时） | **是**（与回测同一 `evaluate_exit`） |
| `stock-platform-position-review` | 默认仍 `ExitPolicy()`；需显式传策略或设环境变量后经库函数 `ExitPolicy(trail_tp=resolve_trail_tp())` |
| 选股 / brief / picks 账本 / 影子终榜默认 | **否**（入口与席位不变） |
| 执行层 / 券商 | **否**（仍 SIMULATE；无 live） |

## 回滚

1. 删掉环境变量 / `.env` 行，或设 `STOCK_PLATFORM_LVREV_TRAIL_TP=0`。  
2. 不传 `trail_tp=True`。  
3. **无需改代码、无需发版**：出厂默认即关。

回滚后 ③B 与回测退出理由回到出厂分支（无 `trail_tp(...)`）。

## 改出厂默认（禁止本轮擅自做）

须同时满足：

1. 用户明确签核；  
2. **另开 ADR 修订**（本 ADR 0094 只覆盖 opt-in 开关）；  
3. 用真实 `market.db` **全量回测**，且 [`lvrev-enhancement.md`](../plans/lvrev-enhancement.md) §2 四条预登记标准仍全过；  
4. 更新 [`../contracts/trading-rules.md`](../contracts/trading-rules.md) 出厂叙述 + CHANGELOG。

## 交叉链

- WorkBuddy 操作员清单：[`workbuddy-runbook.md`](workbuddy-runbook.md) §1  
- 调度：[`scheduler.md`](scheduler.md) · 日流水线：[`daily-pipeline.md`](daily-pipeline.md)  
- 现行快照：[`../STATUS.md`](../STATUS.md)
