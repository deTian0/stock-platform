# 契约：标准数据集

> 状态：**Accepted（M0.2）** · 对齐 tick-stock-panel Provider / `docs/plugin-development.md`  
> 破坏性变更须新增 ADR，并升 MINOR（0.x）或 MAJOR（≥1.0）。

## 原则

1. Provider 只做「供应商字段 → 内部标准字段」转换；禁止业务层直接解析源 JSON。
2. 单位写死在本契约；**禁止**「数值 &lt; 1 就 ×100」启发式。
3. 股票 / ETF / 指数用 `asset_type` 区分，**禁止**靠代码猜类型。
4. 缺字段：置 `null` 并记录原因；**禁止伪造**成交额等可推导依赖项。

## 资产类型

```text
asset_type ∈ { "stock", "etf", "index" }
```

标的主数据（instruments）建议列：`symbol`, `name`, `code`, `exchange`, `asset_type`, `source`, `list_date?`, `status?`。

## Ticker（按 market）

### CN（A 股路径）

| 规则 | 说明 |
|------|------|
| 内部 `symbol` | 6 位数字字符串，如 `600519`、`000001` |
| 归一化 | `normalize_symbol(..., market="CN")` 唯一入口 |
| 拒绝 | 港股（4–5 位 / `.HK`）、美股代码进入 A 股路径 |
| 北交所 | v1 默认**纳入归一化但可选宇宙过滤**；号段 43/83/87/88/92 等在策略层配置 |

### US / HK（M5）

| 市场 | 内部 `symbol` | 归一化入口 | 备注 |
|------|---------------|------------|------|
| US | 大写字母 ticker（`AAPL`、`BRK.B`） | `market="US"` | 不得进 CN 路径 |
| HK | **5 位**补零（`00700`） | `market="HK"` | 接受 `0700.HK` / `700`；不得进 CN 路径 |

## 核心数据集字段

### `daily`（日 K）

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | **按 market**：CN=6 位；US=字母；HK=5 位 |
| `asset_type` | str | 建议 | stock/etf/index |
| `source` | str | 建议 | Provider 名 |
| `date` | date | ✅ | **交易日**；内部列名对齐 TSP：`date`（不是 `trade_date`） |
| `open/high/low/close` | float | ✅ | 标价货币（CN=元；US=USD；HK=HKD）；入库可为不复权，enriched 层见下 |
| `volume` | float | ✅ | **CN=手**（1 手 = 100 股）；**US/HK=股（shares）**，禁止按 A 股手换算 |
| `amount` | float | ✅ | 成交额（与价格同币种） |
| `pre_close` | float | 建议 | 与价格同币种 |
| `change_pct` | float | 建议 | **小数制**；可缺，由下游用涨跌额/昨收推导 |
| `quote_ts` | int64? | 可选 | 毫秒行情时间戳；缺失为 null |

自验（**仅 CN**）：`amount ÷ volume ÷ 100 ≈ 当日均价`（量能异常日除外）。US/HK 用 `amount ÷ volume ≈ 均价`。

### `adj_factor`（除权因子）

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | |
| `asset_type` | str | 建议 | |
| `source` | str | 建议 | |
| `trade_date` | date | ✅ | 除权事件对应交易日（Asia/Shanghai 墙钟日期） |
| `ex_factor` | float | ✅ | 复权因子；**列名固定 `ex_factor`**（源字段 `adj_factor` 须在 Provider 内 rename） |

毫秒零点戳转日期时须按 **Asia/Shanghai**，禁止直接用 UTC `from_epoch().date()`（会整体早一天）。

套价（**非独立能力**，M23）：`apply_adjust(bars, factors, kind=qfq|hfq)` 把因子阶梯套到不复权 OHLC。
`qfq` 为除数、`hfq` 为乘数；输出带 `ex_factor` + `adjust_kind`。空因子不得返回未复权价。
只缩放 `open/high/low/close/pre_close`。涨跌停判定仍用不复权 raw。

