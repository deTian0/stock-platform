# 契约：命中追踪（Hit Tracking）

> 里程碑 **X3** · 版本 `v4.0.2` · 代码单点：`packages/research/src/stock_platform_research/hit_tracking.py`
> 相关 ADR：[0057](../architecture/0057-hit-tracking.md) · 上游同源：`a-stock-engine/src/pick_tracker.py`

## 1. 目的

把 `a-stock-engine`「选股命中追踪」的周期规则**搬进平台 SQLite**，使跑在平台上的每日推荐
（②A 头部）自动累计命中次数，并可按 session 查询三类累计。这样「同一只票最近被反复选中」
这一运营信号不在两条线各写一遍。

**验收**（路线图 X3）：10 交易日周期 + 14 天延期 + 同日去重规则落入平台 SQLite；
`pre_market` / `post_market` / `pre_market_in_cycle` 三类累计可查。

## 2. 规则（单点定义）

规则实现只有一处：`hit_tracking.apply_hit(current, ...)`（纯函数，无 I/O）。
仓库 `SqliteHitTrackingRepository.record*` 只负责读写，不重写规则。

对每一个 `(code, session_type)` 键：

| 情形 | 结果 |
|---|---|
| 首次命中 | 新周期：`cycle_id = cycle_start = pick_date`，`cycle_end = pick_date + cycle_calendar_days`，`cycle_hits = 1`，`cumulative = 1`，`total_cycles = 1`，`is_cycle_start = True` |
| 周期内再命中（`pick_date ≤ active_cycle_end`） | **滑动延期**：沿用同一 `cycle_id`，`cycle_end = pick_date + cycle_calendar_days`，`cycle_hits += 1`，`cumulative += 1`，`total_cycles` 不变，`is_cycle_start = False` |
| 周期已结束再命中（`pick_date > active_cycle_end`） | 新周期：`cycle_id = pick_date`，`cycle_hits = 1`，`cumulative += 1`，`total_cycles += 1`，`is_cycle_start = True` |
| 同日同 session 重复 | **去重**：只计 1 次（`UNIQUE(code, session_type, pick_date)` 硬约束） |

- `cycle_calendar_days` 默认 **14**（`DEFAULT_CYCLE_CALENDAR_DAYS`）。引擎把「10 交易日」
  近似为「14 自然日」（`CYCLE_TRADING_DAYS = 10` / `CYCLE_CALENDAR_DAYS = 14`），此处**照搬**。
- `session_type ∈ {pre_market, post_market}`（`HIT_SESSION_TYPES`）。两个 session 的计数**互相独立**。
- 周期边界：`pick_date == active_cycle_end` 视为**周期内**（闭区间，与引擎一致）。
- 命中代码归一为 **6 位数字核**（`norm_hit_code`）：`600519.SH` / `sh600519` / `600519` 视为同一键。
- 名称随每次命中刷新（`_clean_name`：空/`nan` → 回落为代码）。

## 3. 存储

平台共享 SQLite（`STOCK_PLATFORM_DB_URL`，默认 `sqlite:///./data/stock_platform.db`），
与 brief 存档（ADR 0049）**同库不同表**：

- `hit_tracking` —— 每日明细，`UNIQUE(code, session_type, pick_date)`；含
  `category`（类目，如 `②A_质量榜` / `②B_短线榜`）、`cycle_id/start/end`、`cycle_hits`、`cumulative`、`is_cycle_start`。
- `hit_summary` —— 每 `(code, session_type)` 一行汇总：`cumulative_hits`、`active_cycle_*`、
  `total_cycles`、`last_pick_date`、`first_pick_date`。

写路径一次事务提交（`record_many`）；读路径三个方法（`summary` / `active_cycles` / `details`）。

## 4. 三类累计查询（验收口径）

`hit_tracking_snapshot(repo, asof=...)` 一次性返回：

| 键 | 含义 | 取值 |
|---|---|---|
| `pre_market` | 盘前累计 | `codeCount` / `cumulativeHits` / `totalCycles` / `activeCodeCount` / `lastPickDate` |
| `post_market` | 盘后累计 | 同上 |
| `pre_market_in_cycle` | 盘前**活动周期内**命中 | `codeCount` / `cycleHits` / `items[]`（按 `active_cycle_hits` 降序） |

「活动周期」按参考日判定：`active_cycle_end >= asof`。`cumulative` 不受窗口影响（生命周期累计），
`in_cycle` 只统计窗口仍开着的代码——两者**故意不同**，勿混用。

## 5. 出口

| 出口 | 用法 |
|---|---|
| 流水线 | `run_daily_pipeline(..., track_hits=True)`（默认开）把 ②A 头部记入 `pre_market`；失败落 `report.hits["error"]`，**绝不**中断 brief |
| CLI | `stock-platform-hits`（`--summary` / `--report` / `--details` / `--track-brief` / `--track-json`） |
| daily CLI | `stock-platform-daily --no-track-hits` 关闭默认追踪 |
| Workbench | `GET /api/research/hit-tracking`（只读三类累计 + 明细 + markdown）；`POST /api/research/hit-tracking/track`（显式把已存 brief 记入，幂等） |
| 前端 | `#hits` 面板：三块汇总 + 明细表 + 「同步命中」按钮 |

默认追踪的榜单为 **②A 质量榜**（`boards=("quality",)`，即 `picks` 头部）；`boards` 可扩展为
`short_term` / `watchlist`，对应 `category` 记为该榜中文键。

## 6. 与 `a-stock-engine` 的同源与差异

**同源**（刻意保持，避免两条线漂移）：

- 周期长度、滑动延期、闭区间边界、同日去重、字段语义（`cycle_hits` / `cumulative` / `total_cycles`）。

**差异**（平台加固，写死在此以免后人「对齐」时误抄）：

1. **去重改为硬约束** `UNIQUE(code, session_type, pick_date)`：引擎是「先查后插」，
   并发下可能重复；平台用约束 + `INSERT ... ON CONFLICT` 兜底。
2. **不写 `history/picks.db`**：引擎的命中库是独立文件；平台落共享平台库，与 brief 同库事务边界。
3. **周期长度可配** 但默认 14 自然日，**不实现真实交易日历**——引擎用自然日近似，
   平台照搬；若要改真实交易日计数属新里程碑（会引入日历依赖），不在 X3 范围。
4. **写入口收敛**：只由流水线 / 显式 API 触发，`GET /brief` 不隐式写命中（避免把探索性选股计入周期）。

## 7. 非目标

- 不做 T+N 收益结算（那是 `performance` JSONL 与 B5/X4 的职责）。
- 不做「命中即推荐」——命中是运营统计，不是买卖信号。
- 不聚合多日横截面（`hit_summary` 是累计计数，非时序曲线）。

## 8. 免责

研究口径、SIMULATE；非投资建议；不接实盘。
