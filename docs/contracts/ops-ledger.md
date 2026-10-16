# 契约：调度执行台账（Ops Run Ledger）

> 里程碑 **T2 调度与回补执行台账 + brief 连续性守卫**（`v4.9.1`）·
> 代码单点：`packages/research/src/stock_platform_research/ops_ledger.py`
> CLI：`stock-platform-ops-ledger` · 写入端：`scripts/ops/Invoke-ScheduledRun.ps1`
> 相关 ADR：[0076](../architecture/0076-ops-run-ledger-and-brief-continuity.md)（T2 决定）·
> [0073](../architecture/0073-daily-loop-health-single-point.md)（循环健康度单点）·
> [0075](../architecture/0075-loop-health-export-and-history.md)（T1 出口与趋势台账）·
> [0058](../architecture/0058-market-db-source-of-truth.md)（market.db 只读真相源）·
> [0070](../architecture/0070-daily-loop-self-sufficiency.md)（供数守卫）·
> 消费方契约：[loop-health](loop-health.md) §4.8

## 1. 目的

回答「**任务到底跑没跑**」，并回答「**跑了没成，还是压根没跑**」。

把**调度执行痕迹**落成一条 append-only 台账（`data/logs/runs.jsonl`），
给出每个任务**最近一次的时刻 / 退出码 / 耗时**、**连续失败次数**与最近 N 次执行。
本契约定义**台账格式**、**写入语义**、**失败判定**与**读写规则**；
`loop_health` 对它的消费口径见 [loop-health](loop-health.md) §4.8。

## 2. 硬约束（不可协商）

| 约束 | 含义 |
|------|------|
| **零网络** | 本模块不发布任何 HTTP 请求 |
| **只读行情** | 不触碰 `market.db`；台账只写平台自有 `data/` |
| **写入端唯一** | 本模块的**唯一写**是 `record_run`；写入端只有调度包装器与 CLI `--record` |
| **fail-open（写）** | 写失败 → `{"recorded": false, "reason": …}`，**绝不**拖垮被调度的任务 |
| **fail-closed（读）** | 台账缺失 / 读失败 → `status="unavailable"` + `reason`，**绝不**假装有记录 |
| **永不抛（对外入口）** | `record_run` / `collect_ops_ledger` 是 total function；`read_runs` 读失败向上抛（由调用方降级） |
| **不改口径** | 台账只记录事实，不参与任何选股 / 回测 / 绩效算术 |
| **单向依赖** | 本模块**不 import** `loop_health`（避免循环导入）；`SECTION_*` 常量本模块自持，有测试钉住与 `loop_health` 同字面量 |

## 3. 台账格式（`data/logs/runs.jsonl`）

**JSON Lines**，每行一条，**追加**（最旧在前，文件顺序 = 时间序）：

```
{"ts": "<ISO8601>", "task": "marketdb-backfill", "plannedAt": "18:30",
 "startedAt": "<ISO8601|null>", "endedAt": "<ISO8601|null>",
 "exitCode": 0, "durationSec": 42.315, "asof": "YYYY-MM-DD|null", "note": "<str|null>"}
```

| 字段 | 含义 |
|------|------|
| `ts` | 记录时刻（缺省 = `endedAt` 或当前 UTC；**同刻可直接当时间序键**） |
| `task` | 任务名（= 台账主键；**为空拒绝记录**） |
| `plannedAt` | 计划时刻（`HH:MM`）；缺省回落到 `TASK_SCHEDULES` 登记值 |
| `startedAt` / `endedAt` | 起止时刻（可缺） |
| `exitCode` | 目标退出码；非整数 → 记为 `-1` |
| `durationSec` | 耗时（秒，保留 3 位）；缺省 `null` |
| `asof` | 本次针对的交易日（取前 10 字符） |
| `note` | 备注（可缺） |

## 4. 已知任务登记表 `TASK_SCHEDULES`

**只用于展示**（中文名 + 计划时刻），**不参与判定**；未知任务名原样展示（不报错）——
台账要能容纳将来新增的任务。

| `task` | `label` | `plannedAt` | 包装器预设参数 |
|--------|---------|-------------|----------------|
| `daily` | 盘前选股 | `08:30` | `Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Digest` |
| `postmarket` | 盘后台账 | `15:30` | `Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Digest` |
| `marketdb-backfill` | 行情回补 | `18:30` | `Invoke-MarketDbBackfill.ps1 -Mode apply` |

> `daily` 与 `postmarket` 都带 `-SettleAfter`：两个任务用**同一个** T-1 `asof`，写入幂等
> （`log_brief_decisions(..., skip_existing=True)`），所以是**冗余**而非重复——任一任务成功即入账，
> 消除「盘后漏跑一次则该日推荐永久丢失」的单点（2026-10-14 事故，ADR 0079）。

## 5. 写入语义（`record_run`）

