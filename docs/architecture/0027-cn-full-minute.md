# ADR 0027：CN 全量分钟（full_minute）

- 状态：Accepted
- 日期：2026-09-14

## 背景

能力矩阵 TSP 原第七项 `full_minute` 长期无候选（fail-closed 409）。
M18 已交付个股多频 `minute`（ADR 0023），并明确不做 full_minute。
TSP 语义是盘中全市场当日 1 分钟 K 批量修复轮；本仓以薄 Provider
切片激活矩阵，不引入后台落盘服务。

## 决策

1. **不新增**能力 id：在既有 `full_minute` 上注册 `replay` / `astock_http`。
2. 方法：`get_full_minute(symbols, trade_date=, count=300)` —— **始终 `freq=1m`**；
   单日窗口；每标的尾部截断 `count`（会话约 240 根）。
3. 行字段复用 `MINUTE_COLUMNS`；`datetime` 为北京墙钟 naive。
4. **与 `minute` 区分**：`minute` = 多频历史分时；`full_minute` = 当日 1m 宇宙批量。
   Replay **不**回退读 `minute_{symbol}.json`。
5. HTTP：东财 push2his kline `klt=1`，`beg=end=trade_date`；经 `em_get` /
   可注入 `get_json`；`trade_date=None` → Asia/Shanghai 今日。
6. `ReplayProvider` 读 `full_minute_{symbol}.json`；缺文件跳过（空贡献）。
7. `global_*` 不声明；workbench 默认 `full_minute=replay`。
8. **不做** `minute_refresh` 后台、本地分区落盘、`get_intraday_latest`、腾讯备胎、默认 live。

## 后果

- 有候选时 `/api/market/full-minute` 不再 409；矩阵十项 CN 能力均可 usable。
- 批量 live 路径每标的 1 次东财 kline 请求，经 `em_get` 限流。
