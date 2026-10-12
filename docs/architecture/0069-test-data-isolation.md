# 0069 — 测试数据隔离（测试套件不得写入生产 `data/`）

- **状态**：Accepted
- **日期**：2026-10-12
- **里程碑**：测试数据隔离 + 日报修复（发布 `v4.3.1`）
- **相关**：ADR [`0049`](0049-sqlite-first-persistence.md)（SQLite 优先持久化 / brief 权威存档）·
  ADR [`0057`](0057-hit-tracking.md)（命中追踪三视图）·
  ADR [`0033`](0033-recommend-performance.md) / [`0068`](0068-performance-pnl-closed-loop.md)（绩效口径）·
  ADR [`0058`](0058-market-db-source-of-truth.md)（`market.db` 只读真相源）

---

## 1. 背景：闭环"有了"，日报却是空的

`v4.3.0` 交付绩效 PnL 闭环后，验收"让闭环在真实每日循环里自然累积"时，第一眼看
`data/digests/latest.md` 就发现**用户可见日报是无意义的**：

```
# 每日简报 · 2026-10-12
- 宇宙：3 只（档位 -），截面 0 行，TopN 10
## 当日推荐（0 条）
**截面为空…（replay 样例仅覆盖到 2026-09-02；live 请用最近交易日）**
```

而**同一时刻库里明明有一份真实 brief**：`asof=2026-10-09`、`universeSize=5235`、10 条 picks ——
是当天 08:30 盘前任务（`-MarketDb -PrevSession`）正常产出的。日报却渲染了另一个 `asof`。

## 2. 根因（三条，均可复现）

运行时的三个存储都从 **cwd 相对默认值**解析：

| 存储 | 解析入口 | 默认 |
|---|---|---|
| brief 权威存档 | `persistence.default_db_url()` | `sqlite:///./data/stock_platform.db` |
| 命中追踪 | `hit_tracking` 同名 `ENV_DB_URL` | 同上（**同一文件**） |
| 绩效决策台账 | `performance.default_performance_log_path()` | `./data/recommend_decisions.jsonl` |

### R1 有一个测试直接写生产库

`packages/research/tests/test_daily_pipeline.py::test_daily_cli_settle_after_logs_performance`
驱动**整个 CLI**（`daily_cli.main([...])`），却只钉住了 `STOCK_PLATFORM_PERFORMANCE_LOG`，
**没有钉 `STOCK_PLATFORM_DB_URL`**。CLI 于是走默认路径 + `persist_db=True` →
把 fixture brief（`asof=2026-09-02`、`universeSize=3`）**upsert 进生产存档**，并写入该 pick 的命中行。

**证据**：`daily_briefs` 中 `asof=2026-09-02` 那一行的 `updated_at` **精确等于全量测试运行的墙钟分钟**
（`2026-10-12T08:49:37Z` ↔ 本机 16:49:37），且 DB 文件 mtime 同一秒；仓库内**没有任何 `conftest.py`**
做兜底。用「逐文件跑 pytest + 前后哈希比对」精确指认到该文件（其余 14 个候选文件全部零变化）。

### R2 污染行遮蔽真实 brief —— 这才是日报变空的直接原因

库里被写入的 `asof=2026-10-12` 行（`universeSize=3`、`picks=[]`，来自一次 replay 试探运行）
**日期最新**，于是 `build_digest` 的 `repo.list_recent(limit=1)` 取到的就是它 →
日报「当日推荐（0 条）」。真实 brief（`2026-10-09`）**没有被删**，只是**被遮蔽**。

### R3 命中汇总是独立表，"只清明细"清不干净

`hit_tracking`（按周期明细）与 `hit_summary`（终身上卷，**日报读的是这张**）是**两张表**。
第一次清理只动了明细表 → fixture 代码 `000001` / `600519`（周期 `2026-09-02`）**仍在日报的
「命中追踪」里继续显示**。

## 3. 决策

### 3.1 仓库根 `conftest.py`：会话级数据隔离（守在一次）

- 在 **import 时**（早于任何测试模块体与 `.env` 加载）把
  `STOCK_PLATFORM_DB_URL` / `STOCK_PLATFORM_PERFORMANCE_LOG` 指向会话临时目录；
