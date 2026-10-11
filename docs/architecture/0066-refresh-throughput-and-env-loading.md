# 0066 — 取数吞吐重构（离线批量 provider）与环境自动加载

- **状态**：Accepted
- **日期**：2026-10-10
- **里程碑**：`P0-1` / `P0-2`（目标 tag `v4.1.6`，生产可用前置修复）
- **相关**：ADR [`0050`](0050-engine-pit-fundamentals-readonly.md)（引擎 PIT 基本面 / 行情只读暴露）·
  ADR [`0054`](0054-data-source-adapters.md)（数据源适配层）·
  ADR [`0055`](0055-market-universe.md)（全市场宇宙）·
  ADR [`0058`](0058-market-db-source-of-truth.md)（数据真相源 + 覆盖守卫）·
  契约 [`docs/contracts/refresh-throughput.md`](../contracts/refresh-throughput.md) ·
  [`docs/contracts/dotenv-loading.md`](../contracts/dotenv-loading.md)

---

## 1. 背景：真机测试暴露的两个 P0 阻塞

用户目标明确：**系统要做到生产可用、真实可用 —— 完成每日选股、盘前盘后信息收集，最终目标是盈利**。

在这个目标下，对真机（真实 `.env`、真实 `market.db`、真实 provider）做了端到端跑测，暴露出两个 P0 级阻塞，导致 08:30 盘前任务在真机上根本跑不完：

### P0-1：`run_refresh` 是全市场取数瓶颈

`run_refresh` 的实现是**双层串行同步 HTTP**：

```python
for symbol in symbols:          # 5213 只
    for dataset in datasets:    # 4 类数据集
        resp = provider.get_daily(symbol, ...)   # 一次阻塞 HTTP
        json.dump(resp, f"{cache}/{dataset}_{symbol}.json")
```

真机实测（307 只样例）：**11 分 48 秒 / 614 个文件**；其中 CPU 时间仅 **9.7 秒** → 进程 **100% 卡在网络 I/O**。按此线性外推，全市场 5213 只约需 **3 小时**，且每日重复拉取同一批数据。08:30 盘前窗口完全不可能容纳。

**根因不是"并发不够"，而是取数路径选错了。** 本机 `a-stock-engine/data_cache/market.db` 已经是**全市场行情真相源**（ADR 0058），一次 120 天全市场 SQL 读只需 **3.2 秒 / 422k 行**。而 `run_refresh` 却在用 HTTP 重新拉取**已经躺在磁盘上**的数据。

### P0-2：CLI 不自动加载 `.env`

`daily_cli._build_provider` 直接读 `os.environ["STOCK_PLATFORM_TUSHARE_TOKEN"]`，而全仓只有 `start-workbench.bat` 会注入 `.env`。真机复现：

```
$ python -m stock_platform_research.daily_cli --provider cn_tushare_http --live
live provider='cn_tushare_http' requires STOCK_PLATFORM_TUSHARE_TOKEN
(exit 1)
```

调度器（`schtasks`）不会替你 export 环境变量，所以每日自动化在真机上**必然失败**。

---

## 2. 决策

### 决策 A：新增离线批量 provider，把"逐只 HTTP"降级为"一次 SQL"

新增 `MarketDbBulkProvider`（`packages/providers/.../market_db_bulk.py`），包装现有 `EngineSqliteProvider`：

- 能力声明 `capabilities = frozenset({"daily"})` —— 只声明它**真正能批量供给**的数据集；
- 唯一的批量入口 `bulk_daily(symbols, *, start, end, asset_type) -> dict[str, list[dict]]`：以 `_CHUNK = 900` 分块，对 `daily_price` 表做**一趟 SQL**，`WHERE code IN (...) AND date BETWEEN ? AND ?`，再按 `normalize_daily_row` 归一；
- 代码归一：`_bare_codes` 去重保序，`_engine_code_map` 把 `600519.SH` / `sh600519` / `600519` 折叠到 6 位裸码同一键（与 ADR 0055/X1 的归一规则一致，不写第二套）；
- `unsupported` 数据集（`adj_factor` / `fund_flow` / `full_minute`）**显式声明**，便于上层 fail-closed 而不是静默丢数据。

`run_refresh` 增加 `bulk` 开关：当 provider 同时满足 `hasattr(provider, "bulk_daily")` 且**请求的数据集全部在 `capabilities` 内**时，走批量路径（一次调用），否则回落到线程池路径。`bulk=False` 可强制关闭。

**不做"直连 Markdown / 自然语言"的取数**（延续 ADR 0054 的 workbuddy 适配器决策）：批量路径读的是本机 SQLite，**零网络、可单测**。

### 决策 B：并发 + 全局限速，但并发不是主修复

对 HTTP 路径保留多线程（`ThreadPoolExecutor`），但并发**必须**受一个跨所有 worker 的共享限速闸门约束：

