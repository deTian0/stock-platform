# 交接：stock-platform v4.2.0 → 下一块砖（绩效 PnL 闭环）

> 生成：2026-10-12 · 用途：**新对话零上下文接续**，不必回读旧会话
> 仓库：`D:\workspace\stock_trading\stock-platform` · 分支 `main` · HEAD `5f712cb` · tag `v4.2.0`
> 状态：工作树**干净**，远端 `main` == 本地 HEAD，tag 已推

---

## 0. 接手第一件事（照抄执行）

```powershell
cd D:\workspace\stock_trading\stock-platform
.\.venv\Scripts\python.exe -m pytest packages apps -q          # 期望 980 passed / 0 failed
.\scripts\ops\Register-ScheduledTasks.ps1 -Status               # 看两个任务 lastResult 是否 0x0
.\.venv\Scripts\python.exe -m stock_platform_research.daily_digest_cli   # 看 data/digests/latest.md
```

**环境**：`.venv`（→ miniconda 3.14.6，`--system-site-packages`）。**注意**：裸 miniconda python **没有** stock_platform 包，一切命令必须用 `.venv\Scripts\python.exe`。

---

## 1. 上一里程碑（v4.2.0，已完成并验收）

**主题**：每日调度上线（双任务）+ 用户可读日报。**两块砖一起落**。

| 交付 | 说明 |
|---|---|
| `stock-platform-daily`（08:30） | `-MarketDb -PrevSession -Digest`，**已注册进本机任务计划程序** |
| `stock-platform-postmarket`（15:30，新） | `-MarketDb -PrevSession -SettleAfter -Digest`，**已注册** |
| `scripts/ops/Register-ScheduledTasks.ps1` | 注册 / `-Status` / `-Unregister` / `-RunNow`，幂等，**无需管理员** |
| `stock-platform-digest`（新 CLI） | `daily_digest.py` 从权威 SQLite brief 渲染 Markdown → `data/digests/{asof}.md` + `latest.md` |
| `-PrevSession`（包装脚本新开关） | asof 解析为**前一交易日**，见下方红线 |

**实测证据**：调度器按需触发 `result=0x0`；整市 brief 5210 行截面 / Top10；digest 118 行含推荐表+五榜+命中追踪；测试 972→**980**（+8）。

**三个必须知道的事实**

1. **`-PrevSession` 不是可选项**：market.db 由生产侧**晚间**回补，08:30 与 15:30 时点**都没有当日 bar**，用今天必得空面板。库里 asof=2026-10-12 那条 `panelSize=0 / picks=[]` 的废 brief 就是实证。→ **盘后复盘同样基于 T-1**。
2. **PS 5.1 两个注册坑**（已在 `Register-ScheduledTasks.ps1` 内置规避，勿"优化"掉）：① `Get-Content -Raw` 会按 GBK 解码 UTF-8 无 BOM 文件 → 中文乱码 → 必须用 `[System.IO.File]::ReadAllText()`；② `Register-ScheduledTask -Xml` **拒绝** `<?xml encoding="UTF-8"?>` 声明 → 注册前须剥掉（XML 文件里保留，供 GUI 导入）。
3. **正确性的项目约定**：日报只从**权威 SQLite brief 仓库**（`persistence.py`）读，绝不并行解析 JSON 导出；查无数据 fail-closed 输出占位说明，**不编造数字**；辅助数据（绩效 JSONL）读取 best-effort，缺失不阻断。

---

## 2. 下一块砖 = 绩效 PnL 闭环

路线图原文（`docs/plans/trading-system-roadmap.md` 末行）：
> **下一块砖 = 绩效 PnL 闭环（performance JSONL → 用户可见收益归因）**

### 现状（已探明，勿重新发现）

| 组件 | 位置 | 状态 |
|---|---|---|
| 记账写入 | `data/recommend_decisions.jsonl` | 3 行，**全部 `pending: true`**（2026-09-02 / 09-22） |
| 字段 | `date, symbol, rating, raw, alpha, holding, pending, source, rank, score` | `raw`/`alpha` **全为 null** = 未结算 |
| 已有 CLI | `stock-platform-performance`（`performance_cli.py`） | 存在，未端到端验证 |
| 已有引擎 | `--settle-after`（日流水线已接，盘后任务带此开关） | 依赖 engine `market.db` 结算 |
| 日报已接 | `daily_digest.performance_summary()` | 只统计 pending/settled **计数**，无收益数字 |

### 缺口（这就是要做的事）

**计数有了，收益没有。** 具体：

1. **为什么全是 pending？** 先查清 `--settle-after` 为何没结算掉 2026-09-02 的样本（持有期 `5d` 应早已到期）。可能是：结算窗口判定、market.db 缺该票该区间 bar、或 settle 路径未被实际触发过（盘后任务刚注册，**尚未自然运行过一次**）。
2. **`raw` / `alpha` 为何恒 null**：找到结算函数，确认它写不写这两个字段。
3. **收益归因**：现在没有任何地方回答"这套推荐逻辑赚不赚钱"。需要：单条收益 → 按 rank / 分数分桶 / 按日期聚合 → 胜率、平均收益、累计曲线、是否跑赢基准。
4. **让日报显示真数字**：`performance_summary` 从"计数"升级为"计数 + 收益概览"（在闭环打通之后）。

### 建议切入点（按序）

```powershell
# 1) 读现有实现，搞清 settle 语义与字段契约
#    packages/research/src/stock_platform_research/performance.py（及 *_cli.py）
#    docs/architecture/0033-recommend-performance.md   ← 先读这份 ADR
# 2) 手工触发一次盘后任务，看 settle 到底做了什么
Start-ScheduledTask -TaskName 'stock-platform-postmarket'
#    或直接: .\scripts\ops\Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Verbose
# 3) 对照 JSONL 前后差异，定位为何未结算
```

**风险提示**：结算读 engine `market.db`（3.15 GB，只读）。参考日期 `5d` 持有期需按**交易日**推进，不是日历日——2026-10-09 至今跨了国庆长假。

---

## 3. 红线与约束（不变）

- `liveTradingEnabled` **恒为 false**；全部 SIMULATE/paper。ADR `0064`（`L1` 实盘立项）通过前禁止触碰。
- market.db 是**只读**行情真相源（ADR `0058`）；摄取归生产侧 `a-stock-engine`，平台**不代抓不补写**。
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

## 5. 工程环境坑（上一会话踩过，务必沿用）

| 坑 | 规避 |
|---|---|
| **Bash PATH 损坏** | `dirname`/`head`/`cat`/`grep`/`sed`/`wc` 全部 exit 127。读文件用 Read 工具，或 `python -c` |
| **PowerShell 工具不捕获子进程 stdout** | 用 `[System.IO.File]::WriteAllText/AppendAllText` 写文件后再 Read |
| **PowerShell 遇子进程非零退出即中断** | 命令串里 `exit 0`，真实退出码单独落文件 |
| **here-string 传 `python -c` 引号被吃** | 写 `.py` 脚本文件再执行 |
| **`Remove-Item` / `rm` 静默失败** | 用 Python `pathlib.Path.unlink()` |
| **同消息多 Edit 只落部分** | 一次只发一个 Edit，或改用 Python 精确替换 + 断言唯一命中 |
| **`Out-File` 编码 mojibake** | 读取时显式指定 encoding |

---

## 6. 一句话状态

**v4.2.0 已交付并验收**（调度真跑起来了 + 日报能看懂了）；下一个目标是把 `performance` JSONL 里那 3 条 pending 结算掉，并让"赚不赚钱"这个问题的答案出现在日报上。
