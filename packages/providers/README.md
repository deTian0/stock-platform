# packages/providers

统一行情 / 基本面 Vendor。安装名：`stock-platform-providers`；导入名：`stock_platform_providers`。

## 状态

| 版本 | 能力 |
|------|------|
| M1.1 / v0.1.1 | `normalize_symbol` / `exchange_prefix` |
| **M1.2 / v0.1.2** | `ReplayProvider`：daily + realtime **录制回放**（无网络） |

尚无 live HTTP（M1.3 起接东财限流单点）。

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
| `exchange_prefix(code)` | `sh` / `sz` / `bj` |
| `is_bse_symbol(code)` | 北交所号段（4/8/92） |
| `ReplayTransport` / `ReplayProvider` | 从 fixtures 读 daily/realtime |
| `SymbolError` | 非法代码 |

### 回放约定

```text
fixtures/daily_{symbol}.json      # list 或 {"bars":[...]}
fixtures/realtime_{symbol}.json   # quote dict 或 {"quote":{...}}
```

字段经 `normalize_*_row` 转为 `docs/contracts/datasets.md` 口径（`volume`=手，`amount`=元，比例小数制；`pct_unit=percent` 时自动 /100）。

## 约束

- **新代码禁止直连东财 URL**；必须走未来 `_em_get`（M1.3）
- 对外只暴露契约字段
- 测试优先录制回放，少依赖 live