- `atexit` 还原原始环境；设 `STOCK_PLATFORM_TEST_DATA_DIR` 可保留一份现场；
- 与既有 `dotenv` 的 pytest 守卫同向：**测试永不继承开发者的真实环境**。

### 3.2 驱动 CLI 的测试额外自钉（局部可读）

`test_daily_cli_settle_after_logs_performance` 自己再钉一次 `STOCK_PLATFORM_DB_URL` ——
**凡是驱动 CLI / pipeline / workbench 路由的测试，都必须显式钉住存储位置**，不依赖环境残留。

### 3.3 回归测试

新增断言：会话内解析出的 brief 库与绩效台账路径**不得落在仓库根的 `data/` 下**。
守卫一旦失效（例如有人删掉 `conftest.py`），测试立即变红。

### 3.4 数据清理：独立复核，不信脚本自报

- 清掉 fixture 规模（`universeSize==3`）的 brief 行与它们的命中明细/汇总行，并**先备份**；
- 清空后**另起一条只读连接独立复核**行数（**脚本打印的计数不可信** —— 本次工具把清理脚本
  重跑了一遍，可见输出其实是**第二次**执行的结果，第一次已改完而输出不可见）；
- 断言护栏：只允许 `universeSize==3` 的行被删，防手滑扩大范围。

### 3.5 参数化的存储位置（可选入口）

测试可用 `STOCK_PLATFORM_DB_URL` / `STOCK_PLATFORM_PERFORMANCE_LOG` 指向临时库，
无需 `monkeypatch.chdir`；`default_db_url()` / `default_performance_log_path()`
保持在业务代码里作为**唯一**默认点。

## 4. 后果

### 正面

- **日报恢复真实**：`latest.md` 渲染 `2026-10-09`（5235 只 / 10 picks / 五榜 / 命中追踪 10 只），
  「绩效台账」显示 `累计决策 13 条：待结算 10，已结算 3`；
- **测试不再污染权威存档**：全量 `pytest packages apps` 前后，`daily_briefs` / `hit_tracking` /
  `hit_summary` / `recommend_decisions.jsonl` **行级逐位不变**；
- **清理有据可查**：删了什么、依据什么判据、如何独立复核，全部留痕。

### 负面 / 边界

- 需要真实生产库的测试必须**显式 opt-in**（钉住真实路径），不能再靠"默认值恰好是真库"；
- `conftest.py` 只覆盖**被环境变量参数化的**存储。新增任何 cwd 相对存储时，
  **必须同时加进 `GUARDED_ENV`**，否则守卫有盲区；
- 本次未改动任何业务路径，`liveTradingEnabled` 恒 `false`，`market.db` 仍只读。

## 5. 实测证据（2026-10-12，本机）

| 项 | 结果 |
|---|---|
| 逐文件二分（修复前） | 15 个候选文件中**恰好 1 个**改生产库：`test_daily_pipeline.py` |
| 修复后（该文件） | 32 passed，`stock_platform.db` + `recommend_decisions.jsonl` 哈希**逐位不变** |
| 全量测试（行级指纹） | **988 passed**，四类存储（briefs / 命中明细 / 命中汇总 / 绩效台账）**逐位不变** |
| 污染清理 | brief 行 −2（`2026-09-02` / `2026-10-12`）、命中明细 −2、命中汇总 −2；独立复核通过 |
| 日报修复 | `latest.md`：`2026-10-09` 真实 brief，「命中追踪」10 只（`2026-09-02` 残留 = `False`） |

## 6. 顺带确认的两条事实（免下次重新踩）

1. **`_ensure_schema()` 与只读操作不改文件**（实测：构造 repo + 多次读取后哈希三次不变）——
   所以"刷新 `data/stock_platform.db` 的哈希"是**真实逻辑写入**的可靠信号，不是噪音。
2. **仓库内不存在任何行删除路径**（全仓 `DELETE FROM` / `DROP TABLE` / `unlink` / `rmtree` 扫描 =
   零命中）。归档**只增不删**；若观测到行消失，先查**外部/人工操作**，不要怀疑业务代码。
