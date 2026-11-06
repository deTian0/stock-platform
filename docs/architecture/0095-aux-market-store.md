# 0095 — 平台自有只读补充行情库（`aux_market.db`）

- **状态**：Accepted
- **日期**：2026-11-06
- **相关**：[`0058`](0058-market-db-source-of-truth.md) · [`0090`](0090-benchmark-identity-and-sh-fund-prefix.md) · [`0091`](0091-data-quality-scan.md) · [`0094`](0094-lvrev-trail-tp-exit.md)
  契约 [`../contracts/datasets.md`](../contracts/datasets.md) §补充行情库 · [`../contracts/capability-matrix.md`](../contracts/capability-matrix.md) · [`../contracts/benchmark-identity.md`](../contracts/benchmark-identity.md)

---

## 背景

1. 引擎 `market.db`（只读）的 `daily_price` 只有 `code,date,close,pct_chg,vol,amount`，**没有任何指数行**；`000905` / `000852` / `000016` 在库里是个股（厦门港务 / 石化机械 / *ST康佳A），`000300` 不存在。F1 身份校验（ADR 0090）因此 fail-closed：回测、影子回测、lvrev 增强实验的超额列全部「不可用」。
2. 同库也没有 `open/high/low`，数据质量体检与诊断无法评估开盘跳空、涨停开板。
3. `market.db` 归引擎所有，平台**不得写**（ADR 0058）。

## 决策

1. **独立 SQLite**：平台自有补充库，默认 `local/aux_market/aux_market.db`（cwd 相对，`local/` 已 gitignore），可用 `STOCK_PLATFORM_AUX_MARKET_DB` 覆盖。**不是** `market.db`：写入口拒绝文件名为 `market.db` 或与 `STOCK_PLATFORM_ENGINE_MARKET_DB` 同路径的目标。
2. **单点**：`stock_platform_providers.aux_market`（存储 + 抓取）；CLI `stock-platform-aux-market`（research 包注册）。东财请求**只经 `em_get`**（可注入 transport 供测试 replay）。
3. **指数日线**：`000300` 沪深300、`000905` 中证500、`000852` 中证1000、`000016` 上证50、`399006` 创业板指。secid 走指数表（`1.000xxx` 上证/中证指数、`0.399xxx` 深证指数），**不**用个股 `em_secid` 规则。写入前核对东财返回 `data.code` 与 `data.name`：名称必须命中 `benchmark.KNOWN_INDEX_NAME_HINTS`（`399006` 用同模块新增的 `AUX_EXTRA_INDEX_NAME_HINTS`，不改既有别名表与报价键规则）；不命中 / 缺名称 → **拒写**并在 `fetch_log` 记原因。
4. **个股 OHLC**：只按传入代码列表抓（默认不抓全市场），校验返回 `data.code` 一致。
5. **字段口径**：`date,open,high,low,close,vol,amount,pct_chg`；`pct_chg` **小数**（东财 f59 百分数 ÷100）；`amount` 元；`vol` 为东财 kline 原值（**手**，与 `daily` 契约一致；注意 `market.db.vol` 是股，跨库比较须 ×100）。价格不复权（`fqt=0`）。
6. **预算**：按 Asia/Shanghai 自然日计逻辑请求数（每代码 1 次），上限 `STOCK_PLATFORM_AUX_MARKET_EM_BUDGET`（默认 60），账本在库内 `em_budget` 表；超限的代码记 `budget_exceeded`，不抓。
7. **幂等 / fail-soft**：主键 `(code, date)`，`ON CONFLICT DO UPDATE`；任何单代码失败只降级该代码，`sync_aux_market` 永不抛错。`--dry-run` 只出计划，零网络、不建库。
8. **基准接入**（读侧，`stock_platform_research.benchmark.load_benchmark_closes`）：先走原 F1 路径（身份校验 → 只读 `market.db`）；**仅当**身份碰撞或 `market.db` 无行时，读补充库中已校验的指数行（读时再核一次名称别名）。**补充库不存在时返回值与接入前逐位一致**（单测钉住）。影子回测 `resolve_backtest_benchmark` 与 lvrev 增强 CLI 经此单点取基准，超额列由此可算。
9. **不动** `resolve_benchmark_identity`：日循环 settle / sameday / performance 等调用方用 `market.db` provider 取基准序列，若身份块因补充库翻成 `alphaAvailable=true`，会把个股序列当指数结算。这些链路接补充库需另立变更。

## 非目标

写 `market.db`；全市场 OHLC 回补；把补充库注册进能力矩阵路由（不影响 `usable` 探测）；data_quality / 诊断改读 OHLC（后续单独接）；复权。

## 后果

**正面**：离线研究的超额从「不可用」变为可算，且身份仍 fail-closed（未校验的行不进库、不被读）。
**代价**：多一份本机状态（需定期跑 CLI 增量）；补充库覆盖滞后时超额会因首/末交易日缺失回落为不可用；`vol` 单位与 `market.db` 不同，消费方须显式换算。
