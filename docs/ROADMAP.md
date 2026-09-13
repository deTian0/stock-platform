# 路线图与里程碑

> 大里程碑 → **minor**（或产品就绪时 **major**）tag  
> 小里程碑 → **patch** tag  
> 规则细节：[`versioning.md`](versioning.md)

状态图例：`planned` / `in_progress` / `done`

---

## 总览

| ID | 名称 | 类型 | 目标 tag | 状态 |
|----|------|------|----------|------|
| M0 | 工程架子 + 契约草稿 | 大 | `v0.1.0` | planned（当前在 `v0.0.x` 搭架子） |
| M0.1 | 空仓脚手架与 Git | 小 | `v0.0.1` | done |
| M0.2 | 契约草案评审定稿 | 小 | `v0.0.2` | planned |
| M0.3 | CI 绿 + 文档交叉链接检查 | 小 | `v0.0.3` | planned |
| M1 | 统一 A 股 Provider 包（可安装） | 大 | `v0.2.0` | planned |
| M1.1 | providers 包骨架 + ticker 归一化 | 小 | `v0.1.1` | planned |
| M1.2 | daily + realtime 适配器（录制回放测） | 小 | `v0.1.2` | planned |
| M1.3 | 东财限流单点 + 能力矩阵注册 | 小 | `v0.1.3` | planned |
| M2 | 工作台壳接入 Provider | 大 | `v0.3.0` | planned |
| M2.1 | workbench 目录迁入最小可跑壳 | 小 | `v0.2.1` | planned |
| M2.2 | 能力矩阵驱动路由（缺能力 fail-closed） | 小 | `v0.2.2` | planned |
| M2.3 | 同标的/同日与批处理口径对齐验收 | 小 | `v0.2.3` | planned |
| M3 | 选股 / PIT 回测内核迁入 | 大 | `v0.4.0` | planned |
| M3.1 | lvrev / 分层闸门库化 | 小 | `v0.3.1` | planned |
| M3.2 | PIT 回测权威路径 + 防未来函数测 | 小 | `v0.3.2` | planned |
| M3.3 | 盘前简报批处理模式对接 | 小 | `v0.3.3` | planned |
| M4 | 投研 Agent 插件化（无内嵌抓取） | 大 | `v0.5.0` | planned |
| M4.1 | Agent 改调 packages/providers | 小 | `v0.4.1` | planned |
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

- [ ] `docs/contracts/*` 字段表无「TBD」关键空洞（至少 daily / realtime / adj_factor）
- [ ] 能力矩阵七项与 TSP 语义对齐说明写清
- [ ] 市场策略：A 股规则表初稿（T+1、涨跌停、时区）

#### M0.3 → `v0.0.3`

验收：

- [ ] GitHub Actions（或等价）对 docs / 脚本做基础检查
- [ ] `release_tag.ps1 -DryRun` 文档示例可跑通

#### M0 完成 → `v0.1.0`

验收：上述小里程碑全部 done；CHANGELOG 汇总；ADR 无未决「阻塞合并」项。

---

## M1 — 统一 A 股 Provider → `v0.2.0`

**目标**：可 `pip install` 的 `packages/providers`；东财限流单点；与旧仓抓取去重启动。

验收（大）：

- [ ] daily + realtime 契约测试（录制回放）通过
- [ ] ticker 归一化 + 非 A 股拒绝
- [ ] 文档声明：新代码禁止直连东财 URL

---

## M2 — 工作台壳 → `v0.3.0`

**目标**：最小可运行 workbench 只通过能力矩阵消费 Provider。

验收（大）：

- [ ] 通用路径无硬编码单一数据源品牌
- [ ] 缺 minute 等能力时 UI/API fail-closed

---

## M3 — 选股回测内核 → `v0.4.0`

**目标**：lvrev / PIT 回测权威路径在本仓；engine 旧路径标记废弃。

---

## M4 — Agent 插件 → `v0.5.0`

**目标**：研报图不自带 HTTP 抓取；历史日未来函数护栏保留。

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
