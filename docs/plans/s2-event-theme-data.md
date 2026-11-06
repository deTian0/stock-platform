# S2 事件/主题数据源规划

> 状态：**P1 已实现**（2026-11-06，见 §2.1）；P0 由仲裁线另行评估；P2–P4 仍为规划。初稿 2026-11-05。相关：ADR [`0093`](../architecture/0093-multi-strategy-shadow-board.md) · 契约 [`multi-strategy-shadow.md`](../contracts/multi-strategy-shadow.md) · 计划 [`multi-strategy-final-board.md`](multi-strategy-final-board.md) §11/§12 · 治理 [`ops/skills-governance.md`](../ops/skills-governance.md)
> 红线：东财请求只经 `em_get`；不 `pip install` 任何 Skill / 抓取库；不另起平行抓取通路；不写 `market.db`；S2 信号未过 `FACTOR_LIBRARY` 准入不得进生产权重。

## 0. 结论先行

- S2 在回测里恒空池，原因是**没有按日 PIT 可回放的题材历史**，不是代码缺陷。现有 4 个 DI 钩子（`concept_blocks` / `sector_fund_flow` / `lhb` / `unlock`）在 `astock_http`（em_get）与 `replay` 都已实现，但只有一部分能按历史日期取数。
- 推荐路线：**先前向积累，再有限回补**。
  1. P1：生产日循环里给影子链注入当日截面（龙虎榜、板块资金流、解禁），落到 `local/shadow/s2_snapshots/`，从开启日起积累 PIT 前向账本。
  2. P2：对**本身带交易日期**的数据（龙虎榜、解禁、板块资金流 daykline）做有限历史回补，供回测用。
  3. P3：概念成分（`concept_blocks`）只有当前快照，历史回测须标「非 PIT」，或只用前向积累段。
- 即使 S2 有数据，在现行 Round2 仲裁下（优先级排在分数前，见 [`multi-strategy-final-board.md`](multi-strategy-final-board.md) §11）也大概率 0 席。**仲裁口径须先签核**，否则 S2 接入的回测收益无法体现。

## 1. 数据源盘点

| 能力 | 平台实现 | 端点（经 `em_get`） | 历史 PIT 可回放 | 覆盖起始 | PIT 风险 | 成本 / 限流 |
|------|---------|---------------------|-----------------|----------|---------|-------------|
| `lhb` 龙虎榜 | `astock_http.get_lhb(asof_date, look_back_days)` | datacenter `RPT_DAILYBILLBOARD_DETAILSNEW` + 买卖席位 | **可**：记录自带 `TRADE_DATE`，按 `asof` 过滤即 PIT | 东财多年历史（具体起点待 P2 实测，不预设） | 低：上榜当晚公布，T 日盘后可得 → 只能用于 T+1 入场 | 现实现按**个股**逐只查（3 次请求/只），全市场回补成本高；需改为按日期全市场查一页（新方法，须先扩矩阵） |
| `unlock` 限售解禁 | `get_unlock(asof_date, forward_days)` | datacenter `RPT_LIFT_STAGE` | **可（日程类）**：解禁日程提前公告，`FREE_DATE` 可按 asof 截取 | 多年 | 中：历史查询拿到的是**现在**的日程表，若曾修订则有前视；需记录公告日或接受误差 | 按个股查，成本同上 |
| `sector_fund_flow` 板块资金流 | `get_sector_fund_flow(sectors, start, end, limit≤1000)` | push2his `fflow/daykline`（`90.BK####`） | **部分**：daykline 带日期，可回放约 `limit` 根（端点实际保留深度待实测） | 近若干个月～数年，待实测 | 低（日期级） | 按板块查，板块数百个，成本可控 |
| `concept_blocks` 概念成分 | `get_concept_blocks(symbols)` | push2 `slist`（spt=3） | **不可**：只有当前成分 | 仅当日 | **高**：成分随热点调入调出，用今天的成分回放历史 = 前视 | 按个股查，全市场约 5k 次请求 |
| `news` 轻量新闻 | `get_news` | np-weblist 快讯 | **不可**：只取最近 N 条 | 仅当日 | 高 | 低；但未结构化，不建议进 S2 打分 |
| `fund_flow` 个股资金流 | `get_fund_flow` | push2his daykline | 部分（`limit` 根） | 待实测 | 低 | 属 S5，不在本计划 |
| 涨停原因 / 连板梯队 | **未实现**（矩阵仅 `depth5`「连板梯队封单」） | — | — | — | — | 需先扩能力矩阵 + 契约，再在 `providers` 内经 `em_get` 实现 |
| 上游 Skill（`a-stock-data` 等） | 只读配方（[`upstream/a-stock-data-em-get-recipe.md`](../upstream/a-stock-data-em-get-recipe.md)） | — | 取决于配方 | — | — | **不得**作为运行时；只能作为 P2/P4 实现的参考 |
| 引擎 `market.db` | 只读 | — | `daily_price` / `daily_basic_pit` / `fundamentals_pit` 有 PIT，但**无**题材 / 龙虎榜 / 板块表 | 2020-01-02 起 | — | 零网络；不能作为 S2 来源 |

