# 路线图与里程碑

> 大里程碑 → **minor**（或产品就绪时 **major**）tag  
> 小里程碑 → **patch** tag  
> 规则细节：[`versioning.md`](versioning.md)

状态图例：`planned` / `in_progress` / `done`

---

## 总览

| ID | 名称 | 类型 | 目标 tag | 状态 |
|----|------|------|----------|------|
| M0 | 工程架子 + 契约草稿 | 大 | `v0.1.0` | done |
| M0.1 | 空仓脚手架与 Git | 小 | `v0.0.1` | done |
| M0.2 | 契约草案评审定稿 | 小 | `v0.0.2` | done |
| M0.3 | CI 绿 + 文档交叉链接检查 | 小 | `v0.0.3` | done |
| M1 | 统一 A 股 Provider 包（可安装） | 大 | `v0.2.0` | done |
| M1.1 | providers 包骨架 + ticker 归一化 | 小 | `v0.1.1` | done |
| M1.2 | daily + realtime 适配器（录制回放测） | 小 | `v0.1.2` | done |
| M1.3 | 东财限流单点 + 能力矩阵注册 | 小 | `v0.1.3` | done |
| M2 | 工作台壳接入 Provider | 大 | `v0.3.0` | done |
| M2.1 | workbench 目录迁入最小可跑壳 | 小 | `v0.2.1` | done |
| M2.2 | 能力矩阵驱动路由（缺能力 fail-closed） | 小 | `v0.2.2` | done |
| M2.3 | 同标的/同日与批处理口径对齐验收 | 小 | `v0.2.3` | done |
| M3 | 选股 / PIT 回测内核迁入 | 大 | `v0.4.0` | done |
| M3.1 | lvrev / 分层闸门库化 | 小 | `v0.3.1` | done |
| M3.2 | PIT 回测权威路径 + 防未来函数测 | 小 | `v0.3.2` | done |
| M3.3 | 盘前简报批处理模式对接 | 小 | `v0.3.3` | done |
| M4 | 投研 Agent 插件化（无内嵌抓取） | 大 | `v0.5.0` | done |
| M4.1 | Agent 改调 packages/providers | 小 | `v0.4.1` | done |
| M4.2 | 工作台个股/复盘槽位挂载 | 小 | `v0.4.2` | done |
| M5 | 美港 Vendor + 市场策略表 | 大 | `v0.6.0` | done |
| M5.1 | MarketStrategy CN/US/HK 表 | 小 | `v0.5.1` | done |
| M5.2 | US/HK `normalize_symbol` | 小 | `v0.5.2` | done |
| M5.3 | global_replay fixtures Vendor | 小 | `v0.5.3` | done |
| M6 | 纸面执行安全模型（可选） | 大 | `v0.7.0` | done |
| M6.1 | 执行安全内核（broker-free） | 小 | `v0.6.1` | done |
| M6.2 | Paper ledger 草稿/提交/幂等 | 小 | `v0.6.2` | done |
| M6.3 | workbench `/api/paper/*` | 小 | `v0.6.3` | done |
| M7 | 产品收敛 / 上游仓归档说明 | 大 | `v1.0.0` | done |
| M7.1 | 上游归档清单 + v1 边界 ADR | 小 | `v0.7.1` | done |
| M7.2 | README / CONTRIBUTING / AGENTS 产品化 | 小 | `v0.7.2` | done |
| M7.3 | 发版清单 + 版本一致性脚本 | 小 | `v0.7.3` | done |
| M8 | A 股 live HTTP（可选） | 大 | `v1.1.0` | done |
| M8.1 | `AStockHttpProvider` via `em_get` | 小 | `v1.0.1` | done |
| M8.2 | workbench 可偏好 live daily/realtime | 小 | `v1.0.2` | done |
| M9 | 美港 live HTTP（可选） | 大 | `v1.2.0` | done |
| M9.1 | `GlobalHttpProvider`（Yahoo + 新浪） | 小 | `v1.1.1` | done |
| M9.2 | workbench 可偏好 `global_http` | 小 | `v1.1.2` | done |
| M10 | CN 交易日历（静态休市日） | 大 | `v1.3.0` | done |
| M10.1 | `TradingCalendar` + `cn_closed_days` | 小 | `v1.2.1` | done |
| M10.2 | MarketStrategy + timing 接线 | 小 | `v1.2.2` | done |
| M11 | Workbench 最小 UI | 大 | `v1.4.0` | done |
| M11.1 | 壳与首页 `GET /` | 小 | `v1.3.1` | done |
| M11.2 | 三区交互（矩阵/日K/纸面） | 小 | `v1.3.2` | done |
| M12 | Agent 轻量辩论图 | 大 | `v1.5.0` | done |
| M12.1 | 确定性 Bull/Bear/Risk 内核 | 小 | `v1.4.1` | done |
| M12.2 | `/api/debate/report` + UI | 小 | `v1.4.2` | done |
| M13 | US/HK 静态交易日历 | 大 | `v1.6.0` | done |
| M13.1 | us/hk closed days + 日历加载 | 小 | `v1.5.1` | done |
| M13.2 | MarketStrategy 验收 + 文档 | 小 | `v1.5.2` | done |
| M14 | 多市场纸面 timing | 大 | `v1.7.0` | done |
| M14.1 | timing market= + ADR 0019 | 小 | `v1.6.1` | done |
| M14.2 | PaperLedger + workbench market | 小 | `v1.6.2` | done |
| M15 | CN 日级资金流 | 大 | `v1.8.0` | done |
| M15.1 | fund_flow provider + matrix + ADR 0020 | 小 | `v1.7.1` | done |
| M15.2 | workbench fund-flow API + UI | 小 | `v1.7.2` | done |
| M16 | CN 龙虎榜 | 大 | `v1.9.0` | done |
| M16.1 | lhb provider + matrix + ADR 0021 | 小 | `v1.8.1` | done |
| M16.2 | workbench lhb API + UI | 小 | `v1.8.2` | done |
| M17 | CN 限售解禁 | 大 | `v1.10.0` | done |
| M17.1 | unlock provider + matrix + ADR 0022 | 小 | `v1.9.1` | done |
| M17.2 | workbench unlock API + UI | 小 | `v1.9.2` | done |
| M18 | CN 分钟 K | 大 | `v1.11.0` | done |
| M18.1 | minute provider + matrix + ADR 0023 | 小 | `v1.10.1` | done |
| M18.2 | workbench minute API + UI | 小 | `v1.10.2` | done |
| M19 | CN 五档盘口 | 大 | `v1.12.0` | done |
| M19.1 | depth5 provider + matrix + ADR 0024 | 小 | `v1.11.1` | done |
| M19.2 | workbench depth5 API + UI | 小 | `v1.11.2` | done |
| M20 | CN 财务报表 | 大 | `v1.13.0` | done |
| M20.1 | financial provider + matrix + ADR 0025 | 小 | `v1.12.1` | done |
| M20.2 | workbench financial API + UI | 小 | `v1.12.2` | done |
| M21 | CN 复权因子 | 大 | `v1.14.0` | done |
| M21.1 | adj_factor provider + matrix + ADR 0026 | 小 | `v1.13.1` | done |
| M21.2 | workbench adj-factor API + UI | 小 | `v1.13.2` | done |
| M22 | CN 全量分钟 | 大 | `v1.15.0` | done |
| M22.1 | full_minute provider + matrix + ADR 0027 | 小 | `v1.14.1` | done |
| M22.2 | workbench full-minute API + UI | 小 | `v1.14.2` | done |
| M23 | CN 复权套价 | 大 | `v1.16.0` | done |
| M23.1 | apply_adjust 内核 + ADR 0028 | 小 | `v1.15.1` | done |
| M23.2 | workbench daily-adjusted API + UI | 小 | `v1.15.2` | done |
| M24 | Universe + PIT 截面面板 | 大 | `v1.17.0` | done |
| M24.1 | universe + panel 内核 + ADR 0029 | 小 | `v1.16.1` | done |
| M25 | 盘前简报批处理 | 大 | `v1.18.0` | done |
| M26 | 工作台「今日推荐」 | 大 | `v1.19.0` | done |
| M27 | Recommend → PaperLedger | 大 | `v1.20.0` | done |
| M28 | Phase A 产品稳定收口 | 大 | `v2.0.0` | done |
| M29 | 日数据刷新 / full_minute 落盘 | 大 | `v2.1.0` | done |
| M30 | live 偏好模板 + 东财熔断 | 大 | `v2.2.0` | done |
| M31 | 运维健康检查 + Phase B 收口 | 大 | `v2.3.0` | done |
| M32 | 推荐绩效统计 | 大 | `v2.4.0` | done |
| M33 | 可选 LLM 辩论挂在 TopN 之后 | 大 | `v2.5.0` | done |
| M34 | 策略配置版本化 + 回测对比 + Phase C 收口 | 大 | `v2.6.0` | done |
| M35 | 执行端口抽象（Paper vs ExternalSim） | 大 | `v2.7.0` | done |
| M36 | 同花顺模拟盘适配器（mock / experimental） | 大 | `v2.8.0` | done |
| M37 | 风控闸门接到外部模拟 | 大 | `v2.9.0` | done |
| M38 | Phase D E2E 收口（recommend → ths_sim） | 大 | `v3.0.0` | done |
| M39 | 日用宇宙扩容 + 可读推荐理由 | 大 | `v3.1.0` | done |
| M40 | 定时 refresh→brief 日流水线 | 大 | `v3.2.0` | done |
| M41 | 板块资金流 / 新闻特征 | 大 | `v3.3.0` | done |
| M42 | 日历 2028+ + Task Scheduler/cron 运维包 | 大 | `v3.4.0` | done |
| M43 | （可选）组合回测加深 + 绩效对齐纸面成交 | 大 | `v3.5.0` | done |
| M44 | （可选）LLM 成本/质量控制 | 大 | `v3.6.0` | done |
| M45 | Workbench IA + 一键向导（刷新→推荐→纸面） | 大 | `v3.7.0` | planned |
| M46 | Phase E 日用稳定收口 | 大 | `v3.8.0` | planned |

