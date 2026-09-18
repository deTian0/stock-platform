# ADR 0051：概念板块归属（concept_blocks）

- **状态**：Accepted
- **日期**：2026-09-18
- **相关**：M-D1 / M-D3 · [`docs/contracts/capability-matrix.md`](../contracts/capability-matrix.md) · a-stock-data §3.3

## 背景

游资/板块叙事与 Agent 角色需要「个股所属行业/概念/地域」列表。Skill 配方
`eastmoney_concept_blocks`（东财 push2 `slist`，`spt=3`）已稳定；平台矩阵此前未声明。

## 决策

1. 能力矩阵新增第 13 项：`concept_blocks`（接在 `news` 之后）。
2. 契约聚合载荷：`symbol` / `source` / `asset_type` / `total` / `boards[]` /
   `concept_tags[]`；`boards` 元素含 `name`、`code`（BK####）、可选 `change_pct`、
   `lead_stock`。东财不区分行业/概念/地域类型（混列），平台原样透传。
3. `ReplayProvider`：`concept_blocks_{symbol}.json`；缺 fixture → `SymbolError`。
4. `AStockHttpProvider`：`push2.eastmoney.com/api/qt/slist/get`，经 `_fetch` / `em_get`；
   `secid` 走 `em_secid`。
5. 仅 `replay` / `astock_http` 声明；`global_*` / `engine_sqlite` 不声明。
6. Workbench：`GET /api/market/concept-blocks`；缺能力 fail-closed。

## 非目标

- 全市场板块树 UI、iwencai、平行 Skill 运行时。
- 百度 PAE `getrelatedblock`（已失效，见 Skill 变更记录）。

## 后果

- 矩阵 12→13；CI 用 replay fixtures，零公网。
- 批量拉取须尊重 `EM_MIN_INTERVAL`。
