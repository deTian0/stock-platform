# 0076 — 调度执行台账与 brief 连续性守卫（ops run ledger & brief continuity）

- Status: Accepted
- Date: 2026-10-14
- Supersedes: —
- Related: ADR 0073（循环健康度单点）、ADR 0075（循环健康度出口与趋势台账）、
  ADR 0070（日用循环自足 / 供数守卫）、ADR 0058（market.db 只读真相源）、
  ADR 0049（brief 权威）、ADR 0044（日历与调度）

## 背景

`R3` / `T1` 把日用循环的信号聚成一个裁决，并补了出口与趋势面。但裁决回答的是
「循环**现在**健不健康」，**回答不了「任务到底跑没跑」**。这个缺口有真实代价：

```
2026-10-13 / 10-14：market.db 连续两日无 bar、brief 停在 10-12。
排查必须离开平台去翻 Windows 任务计划程序 ——
才发现 18:30 的回补任务压根没注册。
```

平台内**没有任何结构化的「任务执行痕迹」入口** ⇒「是任务没跑，还是跑了没成」
无法自证；`latestBrief` 也对**中间缺日**完全无感（最新两条是 `10-09` / `10-12`，
之间若有缺日照样报 `ok`）。两件事都必须有各自的观测面。

## 决定

### 1. 新增 `research.ops_ledger` 单点（append-only 台账）

`packages/research/src/stock_platform_research/ops_ledger.py`：

| 函数 | 职责 |
|---|---|
| `record_run(*, task, exit_code, …)` | **唯一写**：向 `data/logs/runs.jsonl` **追加**一行；**fail-open**（写失败返回 `recorded=False` + `reason`，绝不拖垮被调度的任务）；`task` 为空直接拒绝；超 `RUNS_MAX_RECORDS`（400）裁最旧 |
| `read_runs(path)` | 读台账（追加序 = 时间序，最旧在前）；文件不存在 → `[]`；**读失败向上抛**（调用方 fail-closed）；坏行跳过 |
| `summarize_runs(records, *, recent_limit, failure_threshold)` | **纯函数**：逐任务给最近一次 `ts`/`exitCode`/`durationSec`/`asof`、`runs` 次数、**连续失败次数**、`lastOk`；汇总 `failingTasks`（连续失败 ≥ 阈值）+ `recent` |
| `collect_ops_ledger(*, path, recent_limit)` | 段形状出口（供 `loop_health` 消费）；台账缺失 → `status="unavailable"`（fail-closed，**不假装有记录**）；读失败 → `unavailable` + `reason` |
| `render_ops_ledger_markdown(payload)` | 人读版（结论先行 + 逐任务表 + 最近执行表） |
| `task_label` / `task_planned_at` / `default_ops_ledger_dir` / `default_ops_ledger_path` | 展示名与路径解析（`STOCK_PLATFORM_OPS_LEDGER_DIR` 优先，否则 `./data/logs`） |

`TASK_SCHEDULES` 登记已知任务（`daily` 08:30 盘前选股 / `postmarket` 15:30 盘后台账 /
`marketdb-backfill` 18:30 行情回补），**只用于展示**（中文名 + 计划时刻），不参与判定；
未知任务名原样展示（台账要能容纳将来新增的任务）。

### 2. 写入口：调度包装器 `scripts/ops/Invoke-ScheduledRun.ps1`

调度任务**不再直接**调 `Invoke-DailyPipeline.ps1` / `Invoke-MarketDbBackfill.ps1`，
而是统一经这层薄包装器：

| 项 | 决定 |
|---|---|
| 职责 | 从**任务预设**解析目标脚本与规范参数（参数不会漏）→ 在**子进程**中运行目标（目标自己的 `exit` 无法绕过本层，因此**总能记到一行**）→ 追加一条台账 |
| 预设 | `daily` / `postmarket` / `marketdb-backfill`；未登记任务**必须显式给 `-Script`**，否则拒绝（`exit 2`），不臆造 |
| 记台账 | `best-effort`：记失败**只报告、绝不改退出码** —— 记账问题不该让它所观测的任务失败 |
| 退出码 | **原样透传**目标退出码（包装器透明） |
| `TargetArgs` | **空格分隔的字符串**（非数组）——`powershell -File` 会把 `-Name a,b` 当**一个** token 传，数组参数会静默退化成一个参数 |

