# 交接：stock-platform v4.3.0 → 下一块砖（让 PnL 闭环每天自然累积）

> 生成：2026-10-12 · 用途：**新对话零上下文接续**，不必回读旧会话
> 仓库：`D:\workspace\stock_trading\stock-platform` · 分支 `main` · tag `v4.3.0`（本次发布 commit）
> 状态：工作树**干净**，远端 `main` == 本地 HEAD，tag 已推

---

## 0. 接手第一件事（照抄执行）

```powershell
cd D:\workspace\stock_trading\stock-platform
.\.venv\Scripts\python.exe -m pytest packages apps -q          # 期望 988 passed / 0 failed
.\scripts\ops\Register-ScheduledTasks.ps1 -Status               # 看两个任务 lastResult 是否 0x0
.\.venv\Scripts\python.exe -m stock_platform_research.performance_cli --settle-daily   # 看收益 + alpha
.\.venv\Scripts\python.exe -m stock_platform_research.daily_digest_cli                 # 看 data/digests/latest.md 绩效台账
```

**环境**：`.venv`（→ miniconda 3.14.6，`--system-site-packages`）。**裸 miniconda python 没有 stock_platform 包**，一切命令必须用 `.venv\Scripts\python.exe`。

---

## 1. 上一里程碑（v4.3.0，已完成并验收）

**主题**：绩效 PnL 闭环 —— `performance` JSONL → 用户可见收益归因。

| 交付 | 说明 |
|---|---|
| **基准 alpha** | `alpha = raw − benchmark`；基准默认 **中证500 `000905`**，env `STOCK_PLATFORM_BENCHMARK_SYMBOL` 覆盖；`raw`/`alpha` 共用**同一** `_holding_window`（entry/exit 日期一致） |
| **alpha 回填** | 已结算但 `alpha=null` 的历史行，下一次带基准结算时补齐（`alphaSettledNewly`） |
| **`build_attribution`** | `winRate`/`avgReturn`/`medianReturn`/`avgAlpha`/`beatBenchmarkRate`/`best`/`worst` + `byRank`/`byScore`（等数量分桶）/`byDate`/`equityCurve`；并入 `performance_summary`（旧键不变） |
| **`DEFAULT_HOLDING="5d"`** | 记账=结算=日报三口径合一（`daily_cli` 不再硬写 `1d`） |
| **日报真数字** | `daily_digest.performance_summary` 增 `returns`（复用 research 单点 口径），「绩效台账」显示胜率/平均收益/跑赢基准率/最好最差 |
| **出口** | CLI `--settle-daily/--benchmark/--no-benchmark`；盘后任务 `-SettleAfter` 带基准；`GET/POST /api/research/performance[/settle]` |

**实测证据**：3 条 pending → `settledNewly=3`（`+0.38%`/`+2.96%`/`-1.76%`）；再结算 `alphaSettledNewly=3`（`+2.41%`/`+4.99%`/`-7.72%`）；`direction_accuracy` 0.667 / `avgReturn` +0.53% / `beatBenchmarkRate` 0.667；日报出现「收益概览（已结算 3 条 / 基准 000905）…」；测试 980→**988**（+8）。

**三个必须知道的事实**

1. **3 条 pending 的根因是"结算从未跑过"**，不是窗口/数据问题 —— 盘后任务注册后**尚未自然运行过一次**。`v4.3.0` 手工结算已证明数据齐备。
2. **基准是代理**：`market.db` **没有**沪深300（`000300`）；完整的指数只有 `000905`（中证500）/`000852`（中证1000）；`000016`（上证50）止于 2026-09-30；`510300.SH`（沪深300ETF）仅 65 行（C2 ETF 退化）。默认取中证500。
3. **换基准不自动重算历史 alpha**：只影响后续结算；要重算须重跑结算（已知边界，写在契约 §7）。

---

## 2. 下一块砖（建议）：让闭环每日自然累积

`v4.3.0` 的验证是**手工结算**。要让"赚不赚钱"成为**持续信号**，需要：

1. **跑通一次真实每日循环**：盘后任务（`-MarketDb -PrevSession -SettleAfter`）在自然时点触发 → 当天 brief 的 TopN 落 pending，且**到期样本自动结算 + 带 alpha**。当前 JSONL 只有 3 条人工样本；需要一个**自然产生**的样本证明端到端无人工介入。
2. **核对 `-PrevSession` 下的持有期语义**：记账 asof = 前一交易日；`5d` 持有期需按**交易日**推进（`_holding_window` 已是交易日口径）。确认盘后任务连续跑几天后 pending 会自然转 settled。
3. **（可选）日报加"最近一次结算"提示**：现在日报只给汇总，不给"今天新结算了哪些票"。

**风险提示**：结算读 engine `market.db`（~3.15 GB，只读）。示例 2026-10-09 → 至今跨了国庆长假，`hold` 按交易日但 `end_buffer_calendar_days=40` 已覆盖。

**其它候选**（路线图末行）：`C3`（重复实现收敛清单）或 `L2`/`L3`（须 `L1` 显式指定 P1/P2 解锁）。

---

## 3. 红线与约束（不变）

- `liveTradingEnabled` **恒为 false**；全部 SIMULATE/paper。ADR `0064`（`L1` 实盘立项）通过前禁止触碰。
- market.db 是**只读**行情真相源（ADR `0058`）；摄取归生产侧 `a-stock-engine`，平台**不代抓不补写**。
- 绩效口径红线（ADR `0033`/`0068`）：**不算夏普/年化；样本 <20 标噪音；`equityCurve` 非可交易组合曲线**。
- 改行为必须同步：CHANGELOG + 契约/ADR + 路线图 + `check_docs.ps1` 注册（若是新文档）。
- 发版流程见 Skill `stock-platform-release`（11 处版本号 + 双绿 + 全量测试 + tag + push + `ls-remote` 复核）。

---

## 4. 相关技能（可直接调用）

| Skill | 用途 |
|---|---|
| `stock-platform-release` | 收口发版：升版本 → 双绿校验 → commit → tag → push |
| `wb-finance-skill` | 金融场景总入口 |
| `westock-data` / `westock-tool` | 行情数据 / 选股（workbuddy 模式的数据源） |

---

## 5. 工程环境坑（沿用，勿重新踩）

| 坑 | 规避 |
|---|---|
| **Bash PATH 损坏** | `dirname`/`head`/`cat`/`grep`/`sed`/`tail` 全 exit 127（**别用管道**）→ 读文件用 Read，或 `python -c` |
| **PowerShell 工具不捕获子进程 stdout** | 写 `$env:TEMP` 或 `[System.IO.File]::WriteAllText` 后再 Read |
| **PowerShell 遇子进程非零退出即中断** | 命令串里 `exit 0`；真实退出码单独落文件 |
| **here-string 传 `python -c` 引号被吃** | 写 `.py` 脚本文件再执行 |
| **`Remove-Item` / `rm` 静默失败** | 用 Python `pathlib.Path.unlink()` |
| **同消息多 Edit 只落部分** | 一次只发一个 Edit，或改用 Python 精确替换 + 断言唯一命中 |
| **测试全绿但 `EXIT 1`** | safe-delete 杀 teardown（摘要行丢失）；判据 = 进度条 100% 且 `--co -q` 收集数 == 通过数 |

---

## 6. 一句话状态

**v4.3.0 已交付并验收**（"赚不赚钱"第一次有确定答案：胜率 / 平均收益 / 跑赢基准率 / 分桶 / 累计曲线，含历史行 alpha 回填）；下一个目标是让这套闭环在**真实每日循环**里无人值守地持续累积结算样本。
