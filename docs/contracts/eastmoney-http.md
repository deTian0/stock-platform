# 东财请求规范

> 状态：Accepted（M1.3）  
> 实现：`stock_platform_providers.eastmoney`

## 硬规则

1. **禁止**对 `*.eastmoney.com` 使用裸 `requests.get` / `urllib` / `httpx`。
2. **必须**使用 `em_get(...)` 或同一进程内的 `EastmoneyClient.get(...)`。
3. 非东财源（腾讯 / 新浪 / mootdx / 同花顺等）**不要**走 `em_get`（会被 URL 校验拒绝）。

## 限流

| 项 | 默认 | 覆盖 |
|----|------|------|
| 最小间隔 | 1.0s | 环境变量 `EM_MIN_INTERVAL` |
| 抖动 | 0.1–0.5s | 客户端构造时注入 `rng` |
| 并发 | 进程内锁串行 | — |

批量任务建议 `EM_MIN_INTERVAL=1.5`～`2`。

## 熔断（M30）

| 项 | 默认 | 覆盖 |
|----|------|------|
| 连续失败阈值 | 5 | `EM_CIRCUIT_FAILURES`（`0` 关闭熔断） |
| 冷却 | 60s | `EM_CIRCUIT_COOLDOWN` |
| 打开后 | 抛 `CircuitOpenError`，不打东财 | `snapshot()` 可读状态 |

成功请求清零失败计数。不自动换源（fail-closed）。

## 依赖

```powershell
pip install "stock-platform-providers[http]"
```

单测使用注入 `transport`，不访问公网。

## 已知东财端点（本仓）

| 用途 | URL（须经 `em_get`） |
|------|----------------------|
| 日 K | `push2his.../api/qt/stock/kline/get`（`klt=101`） |
| 分钟 K（M18） | 同上 URL，`klt=1/5/15/30/60`；`datetime` 北京墙钟 naive |
| 实时 | `push2.../api/qt/stock/get` |
| 五档盘口（M19） | 同上 URL；买/卖五档 `f19`…`f12` / `f39`…`f32`；量=手 |
| 日级资金流（M15） | `push2his.../api/qt/stock/fflow/daykline/get` |