### `realtime`（实时快照）

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | |
| `name` | str | 建议 | |
| `price` | float | ✅ | 最新价（与 market 币种一致） |
| `prev_close` | float | 建议 | 昨收 |
| `change_amount` | float | 建议 | 涨跌额 |
| `change_pct` | float | 建议 | **小数制**入口：`0.0366` = 3.66% |
| `amplitude` | float | 建议 | **小数制**入口 |
| `turnover_rate` | float | 建议 | **小数制**入口：`0.05` = 5% |
| `volume` | float | ✅ | **CN=手**；**US/HK=股** |
| `amount` | float | 建议 | 成交额（与价格同币种） |
| `asof_ts` | int64 或 datetime | ✅ | 快照时刻；存储为 **Unix 毫秒 UTC**，展示转该 market 时区。禁止把「本地墙钟 naive」当 UTC 入库 |

百分制源必须在 Provider/`pct_unit` 配置中**显式**声明并 `/100`；未声明时 `change_pct` 仅允许有文档的截面判定，`amplitude`/`turnover_rate` 应置 null 交下游重算。

### 其余能力（字段摘要，M1+ 实现）

| 数据集 | 关键列 |
|--------|--------|
| `minute` | `symbol`, `datetime`（**北京墙钟 naive** `YYYY-MM-DD HH:MM:SS`，禁止 tz/UTC 入库）, `open/high/low/close`, `volume`（手）, `amount`（元，可 null）, `freq`（`1m`/`5m`/`15m`/`30m`/`60m`）, `source`, `asset_type` |
| `depth5` | 见下表（M19） |
| `financial` | 见下表（M20） |
| `full_minute` | 同 minute 列；**仅 `freq=1m`**；语义为**单交易日**标的批量当日 1m（宇宙修复轮）；见 ADR 0027；与多频历史 `minute` 独立 |
| `fund_flow` | 见下表（M15） |
| `lhb` | 见下表（M16） |
| `unlock` | 见下表（M17） |
| `sector_fund_flow` | 见下表（M41） |
| `news` | 见下表（M41） |

### `depth5`（五档盘口，M19）

快照 payload（非日 K 行集）。价=元；量=**手**。数组按一档→五档排列，长度固定 5。

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | CN=6 位 |
| `asset_type` | str | 建议 | stock/etf/index |
| `source` | str | 建议 | Provider 名 |
| `bid_prices` | list[float] | ✅ | 买一～买五价格，**元**；长度 5 |
| `bid_volumes` | list[float] | ✅ | 买一～买五量，**手**；长度 5 |
| `ask_prices` | list[float] | ✅ | 卖一～卖五价格，**元**；长度 5 |
| `ask_volumes` | list[float] | ✅ | 卖一～卖五量，**手**；长度 5 |
| `asof_ts` | int64 | ✅ | 快照时刻；**Unix 毫秒 UTC** |

配方：东财 push2 `stock/get` 五档字段（经 `em_get`；与 realtime 同 URL）。mootdx / 交易所官方备胎不在本契约。

### `financial`（财务报表，M20）

聚合 payload（非日 K 行集）。金额一律 **元**。三表按报告期倒序；空表为 `[]`。

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | CN=6 位 |
| `asset_type` | str | 建议 | stock/etf/index |
| `source` | str | 建议 | Provider 名 |
| `periods` | int | ✅ | 请求/返回期次数 |
| `income` | list | ✅ | 利润表期次；空为 `[]` |
| `balance` | list | ✅ | 资产负债表期次；空为 `[]` |
| `cashflow` | list | ✅ | 现金流量表期次；空为 `[]` |
| `*.period_end` | date | ✅ | 报告期截止日 |
| `income.revenue` / `net_income` / `net_income_attributable` / `basic_eps` | float | 建议 | 元 / 元每股 |
| `balance.total_assets` / `total_liabilities` / `total_equity` | float | 建议 | **元** |
| `cashflow.net_operating_cash_flow` / `net_investing_cash_flow` / `net_financing_cash_flow` | float | 建议 | **元** |

配方：新浪 `CompanyFinanceService.getFinanceReport2022`（`lrb`/`fzb`/`llb`；**非** `em_get`）。mootdx / 东财财报备胎不在本契约。

### `fund_flow`（日级资金流，M15）

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | CN=6 位 |
| `asset_type` | str | 建议 | stock/etf/index |
| `source` | str | 建议 | Provider 名 |
| `date` | date | ✅ | 交易日 |
| `main_net` | float | ✅ | 主力净流入，**元** |
| `small_net` | float | 建议 | 小单净流入，**元** |
| `mid_net` | float | 建议 | 中单净流入，**元** |
| `large_net` | float | 建议 | 大单净流入，**元** |
| `super_net` | float | 建议 | 超大单净流入，**元** |

