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

### 1.4 桥接：`westock` CLI → JSON 缓存（v4.1.8）

**问题**：provider 只读缓存，但此前**没有任何东西写入它** —— provider 的 docstring 提到一个"MCP bridge"，而那个 bridge 从未实现，所以 "workbuddy 模式"永远拿不到真实数据。

**解法**：`stock_platform_research.workbuddy_bridge` 补齐写的那一半。

```
westock kline <codes> --period day --limit N --fq qfq   ─┐
westock quote  <codes> [--date D]                        ─┴─► parse Markdown table
                                                              │
                                                              ▼
                                          write_daily_cache / write_realtime_cache
                                                              │
                                                              ▼
                                       STOCK_PLATFORM_WORKBUDDY_CACHE_DIR/*.json
```

**`westock` 来源**：WorkBuddy `finance-data` 插件自带安装脚本
（`skills/westock-data/scripts/setup.{cjs,ps1,sh}`），从
`https://stockbuddy.qq.com/release/workbuddy/cli` 下载带 SHA256 校验的 Go 二进制。
本机装于 `~/.local/bin/westock.exe`（`v0.0.4`，实测 2,600,960 B）。

**字段映射**（实测 `kline sh600519 --period day --limit 5`）：

| westock 列 | provider 字段 | 说明 |
|---|---|---|
| `date` | `date` | ISO `YYYY-MM-DD` |
| `open` / `high` / `low` | 同名 | — |
| `last` | `close` | **改名**：westock 用 `last` 表示收盘 |
| `volume` | `volume` | 手 |
| `amount` | `amount` | 元 |
| `change_pct` | `change_pct` | **percent 标度**（`0.574` == +0.574%），带 `pct_unit="percent"`，由 `normalize_daily_row` ÷100 |
| `exchange` | **丢弃** | 是换手率（%），不是交易所代码；语义不同不得挪用 |

`quote` 输出面更宽（42 列）；契约认识的字段被提升，`pe_ratio` / `pb_ratio` /
`total_market_cap` 等作为额外键原样保留（`normalize_realtime_row` 忽略未声明字段）。

**关键决策与守卫**

1. **批量调用**：`westock` 支持逗号分隔的代码列表（`kline a,b`），桥按 40/30 个一批合并调用，避免 5k 次进程启动。批量响应会**额外带一列 `code`**（单代码响应没有该列）。
2. **单代码响应归因**：无 `code` 列时，**仅当该批只有 1 个代码**才可归因；多代码批出现无 `code` 行 → 记入 `warnings` 并跳过，**绝不**把 bar 静默安到第一个 symbol 上。
3. **裸码碰撞守卫**：平台的符号契约（`normalize_symbol`）**有意丢弃交易所前缀**，所以 `sh000001`（上证指数）与 `sz000001`（平安银行）都归一为 `000001`，而缓存文件名无法区分二者。两个来源写同一个 `daily_000001.json` 会让 bar 静默交错 → 桥在抓取前**拒绝**这类歧义对（`warnings` 记录，其余 symbol 照常桥接）。
4. **explicit `--bin` 是权威**：显式传入的**路径**不存在即报错，绝不静默回落到 PATH；裸命令名才走 PATH 查找。同理 `STOCK_PLATFORM_WESTOCK_BIN` 一旦设置就只认它。
5. **失败软着陆**：单个 symbol 抓取失败只记入 `BridgeReport.items[].error`，不中断整轮；`--fail-on-error` 才把非零退出码带出。
6. **dry-run**：`--dry-run` 解析并报告但**不落盘**（可先验证连通性再写真缓存）。

**CLI**：`stock-platform-workbuddy-bridge`（`packages/research`）。
`--symbols` / `--symbols-file` / 默认取平台宇宙；`--datasets daily,realtime`；
`--limit` / `--start` / `--end` / `--period` / `--adjust` / `--asof` / `--timeout` / `--json`。

**实测证据**（2026-10-12，本机，`westock v0.0.4`）：

| 项 | 结果 |
|---|---|
| `--symbols sh600519,sz000001,sh510300,sh000001 --datasets daily,realtime --limit 30` | **8/8 ok / 124 bars / 0 failed** |
| bridge → `WorkbuddyProvider.get_daily([600519,000001,510300])` | **90 行**，跨度 `2026-08-21 → 2026-10-09`，`source="workbuddy"` |
| percent→decimal | `0.5741405808` → `0.005741405808` ✅ |
| 碰撞守卫（`sh000001`+`sz000001`） | `WARN code collision on 000001` + 跳过，`600519` 照常桥接 ✅ |
| 全链路（launcher → bridge → daily） | `provider="workbuddy"`，`ok: true` ✅ |

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

### 4.1 workbuddy 模式启动（v4.1.8）

预设**本身不足以**让 daily 走 workbuddy：`Invoke-DailyPipeline.ps1` 把
`--provider` 默认成 `replay` 并显式传参，会覆盖预设。所以 `daily_cli` 的
`--provider` **直接接受 `workbuddy`**（别名 `workbuddy_mcp`），与 `market_db`
同一模式；缺 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR` 或目录不存在 → 中文 fail-closed
报错并指向 `stock-platform-workbuddy-bridge`。

| 入口 | 作用 |
|---|---|
| `start-workbuddy.bat` | 双击版：可选位置参数 `symbols` / `datasets` |
| `scripts/ops/Invoke-WorkbuddyBridge.ps1` | 两步编排：先 bridge 刷缓存，再 daily（`--provider workbuddy`） |
| `stock-platform-workbuddy-bridge` | 只刷缓存（可单独用） |

`Invoke-WorkbuddyBridge.ps1` 参数：`-Symbols` / `-SymbolsFile` /
`-FromMarketDb -Top N`（从 `market.db` 取成交额 Top-N）/ `-Datasets` / `-Limit` /
`-Period` / `-Adjust` / `-Asof` / `-AsofQuote` / `-CacheDir` / `-SkipBridge` /
`-SkipDaily` / `-DryRun` / `-Force`。默认缓存目录 `data/workbuddy_cache`（可跨重启留存）。

**注意**：单代码响应无 `code` 列（见 §1.4）。桥此时无歧义（只有 1 个代码），
但**不要**把 2 个以上代码的请求指向无 `code` 列的响应 —— 桥会拒绝归因并告警。

