# 榜单契约（Ranking boards）— X2

> 状态：**已落地**（`v4.0.1`）。实现单点：`packages/research/.../rankings.py`。
> 契约对象：盘前 brief 的 `rankings` 段、`stock-platform-rankings` CLI、Workbench `#recommend` 页「榜单」区块。
> SIMULATE only；`liveTradingEnabled=False`；非投资建议。

---

## 1. 五类榜单

榜单把**同一份已评分截面**（`score_lvrev` 输出，按 `composite_score` 降序）切成五块，
与 `a-stock-engine: src/multifactor.py :: categorize()` 一一对应：

| 键（engine） | slug | 口径 |
|---|---|---|
| `②A_质量榜` | `quality` | 综合分最高的前 `quality_top_n` 只（默认 **10**） |
| `②B_短线榜` | `short_term` | 在**排除 ②A 头部**后的池里取 `short_term_top_n` 只（默认 **5**）；若截面带 `entry_ok` 列则**优先取 `entry_ok=True`**，不足再按综合分补足 |
| `③A_持仓` | `holdings` | 传入的持仓 ∩ 评分截面，按综合分降序；**未过今日入场闸门的持仓也会列示**（`composite_score=null`，说明「未过今日入场闸门」），持仓是既成事实，不因买点闸门而消失 |
| `③B_操作建议` | `actions` | **只**收录 `review_positions()` 判为 `exit` / `trim` 的持仓（B5 规则单点）。行内含 `action` / `reason` / `ret_pct` / `deferred` |
| `③C_观察名单` | `watchlist` | ②A 头部之后的 `watchlist_top_n` 只（默认 **23**） |

`add` 属加仓偏差、`hold` / `pending` 属无指令，**都不进 ③B**。

---

## 2. 参数（单点：`RankingConfig`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `quality_top_n` | 10 | ②A 大小 |
| `short_term_top_n` | 5 | ②B 大小 |
| `watchlist_top_n` | 23 | ③C 大小 |
| `min_composite_score` | **0.0（关闭）** | 低分门槛，**只作用于 ②A / ②B / ③C**；③A / ③B（持仓）不受影响 |

⚠️ **值域不同，禁止照抄**：平台 `composite_score` 是 `[0, 1]` 的分位合成值，
而 `a-stock-engine` 的 `output.min_composite_score=60` 是**百分制**。
把 `60` 直接搬过来会把全市场过滤成空集。要启用门槛请按本平台量纲取值（如 `0.60`）。

---

## 3. fail-closed 约定（不可协商）

| 情形 | 行为 |
|---|---|
| 评分为空 | 五个榜全空 + 中文 `notes`（「截面为空：无可排名标的（fail-closed，不生成占位榜单）」），**不生成占位条目** |
| 未传持仓 | ③A / ③B 为空 + note「未提供持仓（holdings 为空）」；Workbench 读 `STOCK_PLATFORM_HOLDINGS_PATH` 或 `?holdingsPath=` |
| 持仓缺 `entry_price` / 现价 | 该持仓 `pending`，**不给建议**；note 标注数量 |
| 持仓文件读取失败 | `holdingsLoaded=0` + `holdingsNote` 中文原因，③A / ③B 留空，**不回退、不臆造** |

---

## 4. 不重复实现（single definition）

| 能力 | 唯一定义 | 本模块的用法 |
|---|---|---|
| 理由串 | `brief.build_reasons_for_row` / `reason_summary` | 榜单项直接复用，**不重写** |
| 退出 / 冷静期 / 偏差 | `rules.*`（B5） | ③B 完全委派 `review_positions`，`reason` 原文透传 |
| 资产分类 | `portfolio.asset_class` | 沿用 |
| 代码归一 | 6 位数字核 `rankings.code_key` | 仅用于持仓↔截面匹配；BSE 前缀表仍在 `providers.symbol` |

### 与 a-stock-engine 的一处**有意差异**

引擎的 ③B 是「持仓评分 < 全截面中位数 ⇒ 建议减仓」这一**启发式**。
平台**不复制**它：平台已经有 B5 规则单点（止损 / 目标 / 跟踪 / 趋势破位 / 冷静期 / 偏差），
再写一条中位数卖出规则就会形成第二套可操作来源。
因此：

* **可操作建议**唯一来自 B5（③B）；
* 引擎的中位数口径**降级为 ③A 行上的只读标记 `belowMedian`**（信息，不是指令）。

---

## 5. 出口

| 出口 | 说明 |
|---|---|
| `build_premarket_brief(..., holdings=...)` | 返回 `rankings`（全量）+ `rankingsCounts`（计数）；**`picks` 语义不变（= ②A 头部）**，老消费方零迁移 |
| `stock-platform-rankings --panel panel.csv [--holdings book.json] [--md/--csv/--json]` | 离线重放；`--panel` 可为原始特征面板（自动评分）或已评分面板 |
| `stock-platform-daily --holdings book.json` | 流水线写入 `briefs/{asof}/brief.json` 的 `rankings` 段 |
| `GET /api/research/brief?holdingsPath=...` | Workbench；响应带 `rankings` / `rankingsCounts` / `holdingsLoaded` / `holdingsNote` |

---

## 6. 验收断言（回归网）

`packages/research/tests/test_rankings.py`（16 项）+ `apps/workbench/tests/test_rankings_api.py`（4 项）：

* ②A / ②B 不重叠；②B 优先 `entry_ok`；不足按分补足；
* ③C 恰好是 ②A 之后的连续切片；
* `min_composite_score` 只切推荐类目；
* ③A 交集 + 未过闸门持仓仍在榜（分数为空）；
* ③B 的 `reason` 来自 `rules`（断言 `stop_loss` 子串，非本地改写）；
* 空截面 / 无持仓 / 坏持仓文件 三种 fail-closed。
