# packages/providers

统一行情 / 基本面 Vendor。安装名：`stock-platform-providers`；导入名：`stock_platform_providers`。

## 状态

**M1.1（v0.1.1）**：可 `pip install -e`；已提供 A 股 `normalize_symbol` / `exchange_prefix`。  
尚无 HTTP 取数（M1.2+）。

## 安装

```powershell
cd D:\workspace\git\stock-platform\packages\providers
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 公开 API（当前）

| 符号 | 作用 |
|------|------|
| `normalize_symbol(raw, market="CN")` | 归一为 6 位 A 股代码；拒港美/中文名 |
| `exchange_prefix(code)` | `sh` / `sz` / `bj`（腾讯等前缀） |
| `is_bse_symbol(code)` | 北交所号段（4/8/92） |
| `SymbolError` | 非法代码 |

## 计划吸收

- `a-stock-data`（A 股配方）→ M1.2+
- `TradingAgents-astock` 的 `a_stock.py` 去重合并 → M1
- `global-stock-data` → M5

## 约束

- 东财请求必须走单一限流入口（M1.3 `_em_get`）
- 对外只暴露契约字段（见 `docs/contracts/`）
- 新代码禁止直连东财 URL（绕过限流）
- 测试优先录制回放，少依赖 live
