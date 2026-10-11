# 取数吞吐契约（离线批量 provider / 并发 / 持久化）

> 状态：Accepted｜目标 tag：`v4.1.6`（2026-10-10）
> 关联：`docs/architecture/0066-refresh-throughput-and-env-loading.md` · ADR `0058`（数据真相源）· ADR `0054`（适配层）

本契约锁定 `run_refresh` 的**吞吐行为**：批量取数入口、并发与节流、持久化开关。目的是让「08:30 盘前跑完全市场」成为**可复现的契约**，而不是依赖调参。

---

## 1. 三种取数路径与优先级

`run_refresh(provider, symbols, datasets, *, workers=None, min_interval=None, bulk=None, persist=True)`：

| 路径 | 触发条件 | 调用形态 | 适用 |
|---|---|---|---|
| **批量（bulk）** | `bulk is not False` **且** provider 有 `bulk_daily` **且** 请求数据集 ⊆ `provider.capabilities` | 一次 `bulk_daily(...)` | `market_db`（本机真相源） |
| **并发（pool）** | 不满足 bulk，且 `workers > 1` | `ThreadPoolExecutor(max_workers=workers)` + 共享限速闸门 | HTTP provider |
| **串行** | 不满足 bulk，且 `workers == 1`（**默认**） | 逐只逐集合同步调用 | HTTP provider（历史行为） |

**优先级判定单点**：`_bulk_daily_allowed(provider, datasets, bulk)`。

- `bulk=False` **强制**关闭批量（即使 provider 支持）。
- 只要**任一**请求数据集不在 `capabilities` 内 → 不走批量（**fail-closed，不静默丢数据集**）。
- provider 无 `bulk_daily` 属性 → 不走批量。

**结果顺序不变式**：无论走哪条路径，返回值恒按 `(symbol, dataset)` 的**输入顺序**排列（批量路径缺失的 symbol → `[]`）。

---

## 2. 批量 provider：`MarketDbBulkProvider`

- `PROVIDER_NAME = "market_db_bulk"`
- `capabilities = frozenset({"daily"})` —— **只声明真正能批量供给的数据集**
- `MARKET_DB_BULK_UNSUPPORTED = ("adj_factor", "fund_flow", "full_minute")` —— 显式声明不支持项
- 唯一入口：`bulk_daily(symbols, *, start=None, end=None, asset_type="stock") -> dict[str, list[dict]]`

实现约束：

1. **一趟 SQL**：`SELECT code, date, close, pct_chg, vol, amount FROM daily_price WHERE code IN (...) AND date >= ? AND date <= ? ORDER BY code, date`，以 `_CHUNK = 900` 分块（避开 SQLite 变量上限）。
2. **代码归一（复用，不重写）**：`_bare_codes` 去重保序走 `normalize_symbol(raw, market="CN")`；`_engine_code_map` 把 `600519.SH` / `sh600519` / `600519` 折叠到同一 6 位裸码键 —— 与 ADR 0055/X1 的归一规则**同源**。
3. **缺失即空**：请求了但库里没有的 symbol → `[]`（**不报错**；覆盖问题由 `coverage_snapshot` 暴露）。
4. **归一**：每行经 `normalize_daily_row(...)`，输出与其它 provider 同构。
5. **零网络**：读本机 SQLite。**不得**直连 Markdown / 自然语言源（延续 ADR 0054）。

---

## 3. 并发与节流

### 3.1 默认值

| 参数 | 默认 | 来源 |
|---|---|---|
| `workers` | `1` | `default_workers()` ← `STOCK_PLATFORM_REFRESH_WORKERS` |
| `min_interval` | 见下 | `default_min_interval()` ← `STOCK_PLATFORM_REFRESH_MIN_INTERVAL`，**回落 `EM_MIN_INTERVAL`** |

**默认串行是契约**：不改变既有基线；并发是显式选项。

### 3.2 限速闸门

```python
class RateLimiter(min_interval, *, sleeper=time.sleep, clock=time.monotonic)
```

- `min_interval <= 0` → `acquire()` **立即返回**（noop，不 sleep）。
- 否则 `acquire()` 在**跨所有 worker 的共享锁**下计算等待：保证任意两次上游调用间隔 ≥ `min_interval`。
- **硬约束**：提高 `workers` **不能**越过上游节流 —— 并发只提升吞吐，不放宽限速。

---

## 4. 持久化开关（`persist`）

- `run_refresh(..., persist=True)` 为**默认**（历史行为不变）。
- `persist=False`：跳过逐只 JSON 落盘（仅服务于 replay）。**热路径必须用 `False`** —— `daily_pipeline` 是通过 provider 回读 bar 的，从不回放 refresh 目录。
- `daily_cli._resolve_persist(args)` 的解析规则：
  1. 显式 `--refresh-persist` / `--no-refresh-persist` **优先**；
  2. 否则 `True`，**除非** provider ∈ `{"market_db", "market_db_bulk", "engine_sqlite"}`（`_MARKET_DB_ALIASES`）→ `False`。

---

## 5. 流水线侧裁剪：`_effective_datasets`

`daily_pipeline._effective_datasets(provider, datasets)`：

- provider **未声明** `capabilities` → 返回 `None`（**行为不变**，沿用历史数据集）。
- 声明了 → 返回 `请求数据集 ∩ capabilities`；交集为空 → `None`（视为"无能力信息"，不 fail）。

目的：让只有 `daily` 的批量 provider 不会因缺 `adj_factor` 而让整条流水线 fail-close。被裁掉的数据集是**显式裁剪**，不是静默丢数据。

---

## 6. 验收基线（真机实测）

| 场景 | 数字 |
|---|---|
| 全市场 5213 只 refresh（带 JSON） | **115 s** |
| 全市场 refresh（`persist=False`） | ≈ 5 s 级 |
| `daily_cli` 端到端（快路径） | **12.78 s** |
| `daily_cli` 端到端（带持久化） | 129.94 s |
| ops 脚本 `Invoke-DailyPipeline.ps1 -MarketDb` | **14.78 s** |
| 修复前外推（HTTP 串行全市场） | ~3 h |
