# 交接：stock-platform v4.4.0 → 下一块砖（循环已自足，等第一个无人值守结算）

> 生成：2026-10-12 · 用途：**新对话零上下文接续**，不必回读旧会话
> 仓库：`D:\workspace\stock_trading\stock-platform` · 分支 `main` · tag `v4.4.0`
> 上一条交接：`docs/plans/handoff-v4.3.1.md`（测试数据隔离 + 日报修复）

---

## 0. 接手第一件事（照抄执行）

```powershell
cd D:\workspace\stock_trading\stock-platform
.\.venv\Scripts\python.exe -m pytest packages apps -q          # 期望 995 passed / 0 failed
.\scripts\ops\Register-ScheduledTasks.ps1 -Status               # 三个任务（daily/postmarket/backfill）lastResult
.\.venv\Scripts\python.exe -m stock_platform_research.performance_cli --settle-daily   # 看收益 + alpha
.\.venv\Scripts\python.exe -m stock_platform_research.daily_digest_cli                 # 看 data/digests/latest.md
```

**环境**：`.venv`（→ miniconda 3.14.6，`--system-site-packages`）。**裸 miniconda python 没有
`stock_platform` 包**，一切命令必须用 `.venv\Scripts\python.exe`。

---

## 1. 上一里程碑（v4.4.0，已完成并验收）

**主题**：日常循环自足 —— 把「无人值守」真正焊死（供数守卫 + 中文名 + 持仓接线）。

| 交付 | 说明 |
|---|---|
| **供数覆盖率守卫** | `Invoke-DailyPipeline.ps1` 跑流水线**前**复用 `coverage_snapshot()` 校验 asof：可用→照常 / 不可用→**回落 `latestTradeDate` + WARN** / 回落目标也不可用→**退出 1 拒绝写 brief**；`-StrictCoverage` 不回退直接失败。守卫放 **ops 层**（CLI 还要服务 replay/fixtures/测试） |
| **回补计划任务** | `Invoke-MarketDbBackfill.ps1`（包引擎自己的 `empirical/backfill_market_daily.py`，幂等 + CPU-safe）+ `stock-platform-marketdb-backfill.xml`（每日 **18:30**）+ `Register-ScheduledTasks.ps1 -Backfill` |
| **中文名直出** | `load_engine_names`（读 `fundamentals.name`，**fail-open**）→ `_build_name_map`（key 归一到 6 位核）→ `build_premarket_brief` / `build_rankings`；**取不到名就不写 `name` 键** ⇒ 无 map / 未命中两条路径下产物**逐字节不变** |
| **持仓自动探测** | `-Holdings` / `-NoHoldings`，默认探测 `data\holdings.json`；不存在则不传（③A/③B 空，fail-closed 不猜）；`data/` 已 gitignore ⇒ XML 零改动 |
| **守卫自愈** | 会话级测试隔离守卫从「import 时设一次」升级为 **autouse 函数级 fixture 每测试前重新断言**（ADR 0069 修订） |

**实测证据**：全量 989 → **995 passed**（+6，新 `test_display_names.py`）；四类存储整轮全量测试前后
**行级逐位不变**；守卫 `asof=2026-10-12`（5224 行）→ `ok`；`asof=2026-10-13`（超库尾）→ 回落
`2026-10-12` 且 `EXIT=0`；同输入 `-StrictCoverage` → `EXIT=1`。

**四条必须知道的事实**

1. **空 brief 比失败更毒**：供数滞后时面板为空，但流水线仍会写出一份 `picks=[]` 的 brief，其 asof
   **最新** → 日报 `list_recent(limit=1)` 取到它 → 「当日无推荐」。守卫的唯一职责就是**在写盘前拦下**
   （宁可给旧截面 + WARN，也绝不写空）。
2. **中文名是装饰性契约**：名称**不承载语义**。取到才写 `item["name"]`，取不到不写键 —— 于是
   `brief.json` / `picks_ledger.jsonl` / 命中周期 / 绩效 JSONL 在「无名称」路径下**逐字节不变**。
   新增任何「显示字段」都照此办理。
3. **`fundamentals.name` 是唯一名称来源**；`daily_price.code` **带交易所后缀**（`000001.SZ`）而
   `fundamentals.code` 是**裸 6 位**，join 前**必须**过 `rankings.code_key` / `portfolio.norm_code`。
