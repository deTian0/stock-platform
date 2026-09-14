# ADR 0032：运维健康检查

- 状态：Accepted
- 日期：2026-09-14

## 背景

`GET /health` 只回答进程是否起来，不能看到默认是否仍 replay、东财是否熔断、
最近一次本地刷新是否失败。

## 决策

1. **保留** `GET /health` 作为存活探针（负载均衡 / 编排用）。
2. **新增** `GET /api/ops/health`：
   - `liveTradingEnabled=false`、`executionMode=SIMULATE`
   - `defaultReplay`：当前进程 preferences 是否全为 replay
   - `eastmoney`：`EastmoneyClient.snapshot()`（节流 + 熔断；无网络）
   - `lastRefresh`：若设置 `STOCK_PLATFORM_REFRESH_DIR` 则读 `latest.json`，否则 `null`
   - 熔断打开或 lastRefresh.ok=false → `status=degraded`（HTTP 仍 200）
3. Fixture 录制 / 刷新步骤见 [`docs/ops/refresh-and-fixtures.md`](../ops/refresh-and-fixtures.md)。
4. **不做**：鉴权网关、对外暴露密钥、自动切 live、板块资金流 / 新闻。

## 后果

- 编排可继续探 `/health`；人/脚本看 `/api/ops/health`。
- CI 不设 refresh dir 时 `lastRefresh` 为空，不误报。