> **说明**：M0 完成打 `v0.1.0`；其间小步用 `v0.0.x`。  
> M1 完成打 `v0.2.0`；M1 期间的小步在 `v0.1.x`（即 M0 大版本之后的 patch 线）。  
> 上表「目标 tag」列与阶段绑定；若插入额外小里程碑，只增加 patch，不跳过已规划的大 tag。  
> **Phase A（M24–M28）**：日更选股推荐 + 纸面闭环 → major `v2.0.0`。  
> **Phase B（M29–M31）**：日刷新落盘 + live 运维稳定 → `v2.1.0`–`v2.3.0`。  
> **Phase C（M32–M34）**：投研稳定（绩效 / 可选 LLM / 策略对比）→ `v2.4.0`–`v2.6.0`。  
> **Phase D（M35–M38）**：同花顺**模拟盘**外部 broker（默认仍 paper）→ `v2.7.0`–`v3.0.0`。  
> **Phase E（M39–M46）**：每日推荐真日用 + 数据/运维加固（可选投研/体验）→ `v3.1.0`–`v3.8.0`（不跳 `v4`）。

---

## M0 — 工程架子 + 契约草稿 → `v0.1.0`

**目标**：可协作的空产品仓；合并规则与契约可读；尚无行情业务。

### 小里程碑

