# 契约：日用循环健康度（Loop Health）

> 里程碑 **R3 日用循环健康度单点**（`v4.7.0`）→ **T1 出口与趋势台账**（`v4.9.0`）
> → **T2 执行台账与 brief 连续性**（`v4.9.1`）·
> 代码单点：`packages/research/src/stock_platform_research/loop_health.py`
> CLI：`stock-platform-loop-health` · API：`GET /api/ops/loop-health`
> 相关 ADR：[0073](../architecture/0073-daily-loop-health-single-point.md)（R3 单点）·
> [0075](../architecture/0075-loop-health-export-and-history.md)（T1 出口与台账）·
> [0076](../architecture/0076-ops-run-ledger-and-brief-continuity.md)（T2 执行台账与 brief 连续性）·
> [0058](../architecture/0058-market-db-source-of-truth.md)（market.db 只读真相源）·
> [0049](../architecture/0049-sqlite-first-persistence.md)（brief 权威）·
> [0057](../architecture/0057-hit-tracking.md)（命中追踪）·
> [0068](../architecture/0068-performance-pnl-closed-loop.md)（绩效 PnL）·
> [0070](../architecture/0070-daily-loop-self-sufficiency.md)（供数守卫）·
> [0072](../architecture/0072-symbol-master-name-authority.md)（名称权威）

## 1. 目的

给「今天的日用循环正不正常」一个**唯一只读答案**，并回答「**任务到底跑没跑**」。
把八路信号（供数覆盖率 → 最新 brief → brief 连续性 → 命中 → 绩效 → 名称 → 调度执行 → 下一结算日提示）
的既有信号聚合到一个 payload + 一份人读报告，并给出规则化裁决。

**不重新定义任何段的口径** —— 本契约只定义**聚合方式**、**裁决规则**与**台账格式**；
各段口径归各自契约（执行台账另见 [ops-ledger](ops-ledger.md)）。

## 2. 硬约束（不可协商）

| 约束 | 含义 |
|------|------|
| **零网络** | 本模块不发布任何 HTTP 请求，也不触发 provider 抓数 |
| **只读（库）** | 不写任何库 / 表；`market.db` 由 provider 以 `mode=ro` 打开 |
| **台账例外（唯一写）** | T1 起唯一写动作：向平台自有 `<health-dir>/history.jsonl` **追加一行**。**绝不写 `market.db` / 平台库**。T2 的执行台账由**另一个模块**（`research.ops_ledger`）写 `data/logs/runs.jsonl`，本模块只**读** |
| **fail-closed** | 缺件 → `status="unavailable"` + `reason`；**绝不**用默认值冒充 `ok` |
| **方法永不抛** | 每段独立 try/except 就地降级；`collect_loop_health` 是 total function；`append_history` fail-open |
| **providers 懒导入** | `research` 顶层零 `stock_platform_providers` 依赖（函数内导入） |
| **退出码恒 0** | 体检不是门禁；裁决在 payload `verdict.status` |
| **API 零业务逻辑** | `/api/ops/loop-health` 只转发 `collect_loop_health`，自身不判、不算、不写 |

## 3. Payload 形状（JSON）

```
{
  "environment": "SIMULATE", "liveTradingEnabled": false,
  "asof": "YYYY-MM-DD", "generatedAt": "<ISO8601 UTC>", "holdingDays": 5,
  "verdict": { "status": "ok|degraded|blocked", "failed": [...], "warned": [...],
               "checks": [{"id","level":"ok|warn|fail","detail"}] },
  "coverage":       { ... §4.1 ... },
  "latestBrief":    { ... §4.2 ... },
  "briefContinuity":{ ... §4.7 ... },
  "hits":           { ... §4.3 ... },
  "performance":    { ... §4.4 ... },
  "symbolMaster":   { ... §4.5 ... },
  "opsLedger":      { ... §4.8 ... },
  "nextSettlement": { "available": bool, "entryAsof", "holdingDays",
                      "expectedSettlementDate" | "reason" },
  "history":        { ... §4.6 ... },
  "disclaimer": "..."
}
```

