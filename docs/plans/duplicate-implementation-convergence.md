# C3 — 重复实现收敛清单（双线）

> 里程碑 **C3**（由 **R2** 收口）· 状态 **done（2026-10-14）** · 版本 `v4.6.2`
> 承接：[dual-line-responsibility.md](dual-line-responsibility.md)（`C1` 职责边界）·
> [trading-system-roadmap.md](trading-system-roadmap.md) §3.6
> 相关 ADR：[0058](../architecture/0058-market-db-source-of-truth.md)（`market.db` 真相源）·
> [0072](../architecture/0072-symbol-master-name-authority.md)（名称权威）

## 0. 一句话结论

**`stock-platform` 是唯一权威实现；`a-stock-engine`（已归档）降级为「只读参考 + 行情/基本面生产者」。**
本清单**只定边界、不删代码**（承接 C 域约束）——收敛通过已有里程碑**逐项委派或静态互测**完成，
而非一次性大合并。

## 1. 判据

出现以下任一即为「重复实现」：

1. 同一能力在两条线各有一份**可执行实现**（不是文档/说明）；
2. 同一套常量或规则被**复制**而非**委派**；
3. 同一份数据被两条线各自**抓取**或各自**写库**。

**处置档**：`保留`（各线自有、边界不同，不复用）／`降级为参考`（引擎侧冻结、只作对照）／
`已收敛`（已单点化或已委派，重复已消除）。

## 2. 收敛清单（主表）

| # | 能力域 | 平台侧（权威单点） | 引擎 / 上游侧（参考） | 处置 | 依据 | 状态 |
|---|--------|--------------------|------------------------|------|------|------|
| 1 | 选股打分 | `research/lvrev.py`（`score_lvrev`） | `src/lvrev_scorer.py`、`src/factor_engine.py` | 降级为参考 | M3.1 | 已收敛 |
| 2 | 因子库 / 权重 | `research/factors.py`（`FACTOR_LIBRARY`）+ `lvrev.W_DEFAULT` | `src/multifactor.py`、`src/factor_analysis.py` | 降级为参考 | S2 | 已收敛 |
| 3 | 入场闸门 | `research/gates.py`（`EntryGateParams`） | `src/guard.py` | 降级为参考 | S3 | 已收敛 |
| 4 | 组合回测引擎 | `research/backtest.py` + `book_replay.replay_book` | `local_backtest.py`、`mini_backtest.py`、`src/backtest.py` | 降级为参考 | B1–B6、X4 | 已收敛 |
| 5 | 交易规则（退出/冷静期/偏差/涨跌停） | `research/rules.py` | `local_backtest.py` 内联、`src/risk_module.py` | 降级为参考 | B5 | 已收敛 |
| 6 | 费用模型 | `portfolio.CostModel` | `local_backtest.py` 常量 + ETF 前缀表 | 降级为参考 | B3（跨线静态互测） | 已收敛 |
| 7 | 资产类型 / ETF 免税 | `portfolio.asset_class` | `local_backtest.py` `_is_fund` / `_is_etf` | 降级为参考 | B4（跨线静态互测） | 已收敛 |
| 8 | 榜单（②A/②B/③A/③B/③C） | `research/rankings.py` | `src/daily_brief.py`、`src/stock_research.py` | 降级为参考 | X2（只搬语义） | 已收敛 |
| 9 | 命中追踪 | `research/hit_tracking.py` | `src/pick_tracker.py` | 降级为参考 | X3 | 已收敛 |
| 10 | 行情抓取 | `packages/providers/*`（东财只走 `em_get`） | `src/tushare_provider.py`、`src/akshare_provider.py`、`import_local_data.py`、`src/westock_cli.py` | 降级为参考（**平台不代抓**） | C2 / ADR 0058 | 已收敛 |
| 11 | 行情真相源 | `market.db.daily_price`（**只读**挂载） | 引擎写库侧 | 保留（生产者唯一） | C2 | 已收敛 |
| 12 | 基本面 / 名称 | `research/symbol_master.py`（读引擎 `fundamentals`） | `src/fundamental_store.py`、`collect_fundamentals.py` | 保留（生产者唯一） | R1 | 已收敛 |
| 13 | 多 Agent（研报/复盘/辩论） | `packages/agents`（`plugin` / `debate` / `debate_lane` / `llm_debate`） | 上游 TradingAgents、`src/stock_research.py` | 降级为参考 | M4 / M12 / M33 / M-A1 | 已收敛 |
| 14 | 报告渲染（md→html） | `research/report_html.py` | `src/html_report.py`、`src/report_renderer.py` | 降级为参考 | v4.5.0 | 已收敛 |
| 15 | 交易日历 | `providers/calendar.py` + `data/*_closed_days.txt` | 引擎无独立日历 | 保留（平台唯一） | M10 / M13 / M42 | 已收敛 |
| 16 | `.env` 加载 | `research/dotenv.py` | `src/sys_config.py`（自带） | **保留** | ADR 0066 | 保留 |
| 17 | 每日调度 | WorkBuddy 自动化（盘前/盘后/回补） | Windows 任务计划程序（**已注销**） | 保留（WorkBuddy 唯一） | §调度迁移 | 已收敛 |
| 18 | 报告跑批 | Skill `stock-platform-report-sweep`（import 平台单点） | 无 | 保留（平台唯一） | v4.5.0 | 已收敛 |