注：表中「覆盖起始」凡写「待实测」的，P2 开工前须先实测并在本文回填，不预设数字。

## 2. 分阶段里程碑

### S2-P0 仲裁前置（口径，需签核）

- 先按 [`multi-strategy-final-board.md`](multi-strategy-final-board.md) §11.3 在回测里比较方案 A / B，你签核后写 ADR 再改 `round2`。
- 不做 P0 也能推进 P1（数据积累不依赖仲裁），但 S2 的回测席位指标要等 P0 落地后才有意义。

### S2-P1 前向积累（不改口径，最先做）

- 日循环开启影子链时，只用 `astock_http`（em_get）拉当日 `lhb`（全市场当日上榜）、`sector_fund_flow`（热门板块）、`unlock`（候选池内个股的 90 日窗口），注入 `school_s2_theme`。
- 同时把原始响应快照写入 `local/shadow/s2_snapshots/{asof}/`（不提交），作为以后回测的 PIT 历史。
- fail-open：S2 取数失败时 S2 空池并带 `reason`，不阻塞影子链，更不影响主链。
- 东财限流：遵守 `EM_MIN_INTERVAL` / 熔断；请求预算 ≤ 每日数百次（不对全市场 5k 只做 `concept_blocks`）。
- 需要新增「按日期全市场龙虎榜」方法时，先在 `capabilities` 和契约里声明，再在 `providers` 内实现（不在 research 里写 HTTP）。

### 2.1 S2-P1 实现记录（2026-11-06，已落地）

与上面初稿的差异：龙虎榜、解禁都改成**按日期全市场一次查**（不按个股循环）。板块资金流改用 push2 `clist` 的板块主力净流入排名截面，不再按板块逐个拉 daykline。这样每天请求数从「数百」降到个位数。

| 项 | 实现 |
|----|------|
| 触发 | 只在影子链日循环里触发（`run_shadow_board_daily`，即 `-ShadowBoard` / `--shadow-board`）；库默认仍关 |
| 模块 | `stock_platform_research.shadow_board.s2_snapshot`；provider 新方法 `AStockHttpProvider.get_lhb_daily` / `get_unlock_calendar` / `get_board_rank` |
| 传输 | 全部经 `em_get`（进程级节流 + 熔断 + 重试）；research 侧不写 HTTP |
| 落盘 | `local/shadow/s2_snapshots/s2_snapshot_{asof}.json`（或 `STOCK_PLATFORM_SHADOW_DIR` 下同名子目录），tmp + `os.replace` 原子写；预算台账 `s2_snapshots/_budget.json`（按运行日计数，留 60 天）。`local/` 已 gitignore，不提交 |
| 幂等 | 同一 asof 已有 `status=ok` 快照 → 直接复用，**零网络**；`partial` / `failed` → 重抓并覆盖 |
| 预算 | `STOCK_PLATFORM_S2_EM_BUDGET`（默认 **300**/自然日，Asia/Shanghai），跨重跑累计；超预算的源记 `budget_exceeded`，不抛异常 |
| 开关 | `STOCK_PLATFORM_S2_SNAPSHOT=0/1`；replay 预设或 pytest 下默认不联网（已落盘的快照仍可读） |
| fail-soft | 单源失败只标该源 `failed`；整体异常 → `status=failed`；S2 退回空池并带 reason；影子链与主链都不受影响（测试锁） |