```python
class RateLimiter:                      # 线程安全
    def acquire(self):
        with self._lock:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0: self._sleeper(wait)
            self._last = self._clock()
```

- 默认 `workers=1`（**保持历史串行行为**，不改变既有基线）；
- 默认最小间隔取 `STOCK_PLATFORM_REFRESH_MIN_INTERVAL`，回落到 `EM_MIN_INTERVAL`（东财节流单点定义）；
- 提高并发**不能**越过上游节流 —— 这是设计上的硬约束，不是调参建议。

### 决策 C：热路径不落 JSON

`market.db` 是全市场真相源，`run_refresh` 落盘的逐只 JSON **只服务于 replay**；而 `daily_pipeline` 是通过 provider 读 bar 的，**从不回放 refresh 目录**。因此：

- `run_refresh(..., persist=True)`：保持历史行为（兼容既有调用方与测试）；
- `daily_cli` 用 `_resolve_persist(args)`：显式 `--refresh-persist/--no-refresh-persist` 优先，否则**当 provider 属于 `{"market_db","market_db_bulk","engine_sqlite"}` 时默认 `False`**；
- 实测差异：全市场 refresh 带 JSON **115s** vs 不带 **≈ 5s 级**；CLI 端到端 12.78s（快路径）vs 129.94s（带持久化）。

### 决策 D：`.env` 自动加载收敛为单点实现

新增 `packages/research/.../dotenv.py`，作为**全仓唯一**的 `.env` 读取器：

- 路径优先级：显式参数 > `STOCK_PLATFORM_DOTENV` > 从 `__file__` 向上走找仓库根 > cwd；
- **默认不覆盖**已存在的进程环境变量（`override=False`）—— 调度器/CI 显式注入的变量优先；
- 文件缺失**不报错**（返回空映射）；仅当调用方声明 `required=[...]` 且缺失时抛 `DotenvMissingError`；
- **pytest 守卫**：当 `PYTEST_CURRENT_TEST` / `PYTEST_VERSION` 存在，或 `STOCK_PLATFORM_DOTENV_DISABLE` 为真时，**跳过隐式加载** —— 防止开发者本机真实 `.env` 泄漏进测试；`force=True` 供加载器自身测试使用。

在 **14 个 CLI** 的 `main()` 首行接入 `load_dotenv()`（`daily_cli`、`refresh_cli` 及另外 12 个）。

### 决策 E：流水线按 provider 能力裁剪数据集

`daily_pipeline` 增加 `_effective_datasets(provider, datasets)`：把请求的数据集与 provider `capabilities` **取交集**。这样"只有 `daily`"的批量 provider 不会让整个流水线因缺少 `adj_factor` 而 fail-close；provider 未声明 capabilities 时**行为不变**（返回 `None`）。

---

## 3. 后果

### 正向

- **全市场取数从 ~3 小时降到分钟级**：真机实测全市场 5213 只 refresh = **115s**（带 JSON）/ CLI 端到端 **12.78s**（快路径） / ops 脚本 **14.78s** —— 相较外推的 ~3 小时约 **94×–700×**。08:30 盘前窗口变得可行。
- **每日自动化在真机可跑**：`.env` 自动加载消除了 `schtasks` 环境下 "requires STOCK_PLATFORM_TUSHARE_TOKEN" 的必然失败。
- **不改变既有基线**：`workers` 默认 1、`persist` 默认 True（`run_refresh` 层），并发与快路径都是**显式选项**，历史调用方行为逐位不变。
- **单一实现**：`.env` 解析、代码归一、节流单点各有唯一定义，无重复实现。
- **测试 +40**：全量 **927 passed / 0 failed**。

### 负向 / 代价

- **批量 provider 的覆盖受 `market.db` 新鲜度约束**：若上游摄取中断（C2 场景），批量取数会照单全收陈旧数据 —— 由既有的 `coverage_snapshot` 覆盖守卫（ADR 0058）在出口暴露 `stale`/`thin`，不新增机制。
- **`daily` 之外的批量供给尚未实现**：`adj_factor` / `fund_flow` / `full_minute` 仍走 HTTP 路径；在 `market_db` provider 下这些数据集会被 `_effective_datasets` 裁掉（**显式裁剪，不是静默丢**）。
- **`.env` 自动加载是隐式行为**：靠 pytest 守卫防泄漏；若未来新增非 pytest 的测试框架，需同步扩展 `_TEST_MARKERS`。

### 不做

- 不把 `.env` 加载下沉到 `providers` 包（保持 providers 只做 I/O、不碰开发环境约定）。
- 不用"更多并发"替代批量 SQL（并发受上游节流硬约束，且解决的是错误的瓶颈）。
- 不新增手动 UI 面板（本项是主链自动化特性）。

