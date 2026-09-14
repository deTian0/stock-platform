# ADR 0023：CN 分钟 K（minute）

- 状态：Accepted
- 日期：2026-09-14

## 背景

能力矩阵 TSP 原第四项 `minute` 长期无候选（fail-closed 409）。
日 K 已走东财 `push2his/api/qt/stock/kline/get`（`klt=101`）；同端点
`klt=1/5/15/30/60` 即可取分钟线，无需新域名。

## 决策

1. **不新增**能力 id：在既有 `minute` 上注册 `replay` / `astock_http`。
2. 契约：`symbol/datetime/open/high/low/close/volume/amount/freq` +
   `source/asset_type`；`datetime` 为 **北京墙钟 naive** 字符串
   （`YYYY-MM-DD HH:MM:SS`），禁止 tz / `Z` / UTC 入库。
3. `freq` ∈ `1m|5m|15m|30m|60m`；HTTP 映射 `klt` 同名分钟数。
4. `ReplayProvider.get_minute` 读 `minute_{symbol}.json`；缺文件返回空列表。
5. `AStockHttpProvider.get_minute` 经 `em_get` / 可注入 `get_json`（CI 零公网）。
6. `global_*` 不声明 `minute`；workbench 默认 `minute=replay`。
7. **不做** `full_minute`、腾讯备胎、分钟资金流、默认 live。

## 后果

- 有候选时 `/api/market/minute` 不再 409；`depth5` 等仍 fail-closed。
- 单票 live 路径 1 次东财 kline 请求（按 freq），经 `em_get` 限流。
