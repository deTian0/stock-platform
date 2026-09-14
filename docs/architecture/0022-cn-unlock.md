# ADR 0022：CN 限售解禁（unlock）

- 状态：Accepted
- 日期：2026-09-14

## 背景

M16 已提供个股 `lhb`。上游 a-stock-data §3.6 `lockup_expiry`
（datacenter-web `RPT_LIFT_STAGE`）与 TradingAgents `get_lockup_expiry`
尚未迁入；研报常需历史解禁与未来待解禁预警。

## 决策

1. 能力矩阵新增第十项 `unlock`（TSP 原七项 + `fund_flow` + `lhb` 顺序保留在前）。
2. 契约为聚合 payload：`symbol/asof_date/forward_days/history/upcoming`
   + `source/asset_type`；`shares`/`able_shares` 单位 **万股**（东财原始）；
   `ratio` **小数制**。
3. 列名以 a-stock-data §3.6 为准：`FREE_SHARES_TYPE` / `FREE_SHARES` /
   `ABLE_FREE_SHARES`；兼容旧列名回退。
4. `ReplayProvider.get_unlock` 读 `unlock_{symbol}.json`；
   `AStockHttpProvider.get_unlock` 走 `em_get` → datacenter-web（可注入 `get_json`；CI 零公网）。
5. 空历史 / 空待解禁返回空列表，禁止崩溃。
6. 仅 `replay` / `astock_http` 声明该能力；`global_*` 不声明。
7. workbench 默认偏好 `unlock=replay`；可选切 `astock_http`。
8. **不做** 全市场解禁日历、分钟/板块资金流。

## 后果

- 矩阵行数由 9→10；缺 `unlock` 仍 fail-closed（409）。
- 单票 live 路径最多 2 次东财请求（历史 + 未来），均经 `em_get` 串行限流。
