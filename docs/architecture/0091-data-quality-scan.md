# 0091 — market.db 数据质量体检（T3）

- **状态**：Accepted
- **日期**：2026-11-05
- **相关**：[`0058`](0058-market-db-source-of-truth.md) · [`0073`](0073-daily-loop-health-single-point.md) · [`0090`](0090-benchmark-identity-and-sh-fund-prefix.md)  
  契约 [`../contracts/data-quality.md`](../contracts/data-quality.md) · [`../contracts/loop-health.md`](../contracts/loop-health.md)

---

## 背景

供数覆盖率（C2）只回答「近日有没有行」；不回答尺度混用、停牌堆积、除权跳变、脏码、声明基准/ETF 缺日。日用循环需要一路**只读、零网络**的质量信号，且不能阻断选股。

## 决策

1. 单点 `stock_platform_research.data_quality.collect_data_quality`；CLI `stock-platform-data-quality`。
2. 五项检查：`pctScale` / `halts` / `closeJumps` / `dirtyCodes` / `coverageGaps`（阈值见契约）。
3. `market.db` 仅 `mode=ro`；报告写入平台 `local/health/`（或 `STOCK_PLATFORM_LOOP_HEALTH_DIR`）；**不写行情库**。
4. `loop_health` 增段 `dataQuality`；裁决：**仅** `warn`（含段级 `degraded`），**永不** `fail` / `blocked`。
5. CLI 退出码恒 0；providers 函数内懒导入。
6. **Schema 兼容**：以 `PRAGMA table_info(daily_price)` 检测实际列（真实库仅 `code,date,close,pct_chg,vol,amount`，无 OHLC；`vol`/`volume` 等别名兼容）。缺可选列 → 跳过依赖检查并在 `notes` / `skippedChecks` 标注，不计入汇总；缺必需列 `code`/`date` → `unavailable` + `missing_columns` 原因；均不抛错。

## 后果

**正面**：脏库有显式降级信号。  
**代价**：大库抽样（默认 400 码 / 60 自然日）可能漏检；故意不扫全表以保证体检可交互。
