# ADR 0013：A 股 live HTTP（em_get）

- 状态：Accepted
- 日期：2026-09-14

## 背景

v1.0 默认 replay。产品下一步需可选 live 日 K / 实时，且不得绕过东财限流单点。

## 决策

1. 新增 `AStockHttpProvider`（`name=astock_http`），日 K 走 `push2his` kline，实时走 `push2` stock/get。
2. **所有**请求经注入的 `EastmoneyClient` / `em_get`；单测用 `get_json` 注入，CI 不访问公网。
3. 能力矩阵中 `astock_http` 标为 usable；workbench **默认偏好仍为 replay**。
4. `secid` 经 `exchange_prefix`：沪 `1.*`，深/北 `0.*`。
5. 日 K `fqt=0`（不复权）；涨跌幅按 EM 百分数 + `pct_unit=percent` 归一。

## 后果

- 公网可用性依赖东财；封禁时应用降级回 replay，不得静默换裸 URL。
- 美港 live 见 ADR 0014（`global_http`）。