`status` 词表统一为 `ok` / `empty` / `unavailable`，外加各段自身的细分状态
（如 coverage 的 `stale` / `thin` / `missing_table` / `error` / `unconfigured`，
briefContinuity 的 `incomplete`）。

## 4. 段定义

### 4.1 `coverage` —— 供数覆盖率

**复用** `EngineSqliteProvider.coverage_snapshot()`（ADR 0058 / `C2` 单点），
原样透传其字段：`status`（`ok|thin|stale|empty|missing_table|error`）、`latestTradeDate`、
`latestRows`、`lagTradingDays`、`missingDays`、`thinDays`、`message`，并补 `source="engine_sqlite"`。

引擎库不可用（环境变量未指 / 文件不存在）→ `status="unavailable"` + `reason`。
库存在但不可读 → 透传 `error`（若 provider 直接抛则由就地降级给出 `unavailable`）。

### 4.2 `latestBrief` —— 最新归档 brief

来源 `open_brief_repository().list_recent(limit=1)`：`asof` / `pickCount` / `provider` /
`universeTier` / `generatedAt` / `updatedAt`。空库 → `status="empty"`。

### 4.3 `hits` —— 命中记账

对 `HIT_SESSION_TYPES` 每类调 `open_hit_repository().summary(session_type=…)`，
汇总 `codeCount` / `cumulativeHits` / `totalCycles` / `lastPickDate`；
顶层再给 `totalCodeCount` / `totalCumulativeHits` / `lastPickDate`。全空 → `status="empty"`。

### 4.4 `performance` —— 绩效闭环

来源 `performance_summary(perf_log)` + `load_jsonl(perf_log)`：
`totalEntries` / `pendingCount` / `settledCount` / `avgReturn` / `sampleNote` /
`minMeaningfulSample`（=`MIN_MEANINGFUL_SAMPLE`）/ `sampleSufficient` /
`latestSettledDate` / `settledDates` / `holdingDays`。台账空 → `status="empty"`。

> 真实台账之外还有 R4 的**代理台账**（`docs/contracts/performance-proxy.md`）：
> 两者**分栏禁混算**，本段**只读真实台账**。

### 4.5 `symbolMaster` —— 名称主表

来源 `open_symbol_master().stats()`：`total` / `bySource`。`total==0` → `status="empty"`。

### 4.6 `history` —— 趋势面（T1 / `v4.9.0`）

来源 `<health-dir>/history.jsonl`（§8）。

| 字段 | 含义 |
|------|------|
| `status` | `ok`（有历史行）/ `empty`（首次体检）/ `unavailable`（读失败，附 `reason`） |
| `path` | 台账文件路径 |
| `daysRecorded` | **去重后**已记录的天数（**不含本次**，故首跑为 0） |
| `degradedStreak` | 以本次 `asof` 为末尾，**连续** `degraded` 的天数（**含本次**） |
| `blockedStreak` | 同上，连续 `blocked` 的天数（含本次） |
| `notOkStreak` | 同上，连续「非 `ok`」的天数（含本次） |
| `streakSince` | 该连续段的起始 `asof`（无则 `null`） |
| `recent` | 最近 `N`（默认 7）天的 `{asof,status,ts,failed,warned}`，**最新在前** |

**`history` 不参与裁决**：裁决仍只看各路信号的当下快照；趋势只回答
「这次降级是持续还是偶发」。加这一段**不改**任何既有段的语义。

### 4.7 `briefContinuity` —— brief 连续性（T2 / `v4.9.1`）

回答「**brief 是不是按交易日连续产出**」—— 命中 `latestBrief` 看不见的**中间缺日**
（如 `2026-10-13`/`10-14` 无 brief 而最新两条是 `10-09`/`10-12`）。

**窗口锚点**：`end_day` 取 `coverage.latestTradeDate`（有供数才有截面可对照）；
供数不可用时退化为体检 `asof`。往回取 `window_days`（默认 **5**，可用
`brief_window_days` / `--brief-window` 覆盖）个**交易日**（走 `providers.calendar`，非自然日）。

