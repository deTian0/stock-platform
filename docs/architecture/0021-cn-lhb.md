# ADR 0021：CN 龙虎榜（lhb）

- 状态：Accepted
- 日期：2026-09-14

## 背景

M15 已提供日级 `fund_flow`。上游 a-stock-data §3.5 `dragon_tiger_board`
（datacenter-web `RPT_DAILYBILLBOARD_*`）与 TradingAgents `get_dragon_tiger_board`
尚未迁入；研报常需个股上榜记录与营业部席位。

## 决策

1. 能力矩阵新增第九项 `lhb`（TSP 原七项 + `fund_flow` 顺序保留在前）。
2. 契约为聚合 payload：`symbol/asof_date/look_back_days/records/seats/institution`
   + `source/asset_type`；金额单位 **元**；`turnover_rate` **小数制**。
3. `ReplayProvider.get_lhb` 读 `lhb_{symbol}.json`；
   `AStockHttpProvider.get_lhb` 走 `em_get` → datacenter-web（可注入 `get_json`；CI 零公网）。
4. 空回看窗口返回空结构（对齐 a-stock-data #45），禁止崩溃。
5. 仅 `replay` / `astock_http` 声明该能力；`global_*` 不声明。
6. workbench 默认偏好 `lhb=replay`；可选切 `astock_http`。
7. **不做** 全市场日榜、交易所官方备胎、分钟/板块资金流。

## 后果

- 矩阵行数由 8→9；缺 `lhb` 仍 fail-closed（409）。
- 单票 live 路径最多 3 次东财请求（记录 + 买席位 + 卖席位），均经 `em_get` 串行限流。
