# 0073 — 日用循环健康度单点（loop health）

- Status: Accepted
- Date: 2026-10-14
- Supersedes: —
- Related: ADR 0049（SQLite brief 权威）、ADR 0057（命中追踪）、ADR 0058（market.db 是唯一历史真相源）、
  ADR 0068（绩效 PnL 闭环）、ADR 0070（日常循环自足：供数守卫）、ADR 0072（名称权威）

## 背景

平台的日用循环由**五段**串成：

```
供数（market.db 回补） → 选股（brief） → 命中记账（hit cycles）
      → 绩效结算（performance JSONL） → 名称展示（symbol_master）
```

每一段都各自有守卫与契约：

| 段 | 既有守卫 | 出处 |
|----|----------|------|
| 供数 | `EngineSqliteProvider.coverage_snapshot()`（`ok/thin/stale/empty/missing_table`） | ADR 0058；`C2` |
| 选股 | 覆盖率守卫置于 ops 脚本（asof 不可用 → 回落 `latestTradeDate`） | ADR 0070 |
| 命中 | 三累计查询（`hit_tracking_snapshot`） | ADR 0057；`X3` |
| 绩效 | `performance_summary()` settled / pending + 样本量提示 | ADR 0068 |
| 名称 | `symbol_master` 主表 + `display_name` 四层优先级 | ADR 0072 |

**缺口**：没有任何一处把五段放在一起裁决。运维/用户早上打开日报，看到的是**最新 brief**
（ADR 0049 的 `list_recent(limit=1)`），而真相可能是：库里供数滞后 2 个交易日、绩效样本
只有 3 条（< `MIN_MEANINGFUL_SAMPLE=20`，属噪音区）、名称主表为空导致名称全是 `—`。
这些事实**分散在五个地方**，没有任何单一入口回答「今天的循环到底正不正常」。

实测（2026-10-14）：`market.db` 尾部止于 `2026-10-12`（滞后 2 个交易日），
绩效 `settled=3`——两者都只在各自的报告里以脚注形式出现，日报本身看不出异常。

## 决定

### 1. 新增只读单点 `research.loop_health`，把六路信号聚合到一个裁决

`packages/research/src/stock_platform_research/loop_health.py` 提供：

- `collect_loop_health(...) -> dict`：聚合六路信号 + 一个规则化裁决；
- `roll_up_verdict(sections) -> dict`：**纯函数**，把段状态卷成 `ok/degraded/blocked`；
- `render_loop_health_markdown(payload) -> str`：人读版（结论先行、逐段表格）；
- 配套 CLI `stock-platform-loop-health`（写 `loop_health.{json,md,html}`）。

聚合的六路信号：

| 段 | 来源 | 复用方式 |
|----|------|----------|
| `coverage` | 引擎 `market.db` | **复用** `EngineSqliteProvider.coverage_snapshot`（懒导入） |
| `latestBrief` | 平台 SQLite `daily_briefs` | `open_brief_repository().list_recent(limit=1)` |
| `hits` | 命中记账 | `open_hit_repository().summary(session_type=…)` × 两类 |
| `performance` | `recommend_decisions.jsonl` | `performance_summary()` + `load_jsonl()` |
| `symbolMaster` | 本地名称主表 | `open_symbol_master().stats()` |
| `nextSettlement` | 由 brief asof 推 | 交易日历推第 `holding` 个交易日（**提示**，非承诺） |

### 2. 口径硬约束：零网络 / 只读 / fail-closed / 方法永不抛

- **零网络**：本模块不发布任何 HTTP 请求，也不触发 provider 抓数。`market.db` 由
  `EngineSqliteProvider` 以 `mode=ro` 打开（ADR 0058 / ADR 0050）。
- **只读**：不写任何库 / 表。CLI 只写 `data/health/` 下的产物。
- **fail-closed**：某段缺失 → 该段 `status="unavailable"` 并附 `reason`，
  **绝不**用默认值冒充「正常」；`empty` 与 `ok` 是两个不同的词。
- **方法永不抛**：每段独立 `try/except`，失败段就地降级为 `unavailable`，
  其余段照常产出。`collect_loop_health` 对调用方是 **total function**。

### 3. 裁决规则（写进契约，可被单测逐条锁定）

| 段 | `fail`（→ blocked） | `warn`（→ degraded） | `ok` |
|----|---------------------|----------------------|------|
| `coverage` | `unavailable` / `missing_table` / `empty` | `stale` / `thin` | `ok` |
| `latestBrief` | `unavailable` / `empty` | asof 落后 `coverage.latestTradeDate`（按交易日） | 同步 |
| `hits` | — | `unavailable` / `empty` | `ok` |
| `performance` | — | `unavailable` / `empty` / 样本 < 20 | 样本 ≥ 20 |
| `symbolMaster` | — | `unavailable` / `total==0` | `ok` |

- 任一 `fail` → `blocked`；否则任一 `warn` → `degraded`；否则 `ok`。

**为什么 coverage 的硬失败是 blocked 而绩效缺失只是 warn**：没有供数就**根本选不出票**
（循环的物理前提），而绩效样本不足只是「结论暂时不可信」——两者严重度不同，不该同档。

### 4. CLI 退出码恒为 0

体检**不是门禁**。裁决在 payload 的 `verdict.status` 里；需要门禁的运维脚本读 JSON 判断。
CLI 返回非 0 会与「循环可用但需留意」的正常状态混淆。

### 5. `providers` 必须懒导入

`research` 包不得在模块顶层 import `providers`（既有工程约束：`research` 的
`pyproject.toml` 只声明 `numpy`/`pandas`）。因此 `loop_health` 对
`EngineSqliteProvider` / `get_trading_calendar` 一律**函数内导入**，并加
`# type: ignore`。新增 `test_providers_imported_lazily_only` 静态锁死这条约束。

## 后果

**正面**

- 「今天的循环正不正常」从**五个地方**收敛到**一个 JSON + 一份报告**。
- 供数滞后 / 样本不足这两个最隐蔽的降级，从「脚注」升级为**第一等裁决输出**。
- 裁决规则是纯函数，可被单测逐条锁定；将来加段只需扩 `roll_up_verdict` 的表。
- 零网络、只读、永不抛 → 可以被任何调度器（含无人值守）安全地高频调用。

**代价 / 已知边界**

- **不替代既有守卫**：ops 的 asof 回落守卫（ADR 0070）仍在写 brief **之前**生效；
  `loop_health` 是**事后**体检，不阻断写 brief。二者分工：守卫防伤害，体检认伤害。
- **不抓数、不回补**：体检只能**如实报告**供数滞后，治成因仍是 `Invoke-MarketDbBackfill.ps1`
  （ADR 0070）。
- `nextSettlement` 是**日历推算的提示**，真实结算仍取决于行情是否到位（ADR 0068），
  报告里明确标注「提示，非承诺」。
- 段口径各自沿用既有契约（0057/0058/0068/0072），本 ADR **不重新定义**任何口径。

## 验证

- 单测 `packages/research/tests/test_loop_health.py`（19 例）：fail-closed、段隔离、
  coverage 复用 C2、裁决规则表驱动、渲染、providers 懒导入、CLI 写/不写产物。
- 真机一次运行（2026-10-14）：裁决 `degraded`，`warned=['coverage','performance']`
  —— 供数滞后 2 个交易日（`latestTradeDate=2026-10-12`）、绩效样本 3 < 20；
  `hits=14 码/20 次`、`symbolMaster=5237 行`、`nextSettlement=2026-10-19` 均正常。
- `check_docs.ps1` / `check_versions.ps1` 双绿；全量 pytest 全绿。
