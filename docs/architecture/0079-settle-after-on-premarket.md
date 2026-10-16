# 0079 — 盘前任务也带 `-SettleAfter`：推荐入账去单点

- Status: Accepted
- Date: 2026-10-16
- Supersedes: —
- Related: ADR 0068（绩效 PnL 闭环）、ADR 0070（日用循环自足）、ADR 0049（brief 权威档案）、
  ADR 0076（执行台账）、ADR 0058（market.db 只读真相源）

## 背景

推荐样本的入账（写 `data/recommend_decisions.jsonl`）此前**只挂在盘后任务上**：

| 任务 | 触发 | 包装器预设参数 |
|------|------|----------------|
| `daily`（盘前选股） | 08:30 | `-MarketDb -PrevSession -Digest` |
| `postmarket`（盘后台账） | 15:30 | `-MarketDb -PrevSession -SettleAfter -Digest` |

`-SettleAfter` 才调 `_settle_after_pipeline`（`daily_cli.py`）→ `log_brief_decisions` + `settle_performance_log`。
**两个任务用的是同一个 T-1 `asof`**（都带 `-PrevSession`），也就是说盘前那次运行本已具备入账所需的
一切条件，只是没带开关。

后果是一个**单点失效**：只要某天的 15:30 盘后没跑成，**那一天 `asof` 的推荐就永久丢失**——
次日盘前的 `asof` 已推进到新的 T-1，不会回头补。

真机实证（2026-10-16 体检）：

- `data/logs/runs.jsonl` **没有 2026-10-15 15:30 的 postmarket 行**（盘后漏跑一次）；
- `data/recommend_decisions.jsonl` 共 33 行，日期只有 `09-02 / 09-22 / 10-09 / 10-12 / 10-15`，
  **缺 `2026-10-14`**（应有 43 行）；
- 同日 `daily` 08:31 成功（`exit=0`）——**它本该顺手把 10-14 的 10 条入账，却因为没带开关而放过**。

## 决定

**把 `-SettleAfter` 同时挂到盘前任务**，让入账有两个独立的成功路径。

改动为 canonical 参数的三处同步（缺一即口径漂移）：

| 位置 | 作用 |
|------|------|
| `scripts/ops/stock-platform-daily.xml` | Windows 任务计划程序实际执行的 `Arguments` |
| `scripts/ops/Invoke-ScheduledRun.ps1` → `TASK_PRESETS['daily'].Args` | 调度包装器预设（台账写入端） |
| `scripts/ops/Register-ScheduledTasks.ps1` 头注 | 注册脚本自述 |

`daily` 的新参数：`-MarketDb -PrevSession -SettleAfter -Digest`。

### 为什么是「冗余」而不是「重复」

两个任务**同一天、同一个 `asof`**，写入是幂等的：

- `log_brief_decisions(..., skip_existing=True)` —— 已存在的 `(date, code)` 不再追加；
- `settle_performance_log` 只报**新**结算数（`settledNewly`），已结算样本不重复计入；
- 两次运行的日线可见范围相同（08:30 与 15:30 时 `market.db` 最新都停在 T-1，当日 K 线要等 18:30 回补），
  所以结算结果不因提前到 08:30 而改变。

⇒ 先跑成的那个任务完成入账与结算，后跑的成为**空操作**。

### 仍不覆盖的情形

两个任务**当天都**没跑（例如机器全天关机）时，该 `asof` 依然拿不回来——那属于「当日循环未运行」，
不在本次修复范围；补救手段是对该 `asof` 显式补录：
`Invoke-DailyPipeline.ps1 -Asof <D> -MarketDb -SettleAfter`（**显式 `-Asof`，不要带 `-PrevSession`**，
否则 `asof` 会被再前移一天）。

## 影响

- **口径不变**：选股口径、`asof` 口径、持有期（`DEFAULT_HOLDING=5d`）与基准（`000905`）全部不动；
  变的只是「哪个任务负责把它写进账本」。
- `A4` / `loop_health.performance` 的样本数会随后续交易日自然增长；`2026-10-14` 的 10 条以补录方式找回。
- 执行台账 `runs.jsonl` 语义不变：仍是一任务一行（`daily` / `postmarket` / `marketdb-backfill`）。
- 边界不变：仍 **SIMULATE**、`liveTradingEnabled=false`、纸面记账；`market.db` 仍只读（ADR 0058）。

## 验证

- `packages/research/tests/test_scheduler_args_contract.py` —— 断言三处 canonical 参数一致，
  且 `daily` 预设必须含 `-SettleAfter`（防止将来只改一处就悄悄回退）。
- 补录 `2026-10-14` 后 `recommend_decisions.jsonl` 出现该日 10 行（33 → 43）。
- `loop_health` 的 `performance` 段样本数随之上升（`待结算` +10）。
