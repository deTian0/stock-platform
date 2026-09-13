# 契约：标准数据集（草稿）

> 状态：Draft（M0.2 定稿）  
> 权威目标：与 tick-stock-panel Provider 语义对齐；本文件为合并期单一文字源。

## 原则

- Provider 只做「供应商字段 → 内部标准字段」转换。
- 禁止页面/脚本绕过标准化直接解析源 JSON。
- 单位写死在契约里，禁止「&lt;1 就 ×100」启发式。

## 数据集（能力矩阵对应）

| 数据集 ID | 说明 | M0.2 最低字段 |
|-----------|------|----------------|
| `daily` | 日 K | `symbol`, `trade_date`, `open`, `high`, `low`, `close`, `volume`, `amount` |
| `adj_factor` | 复权因子 | `symbol`, `trade_date`, `adj_factor` |
| `realtime` | 实时快照 | `symbol`, `price`, `change_pct`, `volume`, `asof_ts` |
| `minute` | 分钟 K | （M1+ 展开） |
| `depth5` | 五档 | （M1+ 展开） |
| `financial` | 财务 | （M1+ 展开） |
| `full_minute` | 全历史分钟 | （M2+） |

## 单位（不可混用）

| 字段 | 单位 | 备注 |
|------|------|------|
| `change_pct`（realtime 入口） | **小数制** | `0.0366` = 3.66% |
| `volume` | 手（A 股惯例） | 与金额换算在消费方显式 ×100 |
| OHLC（enriched） | 前复权价 | 涨跌停判断必须用原始价字段（待命名 `raw_*`） |
| `trade_date` | 交易日 `YYYY-MM-DD` | 非自然日；时区：Asia/Shanghai |

## Ticker

- A 股内部规范：6 位数字字符串，如 `600519`
- 归一化入口：未来 `packages/providers` 的 `normalize_symbol()`
- 港股/美股：拒绝进入 A 股 Agent 路径；美港走独立市场策略（M5）

## TBD（M0.2 必须关掉）

- [ ] `amount` 单位（元 vs 千元）与上游对齐表
- [ ] `asof_ts` 时区存储（aware vs naive 墙钟）
- [ ] 指数 / ETF / 股票分表还是 `asset_type` 字段
