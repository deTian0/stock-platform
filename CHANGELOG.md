# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循本仓 [`docs/versioning.md`](docs/versioning.md)。

## [Unreleased]

### Added

- （无）

## [4.1.0] - 2026-10-10

### Added

- **因子 / 闸门 A/B 完整版（`S1`，U7 遗留）**：让 A/B 与回测 / 推荐回放**同源** —— 两臂消费同一特征帧、跑**同一台** `book_replay.replay_book`（`X4` 单点定义），只由 entry provider 区分。ADR [`0060`](docs/architecture/0060-strategy-ab-full-engine.md)
  - `StrategyConfig` 增 `gates`（`min_pick_score` 缺省 `0.80`；接受扁平别名 `min_pick_score` / `minPickScore`）→ **闸门变更可表达**；`load_strategy_config` 现接受**裸 id**（`<id>` / `<id>.json`）
  - `strategy_ab` 新增 `config_entry_provider` / `run_config_book` / `compare_strategy_ab_engine` / `compare_strategy_ab_from_bars`
  - 每臂附 **`review` 复盘块**（`directionAccuracy` / `settledCount` / `pendingCount`，口径对齐 `performance` / U3；空仓为 `null`，不填 0）
  - `delta = B − A`（同口径无需二次归一）+ `sameDefinition` 身份块（`singleLoop` / `singleEntryProvider` / `singleMetrics` / `singleExitDefinition`）
- CLI `stock-platform-strategy-ab`（`--config-a/--config-b --start --end --universe --json`，只读 `market.db`）
- API `POST /api/research/strategy/ab-engine`（只读 `market.db`；未知配置 **404** / 无 DB **503** fail-closed）
- Workbench `#strategy-compare` 面板内新增「**A/B 同屏**」区块（两列指标 + Δ 列 + 复盘表 + 双净值曲线，手写 SVG 零新依赖）
- 契约 [`docs/contracts/strategy-ab.md`](docs/contracts/strategy-ab.md)；打包闸门演示臂 `lvrev-gate-strict-v1`

### Changed

- 打包策略配置 `lvrev-default-v1` / `lvrev-rev-heavy-v1` 补 `gates.min_pick_score = 0.80`
- 版本号 `4.0.5` → **`4.1.0`**（`S` 域首版；目标 tag 由陈旧的 `v3.14.0` 顺延）

### Verified

- **同源一致性**：baseline 配置 vs `run_portfolio_backtest` —— 曲线 / 成交 / 指标 / 未平仓**逐位一致**（`tests/test_strategy_ab_engine.py`）
- `sameDefinition` 四项全 `true`；严格闸门臂入场数 **≤** 宽松臂
- 真机 `market.db` 端到端（1 年窗，143 万行 / 6761 码 / 243 日）：两臂 87 vs 93 笔，指标 + 复盘 + delta 齐全
- 聚焦测试：research `19 passed`、workbench `145 passed`（端点目录 61 → **62**）

### Docs

- 新增 `docs/architecture/0060-strategy-ab-full-engine.md` + `docs/contracts/strategy-ab.md`（均已登记 `scripts/check_docs.ps1`）
- 路线图 `S1` 标 `done（2026-10-10）`；版本映射 `S` 域改 `v4.1.0` → `v4.1.4`

## [4.0.5] - 2026-10-10

### Added

- **双线职责边界（`C1`）**：新增 [`docs/plans/dual-line-responsibility.md`](docs/plans/dual-line-responsibility.md) —— 定边界 + 定归属 + 列判据（不做大规模代码合并）。
  - 日常调度主链 = **引擎线**（`a-stock-engine`，08:30 盘前 / 15:30 盘后）；历史行情真相源 = `market.db`·`daily_price`（平台**只读**）；产品 / 研究权威 = **平台线**
  - 5 组使用判据（日用 → 引擎；研究 / 回测 / 绩效 / 选股↔回测 → 平台；数据缺口 → 修生产侧；命中追踪 / 榜单 → 平台；实盘 → 都停）
  - 数据归属表（承接 ADR 0058）+ 双方红线（平台不代抓不补写 / 引擎冻结新功能）
  - 与路线图 / `ROADMAP` / `README` / ADR 0058 / `engine-market-db.md` 交叉链

### Changed

- **文档与 CI 一致性（`G3`）**：自有主线路线图 `trading-system-roadmap.md` 挂进 `docs/ROADMAP.md` 顶部焦点区与 `docs/README.md`；`docs/plans/README.md` 陈旧状态刷新
- **补齐 `scripts/check_docs.ps1` 的 `$required` 三处遗漏**：`trading-system-roadmap.md`（主路线图竟未登记）/ `b3-cost-model-milestone.md` / 新 C1 文档 —— `files` **128 → 131**
- 版本号 `4.0.4` → **`4.0.5`**

### Verified

- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.5，docs `files=131` / `md=158`）
- CI `monorepo` job 确认：5 包 editable 安装 + `pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）
- 全量 `pytest packages apps`（`replay`）= **786 passed / 0 failed**（纯文档里程碑，计数不变）

### Docs

- 新增 `docs/plans/dual-line-responsibility.md`（已登记 `scripts/check_docs.ps1`）
- 路线图 `G3` / `C1` 标 `done（2026-10-10）`；**G 域（G1–G3）全部收官**

## [4.0.4] - 2026-10-10

### Added

- **选股↔回测同引擎（`X4`）**：把逐日回放循环抽成**唯一定义** `research.book_replay.replay_book`（`entry_provider` 多态），`backtest.run_portfolio_backtest` 转薄封装、`picks_backtest.run_picks_backtest` 用**同一台引擎**跑推荐账本 —— 推荐绩效与回测口径**同源**（承接 B5）。ADR [`0059`](docs/architecture/0059-picks-backtest-parity.md)
  - picks 账本 append-only JSONL `{out}/picks_ledger.jsonl`（`(date, code)` 去重；`normalize_picks` 冻结为 `{date, code, rank?, score?}`）；流水线默认 `track_picks_ledger=True` 自动写入 ②A 头部
  - `replay_book` 新增 `open_positions[]` 出口（窗口结束仍持有的仓位：`code` / `entry_idx` / `entry_price` / `shares` / `target` / `peak` / `held_days`），两条路径都透出；`ok` 判据改为「形成至少一个持仓 = 已平仓 ∪ 未平仓」
  - 对照 `compare_picks_vs_screener`：同堆 bars 跑两侧，`delta = picks 指标 − 回测指标`（同口径无需二次归一），附 `sameDefinition` 身份块
- CLI `stock-platform-picks-backtest`（读 `--ledger` 或 `--briefs-dir`，只读 `market.db`）
- 流水线可选回放对照：`replay_picks` / `replay_bars` / `replay_against_screener` → 写 `{asof}/picks_replay.json`，`report.picksReplay` 为裁剪摘要（不含曲线/成交）

### Changed

- `backtest.py` 内联回放循环抽走 → 薄封装（新增 `prepare_book_frame` 共享 bars→特征帧，含 universe 过滤 + 窗口切片）；**默认档全周期逐位不变**
- `daily_pipeline` 默认自动写 picks 账本（`track_picks_ledger=True`；失败 best-effort，写进 `report.picksLedger` 绝不中断 brief）
- 版本号 `4.0.3` → **`4.0.4`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **786 passed / 0 failed**（761 → 786，**+25**）
- research 新增 3 测试文件（`test_book_replay.py` / `test_picks_backtest.py` / `test_daily_pipeline.py` 的 X4 项）共 **32 passed**
- **纯重构证据**：从重构前 `run_portfolio_backtest` 抓 8 场景（股票 / ETF / 混合 / 滑点 / 零费 / 冷静期 / 旧 `verbatim` 尺度 / 单码）曲线与成交 sha256 + 全部指标存 fixture，**8/8 逐位一致**
- **同引擎证明**：把回测 `trades` + `open_positions` 回灌成 picks schedule 后，`trades` / `equity_curve` / `metrics` / `open_positions` **逐位相等**
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.4）

### Docs

- 新增 ADR [`0059`](docs/architecture/0059-picks-backtest-parity.md) + 契约 [`docs/contracts/picks-backtest.md`](docs/contracts/picks-backtest.md)（均登记 `scripts/check_docs.ps1`）
- `docs/ops/daily-pipeline.md` 新增「X4：picks 账本与推荐↔回测对照」段

## [4.0.3] - 2026-10-10

### Added

- **数据真相源统一 + 覆盖守卫（`C2`）**：确认 `daily_price`（`market.db`）为唯一历史行情真相源，并把"摄取还在不在跑"变成**可查询的判据**。ADR [`0058`](docs/architecture/0058-market-db-source-of-truth.md)
  - `EngineSqliteProvider.coverage_snapshot(asof, lookback_days=30, min_rows=3000)`：**只读**双判据快照 —— ① 窗口内 CN 交易日是否齐全（含 `lagTradingDays`，**按交易日而非自然日**计滞后，周末/长假不误报）；② 每日行数是否 ≥ `min_rows`。裁决 `ok | thin | stale | empty | missing_table`；异常收敛为 `status="error"`，**永不抛给调用方**
  - `GET /api/ops/health` 新增 `marketDb` 块：`thin` / `stale` / `empty` / `missing_table` / `error` 会把整体 `status` 降级为 `degraded`；未配置时为 `unconfigured`**不降级**
- 派生库归属写明（ADR 0058 表）：引擎 `a-stock-engine.db` / `selections.db` / `history/picks.db`、平台 `stock_platform.db` —— 均**不得**作为历史行情输入

### Fixed

- **引擎 `market.db` 覆盖破相（静默一个月）**：`daily_price` 自 `2026-09-04` 起破相 —— `09-04` / `09-07` / `09-08` 各仅 **14 行**（引擎 `refresh_etf_daily_prices` 每日只写 14 只 ETF 的签名行数），`09-09`~`10-09` 共 **17 个交易日完全缺失**，最后全市场日停在 `2026-09-03`（5223 行）。已在生产侧回补 **20 个交易日 / 104,301 行 / 0 失败**，覆盖恢复（每日 ~5.2k 行，最新 `2026-10-09`）
- 摄取链路的两处结构缺陷已定位并写入 runbook：① 全市场写入只靠手动 `empirical/backfill_market_daily.py`，日常自动化随引擎归档停止后无人补；② `import_local_data.py` 的断点续传按**日期存在性**判定，**部分覆盖日被永久跳过**、无法自愈
- **已知遗留（本轮不改）**：`refresh_etf_daily_prices` 会删光 14 只 `WELL_KNOWN_ETFS` 的**全部历史**再写 65 根、`pct_chg` 全 0（实测各仅剩 `2026-06-09~09-08`；同表裸码 `518880` 仍有 1499 行）。修复路径已实测可用（`fund_daily`，14 次调用），待复权口径决策后单独处理

### Changed

- 版本号 `4.0.2` → **`4.0.3`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **761 passed / 0 failed**（747 → 761，**+14**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.3）
- 新增测试：`packages/providers/tests/test_engine_coverage.py`（9 项：窗口齐全 / 薄日 / 缺日 / **交易日滞后口径** / 空窗 / 缺表不抛 / 快照形状与只读 / asof 默认 / 非法 asof）、`apps/workbench/tests/test_ops_market_db.py`（5 项：未配置不降级 / 齐全 ok / 薄日降级 / 缺日降级 / 坏库**不 5xx**）
- 回补单位口径实测：`--validate` 对 `2026-09-03` 存量全市场日抽样 400 只，`close` / `pct_chg` / `vol` / `amount` 比值中位数**全为 1.0000**
- 覆盖复核：`2026-09-04`~`10-09` 每个交易日恢复 ~5.2k 行；全库 8,875,338 行 / 1638 交易日 / 6983 码

### Docs

- 新增 ADR `docs/architecture/0058-market-db-source-of-truth.md`（已登记 `scripts/check_docs.ps1`）
- `docs/ops/engine-market-db.md` 新增「摄取与覆盖自检（C2）」：刷新命令 / 单位口径 / 自检出口 / 三条已知坑

## [4.0.2] - 2026-10-10

### Added

- **命中追踪接入（`X3`）**：把 `a-stock-engine` 的选股命中周期**搬进平台 SQLite**，规则只有**一个定义** `research.hit_tracking.apply_hit`。契约 [`docs/contracts/hit-tracking.md`](docs/contracts/hit-tracking.md)、ADR [`0057`](docs/architecture/0057-hit-tracking.md)
  - 周期规则（**照搬引擎**）：首次命中启动周期 `cycle_end = pick_date + 14 日历日`（10 交易日≈14 自然日）；周期内再命中 **滑动延期** 14 天且 `cycle_hits += 1`；`pick_date == cycle_end` 算周期内（闭区间）；`total_cycles` 仅在新周期递增；`session_type ∈ {pre_market, post_market}` 两套计数独立
  - `SqliteHitTrackingRepository`：`hit_tracking` 明细表 + `hit_summary` 汇总表，建在 `STOCK_PLATFORM_DB_URL`（与 brief 存档**同库不同表**）；去重由引擎的「先查后插」升级为硬约束 `UNIQUE(code, session_type, pick_date)`
  - 代码归一为 6 位数字核（`600519.SH` / `sh600519` / `600519` 同键）；`HitTrackingConfig.cycle_calendar_days` 可配，默认 14
- **三类累计查询**：`hit_tracking_snapshot(repo, asof=...)` 一次返回 `pre_market` / `post_market` / `pre_market_in_cycle`（前两者为生命周期累计，后者仅统计窗口仍开着的代码——语义分离，契约写明不可混用）；`format_hit_report` 输出 markdown
- **CLI** `stock-platform-hits`：`--summary` / `--report` / `--details` / `--track-brief` / `--track-json`
- **Workbench**：`GET /api/research/hit-tracking`（只读三类累计 + 明细 + markdown，空库中文 `emptyMessage`）；`POST /api/research/hit-tracking/track`（显式把已存 brief 记入，幂等）；新增 `#hits` 面板（三块汇总 + 明细表 + 「同步命中」按钮）