#### M0.1 → `v0.0.1`（本阶段）

验收：

- [x] `main` 分支 Git 仓库
- [x] README / CONTRIBUTING / AGENTS / CHANGELOG / VERSION
- [x] `docs/ROADMAP.md`、`docs/versioning.md`
- [x] 架构 ADR + 三份契约草稿
- [x] `apps/workbench`、`packages/providers` 占位
- [x] `scripts/release_tag.ps1`
- [x] 注解 tag `v0.0.1`

#### M0.2 → `v0.0.2`

验收：

- [x] `docs/contracts/*` 字段表无「TBD」关键空洞（至少 daily / realtime / adj_factor）
- [x] 能力矩阵七项与 TSP 语义对齐说明写清
- [x] 市场策略：A 股规则表初稿（T+1、涨跌停、时区）
- [x] ADR 0002 记录冻结决策

#### M0.3 → `v0.0.3`

验收：

- [x] GitHub Actions 对 docs / 脚本做基础检查（`check_docs.ps1` + DryRun）
- [x] `release_tag.ps1 -DryRun` 文档示例可跑通（已存在 tag 时仅提示）
- [x] README / versioning 写明自检与 DryRun 流程

#### M0 完成 → `v0.1.0`

验收：上述小里程碑全部 done；CHANGELOG 汇总；ADR 无未决「阻塞合并」项。

- [x] M0.1 / M0.2 / M0.3 均 done
- [x] CHANGELOG 含 `0.1.0` 大里程碑节
- [x] 契约与 ADR 0001/0002 无阻塞项

---

## M1 — 统一 A 股 Provider → `v0.2.0`

**目标**：可 `pip install` 的 `packages/providers`；东财限流单点；与旧仓抓取去重启动。

### 小里程碑

#### M1.1 → `v0.1.1`

验收：

- [x] `packages/providers` 可 `pip install -e ".[dev]"`
- [x] `normalize_symbol` / `exchange_prefix` / `is_bse_symbol`
- [x] 拒绝港美与中文名；`920xxx` → `bj`
- [x] pytest 覆盖上述行为；CI `providers` job
- [x] ADR 0003

#### M1.2 → `v0.1.2`

验收：

- [x] `ReplayProvider.get_daily` / `get_realtime` + fixtures
- [x] 归一化：手/元/小数制；`pct_unit=percent` 显式转换
- [x] 港美代码在取数前被 `normalize_symbol` 拒绝
- [x] ADR 0004

#### M1.3 → `v0.1.3`

验收：

- [x] `em_get` / `EastmoneyClient` 串行限流 + 拒绝非东财 URL
- [x] `build_capability_matrix` + 七项注册表；`replay` usable / `astock_http` pending
- [x] 文档 `docs/contracts/eastmoney-http.md`：禁止裸东财请求
- [x] ADR 0005

验收（大 M1 → `v0.2.0`）：

- [x] daily + realtime 契约测试（录制回放）通过
- [x] ticker 归一化 + 非 A 股拒绝
- [x] 文档声明：新代码禁止直连东财 URL
- [x] M1.1 / M1.2 / M1.3 全部 done；CHANGELOG 含 `0.2.0` 节

---

## M2 — 工作台壳 → `v0.3.0`

**目标**：最小可运行 workbench 只通过能力矩阵消费 Provider。

### 小里程碑

#### M2.1 → `v0.2.1`

验收：

- [x] `apps/workbench` 可 `pip install -e` + FastAPI 壳
- [x] `/health`、`/api/settings/capability-matrix`
- [x] `/api/market/daily` / `realtime` 经 `resolve(capability)`
- [x] pytest + ADR 0006

#### M2.2 → `v0.2.2`

验收：

- [x] 缺 minute 等能力时 API **409** fail-closed（矩阵细节）
- [x] 通用路径无硬编码单一数据源品牌（路由源码扫描 + 响应断言）
- [x] `PUT /api/settings/preferences` 不绕过 usable
- [x] ADR 0007

#### M2.3 → `v0.2.3`

验收：

- [x] 同标的/同日：API daily 与直接 `ReplayProvider.get_daily` 字段一致

验收（大）：

- [x] 通用路径无硬编码单一数据源品牌
- [x] 缺 minute 等能力时 UI/API fail-closed
- [x] M2.1 / M2.2 / M2.3 全部 done；CHANGELOG 含 `0.3.0` 节

---

## M3 — 选股回测内核 → `v0.4.0`

**目标**：lvrev / PIT 回测权威路径在本仓；engine 旧路径标记为参考。

### 小里程碑

#### M3.1 → `v0.3.1`

验收：

- [x] `packages/research` 可安装
- [x] `score_lvrev` / `apply_entry_gates` / `apply_risk_gates`
- [x] pytest 覆盖（迁自 engine 语义）
- [x] ADR 0008

#### M3.2 → `v0.3.2`

验收：

- [x] `run_pit_long_only`：T 信号 / T+1 open 成交
- [x] 防未来函数列护栏测试

#### M3.3 → `v0.3.3`

验收：

- [x] `score_cross_section_csv` + CLI `stock-platform-score`

验收（大）：

- [x] M3.1–M3.3 done；CHANGELOG 含 `0.4.0`

---

## M4 — Agent 插件 → `v0.5.0`

**目标**：研报图不自带 HTTP 抓取；历史日未来函数护栏保留。

