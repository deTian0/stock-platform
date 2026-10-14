# 0077 — 策略采纳闸门（strategy adoption gate）

- Status: Accepted
- Date: 2026-10-14
- Supersedes: —
- Related: ADR 0063（`S4` 行业中性化）、ADR 0062（`S3` 闸门敏感性）、
  ADR 0060（`S1` 同源 A/B）、ADR 0059（`X4` 回放单点）、
  ADR 0058（market.db 只读真相源）、ADR 0074（绩效代理：真实/代理禁混算）

## 背景

到 `v4.9.1` 为止，`G/B/S/X/C/R/T` 七域已在**研究侧**做得相当完整：回测可信（`B1–B6`）、
策略可迭代（`S1–S5`）、选股可日用（`X1–X4`）、循环可观测（`R3`/`T1`/`T2`）。
但出现了一个结构性问题：**研究结论与生产默认档之间没有桥**。

三个实测事实：

| 事实 | 数字 | 当时处置 |
|------|------|----------|
| `S4` 行业中性化 | `total_return` 0.3029 → **0.5257**、`sharpe` 1.06 → **1.14**；叠加 `max_per_industry=3` → **0.5850 / 1.2492** | **只诊断不改档** |
| `S3` 闸门敏感性 | 出厂 `min_pick_score=0.80` 的 `sharpe` **1.060 是全网格最差**（`0.5/0.6/0.7` = 1.253/1.129/1.157） | **只诊断不改档** |
| `R4` 绩效代理（近一年） | `winRate=0.3735`、`avgReturn=−0.38%` | 记录，不处置 |

「不采纳」在当时是**对的判断**：单窗口的最优点可能是**噪声**（曲线拟合）。
但由此产生一个更坏的结果 —— **没有任何机制**能把「多窗口稳健成立」的改进送进生产，
于是所有研究都停在报告里。**平台不改进 = 赚不到钱。**

## 决定

新增 **`Y — 收益增强（Yield）`** 域，首个里程碑 **`Y1` 策略采纳闸门**。
新增单点 `packages/research/src/stock_platform_research/adoption_gate.py` +
CLI `stock-platform-strategy-adoption`。

### 1. 用「多窗口样本外 + 事前登记规则」替代「单窗口最优点」

| 决定 | 内容 |
|---|---|
| **基线 = 生产档本身** | `BASELINE_SPEC` 就是 `min_pick_score=0.80` + `neutralize=None` 的原始筛选档；候选与它**共用同一引擎**（`run_neutralization_book` → `X4` 单点 `book_replay.replay_book`），差异只来自旋钮 |
| **窗口互不重叠** | `build_windows(last_date, years=1, count=3)` 从最后交易日**向前**按年切分，旧→新排序 |
| **特征只算一次** | 全跨度上算 `prepare_book_frame`（含 `ma20`/`ma60` 预热）后按日期切窗 ⇒ 窗口边界**不损失**预热，且比每窗重算快得多 |
| **规则事前登记** | `AdoptionRule(min_sharpe_margin=0.05, max_drawdown_tolerance=0.05, max_winrate_drop=0.05, min_trades=8, require_all_windows=True)` —— 阈值**先于**看结果固定 |
| **纯函数裁决** | `decide_adoption(per_window, rule)` 只吃两组指标字典，不碰引擎、不碰 pandas，可被单测穷举 |

### 2. 三种结论，样本不足**不做结论**

| 结论 | 条件 |
|---|---|
| `adopt` | 全部可评估窗口 `pass`（或 `--any-window` 下 `pass` 多于 `fail`） |
| `reject` | 存在 `fail` 窗口（严格档） |
| `insufficient` | 全部窗口笔数 < `min_trades` ⇒ **不给结论**，明确写出理由 |

