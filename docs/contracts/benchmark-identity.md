# 契约：基准身份（benchmark identity）

- 里程碑：`F1`
- 单点：`stock_platform_research.benchmark`
- ADR：[0090](../architecture/0090-benchmark-identity-and-sh-fund-prefix.md)
- 状态：生效（SIMULATE / 只读）

## 1. 目的

保证相对基准超额（alpha / dayAlpha）**只在基准可识别为声明指数时**写入；个股碰撞 fail-closed。

## 2. 符号与键

| 形式 | 函数 | 例 |
|------|------|-----|
| 裸码（默认 / 环境） | `resolve_benchmark_symbol` | `000905` |
| 外部报价键 | `quote_benchmark_key` | `sh000905`（已知指数强制 sh） |
| 引擎日线码 | `engine_benchmark_code` | `000905.SZ` / `510300.SH`（经 `exchange_prefix`） |

环境覆盖：`STOCK_PLATFORM_BENCHMARK_SYMBOL`。

## 3. 身份块 `resolve_benchmark_identity`

| 字段 | 含义 |
|------|------|
| `ok` / `checked` | 已知指数表内且名称匹配别名 → ok；未知码 `checked=false` 且默认放行 |
| `alphaAvailable` | `false` 时调用方**禁止**写 alpha / dayAlpha |
| `warning` | 中文说明；可进报告 `benchmarkWarning` |
| `name` / `expectedHints` | fundamentals 名 vs 别名表 |

已知指数别名表：`KNOWN_INDEX_NAME_HINTS`（至少含中证500 / 沪深300 / 中证1000 / 上证50）。

## 4. 沪市基金前缀（providers）

`exchange_prefix("5xxxxx") == "sh"`。深市基金 `1xxxxx` → `sz`。详见 ADR 0090 与 `packages/providers` 单测。

## 5. 非目标

不写 `market.db`；不强制改默认基准品种；不把辩论/LLM 接入身份判定。
