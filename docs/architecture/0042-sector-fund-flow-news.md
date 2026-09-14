# ADR 0042：板块资金流（sector_fund_flow）与轻量新闻（news）

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase E / M41 要为日用推荐补板块级资金流与轻量新闻特征。个股 `fund_flow`（ADR 0020）
已覆盖日级主力净流入；板块日级序列与新闻特征此前未进能力矩阵。

## 决策

1. 能力矩阵新增两项平台扩展：`sector_fund_flow`、`news`（顺序接在 `unlock` 之后）。
2. `sector_fund_flow` 契约字段：`sector_code/date/main_net` + 可选
   `sector_name/change_pct` + `source` + `asset_type`（`sector` 或 `index`）；净流入 **元**。
3. `news` 契约字段：`symbol` 或 `sector_code`（至少其一）、`date`、`title`，可选
   `summary` / `sentiment`（float，可 null）+ `source`。**不做**默认 LLM 摘要。
4. `ReplayProvider`：`sector_fund_flow_{code}.json` / `news_{symbol}.json`；缺 fixture →
   `SymbolError`（fail-closed）。
5. `AStockHttpProvider`：
   - 板块资金流：push2his `fflow/daykline`，`secid=90.BK####`，经 `_fetch` / `em_get`。
   - 新闻：np-weblist `getFastNewsList`（轻量列表，按请求 symbol 打标），经 `em_get`。
6. 仅 `replay` / `astock_http` 声明；`global_*` 不声明。默认偏好仍为 replay。
7. workbench 提供只读 API（`/api/market/sector-fund-flow`、`/api/market/news`）+ 薄 UI；
   CI 注入假 transport / replay，零公网。

## 后果

- 矩阵行数由 10→12；缺能力仍 fail-closed（409）。
- 东财请求继续串行走 `em_get`；新闻路径不做情绪模型推断（`sentiment` 仅透传/可 null）。