台账**只写平台自有 `data/`**，**绝不写 `market.db` / 平台库**（承接 ADR 0058 只读）。

### 3. `loop_health` 新增两路信号（T2）

`packages/research/src/stock_platform_research/loop_health.py`：

| 段 | 决定 |
|---|---|
| `briefContinuity` | 近 `window_days`（默认 **5**）个**交易日**（走 `providers.calendar`，非自然日）的 brief 覆盖；`end_day` 取 `coverage.latestTradeDate`（无供数则退化体检 `asof`）；**缺日逐个列出**（`missingDays`）+ `coverageRatio`；`status ∈ {ok, incomplete, empty, unavailable}` |
| `opsLedger` | **只读** `collect_ops_ledger()` 原样透传（台账写入端在别处，本模块不写）；`status ∈ {ok, empty, unavailable}` |

### 4. 两路信号**只降级、不阻断**

裁决规则（写入契约 §5）：`briefContinuity` 的 `unavailable`/`empty`/缺日，
`opsLedger` 的 `unavailable`/`empty`/`failingTasks` 非空 → 都判 **warn** ⇒ `degraded`，
**永不 `blocked`**。理由：这两路是**观测面**信号 —— 缺 brief 日或任务连续失败说明
**流水线本身出问题**，但过去的日子已经跑完、当日仍能选股，没有「物理上选不出票」
那种硬前提，故只降级不阻断（与 `coverage` 的 hard-fail 不同档）。

### 5. 出口同步

- API `GET /api/ops/loop-health` 的响应模型 `LoopHealthResponse` 增加 `briefContinuity` / `opsLedger`；
- Workbench `#health` 面板增两行 `kv`（brief 连续性 / 调度执行台账）；
- CLI `stock-platform-loop-health` 增 `--ops-ledger` / `--ops-recent` / `--brief-window`；
- 新增 CLI `stock-platform-ops-ledger`（`--record` 写；默认读并写 `data/health/ops_ledger.{json,md,html}`）。

## 后果

- **正面**：诊断链闭合 —— 从「裁决 degraded」到「哪个任务没跑 / 哪几天缺 brief」
  平台内可自证，不再需要人工翻任务计划程序；`failingTasks` 把「跑了没成」与
  「压根没跑」分开。
- **代价**：`research` 包再引入**一处文件写**（`ops_ledger` 的台账），与 T1 的
  `history.jsonl` 并列；已用本文 + 契约 [`ops-ledger`](../contracts/ops-ledger.md) 双重显式化，
  并有测试锁定 fail-open、裁剪、坏行容忍、`unavailable` 语义与「常量与 `loop_health` 对齐」。
- **风险**：调度任务**必须改经包装器**才能被记录 —— 未改的旧任务台账会缺行。
  缓解：`collect_ops_ledger` 对缺失/为空如实报 `unavailable`/`empty`，不假装正常；
  三个既有自动化（盘前 / 盘后 / 回补）已切到包装器。
- **测试**：`packages/research/tests/test_ops_ledger.py`（记录往返 / 裁剪 / 坏行 /
  失败段 / 目录解析 / 渲染 / CLI）+ `test_loop_health.py` §10（连续性 / 裁决 warn-不阻断 /
  常量对齐 / 段读取）+ `apps/workbench/tests/test_ops_loop_health.py`（连续失败降级但仍 200）。

## 不做的事

- **不写 `market.db` / 平台库**：除平台自有 `data/` 台账外无任何写动作。
- **不抓数、不回补**：只如实报告任务执行与 brief 覆盖；回补本身归
  `Invoke-MarketDbBackfill.ps1`（平台外动作）。
- **不做告警推送**：通知属 T 域后续里程碑。
- **不改任何选股 / 回测 / 绩效口径**：台账只记录事实，不参与任何算术。
- **不替代** ADR 0070 的 ops asof 回落守卫：那是在**写 brief 之前**防伤害，本台账是**事后**认伤害。