### Changed

- `run_daily_pipeline(track_hits=True)`（默认）把 ②A 头部记入 `pre_market` 命中周期，结果落在 `report.hits`；**追踪失败记 `report.hits["error"]`，绝不中断 brief**（`hit_boards` 可覆盖榜单集）
- `stock-platform-daily --no-track-hits`：关闭默认命中追踪
- **写入口收敛**：`GET /brief` **不**隐式写命中——Workbench 的 /brief 也用于探索性选股（任意 asof / symbols），计进去会污染周期
- 版本号 `4.0.1` → **`4.0.2`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **747 passed / 0 failed**（719 → 747，**+28**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.2）
- 新增测试：`packages/research/tests/test_hit_tracking.py`（20 项：纯规则首次 / 滑窗 / 边界闭区间 / 新周期 / 可配天数、仓库同日去重 / 两 session 独立 / 代码归一 / 非法 session / `record_many`、三类累计快照 / 排除已结束周期 / 空库零值 / markdown / 明细筛选、brief 榜单→category 映射）、`apps/workbench/tests/test_hit_tracking_api.py`（5 项）；`test_daily_pipeline.py` 增命中周期回归（+1）
- `test_all_api_endpoints.py` 端点目录登记两新操作（59 → 61 ops）

### Docs

- 新增契约 `docs/contracts/hit-tracking.md`、ADR `docs/architecture/0057-hit-tracking.md`，均已登记进 `scripts/check_docs.ps1` 的 `$required`

## [4.0.1] - 2026-10-10

### Added

- **榜单体系对齐（`X2`）**：brief 现在除 `picks[]` 外还产出与 `a-stock-engine` 同构的**五类榜单**，切分逻辑只有**一个定义** `research.rankings.build_rankings`。契约 [`docs/contracts/rankings.md`](docs/contracts/rankings.md)、ADR [`0056`](docs/architecture/0056-ranking-boards.md)
  - `②A_质量榜` 综合分 TopN（默认 10）／`②B_短线榜`（默认 5，**排除 ②A 头部**，带 `entry_ok` 列时优先取过闸门者、不足按分补足）／`③A_持仓`（持仓 ∩ 截面；**未过今日入场闸门的持仓也列示**，`composite_score=null`）／`③B_操作建议`（**完全委派 B5 `rules`**，只收 `exit`/`trim`，`reason` 原文透传）／`③C_观察名单`（②A 之后 23 只）
  - `RankingConfig` 为档位参数单点：`quality_top_n` / `short_term_top_n` / `watchlist_top_n` / `min_composite_score`（默认 0.0 关闭）
  - **`picks` 语义不变**（= ②A 头部），DB 存档 / 绩效日志 / intel-report 零迁移
- **CLI** `stock-platform-rankings`：`--panel`（原始特征面板或已评分面板）+ `--holdings` → `--md` / `--csv` / `--json`
- **Workbench**：`/api/research/brief?holdingsPath=`（默认 `STOCK_PLATFORM_HOLDINGS_PATH`，复用 `position_review_cli.load_holdings` 唯一读取器）；响应新增 `rankings` / `rankingsCounts` / `holdingsLoaded` / `holdingsNote`；`#recommend` 页新增「榜单」区块（五榜表格 + fail-closed 提示）

### Changed

- `build_premarket_brief` 改为对**全量**评分截面切榜单后再 `head(top_n)` 生成 `picks`（默认档逐位不变）
- `run_daily_pipeline(holdings=...)` / `stock-platform-daily --holdings`：流水线支持传入持仓以填充 ③A / ③B
- 版本号 `4.0.0` → **`4.0.1`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **719 passed / 0 failed**（698 → 719，**+21**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.1）
- 新增测试：`packages/research/tests/test_rankings.py`（16 项：分榜切分 / ②B 优先 entry_ok / 门槛只切推荐类目 / 未过闸门持仓不丢 / ③B reason 来自 `rules` / 三种 fail-closed / CLI 三出口）、`apps/workbench/tests/test_rankings_api.py`（4 项：五榜结构 / 持仓填充 / 坏文件 fail-closed / UI 区块存在）

### Docs

- 新增契约 `docs/contracts/rankings.md`、ADR `docs/architecture/0056-ranking-boards.md`，均已登记进 `scripts/check_docs.ps1` 的 `$required`

## [4.0.0] - 2026-10-10

### Added

- **全市场选股接入（`X1`）**：日线宇宙从 JSON fixture（`core`/`watch`/`full`，数十~数百代码）扩到 `market.db` **全市场**（排除 BSE）。宇宙解析只有**一个入口** `research.market_universe.resolve_universe(source=...)`，`UNIVERSE_SOURCES = ("config", "market_db")`，默认仍是 `config`（X1 不改变既有行为）。契约 [`docs/contracts/market-universe.md`](docs/contracts/market-universe.md)、ADR [`0055`](docs/architecture/0055-market-universe.md)
  - **providers** `EngineSqliteProvider.list_symbols`：仓库 → 代码列表的**唯一定义** —— 日期窗口聚合（走 `idx_dp_date`）、`min_bars`、BSE 排除（经 `symbol.is_bse_symbol` 单点）、6 位归一、**裸码与带后缀码合并计数**、脏码（非 6 位）丢弃
  - **research** `resolve_market_universe`：只做资产类别过滤（复用 B4 单点 `portfolio.asset_class`）、`limit`、出处与代价记录、fail-closed；**不重复** BSE 前缀表，也**不重排** provider 结果
  - `MarketUniverse` 随结果返回出处与代价：`counts`（source → normalized → asset_matched → final）、`elapsed_s`、`peak_memory_mb`（`tracemalloc`，默认关）
- **CLI** `stock-platform-market-universe`：`--db` / `--asof` / `--asset-type` / `--min-bars` / `--limit` / `--include-bse` / `--probe-panel` / `--json` / `--symbols-only`；文档里的每个实测数字都由它现场产出
- **流水线接线**：`run_daily_pipeline(universe_source="market_db", market_symbol_source=...)` 自动注入本次 `asof` / `lookback_days`，报告新增 `universe{source,size}`；`daily_cli` 新增 `--universe-source` / `--market-db` / `--asset-type` / `--min-bars` / `--limit` / `--include-bse`
- 新增测试 `packages/research/tests/test_market_universe.py`（fake source）与 `packages/providers/tests/test_engine_sqlite_universe.py`（合成 sqlite，含裸码 / BSE / 脏码 / 窗口外数据），**全程不碰 3.14 GB 真实库**

### Changed

- 版本号 `3.13.9` → **`4.0.0`**（**major**：能力边界从 watch 宇宙扩到全市场）

### Verified

- 实测（`market.db` 3.14 GB / 877 万行 / asof 2026-09-03，见 [`docs/ops/market-universe-benchmark.md`](docs/ops/market-universe-benchmark.md)）：
  - 全市场枚举（stock / 排除 BSE）= **5227 只**，耗时 **0.21 s**、峰值 **1.04 MB**
  - `asset_type=all` 5241 只；`min_bars=60` 5194 只；`include_bse=True` 与默认一致（库内无 BSE 数据）
  - **全市场单日 PIT panel**：5227 只 → **5209 行** / **23.0 s** / 峰值 **498.8 MB**
  - SQL 口径：日期窗口聚合 **0.15 s** vs `SUBSTR(code,-2)` 全表扫描 **5.12 s**（**34×**）
- 全量 `pytest packages apps`（`replay`）= **698 passed / 0 failed**（679 → 698，**+19**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.0）

### Docs

- 新增契约 `docs/contracts/market-universe.md`、ADR `docs/architecture/0055-market-universe.md`、实测 `docs/ops/market-universe-benchmark.md`，均已登记进 `scripts/check_docs.ps1` 的 `$required`

### Notes

- ⚠️ **发现数据覆盖缺陷（非平台代码问题）**：`market.db` 自 **2026-09-04** 起每日 bar 数从 ~5.2k 塌到 **14** 只（引擎侧导入中断），**最后可用交易日 = 2026-09-03**。宇宙枚举（120 天窗口）不受影响，但**当日横截面 / 选股会几乎空**（PIT 要求 asof 当日有 bar）。`X3` / `X4` 开工前应先修引擎侧导入 —— 平台只读，不代抓
- 当前库**不含北交所数据**：`include_bse=True` 与默认结果完全一致（实际过滤 0 个）；排除规则为将来保留
- `X1` 只做内核 + CLI + 文档，**未新增 Workbench API**；UI 接入留待 `X2`（榜单体系对齐）
- 与既有红线无关：`L1` 未立项前不触碰 `liveTradingEnabled`

## [3.13.9] - 2026-10-10

### Added

