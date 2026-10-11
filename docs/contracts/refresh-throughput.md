# 取数吞吐契约（离线批量 provider / 并发 / 持久化 / 缺口容忍）

> 状态：Accepted｜目标 tag：`v4.1.7`（2026-10-10）
> 关联：`docs/architecture/0066-refresh-throughput-and-env-loading.md` · ADR `0058`（数据真相源）· ADR `0054`（适配层）
> `v4.1.6` 建立前三节（吞吐）；`v4.1.7` 增加第 5 节（缺口容忍）与第 6 节（能力解析）。

本契约锁定 `run_refresh` 的**吞吐行为**与**失败判定**：批量取数入口、并发与节流、持久化开关、数据集裁剪、**缺口 vs 真失败**。目的是让「08:30 盘前跑完全市场」成为**可复现的契约**，而不是依赖调参，且单只票的薄数据不拖垮整轮。

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

`daily_pipeline._effective_datasets(provider, datasets)` 的解析顺序（`_declared_capabilities`，**首次命中即胜出**）：

| 优先级 | 来源 | 结果 | 例子 |
|---|---|---|---|
| ① | provider 有显式 `capabilities` 属性 | 直接用该集合 | `MarketDbBulkProvider` → `{"daily"}` |
| ② | provider 有 `supports(dataset)` 可调用 | 逐数据集试算 | 适配层 provider |
| ③ | provider 有 `name`，且该名在**能力注册表**中 | 注册表声明的集合 | `tushare_http` → `{"daily"}`；`replay` → 13 项 |
| ④ | 以上皆无 | `None` ＝「无能力信息」 | 匿名测试替身 |

**关键不变量**：

- 解析出的集合为**空** → 一律当作 `None`（**永不静默收窄到零数据集**）。
- ③ 依赖 `stock_platform_providers.build_capability_matrix()`（**唯一真源**，见第 6 节）。**禁止**在 `daily_pipeline` 里再抄一份 provider→datasets 表。
- 解析结果为 `None` → 沿用调用方请求的数据集（历史行为不变）。

**为什么需要 ③**：线上 HTTP provider（`tushare_http` / `cn_tushare_http`）只实现 `get_daily`，**既不声明 `capabilities` 也没有 `supports`**。缺 ③ 时流水线会请求全部 4 个数据集，每只票失败 3 个，整轮在 `stage="refresh"` 失败 —— 而这正是本机生产路径。此前真机验证只覆盖 `market_db`，故该回归一度静默上线。

---

## 6. 缺口 vs 真失败（`tolerate_gaps`）

### 6.1 判定单点

`RefreshItemResult.is_gap` 为真 **当且仅当**：

```python
not ok  and  error 含 EMPTY_BARS_MARKER  and  dataset in TOLERABLE_GAP_DATASETS
```

- `EMPTY_BARS_MARKER = "empty daily bars"` —— 该串**仅对 `dataset == "daily"`** 抛出（`refresh.py`），故非日线数据集天然不会被判为缺口。
- `TOLERABLE_GAP_DATASETS = frozenset({"daily"})` —— 未来要放行别的数据集，**只改这一个常量**。

语义：provider **应答了**，只是没有数据（薄票/停牌/ETF 窗口过期）；区别于传输或 schema 错误。

### 6.2 报告与门禁

`RefreshReport(tolerate_gaps=True)` 下：

| 概念 | 定义 | 影响 `ok` |
|---|---|---|
| `gaps` | `is_gap` 为真的项 | **否**（默认） |
| `hard_failures` | `not ok and not (tolerate_gaps and is_gap)` | **是** |
| `ok` | `bool(items) and not hard_failures` | — |

`to_dict()` 新增字段：`tolerateGaps` / `gapCount` / `gaps[]`（`symbol,dataset,error`）；`failures[]` **只列 `hard_failures`**（不再被缺口污染）。

**硬约束：缺口永不遮蔽真失败**。`test_tolerated_gap_does_not_hide_other_failures` 锁定：同轮内一个真错误 + 一个缺口 → `ok=False`、`failCount=1`、`gapCount=1`。

### 6.3 开关（默认开，可显式关）

| 入口 | 打开（默认） | 关闭（严格） | 环境变量 |
|---|---|---|---|
| `run_refresh` | `tolerate_gaps=True` | `tolerate_gaps=False` | — |
| `daily_pipeline` | `refresh_tolerate_gaps=True` | `refresh_tolerate_gaps=False` | — |
| `daily_cli` | 缺省 | `--no-refresh-tolerate-gaps` | `STOCK_PLATFORM_REFRESH_TOLERATE_GAPS=0/false/no/off` |
| `refresh_cli` | 缺省 | `--no-tolerate-gaps` | 同上 |

解析规则：**显式 flag ＞ 环境变量 ＞ 默认 `True`**。

**为什么默认开**：下游 `panel.py` 本就容忍空数据（空 frame → 跳过；严格 PIT 只要求 `asof` 当日有 bar）。整轮 fail-close 会让一个薄票否决全市场选股 —— 与「生产可用」目标相悖。**严格模式保留**给验收/取证（断言完整性时用）。

**可观测性**：CLI 逐条以 `GAP <symbol> <dataset>: <error>` 写 stderr（区别于 `FAIL ...`），退出码仍为 0；`daily_cli` 的 JSON 摘要回带完整 `refresh` 块。

---

## 7. 验收基线（真机实测）

| 场景 | 数字 |
|---|---|
| 全市场 5213 只 refresh（带 JSON） | **115 s** |
| 全市场 refresh（`persist=False`） | ≈ 5 s 级 |
| `daily_cli` 端到端（快路径） | **12.78 s** |
| `daily_cli` 端到端（带持久化） | 129.94 s |
| ops 脚本 `Invoke-DailyPipeline.ps1 -MarketDb` | **14.78 s** |
| 修复前外推（HTTP 串行全市场） | ~3 h |
| `market_db` 有界跑（含 1 只薄票） | `ok=True stage=brief gapCount=1 failCount=0` |
