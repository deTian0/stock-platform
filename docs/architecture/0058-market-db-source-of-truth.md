# ADR 0058：market.db 作为唯一历史行情真相源 + 覆盖守卫

- **状态**：Accepted（里程碑 `C2`，2026-10-10）
- **日期**：2026-10-10
- **相关**：ADR 0049（brief SQLite）· ADR 0050（引擎 PIT 只读）· ADR 0055（全市场宇宙）· [`docs/ops/engine-market-db.md`](../ops/engine-market-db.md)

## 背景

平台的历史行情全部来自 `a-stock-engine/data_cache/market.db` 的 `daily_price`（ADR 0050 已确立**只读**）。2026-10-10 复核发现该库**自 2026-09-04 起静默破相**：

| 现象 | 实测 |
|------|------|
| 部分覆盖日 | `2026-09-04` / `09-07` / `09-08` 各 **14 行**（全市场正常 ~5.2k） |
| 完全缺失日 | `2026-09-09` ~ `2026-10-09` 共 **17 个交易日** 0 行 |
| 最后全市场日 | `2026-09-03`（5223 行） |
| 表级表象 | `MAX(date)` 仍为 `2026-09-08`，**看起来"有数据"** |

**根因两条**：

1. **摄取链路断在归档上**：全市场写入只有手动脚本 `empirical/backfill_market_daily.py`（tushare）；日常只跑 `multifactor.refresh_etf_daily_prices`，它**每日只写 14 只 ETF**。引擎日常自动化随归档停止后，没有任何东西再补全市场 → 只剩 14 行/日。
2. **断点续传按日期存在性判定**：`import_local_data.py` 用 `SELECT DISTINCT date FROM daily_price` 判「已导入」，于是**部分覆盖日被永久跳过**，缺陷无法自愈。

一个月的破相无人发现，说明缺的不是修数据的脚本，而是**判据与出口**。路线图 `C2` 本就要求"确认 market.db 为唯一历史行情真相源；派生库归属与同步方式写明"，此前一直挂在 `B1` 名下未落地。

**另发现一条独立缺陷（本轮记录、不修）**：`refresh_etf_daily_prices` 先 `delete_prices_for_codes` 删光 `WELL_KNOWN_ETFS` 14 只 ETF 的**全部历史**，再写入 `LocalPriceLoader` 的 65 根 K 线，且 `pct_chg` 全为 0。实测（2026-10-10）：14 只各仅剩 `2026-06-09 ~ 2026-09-08` **65 行**；同一张表里不在该名单的 ETF（裸码 `518880`）仍有 **1499 行**长历史。修复本身不难（`pro.fund_daily(ts_code=...)` 已实测可用，14 次调用），但须先定**复权口径**（`fund_daily` 未复权 vs 存量裸码 ETF 的未知口径），故留作独立决策，不在本轮夹带。

## 决策

1. **真相源单一化**
   - **唯一历史行情真相源**：`market.db / daily_price`（只读挂载，`STOCK_PLATFORM_ENGINE_MARKET_DB`）。
   - **派生库归属写明**，均**不得**被当作历史行情输入：
     | 库 | 归属 | 用途 |
     |----|------|------|
     | `market.db` | 引擎（生产侧） | 唯一历史日线 / PIT 基本面（只读） |
     | `a-stock-engine.db` | 引擎 | 选股/轮动/验证的过程库（**不入平台**） |
     | `selections.db` | 引擎 | 轮动选股（**不入平台**） |
     | `stock_platform.db` | 平台 | brief 存档 / 命中追踪（ADR 0049） |
     | `history/picks.db` | 引擎 | 引擎侧命中（**与平台命中追踪并存，勿合并**） |

2. **摄取职责留在生产侧**：写 `daily_price` 归 `a-stock-engine`（`empirical/backfill_market_daily.py`）。平台**不代抓、不补写**；延续 ADR 0050，`mode=ro`。

3. **平台侧加覆盖守卫（只读）**
   - `EngineSqliteProvider.coverage_snapshot(asof, lookback_days=30, min_rows=3000)`：**双判据**——① 窗口内 CN 交易日是否齐全（含 `lagTradingDays` 交易日滞后）；② 每日行数是否 ≥ `min_rows`。
   - 出口：`GET /api/ops/health` 的 `marketDb` 块。裁决 `ok|thin|stale|empty|missing_table|unconfigured|error`；除 `ok|unconfigured` 外整体 `status` 降级为 `degraded`。
   - **绝不 500**：异常收敛为 `status="error"`，ops 端点必须始终可用。

4. **告警语义**：滞后按**交易日**而非自然日计数（避免周末/长假误报）；行数下限是可配参数，默认 3000（全市场 ~5.2k 的保守下界，14 行的 ETF-only 日必被捕获）。

## 非目标

- **不**把摄取搬进平台（不复活引擎每日管线，ADR 0050 非目标）。
- **不**改 `market.db` schema，**不**写回引擎库。
- **不**引入真实交易日历之外的调度；平台不做定时抓取。
- **不**声称 live：覆盖新鲜度 ≠ 实时行情。

## 后果

- 破相从"一个月后偶然发现"变成"下次 `/api/ops/health` 就能看到 `stale`"。
- 平台侧新增 1 个 provider 方法 + 1 个 ops 字段，零新依赖、零写路径。
- 数据回补仍是人工/脚本动作（生产侧），但**有判据、有出口、有 runbook**。

## 风险

| 风险 | 缓解 |
|------|------|
| ops 端点扫大表拖慢 | 窗口 GROUP BY 走 `idx_dp_date`，默认 30 天；禁全表扫描 |
| 阈值 3000 误报（新股扩容） | 参数化；实测全市场 ~5.2k 且剔除 BSE 后仍 >5k，余量充足 |
| 交易日历覆盖不足（>2028） | `calendar.py` 静态闭市表，超范围会退化为自然日近似 → 需随 ADR 0044 一并延期 |
| 只报警不修复 | runbook 写明回补命令；本轮已回补 2026-09-04~10-09 |

## 参考

- 覆盖实现：`packages/providers/src/stock_platform_providers/engine_sqlite.py`（`coverage_snapshot`）
- 出口：`apps/workbench/src/stock_platform_workbench/routes/ops.py`
- 测试：`packages/providers/tests/test_engine_coverage.py` · `apps/workbench/tests/test_ops_market_db.py`
- 摄取脚本：`a-stock-engine/empirical/backfill_market_daily.py`