配方：东财 push2his `fflow/daykline`（经 `em_get`）；分钟资金流不在本契约（板块日级见 `sector_fund_flow`）。

### `lhb`（龙虎榜，M16）

聚合 payload（非日 K 行集）。金额一律 **元**（东财原始金额；不做「万」换算）。

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | CN=6 位 |
| `asset_type` | str | 建议 | stock/etf/index |
| `source` | str | 建议 | Provider 名 |
| `asof_date` | date | ✅ | 查询截止交易日 |
| `look_back_days` | int | ✅ | 回看自然日数（默认 30） |
| `records` | list | ✅ | 上榜记录；空窗口为 `[]` |
| `records[].date` | date | ✅ | 上榜日 |
| `records[].reason` | str | 建议 | 上榜原因 |
| `records[].net_buy` | float | 建议 | 龙虎榜净买入，**元** |
| `records[].turnover_rate` | float | 建议 | **小数制**（`0.1234` = 12.34%） |
| `seats.buy` / `seats.sell` | list | ✅ | 最近上榜日买卖席位 TOP5；空为 `[]` |
| `seats.*.name` | str | 建议 | 营业部名称 |
| `seats.*.buy_amt` / `sell_amt` / `net` | float | 建议 | **元** |
| `institution.buy_amt` / `sell_amt` / `net_amt` | float | ✅ | 机构专用席位汇总，**元**；无机构为 0 |

配方：东财 datacenter-web `RPT_DAILYBILLBOARD_DETAILSNEW` + `RPT_BILLBOARD_DAILYDETAILSBUY/SELL`（经 `em_get`）。全市场日榜与交易所备胎不在本契约。

### `unlock`（限售解禁，M17）

聚合 payload（非日 K 行集）。股数一律 **万股**（东财原始；不做「股」换算）。`ratio` 为**小数制**。

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | ✅ | CN=6 位 |
| `asset_type` | str | 建议 | stock/etf/index |
| `source` | str | 建议 | Provider 名 |
| `asof_date` | date | ✅ | 查询基准日（未来窗口起点） |
| `forward_days` | int | ✅ | 向前自然日数（默认 90） |
| `history` | list | ✅ | 历史解禁；无记录为 `[]` |
| `upcoming` | list | ✅ | `[asof, asof+forward]` 待解禁；无则为 `[]` |
| `*.date` | date | ✅ | 解禁日 |
| `*.type` | str | 建议 | 限售类型（`FREE_SHARES_TYPE`） |
| `*.shares` | float | 建议 | 本次解禁股数，**万股** |
| `*.able_shares` | float | 建议 | 实际可流通股数，**万股** |
| `*.ratio` | float | 建议 | 占总股本比，**小数制** |

配方：东财 datacenter-web `RPT_LIFT_STAGE`（经 `em_get`；历史 + 未来各一次）。全市场解禁日历不在本契约。

### `sector_fund_flow`（板块资金流，M41）

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `sector_code` | str | ✅ | 东财板块代码（如 `BK0477`） |
| `sector_name` | str | 建议 | 板块名称 |
| `asset_type` | str | 建议 | `sector` 或 `index` |
| `source` | str | 建议 | Provider 名 |
| `date` | date | ✅ | 交易日 |
| `main_net` | float | ✅ | 主力净流入，**元** |
| `change_pct` | float | 建议 | 板块涨跌幅（百分数口径由源决定；可 null） |

配方：东财 push2his `fflow/daykline`，`secid=90.BK####`（经 `em_get`）。排名截面（clist 今日/5日/10日）不在本契约。

### `news`（轻量新闻特征，M41）

| 字段 | 类型 | 必填 | 单位 / 语义 |
|------|------|------|-------------|
| `symbol` | str | 条件 | CN=6 位；与 `sector_code` 至少其一 |
| `sector_code` | str | 条件 | 东财板块代码；与 `symbol` 至少其一 |
| `date` | date | ✅ | 新闻日（取自发布时间） |
| `title` | str | ✅ | 标题 |
| `summary` | str | 建议 | 短摘要；可 null（**非** LLM 生成） |
| `source` | str | 建议 | Provider 名 |
| `sentiment` | float | 建议 | 可选情绪分；可 null；不做默认模型推断 |

