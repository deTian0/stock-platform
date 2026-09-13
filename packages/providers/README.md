# packages/providers

统一行情 / 基本面 Vendor。安装名：`stock-platform-providers`；导入名：`stock_platform_providers`。

## 状态

| 版本 | 能力 |
|------|------|
| M1.1 / v0.1.1 | `normalize_symbol` / `exchange_prefix` |
| M1.2 / v0.1.2 | `ReplayProvider` daily + realtime 录制回放 |
| **M1.3 / v0.1.3** | `em_get` 东财限流单点 + `build_capability_matrix` |

## 安装

```powershell
cd D:\workspace\git\stock-platform\packages\providers
python -m pip install -e ".[dev]"
python -m pytest -q
```

Live 东财 HTTP（可选）：

```powershell
python -m pip install -e ".[http]"
```

## 公开 API（当前）

| 符号 | 作用 |
|------|------|
| `normalize_symbol` / `exchange_prefix` / `is_bse_symbol` | A 股代码 |
| `ReplayTransport` / `ReplayProvider` | fixtures 回放 |
| `em_get` / `EastmoneyClient` | **唯一**东财 HTTP 入口 |
| `build_capability_matrix` / `register_builtin_providers` | 能力路由 |
| `SymbolError` | 非法代码 |

## 硬约束

- **新代码禁止直连东财 URL** — 见 [`docs/contracts/eastmoney-http.md`](../../docs/contracts/eastmoney-http.md)
- 对外字段遵循 [`docs/contracts/datasets.md`](../../docs/contracts/datasets.md)
- 缺能力 fail-closed（矩阵 `usable=false`）
