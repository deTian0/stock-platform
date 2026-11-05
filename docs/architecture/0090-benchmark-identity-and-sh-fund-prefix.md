# 0090 — 基准身份 fail-closed + 沪市基金 `exchange_prefix`

- **状态**：Accepted
- **日期**：2026-11-05
- **相关**：F1 · [`0003`](0003-providers-normalize-symbol.md) · [`0068`](0068-performance-pnl-closed-loop.md) · [`0082`](0082-day-quote-attribution.md)  
  契约 [`../contracts/benchmark-identity.md`](../contracts/benchmark-identity.md) · [`../contracts/day-quote.md`](../contracts/day-quote.md)

---

## 背景

1. `exchange_prefix` 只把 `6`/`9` 当沪市，`5xxxxx` 沪市基金/ETF（如 `588080`）被判成 `sz`，东财/腾讯/新浪/westock 四源 secid 全错。
2. 默认基准裸码 `000905` 在引擎 fundamentals 常解析为个股「厦门港务」，不是中证 500；绩效 `avgAlpha` / 日行情 `dayAlpha` 若仍相对该序列，会**静默**把个股超额当指数超额。

## 决策

1. **`exchange_prefix`**：`5xxxxx` → `sh`（与 `6`/`9` 并列）；深市基金 `1xxxxx` 仍 `sz`；北交所规则不变。
2. **基准身份单点** `stock_platform_research.benchmark`：
   - `resolve_benchmark_symbol` / `quote_benchmark_key` / `engine_benchmark_code` / `resolve_benchmark_identity`
   - 已知指数码（`000905`/`000300`/…）的**外部报价键**强制 `sh000905` 等（与个股前缀规则解耦）
   - 名称须命中指数别名表；命中失败 → `alphaAvailable=false` + 中文 `warning`，**不写 alpha**
3. day-quote / settle / sameday / digest 路径消费 `alphaAvailable`；禁止 silent 个股当指数。
4. 不迁默认品种到别的指数；不写 `market.db`；不改选股权重。

## 后果

**正面**：沪市 ETF 四源可取；alpha 在碰撞时显式 unavailable。  
**代价**：本机引擎若只有「厦门港务」序列，默认基准下 alpha 段为空，直到生产侧入库真指数或 `STOCK_PLATFORM_BENCHMARK_SYMBOL` 指向库内可核对名称的指数码。