### 小里程碑

#### M4.1 → `v0.4.1`

验收：

- [x] `packages/agents` 可安装（`stock-platform-agents`）
- [x] `ResearchAgentPlugin` / `ReviewAgentPlugin` 仅经注入的 `MarketDataProvider`
- [x] 历史 `asof` 跳过 realtime 并告警；`normalize_symbol` 拒港美
- [x] pytest + CI `agents` job；ADR 0009

#### M4.2 → `v0.4.2`

验收：

- [x] workbench `GET /api/research/report`、`GET /api/review/report`
- [x] 路由经 `resolve("daily")`；无内嵌东财 URL

验收（大）：

- [x] M4.1–M4.2 done；CHANGELOG 含 `0.5.0`

---

## M5 — 美港 → `v0.6.0`

**目标**：独立市场策略；不复用 A 股涨跌停/T+1 假设。

### 小里程碑

#### M5.1 → `v0.5.1`

验收：

- [x] `get_market_strategy`：CN/US/HK 时区、会话、settle、limit
- [x] US/HK `buy_to_sell_delay_days=0` 且 `has_limits=False`
- [x] ADR 0010；`market-strategy.md` 美港表定稿

#### M5.2 → `v0.5.2`

验收：

- [x] `normalize_symbol(..., market="US"|"HK")`
- [x] CN 路径继续拒绝港美形态

#### M5.3 → `v0.5.3`

验收：

- [x] `GlobalReplayProvider` + fixtures（AAPL / 00700）
- [x] 能力矩阵注册 `global_replay` / `global_http`(pending)

验收（大）：

- [x] M5.1–M5.3 done；CHANGELOG 含 `0.6.0`

---

## M6 — 纸面执行 → `v0.7.0`

**目标**：吸收 V2 审查结论（信号新鲜度、事务化意图、草稿/激活）；默认仅模拟。

### 小里程碑

#### M6.1 → `v0.6.1`

验收：

- [x] `packages/execution`：timing / transactional / profile / lifecycle / admission
- [x] paper-only 闸门；市场态 ≠ 执行态；ADR 0011

#### M6.2 → `v0.6.2`

验收：

- [x] `PaperLedger`：decision_only 清订单、窗口外禁补单、draftId 幂等

#### M6.3 → `v0.6.3`

验收：

- [x] workbench `/api/paper/status|drafts|strategies/*`
- [x] 无 live 开关；显式激活

验收（大）：

- [x] M6.1–M6.3 done；CHANGELOG 含 `0.7.0`

---

## M7 — v1.0.0

**目标**：单一产品可发布；上游参考仓归档说明齐全；版本/文档/CI 一致。

### 小里程碑

#### M7.1 → `v0.7.1`

验收：

- [x] `docs/upstream-archive.md` 上游总表 + 红线 + 未迁入清单
- [x] ADR 0012：v1.0 产品边界

#### M7.2 → `v0.7.2`

验收：

- [x] README / CONTRIBUTING / AGENTS 按 v1 交付面改写（去掉「架子」表述）

#### M7.3 → `v0.7.3`

验收：

- [x] `docs/release-checklist.md` + `scripts/check_versions.ps1` + CI 接入

验收（大）：

- [x] M7.1–M7.3 done；CHANGELOG 含 `1.0.0`；`release_tag -Kind major`

---

## M8 — A 股 live HTTP → `v1.1.0`

**目标**：可选 live 日 K / 实时；默认仍 replay；东财只走 `em_get`。

### 小里程碑

#### M8.1 → `v1.0.1`

验收：

- [x] `AStockHttpProvider`（push2his kline + push2 quote）
- [x] 单测注入 `get_json`；ADR 0013；矩阵 `astock_http` usable

#### M8.2 → `v1.0.2`

验收：

- [x] workbench 可 `preferences` 切到 `astock_http`（默认仍 replay）

验收（大）：

- [x] M8.1–M8.2 done；CHANGELOG 含 `1.1.0`

---

## M9 — 美港 live HTTP → `v1.2.0`

**目标**：可选 US/HK live 日 K / 实时；默认仍 replay；不经 `em_get`；仅 daily+realtime。

### 小里程碑

#### M9.1 → `v1.1.1`

验收：

- [x] `GlobalHttpProvider`（Yahoo chart 日 K + 新浪实时）
- [x] 可注入 `get_json` / `get_text`；ADR 0014；矩阵 `global_http` usable

#### M9.2 → `v1.1.2`

验收：

- [x] workbench 注册 `global_http`（按标的 US/HK 分发）；preferences 可切；默认仍 replay

验收（大）：

- [x] M9.1–M9.2 done；CHANGELOG 含 `1.2.0`

---

## M10 — CN 交易日历 → `v1.3.0`

**目标**：静态上交所休市日替换「只跳周末」；纸面 timing 与 MarketStrategy 共用；US/HK 假日表见 M13。

### 小里程碑

#### M10.1 → `v1.2.1`

验收：

- [x] `TradingCalendar` + `data/cn_closed_days.txt`（2024–2027）
- [x] ADR 0015；单测覆盖春节/国庆跨越

#### M10.2 → `v1.2.2`

验收：

- [x] `MarketStrategy.is_trading_day` 与 `timing` 走 CN 日历
- [x] `completed_bar_cutoff` 回退跳过非交易日；execution 依赖 providers

验收（大）：

- [x] M10.1–M10.2 done；CHANGELOG 含 `1.3.0`

---

## M11 — Workbench 最小 UI → `v1.4.0`

**目标**：单页操作台调用既有 API；不引入 SPA / 实盘。

### 小里程碑

#### M11.1 → `v1.3.1`

