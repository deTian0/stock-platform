# ADR 0050：engine `market.db` PIT 基本面只读暴露

- **状态**：Accepted（M-D4 已实现）
- **日期**：2026-09-17（Accepted 2026-09-18）
- **相关**：ADR 0049（brief SQLite）· [`docs/ops/engine-market-db.md`](../ops/engine-market-db.md) · 路线图 M-D2 / M-D4

## 背景

`EngineSqliteProvider` 已只读挂载 a-stock-engine `market.db` 的 `daily_price`（能力矩阵 `daily`）。引擎库内另有时点正确（PIT）基本面表，研究侧（价值/质量因子、实证对照）需要**可选只读查询**，但不能：

- 整仓拷贝引擎或恢复抓取管线；
- 与 Workbench brief 权威库（ADR 0049 `stock_platform.db`）混用；
- 未进能力矩阵就静默当 live 财务。

### 实地盘点（本机 2026-09-17）

路径：`a-stock-engine/data_cache/market.db`（约 3.4 GB，只读打开）。

| 表 | 行数（约） | 关键列 | 现状 |
|----|------------|--------|------|
| `daily_price` | 8.77M | code, date, close, pct_chg, vol, amount | **已暴露**（`daily`） |
| `fundamentals_pit` | 312k | code, end_date, **ann_date**, roe, roa, … | **已暴露**（库方法 + HTTP） |
| `daily_basic_pit` | 7.31M | code, trade_date, pe/pb/ps, total_mv, … | **已暴露**（库方法 + HTTP） |
| `fundamentals` | 5.2k | 截面快照（非 PIT） | **不暴露**（易未来函数） |

## 决策

1. **只读挂载**：继续仅用 `STOCK_PLATFORM_ENGINE_MARKET_DB`；`mode=ro`；禁止平台写引擎库、禁止把 DB 提交进 git。
2. **暴露边界**  
   - 允许：`fundamentals_pit`（按 `ann_date <= asof` 取最近报告期）、`daily_basic_pit`（按 `trade_date = asof`）。  
   - 禁止：把 `fundamentals` 截面快照当历史回测输入；禁止 westock / `collect_pit_*` 抓取链进平台。
3. **与 brief SQLite 分离**：PIT 查询走 engine 路径；每日推荐存档仍只写 ADR 0049 库。
4. **能力矩阵**  
   - **首刀（M-D4）**：`EngineSqliteProvider.get_fundamentals_pit` / `get_daily_basic_pit` + `GET /api/research/pit/fundamentals`；标注 `offline_pit` / `dataNote`，**不**占用 live `financial`。  
   - 若日后把 PIT 当矩阵对外默认路由：再新增 `pit_fundamentals` 并 fail-closed；当前 HTTP 走引擎适配器直连（无 DB → 503 中文）。  
   - **不得**复用现有 `financial`（那是 live/新浪三表，非 PIT）。
5. **未来函数**：查询必须强制 `asof`；缺 `ann_date` 的行丢弃；单测覆盖「asof 前不可见后日公告」。

## 非目标

- 非整仓拷贝 `a-stock-engine` 源码或每日管线。  
- 不恢复 `selections` / HTML 简报双主链。  
- 不把 PIT 表复制进 `stock_platform.db`。  
- 不声称 live 基本面；截止日以引擎导入日为准。

## 后果

- Provider 切片 + 零公网测已落地；Workbench 只读入口 `GET /api/research/pit/fundamentals`。  
- 若本机无 `market.db`：fail-closed（路径未配置 / 表缺失 → 明确中文错误），不得静默空面板冒充。

## 风险

| 风险 | 缓解 |
|------|------|
| 大表扫描拖垮 Workbench | 按 code 列表 + asof 索引查询；禁止全表拉进内存默认路径 |
| 与 `financial` 口径混淆 | 文档/字段前缀 / `dataNote=offline_pit`；矩阵分项 |
| 引擎 schema 漂移 | 以本 ADR 列名为契约；缺列/缺表 fail-closed |
| 误当 live | `dataNote` / provider note 标明 offline settle |

## 参考

- 引擎 schema：`a-stock-engine/src/database.py`（`fundamentals_pit` / `daily_basic_pit`）  
- 引擎查询：`a-stock-engine/src/pit_fundamentals.py`  
- 平台：`EngineSqliteProvider` · `docs/ops/engine-market-db.md`