4. **持仓只靠一个文件启用**：放 `data\holdings.json`（gitignore）即可，计划任务 XML **不用改**。
   用户 2026-10-12 明确「持仓先不管」→ 该文件**当前不存在**，③A/③B 因此为空，属预期。

---

## 2. 下一块砖（建议）

`v4.3.0` 证明闭环**能算**，`v4.3.1` 让输出**可信**，`v4.4.0` 让循环**自足**。剩下的仍是**时间**：

1. **等第一个自然结算样本**（最优先）：`2026-10-09` 那批 10 条 picks 已自然落 pending（`holding=5d`，
   入场 = `2026-10-09` bar，出场 = 其后 **5 个交易日**）。`market.db` 现止于 `2026-10-12`，
   **现在必然 pending** —— 等生产侧（`a-stock-engine`）回补到 `≥ 2026-10-16` 的 bar，盘后任务下一次
   跑就该**自动结算 + 带 alpha**。此时看 `settledNewly > 0`。
2. **核对三个计划任务真的自然触发**：`stock-platform-postmarket`（15:30）与
   `stock-platform-marketdb-backfill`（18:30）**均尚未自然运行过一次**。用 `-Status` 看 `lastResult=0x0`
   与 `lastRun`，并用 `data/digests/latest.md` 的 asof 交叉验证。
3. **（可选）命中追踪历史行名称回填**：`hit_tracking` / `hit_summary` 里**在名称功能之前**记录的行程
   `name=null`，日报「命中追踪」的「名称」列对它们仍回落成代码。可在渲染时按 code 现查「名称」补上，
   或一次性回填历史行（注意：属写库，须先备份 + 断言范围 + 独立复核）。
4. **（可选）ETF 进 ③A 的既有限制**：brief 宇宙是 `asset_type=stock`，ETF 不在截面；且 `market.db`
   的 ETF 日线只到 `2026-09-08`（65 行）。持仓含 ETF 时只能靠 `review_positions` 全 book 复核（无现价 → `pending`）。

**风险提示**：守卫会让盘前 asof **不再是严格 T-1**（供数滞后时更旧）—— 报表里的 asof 就是真 asof，
不撒谎；但要接受「今天的简报可能是两天前的截面」。回补任务默认 `EngineRoot` 写死为
`D:\workspace\stock_trading\a-stock-engine`，换机需改 XML/参数。

---

## 3. 红线与约束（不变）

- `liveTradingEnabled` **恒为 false**；全部 SIMULATE/paper。ADR `0064` 之前禁止触碰。
- `market.db` 是**只读**行情真相源（ADR `0058`）；摄取归生产侧，平台**不代抓不补写**（回补任务唤醒的是
  **引擎自己的脚本**，不是平台去抓数）。
- 绩效口径红线（ADR `0033`/`0068`）：**不算夏普/年化；样本 <20 标噪音；`equityCurve` 非可交易组合曲线**。
- **`data/` 下的存储是生产数据**：测试一律不得写入（ADR `0069`）。新增任何 cwd 相对存储时，
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
| **PowerShell 工具不捕获子进程 stdout** | 落文件再 Read（且 `WriteAllText` 用 UTF-8，避免 BOM 乱码） |
| **PowerShell 遇子进程非零退出即中断** | 命令串尾 `exit 0`；真实退出码单独落文件 |
| **`Remove-Item` / `rm` 静默失败** | 用 Python `pathlib.Path.unlink()` |
| **同消息多 Edit 只落部分** | 一次只发一个 Edit，或改用 Python 精确替换 + 断言唯一命中 |
| **测试全绿但 `EXIT 1`** | safe-delete 杀 teardown；判据 = 进度条 100% 且收集数 == 通过数 |

---

## 6. 一句话状态

**`v4.3.0` 让闭环"能算"，`v4.3.1` 让输出"可信"，`v4.4.0` 让循环"自足"**：盘前不再可能静默写空
（覆盖率守卫 + 回补任务），选股输出自带**中文名**，持仓放一个文件即进 ③A/③B；下一个目标是在生产侧
回补 `≥ 2026-10-16` 的 bar 之后，看到**第一个无人值守的 `settledNewly > 0`**。
