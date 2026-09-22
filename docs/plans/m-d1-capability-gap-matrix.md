# M-D1：能力矩阵 × Skill 端点缺口对照表

> **状态**：done（2026-09-17）  
> **范围**：对照表 only；**不写业务代码**、不扩矩阵、不接线。  
> **权威**：`packages/providers` `CAPABILITY_REGISTRY`（12 项）+ `docs/contracts/capability-matrix.md`  
> **输入**：[workspace-projects-capability-inventory.md](workspace-projects-capability-inventory.md) · [capability-domain-merge-roadmap.md](capability-domain-merge-roadmap.md)

---

## 1. 平台已有（矩阵内）

| 矩阵 id | 平台 Provider | Skill / 配方来源（摘要） | 限流 / 备胎备注 |
|---------|---------------|--------------------------|-----------------|
| `daily` | `astock_http` / `replay` / `engine_sqlite` / `tushare_http`；US/HK：`global_http` / `global_replay` | a-stock-data §1.1 mootdx / 东财 push2his；global §K 线 Yahoo+新浪 | CN live 东财走 `em_get`；engine 只读 `daily_price`；Tushare 非默认 |
| `adj_factor` | `astock_http` / `replay` | a-stock-data §1.4 `sina_adjust_factor` | **非** `em_get`；新浪 HTTP |
| `realtime` | `astock_http` / `replay`；US/HK global_* | a-stock-data §1.2 腾讯 / 东财 push2；global 新浪/腾讯/东财 | CN 主链 `em_get` 或腾讯配方；历史 asof 不得静默当 realtime |
| `minute` | `astock_http` / `replay` | 东财 push2his 分钟 | `em_get` |
| `depth5` | `astock_http` / `replay` | mootdx quotes / 东财 | 通达信优先于东财（Skill 总则） |
| `financial` | `astock_http` / `replay` | §6.4 新浪三表 / §6.1 mootdx finance | **非** `em_get`；非 PIT 时点表 |
| `full_minute` | `astock_http` / `replay` | 东财全市场当日分钟 | `em_get`；批量须调大 `EM_MIN_INTERVAL` |
| `fund_flow` | `astock_http` / `replay` | §4.5 `stock_fund_flow_120d` / §3.4 分钟流 | `em_get`；单位 **元**；备胎 `fund_flow_backup`（Skill） |
| `lhb` | `astock_http` / `replay` | §3.5 `dragon_tiger_board` | `em_get`；备胎 `dragon_tiger_backup`；**非**全市场日榜 §3.9 |
| `unlock` | `astock_http` / `replay` | §3.6 `lockup_expiry` | `em_get`；万股 |
| `sector_fund_flow` | `astock_http` / `replay` | §3.8 `board_fund_flow` | `em_get` |
| `news` | `astock_http` / `replay` | §5.1 东财个股新闻（轻量特征，非 LLM 摘要） | `em_get`；财联社/全球资讯**未**进矩阵 |

`engine_sqlite` 仅声明 `daily`；PIT 基本面表见 **M-D2 / ADR 0050**（未进矩阵）。

---

## 2. 可增量吸收（有序候选，CN 优先）

吸收顺序原则：先扩矩阵契约 → Provider + replay fixture → Workbench 接线；缺能力 fail-closed。

| 优先级 | 候选能力（建议矩阵 id） | Skill 端点 / 路径 | 字段要点 | 限流 / 备胎 | 备注 |
|--------|-------------------------|-------------------|----------|-------------|------|
| **P0（M-D3 建议）** | `concept_blocks` | a-stock-data §3.3 `eastmoney_concept_blocks` | 个股所属行业/概念列表 | `em_get` | 游资/板块叙事刚需；无新源类型 |
| P1 | `announcements` | §7.1 `cninfo_announcements` + 备胎 | 标题/日期/PDF URL | 巨潮为主；`announcements_backup` | 非东财；政策/解禁 Agent 可复用 |
| P1 | `market_lhb` | §3.9 `daily_dragon_tiger` | 全日上榜净买排名 | `em_get` | 与个股 `lhb` 区分；批量慎流控 |
| P2 | `northbound` | §3.2 `hsgt_realtime` | 沪/深股通分钟流向 | 同花顺；非 `em_get` | 需独立节流策略 |
| P2 | `hot_reason` | §3.1 `ths_hot_reason` | 强势股+题材标签 | 同花顺 | 与 `news` 互补 |
| P2 | `margin` | §4.1 `margin_trading` | 融资融券余额 | `em_get`；官方备胎 §12 | |
| P3 | `holder_num` / `block_trade` / `dividend` | §4.2–4.4 | 户数/大宗/分红 | `em_get` | 研究增强，非日用主路径 |
| P3 | `chip_distribution` | §4.6 本地计算 | 获利比例/成本区间 | 无 HTTP | 依赖日 K，可纯函数 |
| P3 | `eps_forecast` | §2.2 `ths_eps_forecast` | 一致预期 EPS | 同花顺 | 历史 asof 须告警（无 PIT） |
| P3 | `industry_rank` | §3.7 `industry_comparison` | 行业涨跌排名 | `em_get` | 可与 `sector_fund_flow` 并列 |

**US/HK 薄补（M-D5，暂缓接线）**

| 候选 | Skill | 矩阵现状 | 说明 |
|------|-------|----------|------|
| US/HK `financial` | global 东财三表 / Yahoo | 未声明 | 合规分级后仅补矩阵缺口 |
| US/HK `fund_flow` | global 东财 push2his | 未声明 | 勿套用 CN T+1 |
| 宏观/日历 | Treasury / Nasdaq 日历 | 不做深水区 | Later |

---

## 3. 明确不做（本阶段）

| Skill / 能力 | 原因 |
|--------------|------|
| iwencai 语义搜（§2.3） | 需 Key；非矩阵主链 |
| 期权（a-stock §9 / global CBOE） | 产品边界外；global 深水区 |
| SEC / FINRA / CFTC / EDGAR screener | global V2.0 深水区，刻意不搬 |
| 打板四池 / 异动监控（§8） | 交易风格工具；非研究主链优先 |
| 宏观 PBOC/NBS（§11） | 低频；非能力矩阵日用 |
| 平行 `pip install` Skill 仓 / 第二套东财客户端 | 红线：唯一权威 = providers + 矩阵 |
| TradingAgents `dataflows/a_stock.py` 回灌 | ADR 0009；对照用，禁止并入 |
| 引擎 westock 抓取链 / selections 双管线 | 只读 DB；非整仓 |

---

## 4. 下一刀（给 M-D3）

**选定候选**：`concept_blocks`（个股所属板块/概念归属）。

| 项 | 约定 |
|----|------|
| 契约 | 新 `docs/contracts/` 短文 + 必要时小 ADR |
| 矩阵 | 第 13 项；先声明再接线 |
| 实现 | `astock_http` + `replay` fixtures；一律 `em_get` |
| 验收 | 缺能力 409；零公网单测；Workbench 可选只读展示 |
| 非目标 | 全市场板块树 UI、iwencai、平行 Skill 运行时 |

---

## 5. 交叉链

- 路线图：M-D1 → M-D3 / M-D5  
- PIT 表暴露：ADR 0050（M-D2）  
- Skills 治理：[`docs/ops/skills-governance.md`](../ops/skills-governance.md)