配方：东财 np-weblist `getFastNewsList`（经 `em_get`；轻量列表）。默认路径不做 LLM 摘要。

## 影子链产物（平台自有 JSON，非 Provider 出口）

多策略影子链（ADR [0093](../architecture/0093-multi-strategy-shadow-board.md)，契约 [`multi-strategy-shadow.md`](multi-strategy-shadow.md)）的落盘文件。根目录 `<shadow_dir>` 默认 `local/shadow/`，**跟随 `STOCK_PLATFORM_SHADOW_DIR`**；写入经 `_assert_shadow_path` 守卫（不得逃出影子根、不得命中 `recommend_decisions.jsonl` / `performance_proxy.jsonl` / `holdings.json`）。全部 `shadowOnly=true`、`excludedFromPerformance=true`，不提交、不写 `market.db`。口径：**金额元、比例小数**。

| 文件 | 写入方 | 语义 |
|------|--------|------|
| `<shadow_dir>/s2_snapshots/s2_snapshot_{asof}.json` | `shadow_board.s2_snapshot.collect_s2_snapshot` | 当日 S2 事件/题材截面；原子写（tmp + replace）；同 asof `ok` 复用零网络，`partial`/`failed` 重抓覆盖 |
| `<shadow_dir>/s2_snapshots/_budget.json` | 同上 | `{ "YYYY-MM-DD": 已用逻辑请求数 }`，按 Asia/Shanghai 自然日计，保留最近 60 天；best-effort |
| `<shadow_dir>/final_board_{asof}.json` | `shadow_board.ledger.write_shadow_ledger` | 当日完整 Final Board payload（形状见 `multi-strategy-shadow.md` §3） |
| `<shadow_dir>/final_board.jsonl` | 同上 | 每次运行追加一行摘要 |
| `<shadow_dir>/shadow_decisions.jsonl` | `shadow_board.performance.log_shadow_board` | 影子前向绩效账本；每终榜席位一行，`(date, symbol)` 幂等，空榜不落行 |

### `s2_snapshot_{asof}.json`（`schemaVersion=1`）

| 字段 | 类型 | 语义 |
|------|------|------|
| `kind` | str | 固定 `s2_snapshot` |
| `asof` | date | 快照所属交易日 |
| `status` | str | `ok`（四源均 ok）/ `partial` / `failed`（四源均 failed 或 budget_exceeded）；联网关闭且无文件时返回 `disabled`（不落盘） |
| `fetchedAt` | str | 抓取时刻（Asia/Shanghai ISO） |
| `provider` / `transport` | str | `astock_http` / `em_get` |
| `budget` | obj | `dailyLimit`（`STOCK_PLATFORM_S2_EM_BUDGET`，默认 300）、`runDate`、`usedThisRun`、`usedToday`、`exceeded` |
| `sources.{lhb,concept_rank,industry_rank,unlock}` | obj | `status`（`ok`/`empty`/`stale`/`failed`/`budget_exceeded`）、`count`；lhb 另有 `symbols`、`truncated`；排名另有 `updatedAt`、`pitOk`、`note`；unlock 另有 `truncated`、`window` |
| `lhb[]` | list | `date,symbol,name,reason,net_buy,buy_amt,sell_amt,deal_amt`（**元**）、`close`、`change_pct`、`turnover_rate`（**小数**）；只留 `date==asof` |
| `boards.concept[]` / `boards.industry[]` | list | `code,name,kind,change_pct`（**小数**）、`main_net`（**元**）、`lead_stock,lead_name` |
| `unlock[]` | list | `symbol,name,date,type`、`shares`/`able_shares`（**万股**）、`ratio`（**小数**，占流通股） |
| `units` / `pit` | obj | 单位与 PIT 口径自描述 |

PIT：`lhb` 盘后公布，仅可用于 asof 次日入场；板块排名仅 `pitOk`（`updatedAt` 日期 == asof）才进 S2；`unlock` 为当前公告日程，有修订前视风险，仅作软排除（`ratio ≥ 0.05`）。回测不读快照。