- **追加**（不是覆盖）：执行痕迹必须保留每次运行；
- **`task` 为空 → 拒绝**（记一条无名记录没有意义），以 fail-open 形式返回 `recorded=false`；
- **目录自动创建**（`<dir>` 不存在则 `mkdir -p`）；
- **裁剪**：超过 `RUNS_MAX_RECORDS`（=400 行）时裁掉最旧部分（裁失败不算错误）；
- **fail-open**：上述任一步抛异常 → 返回 `recorded=false` + `reason`，**不影响** `exit_code`
  （包装器按 best-effort 处理：只报告、不改退出码）。

**目录解析**：`STOCK_PLATFORM_OPS_LEDGER_DIR` 优先，否则 `./data/logs`；文件名固定 `runs.jsonl`。

## 6. 读取与汇总语义

### 6.1 `read_runs(path)`

- 文件不存在 → `[]`；**读失败向上抛**（由调用方标 `unavailable`，fail-closed）；
- **坏行跳过而不抛**（非 JSON / 缺 `task`）—— 单行损坏不该让整条台账消失。

### 6.2 `summarize_runs(records, *, recent_limit, failure_threshold)`（**纯函数**）

- 逐任务：`task` / `label` / `plannedAt` / `runs`（次数）/ `lastRunAt` / `lastExitCode` /
  `lastOk` / `lastDurationSec` / `lastAsof` / **`failureStreak`**（从最新往回数的连续失败次数）；
- `failingTasks`：`failureStreak ≥ failure_threshold` 的任务名（**说出口的那一条**）；
- `failureThreshold` 默认 `OPERATIONAL_FAILURE_STREAK`（=**2**：1 次可能是偶发抖动，2 次就该说出口）；
- `recent`：最近 `recent_limit`（默认 `DEFAULT_RUNS_RECENT`=12）次执行（新→旧）；
- `status`：有记录 → `ok`；无有效行 → `empty`（附 `reason`）。

**失败判定**：`exitCode != 0`（或不可解析为整数）即为失败；`exitCode == 0` 为成功。

### 6.3 `collect_ops_ledger(*, path, recent_limit)`（段形状，**永不抛**）

| 情形 | `status` |
|------|----------|
| 台账文件不存在 | `unavailable` + 中文 `reason`（首次调度运行后建立） |
| 文件存在但无有效行 | `empty` |
| 读失败 | `unavailable` + `reason` |
| 有记录 | `ok` + 完整汇总（+ `path`） |

## 7. 出口

| 出口 | 说明 |
|------|------|
| **CLI（写）** | `stock-platform-ops-ledger --record --task … --exit-code … [--started-at … --ended-at … --planned-at … --duration-sec … --asof … --note …]`；**退出码恒 0**（记账不构成门禁） |
| **CLI（读，默认）** | `stock-platform-ops-ledger [--ledger … --recent N --out-dir … --json-out … --out … --html-out … --no-write --json]` → 默认写 `data/health/ops_ledger.{json,md,html}` |
| **写入端（生产）** | `scripts/ops/Invoke-ScheduledRun.ps1 -Task <id>` —— 调度任务统一入口；台账仅 `best-effort`，退出码原样透传目标 |
| **消费方** | `loop_health` 作为一路 `opsLedger` 信号（[loop-health](loop-health.md) §4.8），**只读** |
| **库** | `stock_platform_research` 顶层导出 `record_run` / `read_runs` / `summarize_runs` / `collect_ops_ledger` / `render_ops_ledger_markdown` / `default_ops_ledger_dir` / `default_ops_ledger_path` / `task_label` / `task_planned_at` / `TASK_SCHEDULES` / `OPS_LEDGER_FILENAME` / `ENV_OPS_LEDGER_DIR` / `DEFAULT_OPS_LEDGER_OUT_DIR` / `DEFAULT_RUNS_RECENT` / `RUNS_MAX_RECORDS` / `OPERATIONAL_FAILURE_STREAK` / `SECTION_OK` / `SECTION_EMPTY` / `SECTION_UNAVAILABLE` |

## 8. 计划时刻与跳号说明

- 计划时刻是**登记表口径**（`HH:MM`），仅用于展示「应跑时刻」；实际时刻以记录的 `ts` 为准。
- **跳号说明**：本里程碑编 `v4.9.1`（patch，加固），承接 `v4.9.0`（T1）；
  `v4.8.0`（`R5` ETF 进宇宙）因**生产侧 ETF 回补未完成**而顺延，按完成顺序直接编号。

## 9. 边界（本契约**不做**的事）

- **不做告警推送**：通知属 T 域后续里程碑（T3 及以后）。
- **不做跨机同步**：台账是本机 `data/` 下的本地文件。
- **不做生产侧回补**：回补本身归 `Invoke-MarketDbBackfill.ps1`（平台外动作）。
- **不参与任何算术**：台账只记录事实；选股 / 回测 / 绩效口径一概不受影响。