| 字段 | 含义 |
|------|------|
| `status` | `ok`（窗口内无缺日）/ `incomplete`（有缺日）/ `empty`（尚无任何 brief）/ `unavailable`（日历不可用） |
| `windowDays` | 实际窗口长度（交易日） |
| `endDay` | 窗口末端（= `expectedDays[-1]`） |
| `expectedDays` | 应有 brief 的交易日列表（**升序**） |
| `coveredDays` | 其中确实有 brief 的交易日 |
| `missingDays` | **缺日列表（升序，逐个列出）** |
| `coverageRatio` | `coveredDays / expectedDays`（4 位小数） |
| `latestBriefAsof` | 窗口内（不限）最新一条 brief 的 `asof` |
| `reason` | 缺日 / 空 / 不可判定时的中文说明 |

### 4.8 `opsLedger` —— 调度执行台账（T2 / `v4.9.1`）

回答「**计划任务到底跑没跑**」。本段**只读** `research.ops_ledger.collect_ops_ledger()`
（台账格式、写入端、失败语义见 [ops-ledger](ops-ledger.md)），原样透传其汇总：
`status`（`ok` / `empty` / `unavailable`）、`path`、`totalRuns`、`taskCount`、
`tasks[]`（`task` / `label` / `plannedAt` / `runs` / `lastRunAt` / `lastExitCode` /
`lastOk` / `lastDurationSec` / `lastAsof` / `failureStreak`）、
`failingTasks[]`（连续失败 ≥ `OPERATIONAL_FAILURE_STREAK`=2 的任务名）、
`failureThreshold`、`lastRunAt`、`recent[]`。

台账路径：`ops_ledger_path` 参数 / `STOCK_PLATFORM_OPS_LEDGER_DIR` 环境变量，
默认 `./data/logs/runs.jsonl`；CLI 为 `--ops-ledger`。

**本模块不写执行台账** —— 写入端是调度包装器 `scripts/ops/Invoke-ScheduledRun.ps1`
（或 CLI `stock-platform-ops-ledger --record`）。

## 5. 裁决规则（`roll_up_verdict`，纯函数）

| 段 | `fail`（→ `blocked`） | `warn`（→ `degraded`） | `ok` |
|----|----------------------|----------------------|------|
| `coverage` | `COVERAGE_HARD_FAIL`：`unavailable` / `empty` / `missing_table` / **`error`** / **`unconfigured`** | `COVERAGE_WARN`：`stale` / `thin` | `ok` |
| `latestBrief` | `unavailable` / `empty` | asof 落后 `coverage.latestTradeDate`（按交易日，lag>0） | 同步或滞后不可判定 |
| `briefContinuity` | — | `unavailable` / `empty` / 窗口内有缺日（`incomplete`） | 无缺日 |
| `hits` | — | `unavailable` / `empty` | `ok` |
| `performance` | — | `unavailable` / `empty` / `settledCount < 20` | ≥ 20 |
| `symbolMaster` | — | `unavailable` / `total==0` | `ok` |
| `opsLedger` | — | `unavailable` / `empty` / `failingTasks` 非空 | 无连续失败 |
| `history` | —（**不参与裁决**） | — | — |

- 任一 `fail` → `blocked`；否则任一 `warn` → `degraded`；否则 `ok`。
- `verdict.checks[i].detail` 为中文人读串；`failed`/`warned` 为检查项 id 列表。
- 加新段 = 扩这张表 + 加一段采集，不改既有段语义。

**严重度理由**：无供数 → **物理上选不出票**（硬前提，blocked）；绩效样本不足
→ **结论暂时不可信**（可跑，degraded）。两者不可同档。
`briefContinuity` / `opsLedger` 是**观测面**信号：缺 brief 日或任务连续失败说明
**流水线本身出问题**，但过去的日子已经跑完、当日仍能选股，故**只降级不阻断**。

