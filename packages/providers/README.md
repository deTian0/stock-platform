# packages/providers

统一行情 / 基本面 Vendor（规划包名暂定 `stock_platform_providers`）。

## 状态

**占位（v0.0.x）** — 无安装入口、无运行时。

## 计划吸收

- `a-stock-data`（A 股配方）→ M1
- `TradingAgents-astock` 的 `a_stock.py` 去重合并 → M1
- `global-stock-data` → M5

## 约束

- 东财请求必须走单一限流入口（未来 `_em_get`）
- 对外只暴露契约字段（见 `docs/contracts/`）
- 测试优先录制回放，少依赖 live

待 M1.1 添加 `pyproject.toml` 与 `src/` 布局。