数据源与字段口径（金额单位为**元**；涨跌幅、换手率、解禁比例都是**小数**）：

| 源 | 端点（经 `em_get`） | 字段 | PIT 口径 |
|----|--------------------|------|---------|
| `lhb` | datacenter `RPT_DAILYBILLBOARD_DETAILSNEW`，`TRADE_DATE=asof`，每页 500，最多 4 页 | `date,symbol,name,reason,net_buy,buy_amt,sell_amt,deal_amt,close,change_pct,turnover_rate` | 只保留 `TRADE_DATE==asof`；盘后才公布，只能用于 asof 次日入场 |
| `concept_rank` | push2 `clist` `fs=m:90+t:3`，按 `f62` 主力净流入排序，取前 100 | `code,name,kind,change_pct,main_net,lead_stock,lead_name` + `updatedAt` | vendor 当前快照；`updatedAt` 日期 == asof 才算 `pitOk` 进入 S2，否则记 `stale` 不用 |
| `industry_rank` | 同上，`fs=m:90+t:2` | 同上 | 同上 |
| `unlock` | datacenter `RPT_LIFT_STAGE`，`asof ≤ FREE_DATE ≤ asof+30` | `symbol,name,date,type,shares(万股),able_shares,ratio` | 取当前公告的日程，日程修订过就可能有前视，只用作软排除 |

S2 怎么用快照：热门概念（净流入为正的前 20）的领涨股记「概念龙头」；热门行业（前 10）记「板块资金流」；当日上榜记「龙虎榜窗口」。未来 30 日解禁比例 ≥5% 的票做软排除。流动性闸门照旧。仍然是 advisory，未过 `FACTOR_LIBRARY` 不进生产权重。

**回测不变**：walk-forward 回测不读快照，S2 在回测里仍恒空池，这是预期行为。不用当前快照回放历史，以免引入前视偏差。

**实测**（2026-11-06 00:5x，asof=2026-11-05，生产 market.db 截面 5218 只，跑在临时影子目录，没写生产 `local/shadow/`）：

- 每日东财请求 **4 次**（龙虎榜 1 + 概念排名 1 + 行业排名 1 + 解禁 1），远低于 300 上限；同日重跑 0 次
- 当日龙虎榜 69 条 / 63 只；概念、行业各 100 个板块，`updatedAt=2026-11-05 15:39:30+08:00` → `pitOk`；30 日解禁 158 条，其中 61 只 ≥5%
- S2 候选池 `ok` / 8 只；进终榜 **0 席**（见下）

可观测性：`DailyPipelineReport.shadowBoard.s2Snapshot`（快照状态、预算、各源计数、`s2PoolStatus` / `s2Candidates`）；`final_board_{asof}.json` 的 `schools.S2.snapshot`；`loop_health.shadowBoard.s2`（近 20 日落盘天数、S2 非空池天数/比例、逐日明细）。只有最新一天快照 `failed` / `corrupt` 时才加一条 `shadowS2Snapshot` **warn**，永不 fail/blocked。

**调度时点与 PIT**（推断，待首个生产日核对 `sources.*.pitOk`）：生产调度用 `-PrevSession`，asof=T-1。盘前 08:30 那次跑时板块排名的 `updatedAt` 还是 T-1 收盘，判 `pitOk` 并落 `ok` 快照；盘后 15:30 那次同一 asof 直接复用，零网络。如果盘前那次失败、盘后才首抓，板块排名 `updatedAt` 已是 T 日，会记 `stale` 不进 S2（快照 `partial`），只有龙虎榜 / 解禁生效。这是有意为之，不用非 PIT 数据。

