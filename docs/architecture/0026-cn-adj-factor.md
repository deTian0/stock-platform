# ADR 0026：CN 复权因子（adj_factor）

- 状态：Accepted
- 日期：2026-09-14

## 背景

能力矩阵 TSP 原第二项 `adj_factor` 长期无候选（fail-closed 409）。
a-stock-data §1.4 新浪复权因子（qfq/hfq JS）已文档化；
与 M20 财报同属已文档化新浪路径。因子不走东财，故**不得**经 `em_get`。

## 决策

1. **不新增**能力 id：在既有 `adj_factor` 上注册 `replay` / `astock_http`。
2. 契约：行级 payload — `symbol` + `trade_date` + `ex_factor` + `source`/`asset_type`。
   源字段 `factor`/`adj_factor`/`f`、`date`/`d` 在 Provider 内 rename。
3. HTTP：新浪 `finance.sina.com.cn/realstock/company/{prefix}{code}/{kind}.js`；
   默认 `kind=qfq`（前复权；hfq 可选）；`JSONDecoder.raw_decode` 解析（末尾 base64 注释）；
   可注入 `get_text`；**禁止**经 `em_get`。
4. `ReplayProvider.get_adj_factor` 读 `adj_factor_{symbol}.json`；缺文件返回空贡献。
5. `AStockHttpProvider.get_adj_factor` 走 `_fetch_sina_text`（非东财路径）。
6. `global_*` 不声明 `adj_factor`；workbench 默认 `adj_factor=replay`。
7. **不做** mootdx、东财复权备胎、`apply_adjust` 套价 API、默认 live。

## 后果

- 有候选时 `/api/market/adj-factor` 不再 409；`full_minute` 仍 fail-closed。
- 单票 live 路径 1 次新浪请求；不占用东财限流配额。
- qfq 因子为除数语义（前复权价 = 不复权价 ÷ factor）；本仓只交付因子序列，不套价。
