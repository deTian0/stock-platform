# ADR 0025：CN 财务报表（financial）

- 状态：Accepted
- 日期：2026-09-14

## 背景

能力矩阵 TSP 原第六项 `financial` 长期无候选（fail-closed 409）。
a-stock-data §6.4 新浪财报三表（资产负债表/利润表/现金流量表）已文档化；
本仓 `global_http` 已使用新浪 HTTP。财报不走东财，故**不得**经 `em_get`。

## 决策

1. **不新增**能力 id：在既有 `financial` 上注册 `replay` / `astock_http`。
2. 契约：聚合 payload — `symbol` + `periods` + `income`/`balance`/`cashflow`
   （按 `period_end` 倒序的期次列表）+ `source`/`asset_type`；金额 **元**。
   标准列对齐 TSP/fuyao 语义（`revenue`/`net_income`/…）。
3. HTTP：新浪 `CompanyFinanceService.getFinanceReport2022`
   （`lrb`/`fzb`/`llb`）；可注入 `get_json`；**禁止**经 `em_get`。
4. `ReplayProvider.get_financial` 读 `financial_{symbol}.json`；缺文件返回空贡献。
5. `AStockHttpProvider.get_financial` 走 `_fetch_sina`（非东财路径）。
6. `global_*` 不声明 `financial`；workbench 默认 `financial=replay`。
7. **不做** mootdx、东财财报备胎、指标大宽表、默认 live。

## 后果

- 有候选时 `/api/market/financial` 不再 409；`adj_factor` / `full_minute` 等仍 fail-closed。
- 单票 live 路径 3 次新浪请求（三表）；不占用东财限流配额。