**契约已补（2026-11-06，已签核）**：三个新 provider 方法登记在 [`../contracts/capability-matrix.md`](../contracts/capability-matrix.md)「全市场按日截面方法」（只给影子链用，不进路由矩阵）；快照 / 预算账 / 终榜 / 前向影子账本字段见 [`../contracts/datasets.md`](../contracts/datasets.md)「影子链产物」；ADR [0093](../architecture/0093-multi-strategy-shadow-board.md) 已追加增补段。

**P1 验收进展**：前向积累**起算日 asof=2026-11-05**（第一次真实生产落盘要等下一次调度运行），「20 个交易日内 S2 非空池比例 ≥60%」**待观察，未达标也未失败**，目前不到 1 个交易日样本。

**非空池 ≠ 入榜席位**：P1 只考核 S2 候选池有没有票。现行 Round2 仲裁 D 把学校优先级排在分数前（S3 > S4 > S5 > S2 > S1），S3/S4 会先把 10 席填满，所以 S2 有票也大概率 0 席，实测正是 0 席。席位问题归仲裁线（§S2-P0 / [`multi-strategy-final-board.md`](multi-strategy-final-board.md) §11），不算 P1 的验收项。

### S2-P2 有限历史回补（日期型数据）

- 回补龙虎榜、板块资金流 daykline 到**平台自有**只读存档（如 `local/s2_history.sqlite`，不提交；不写 `market.db`）。
- 回测里 S2 只读此存档，按 `asof` 严格截取；龙虎榜只用于 T+1 入场。
- 解禁日程按「可能有前视」标注到回测 `limitations`。

### S2-P3 概念成分

- 不用当前成分回放历史。只用 P1 积累的快照段做回测；在此之前，回测里 `concept_blocks` 一律视为不可用。

### S2-P4 新信号（涨停原因 / 连板）

- 先扩矩阵 + 契约 + ADR，再实现；新因子走 `FACTOR_LIBRARY` IC / 正交准入。

## 3. 验收标准

| 阶段 | 指标 | 门槛（初值，可在签核时调整） |
|------|------|------------------------------|
| P1 | 前向日 S2 非空池比例 | 开启后 20 个交易日内 ≥ 60%（**待观察**，起算日 asof=2026-11-05；看 `loop_health.shadowBoard.s2.nonEmptyPoolRatio`） |
| P1 | S2 取数失败是否阻塞主链 / 影子链 | 0 次（测试锁：`test_shadow_board_s2_snapshot.py`） |
| P1 | 东财请求是否全部经 `em_get` | 是（默认传输 `em_get`；测试锁 + 代码审） |
| P1 | 每日东财请求数 | ≤ 300（实测 4 次/日；同日重跑 0 次） |
| P2 | 回测期 S2 非空池天数占比 | ≥ 50%（仅回补覆盖区间内） |
| P2 + P0 | 回测 `schoolCoverage.S2.seats` | > 0，且分校绩效可单独报告 |
| 全程 | 影子是否写入生产账本 | 否（`FORBIDDEN_BASENAMES` 守卫） |
| 升级 | 进入 Y1 的前提 | 影子前向样本 ≥ `MIN_MEANINGFUL_SAMPLE`(20)，Y1 判 adopt，你签核 |

## 4. 是否需要 ADR

- P1 / P2：不改选股口径（仍是影子、仍 `excludedFromPerformance`），但新增数据存档与新 provider 方法，属于能力矩阵扩展 → 开工前补契约条目即可；新增全市场按日龙虎榜方法时补一段 ADR 0093 增补。
- P0 改仲裁、P4 新信号进入任何权重：**必须先写 ADR 并签核**。

## 5. 需要你决定

1. 是否先做 P0（仲裁方案 A 或 B 回测对照），还是先只做 P1 积累数据。
2. P1 每日东财请求预算上限（建议 ≤ 300 次 / 日）。
3. P2 回补存档放 `local/` 下的平台自有 SQLite 是否可接受。
