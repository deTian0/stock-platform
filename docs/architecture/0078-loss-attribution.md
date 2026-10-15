# 0078 — 收益归因 / 负收益根因诊断（loss attribution）

- Status: Accepted
- Date: 2026-10-15
- Supersedes: —
- Related: ADR 0077（`Y1` 策略采纳闸门）、ADR 0074（`R4` 绩效代理台账）、
  ADR 0063（`S4` 行业中性化）、ADR 0062（`S3` 闸门敏感性）、
  ADR 0059（`X4` 回放单点）、ADR 0058（market.db 只读真相源）、
  ADR 0071（`report_html` 单点）

## 背景

`Y1`（采纳闸门）解决了「改进能不能进生产」，但它**第一次把坏消息完整地摆上桌面**：

| 证据 | 数字 | 来源 |
|------|------|------|
| 生产基线在三个样本外窗口**全部**跑输 | `w1/w2/w3` 基线夏普 0.944 / 0.639 / 0.506，候选 `gate_070` 在 2/3 窗有正超额 | `Y1` 真机三窗 |
| 近一年代理台账（长窗回测）实际亏损 | `avgReturn=−0.38%`、`winRate=0.3735`、`avgHold=34.3d` | `R4` 真机 |

两个事实合起来给出一个**平台此前无法回答**的问题：**为什么现在是亏的？**

此前的观测面（`R3`/`T1`/`T2`）只能回答「循环有没有跑」「供数准不准」，回答不了收益；
`A4`/`A5` 能给出「赚了多少」的**结论**，但给不出**归因**。于是「下一步改什么」只能靠猜，
而 `S3`/`S4` 的教训（单窗口最优点在样本外不复现）说明**猜错的代价很实在**。

## 决定

新增里程碑 **`Y3` 收益归因**。新增单点
`packages/research/src/stock_platform_research/attribution.py` +
CLI `stock-platform-attribution`。

### 1. 把「为什么亏」拆成**四问**，每问一个可处置动作

| 问 | 口径 | 若命中 ⇒ 动作 |
|---|---|---|
| **信号有 edge 吗？** | 过闸/入选标的对未来 `k∈{1,3,5,10,20,40}` 交易日的**平均超额**（个股 − 基准）与胜率曲线 | 全负 ⇒ 信号本身无效，先改信号 |
| **持有期错配？** | 同一曲线：短端见顶后转负 ⇒ 持有过久；只在长端为正 ⇒ 持有过短 | 移动出场 / 调整持有窗 |
| **成本吃掉了？** | 同一批成交的 `gross_ret` vs `net_ret`（佣金/印花税/滑点） | 毛正净负 ⇒ 降换手；成本占比 ≥ 30% ⇒ 评估换手 |
| **集中在某处？** | 按月份 / 退出原因 / 资产类别 / 行业分组的净收益占比与**亏损质量占比** | 单组占亏损 ≥ 40% ⇒ 定点排查该暴露 |

另附**赔率结构**（胜率 / 平均盈 / 平均亏 / 盈亏比 / 期望值），区分「输多但小赢大亏」与
「输赢对称但整体偏负」——这两者的处方完全不同。

### 2. 两个样本集，回答不同问题

| 集合 | 定义 | 用来回答 |
|---|---|---|
| `gated` | 过闸（`apply_entry_gates`）的**全部**标的 | **评分单调性**：高分是否真的更好（`Y1` 的 `gate_070` 线索） |
| `picks` | 过闸 **且** `composite_score >= score_floor`（生产默认 0.80） | **实际会买的**那批标的的 edge / 成本 / 赔率 |

曲线对**两个集合各算一遍**：`gated` 与 `picks` 的差就是**评分闸门**本身的贡献——
这正是 `S3` 敏感性说「0.80 是全网格最差」却始终无法证实的地方。

### 3. 与生产**同源**的打分，绝不另起一套

面板用 `lvrev.score_lvrev` + `gates.apply_entry_gates`，**逐日**在当日截面上打分
（与 `screener_entry_provider` 的调用方式完全一致）。收益/成本块用
`neutralization_ab.run_neutralization_book`（其内部是 `X4` 单点 `book_replay.replay_book`）
跑一次基线档得到成交。**归因面板与生产选股不存在第二份实现**。

### 4. 裁决是**纯函数 + 事前登记阈值**

