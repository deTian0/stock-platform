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
| M4 | 投研 Agent 插件化（无内嵌抓取） | 大 | `v0.5.0` | in_progress |
| M4.1 | Agent 改调 packages/providers | 小 | `v0.4.1` | done |
| M4.2 | 工作台个股/复盘槽位挂载 | 小 | `v0.4.2` | planned |
| M5 | 美港 Vendor + 市场策略表 | 大 | `v0.6.0` | planned |
| M6 | 纸面执行安全模型（可选） | 大 | `v0.7.0` | planned |
| M7 | 产品收敛 / 上游仓归档说明 | 大 | `v1.0.0` | planned |

> **说明**：M0 完成打 `v0.1.0`；其间小步用 `v0.0.x`。  
> M1 完成打 `v0.2.0`；M1 期间的小步在 `v0.1.x`（即 M0 大版本之后的 patch 线）。  
> 上表「目标 tag」列与阶段绑定；若插入额外小里程碑，只增加 patch，不跳过已规划的大 tag。

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

- [ ] workbench `GET /api/research/report`、`GET /api/review/report`
- [ ] 路由经 `resolve("daily")`；无内嵌东财 URL

验收（大）：

- [ ] M4.1–M4.2 done；CHANGELOG 含 `0.5.0`

---

## M5 — 美港 → `v0.6.0`

**目标**：独立市场策略；不复用 A 股涨跌停/T+1 假设。

---

## M6 — 纸面执行 → `v0.7.0`

**目标**：吸收 V2 审查结论（信号新鲜度、事务化意图、草稿/激活）；默认仅模拟。

---

## M7 — v1.0.0

**目标**：单一产品可发布；上游参考仓归档说明齐全；版本/文档/CI 一致。

---

## 进度维护

每完成一个小/大里程碑：

1. 勾选本文件验收项  
2. 更新 `CHANGELOG.md`  
3. 更新 `VERSION`  
4. 运行 `scripts/release_tag.ps1` 打对应 tag  
5. （可选）推送 `git push origin main --tags`
