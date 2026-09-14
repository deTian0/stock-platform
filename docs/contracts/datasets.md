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
| `minute` | `symbol`, `datetime`（**北京墙钟 naive**，禁止 UTC 入库）, `open/high/low/close`, `volume`（手）, `amount`（元，可 null）, `freq` |
| `depth5` | 按 symbol 的五档；`bid_volumes`/`ask_volumes` 单位为**手** |
| `financial` | 报表期 + 标准财务字段（M1 另表） |
| `full_minute` | 同 minute 语义的全市场当日落盘批次 |
| `fund_flow` | 见下表（M15） |
| `lhb` | 见下表（M16） |
| `unlock` | 见下表（M17） |

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

配方：东财 push2his `fflow/daykline`（经 `em_get`）；分钟/板块资金流不在本契约。

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