验收：

- [x] Jinja2 `GET /` + `/static`；ADR 0016
- [x] 页面含 `#capability` / `#daily` / `#paper` 锚点

#### M11.2 → `v1.3.2`

验收：

- [x] JS 拉取矩阵 / 日 K / 纸面；409 可见；可选切 daily 偏好

验收（大）：

- [x] M11.1–M11.2 done；CHANGELOG 含 `1.4.0`

---

## M12 — Agent 轻量辩论图 → `v1.5.0`

**目标**：确定性 Bull/Bear/Risk 辩论；零 LLM / 零内嵌抓取；仅经 providers。

### 小里程碑

#### M12.1 → `v1.4.1`

验收：

- [x] `build_debate_report` + ADR 0017
- [x] 上涨偏 Buy、下跌偏 Sell 单测

#### M12.2 → `v1.4.2`

验收：

- [x] `DebateAgentPlugin` + `GET /api/debate/report`
- [x] UI `#debate` 区

验收（大）：

- [x] M12.1–M12.2 done；CHANGELOG 含 `1.5.0`

---

## M13 — US/HK 静态交易日历 → `v1.6.0`

**目标**：美港静态休市日对标 CN；MarketStrategy 自动生效；不改 CN 纸面 timing。

### 小里程碑

#### M13.1 → `v1.5.1`

验收：

- [x] `us_closed_days.txt` / `hk_closed_days.txt` + 通用加载
- [x] ADR 0018；US/HK 假日单测

#### M13.2 → `v1.5.2`

验收：

- [x] `MarketStrategy` US/HK 假日断言；文档更新

验收（大）：

- [x] M13.1–M13.2 done；CHANGELOG 含 `1.6.0`

---

## M14 — 多市场纸面 timing → `v1.7.0`

**目标**：纸面 execution timing 按 CN/US/HK 日历与本地时区计算；默认仍 CN。

### 小里程碑

#### M14.1 → `v1.6.1`

验收：

- [x] `timing` helpers 接受 `market=`；`market_now` / `daily_bar_final_at`
- [x] US Jul4 / HK 春节跨越 + US ET cutoff 单测；ADR 0019

#### M14.2 → `v1.6.2`

验收：

- [x] `PaperLedger` / workbench `/api/paper/*` 可选 `market`（默认 CN）
- [x] 草稿落盘 `marketId`；execution README 一句

验收（大）：

- [x] M14.1–M14.2 done；CHANGELOG 含 `1.7.0`

---

## M15 — CN 日级资金流 → `v1.8.0`

**目标**：个股日级资金流（主力/大小单净流入，元）；经 `em_get`；默认 replay；CI 零公网。

### 小里程碑

#### M15.1 → `v1.7.1`

验收：

- [x] 能力矩阵第八项 `fund_flow`；契约字段；ADR 0020
- [x] `ReplayProvider` / `AStockHttpProvider.get_fund_flow` + fixtures / 注入测

#### M15.2 → `v1.7.2`

验收：

- [x] workbench `GET /api/market/fund-flow`；默认偏好 replay；可选 UI

验收（大）：

- [x] M15.1–M15.2 done；CHANGELOG 含 `1.8.0`

---

## M16 — CN 龙虎榜 → `v1.9.0`

**目标**：个股龙虎榜（上榜记录 + 买卖席位 TOP5 + 机构动向，元）；经 `em_get` datacenter-web；默认 replay；CI 零公网。

### 小里程碑

#### M16.1 → `v1.8.1`

验收：

- [x] 能力矩阵第九项 `lhb`；契约字段；ADR 0021
- [x] `ReplayProvider` / `AStockHttpProvider.get_lhb` + fixtures / 注入测；空窗口不崩

#### M16.2 → `v1.8.2`

验收：

- [x] workbench `GET /api/market/lhb`；默认偏好 replay；可选 UI

验收（大）：

- [x] M16.1–M16.2 done；CHANGELOG 含 `1.9.0`

---

## M17 — CN 限售解禁 → `v1.10.0`

**目标**：个股限售解禁日历（历史解禁 + 未来 N 天待解禁，万股）；经 `em_get` datacenter-web；默认 replay；CI 零公网。

### 小里程碑

#### M17.1 → `v1.9.1`

验收：

- [x] 能力矩阵第十项 `unlock`；契约字段；ADR 0022
- [x] `ReplayProvider` / `AStockHttpProvider.get_unlock` + fixtures / 注入测；空窗口不崩

#### M17.2 → `v1.9.2`

验收：

- [x] workbench `GET /api/market/unlock`；默认偏好 replay；可选 UI

验收（大）：

- [x] M17.1–M17.2 done；CHANGELOG 含 `1.10.0`

---

## M18 — CN 分钟 K → `v1.11.0`

**目标**：个股分钟 K（1m/5m/15m/30m/60m；北京墙钟 naive）；经 `em_get` push2his kline；默认 replay；CI 零公网；激活矩阵既有 `minute`。

### 小里程碑

#### M18.1 → `v1.10.1`

验收：

- [x] 契约字段 + ADR 0023；`ReplayProvider` / `AStockHttpProvider.get_minute` + fixtures / 注入测
- [x] `replay` / `astock_http` 声明 `minute`；拒 tz；空 klines 不崩

#### M18.2 → `v1.10.2`

验收：

- [x] workbench `GET /api/market/minute` 真正取数；默认偏好 replay；可选 UI
- [x] 有候选时不再 409；`depth5` 等仍 fail-closed

验收（大）：

- [x] M18.1–M18.2 done；CHANGELOG 含 `1.11.0`

---

## M19 — CN 五档盘口 → `v1.12.0`