- **数据源适配层**：新增三个 provider（均实现 `MarketDataProvider`，缺源 fail-closed 中文报错），统一接入非默认数据源（详见 [`docs/contracts/data-source-adapters.md`](docs/contracts/data-source-adapters.md)、[`docs/architecture/0054-data-source-adapters.md`](docs/architecture/0054-data-source-adapters.md)）：
  - **`workbuddy`**（`daily`+`realtime`）：WorkBuddy MCP 数据能力（`westock-data` / `neodata-financial-search`）的 **JSON 缓存适配器** —— 读 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR` 下 `daily_{code}.json` / `realtime_{code}.json`（与 `replay` fixture 同构）；`write_daily_cache` / `write_realtime_cache` 是 schema 唯一生产点
  - **`tdx`**（`daily`）：读通达信本地 `vipdoc/{sh,sz,bj}/lday/*.day`（32 字节定长记录，`struct` 零依赖）；`STOCK_PLATFORM_TDX_ROOT` 或自动探测；实时未映射（fail-closed）
  - **`futu`**（`daily`+`realtime`）：懒加载 `futu-api` 连 OpenD（默认 `127.0.0.1:11111`）；`request_history_kline` / `get_market_snapshot`；缺包/无网关 fail-closed
- 新增预设 `workbuddy` / `cn_tdx` / `cn_futu`（均 `is_default=False`），能力矩阵各声明对应数据集
- 新增测试 `test_workbuddy.py` / `test_tdx.py` / `test_futu.py`（合成 JSON / `struct.pack` 二进制 / fake module+context，**零网络**）

### Verified

- 新增适配器 + 既有 preset/capability 测试 **26 passed**
- 全量 `pytest packages apps`（`replay`）= 见下方 Notes 之最新计数
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.9）

### Notes

- 生产默认仍 `cn_astock_http`；三新源均不触碰 `liveTradingEnabled`，仅数据读路径
- `workbuddy` 的「MCP 兼容」= MCP 桥接方落 JSON 缓存 → provider 只读消费（刻意不直连 Markdown/自然语言，避免解析脆弱性）

## [3.13.8] - 2026-10-10

### Fixed

- **修复涨跌停判定因 `pct_chg` 标度混用而近乎失效**（B5 遗留缺陷，见 `docs/contracts/trading-rules.md` §7）：`daily_price.pct_chg` 绝大多数**股票**行是小数（`0.0123` == 1.23%），绝大多数 **ETF** 行是百分点（`1.23` == 1.23%），旧实现按 `|x|>0.5` 一刀切，把新股首日 +86.9%（小数）误判为百分点、把 ETF 0.94%（百分点）漏判，导致 `rules.is_limit_up/down`（阈值按百分点）**漏判 99.6%**（实测涨停 1007 次 → 归一后 104034 次）

### Added

- 新增 `pct_scale.py` 单点定义：`detect_pct_scale(bars)` 用 **`close` 序列拟合投票**逐 code 判定 `fraction` / `points`（剔除 |隐含收益|>21% 的除权日防污染，少于 10 个可投会话则回退 `asset_class` 先验）；`to_points` / `normalize_pct_chg` 归一为百分点（`rules` 契约标度）
- `backtest.compute_features` / `run_portfolio_backtest` 新增 `pct_scale="auto"|"verbatim"`（默认 `auto`）；`auto` 用归一后的百分点重建复权价并喂涨跌停判定，`verbatim` 锁定旧行为供对照
- 新增 `packages/research/tests/test_pct_scale.py`（12 用例：判据 / 边界 / 回退 / 单点一致）

### Verified

- 真机全周期 A/B（`market.db` 3.14 GB / 877 万行 / 6974 码）：`verbatim`（旧）与 B1–B6 基线**逐位一致**（0.902353 / 0.105348 / −0.171435 / 0.7511 / 630）；`auto`（新默认）→ 总收益 **+91.71%**（0.917123）/ CAGR 10.67% / 最大回撤 −17.30% / 夏普 0.7612 / 笔数 **628**（跌停顺延生效，−2 笔）/ 终值 **95,856.17**
- 全量 `pytest packages apps`（`replay`）= **660 passed / 0 failed**（648 → 660，+12）

### Notes

- **这是行为修复（策略变更），非纯重构**：默认档 `auto` 相对 B1–B6 基线**基线移动**（涨跌停约束从失效变生效）；`verbatim` 档保留旧行为供回放。报告任何数字须声明 `pct_scale` 档位。

## [3.13.7] - 2026-10-09

### Fixed

- **修复 `GET /api/research/intel-report/crosswalk` 与 `GET /api/research/intel-report/prefill` 在**不带 `asof`** 参数时的 500**：`TypeError: default_brief_asof() missing 1 required positional argument: 'state'`。`default_brief_asof` 在 `v3.10.1`（`c640b5c`）改为必需 `state`，而 `v3.12.5`（`0da5f2d`）新增的这两个调用点仍按**旧签名**写成 `default_brief_asof()` —— 该缺陷**自 `v3.12.5` 起潜伏五个版本**（`v3.12.5` → `v3.13.6`）。现两处统一走既有的 `_resolve_asof(request, asof)`，重复的兜底逻辑一并消除
- 复现条件恰是 UI 默认行为：`loadIntelCrosswalk()` 在 asof 输入框为空时**不发 query string**，故该端点在浏览器首屏必崩。此前全部用例都显式传 `asof`，**兜底分支零覆盖**，CI 与真实路径脱节

### Added

- 新增静态守卫 `apps/workbench/tests/test_signature_call_guard.py`：AST 扫描包内所有「模块级唯一定义函数」的调用点，**位置实参 + 关键字实参少于必填参数即失败**（`*args` / `**kwargs` / 重名函数一律跳过，以杜绝误报）。自带「有牙齿」用例，能复现并捕获本次这处历史缺陷。全包扫描当前**零违规** —— 说明该 bug 仅此一处且已清
- 行为端回归：`test_intel_crosswalk_default_asof` / `test_intel_prefill_default_asof` 覆盖**不带 `asof`** 的真实调用路径

### Verified

- 真机端到端（`D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`，只读；实例起在 `3021` 以避开占用中的 `3018`）：两条**裸调用**均 **HTTP 200** · `asof=2026-09-02`（replay 夹具日）· `writesBriefSqlite=false`
- 全量 `pytest packages apps`（`replay`）= **648 passed / 0 failed / 38.00 s**（`643` → `648`，+5）
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.7）

### Notes

- 纯缺陷修复：无指标 / 口径变化，**回测基线逐位不变**

## [3.13.6] - 2026-10-09

### Added

- **`B6` 回测可视化扩展**：Workbench `#backtest` 面板新增「组合净值曲线（B1 引擎 · 只读 market.db）」区块 —— **净值曲线 + 回撤带 + 逐日表三者共用同一份 `daily` 数组**，悬停图上某日即高亮对应表行、点表行也定位图上该点（逐日表联动）。仍是 Jinja + static，**未引入任何新前端依赖**（手写 `createElementNS` SVG，无 chart/echarts/plotly/d3）
- 新增组合指标 `portfolio.drawdown_series(equity_curve)`：逐点**瞬时**回撤（`equity / peak - 1`，每次创新高归零）的**单点定义**；非正权益日（停牌）跳过但保持**索引对齐**（图上第 i 点 == 表第 i 行）。`max_drawdown_from_curve` 改为返回该序列的最深点（同一模块内委派），**scalar 指标与图上回撤带不可能分叉**
- 新增 API `POST /api/research/backtest/portfolio`：只读 `STOCK_PLATFORM_ENGINE_MARKET_DB`，走与 `stock-platform-backtest` CLI **完全相同的代码路径**（`load_engine_bars` → `filter_universe` → `run_portfolio_backtest`）；返回对齐的 `daily[]`（`date` / `equity` / `ret` / `drawdown` / `n_positions` / `invested_ratio`）+ `B2`–`B5` 指标块 + `params`。无 DB / 非法 `universe` 一律 fail-closed（503 / 400 中文）

### Changed

- `apps/workbench`：`routes/research.py` 新增 `PortfolioBacktestRequest` + `_daily_from_curve()`；`openapi_models.py` 新增 `PortfolioBacktestResponse`；`templates/index.html` / `static/app.js` / `static/app.css` 扩展可视化。Workbench API 操作数 **58 → 59**（全量 API 目录测与计数断言同步）
- 包根 re-export `drawdown_series`

### Verified

- **零回归（纯重构）**：`drawdown_series` 落地后全周期（2020-01～2026-09）默认档指标与 `B5` 基线**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `max_drawdown` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64（加载 13.4 s + 回测 49.3 s）
- **pre-`B6` oracle 等价**：测试保留旧实现为 oracle，对 600 点（含停牌日）序列断言 `max_drawdown_from_curve` **逐位相等**，并把「最深处 == 序列最小值」写成不变量
- **真机端到端**（`D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`，3.14 GB，只读）：`POST /api/research/backtest/portfolio`（2025-09-01～2026-09-03）= **HTTP 200 · 18.5 s** · 245 交易日 · 85 笔 · 终值 46,502.02；`daily[0].ret is None`；`metrics.max_drawdown` **-0.193254** 与 `min(daily[].drawdown)` **逐位相等**
- 测试：全量 `pytest packages apps`（`replay`）= **643 passed / 0 failed / 37.22 s**（B6 新增 10 个用例：`drawdown_series` 5 + API/UI 契约 5）
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.6）

### Docs

- `docs/contracts/portfolio-metrics.md`：补 `drawdown_series` 口径与「最深处 = `max_drawdown_from_curve`」契约
- `docs/plans/trading-system-roadmap.md`：`B6` 标 done → **B 域（B1–B6）全部收官**
- `docs/ops/backtest-baseline.md`：补可视化端点入口与耗时口径

## [3.13.5] - 2026-10-09

### Added

- **`B5` 回测↔在线规则统一层**：新增 `rules.py` 作为交易规则的**单点定义**——`ExitPolicy` / `CooldownPolicy` / `DriftPolicy`（frozen dataclass）、`ExitDecision` / `DriftDecision`，纯函数 `evaluate_exit()` / `advance_peak()` / `evaluate_drift()`，以及共享交易限制 `limit_pct()` / `is_limit_up()` / `is_limit_down()`
- **在线路径**：新增 `position_review.review_positions()` —— 对当前持仓逐只给出 `hold` / `exit` / `trim` / `add`，**调用与回测完全相同的 rules 函数**（吸收 `V2-code-review-20260905` 检查重点 item 5）
- 新增 CLI `stock-platform-position-review`：自包含模式（holdings JSON 自带价）或富化模式（`--db` + `--asof` 只读 `market.db`，经 `compute_features` 取同源复权价与 `ma20`/`ma60`，并由 `entry_date` 定位 `held_days`）
- **冷静期**（`cooldown_days`）：出场后 N 会话内禁止同码再入场；**持仓偏差**（`drift_band`）：权重相对偏离超带即 `trim` / `add`。两者**默认关闭**（`0` / `None`）
- **口径契约**：`docs/contracts/trading-rules.md` —— 退出规则顺序与 reason 字符串 / 冷静期 / 持仓偏差 / 涨跌停判据 / T+1 / 单点定义双路调用契约 / 已知局限

### Changed

- `run_portfolio_backtest` 的**全部**交易判断改为委派 rules：退出走 `evaluate_exit()`、峰值走 `advance_peak()`、涨跌停走 `is_limit_up()` / `is_limit_down()`；删除内联退出逻辑与本地 `limit_pct()`，`_Position` 变为 `rules.PositionState` 的别名
- `params` 新增回显 `exit_policy` / `cooldown_days` / `drift_band`（供"两侧参数一致"断言）
- 包根 re-export `ExitPolicy` / `CooldownPolicy` / `DriftPolicy` / `evaluate_exit` / `evaluate_drift` / `review_positions` 等

### Verified

- **零回归（纯重构）**：默认档全周期指标与 `B4` 基线**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64；耗时 加载 13.3 s + 回测 47.0 s
- **冷静期对照**（`cooldown_days=10`）：`total_return` 0.898259（−0.41 pp）· `n_trades` 631 · `final_equity` 94912.95（**−204.69**，≈ −0.22%）· `sharpe` 0.7508 —— 低频组合同码快速再入场罕见，故影响小；属风险约束而非收益工具
- **单点定义断言**：`backtest.evaluate_exit is rules.evaluate_exit`、`backtest.ExitPolicy is rules.ExitPolicy`、`backtest._Position is rules.PositionState` 等全部为真（同一对象，非等价拷贝）
- **差分一致断言**：同一持仓状态下，在线路径给出的 `reason` 与回测所用规则函数的输出**逐字相同**；且回测 `params.exit_policy` 与 `rules.ExitPolicy()` 默认值相等
- 测试：`pytest packages/research` = **179 passed**（B5 新增 41 个用例）；全量 `pytest packages apps`（`replay`）= **633 passed / 0 failed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.5）

### Docs

- 新增 `docs/contracts/trading-rules.md` 并登记进 `scripts/check_docs.ps1` required
- `docs/ops/backtest-baseline.md`：新增退出/冷静期参数口径与冷静期对照
- `docs/plans/trading-system-roadmap.md`：`B5` 标 done（**关键路径项** `G1 → B1 → B5 → X4 → L1`）

## [3.13.4] - 2026-10-09

### Added

- **`B4` ETF 与资产类型支持**：`portfolio.asset_class(code)` **单点定义** —— 按共享前缀表返回 `stock` / `etf` / `fund`（`etf` = 命中 `_ETF_PREFIXES`；`fund` = 其余 `1xxxxx` / `5xxxxx`，**保守**按应税处理）；分类与印花税豁免由同一张表驱动，不可能分叉
- `run_portfolio_backtest(..., universe=)`：`stock`（默认，与引擎一致整体排除基金）/ `etf` / `all`（股票 + ETF 混池）；非法档位 `ValueError` fail-closed；旧参数 `exclude_funds` 保留为别名（显式传入时覆盖 `universe`）
- CLI 新增 `--universe {stock,etf,all}`（默认 `stock`），运行时在 stderr 回显入选行数 / 码数
- **分资产报告**：`compute_metrics(...)["by_asset"]` 按类给出 `n_trades` / `win_rate` / `avg_net_ret` / `turnover_notional`；`trades` 新增 `asset_class` 字段；既无 `code` 也无 `asset_class` 的交易跳过，空输入 = `{}`（**不编造**）
- **口径契约**：`docs/contracts/asset-classes.md` —— 三分类判定 / `universe` 三档语义 / 与免税绑定 / `by_asset` / 跨线对齐 / 实测发现
- 测试：新增 `test_asset_class.py`（语义 + **跨线互测**：静态解析引擎 `_is_fund` / `_is_etf` 前缀表 + `by_asset` 报告）

### Changed

- `backtest.py` 的基金过滤由「一刀切 `exclude_funds`」改为 `universe` 选择；**默认档 `universe="stock"` 与旧默认 `exclude_funds=True` 完全等价**
- `backtest.py` 与包根 re-export `asset_class` / `UNIVERSES`

### Verified

- **零回归**：`universe="stock"` 全周期指标**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64
- **宇宙对照**（同区间同参数，1618 日）：`stock` **+90.24%** / 630 笔 · `all` **+102.58%** / 609 笔（**ETF 0 笔**）· `etf` **-16.31%** / 9 笔
- **免税路径贯通实测**：混池中真实 ETF `515250` 卖出成本率 **8.54e-05**（仅佣金）vs 股票参照 `600519.SH` **5.854e-04**（佣金 + 万5 印花税）
- **三条诚实发现**（已写入契约 §6）：① 默认门槛 `min_pick_score=0.80` 下 ETF 全部被挡（ETF 合成分中位上限 0.50 vs 股票 0.86）→ **混池 ≠ ETF 配置**；② 入场闸门截面分位取自当日入选帧，加入 ETF 会改变股票入选 → `all` 数字**不可与 `stock` 横比**；③ 原始 ETF 池含非标准 / 流动性枯竭条目 → 作宇宙前须先清洗（X 域议题）
- `pytest packages/research` = **138 passed**（B4 新增 18 个用例）；全量 `pytest packages apps`（`replay`）= **592 passed / 0 failed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.4）

### Docs

- 新增 `docs/contracts/asset-classes.md` 并登记进 `scripts/check_docs.ps1` required
- `docs/ops/backtest-baseline.md`：新增 §3.2 资产类型 / 宇宙对照 + §6 已知限制补 ETF 名册未清洗
- `docs/plans/trading-system-roadmap.md`：`B4` 标 done

## [3.13.3] - 2026-10-09

### Added

- **`B3` 费用与摩擦模型配置化**：新增 `portfolio.CostModel`（frozen dataclass）—— `commission_rate` / `stamp_sell_rate` / `slippage_bps` / `min_commission` / `etf_stamp_exempt`，含 `trade_cost()`（比例）/ `costs()`（金额，含佣金下限）/ `fill_price()`（滑点后成交价）/ `zero()`（对标引擎 `--zero-cost`）
- **滑点**（此前完全缺失的摩擦项）：单边基点，**仅作用于成交价**（买入抬价、卖出压价）；选股 / 入场闸门 / 涨跌停判定 / 止损目标与移动止损**触发**一律读参考收盘价
- 回测引擎新增 `slippage_bps` / `min_commission` 参数；`trades` 的 `entry_price` / `exit_price` / `entry_value` / `exit_value` 改为**真实成交口径**（含滑点）
- CLI 新增 `--commission-rate` / `--stamp-sell-rate` / `--slippage-bps` / `--zero-cost`；运行时在 stderr 回显费用档
- **口径契约**：`docs/contracts/cost-model.md` —— 固化费率 / 滑点语义 / 比率与金额双 API / 免5 含义 / 跨线对齐 / 敏感性口径
- 测试：新增 `test_cost_model.py`（语义 + **跨线互测**：静态解析 `a-stock-engine/local_backtest.py` 的常量与 ETF 前缀表）

### Changed

- **费用单点定义**：费率常量、资产类型判定（`norm_code` / `is_fund` / `is_etf` / `_ETF_PREFIXES`）与 `trade_cost` 从 `backtest.py` 移入 `portfolio.py`；`backtest.py` 顶部 re-export，旧调用点 `from .backtest import ...` 不变（`backtest.CostModel is portfolio.CostModel` 为真）。这是 `B5`（回测↔在线规则统一层）的又一块铺路砖

### Fixed

- **买入侧计费不对称**：建仓与持仓成本基（`cost_basis`）原先硬用 `commission_rate`、绕过 `trade_cost()`，现统一走 `CostModel` 使买入腿与卖出腿对称。因 ETF 与股票买入佣金相同，**当前数值无害**，但消除了一引入滑点 / 分品种费率即漏计的隐性缺陷

### Verified

- **零回归**：默认档（滑点 0）全周期指标**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64 / `turnover_notional_per_year` 11.28 / `avg_hhi` 0.086483
- **成本敏感性**（全周期 1618 日 / 6964 码；权益差 vs 默认档）：零成本 **+1226.93** / 滑点 5 bps **−411.45** / 滑点 10 bps **−1442.73**（≈ 2.89% 收益）—— 费率拖累与 10 bps 滑点拖累同级，**摩擦不可忽略**
- **两线互测**：平台 `CostModel.trade_cost` 与引擎 `_trade_cost` 在 股票/ETF × 买/卖 四象限逐项相等；费率常量与 ETF 前缀表（30 项）一致
- `pytest packages/research` = **120 passed**（B3 新增 16 个用例）；全量 `pytest packages apps`（`replay`）= **574 passed / 0 failed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.3）

### Docs

- 新增 `docs/contracts/cost-model.md` 并登记进 `scripts/check_docs.ps1` required
- 新增 `docs/plans/b3-cost-model-milestone.md`（里程碑方案），`docs/plans/README.md` 登记
- `docs/plans/trading-system-roadmap.md`：`B3` 标 done
- `docs/ops/backtest-baseline.md`：新增成本敏感性小节

## [3.13.2] - 2026-10-09

### Added

- **`B2` 组合级指标补全**：`portfolio.compute_metrics` 新增 —— 成交额口径换手 `turnover_notional_per_year`（`Σ(entry_value+exit_value) / mean(equity) / years`）、持仓集中度 `avg_hhi` / `avg_top_weight`、真实暴露 `avg_invested_ratio`、持仓数 `avg_positions` / `max_positions`。缺失输入一律 `None`，**不编造**
- **`hhi()` 工具**：赫芬达尔-赫希曼指数，先归一化再平方求和（scale-free，对原始市值与权重同值；单票 = 1.0，n 只等权 = 1/n，空仓 = 0.0）
- 组合引擎净值曲线点新增 `hhi` / `top_weight` / `invested_ratio` **标量**（不引入 dict 列，CSV / JSON 输出不受影响）；`trades` 新增 `entry_value` / `exit_value` 成交额
- **口径契约**：`docs/contracts/portfolio-metrics.md` —— 固化年化基数（252）/ 无风险利率（0）/ 回撤符号 / 换手双口径 / 集中度口径 / 「不可横比」铁律
- 测试：`test_portfolio.py` 增补 HHI 与 B2 字段用例；`test_backtest.py` 增补曲线集中度与成交额用例

### Changed

- **指标实现单点化**：`compute_metrics` 移入 `portfolio.py` 作为唯一权威定义；`backtest.py` 改为顶部 `from .portfolio import compute_metrics` **re-export**（`backtest.compute_metrics is portfolio.compute_metrics` 为真），旧调用点 `from .backtest import compute_metrics` 不变。这是 `B5`（回测↔在线规则统一层）的铺路砖

### Verified

- `pytest packages/research` = **104 passed**（B2 新增 7 个用例）；全量 `pytest packages apps`（`replay`）= **558 passed / 0 failed / 19.00s**
- 全周期指标**逐位不变**：`total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `avg_hold_days` 35.41 / `final_equity` 95117.64 —— **仅新增字段，旧口径未动**
- 全周期耗时 **61.8 s**（加载 11.5 s + 回测约 50 s），新增逐日 HHI 计算**无感**
- 新口径实测（2020-01～2026-09，1618 日 / 6964 码）：成交额换手 **11.28 倍/年**、平均 HHI **0.0865**、平均最大单票权重 **10.17%**、平均仓位 **80.0%**、平均持仓 **13.6 只**、最大并发 **15**

### Docs

- 新增 `docs/contracts/portfolio-metrics.md` 并登记进 `scripts/check_docs.ps1` required
- `docs/plans/trading-system-roadmap.md`：`B2` 标 done
- `docs/ops/backtest-baseline.md` §3 回填集中度 / 成交额换手

## [3.13.1] - 2026-10-09

### Changed

- **行情库加载器提速 4.4×**：`backtest_cli.load_engine_bars` 原用 `WHERE date BETWEEN ? AND ? ORDER BY code,date`，全周期窗口需 **54.9 s**。同一窗口实测：`ORDER BY date`（命中 `idx_dp_date`）50.6 s、不排序 + pandas 排序 52.8 s、**全表流式 `SELECT` + 内存过滤仅 12.5 s** —— 该表只有 `idx_dp_date`，投影列迫使回表，`WHERE` 与索引均无收益。改为全表读取后在 pandas 内过滤 / 排序。**全周期回测 106 s → 65 s**（加载 11.5 s + 回测 48.6 s）

### Added

- `packages/research/tests/test_backtest_cli.py`：锁定加载器的日期窗口 / 代码过滤 / 排序 / 只读语义与 BSE 过滤（**8 passed**）

### Fixed

- 修正 `[3.13.0]` 条目中的测试计数笔误（**556 → 543**，实测；该版发布时全量为 543 passed）

### Verified

- 性能改动**零行为变化**：全周期指标逐位不变（`total_return` 0.902353、`cagr` 0.105348、`mdd` -0.171435、`sharpe` 0.7511、`n_trades` 630、`win_rate` 0.4619、`avg_hold_days` 35.41），分年收益与卖出原因分布全同
- 全量 `pytest packages apps`（`replay`）= **551 passed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.1）

### Docs

- `docs/ops/backtest-baseline.md` §5 新增加载器问题条目、§6 更新耗时
- `docs/ops/workbuddy-runtime-limits.md` §9 补充"提速后回到默认档"说明

## [3.13.0] - 2026-10-09

### Added

- **`B1` 组合级回测引擎**：`packages/research/src/stock_platform_research/backtest.py`——在 `lvrev` + `apply_entry_gates` 同一内核之上补齐持仓层（entry/peak/shares）、持有期（`min_hold` 45）、硬止损 / 目标止盈 / 趋势破位 / 移动止损、并发上限与 100 股取整、**跌停顺延 / 涨停跳过**，以及对齐 `local_backtest.py` 的费用模型（佣金万0.854 双边、印花税万5 仅卖出、ETF 免）
- **指标层**：年化 / 最大回撤 / 夏普 / 索提诺 / Calmar / 换手 / 胜率 / 平均持有
- **`stock-platform-backtest` CLI**：只读挂载 `STOCK_PLATFORM_ENGINE_MARKET_DB`，批量加载 `daily_price` 并输出净值曲线 CSV
- **回测基线报告**：`docs/ops/backtest-baseline.md`——2020-01～2026-09 全市场（1618 交易日 / 6964 码）

### Changed

- **`gates.apply_entry_gates` 向量化**：原逐行 `iterrows` 在全市场回测中达 ~880 万次调用，导致全周期回测超命令超时；每个分支均为"拒绝"，等价改写为"任一条件命中即拒绝"。**全周期回测 200 s → 106 s**。等价性由 `packages/research/tests/test_gates.py` 以原逐行实现为 oracle 证明（12 组随机数据 + 缺列场景）
- **复权修正**：引擎库 `close` 为未复权价而 `pct_chg` 为真实涨跌幅（复现：`600551.SH` 单日 close 跳变 -32.6% 而当日 `pct_chg` 仅 -10%）。`compute_features` 改用 `pct_chg`（混用标度自动判定）重建复权价，修复后极值交易归零（最差 -15.2%，无 <-20%）

### Verified

- `pytest packages/research/tests/test_backtest.py packages/research/tests/test_gates.py` = **17 passed**
- 全量 `pytest packages apps`（`replay`）= **543 passed**（2026-10-09 实测更正，原记 556 有误）
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.0）

### Baseline

- 总收益 **+90.24%**｜CAGR **+10.53%**｜最大回撤 **-17.14%**｜夏普 **0.751**｜胜率 **46.2%**｜630 笔｜平均持有 35.4 天
- 与 `a-stock-engine` 差异全部归因于口径（持有期 / 区间 / L0 闸门 / ST 与生存者过滤 / 复权），**不宣称复现引擎数字**（遵循 `empirical/BASELINE.md` §5 铁律）

## [3.12.6] - 2026-10-09

### Added

- **自有推进路线图**：`docs/plans/trading-system-roadmap.md`——既有规划（M0–M47 / U1–U8 / MR-1–MR-5）执行见底后重开产品目标，定义 G/B/S/X/L/C 六域里程碑（工程地基 / 回测 / 策略深化 / 选股 / 实盘 / 双线收口）与关键路径 `G1 → B1 → B5 → X4 → L1`
- **WorkBuddy 运行时限额实测**：`docs/ops/workbuddy-runtime-limits.md`——单请求 100 步、命令默认 120s（PowerShell 上限 600s）、上下文压缩阈值 60/70/90%、沙箱 6 程序黑名单、会话缓存上限 3000 MB；含对回测阶段的设计约束

### Changed

- **`G1` 工程地基（环境恢复）**：5 个 `stock_platform_*` 包 editable install 恢复；`pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）**526 passed / 0 failed**
- **`G2` 外部路径与 env 治理**：全仓仓根路径 `D:\workspace\git\` → `D:\workspace\stock_trading\` 迁移（**14 个文件**：README × 4、`docs/ops` × 5、`docs/upstream` × 2、`templates/index.html`、`.env.example`、`scripts/ops/stock-platform-daily.xml`）；`.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB` 实测指向 `a-stock-engine/data_cache/market.db`（3.14 GB，冒烟 600519 → 406 交易日）；计划任务 `WorkingDirectory` 修正，XML 编码声明 `UTF-16`→`UTF-8`（原声明与文件实际 UTF-8 字节不符）

### Verified

- `scripts/check_docs.ps1`：**OK**（VERSION=3.12.6，112 required files，139 md）
- `scripts/check_versions.ps1`：**OK**（VERSION 与 5 个 pyproject + 5 个 `__init__` 一致）
- `pytest packages apps`：**526 passed / 1 warning / 14.14s**

## [3.12.5] - 2026-09-23

### Added

- **MR-3 情报 ↔ brief 对照**：ADR [`docs/architecture/0053-intel-report-brief-crosswalk.md`](docs/architecture/0053-intel-report-brief-crosswalk.md)；Workbench `#intel-report` 与向导/今日推荐互跳；`GET /api/research/intel-report/crosswalk`（asof/宇宙只读对照）
- **MR-5 平台数据部分预填**：`GET /api/research/intel-report/prefill`（json/html）+「用平台数据预填预览」；填日历 / 已存 brief picks / 可选 concept_blocks / ops；缺能力进 `missing` 中文说明，保留 `{{占位符}}`；**不写** brief SQLite
- Workbench 测：`tests/test_intel_report.py` + OpenAPI / 全量 endpoint 注册（现 **58** 个 path+method）

### Changed

- 里程碑 MR-3/MR-5 → done；版本 **3.12.5**；**未**引入 WebSearch 主链 / Skill 运行时 import / M-E4 实盘

## [3.12.4] - 2026-09-23

### Added

- **market-report-dashboard 配方吸收（MR-1/2/4）**：三类 HTML 模板只读归档至 `docs/upstream/market-report-templates/`；Workbench `#intel-report` 入口 + `static/report-templates/` 预览；Skills 治理挂接；里程碑 [`docs/plans/market-report-dashboard-merge-milestones.md`](docs/plans/market-report-dashboard-merge-milestones.md)
- **小测**：Workbench UI / 静态模板可访问断言

### Changed

- 上游 README / 能力盘点 / AGENTS / ROADMAP / `check_docs` 短链同步；**未**引入 WebSearch 第二数据主链；版本 **3.12.4**

## [3.12.3] - 2026-09-22

### Added

- **Workbench 全量 API 自动化测**：`apps/workbench/tests/test_all_api_endpoints.py` — OpenAPI 56 个 path+method 参数化「每接口至少一击」+ 覆盖门禁；`/docs` `/redoc` `/openapi.json` 额外 smoke；replay 零公网；fail-closed 路径有意识断言 4xx/5xx

## [3.12.2] - 2026-09-22

### Changed

- **文档整理**：`.cursor/plans` 正式正文迁入 `docs/plans/`（能力盘点 / 合并路线图 / U 线 / M-D1·R1·A1）；新增 `docs/README.md`、`docs/engineering/`、`docs/upstream/` 配方摘要；plans 目录仅留索引指针；交叉链接与 `check_docs` 路径列表同步；版本 **3.12.2**

## [3.12.1] - 2026-09-22

### Added

- **Workbench OpenAPI**：全部 HTTP 路由补齐 `summary` / docstring、响应 envelope（`openapi_models.py`）、常见错误码；`/docs` `/redoc` `/openapi.json` 可用
- **OpenAPI 契约测**：`tests/test_openapi_contract.py`（路径存在 + 200 schema 非空 object）
- **测试分层**：pytest markers `unit` / `integration`；wizard / brief→paper→broker 标 integration
- **CI**：`monorepo` job 跑 `pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）；CONTRIBUTING 对齐

### Changed

- 文档：CONTRIBUTING / workbench README 写明分层命令与 `/docs` 入口；版本 **3.12.1**

## [3.12.0] - 2026-09-22

### Added

- **M-R5**：策略 A/B 进日用主路径旁路（`STOCK_PLATFORM_STRATEGY_AB` / `strategyAb`；**默认关闭**；不替换 picks）
- **M-U3**：ADR 0052 TSP UI 子集范围 **Accepted**
- **M-U4**：`#tsp-subset` 近 N 日 `direction_accuracy` SVG sparkline（零新前端依赖）
- **M-A4**：可选更深多角色 LLM 图（`STOCK_PLATFORM_DEEP_LLM_GRAPH`；非默认；fail-closed；禁 dataflows）
- **M-D6**：[`docs/ops/m-d6-batch-recipe-upstream-feedback.md`](docs/ops/m-d6-batch-recipe-upstream-feedback.md)
- **M-E3**：[`docs/ops/broker-port-honesty.md`](docs/ops/broker-port-honesty.md)（mock / experimental / 未接真实）
- **M-R4 深刀**：ICIR / `std_ic` / `summarize_factor_ic_from_rows` + `POST /api/research/backtest/factor-ic`

### Changed

- 能力域路线图 Later 余量收口（**M-E4 实盘仍门禁未开工**）；版本 **3.12.0**

## [3.11.1] - 2026-09-18

### Added

- **M-R3**：[`docs/ops/empirical-baseline-compare.md`](docs/ops/empirical-baseline-compare.md) + `compare_empirical_baseline`（只读对照，无双调度）
- **M-R4 薄刀**：`summarize_factor_ic` / Spearman rank IC（不进 brief 主路径）
- **M-A3**：`role_prompts`（政策/游资/解禁等）+ 所需 capabilities fail-closed
- **M-E2**：错哈希 / admission / order_guards 安全缺口回归测（SIMULATE）
- **M-D5**：[`docs/ops/m-d5-global-thin-gap.md`](docs/ops/m-d5-global-thin-gap.md)（美港薄缺口；不接期权/SEC）
- **M-S2**：[`docs/ops/skill-recipe-feedback-checklist.md`](docs/ops/skill-recipe-feedback-checklist.md)
- **Workbench**：`#concept-blocks` / `#pit-fundamentals` 只读面板

### Changed

- 能力域路线图 Later 首批收口；版本 **3.11.1**

## [3.11.0] - 2026-09-18

### Added

- **M-D3 `concept_blocks`**：能力矩阵第 13 项；`astock_http`（`slist`/`em_get`）+ `replay` fixtures；`GET /api/market/concept-blocks`；ADR 0051
- **M-D4 engine PIT 只读**：`get_fundamentals_pit` / `get_daily_basic_pit`；`GET /api/research/pit/fundamentals`；无 DB/缺表 fail-closed 中文；ADR 0050 → Accepted
- **M-R2 walk-forward 摘要**：`packages/research/walkforward.py` + `POST /api/research/backtest/walk-forward` + `#backtest` 折叠入口；契约 `docs/contracts/walk-forward-summary.md`
- **M-A2 评级边界**：`packages/agents/rating.py`（5 档 + 词边界矩阵测）；LLM 自由文本回退接线；禁 dataflows
- **M-U2**：绩效 `recentDays[]` 近 N 日 `direction_accuracy`；推荐页迷你 chips
- **M-E1**：[`docs/ops/v2-safety-test-mapping.md`](docs/ops/v2-safety-test-mapping.md)（不恢复 Futu）

### Changed

- 能力域合并路线图 Next 批次收口勾选；版本 **3.11.0**

## [3.10.7] - 2026-09-17

### Added

- **能力域合并 Now 批次（文档）**：M-D1 缺口对照表、M-D2 ADR 0050（engine PIT 只读草案）、M-R1 TSP 首刀选型（walk-forward 摘要）、M-A1 TA 可移植清单、M-S1 Skills 治理 SSOT（`docs/ops/skills-governance.md`）

### Changed

- **M-U1 Workbench 可读性**：导航 ①向导→②推荐→③纸面；向导步骤清单；推荐/历史/复盘空态与中文 tip；交叉锚点链接

## [3.10.6] - 2026-09-15

### Added

- **回测 ↔ 今日推荐打通**：`#backtest` 逐日表「看推荐」→ 跳转 `#recommend` 加载该日 picks（已存 SQLite 则回看+复盘，否则按同宇宙重生成）；回测 `days[]` 带 `pickSymbols`
- **推荐页绩效摘要条**：pending / settled / `direction_accuracy` + 回测/绩效/策略对比快捷链；空态/fail-closed 文案统一
- **策略对比接 engine 真面板**：`POST /strategy/compare` 无 body.panel 时优先 `build_multi_day_pit_panel`（engine/daily）；标注 `panelSource`；`requireEngine` 时无源 503；否则回退 fixture 并写 `panelNote`
- **日批一键 live+落库+结算**：`Invoke-DailyPipeline.ps1 -LiveDay`；CLI `--settle-after`（记入 JSONL + 结算）；`daily-pipeline.md` 更新

### Changed

- 里程碑计划：U8 联通切片收口；下一档见 Now/Next/Later

## [3.10.5] - 2026-09-15

### Added

- **U7 最小切片（回测进 Workbench）**：`POST /api/research/backtest/rolling-review` + `#backtest` 区；对 watch/full 宇宙按最近 N 日滚动推荐并用 `review_stored_brief` 汇总 `direction_accuracy` / 样本数；优先只读 `STOCK_PLATFORM_ENGINE_MARKET_DB`；无日线 fail-closed 中文提示
- **U6 轻量**：向导 / 今日推荐 / defaults 可选 `universeTier`（core|watch|full）；切层级重载 symbols；明示勿一次全市场
- `.env.example` 强化 `STOCK_PLATFORM_ENGINE_MARKET_DB` 中文说明（与 brief SQLite 分离）

### Changed

- 里程碑：U6/U7 最小切片收口为 done（轻量）；完整策略 A/B 与全市场仍后置

## [3.10.4] - 2026-09-15

### Added

- **pending 自动结算**：`GET /api/research/performance?autoSettle=true`（默认）与 `POST /performance/settle`；有足够后续日线时把 JSONL pending 结算进盘，`direction_accuracy` 反映每日推荐；CLI `--settle-daily`
- **a-stock-engine 日线适配**：`engine_sqlite` + `STOCK_PLATFORM_ENGINE_MARKET_DB`（只读 `market.db`/`daily_price`）；预设 `cn_engine_sqlite`；结算优先用本地库；文档 `docs/ops/engine-market-db.md`
- UI：`#performance` 显示本次新结算 / settle 源；「结算 pending」按钮

### Changed

- 里程碑 Next（pending 自动结算）收口为 done

## [3.10.3] - 2026-09-15

### Added

- **U3 复盘 UI**：历史推荐「回看 / 复盘」→ T+1/T+5 明细表（pending / 收益 / 方向对错）；汇总 `direction_accuracy` 与 performance 口径对齐
- **推荐 → 绩效闭环**：生成 brief 落库成功后自动 `log_brief_decisions`（同 asof+symbol 幂等跳过）；`#performance` 展示 pending；一键「记入当前 asof」；`POST /performance/log-brief` 支持 `fromStore`
- **U5**：`/api/ops/health` 增加 `providerPreset` / `briefFallback` / `supplementTokenConfigured`（仅布尔）；运维面板可见
- **U4**：`stock-platform-daily` / `Invoke-DailyPipeline.ps1` 支持 `-Provider tushare`（及别名）；`STOCK_PLATFORM_DAILY_PROVIDER`；缺 token fail-closed；`daily-pipeline.md`「真实日用」段
- 文档：`live-startup.md` 日用最小步骤；`.env.example` 日批 / 绩效路径说明

### Changed

- 里程碑计划按「商用可用最短路径」重排 Now（U3 UI → 闭环 → U5 → U4 → U1 冒烟）

## [3.10.2] - 2026-09-15

### Added

- **U2 每日 brief 持久化（SQLite）**：`STOCK_PLATFORM_DB_URL`（默认 `sqlite:///./data/stock_platform.db`）
  - 薄 repository：`stock_platform_research.persistence`（业务不绑死 SQLite 方言；日后可换 PG）
  - 权威存档字段：asof / provider / universe / picks / softGates / gatesRelaxed / dataNote / generatedAt / environment=SIMULATE
  - 同日重复生成：**按 asof 幂等覆盖**
  - Workbench：生成推荐默认自动落库；`GET /api/research/briefs` 历史列表；`GET /api/research/briefs/{asof}` 回看
  - UI「今日推荐」历史表；日批 `run_daily_pipeline` 与 Workbench 共用同一 writer
  - U3 雏形：`GET /api/research/briefs/{asof}/review`（T+1 收益 / pending；完整复盘后续）
  - 文档：ADR 0049 实现节；`.env.example` 已有中文说明；`*.db` / `/data/` 已在 `.gitignore`

### Fixed

- **可用的「今日推荐」路径**：向导 / `#recommend` 默认 asof 按数据源选择（live→最近 CN 交易日；replay→样例日 `2026-09-02`）；主按钮「生成今日推荐」；向导成功后跳转并渲染 TopN 卡片
- **live 日线失败显式回退**：`astock_http` 传输失败时，若已设 `STOCK_PLATFORM_TUSHARE_TOKEN` 则回退 `tushare_http` 并标注「已回退 Tushare」；仅当 `STOCK_PLATFORM_BRIEF_FALLBACK=replay` 才回退 fixtures（不静默假数据）
- **空 picks 可读说明**：截面为空或闸门滤尽时返回中文 `emptyPicksMessage` / `emptyPicksTip`；默认 `softGates` 在闸门过严时软化展示演示排序
- **友好错误**：ConnectionError 等上游中断返回中文 tip（非整段 traceback）

## [3.10.0] - 2026-09-15

### Added

- **Tushare 兼容 HTTP 补充源**（ADR 0048）：`TushareHttpProvider` / `tushare_http`
  - 首切片矩阵能力：`daily`（`api_name=daily`，不复权；成交额千元→元）
  - helper：`get_trade_cal`（`api_name=trade_cal`，不进矩阵）
  - raw HTTP POST，无 `tushare` SDK / MCP 硬依赖；可注入 `post_json`（CI 零公网）
  - 环境变量：`STOCK_PLATFORM_TUSHARE_TOKEN` / `STOCK_PLATFORM_TUSHARE_URL`（默认 `https://t.xiaodefa.top/`）
  - 预设 `cn_tushare_http`（daily→tushare_http，其余 CN 仍 astock_http）；**生产默认仍为 `cn_astock_http`**
  - **安全**：切勿把真实 token 提交进 git / CHANGELOG / ROADMAP；`.env.example` 仅占位符

## [3.9.5] - 2026-09-15

### Fixed

- **Workbench 向导 daily brief / 东财连接中断**：`em_get` 对 `RemoteDisconnected`/`ConnectionError` 退避重试（`EM_HTTP_RETRIES`）；会话复用并保持 `STOCK_PLATFORM_HTTP_TRUST_ENV=0`；`get_daily` 单标的失败可继续（全失败才报错）；向导返回 **503** 中文 tip（可设 `replay` 离线，不静默假数据）；交易仍 SIMULATE

## [3.9.4] - 2026-09-14

### Fixed

- **Workbench 日用纸面 UX**：向导 /「一键到纸面」/ 建草稿在无 active strategy 时自动 ensure 默认 SIMULATE 策略（幂等），状态文案「已自动激活默认纸面策略」；纸面区提供「激活默认策略」；常见执行错误改为中文 detail（仍不绕过时间窗等闸门，无实盘）

## [3.9.3] - 2026-09-14

### Changed

- **Workbench 行情查询结果可读性**：日 K OHLCV 表、实时快照卡片、资金流/财务万亿格式、五档买卖着色；中文表头；空态中文；原始 JSON 默认折叠；补 realtime 面板

## [3.9.2] - 2026-09-14

### Changed

- **Workbench UI 结构化扫读**：向导步骤条、运维/纸面/broker 键值、矩阵可用 pill、绩效 stat、辩论 rounds；实验区 JSON 默认折叠；导航高亮（ADR 0047 补全）

## [3.9.1] - 2026-09-14

### Changed

- **Workbench UI 日用抛光（ADR 0047）**：主流程（向导 / 推荐卡片 / 纸面）置顶；行情工具、运维矩阵、实验区折叠；推荐可读卡片（symbol / score / reasons）；原始 JSON 默认折叠；锚点自动展开祖先 `<details>`

## [3.9.0] - 2026-09-14

### Changed

- **M47 生产 live 行情默认**：Workbench 启动偏好默认 `cn_astock_http`（全 CN 能力 → `astock_http` / `em_get`）
  - CI / pytest：`STOCK_PLATFORM_PROVIDER_PRESET=replay`（fixture + GitHub Actions）保持零公网
  - 美港：`us_hk_global_http` 预设（daily/realtime → `global_http`）
  - 上游失败 fail-closed（熔断 503 / HTTP 502 / 缺方法 501）；不静默回退 fixtures
  - 默认 `STOCK_PLATFORM_HTTP_TRUST_ENV=0`（忽略坏系统代理）
  - 文档：`docs/ops/live-startup.md`；交易仍 paper / SIMULATE（`liveTradingEnabled=false`）

## [3.8.1] - 2026-09-14

### Fixed

- **日流水线 replay 默认可跑通**：样例宇宙（`600519`/`000001`/`510300`）对齐 providers fixtures；日线扩至 ≥60 根以支撑 lvrev；补齐 `fund_flow`/`adj_factor`/`full_minute`；文档命令与 `test_daily_pipeline_repo_fixtures_nonempty_picks` 断言 exit 0 + 非空 picks

## [3.8.0] - 2026-09-14

### Added

- **Phase E 日用稳定收口（M39–M46）**
  - M39：分层宇宙 + 可读推荐理由（ADR 0040）
  - M40：`stock-platform-daily` refresh→brief 流水线（ADR 0041）
  - M41：`sector_fund_flow` / `news`（ADR 0042）
  - M42：日历 2028+ + Task Scheduler/cron（ADR 0044）
  - M43：组合回测指标 + 纸面 fills 对齐绩效（ADR 0043）
  - M44：LLM 预算/截断/降级（ADR 0045）
  - M45：Workbench IA + 一键向导（ADR 0046）
  - 默认仍 paper + replay + SIMULATE；无 SPA；无真实券商；同花顺真实 transport 仍 backlog

## [3.7.0] - 2026-09-14

### Added

- **大里程碑 M45 完成**：Workbench IA + 一键向导
  - 顶栏分区：日用向导 / 推荐 / 纸面 / 运维；`#wizard` + `#ops`
  - `POST /api/research/wizard/daily`（refresh→brief→to-paper；分步可见失败）
  - ADR 0046；无 SPA；无实盘默认文案

## [3.6.0] - 2026-09-14

### Added

- **大里程碑 M44 完成**：LLM 成本/质量控制
  - 调用/token 预算；截断告警（含 Responses incomplete）；超限默认降级 deterministic
  - ADR 0045；默认仍 deterministic；`[llm]` 仍为可选 extra

## [3.5.0] - 2026-09-14

### Added

- **大里程碑 M43 完成**：组合回测加深 + 绩效对齐纸面成交
  - `portfolio_metrics` / `run_portfolio_pit`（回撤、换手、成交数）
  - `align_fills_to_performance` 从纸面 fills 回填 JSONL；`direction_accuracy` 口径不变
  - ADR 0043；默认 SIMULATE；CI fixtures

## [3.4.0] - 2026-09-14

### Added

- **大里程碑 M42 完成**：日历 2028+ + Task Scheduler/cron 运维包
  - CN/US/HK 静态休市日延伸至 2028+（provisional）
  - `scripts/ops/Invoke-DailyPipeline.ps1` + Task Scheduler XML + cron 样例
  - `docs/ops/scheduler.md` / `calendar-maintenance.md`；ADR 0044

## [3.3.0] - 2026-09-14

### Added

- **大里程碑 M41 完成**：板块资金流 / 新闻特征
  - 能力 `sector_fund_flow` / `news`；replay + `astock_http`（`em_get`）
  - 契约 + fixtures；workbench API/薄 UI；缺能力 fail-closed
  - ADR 0042；默认 replay；CI 零公网

## [3.2.0] - 2026-09-14

### Added

- **大里程碑 M40 完成**：定时 refresh→brief 日流水线
  - `run_daily_pipeline` + CLI `stock-platform-daily`；产物 `briefs/{asof}` + `latest.json`
  - 同 asof 幂等覆盖；失败 fail-closed 写 `failure.json`
  - `docs/ops/daily-pipeline.md`；ADR 0041；默认 replay

## [3.1.0] - 2026-09-14

### Added

- **大里程碑 M39 完成**：日用宇宙扩容 + 可读推荐理由
  - 分层宇宙 `core` / `watch` / `full`（`load_universe_tiers`）；样例 `universe_cn_daily.json`
  - brief `reasons[]` + `reasonSummary`（保留兼容 `reason`）；`#recommend` 展示中文摘要
  - `docs/ops/daily-universe.md`；ADR 0040；CI 仍用小 fixture；默认 replay + SIMULATE

## [3.0.0] - 2026-09-14

### Added

- **Phase D 同花顺模拟盘收口（M35–M38）**
  - M35：`BrokerPort` / `PaperBroker` / `resolve_broker`（ADR 0036）
  - M36：`ThsSimBroker` + mock transport；experimental HTTP 扩展点（ADR 0037）
  - M37：`GatedBroker` / admission 接到 `ths_sim`（ADR 0038）
  - M38：brief → broker E2E；`GET /api/broker/status`；`#broker` 只读面板（ADR 0039）
  - 默认仍 `STOCK_PLATFORM_BROKER=paper` + replay；SIMULATE；无实盘
  - 真实 THS HTTP：**experimental/pending**（无稳定公开零售模拟盘 API）

## [2.9.0] - 2026-09-14

### Added

- **大里程碑 M37 完成**：风控闸门接到外部模拟
  - `assert_sim_gates` / `GatedBroker`；ths_sim 复用 timing/window/idempotency/admission
  - ADR 0038

## [2.8.0] - 2026-09-14

### Added

- **大里程碑 M36 完成**：同花顺模拟盘适配器
  - `ThsSimBroker`；`MockThsTransport`（CI 零公网）；`ExperimentalThsHttpTransport` fail-closed
  - Env：`STOCK_PLATFORM_THS_MODE` / `STOCK_PLATFORM_THS_*`；ADR 0037

## [2.7.0] - 2026-09-14

### Added

- **大里程碑 M35 完成**：执行端口抽象
  - `BrokerPort` / `PaperBroker` / `ExternalSimBroker`；Order/Fill/Position/Account 契约
  - `STOCK_PLATFORM_BROKER=paper|ths_sim`（默认 paper）；ADR 0036

## [2.6.0] - 2026-09-14

### Added

- **Phase C 投研稳定收口（M32–M34）**
  - M32：推荐绩效 JSONL + `direction_accuracy` 口径（ADR 0033）
  - M33：可选 LLM 辩论（默认确定性；`[llm]` fail-closed；ADR 0034）
  - M34：策略配置版本化 + `run_pit_long_only` 对比入口（ADR 0035）
  - 默认仍 replay；SIMULATE；无同花顺 / 实盘 / SPA

## [2.5.0] - 2026-09-14

### Added

- **大里程碑 M33 完成**：可选 LLM 辩论挂在 TopN 之后
  - 默认仍 M12 确定性 `engine=deterministic`
  - `engine=llm` + `[llm]` optional-extra；缺依赖/密钥 fail-closed
  - `POST /api/research/brief/debate`；`GET /api/debate/report?engine=`
  - ADR 0034；mocked LLM 单测

## [2.4.0] - 2026-09-14

### Added

- **大里程碑 M32 完成**：推荐决策绩效统计
  - JSONL 决策日志 + `compute_performance`（`direction_accuracy` / `avg_return` / `up_rate` 口径）
  - CLI `stock-platform-performance`；`GET /api/research/performance`；工作台 `#performance`
  - ADR 0033；确定性 fixtures

## [2.3.0] - 2026-09-14

### Added

- **Phase B 运维稳定收口（M29–M31）**
  - M29：`stock-platform-refresh` 日 K / 复权因子 / 资金流 / full_minute 落盘（ADR 0030）
  - M30：live 偏好模板 + 东财熔断（ADR 0031）
  - M31：`GET /api/ops/health` + fixture 录制文档（ADR 0032）
  - 默认仍 replay；SIMULATE；CI 零公网

## [2.2.0] - 2026-09-14

### Added

- **大里程碑 M30 完成**：live 偏好模板 + 东财节流/熔断
  - 预设 `replay` / `cn_astock_http` / `us_hk_global_http`（启动默认仍 replay）
  - `EM_CIRCUIT_FAILURES` / `EM_CIRCUIT_COOLDOWN`；`EastmoneyClient.snapshot()`
  - workbench `GET /api/settings/presets` + `POST .../apply`

## [2.1.0] - 2026-09-14

### Added

- **大里程碑 M29 完成**：CN 日数据刷新 / full_minute 落盘
  - `run_refresh` / `stock-platform-refresh`；重试 + manifest；`STOCK_PLATFORM_REFRESH_DIR`
  - ReplayTransport 文件名；CI `--provider replay`；ADR 0030

## [2.0.0] - 2026-09-14

### Added

- **Phase A 产品稳定（M24–M28）**：日更选股推荐 + 纸面交易闭环
  - M24 宇宙 + PIT 截面面板（ADR 0029）
  - M25 盘前简报（`build_premarket_brief` / CLI / `GET /api/research/brief`）
  - M26 工作台「今日推荐」UI
  - M27 TopN → PaperLedger 草稿（SIMULATE；默认 CN）
  - 默认仍 replay；无同花顺/实盘；无 LLM；无 SPA

## [1.20.0] - 2026-09-14

### Added

- **大里程碑 M27 完成**：Recommend → PaperLedger
  - `POST /api/research/brief/to-paper`；UI 一键纸面草稿；SIMULATE only；默认 market=CN
  - 复用 timing/window/freshness；`liveTradingEnabled=false`

## [1.19.0] - 2026-09-14

### Added

- **大里程碑 M26 完成**：工作台「今日推荐」
  - UI `#recommend` + TopN 分数/理由表；链接日 K / 纸面；默认 replay

## [1.18.0] - 2026-09-14

### Added

- **大里程碑 M25 完成**：盘前简报批处理
  - `build_premarket_brief` / `stock-platform-brief`；`GET /api/research/brief`
  - lvrev + entry gates → TopN + reasons；默认 replay；CI 零公网

## [1.17.0] - 2026-09-14

### Added

- **大里程碑 M24 完成**：CN 宇宙 + PIT 日截面面板（ADR 0029；`load_universe` / `build_cross_section_panel` / CSV）
  - 空宇宙 fail-closed；注入 providers；默认仍无公网抓取

## [1.16.1] - 2026-09-14

### Added

- M24.1：CN 宇宙 + PIT 日截面面板（ADR 0029）
  - `load_universe` / `build_cross_section_panel` / `panel_to_csv`；空宇宙 fail-closed
  - 注入 daily（可选 adj_factor / fund_flow）；CI 零公网

## [1.16.0] - 2026-09-14

### Added

- **大里程碑 M23 完成**：CN 复权套价（`apply_adjust`；qfq 除 / hfq 乘；消费 daily + adj_factor）
  - ADR 0028；workbench API/UI；默认仍 replay；不新增能力 id；空因子 fail-closed

## [1.15.2] - 2026-09-14

### Added

- M23.2：workbench `GET /api/market/daily-adjusted` + UI `#daily-adjusted`；默认偏好 replay

## [1.15.1] - 2026-09-14

### Added

- M23.1：CN 复权套价 `apply_adjust`（ADR 0028）
  - qfq 除 / hfq 乘；空因子 fail-closed；不新增能力 id；CI 零公网

## [1.15.0] - 2026-09-14

### Added

- **大里程碑 M22 完成**：CN 全量分钟（能力矩阵 `full_minute`；replay + `em_get` 当日 1m 批量）
  - ADR 0027；workbench API/UI；默认仍 replay；与多频 `minute` 区分；无后台落盘 / get_intraday_latest

## [1.14.2] - 2026-09-14

### Added

- M22.2：workbench `GET /api/market/full-minute` + UI `#full-minute`；默认偏好 replay

## [1.14.1] - 2026-09-14

### Added

- M22.1：CN 全量分钟 `full_minute`（激活矩阵第七项；ADR 0027）
  - `ReplayProvider` / `AStockHttpProvider.get_full_minute`；东财 push2his `klt=1`（em_get）；fixtures；与多频 `minute` 区分；CI 零公网

## [1.14.0] - 2026-09-14

### Added

- **大里程碑 M21 完成**：CN 个股复权因子（能力矩阵 `adj_factor`；replay + 新浪 qfq/hfq HTTP）
  - ADR 0026；workbench API/UI；默认仍 replay；mootdx / 东财复权备胎 / apply_adjust 套价不做

## [1.13.2] - 2026-09-14

### Added

- M21.2：workbench `GET /api/market/adj-factor` + UI `#adj-factor`；默认偏好 replay

## [1.13.1] - 2026-09-14

### Added

- M21.1：CN 复权因子 `adj_factor`（激活矩阵第二项；ADR 0026）
  - `ReplayProvider` / `AStockHttpProvider.get_adj_factor`；新浪 qfq/hfq（非 em_get）；fixtures；CI 零公网

## [1.13.0] - 2026-09-14

### Added

- **大里程碑 M20 完成**：CN 个股财务报表（能力矩阵 `financial`；replay + 新浪三表 HTTP）
  - ADR 0025；workbench API/UI；默认仍 replay；mootdx / 东财财报备胎不做

## [1.12.2] - 2026-09-14

### Added

- M20.2：workbench `GET /api/market/financial` + UI `#financial`；默认偏好 replay

## [1.12.1] - 2026-09-14

### Added

- M20.1：CN 财务报表 `financial`（激活矩阵第六项；ADR 0025）
  - `ReplayProvider` / `AStockHttpProvider.get_financial`；新浪三表（非 em_get）；fixtures；CI 零公网

## [1.12.0] - 2026-09-14

### Added

- **大里程碑 M19 完成**：CN 个股五档盘口（能力矩阵 `depth5`；replay + `em_get` push2 stock/get）
  - ADR 0024；workbench API/UI；默认仍 replay；mootdx / 交易所官方备胎不做

## [1.11.2] - 2026-09-14

### Added

- M19.2：workbench `GET /api/market/depth5` + UI `#depth5`；默认偏好 replay

## [1.11.1] - 2026-09-14

### Added

- M19.1：CN 五档盘口 `depth5`（激活矩阵第五项；ADR 0024）
  - `ReplayProvider` / `AStockHttpProvider.get_depth5`；fixtures；量=手；CI 零公网

## [1.11.0] - 2026-09-14

### Added

- **大里程碑 M18 完成**：CN 个股分钟 K（能力矩阵 `minute`；replay + `em_get` push2his kline）
  - ADR 0023；workbench API/UI；默认仍 replay；`full_minute` / 腾讯备胎不做

## [1.10.2] - 2026-09-14

### Added

- M18.2：workbench `GET /api/market/minute` + UI `#minute`；默认偏好 replay

## [1.10.1] - 2026-09-14

### Added

- M18.1：CN 分钟 K `minute`（激活矩阵第四项；ADR 0023）
  - `ReplayProvider` / `AStockHttpProvider.get_minute`；fixtures；北京墙钟 naive；CI 零公网

## [1.10.0] - 2026-09-14

### Added

- **大里程碑 M17 完成**：CN 个股限售解禁（能力矩阵 `unlock`；replay + `em_get` datacenter）
  - ADR 0022；workbench API/UI；默认仍 replay；全市场解禁日历不做

## [1.9.2] - 2026-09-14

### Added

- M17.2：workbench `GET /api/market/unlock` + UI `#unlock`；默认偏好 replay

## [1.9.1] - 2026-09-14

### Added

- M17.1：CN 限售解禁 `unlock`（能力矩阵第十项；ADR 0022）
  - `ReplayProvider` / `AStockHttpProvider.get_unlock`；fixtures；空窗口不崩；CI 零公网

## [1.9.0] - 2026-09-14

### Added

- **大里程碑 M16 完成**：CN 个股龙虎榜（能力矩阵 `lhb`；replay + `em_get` datacenter）
  - ADR 0021；workbench API/UI；默认仍 replay；全市场日榜 / 交易所备胎不做

## [1.8.2] - 2026-09-14

### Added

- M16.2：workbench `GET /api/market/lhb` + UI `#lhb`；默认偏好 replay

## [1.8.1] - 2026-09-14

### Added

- M16.1：CN 龙虎榜 `lhb`（能力矩阵第九项；ADR 0021）
  - `ReplayProvider` / `AStockHttpProvider.get_lhb`；fixtures；空窗口不崩；CI 零公网

## [1.8.0] - 2026-09-14

### Added

- **大里程碑 M15 完成**：CN 日级资金流（能力矩阵 `fund_flow`；replay + `em_get`）
  - ADR 0020；workbench API/UI；默认仍 replay；分钟/板块资金流与龙虎榜不做

## [1.7.2] - 2026-09-14

### Added

- M15.2：workbench `GET /api/market/fund-flow` + UI `#fund-flow`；默认偏好 replay

## [1.7.1] - 2026-09-14

### Added

- M15.1：CN 日级资金流 `fund_flow`（能力矩阵第八项；ADR 0020）
  - `ReplayProvider` / `AStockHttpProvider.get_fund_flow`；fixtures；CI 零公网

## [1.7.0] - 2026-09-14

### Added

- **大里程碑 M14 完成**：多市场纸面 timing（CN/US/HK 日历 + 本地时区）
  - ADR 0019；`PaperLedger` / workbench 可选 `market`（默认 CN）；半日市 / 实盘不做

## [1.6.2] - 2026-09-14

### Added

- M14.2：PaperLedger / workbench /api/paper/* 可选 market（默认 CN）；草稿 marketId

## [1.6.1] - 2026-09-14

### Added

- M14.1：纸面 timing 支持 `market=`（CN/US/HK）；`market_now` / `daily_bar_final_at`（ADR 0019）
  - 默认仍 CN；`china_now` / `CHINA_TZ` 保留为别名

## [1.6.0] - 2026-09-14

### Added

- **大里程碑 M13 完成**：US/HK 静态交易日历（对标 CN；MarketStrategy 自动生效）
  - ADR 0018；纸面默认仍 CN timing；不拉交易所 API

## [1.5.2] - 2026-09-14

### Added

- M13.2：`MarketStrategy` US/HK 假日验收；`market-strategy` / providers README / upstream-archive 同步

## [1.5.1] - 2026-09-14

### Added

- M13.1：US/HK 静态休市日表 + `get_trading_calendar` 通用加载（ADR 0018）

## [1.5.0] - 2026-09-14

### Added

- **大里程碑 M12 完成**：确定性 Bull/Bear/Risk 轻量辩论（无 LLM）
  - `/api/debate/report` + UI；ADR 0017

## [1.4.2] - 2026-09-14

### Added

- M12.2：`GET /api/debate/report` + UI `#debate` 区

## [1.4.1] - 2026-09-14

### Added

- M12.1：确定性 `build_debate_report` / Bull·Bear·Risk（ADR 0017；无 LLM）

## [1.4.0] - 2026-09-14

### Added

- **大里程碑 M11 完成**：Workbench 最小 UI（`GET /` 单页操作台）
  - 能力矩阵 / 日 K / 纸面 status；ADR 0016

## [1.3.2] - 2026-09-14

### Added

- M11.2：UI 三区交互（矩阵 / 日 K / 纸面）；409 fail-closed 可见；可切 daily 偏好

## [1.3.1] - 2026-09-14

### Added

- M11.1：workbench `GET /` Jinja2 壳 + `/static`（ADR 0016）

## [1.3.0] - 2026-09-14

### Added

- **大里程碑 M10 完成**：CN 静态交易日历（休市日表 + timing / MarketStrategy 共用）
  - ADR 0015；US/HK 假日表见后续 M13 / ADR 0018

## [1.2.2] - 2026-09-14

### Added

- M10.2：`MarketStrategy.is_trading_day` 与纸面 `timing` 共用 CN 日历
- `completed_bar_cutoff` 回退跳过非交易日；execution 依赖 providers
- 修复：包内 `data/cn_closed_days.txt` 不再被根 `.gitignore` 的 `data/` 规则忽略

## [1.2.1] - 2026-09-14

### Added

- M10.1：`TradingCalendar` / `get_trading_calendar` + 静态 `cn_closed_days.txt`（ADR 0015）

## [1.2.0] - 2026-09-14

### Added

- **大里程碑 M9 完成**：可选美港 live HTTP（`GlobalHttpProvider` / Yahoo + 新浪）
  - workbench preferences 可切 `global_http`；默认仍 replay
  - ADR 0014；`a-stock-engine` 归档横幅

## [1.1.2] - 2026-09-14

### Added

- M9.2：workbench 注册 `GlobalHttpRouter`，preferences 可切 `global_http`（默认仍 replay）

## [1.1.1] - 2026-09-14

### Added

- M9.1：`GlobalHttpProvider` / `GlobalHttpRouter`（Yahoo 日 K + 新浪实时）
- ADR 0014；能力矩阵 `global_http` usable
- `a-stock-engine` README 归档横幅（指向 stock-platform）

## [1.1.0] - 2026-09-14

### Added

- **大里程碑 M8 完成**：可选 A 股 live HTTP（`AStockHttpProvider` via `em_get`）
  - 默认仍 replay；preferences 可切 live
  - ADR 0013

### Notes

- `global_http` 仍 pending；封禁时降级 replay，禁止裸东财 URL

## [1.0.2] - 2026-09-14

### Added

- M8.2 验收：workbench 注册 `astock_http` 实例，可通过 preferences 切换（默认 replay）

## [1.0.1] - 2026-09-14

### Added

- `AStockHttpProvider`：东财日 K / 实时经 `em_get`（ADR 0013）
- 能力矩阵 `astock_http` usable；单测注入 JSON，CI 不打公网

## [1.0.0] - 2026-09-14

### Added

- **大里程碑 M7 完成 / 产品 v1.0.0**
  - 上游归档说明与 v1 产品边界（ADR 0012）
  - 产品化文档与发版检查清单
  - 版本一致性脚本接入 CI

### Notes

- v1.0 = 可发布研究与纸面决策平台骨架（默认 replay；live HTTP / 实盘仍延期）
- 自本版本起破坏契约须 MAJOR

## [0.7.3] - 2026-09-14

### Added

- M7.3 验收：`release-checklist.md`、`check_versions.ps1`、CI version job

## [0.7.2] - 2026-09-14

### Changed

- README / CONTRIBUTING / AGENTS 按 v1.0 交付面改写
- 修复 upstream-archive 示例链接（避免 docs 自检断链）

## [0.7.1] - 2026-09-14

### Added

- `docs/upstream-archive.md`：上游参考仓归档总表与红线
- ADR 0012：v1.0 产品边界
- （同树预置）产品化 README / 发版清单 / `check_versions.ps1`，验收见 0.7.2 / 0.7.3

## [0.7.0] - 2026-09-14

### Added

- **大里程碑 M6 完成**：纸面执行安全模型
  - `packages/execution` broker-free 内核（吸 V2 结论，无券商 SDK）
  - SIMULATE-only / live=false；草稿≠激活；窗口外禁补单；draftId 幂等
  - workbench `/api/paper/*`

### Notes

- Admission 通过 ≠ 策略已证明；下一步 M7 产品收敛 / 上游归档

## [0.6.3] - 2026-09-14

### Added

- M6.3 验收：workbench 纸面路由与显式激活（无 live 开关）

## [0.6.2] - 2026-09-14

### Added

- M6.2 验收：`PaperLedger` decision_only / 窗口外零订单 / draftId 幂等回放

## [0.6.1] - 2026-09-14

### Added

- `packages/execution`：纸面执行安全内核（timing / transactional / profile / lifecycle / admission）
- ADR 0011；paper-only 闸门（SIMULATE + live=false）
- （同树）`PaperLedger` 与 workbench `/api/paper/*`，验收见 0.6.2 / 0.6.3

## [0.6.0] - 2026-09-13

### Added

- **大里程碑 M5 完成**：美港 Vendor + 市场策略表
  - `MarketStrategy` 分市场 settle / limit / 时区
  - `normalize_symbol(market=US|HK)` 与 CN 隔离
  - `GlobalReplayProvider` + 能力矩阵注册

### Notes

- 节假日日历仍为工作日 stub；live `global_http` 未接线
- 下一步 M6：纸面执行安全模型（吸 V2）

## [0.5.3] - 2026-09-13

### Added

- M5.3 验收：`GlobalReplayProvider`（AAPL / 00700 fixtures）
- 能力矩阵：`global_replay` usable、`global_http` pending

## [0.5.2] - 2026-09-13

### Added

- M5.2 验收：`normalize_symbol(market="US"|"HK")`；CN 路径继续拒港美

## [0.5.1] - 2026-09-13

### Added

- `MarketStrategy` / `get_market_strategy`：CN/US/HK 时区、会话、settle、limit
- US/HK 明确 `buy_to_sell_delay_days=0`、`has_limits=False`（不套用 A 股）
- ADR 0010；契约 `market-strategy.md` 美港表定稿
- （同树预置）US/HK `normalize_symbol` 与 `GlobalReplayProvider`，验收见 0.5.2 / 0.5.3

## [0.5.0] - 2026-09-13

### Added

- **大里程碑 M4 完成**：投研 Agent 插件化（无内嵌抓取）
  - `packages/agents` 仅经 `MarketDataProvider`
  - workbench 研报 / 复盘槽位 + 历史 asof 护栏
  - ADR 0009

### Notes

- TradingAgents-astock 完整 LangGraph 辩论仍可后续接入；不得把东财 URL 写回 agents
- 下一步 M5：美港 Vendor + 市场策略表

## [0.4.2] - 2026-09-13

### Added

- M4.2 验收：workbench 个股研报 / 复盘槽位经能力矩阵 `resolve("daily")`
- 路由测试覆盖 historical asof 告警与港股拒绝

## [0.4.1] - 2026-09-13

### Added

- `packages/agents`：`ResearchAgentPlugin` / `ReviewAgentPlugin`（仅经 providers）
- 历史 `asof` 跳过 realtime 护栏；ADR 0009；CI `agents` job
- workbench 预挂 `/api/research/report`、`/api/review/report`（M4.2 验收于 `0.4.2`）

### Notes

- TradingAgents 完整辩论图仍作参考；平台槽位以本插件为准

## [0.4.0] - 2026-09-13

### Added

- **大里程碑 M3 完成**：`packages/research` 选股/回测内核
  - lvrev 评分与入场闸门（迁自 a-stock-engine）
  - PIT long-only（T 信号 / T+1 open）+ 防未来函数
  - 盘前截面批处理 CLI `stock-platform-score`

### Notes

- a-stock-engine 视为参考实现；平台权威评分路径为本包
- 下一步 M4：TradingAgents 研报插件化（去内嵌抓取）

## [0.3.3] - 2026-09-13

### Added

- `score_cross_section_csv` + 控制台入口 `stock-platform-score`（盘前批处理）

## [0.3.2] - 2026-09-13

### Added

- `run_pit_long_only` + `assert_no_lookahead_columns`（信号日/成交日分离）

## [0.3.1] - 2026-09-13

### Added

- `packages/research`：`score_lvrev` / `apply_entry_gates` / `apply_risk_gates`（迁自 a-stock-engine）
- ADR 0008；CI `research` job

## [0.3.0] - 2026-09-13

### Added

- **大里程碑 M2 完成**：工作台最小壳经能力矩阵消费 Provider
  - FastAPI health / matrix / daily / realtime
  - 缺能力 409 fail-closed；禁品牌硬编码
  - API 与 replay 同标的同日口径对齐

### Notes

- 下一步 M3：迁入选股 / PIT 回测内核（lvrev）

## [0.2.3] - 2026-09-13

### Added

- M2.3 验收：同标的同日 API daily 与 `ReplayProvider` 批处理字段对齐测试

## [0.2.2] - 2026-09-13

### Added

- `PUT /api/settings/preferences`；minute/缺能力 **409** fail-closed 护栏
- 路由源码禁止品牌字面量扫描；ADR 0007

## [0.2.1] - 2026-09-13

### Added

- `apps/workbench`：FastAPI 最小壳（health / capability-matrix / daily / realtime）
- minute 缺能力时 409 fail-closed；ADR 0006；CI `workbench` job

## [0.2.0] - 2026-09-13

### Added

- **大里程碑 M1 完成**：可安装 `stock-platform-providers`
  - ticker 归一化与港美拒绝
  - daily/realtime 录制回放契约测试
  - 东财 `em_get` 限流单点 + 能力矩阵注册
  - 文档禁止裸东财 URL

### Notes

- Live HTTP 行情适配仍为 pending（`astock_http`）；下一阶段 M2 接入工作台壳

## [0.1.3] - 2026-09-13

### Added

- `em_get` / `EastmoneyClient`：东财串行限流单点（禁非 EM URL）
- `build_capability_matrix` / `register_builtin_providers`
- `docs/contracts/eastmoney-http.md`、ADR 0005

## [0.1.2] - 2026-09-13

### Added

- `ReplayTransport` / `ReplayProvider`：daily + realtime 录制回放
- `normalize_daily_row` / `normalize_realtime_row` 契约归一化
- ADR 0004；fixtures 与 pytest 覆盖

## [0.1.1] - 2026-09-13

### Added

- `packages/providers`：可安装包 `stock-platform-providers`
- `normalize_symbol` / `exchange_prefix` / `is_bse_symbol` + pytest
- ADR 0003；CI `providers` job（含与根 `VERSION` 对齐校验）

## [0.1.0] - 2026-09-13

### Added

- **大里程碑 M0 完成**：工程架子、契约 Accepted、CI/文档自检、SemVer tag 流程可协作

### Notes

- 仍无可运行行情/选股业务；下一阶段 M1（`v0.2.0`）开始 `packages/providers` 可安装实现

## [0.0.3] - 2026-09-13

### Added

- `scripts/check_docs.ps1`：必选文件、VERSION↔CHANGELOG、Markdown 相对链接检查
- CI：docs 自检 + `release_tag.ps1 -DryRun`

### Changed

- `release_tag.ps1`：`-DryRun` 不再因 tag 已存在或脏工作区失败
- README / versioning：补充 DryRun 与自检示例

## [0.0.2] - 2026-09-13

### Added

- ADR 0002：M0.2 数据集与市场口径冻结
- 契约定稿：`datasets` / `capability-matrix` / `market-strategy`（对齐 TSP）

### Changed

- 关闭 M0.2 关键 TBD（amount 元、ex_factor、asset_type、asof_ts、usable 形状、CN 规则表）

## [0.0.1] - 2026-09-13

### Added

- 仓库骨架：`apps/`、`packages/`、`docs/`、`scripts/`
- 目标架构 ADR、契约草稿、里程碑 ROADMAP、tag 升级规则
- `VERSION` 单一版本源与 `scripts/release_tag.ps1`
- Git 初始化（`main`）与首个工程 tag `v0.0.1`

[Unreleased]: https://github.com/local/stock-platform/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/local/stock-platform/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/local/stock-platform/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/local/stock-platform/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/local/stock-platform/compare/v0.7.3...v1.0.0
[0.7.3]: https://github.com/local/stock-platform/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/local/stock-platform/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/local/stock-platform/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/local/stock-platform/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/local/stock-platform/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/local/stock-platform/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/local/stock-platform/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/local/stock-platform/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/local/stock-platform/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/local/stock-platform/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/local/stock-platform/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/local/stock-platform/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/local/stock-platform/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/local/stock-platform/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/local/stock-platform/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/local/stock-platform/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/local/stock-platform/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/local/stock-platform/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/local/stock-platform/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/local/stock-platform/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/local/stock-platform/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/local/stock-platform/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/local/stock-platform/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/local/stock-platform/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/local/stock-platform/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/local/stock-platform/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/local/stock-platform/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/local/stock-platform/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/local/stock-platform/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/local/stock-platform/releases/tag/v0.0.1