> **T1 修正（`v4.9.0`）**：`error`（库存在但不可读）与 `unconfigured`（未配置路径）
> 在 `v4.7.0` 的规则里**既非 fail 也非 warn** → 会被判成 `ok`，
> 也就是「仓库打不开」被报告成「供数正常」。两档已并入 `COVERAGE_HARD_FAIL`。

> **T2 为何新增两路而不是把 `latestBrief` 变严**：`latestBrief` 只回答「最新一条是什么」，
> 它对**缺日**完全无感（`10-09`/`10-12` 之间有 `10-10` 缺日也报 `ok`）；
> 而 `opsLedger` 回答的是另一件事 —— 循环之外**调度有没有把任务跑起来**。
> 三者视角不同，合并会丢掉诊断力。

## 6. 边界（本契约**不做**的事）

- **不替代** ops 的 asof 回落守卫（ADR 0070）：守卫在**写 brief 之前**防伤害，
  体检在**之后**认伤害；体检不阻断写 brief。
- **不抓数、不回补**：只如实报告供数滞后；成因治理归 `Invoke-MarketDbBackfill.ps1`。
- `nextSettlement` 是**日历推算提示**，真实结算仍取决于行情是否到位（ADR 0068）。
- 不重新定义 coverage / hits / performance / symbol_master 的任何口径。
- 台账**不做**跨机同步、不做告警推送（推送属 T 域后续里程碑）。

## 7. 出口

| 出口 | 说明 |
|------|------|
| **CLI** | `stock-platform-loop-health` → 默认写 `<out-dir>/loop_health.{json,md,html}` + 追加 `<out-dir>/history.jsonl`；`--out-dir` / `--json-out` / `--out` / `--html-out` / `--history-path` / `--no-history` / `--no-write`（`--no-write` 同时不写台账） |
| **API** | `GET /api/ops/loop-health`（T1）→ 200 返回本 payload；**供数段落在 `COVERAGE_HARD_FAIL` → 503**（`detail.reason="loop_health_no_market_db"`）；其余降级仍 200 |
| **面板** | Workbench `#health`（导航「体检」）→ 裁决徽标 + 关键信号表 + 趋势（近 N 天）；失败时中文提示，不静默 |
| **库** | `collect_loop_health` / `roll_up_verdict` / `render_loop_health_markdown` / `read_history` / `summarize_history` / `append_history` / `default_loop_health_dir` / `default_loop_health_history_path`（`stock_platform_research` 顶层导出） |

## 8. 趋势台账 `history.jsonl`（T1 / `v4.9.0`）

**格式**：JSON Lines，每行一条：

```
{"ts": "<ISO8601 UTC>", "asof": "YYYY-MM-DD", "status": "ok|degraded|blocked",
 "failed": ["coverage", ...], "warned": ["latestBrief", ...]}
```

只落这五个审计字段 —— **不落整份 payload**（趋势只需要裁决）。

**目录解析**：`STOCK_PLATFORM_LOOP_HEALTH_DIR` 优先，否则 `./data/health`；
CLI 下为 `<out-dir>`。文件名固定 `history.jsonl`。

**写入规则**：

- **追加**（不是覆盖）：审计台账必须保留每次体检痕迹；
- **fail-open**：写失败返回 `{"appended": false, "reason": ...}`，**绝不**让体检失败；
- **裁剪**：超过 `HISTORY_MAX_RECORDS`（=400 行 ≈ 一年半日频）时裁掉最旧部分（裁失败不算错误）。

**读取规则**：

- 文件不存在 → `[]`；**读失败向上抛**（由调用方标 `unavailable`，fail-closed）；
- **坏行跳过**（非 JSON / 缺 `asof`）—— 单行损坏不该让整个趋势面消失。

**连续段口径**：

- 先按 `asof` **去重**（同一天多次体检只算一次，`ts` 较晚者胜）；
- 再把**本次**（`asof` + 当前裁决）并入并覆盖当天旧值 → 故连续段**含本次**；
- 从最新一天往回数，遇到不满足条件的当天即停；`streakSince` = 该段最早一天。