### `final_board.jsonl` 行

`schemaVersion`、`asof`、`status`（`ok`/`empty`/`degraded`）、`finalCount`、`snapshot`（对应 `final_board_{asof}.json` 路径）、`excludedFromPerformance`、`shadowOnly`。

### `shadow_decisions.jsonl` 行

| 字段 | 语义 |
|------|------|
| `date` / `symbol` / `name` | 决策日（= 终榜 asof）/ 6 位代码 / 名称 |
| `rating` | 固定 `Buy` |
| `holding` | 主结算持有窗口（同 `recommend_decisions.jsonl` 默认） |
| `pending` | 未结算 `true`；结算后由 `settle_pending_entries` 回写 |
| `raw` / `alpha` | 持有期收益 / 超额（**小数**；`alpha = raw − benchmark`）；未结算为 `null` |
| `source` | 固定 `shadow_final_board` |
| `rank` / `score` / `school` / `schoolHolding` | 终榜序号、分数、学校 ID、学校持有期文案 |
| `setA` | `{ arbiter: "set_a", passed: true }` |
| `setB` | `advisoryRank`、`advisoryScore`、`winRate`、`expectedReturn`（**小数**；无顾问为 `null`） |
| `excludedFromPerformance` / `shadowOnly` | 恒 `true`；不并入主绩效 |

## 补充行情库（平台自有 SQLite，ADR 0095）

路径默认 `local/aux_market/aux_market.db`（`STOCK_PLATFORM_AUX_MARKET_DB` 覆盖），**不是** `market.db`，不提交。写入方唯一：`stock_platform_providers.aux_market.sync_aux_market`（CLI `stock-platform-aux-market`）；东财经 `em_get`。读方：`aux_market.read_index_closes` / `read_ohlc`（`mode=ro`，缺库返回 `None`）。

| 表 | 主键 | 字段 |
|----|------|------|
| `index_daily` | `(code, date)` | `code`（裸 6 位，如 `000905`）、`date`、`open/high/low/close`、`vol`（**手**）、`amount`（**元**）、`pct_chg`（**小数**）、`source`、`fetched_at` |
| `stock_ohlc` | `(code, date)` | 同上；`code` 为 `XXXXXX.SH/SZ/BJ`（与 `market.db` 一致） |
| `index_meta` | `code` | `secid`、`name`（东财返回名）、`verified_hint`（命中的别名）、`verified_at` |
| `fetch_log` | 自增 | `run_at`、`kind`（`index`/`stock`）、`code`、`status`（`ok`/`rejected`/`failed`/`empty`/`budget_exceeded`）、`rows`、`reason` |
| `em_budget` | `day` | Asia/Shanghai 自然日 → 已用逻辑请求数 |

- 指数行**仅在名称校验通过后**写入（别名见 `benchmark.KNOWN_INDEX_NAME_HINTS` + `AUX_EXTRA_INDEX_NAME_HINTS`）；读侧再核一次。
- 价格不复权；`vol` 单位与 `market.db.vol`（股）不同，跨库比较须 ×100。

## Enriched 层（消费侧，非 Provider 原始出口）

| 主题 | 规则 |
|------|------|
| 前复权 OHLC | enriched 展示/指标默认前复权 |
| 原始价 | `raw_open/raw_high/raw_low/raw_close` 不复权；**涨跌停 / 一字板必须用 raw_*** |
| `turnover_rate`（enriched） | 可为**百分数值**（`5` = 5%）；与 realtime 入口小数制不同，跨边界必须显式转换 |
| 指数涨跌幅缓存 | 可能存在百分数口径；**不得**直接喂给股票监控阈值 |

## 已关闭的原 TBD

| 原问题 | 决定 |
|--------|------|
| `amount` 单位 | **元**（与 TSP plugin-development 一致） |
| `asof_ts` | Unix **毫秒 UTC**；展示转上海 |
| 指数/ETF/股票 | **`asset_type` 字段**，分路由；不靠代码猜测 |
| 复权因子列名 | 统一 **`ex_factor`**，不用并行的 `adj_factor` 列 |

## 参考

- tick-stock-panel：`backend/app/data_providers/schemas.py`、`normalizer.py`、`docs/plugin-development.md`、`CONTRIBUTING.md` §3
