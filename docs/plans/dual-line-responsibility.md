# 双线职责边界（C1）

> **里程碑**：`C1`（自有线路线图 [§3.6 C 域](trading-system-roadmap.md#36-c--双线收口贯穿)）
> **承接**：[ADR 0058](../architecture/0058-market-db-source-of-truth.md)（数据真相源）· [`docs/ops/engine-market-db.md`](../ops/engine-market-db.md)
> **约束**：本文件只做「**定边界 + 定归属 + 列判据**」，**不**在本路线图内执行任何大规模代码合并（C 域明示非目标）。

## 1. 结论速览

| 问题 | 答案 |
|------|------|
| 谁是**日常调度主链**？ | **`a-stock-engine`**（引擎线）—— 08:30 盘前选股 + 15:30 盘后复盘，唯一在跑的自动化 |
| 谁是**历史行情真相源**？ | **`a-stock-engine/data_cache/market.db` · `daily_price`**（平台**只读**挂载） |
| 谁是**产品 / 研究权威实现**？ | **`stock-platform`**（平台线）—— 回测 / 榜单 / 命中追踪 / 选股↔回测对照 |
| 什么情况下用哪条？ | 见 §4 判据表（日用看引擎，研究看平台，数据缺口修生产侧） |
| 红线 | `L1`（实盘立项）通过前，**两条线都不得触碰 `liveTradingEnabled`** |

## 2. 两条线是什么

| 项 | `a-stock-engine`（引擎线 · 生产侧） | `stock-platform`（平台线 · 消费侧） |
|---|---|---|
| 定位 | **日常调度主链**：日用选股 / 复盘的唯一在跑实现 | **权威产品仓**：回测可信、策略可迭代、选股可日用的正式实现 |
| 仓位置 | `D:\workspace\stock_trading\a-stock-engine` | `D:\workspace\stock_trading\stock-platform` |
| 仓库状态 | 已归档（挂归档横幅，指向本仓）；**冻结新功能**，缺陷优先修平台 | 活跃开发（当前 `v4.0.5`） |
| 每日调度 | 08:30 盘前 + 15:30 盘后（Task Scheduler / cron） | **不接管**日常调度（可被调度跑 refresh→brief，但当前非默认主链） |
| 行情摄取 | **唯一写入方**（`empirical/backfill_market_daily.py` 等） | **只读**（`mode=ro`；ADR 0050 / 0058） |
| 选股内核 | lvrev（日用参考实现） | lvrev **单点**（[`rules.py`](../contracts/trading-rules.md) / [`rankings.py`](../contracts/rankings.md) / [`hit_tracking.py`](../contracts/hit-tracking.md)） |
| 回测 | `local_backtest.py`（口径对照基准） | `backtest.py` / `book_replay.py`（**权威**，X4 与推荐同引擎） |
| 报告产物 | `briefs/YYYY-MM-DD/` + 午盘复盘 HTML | workbench + brief JSON + `{asof}/picks_replay.json` |

## 3. 数据归属（承接 ADR 0058）

| 库 / 表 | 归属方 | 平台可否作**历史行情输入** |
|---|---|---|
| `market.db` · `daily_price` | 引擎（生产侧） | ✅ **唯一历史行情真相源**（只读） |
| `market.db` · `fundamentals_pit` / `daily_basic_pit` | 引擎 | ⚠️ 只读可选（ADR 0050，研究因子用） |
| `a-stock-engine.db` | 引擎 | ❌ 选股/轮动/验证过程库 |
| `selections.db` | 引擎 | ❌ 选股过程库 |
| `history/picks.db` | 引擎 | ❌ 命中历史过程库 |
| `stock_platform.db` | 平台 | ❌ brief 存档 / 命中追踪 / picks 账本（自身产物） |

> **一句话**：行情真相源**唯一**（引擎库）；平台库只存**自己的产物**，两者不互为行情输入。

## 4. 用哪条的判据

| 场景 | 用哪条 | 理由 |
|------|--------|------|
| 「今天该买什么」（日用推荐） | **引擎线** | 它是唯一在跑的日常调度，产出 08:30 简报 |
| 研究 / 回测 / 绩效 / 选股↔回测对照 | **平台线** | 权威实现（B1–B6 / X1–X4 已收官） |
| 命中追踪 / 周期计数 | **平台线** | 规则单点（X3），仅把引擎「先查后插」升级为硬唯一约束 |
| 榜单体系（②A/②B/③A/③B/③C） | **平台线** | 口径单点（X2），③B 委派 B5 `rules` |
| 行情缺口 / 覆盖破相 | **修生产侧（引擎）**，平台只加守卫 | ADR 0058：摄取归生产侧，平台不代抓、不补写 |
| 实盘 | **都不做** | `L1` 门禁前，红线 |

## 5. 边界与红线（双方共同遵守）

- **平台线**：不代抓、不补写行情；发现数据问题**只报警不改库**（`GET /api/ops/health.marketDb`）。只读挂载，`mode=ro`。
- **引擎线**：**冻结新功能**；不恢复为「第二推荐主链」；缺陷优先在平台修复（见 [`../upstream-archive.md`](../upstream-archive.md)）。
- **同名参数不照抄**：值域不同的参数（如 `min_composite_score` 平台 `[0,1]` vs 引擎百分制 60）必须显式隔离，禁止照抄（[`rankings.md`](../contracts/rankings.md) §3）。
- **规则不写两遍**：同一套交易/周期规则只有**一处定义**（B5 `rules` / X3 `hit_tracking`），另一条线委派或对照，不另起实现。

## 6. 交叉链

| 文档 | 关系 |
|------|------|
| [`trading-system-roadmap.md`](trading-system-roadmap.md) §3.6 | C 域出处（本文件为 `C1` 交付物） |
| [`../architecture/0058-market-db-source-of-truth.md`](../architecture/0058-market-db-source-of-truth.md) | 数据真相源 ADR（`C2`） |
| [`../ops/engine-market-db.md`](../ops/engine-market-db.md) | 引擎库摄取与覆盖自检 runbook |
| [`../upstream-archive.md`](../upstream-archive.md) | 上游仓归档与红线（含 `a-stock-engine` 只读边界） |
| [`../ROADMAP.md`](../ROADMAP.md) / [`../README.md`](../README.md) | 顶部焦点区挂载点 |

## 7. 免责

本文件是**边界定义**，不构成投资建议，也不改变任何运行行为；`liveTradingEnabled` 在 `L1` 立项通过前恒为 `false`。