## 3. 已完成收敛的证据（逐条）

- **规则单点（#5）**：`backtest.evaluate_exit is rules.evaluate_exit` 之类**对象同一性**
  随结果返回（`sameDefinition`），并有差分一致断言 —— 回测与在线走**同一个函数**。
- **费用/资产类型（#6/#7）**：跨线互测**静态解析**引擎源码的常量与前缀表（不比运行结果，
  因为引擎构造即连 SQLite、不可在测试内 import），四象限比对通过。
- **回测与推荐同引擎（#4）**：`picks_backtest` 与 `backtest` 共用 `book_replay.replay_book`，
  重构前 8 场景曲线/成交 **sha256 逐位一致**。
- **榜单只搬语义（#8）**：③B 减仓建议**委派** `rules`（`reason` 原文透传），平台不写第二套卖出规则。
- **行情只读（#10/#11）**：平台侧 `EngineSqliteProvider` 只读挂载 + 覆盖守卫；
  **摄取归生产侧**，回补任务唤醒的是**引擎自己的脚本**，不是平台去抓数。
- **名称派生（#12）**：`symbol_master` 由引擎 `fundamentals` 单向只读派生，**不写回引擎**。
- **报告渲染（#14）**：跑批器删除私有 `_CSS` / `md_to_html`，改 import 平台单点 —— 样式只有一处定义。

## 4. 明确「保留」的余量

| 项 | 为什么保留 |
|---|---|
| #16 `.env` 加载 | 两条线是**不同运行边界**（不同 venv / 不同工作目录）；跨线复用会把两套配置耦合在一起，得不偿失 |
| #11 / #12 生产者侧 | **写库归生产侧**（ADR 0058）；平台若代写即制造第二个真相源 —— 正是要避免的重复 |
| 引擎自身脚本 | 引擎已归档但**仍在生产行情/基本面**；其脚本**冻结新功能**，只作参考与供数，不删 |

## 5. 红线（承接 C 域）

1. **不执行为「收敛」而做的批量删除** —— 只定边界、列清单，代码收敛按里程碑渐进。
2. **禁止 fork 出第二条产品主链**；禁止把 Skill 仓 `pip install` 进产品依赖。
3. **平台不代抓、不写回引擎库**（ADR 0058）；`market.db` 只读挂载。
4. 任何跨线**数字比较**仍须遵守 [trading-rules](../contracts/trading-rules.md) §9 的不可横比铁律
   （须声明 `exit_policy` / `cooldown_days` / `drift_band`）。

## 6. 后续动作

- **无强制待办** —— 18 项中 16 项已收敛、2 项按边界**保留**。
- 若未来引擎侧恢复活跃开发，须先复核本清单，把新增的重复项登记进来再动代码。

## 7. 免责

本清单为**工程治理文档**，不构成投资建议。平台全程 SIMULATE（`liveTradingEnabled=false`）。
