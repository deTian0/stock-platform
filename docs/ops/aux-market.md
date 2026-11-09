# 补充行情库增量（`stock-platform-aux-market`）

> **状态**：ADR [`0095`](../architecture/0095-aux-market-store.md) Accepted。  
> **操作员清单**：[`workbuddy-runbook.md`](workbuddy-runbook.md) §4。  
> **红线**：只写 `local/aux_market/aux_market.db`；**永不**写引擎 `market.db`。

## 何时

定期增量（建议每周或盘后）。离线回测 / 影子超额依赖较新的指数日线；**日循环 settle 仍不读**本库。

## 命令

```powershell
cd <repo-root>
# 默认 5 指数；幂等；--start 可收到近窗做增量
stock-platform-aux-market --start 2020-01-01
stock-platform-aux-market --dry-run --json   # 零网络看计划
# 可选个股 OHLC（显式代码，不做全市场）
# stock-platform-aux-market --codes 600519,000001 --start 2024-01-01
```

| 参数 | 说明 |
|------|------|
| `--indices` | 逗号列表；默认 000300/000905/000852/000016/399006；传空串不抓指数 |
| `--codes` | 个股列表；默认不抓 |
| `--start` / `--end` | 窗口；`--end` 默认今天（Asia/Shanghai） |
| `--db` | 覆盖路径；**不得**为 `market.db` 或与 `STOCK_PLATFORM_ENGINE_MARKET_DB` 同路径 |
| `--budget` | 当日 em 请求预算（默认 60） |
| `--dry-run` / `--json` | 计划 / JSON 输出 |

## 产物与失败

| 项 | 说明 |
|----|------|
| 产物 | `local/aux_market/aux_market.db`（`STOCK_PLATFORM_AUX_MARKET_DB`） |
| 成功 | stdout `ok=…`；单代码 `status` + `rows` |
| fail-soft | 单代码失败 / 名称拒写 / 预算超限不抛；整命令仍 exit 0（参数非法除外） |
| 东财 | 只经 `em_get` |

## 交叉链

- CLI 一览：[`cli-catalog.md`](cli-catalog.md)  
- 契约：[`../contracts/datasets.md`](../contracts/datasets.md)（补充行情库节）  
- 基准回落：[`../contracts/benchmark-identity.md`](../contracts/benchmark-identity.md)
