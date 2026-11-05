# S2 事件/主题数据源规划（只规划，不实现抓取）

> 状态：**规划草案**（2026-11-05）。相关：ADR [`0093`](../architecture/0093-multi-strategy-shadow-board.md) · 契约 [`multi-strategy-shadow.md`](../contracts/multi-strategy-shadow.md) · 计划 [`multi-strategy-final-board.md`](multi-strategy-final-board.md) §11/§12 · 治理 [`ops/skills-governance.md`](../ops/skills-governance.md)
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
| P1 | 前向日 S2 非空池比例 | 开启后 20 个交易日内 ≥ 60% |
| P1 | S2 取数失败是否阻塞主链 / 影子链 | 0 次（测试锁） |
| P1 | 东财请求是否全部经 `em_get` | 是（测试锁 / 代码审） |
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
