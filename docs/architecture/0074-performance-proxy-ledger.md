# 0074 — 绩效代理台账（performance proxy ledger）

- Status: Accepted
- Date: 2026-10-14
- Supersedes: —
- Related: ADR 0033（推荐绩效原始口径）、ADR 0059（picks ↔ 回测同源）、ADR 0068（绩效 PnL 闭环）、
  ADR 0069（测试数据隔离）、ADR 0058（market.db 只读真相源）

## 背景

`R3` 的循环体检（ADR 0073）把「绩效样本不足」升格为一等裁决输出，真机读数是
`performance` 段 **settled = 3 / pending = 20**——落进 `MIN_MEANINGFUL_SAMPLE = 20` 的
**噪音区**。于是「这套选股逻辑到底赚不赚钱」这个问题**长期没有可读的样本量**。

根因是结构性的，不是 bug：

```
真实台账 = 实时 brief TopN（每交易日 ≤ N 条）
         × 必须等持有窗口（默认 5 个交易日）走完才能结算
⇒ 样本增长被日历硬约束：一个月的实时运行最多产出几十条，扣掉未到期的窗口，
  真正 settled 的只剩个位数。
```

想回答「赚不赚钱」，需要的是**样本量**，而样本量的前提是**时间**。平台已有两条现成通路：

1. **回测引擎**（ADR 0059 / `book_replay.replay_book`）——一个 ≥1 年长窗就能跑出几十上百笔成交；
2. **绩效汇总算术**（ADR 0068 / `performance.performance_summary`）——一套被契约冻结的口径。

缺的只是**把两者接起来**：一个把「回测成交」翻译成「决策行」的转换口，以及一份
**说清楚两者不可比**的口径契约。

## 决定

### 1. 新增只读单点 `research.performance_proxy`

`packages/research/src/stock_platform_research/performance_proxy.py`：

| 函数 | 职责 |
|---|---|
| `trades_to_decision_rows(trades, equity_curve=…)` | 回测成交 → 与真实台账**逐字段同形状**的决策行（全部 `pending=False`） |
| `write_proxy_ledger(path, rows)` | **覆盖**写代理台账（非追加；代理是「一次回测的完整派生」） |
| `load_proxy_ledger(path)` | 缺失文件返回空表（fail-closed，不抛） |
| `build_proxy_view(...)` | 真实 vs 代理**并排视图**（两侧各跑 `performance_summary`） |
| `render_proxy_markdown(view)` | 人读版：样本充分性 / 两侧指标 / 口径差异表 |

配套 CLI `stock-platform-performance-proxy`：读只读 `market.db` → 跑长窗回测
→ 写代理台账 + 报告（`proxy_vs_real.{json,md,html}`）。

### 2. 代理行与真实行**同形状**（这是能被同一套算术吃下的前提）

代理行沿用真实台账字段，并**不新增**任何既有读取器会误读的键：

| 字段 | 代理取值 |
|---|---|
| `date` | 建仓日 = `equity_curve[trade.entry_idx].date` |
| `symbol` | `trade.code` |
| `rating` | `Buy` |
| `raw` | **扣费**净收益 `net_ret`（百分数 → `"+x.xx%"`，复用 `performance.format_pct`） |
| `alpha` | **恒 `None`**（代理侧无同窗口基准超额，**不编造**） |
| `holding` | `f"{held_days}d"`（真实持有天数，非固定 5） |
| `pending` | **`False`**（成交即已结算） |
| `source` | **`"backtest_proxy"`**（数据层面杜绝误认） |
| `ledgerKind` | `"proxy"` |

额外保留 `exitReason` / `exitDate` / `grossRetPct` / `netRetPct` / `assetClass` 作审计用
（`performance.settled_records` 只读它认识的键，多余键无害）。

### 3. 口径**刻意不同** ⇒ 分栏陈列、**禁止混算**

| 维度 | 真实台账 | 代理台账 |
|---|---|---|
| 信号源 | `brief.asof`（实时） | 回测建仓日（历史回放） |
| 出场 | T+N 固定持有（默认 `5d`） | 引擎退出规则（止损/止盈/趋势/最长持有） |
| 收益口径 | `raw` 裸收益（**不含成本**） | `net_ret` 扣费净收益（**含佣金/印花税/滑点**） |
| 窗口关系 | 决策间**重叠**（非组合曲线） | 单账户序列（仓位上限 + 现金约束） |

四维全不同，故任何**合计 / 平均 / 相减**都会产生无意义数字。`build_proxy_view` 因此：

- **只做并排**：`real` / `proxy` 各跑一次 `performance_summary`，各带 `ledgerKind` 与 `scale`；
- **不产出任何跨侧字段**：视图顶层**没有** `total` / `combined` / `merged` 之类的合并键
  （`test_build_proxy_view_is_never_combinable` 逐名断言）；
- 显式写死 `comparability.combinable = False` + 中文 `reason`。

### 4. 两侧复用**同一套**汇总算术

`real` 与 `proxy` 都走 `performance.performance_summary` → `compute_performance`
（ADR 0068 的冻结口径），所以「样本量对照」是在**同一把尺子**下看的；差异**只**来自输入的
口径（上述四维），不来自两套实现。`comparability.singlePoint` 记录这一事实。

### 5. fail-closed：缺件标注，绝不编造

- 真实台账文件不存在 → 该侧 `totalEntries=0` / `settledCount=0`，**不报错**；
- 回测 `ok=False`（无行情 / 无成交）→ 代理台账为空，报告照常产出并如实标注；
- `alpha` 在代理侧恒 `None`——**不**用 `raw` 冒充 `alpha`。

## 后果

**正面**

- 「这套逻辑赚不赚钱」第一次有 **≥ 门槛**的样本（真机 1 年窗口：代理 settled 83 vs 真实 3）。
- 代理与真实**并排**，差异**显式成表**，读者不会再拿两个不同口径的数字互相印证。
- 复用 `book_replay` 单引擎（ADR 0059）与 `performance_summary` 单算术（ADR 0068），
  **零新增业务逻辑**——本模块只有翻译与呈现。

**代价 / 已知边界**

- **代理不是实盘、也不是那个推荐**：它是「同一套引擎在同一段历史里的选股侧表现」，
  是**代理**（proxy），不是已验证的前瞻绩效。报告里逐字写死。
- 真机 1 年窗口读数为 **负**（`total_return ≈ −2.4%`）——这是**诚实**读数，不美化；
  样本够了只代表「可以看」，不代表「好看」。
- 代理台账**覆盖写**（每次运行整表重算），不做增量；历史窗口变了就必须整跑。
- 不新增 Workbench 端点（与 X4 一致，UI 面留待后续里程碑）。

## 验证

- 单测 `packages/research/tests/test_performance_proxy.py`（19 例）：同形状转换、
  `net/gross` 口径、坏行丢弃、被 `performance_summary` 直接吃下、**禁止混算**（顶层无合并键）、
  样本充分性、缺台账 fail-closed、provenance 传递、渲染、台账覆盖写、模块零 `providers` 依赖、
  CLI 端到端（引擎替身）与 `--no-write`。
- 真机一次运行（2026-10-14，`--years 1`，universe=stock）：代理 settled **83**（≥20）、
  `totalEntries=83`、`winRate=0.3735`、`avgReturn=−0.38%`、`avgHold=34.3d`；
  真实 settled **3** / pending 20。报告落 `data/performance/proxy_vs_real.{json,md,html}`。
- `check_docs.ps1` / `check_versions.ps1` 双绿；全量 pytest 全绿。