`diagnose(curve_picks, curve_gated, score, cost, payoff, concentrations)` 只吃已算好的块，
不碰 pandas、不碰引擎；阈值常量固定：`COST_SHARE_WARN=0.30`、`LOSS_CONCENTRATION_WARN=0.40`、
`SPEARMAN_FLAT=0.05`、`PAYOFF_RATIO_WARN=1.0`、`WINRATE_WARN=0.50`、`MIN_MEANINGFUL_SAMPLE=20`。
输出 `causes[]`（含 `code` / `severity` / `evidence` / `action`），按
**严重度 → |影响量|** 排序。**样本不足的 horizon 不参与结论**（`adequate=False`）。

### 5. 只出归因，**不改档**

本模块**绝不**修改任何生产默认档，**不写** brief / picks，报告显式携带 `attributionNote`。
它产出的「候选方向」（缩短持有 / 抬闸门 / 加暴露上限）**仍须过 `Y1` 采纳闸门 + 人工签核**。
`Y1` 与 `Y3` 因此构成闭环：**`Y3` 找方向 → `Y1` 验方向 → 人工签核落地**。

### 6. 出口

- 报告 `data/strategy/attribution.{json,md,html}`（`.json` 机器契约，`.html` 走 `report_html` 单点）；
- CLI `stock-platform-attribution`（`--years/--start/--end/--universe/--benchmark/--score-floor/--horizons/--buckets/--reference-horizon/--no-replay`）；
- 契约 [`docs/contracts/attribution.md`](../contracts/attribution.md)。

## 备选方案（未采纳）

| 方案 | 为什么不要 |
|---|---|
| **直接按 `Y1` 的 `gate_070` 线索改生产闸门** | `Y1` 已判定「不采纳」（w1 未达标）。归因先给出**为什么**，再决定是否值得重开该候选——顺序不能颠倒 |
| **把归因塞进 `loop_health`（`T` 域）** | `loop_health` 的硬约束是**零网络、只读、秒级**且每段独立 try-except；归因要跑一次回放（分钟级）。混进日常体检会把「监控」变成「跑批」 |
| **把归因做成 Workbench 面板** | 与 `Y1` 同一取舍：归因是**决策前的一次性离线评估**，不是盯盘面；`data/strategy/attribution.html` 可直接打开 |
| **用 SciPy 的 `spearmanr`** | `research` 包只依赖 numpy/pandas（`pyproject` 硬约束）。改用「秩的 Pearson 相关」等价实现，零新依赖 |
| **把真实台账（`recommend_decisions.jsonl`）也纳入** | 真实台账 settled 长期个位数（`R4` 已论证），落进噪音区；归因需要**可读的样本量**，故走长窗回放 + 代理口径，并在报告中标注口径 |

## 后果

- **正面**：平台第一次能回答「为什么亏」并把它变成**可处置清单**；`Y1` 的候选从此有来源，
  不再依赖「抄 `S3`/`S4` 的旧结论」；两个样本集的并列使**评分闸门本身**的价值可被量化。
- **代价**：新增一次回放（近一年基线档，分钟级）；面板逐日打分与 `S3`/`S4` 同级开销。
- **风险**：归因依赖**基准**。基准不可用时退用裸收益（`basis="raw"`）并在报告顶部显式标注，
  不会静默把「裸收益」当「超额」；窗口末端的截尾会让长 horizon 样本变少——按 horizon
  单独统计样本量并标 `adequate`，**不做补零、不做前向填充**。
- **测试**：`packages/research/tests/test_attribution.py`（前瞻收益分位与截尾、基准对齐与 ffill、
  面板构建与两个样本集、曲线/单调性/成本/赔率/集中度各块、`diagnose` 七类原因 +
  严重度排序 + 退用 `gated` 的回落、渲染、CLI 端到端 + 临时 SQLite）。

## 不做的事

- **不改任何生产默认档**（见 §5）。
- **不做参数寻优**：本模块**定位**原因，不搜索最优旋钮（`S3` 的职责）。
- **不做择时/仓位归因**：本期只做**选股信号 + 持有期 + 成本 + 分组集中度**四个维度；
  择时（regime 闸门）与仓位（slot sizing）归因留待后续里程碑。
- **不做生产侧回补 / 不做实盘**：承接 ADR 0058 只读与 `L1` 门禁（`liveTradingEnabled` 恒 `false`）。
- **不加 Workbench 面板**（见备选方案）。
