# ADR 0005：东财限流单点与能力矩阵运行时

- 状态：Accepted
- 日期：2026-09-13

## 背景

多仓各自 `requests.get` 东财易触发封 IP；能力路由若散落在 UI 会静默换错源。

## 决策

1. 本仓唯一东财入口：`em_get` / `EastmoneyClient`（串行间隔 + 抖动 + 可选 Session）。
2. `em_get` **拒绝**非 eastmoney.com URL，防止误用成通用 HTTP 客户端。
3. `CAPABILITY_REGISTRY`（7 项）+ `build_capability_matrix` 为路由文字/运行时权威；`register_builtin_providers` 注册 `replay`（可用）与 `astock_http`（pending）。
4. Live HTTP 适配器可后续接上，但必须调用 `em_get`，禁止裸请求。

## 后果

- 文档与 CI 测试锁死「禁裸东财 URL」与矩阵 fail-closed。
- `requests` 为 optional extra `[http]`；限流逻辑单测不依赖真实网络。
