# ADR 0020：CN 日级资金流（fund_flow）

- 状态：Accepted
- 日期：2026-09-14

## 背景

M8 已提供 `AStockHttpProvider` 日 K / 实时（经 `em_get`）。上游 a-stock-data §4.5
`stock_fund_flow_120d`（push2his `fflow/daykline`）尚未迁入；研报与选股常需日级主力净流入。

## 决策

1. 能力矩阵新增第八项 `fund_flow`（TSP 原七项顺序保留在前；本项为平台扩展）。
2. 契约字段：`symbol/date/main_net/small_net/mid_net/large_net/super_net` +
   `source/asset_type`；净流入单位 **元**。
3. `ReplayProvider.get_fund_flow` 读 `fund_flow_{symbol}.json`；
   `AStockHttpProvider.get_fund_flow` 走 `em_get`（可注入 `get_json`；CI 零公网）。
4. 仅 `replay` / `astock_http` 声明该能力；`global_*` 不声明。
5. workbench 默认偏好 `fund_flow=replay`；可选切 `astock_http`。
6. **不做** 分钟资金流、板块资金流、龙虎榜（后续里程碑）。

## 后果

- 矩阵行数由 7→8；缺 `fund_flow` 仍 fail-closed（409）。
- 东财 `lmt` 默认 120；`start`/`end` 在 Provider 侧截断，禁止静默用「今天」覆盖历史区间。
