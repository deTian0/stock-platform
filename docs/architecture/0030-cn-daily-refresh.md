# ADR 0030：CN 日数据刷新 / full_minute 落盘

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase A 已能用 PIT 截面做盘前简报，但宇宙日 K / 复权因子 / 资金流 / 当日 1m
仍依赖手工 fixtures。运维需要可重复的本地刷新，且 CI 不得打公网。

## 决策

1. **任务内核**：`stock_platform_research.run_refresh` 注入 provider（Protocol），
   默认 datasets：`daily` / `adj_factor` / `fund_flow` / `full_minute`。
2. **重试**：每个 (symbol, dataset) 最多 N 次（默认 3）；失败写入 manifest，作业继续。
   空 `daily` **fail-closed**。空宇宙 `UniverseEmptyError`。
3. **落盘**：`STOCK_PLATFORM_REFRESH_DIR` 或 `--out`；布局 `{out}/{asof}/`，
   文件名与 `ReplayTransport` 一致（`daily_{symbol}.json` 等）+ `manifest.json`；
   根目录 `latest.json` 供 ops health 读取。
4. **CLI**：`stock-platform-refresh`；CI 使用 `--provider replay --fixtures …`。
   不在本里程碑默认接 `astock_http`（live 仍 opt-in）。
5. **不做**：后台常驻调度器、板块资金流、`get_intraday_latest`、默认 live、公网 CI。

## 后果

- 刷新产物可直接当作 replay fixtures 目录。
- 调用方若要用 live，须自行构造 `AStockHttpProvider` 并承受 `em_get` 节流。
