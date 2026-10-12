# 交接：stock-platform v4.3.1 → 下一块砖（闭环已证明可靠，让它自然累积）

> 生成：2026-10-12 · 用途：**新对话零上下文接续**，不必回读旧会话
> 仓库：`D:\workspace\stock_trading\stock-platform` · 分支 `main` · tag `v4.3.1`
> 上一条交接：`docs/plans/handoff-v4.3.0.md`（绩效 PnL 闭环）

---

## 0. 接手第一件事（照抄执行）

```powershell
cd D:\workspace\stock_trading\stock-platform
.\.venv\Scripts\python.exe -m pytest packages apps -q          # 期望 989 passed / 0 failed
.\scripts\ops\Register-ScheduledTasks.ps1 -Status               # 两个任务 lastResult 是否 0x0
.\.venv\Scripts\python.exe -m stock_platform_research.performance_cli --settle-daily   # 看收益 + alpha
.\.venv\Scripts\python.exe -m stock_platform_research.daily_digest_cli                 # 看 data/digests/latest.md
```

**环境**：`.venv`（→ miniconda 3.14.6，`--system-site-packages`）。**裸 miniconda python 没有
`stock_platform` 包**，一切命令必须用 `.venv\Scripts\python.exe`。

---

## 1. 上一里程碑（v4.3.1，已完成并验收）

**主题**：测试数据隔离 + 日报修复 —— 让闭环的**输出**可信。

| 交付 | 说明 |
|---|---|
| **仓库根 `conftest.py`** | 会话 import 时把 `STOCK_PLATFORM_DB_URL` / `STOCK_PLATFORM_PERFORMANCE_LOG` 重定向到临时目录，`atexit` 还原；`STOCK_PLATFORM_TEST_DATA_DIR` 可留现场 |
| **驱动 CLI 的测试自钉** | `test_daily_cli_settle_after_logs_performance` 不再依赖环境残留 |
| **回归测试** | `test_persistence.py::test_session_never_resolves_the_repo_data_dir` —— 守卫被删即变红 |
| **数据清理** | 清掉 fixture 规模的 brief 行（−2）与命中明细/汇总行（各 −2），先备份、后独立复核 |
| **日报恢复** | `latest.md` 恢复渲染真实 brief（`2026-10-09`，5235 只 / 10 picks） |

**实测证据**：全量 988 → **989 passed**（+1 回归测试）；四类存储（`daily_briefs` / `hit_tracking` /
`hit_summary` / `recommend_decisions.jsonl`）在整轮全量测试前后**行级逐位不变**。

**四条必须知道的事实**

1. **测试曾经在写生产库**：`test_daily_pipeline.py` 那一个测试驱动整个 CLI，却没钉
   `STOCK_PLATFORM_DB_URL` → 把 fixture brief（`asof=2026-09-02`）upsert 进
   `./data/stock_platform.db`。**日报之所以空白，正是被污染行遮蔽**，不是数据缺失。
2. **`hit_summary` 与 `hit_tracking` 是两张表**：**日报的「命中追踪」读 `hit_summary`**。
   只清明细表会留下"幽灵代码"。
3. **仓库内没有任何行删除路径**（`DELETE FROM` / `DROP TABLE` / `unlink` / `rmtree` 全仓扫描 = 0）。
   归档**只增不删**；观测到行消失，先查外部/人工操作。
4. **`_ensure_schema()` 与只读不改文件**（实测哈希三次不变）→ 文件哈希变化 = **真实写入**的可信信号。

---

## 2. 下一块砖（建议）：让闭环自然累积并验收首个"无人值守结算"

`v4.3.0` 证明闭环**能**算，`v4.3.1` 证明它的**输出不被污染**。剩下的问题是**时间**：

1. **等第一个自然结算样本**：`2026-10-09` 那批 10 条 picks 已自然落 pending（`holding=5d`，
   入场 = `2026-10-09` 的 bar，出场 = 其后 **5 个交易日**）。`market.db` 止于 `2026-10-09`，
   所以**现在必然 pending** —— 等生产侧（`a-stock-engine`）回补到 `≥ 2026-10-16` 的 bar，
   盘后任务下一次跑就该把它们**自动结算 + 带 alpha**。此时看 `settledNewly > 0`。