**目标**：个股五档盘口（买/卖各五档价量，量=手）；经 `em_get` push2 stock/get；默认 replay；CI 零公网；激活矩阵既有 `depth5`。

### 小里程碑

#### M19.1 → `v1.11.1`

验收：

- [x] 契约字段 + ADR 0024；`ReplayProvider` / `AStockHttpProvider.get_depth5` + fixtures / 注入测
- [x] `replay` / `astock_http` 声明 `depth5`；空 data / 缺 fixture 不崩

#### M19.2 → `v1.11.2`

验收：

- [x] workbench `GET /api/market/depth5` 真正取数；默认偏好 replay；可选 UI
- [x] 有候选时不再 409；`financial` 等仍 fail-closed

验收（大）：

- [x] M19.1–M19.2 done；CHANGELOG 含 `1.12.0`

---

## M20 — CN 财务报表 → `v1.13.0`

**目标**：个股财报三表（利润表/资产负债表/现金流量表）；经新浪 HTTP（非 `em_get`）；默认 replay；CI 零公网；激活矩阵既有 `financial`。

### 小里程碑

#### M20.1 → `v1.12.1`

验收：

- [x] 契约字段 + ADR 0025；`ReplayProvider` / `AStockHttpProvider.get_financial` + fixtures / 注入测
- [x] `replay` / `astock_http` 声明 `financial`；空 report / 缺 fixture 不崩

#### M20.2 → `v1.12.2`

验收：

- [x] workbench `GET /api/market/financial` 真正取数；默认偏好 replay；可选 UI
- [x] 有候选时不再 409；`adj_factor` / `full_minute` 等仍 fail-closed

验收（大）：

- [x] M20.1–M20.2 done；CHANGELOG 含 `1.13.0`

---

## M21 — CN 复权因子 → `v1.14.0`

**目标**：个股复权因子（qfq 默认 / hfq 可选）；经新浪 HTTP（非 `em_get`）；默认 replay；CI 零公网；激活矩阵既有 `adj_factor`。

### 小里程碑

#### M21.1 → `v1.13.1`

验收：

- [x] 契约字段 + ADR 0026；`ReplayProvider` / `AStockHttpProvider.get_adj_factor` + fixtures / 注入测
- [x] `replay` / `astock_http` 声明 `adj_factor`；空 data / 缺 fixture 不崩

#### M21.2 → `v1.13.2`

验收：

- [x] workbench `GET /api/market/adj-factor` 真正取数；默认偏好 replay；可选 UI
- [x] 有候选时不再 409；`full_minute` 等仍 fail-closed

验收（大）：

- [x] M21.1–M21.2 done；CHANGELOG 含 `1.14.0`

---

## M22 — CN 全量分钟 → `v1.15.0`

**目标**：个股当日 1m 批量（宇宙修复语义）；经 `em_get` push2his kline `klt=1`；默认 replay；CI 零公网；激活矩阵既有 `full_minute`；与多频 `minute` 严格区分。

### 小里程碑

#### M22.1 → `v1.14.1`

验收：

- [x] 契约字段 + ADR 0027；`ReplayProvider` / `AStockHttpProvider.get_full_minute` + fixtures / 注入测
- [x] `replay` / `astock_http` 声明 `full_minute`；空 klines / 缺 fixture 不崩；不回退 `minute_*`

#### M22.2 → `v1.14.2`

验收：

- [x] workbench `GET /api/market/full-minute` 真正取数；默认偏好 replay；可选 UI
- [x] 有候选时不再 409

验收（大）：

- [x] M22.1–M22.2 done；CHANGELOG 含 `1.15.0`

---

## M23 — CN 复权套价 → `v1.16.0`

**目标**：用已有 `adj_factor` 对不复权日 K 做确定性套价（qfq 除 / hfq 乘）；不新增能力 id；默认 replay；CI 零公网。

### 小里程碑

#### M23.1 → `v1.15.1`

验收：

- [x] `apply_adjust` + ADR 0028；qfq/hfq 方向与空因子 fail-closed 单测
- [x] 不新增能力 id；无 HTTP / 无 pandas

#### M23.2 → `v1.15.2`

验收：

- [x] workbench `GET /api/market/daily-adjusted`；默认偏好 replay；可选 UI
- [x] 路由 `resolve("daily")` + `resolve("adj_factor")`

验收（大）：

- [x] M23.1–M23.2 done；CHANGELOG 含 `1.16.0`

---

## Phase A — 产品稳定（M24–M28）→ `v2.0.0`

**产品目标**：日更选股推荐 + 纸面交易闭环（SIMULATE；无同花顺/实盘；无 LLM；无 SPA）。

**状态**：done（`v2.0.0`）

---

## M24 — Universe + PIT 截面面板 → `v1.17.0`

**目标**：CN 股票宇宙（config/fixtures；空则 fail-closed）；按交易日 as-of 经能力矩阵 providers 构建 PIT 截面面板（daily / 可选 adj_factor / 可选 fund_flow）。

### 小里程碑

#### M24.1 → `v1.16.1`

验收：

- [x] `load_universe` + `build_cross_section_panel`；ADR 0029
- [x] 注入 provider 单测；零公网；空宇宙 fail-closed

验收（大）：

- [x] CSV 兼容导出；CHANGELOG 含 `1.17.0`

---

## M25 — 盘前简报批处理 → `v1.18.0`

**目标**：`score_lvrev` + `apply_entry_gates` → TopN 简报；CLI 与/或 `GET /api/research/brief`；确定性 fixtures。

验收：

- [x] `build_premarket_brief`（含 reasons）
- [x] CLI / API；默认 replay；CI 零公网

