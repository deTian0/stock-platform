# ADR 0024：CN 五档盘口（depth5）

- 状态：Accepted
- 日期：2026-09-14

## 背景

能力矩阵 TSP 原第五项 `depth5` 长期无候选（fail-closed 409）。
实时行情已走东财 `push2/api/qt/stock/get`；同端点买卖五档 `f` 字段即可取盘口，
无需新域名。a-stock-data 首选 mootdx TCP，但本仓红线要求东财只走 `em_get`，
故采用 push2 HTTP 配方。

## 决策

1. **不新增**能力 id：在既有 `depth5` 上注册 `replay` / `astock_http`。
2. 契约：`symbol` + `bid_prices`/`bid_volumes`/`ask_prices`/`ask_volumes`
   （各长度 5；价=元，量=**手**）+ `asof_ts`（Unix 毫秒 UTC）+
   `source`/`asset_type`；对齐 TSP `get_depth_batch` 数组语义。
3. HTTP：同 realtime `QUOTE_URL`，`fltt=2`；买一～五 `f19/f20`…`f11/f12`，
   卖一～五 `f39/f40`…`f31/f32`；`f86` 为时间戳。
4. `ReplayProvider.get_depth5` 读 `depth5_{symbol}.json`；缺文件返回空列表。
5. `AStockHttpProvider.get_depth5` 经 `em_get` / 可注入 `get_json`（CI 零公网）。
6. `global_*` 不声明 `depth5`；workbench 默认 `depth5=replay`。
7. **不做** mootdx、交易所官方五档备胎、默认 live。

## 后果

- 有候选时 `/api/market/depth5` 不再 409；`financial` / `adj_factor` 等仍 fail-closed。
- 单票 live 路径 1 次东财 quote 请求，经 `em_get` 限流。
