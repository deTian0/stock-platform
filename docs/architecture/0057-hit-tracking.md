# ADR 0057：命中追踪接入（X3）

- 状态：Accepted
- 日期：2026-10-10
- 关联：`docs/contracts/hit-tracking.md`、ADR 0055（X1 全市场宇宙）、ADR 0056（X2 榜单）

## 背景

`a-stock-engine` 有一套「选股命中追踪」：同一只票被反复选中时累计命中次数，并维护一个
**10 交易日（≈14 自然日）的追踪周期**，周期内再命中则**滑动延期**，同日同 session 去重。它产出
三类累计：`pre_market` / `post_market` / `pre_market_in_cycle`，日常用于观察「常客」。

平台在 `X1`（全市场宇宙）与 `X2`（五类榜单）之后，每日 recommendation 已能产出，但**没有命中累计**。
`X3` 要求把该规则落进平台 SQLite，使三类累计可查。风险在于：若平台自己重写一套周期算术，
就会和实际在跑的引擎线漂移 —— 这正是 C 域（双线收口）要压制的「第五套重复实现」。

约束：规则只能有一处定义；缺数据 fail-closed；不触碰 `liveTradingEnabled`。

## 决策

1. **新增单点 `research.hit_tracking`**：`apply_hit(current, *, code, session_type, pick_date, config)`
   是周期规则的**唯一定义**（纯函数，无 I/O）。仓库 `SqliteHitTrackingRepository` 只读写，
   不重写规则。
2. **照搬引擎语义**：`cycle_calendar_days = 14`（「10 交易日 ≈ 14 自然日」）、周期内滑动延期、
   边界闭区间（`pick_date == cycle_end` 算周期内）、`total_cycles` 仅在新周期递增。
3. **去重升级为硬约束**：引擎是「先 `SELECT` 后 `INSERT`」；平台用
   `UNIQUE(code, session_type, pick_date)` + `INSERT`，并发下不会重复计数（fail-closed）。
4. **落平台共享库**：`hit_tracking` / `hit_summary` 建在 `STOCK_PLATFORM_DB_URL` 同一 SQLite
   （与 brief 存档 ADR 0049 同库不同表），不引入引擎的 `history/picks.db`。
5. **不做真实交易日历**：引擎用自然日近似，平台照搬；改成真实交易日计数会引入日历依赖，属新里程碑。
6. **写入口收敛**：只由 `run_daily_pipeline(track_hits=True)`（默认开）与显式
   `POST /hit-tracking/track` 触发。`GET /brief` **不**隐式写命中 —— Workbench 的 /brief 也用于
   探索性选股（任意 asof / symbols），计进去会污染周期。
7. **追踪失败绝不打断 brief**：流水线内以 `try/except` 包裹，失败记 `report.hits["error"]`。
8. **可查询三类累计**：`hit_tracking_snapshot()` 一次返回
   `pre_market` / `post_market` / `pre_market_in_cycle`；`cumulative` 与 `in_cycle` 语义分离
   （前者生命周期累计、后者仅窗口内），契约写明不可混用。
9. **接线**：`stock-platform-hits` CLI、`stock-platform-daily`（默认追踪，`--no-track-hits` 关闭）、
   Workbench `GET /api/research/hit-tracking` + `POST /track` + `#hits` 面板；零网络测试
   （research 合成 / apps 用 replay + 临时库）。

## 后果

- 平台 SQLite 多两张表；`data/stock_platform.db` 与 brief 存档同库，备份/迁移一起走。
- 默认追踪 `quality`（②A）头部；②B / ③C 需显式 `boards`。`category` 只落在明细行，
  汇总按 `(code, session_type)` —— 与引擎一致。
- 命中累计与 `performance` JSONL（方向正确率）是**两码事**：前者数次数，后者算收益；
  两者并存，勿合并。
- 与红线无关：`L1` 未立项前不触碰 `liveTradingEnabled`。

## 备选方案（已否决）

| 方案 | 否决理由 |
|---|---|
| 直接在平台重写周期算术 | 会与引擎线漂移（C 域风险），且违反「规则单点」 |
| 复用引擎 `history/picks.db` | 跨仓跨库写，事务边界与备份策略都会分裂 |
| 用真实交易日历算 10 交易日 | 引入日历依赖、与引擎语义不一致；非 X3 范围 |
| `GET /brief` 自动记命中 | 会把探索性选股计入周期，污染 `pre_market` 累计 |
| 命中即推荐 / 命中进买卖信号 | 命中是运营统计，不是信号；信号单点是 B5 / lvrev |
| 用 `performance` JSONL 兼职记命中 | 两者语义不同（次数 vs 收益），合并即口径污染 |