---

## M26 — 工作台「今日推荐」→ `v1.19.0`

**目标**：UI「今日推荐」+ TopN 分数/理由；链接既有行情面板。

验收：

- [x] `#recommend` UI + API 接线
- [x] `test_app` 断言静态资源调用 brief API

---

## M27 — Recommend → PaperLedger → `v1.20.0`

**目标**：一键 / API：brief TopN → paper draft（SIMULATE only）；复用 timing/window/freshness；默认 CN。

验收：

- [x] `POST` brief→paper；无 liveTradingEnabled
- [x] UI 一键；需 active strategy

---

## M28 — Phase A 收口 → `v2.0.0`

**目标**：ROADMAP Phase A done；CHANGELOG major；upstream-archive / README；全量 pytest；`release_tag -Kind major`。

验收：

- [x] Phase A 勾选完成；CHANGELOG `2.0.0`
- [x] 全量 pytest 绿；tag `v2.0.0` push

---

## Phase B — 运维稳定（M29–M31）→ `v2.3.0`

**产品目标**：日数据自动刷新落盘 + 可靠 live 运维（仍默认 replay；SIMULATE；无同花顺/实盘；无 LLM；无 SPA）。

**状态**：done（`v2.3.0`）

---

## M29 — 日数据刷新 / full_minute 落盘 → `v2.1.0`

**目标**：宇宙级 `daily` / `adj_factor` / `fund_flow` / `full_minute` 刷新到本地路径；重试 + 失败报告；CI 零公网。

验收：

- [x] `run_refresh` + `stock-platform-refresh`；ReplayTransport 文件名
- [x] `STOCK_PLATFORM_REFRESH_DIR` / `--out`；`manifest.json` + `latest.json`
- [x] ADR 0030；注入假 provider 单测

---

## M30 — live 偏好模板 + 节流/熔断 → `v2.2.0`

**目标**：成套 CN/美港 live 预设（非默认）；文档化并硬化 `EM_MIN_INTERVAL` + 连续失败熔断。

验收：

- [x] `PREFERENCE_PRESETS`：`replay` / `cn_astock_http` / `us_hk_global_http`
- [x] workbench `GET/POST /api/settings/presets*`；UI 选择器
- [x] `EastmoneyClient` 熔断 + `snapshot()`；ADR 0031；`eastmoney-http.md`

---

## M31 — 运维健康检查 + Phase B 收口 → `v2.3.0`

**目标**：`/api/ops/health` + fixture 录制文档；Phase B CHANGELOG/ROADMAP 收口。

验收：

- [x] `GET /api/ops/health`（保留 `/health`）；可选 last_refresh
- [x] [`docs/ops/refresh-and-fixtures.md`](ops/refresh-and-fixtures.md)；ADR 0032
- [x] 全量 pytest；tag `v2.3.0`

---

## Phase C — 投研稳定（M32–M34）→ `v2.6.0`

**产品目标**：推荐质量可迭代与复盘——绩效统计、TopN 后可选 LLM 辩论（默认仍确定性）、策略配置版本化 + 轻量 PIT 回测对比。仍纸面 SIMULATE；默认 replay；无同花顺；无 SPA。

**状态**：done（`v2.6.0`）

计划见：`C:\Users\63516\.cursor\plans\phase_c_research_stable_20260914.plan.md`

---

## M32 — 推荐绩效统计 → `v2.4.0`

**目标**：已结算推荐决策 JSONL 日志 + 持有期收益 / 方向正确率等指标；CLI 与 `GET /api/research/performance`；薄工作台面板。

验收：

- [x] JSONL schema + `compute_performance`（`direction_accuracy` / `avg_return` / `up_rate` 口径文档化）
- [x] CLI `stock-platform-performance`；API + `#performance` UI
- [x] ADR 0033；确定性 fixtures 单测

---

## M33 — 可选 LLM 辩论 → `v2.5.0`

**目标**：M12 确定性辩论仍为默认；可选 LLM 路径挂在 TopN 之后；缺依赖/密钥 fail-closed；数据仅经 providers。

验收：

- [x] Soft import / `[llm]` extra；默认 deterministic
- [x] TopN 后辩论 API；mocked LLM 单测；ADR 0034

---

## M34 — 策略配置版本化 + 回测对比 + Phase C 收口 → `v2.6.0`

**目标**：版本化策略 JSON；两配置经 `run_pit_long_only` 对比；API/UI 入口；Phase C CHANGELOG/ROADMAP 收口。

验收：

- [x] 策略配置加载 + compare；fixture panel 单测；ADR 0035
- [x] 全量 pytest；tag `v2.6.0`；Phase C done

---

## Phase D — 同花顺模拟盘（M35–M38）→ `v3.0.0`

**产品目标**：推荐 → 外部 **模拟** broker（同花顺纸面/模拟，非实盘）。默认仍内部 PaperLedger；`STOCK_PLATFORM_BROKER=ths_sim` 显式 opt-in。无稳定公开 THS 交易 API 时交付端口 + mock + experimental 扩展点。

**状态**：done（`v3.0.0`）

计划见：`C:\Users\63516\.cursor\plans\phase_d_ths_sim_20260914.plan.md`

---

## M35 — 执行端口抽象 → `v2.7.0`

**目标**：`BrokerPort` / `PaperBroker` / `ExternalSimBroker`；订单/成交/持仓/账户契约；默认 paper；env `STOCK_PLATFORM_BROKER`。

验收：

- [x] 契约 + 工厂；paper 路径行为不变
- [x] ADR 0036；禁止 liveTradingEnabled / 实盘券商

---