2. **核对盘后任务真的会自然触发**：`stock-platform-postmarket` 当前
   `lastResult=0x41303`（`SCHED_S_TASK_HAS_NOT_RUN`）、`StartBoundary=2026-10-13T15:30` —— 它
   **尚未自然运行过一次**。2026-10-13 15:30 之后用 `-Status` 看 `lastResult=0x0` 与
   `lastRun`，并用 `data/digests/latest.md` 的 asof 交叉验证。
3. **（可选）日报加"最近一次结算"提示**：现在「绩效台账」只给汇总，不给"今天新结算了哪些票"。
4. **（可选）清理 `hit_summary` 的历史周期**：`active_cycle_end` 已过期的代码仍留在"累计命中"里
   （`snapshot` 已有 `excludes closed cycles` 的语义，日报口径可对齐）。

**风险提示**：结算读 engine `market.db`（~3.15 GB，只读）；`end_buffer_calendar_days=40` 覆盖长假。

---

## 3. 红线与约束（不变）

- `liveTradingEnabled` **恒为 false**；全部 SIMULATE/paper。ADR `0064` 之前禁止触碰。
- `market.db` 是**只读**行情真相源（ADR `0058`）；摄取归生产侧，平台**不代抓不补写**。
- 绩效口径红线（ADR `0033`/`0068`）：**不算夏普/年化；样本 <20 标噪音；`equityCurve` 非可交易组合曲线**。
- **`data/` 下的三个存储是生产数据**：测试一律不得写入（ADR `0069`）。新增任何 cwd 相对存储时，
  **必须同步加进 `conftest.py` 的 `GUARDED_ENV`**。
- 改行为必须同步：CHANGELOG + 契约/ADR + 路线图 + `check_docs.ps1` 注册（若是新文档）。
- 发版流程见 Skill `stock-platform-release`（11 处版本号 + 双绿 + 全量测试 + tag + push + `ls-remote` 复核）。

---

## 4. 相关技能（可直接调用）

| Skill | 用途 |
|---|---|
| `stock-platform-release` | 收口发版：升版本 → 双绿校验 → commit → tag → push |
| `wb-finance-skill` | 金融场景总入口 |
| `westock-data` / `westock-screener` | 行情数据 / 选股（workbuddy 模式的数据源） |

---

## 5. 工程环境坑（沿用，勿重新踩）

| 坑 | 规避 |
|---|---|
| **Bash 里内联 `python -c "…"` 会吞反引号** | 写 `.py` 脚本文件再执行 |
| **同一命令可能被工具重跑** | 脚本必须**幂等**；**不要相信脚本打印的计数**，改完用**独立命令**复核终态 |
| **Bash 禁止调用 PowerShell**（安全策略） | 用 PowerShell 工具（`-File` + `[System.IO.File]::WriteAllText` 后 Read） |
| **PowerShell 工具不捕获子进程 stdout** | 落文件再 Read |
| **PowerShell 遇子进程非零退出即中断** | 命令串尾 `exit 0`；真实退出码单独落文件 |
| **`Remove-Item` / `rm` 静默失败** | 用 Python `pathlib.Path.unlink()` |
| **同消息多 Edit 只落部分** | 一次只发一个 Edit，或改用 Python 精确替换 + 断言唯一命中 |
| **测试全绿但 `EXIT 1`** | safe-delete 杀 teardown；判据 = 进度条 100% 且收集数 == 通过数 |
| **后台命令与手工命令并发会互相干扰** | 做"文件/数据是否被改"的实验时，**串行**执行，别并发 |

---

## 6. 一句话状态

**`v4.3.0` 让闭环"能算"，`v4.3.1` 让它的输出"可信"**：真实 brief 恢复渲染（`2026-10-09` /
5235 只 / 10 picks），10 条 picks 已由**自动化路径**（盘后 `-SettleAfter`，非手工）自然落 pending
且归因基准齐备；下一个目标是在生产侧回补 `≥ 2026-10-16` 的 bar 之后，看到**第一个无人值守的
`settledNewly > 0`**。
