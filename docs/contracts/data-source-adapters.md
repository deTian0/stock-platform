# 数据源适配层契约（workbuddy / tdx / futu）

> 状态：Accepted｜目标 tag：`v3.13.9`（2026-10-10）
> 关联：`docs/architecture/0054-data-source-adapters.md`

三个新 provider 都实现 `MarketDataProvider` 协议（`name` + `get_daily` + `get_realtime`），输出经 `normalize_daily_row` / `normalize_realtime_row` 归一为契约行。**所有适配器缺源即 fail-closed**（中文报错，绝不静默回退其它源）。

| provider | 能力 | 数据源 | 环境变量 | 实时 |
|---|---|---|---|---|
| `workbuddy` | `daily` + `realtime` | WorkBuddy MCP 落盘的 JSON 缓存 | `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR` | 是 |
| `tdx` | `daily` | 通达信本地 `vipdoc/*/lday/*.day` | `STOCK_PLATFORM_TDX_ROOT`（或自动探测） | **否**（fail-closed） |
| `futu` | `daily` + `realtime` | 富途 OpenAPI（OpenD 网关） | `STOCK_PLATFORM_FUTU_HOST` / `PORT` | 是 |

---

## 1. workbuddy — JSON 缓存适配器

### 1.1 为什么是 JSON 缓存

WorkBuddy 的金融数据能力（`westock-data` CLI、`neodata-financial-search` HTTP）是**面向 agent** 的：前者输出结构化 Markdown 表、后者是自然语言问答。二者都不构成「确定性、可机器调用的 OHLC API」。因此 provider 层的规范交接点是 **JSON 缓存目录**：MCP 桥接方（agent 或一次薄导出）写入 JSON，provider 只读消费。这与 `replay`（fixtures）、`engine_sqlite`（本地库）的离线一致性模式同构，且**读路径零网络**、可完全单测。

### 1.2 目录布局（与 replay fixture 同构）

```
STOCK_PLATFORM_WORKBUDDY_CACHE_DIR/
  daily_600519.json       # {"symbol": "600519", "bars": [ {date, open, high, low, close, volume, amount, ...}, ... ]}
  realtime_600519.json    # {"symbol": "600519", "price": ..., "prev_close": ..., "change_pct": ..., "asof_ts": ...}
```

- `daily_{code}.json`：`bars` 是 raw bar 列表，字段对齐 `normalize_daily_row` 的 vendor 输入（`date` / `open` / `high` / `low` / `close` / `volume` / `amount` / `change_pct` / `pct_unit`）。
- `realtime_{code}.json`：`quote` 单条，字段对齐 `normalize_realtime_row`（`price` / `prev_close` / `change_pct` / `volume` / `amount` / `asof_ts`）。兼容 `{"quote": {...}}` 包裹形态。
- 缺文件 → 该 symbol 空贡献（不报错）；目录未配置/不存在 → `FileNotFoundError`（fail-closed）。

### 1.3 规范写入器

`write_daily_cache(symbol, bars, cache_dir)` / `write_realtime_cache(symbol, quote, cache_dir)` 是 **JSON schema 的唯一生产点**。MCP 桥接方只应经它们落盘，不得手拼文件。

---

## 2. tdx — 通达信本地日线

### 2.1 文件格式

`.day` 文件 = 定长 32 字节记录（little-endian）：

| 偏移 | 类型 | 字段 |
|---|---|---|
| 0 | uint32 | date（`YYYYMMDD`） |
| 4 | uint32 | open（×100） |
| 8 | uint32 | high（×100） |
| 12 | uint32 | low（×100） |
| 16 | uint32 | close（×100） |
| 20 | float32 | amount（元） |
| 24 | uint32 | volume（手） |
| 28 | uint32 | reserved |

路径：`{root}/vipdoc/{sh|sz|bj}/lday/{prefix}{code}.day`，`prefix` 经 `exchange_prefix`（`6`/`9`→sh、`4`/`8`/`92`→bj、其余→sz）。

### 2.2 边界

- `date==0` 或非法日期记录跳过；文件缺失 → 该 symbol 空贡献。
- `volume` 按 TDX 惯例为**手**（100 股），与契约一致；`amount` 为元。
- 无复权信息（`.day` 是未复权价）—— 使用者需自行注意除权跳变。
- `get_realtime` **未映射**（TDX 实时行情来自桌面端 TCP，非本地文件）→ `NotImplementedError`。

---

## 3. futu — 富途 OpenAPI

### 3.1 依赖与符号

- 懒加载 `futu` 包；缺包 → `RuntimeError`（中文，提示 `pip install futu-api` + 启动 OpenD）。
- 网关默认 `127.0.0.1:11111`，可经 `STOCK_PLATFORM_FUTU_HOST` / `STOCK_PLATFORM_FUTU_PORT` 覆盖。
- 符号映射 `600519` → `SH.600519` / `000001` → `SZ.000001` / `430047` → `BJ.430047`（`exchange_prefix` 单点）。

### 3.2 方法映射

- `get_daily` → `request_history_kline(code, ktype=K_DAY, autype=QFQ, max_count=10000)`；`time_key`→`date`、`turnover`→`amount`（元）。
- `get_realtime` → `get_market_snapshot(code_list)`；`last_price`→`price`、`price_change_rate`→`change_pct`、`update_time`→`asof_ts`。
- `ret != RET_OK` → `RuntimeError`；空帧 → 空贡献。

---

## 4. 预设

| 预设 id | 路由 |
|---|---|
| `workbuddy` | `daily`/`realtime` → `workbuddy`，其余 `replay` |
| `cn_tdx` | `daily` → `tdx`，其余 `replay` |
| `cn_futu` | `daily`/`realtime` → `futu`，其余 `replay` |

启动默认仍为 `cn_astock_http`；三个新预设均 `is_default=False`，经 `STOCK_PLATFORM_PROVIDER_PRESET` 显式启用。