## M36 — 同花顺模拟盘适配器 → `v2.8.0`

**目标**：`ThsSimBroker` + 可注入 transport；默认 mock fixtures；缺凭据 fail-closed；experimental HTTP 不宣称生产就绪。

验收：

- [x] Mock CI 零公网；README / `.env.example`（`STOCK_PLATFORM_THS_*`）
- [x] ADR 0037；不默认启用；无「实盘」UI 开关

---

## M37 — 风控闸门接到外部模拟 → `v2.9.0`

**目标**：timing / freshness / window / idempotency / admission 复用于 `ths_sim`；失败 refuse。

验收：

- [x] 闸门单测；仍 SIMULATE；ADR 0038

---

## M38 — Phase D E2E 收口 → `v3.0.0`

**目标**：brief TopN → ths_sim draft/orders → fill（mock）→ 可选绩效；workbench 只读 broker 状态；major CHANGELOG；全量 pytest。

验收：

- [x] E2E + `#broker` 面板；Phase D ROADMAP done
- [x] `release_tag -Kind major`；push `--follow-tags`

---

## Phase E / 后续 — 每日日用稳定（M39–M46）→ `v3.8.0`

**产品目标**：把「今日推荐」从 demo 做成可坚持的真日用——更大宇宙、定时 refresh→brief、可读理由；加固板块/新闻数据与日历/调度运维；可选加深投研与工作台向导。默认仍 paper + replay；SIMULATE；无 SPA；无真实券商；东财经 `em_get`；矩阵 fail-closed。

**状态**：in_progress（已完成 M39–M44 → `v3.6.0`）

**详细设计**：`C:\Users\63516\.cursor\plans\phase_e_daily_use_roadmap_20260914.plan.md`

**非目标**：同花顺真实 HTTP transport；SPA；默认 live / 默认 `ths_sim`；真实券商 / `liveTradingEnabled=true`。

**Backlog（deferred，非本 Phase 活动项）**：

- **BL-THS-REAL**：同花顺真实 transport —— 待稳定合规接入方式再单独立项；保持现有 mock / experimental 扩展点，不阻塞 Phase E。

---

## M39 — 日用宇宙扩容 + 可读推荐理由 → `v3.1.0`

**目标**：配置化日用宇宙（CI 仍小 fixture）；brief reasons 对人可读；`#recommend` 展示摘要。

验收：

- [x] 日用宇宙配置样例 + 文档；空宇宙 fail-closed
- [x] brief API/CLI 可读 `reasons`；单测；默认 replay
- [x] ADR（建议 0040）；CHANGELOG `3.1.0`

---

## M40 — 定时 refresh→brief 日流水线 → `v3.2.0`

**目标**：可调度流水线 refresh→brief（产物 + 退出码）；不仅人手 CLI。

验收：

- [x] 日流水线脚本/CLI 在 replay 下 E2E；失败 fail-closed
- [x] 运维文档约定路径；ADR（建议 0041）；CHANGELOG `3.2.0`

---

## M41 — 板块资金流 / 新闻特征 → `v3.3.0`

**目标**：能力矩阵新增板块资金流与新闻特征；经 `em_get`（东财）；默认 replay；CI 零公网。

验收：

- [x] 契约 + replay/http 注入测；缺能力 fail-closed
- [x] 可选 workbench API/薄 UI；ADR；CHANGELOG `3.3.0`

---

## M42 — 日历 2028+ + Task Scheduler/cron 运维包 → `v3.4.0`

**目标**：静态休市日维护到 2028+；Windows Task Scheduler / cron 可复制运维包（调度 M40 流水线）。

验收：

- [x] CN（及必要时 US/HK）2028+ 休市日 + 单测
- [x] `docs/ops/` 调度安装步骤 + 包装脚本/XML 样例；CHANGELOG `3.4.0`

---

## M43 —（可选）组合回测加深 + 绩效对齐纸面成交 → `v3.5.0`

**目标**：更接近组合持仓的 PIT 回测；绩效日志可与 paper fills 自动对齐。可整段 `deferred`。

验收：

- [x] 组合级回测指标范围经 ADR 冻结；CLI/API 之一 + 单测
- [x] 纸面成交 → 绩效回填路径；CHANGELOG `3.5.0`

---

## M44 —（可选）LLM 成本/质量控制 → `v3.6.0`

**目标**：可选 LLM 预算/截断/降级到确定性辩论；默认仍 deterministic。可整段 `deferred`。

验收：

- [x] 预算/降级 mock 单测；文档费用护栏；CHANGELOG `3.6.0`

---

## M45 — Workbench IA + 一键向导 → `v3.7.0`

**目标**：整理工作台分区；一键「刷新→推荐→纸面」；仍 Jinja/静态，不做 SPA。

验收：

- [ ] 向导路径 replay E2E 或 `test_app` 断言；无 live 默认文案
- [ ] CHANGELOG `3.7.0`；ADR（建议 0045）

---

## M46 — Phase E 日用稳定收口 → `v3.8.0`

**目标**：Phase E 勾选完成；README/ops 日用路径写清；全量 pytest；**minor** `v3.8.0`（不打 `v4`）。

验收：

- [ ] M39–M42 done；M43–M45 已做或 ROADMAP 标 `deferred`
- [ ] CHANGELOG `3.8.0`；`release_tag -Kind minor`；全量 pytest 绿

---

## 进度维护

每完成一个小/大里程碑：

1. 勾选本文件验收项  
2. 更新 `CHANGELOG.md`  
3. 更新 `VERSION`  
4. 运行 `scripts/release_tag.ps1` 打对应 tag  
5. （可选）推送 `git push origin main --tags`
