# ADR 0055：全市场宇宙接入（X1）

- 状态：Accepted
- 日期：2026-10-10
- 关联：`docs/contracts/market-universe.md`、实测 `docs/ops/market-universe-benchmark.md`

## 背景

`G1 → B1 → B5` 之后回测口径已统一，但日线选股仍跑在一个几十到几百代码的 **JSON fixture 宇宙**（`core` / `watch` / `full`）上 —— "回测可信"与"选股可日用"之间的缺口就是宇宙规模。`X1` 要求把宇宙扩到 `market.db` 全市场（排除 BSE），并给出**实测的耗时 / 内存数字**。

约束：

- 不得新增第五套重复实现 —— BSE 判据已有单点（`symbol.is_bse_symbol`），资产类别已有单点（`portfolio.asset_class`，B4）。
- 3.14 GB 的 `market.db` 只读挂载，禁止拷贝 / 内联。
- 空宇宙必须是**显式失败**，不能静默回落样例（否则会伪装成"选股跑通了"）。

## 决策

1. **单一入口**：`research.market_universe.resolve_universe(source=...)`，`UNIVERSE_SOURCES = ("config", "market_db")`。优先级：显式 `symbols` > `market_db` > config 文件。`config` 仍是默认（X1 不改变既有行为）。
2. **职责切分（不写两遍）**：
   - providers `EngineSqliteProvider.list_symbols` —— 仓库 → 代码列表的唯一定义：日期窗口（`idx_dp_date`）、`min_bars`、BSE 排除、6 位归一、**裸码与带后缀码合并计数**。
   - research `resolve_market_universe` —— 只做资产类别过滤（复用 `portfolio.asset_class`）、`limit`、出处与代价记录、fail-closed。research **不重复** BSE 前缀表，也**不重排** provider 结果。
3. **SQL 只走日期窗口**：`WHERE date BETWEEN ? AND ? GROUP BY code`；绝不对 `code` 做表达式（实测 `SUBSTR(code,-2)` 全表扫描 5.12 s vs 窗口聚合 0.15 s，差 34 倍）。
4. **Fail-closed**：空结果 / 未注入 source / 未知 `source` / 未知 `asset_type` 一律 `UniverseEmptyError`（中文 + `counts`）；DB 缺失 `FileNotFoundError`。**禁止空宇宙回落样例 fixture**。
5. **`MarketUniverse` 随结果返回出处与代价**：`counts`（source → normalized → asset_matched → final）、`elapsed_s`、`peak_memory_mb`（`measure_memory=True` 时才用 `tracemalloc`）。
6. **可观测性 CLI**：`stock-platform-market-universe`（`--db` / `--asof` / `--asset-type` / `--min-bars` / `--limit` / `--include-bse` / `--probe-panel` / `--json` / `--symbols-only`）。文档里的每个数字都由它现场产出。
7. **流水线接线**：`run_daily_pipeline(universe_source="market_db", market_symbol_source=...)`，流水线注入本次 `asof` / `lookback_days`，报告新增 `universe{source,size}`。
8. **测试零依赖真实库**：providers 侧用合成 sqlite（含裸码 / BSE / 脏码 / 窗口外数据），research 侧用 fake source —— 全程不碰 3.14 GB 文件。

## 后果

- 实测（asof 2026-09-03）：全市场 **5 227** 只（stock / 排除 BSE），枚举 **0.21 s / 1.04 MB**；全市场单日 PIT panel **5 209 行 / 23.0 s / 498.8 MB**。全市场选股在现有硬件上可日用，瓶颈在下游而非宇宙。
- **当前 `market.db` 不含北交所数据**：`include_bse=True` 与默认结果一致（过滤 0 个）—— 排除规则是为将来保留。
- ⚠️ **发现数据覆盖缺陷**：自 **2026-09-04** 起每日 bar 数从 ~5.2k 塌到 **14** 只（引擎侧导入中断），最后可用交易日为 **2026-09-03**。宇宙枚举不受影响，但**当日横截面 / 选股会几乎空**。`X3` / `X4` 开工前应先修引擎侧导入（平台只读，不代抓）。
- `X1` 只做内核 + CLI + 文档，**未新增 Workbench API**；UI 接入留待 `X2`（榜单体系对齐）一并考虑。
- 与既有红线无关：`L1` 未立项前不触碰 `liveTradingEnabled`。

## 备选方案（已否决）

| 方案 | 否决理由 |
|---|---|
| 在 research 侧直接 `sqlite3` 查 `market.db` | 复制 DB schema 知识，与 `engine_sqlite` 形成第二套；且 research 刻意不依赖 providers |
| 把全市场码表导出成 JSON 塞进 fixtures | 3.14 GB 库的派生物进仓库 = 必然过期；且违反「只读挂载、不拷贝」 |
| 默认改为 `market_db` | 会让所有既有调用点（含 CI）突然跑 5k 只；保持 `config` 默认，X1 是能力扩展而非行为变更 |
| 空宇宙返回 `[]` 让上层自行判断 | 历史教训（静默空结果冒充成功）；必须显式抛错 |
