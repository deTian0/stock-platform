# ADR 0048：Tushare-compatible HTTP 补充日 K

- 状态：Accepted
- 日期：2026-09-15

## 背景

生产默认 CN live 走 `astock_http` / `em_get`。需要可选的 Tushare 兼容 HTTP 源作 **补充**（不替换默认），用于日 K 与交易日历探测。

## 决策

1. 新增 `TushareHttpProvider`（`name=tushare_http`），核心路径用 **raw HTTP POST**  
   `{"api_name","token","params","fields"}`，**不**把 `tushare` SDK / MCP 作为硬依赖。
2. 环境变量：`STOCK_PLATFORM_TUSHARE_TOKEN`（必填才能拉数）、`STOCK_PLATFORM_TUSHARE_URL`（默认 `https://t.xiaodefa.top/`）。**禁止**把真实 token 写入仓库 / CHANGELOG 正文 / ROADMAP。
3. 能力矩阵首切片仅声明 **`daily`**（`api_name=daily`，不复权，对应 SDK `pro_bar` 未复权形态）。`get_trade_cal` 作为 helper 暴露，不进矩阵 id。
4. 预设 `cn_tushare_http`：`daily → tushare_http`，其余 CN 能力仍 `astock_http`。启动默认仍为 `cn_astock_http`。
5. 符号：`600519` ↔ `600519.SH` / `000001` ↔ `000001.SZ`（经 `exchange_prefix`）。
6. 单测注入 `post_json`；CI 零公网。成交额 Tushare 千元 → 契约元（×1000）。

## 后果

- 缺 token / 上游非 0 code → fail-closed（`TushareHttpError`），不静默回退 fixtures。
- realtime / adj / financial 等未映射前不得宣称 usable；后续切片再扩。
- 与东财限流无关；不经 `em_get`。