窗口级 `pass` 需**三项风险闸门全过**：夏普边际、回撤恶化容差、胜率下滑容差；
任一指标缺失判否（**不**默认通过）。这样 `S4` 那种「收益/夏普大幅改善但回撤恶化 9pp」
的候选会被**如实拦下**，而不是被单看收益就放行。

### 3. 只出建议，采纳是**独立的人工签核**

本模块**绝不**修改任何生产默认档（`W_DEFAULT` / `DEFAULT_MIN_PICK_SCORE` / 出厂闸门），
**不写 brief / picks**，报告里显式携带 `adoptionNote` 说明这一点。
把 `adopt` 写进生产是计划中的 `Y2`（命名档案 + ADR + 契约 + 单点定义 + tag）。
**本模块不提供「一键改默认档」开关** —— 需求上就不该有。

### 4. 出口

- 报告 `data/strategy/adoption_gate.{json,md,html}`（`.json` 机器契约，`.html` 走 `report_html` 单点）；
- CLI `stock-platform-strategy-adoption`（`--years/--windows/--start/--end/--universe/--candidates` +
  规则覆盖 `--min-sharpe-margin/--max-drawdown-tolerance/--max-winrate-drop/--min-trades/--any-window`）；
- 契约 [`docs/contracts/adoption-gate.md`](../contracts/adoption-gate.md)。

## 备选方案（未采纳）

| 方案 | 为什么不要 |
|---|---|
| **直接把 `S4` 中性化设为生产默认** | 单窗口证据不足以排除过拟合；且它会**显著恶化回撤**（−0.1767 → −0.2673），与「赢钱」的另一半（控制回撤）冲突。必须先过样本外闸门 |
| **继续只诊断、不采纳** | 等于承认研究产出永远不进生产；`R4` 近一年 `avgReturn=−0.38%` 的负收益没有出口 |
| **把闸门做成自动改默认档** | 违反本仓「改行为必须同步 ADR / 契约 + 人工签核」的硬规则；交易参数不该由脚本自作主张 |
| **把「跑赢基准」也塞进裁决** | 会把「跑赢自己的基线」与「跑赢中证500」两个问题混在一起；基准 alpha 另有 `A4`/`A5`/`R4` 口径 |

## 后果

- **正面**：研究与生产之间的桥补上了 —— 任何改进只要在**多个样本外窗口**稳健成立就能被
  结构化推荐；「单窗口最优点」与「稳健改进」被同一把尺子区分开；每条候选的**阻塞项**
  逐窗列出（`blockingChecks`），落选原因可读、可复现。
- **代价**：新增一处研究侧计算入口（可跑 3 窗 × 5 档 ≈ 15 次回放）；`Prepare_book_frame`
  在全跨度上算一次的内存占用与 `S3`/`S4` 同级。
- **风险**：窗口切分方式（固定 365 天、按年）本身是一种口径选择；换窗口长度可能改变结论。
  缓解：`--years` / `--windows` 可调，报告显式记录窗口起止与 `rule`，结论**绑定口径**呈现。
- **测试**：`packages/research/tests/test_adoption_gate.py`（窗口切分/非重叠、纯函数裁决
  四种场景、候选注册表、引擎运行、端到端报告、渲染、CLI 端到端 + 临时 SQLite）。

## 不做的事

- **不改任何生产默认档**（见 §3）。
- **不做参数寻优**：本模块**评估**给定候选，不搜索最优旋钮（那是 `S3` 敏感性网格的职责）。
- **不做基准 alpha**：窗口胜负按自指标裁决（见备选方案）。
- **不做生产侧回补 / 不做实盘**：承接 ADR 0058 只读与 `L1` 门禁（`liveTradingEnabled` 恒 `false`）。
- **不加 Workbench 面板**：采纳闸门是**决策前的一次性离线评估**（3 窗 × 5 档约 2 分钟），
  不是日常盯盘面；结论落 `data/strategy/adoption_gate.html` 可直接打开 ——
  与 `S5`「定位是主链自动化、刻意不新增手动面板」同一取舍。
