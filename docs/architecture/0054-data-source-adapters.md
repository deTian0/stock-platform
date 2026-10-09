# ADR 0054：数据源适配层（workbuddy / tdx / futu）

- 状态：Accepted
- 日期：2026-10-10

## 背景

生产默认 CN live 走 `astock_http` / `em_get`，补充源有 `tushare_http`（HTTP）、`engine_sqlite`（本地库）。用户需要**多源兼容**：WorkBuddy 自己的 MCP 数据能力（`westock-data` / `neodata-financial-search`）、通达信（TDX）本地数据、富途（Futu）OpenAPI —— 均以统一 provider 协议接入，不替换默认源。

## 决策

1. 新增三个 provider，全部实现 `MarketDataProvider`（`name` + `get_daily` / `get_realtime`），输出经 `normalize_daily_row` / `normalize_realtime_row` 归一；**缺源即 fail-closed**（中文报错，不静默回退）。
2. **`workbuddy`** = JSON 缓存适配器。WorkBuddy MCP 能力面向 agent（Markdown 表 / 自然语言），非确定性 OHLC API；规范交接点定为 JSON 缓存目录（`STOCK_PLATFORM_WORKBUDDY_CACHE_DIR`），布局与 `replay` fixture 同构（`daily_{code}.json` / `realtime_{code}.json`）。`write_daily_cache` / `write_realtime_cache` 是 schema 唯一生产点。读路径零网络、完全可单测。
3. **`tdx`** = 读通达信本地 `vipdoc/{sh,sz,bj}/lday/*.day`（32 字节定长记录，`struct` 解析，零依赖）。`STOCK_PLATFORM_TDX_ROOT` 或自动探测常见安装目录。实时未映射（TDX 实时来自桌面端 TCP）→ `NotImplementedError`。
4. **`futu`** = 懒加载 `futu` 包连 OpenD（默认 `127.0.0.1:11111`）。`get_daily` → `request_history_kline`、`get_realtime` → `get_market_snapshot`。缺包 / 无网关 fail-closed。符号 `600519` ↔ `SH.600519` 经 `exchange_prefix`。
5. 三个预设 `workbuddy` / `cn_tdx` / `cn_futu`（均 `is_default=False`），能力矩阵各声明对应数据集；启动默认仍 `cn_astock_http`。
6. 测试零网络：`workbuddy` 用规范写入器合成 JSON、`tdx` 用 `struct.pack` 合成 `.day`、`futu` 注入 fake module + fake quote_ctx。

## 后果

- `workbuddy` 的「MCP 兼容」= MCP 桥接方落 JSON 缓存 → provider 只读消费；若后续 westock/neodata 暴露稳定机器 schema，可在**不破坏契约**的前提下把 provider 换成直连（当前刻意不直连，避免解析 Markdown / 自然语言的脆弱性）。
- TDX 是未复权本地价、实时不可用；Futu 依赖第三方 `futu-api` + OpenD（本机未装）—— 两者都属「装好即可用」的适配器，非开箱即用。
- 所有新源都**不触碰** `liveTradingEnabled`，仅数据读路径。
