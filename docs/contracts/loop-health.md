# 契约：日用循环健康度（Loop Health）

> 里程碑 **R3 日用循环健康度单点** · 版本 `v4.7.0` · 代码单点：
> `packages/research/src/stock_platform_research/loop_health.py`
> CLI：`stock-platform-loop-health`
> 相关 ADR：[0073](../architecture/0073-daily-loop-health-single-point.md)（本轮）·
> [0058](../architecture/0058-market-db-source-of-truth.md)（market.db 只读真相源）·
> [0049](../architecture/0049-sqlite-first-persistence.md)（brief 权威）·
> [0057](../architecture/0057-hit-tracking.md)（命中追踪）·
> [0068](../architecture/0068-performance-pnl-closed-loop.md)（绩效 PnL）·
> [0070](../architecture/0070-daily-loop-self-sufficiency.md)（供数守卫）·
> [0072](../architecture/0072-symbol-master-name-authority.md)（名称权威）

## 1. 目的

给「今天的日用循环正不正常」一个**唯一只读答案**。把五段（供数 → 选股 → 命中 → 绩效 → 名称）
的既有信号聚合到一个 payload + 一份人读报告，并给出规则化裁决。

**不重新定义任何段的口径** —— 本契约只定义**聚合方式**与**裁决规则**；各段口径归各自契约。

## 2. 硬约束（不可协商）

| 约束 | 含义 |
|------|------|
| **零网络** | 本模块不发布任何 HTTP 请求，也不触发 provider 抓数 |
| **只读** | 不写任何库 / 表；`market.db` 由 provider 以 `mode=ro` 打开 |
| **fail-closed** | 缺件 → `status="unavailable"` + `reason`；**绝不**用默认值冒充 `ok` |
| **方法永不抛** | 每段独立 try/except 就地降级；`collect_loop_health` 是 total function |
| **providers 懒导入** | `research` 顶层零 `stock_platform_providers` 依赖（函数内导入） |
| **退出码恒 0** | 体检不是门禁；裁决在 payload `verdict.status` |

## 3. Payload 形状（JSON）

```
{
  "environment": "SIMULATE", "liveTradingEnabled": false,
  "asof": "YYYY-MM-DD", "generatedAt": "<ISO8601 UTC>", "holdingDays": 5,
  "verdict": { "status": "ok|degraded|blocked", "failed": [...], "warned": [...],
               "checks": [{"id","level":"ok|warn|fail","detail"}] },
  "coverage":      { ... §4.1 ... },
  "latestBrief":   { ... §4.2 ... },
  "hits":          { ... §4.3 ... },
  "performance":   { ... §4.4 ... },
  "symbolMaster":  { ... §4.5 ... },
  "nextSettlement":{ "available": bool, "entryAsof", "holdingDays",
                     "expectedSettlementDate" | "reason" },
  "disclaimer": "..."
}
```

`status` 词表统一为 `ok` / `empty` / `unavailable`，外加各段自身的细分状态
（如 coverage 的 `stale` / `thin` / `missing_table`）。

## 4. 段定义

### 4.1 `coverage` —— 供数覆盖率

**复用** `EngineSqliteProvider.coverage_snapshot()`（ADR 0058 / `C2` 单点），
原样透传其字段：`status`（`ok|thin|stale|empty|missing_table`）、`latestTradeDate`、
`latestRows`、`lagTradingDays`、`missingDays`、`thinDays`、`message`，并补 `source="engine_sqlite"`。

引擎库不可用（环境变量未指 / 文件不存在）→ `status="unavailable"` + `reason`。

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

### 4.5 `symbolMaster` —— 名称主表

来源 `open_symbol_master().stats()`：`total` / `bySource`。`total==0` → `status="empty"`。

## 5. 裁决规则（`roll_up_verdict`，纯函数）

| 段 | `fail`（→ `blocked`） | `warn`（→ `degraded`） | `ok` |
|----|----------------------|----------------------|------|
| `coverage` | `unavailable` / `missing_table` / `empty` | `stale` / `thin` | `ok` |
| `latestBrief` | `unavailable` / `empty` | asof 落后 `coverage.latestTradeDate`（按交易日，lag>0） | 同步或滞后不可判定 |
| `hits` | — | `unavailable` / `empty` | `ok` |
| `performance` | — | `unavailable` / `empty` / `settledCount < 20` | ≥ 20 |
| `symbolMaster` | — | `unavailable` / `total==0` | `ok` |

- 任一 `fail` → `blocked`；否则任一 `warn` → `degraded`；否则 `ok`。
- `verdict.checks[i].detail` 为中文人读串；`failed`/`warned` 为检查项 id 列表。
- 加新段 = 扩这张表 + 加一段采集，不改既有段语义。

**严重度理由**：无供数 → **物理上选不出票**（硬前提，blocked）；绩效样本不足
→ **结论暂时不可信**（可跑，degraded）。两者不可同档。

## 6. 边界（本契约**不做**的事）

- **不替代** ops 的 asof 回落守卫（ADR 0070）：守卫在**写 brief 之前**防伤害，
  体检在**之后**认伤害；体检不阻断写 brief。
- **不抓数、不回补**：只如实报告供数滞后；成因治理归 `Invoke-MarketDbBackfill.ps1`。
- `nextSettlement` 是**日历推算提示**，真实结算仍取决于行情是否到位（ADR 0068）。
- 不重新定义 coverage / hits / performance / symbol_master 的任何口径。

## 7. 出口

- **CLI** `stock-platform-loop-health` → 默认写 `./data/health/loop_health.{json,md,html}`
  （`--out-dir` / `--json-out` / `--out` / `--html-out` / `--no-write`）。
- **库** `collect_loop_health` / `roll_up_verdict` / `render_loop_health_markdown`
  （`stock_platform_research` 顶层导出）。
