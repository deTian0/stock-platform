# 交易系统推进路线图（自有线）

> **状态**：planned（初版 2026-10-09）
> **版本基线**：`v3.12.5`
> **职责**：定义 `stock-platform` 在既有路线图见底之后的**新推进主线**；覆盖 回测 / 策略 / 选股 / 实盘 / 双线收口 五个方向。
> **不改写**：`docs/ROADMAP.md`（M0–M47 / Phase A–E）与 `docs/plans/` 既有 U1–U8、M-D/R/A/U/E/S、MR-1–MR-5 的 done 叙事。
> **上游依据**：本次体检结论见 §7。

---

## 0. 为什么需要这条线

`v3.12.5` 时点的规划余量实测：

| 轨 | 范围 | 状态 |
|----|------|------|
| `docs/ROADMAP.md` | M0–M47 / Phase A–E | 全 done |
| `usable-recommend-review-milestones.md` | U1–U8 | 全 done |
| `capability-domain-merge-roadmap.md` | Now / Next / Later | **除 `M-E4` 全部 done** |
| `market-report-dashboard-merge-milestones.md` | MR-1–MR-5 | 全 done |

**结论**：既有规划体系已执行到尽头，唯一的未开工项是 `M-E4`（实盘），且其原文标注「未立项前禁止开工」。因此「继续完善」不能靠接续旧计划，**必须重开产品目标**——本文件即该目标的可执行展开。

同时存在两个未绑定的工程事实（详见 §7）：

1. **代码写完但跑不起来**（**已于 `G1` 解决**）：体检时 5 个 `stock_platform_*` 包均未安装，`fastapi` / `uvicorn` / `pytest` / `pandas` / `numpy` 全部缺失；`G1` 完成后已全部恢复，全量测试 **526 passed / 0 failed**。
2. **两条日常线并存**：`a-stock-engine`（当前实际在跑 08:30 盘前 / 15:30 盘后自动化）与本仓（自称唯一权威产品仓）职责重叠未收口。

---

## 1. 总目标与排序

**已确认的推进顺序**（用户指定，不跳步）：

```
工程地基 (G)  →  回测 (B, P0)  →  策略深化 (S, P1)  →  选股 (X, P2)  →  实盘 (L, P3 门禁)
                                    ↑
                            双线收口 (C) 贯穿全程
```

**产品目标**：把 `stock-platform` 从「里程碑全绿的研究平台」推进到「回测可信、策略可迭代、选股可日用」的状态；实盘作为门禁项在 `L1` 立项后才启动。

**本轮明确不做**（继承既有红线）：

- React SPA 第二前端主链
- 平行数据抓取链 / 第二套东财客户端
- 把 Skill 仓 `pip install` 进产品依赖
- 默认开启 LLM 辩论 / 默认 `ths_sim`
- 在 G/B/S/X 阶段触碰 `liveTradingEnabled`

---

## 2. 编号与优先级

| 前缀 | 域 | 档 | 与既有编号冲突 |
|------|----|----|----------------|
| **G** | Groundwork 工程地基 | P0 前置 | 无 |
| **B** | Backtest 回测 | **P0** | 无 |
| **S** | Strategy 策略深化 | P1 | 无（既有 `M-S*` 为两段式，不混） |
| **X** | Selector 选股 | P2 | 无 |
| **L** | Live 实盘 | P3 门禁 | 无（既有 `M-E*` 不混） |
| **C** | Consolidation 双线收口 | 贯穿 | 无 |

量级：**S**（≤1–2 人日） / **M**（3–5 人日） / **L**（需拆子项）。

---

## 3. 里程碑明细

### 3.1 G — 工程地基（P0 前置）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **G1** | 环境恢复与可运行基线 | S | `v3.12.6` | **done（2026-10-09）** 5 个包 editable install 全部成功；`pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）**526 passed / 0 failed / 14.88s**；详见 §7 |
| **G2** | 外部路径与 env 治理 | S | `v3.12.6` | **done（2026-10-09）** `.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB` 实测指向 `D:/workspace/stock_trading/a-stock-engine/data_cache/market.db`（3.14 GB 可读）；**全仓 14 个文件**的仓根路径 `D:\workspace\git\` → `D:\workspace\stock_trading\` 迁移；`scripts/ops/stock-platform-daily.xml` 计划任务 `WorkingDirectory` 修正 + 编码声明 `UTF-16`→`UTF-8`（原声明与 UTF-8 实际字节不符）；详见 §7 |
| **G3** | 文档与 CI 一致性 | S | `v3.12.7` | `check_docs.ps1` + `check_versions.ps1` 通过；新路线图挂进 `docs/README.md` 与 `docs/ROADMAP.md` 顶部焦点区；CI `monorepo` job 覆盖范围确认 |

> **G 域不是可选项**：G1 是 B/S/X 的前置。当前状态下任何回测都无法真实执行。

---

### 3.2 B — 回测深化（P0，第一优先）

**背景**：平台现有回测内核是 `packages/research/{pit,walkforward,factor_ic,portfolio}.py`——PIT 无未来函数、滚动样本外摘要、因子 IC/ICIR 都在，**但没有一套能独立跑出完整组合净值曲线的回测**；`walkforward` 目前只出摘要。而 `a-stock-engine/local_backtest.py` 有更完整的引擎（全市场、费用模型、ETF、止损）。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **B1** | 回测基线与复现报告 | M | `v3.13.0` | **done（2026-10-09）** `backtest.py` 组合引擎 + `stock-platform-backtest` CLI；全周期（2020-01～2026-09，**1618 交易日 / 6964 码**）基线：**+90.24% / CAGR 10.53% / MDD -17.14% / 夏普 0.751 / 胜率 46.2% / 630 笔 / 平均持有 35.4 天**；与引擎对照差异逐条归因（持有期 / 区间 / L0 闸门 / ST·生存者 / 复权）；报告 `docs/ops/backtest-baseline.md`。**加载器优化（`v3.13.1`）后全周期 106 s → 65 s** |
| **B2** | 组合级指标补全 | M | `v3.13.2` | **done（2026-10-09）** `portfolio.py` 升级为指标**权威层**：新增成交额换手（`turnover_notional_per_year`）/ HHI 集中度（`avg_hhi`·`avg_top_weight`）/ 暴露（`avg_invested_ratio`）/ 持仓数；`compute_metrics` **单点定义**（`backtest.py` re-export，`backtest.compute_metrics is portfolio.compute_metrics`）；口径契约 `docs/contracts/portfolio-metrics.md`。全周期旧指标**逐位不变**，耗时 61.8 s |
| **B3** | 费用与摩擦模型对齐 | S | `v3.13.3` | **done（2026-10-09）** `portfolio.CostModel` **单点定义**（`commission_rate` / `stamp_sell_rate` / `slippage_bps` / `min_commission` / `etf_stamp_exempt`）；**新增滑点**（仅改成交价、不改信号）；CLI 四参数 + `--zero-cost`；**修买入侧计费不对称**（建仓与 `cost_basis` 原绕过 `trade_cost()`）；与 `local_backtest.py` 常量 + ETF 前缀表（30 项）**跨线互测**；契约 `docs/contracts/cost-model.md`。默认档指标**逐位不变** |
| **B4** | ETF 与资产类型支持 | M | `v3.13.4` | **done（2026-10-09）** `portfolio.asset_class` **单点定义**（`stock`/`etf`/`fund`，与印花税豁免同源前缀表）；`universe` 三档（`stock` 默认等价旧行为 · `etf` · `all` 混池）+ CLI `--universe`；`compute_metrics["by_asset"]` 分资产报告 + `trades.asset_class`；免税贯通实测（ETF 卖出仅佣金）；契约 `docs/contracts/asset-classes.md`。默认档逐位不变。**发现**：默认门槛下 ETF 全被挡（合成分 0.50 vs 0.86）→ 混池 ≠ ETF 配置；混池经截面分位改变股票入选**不可横比**；原始 ETF 池含脏数据 |
| **B5** | 回测↔在线规则统一层 | M | `v3.13.5` | **done（2026-10-09）** 新增 `rules.py` **单点定义**（`ExitPolicy` / `CooldownPolicy` / `DriftPolicy` + `evaluate_exit` / `advance_peak` / `evaluate_drift` / `limit_pct` / `is_limit_up` / `is_limit_down`）；回测委派全部交易判断（删内联退出逻辑）、**在线路径** `position_review.review_positions` + CLI `stock-platform-position-review` 调**同一批函数**；契约 `docs/contracts/trading-rules.md`；**默认档逐位不变** |
| **B6** | 回测可视化扩展 | M | `v3.13.6` | **done（2026-10-09）** `#backtest` 面板新增组合回测区块：**净值曲线 + 回撤带 + 逐日表联动**（三者共用同一份 `daily` 数组，索引即交易日）；手写 SVG，**未引入新前端依赖**；新增 `portfolio.drawdown_series` **单点定义**（瞬时回撤；`max_drawdown_from_curve` 委派其最小值）+ API `POST /api/research/backtest/portfolio`（只读 market.db，与 CLI 同路径）；契约 `docs/contracts/portfolio-metrics.md` §drawdown；默认档全周期**逐位不变**（0.902353 / 0.105348 / −0.171435 / 0.7511 / 630 / 0.4619 / 95117.64）；真机 1 年窗口 18.5 s（245 日 / 85 笔）|

---

### 3.3 S — 策略深化（P1）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **S1** | 因子 A/B 完整版（U7 遗留） | L | `v3.14.0` | 因子 / 闸门变更可带复盘对比；A/B 结果同屏可比；默认关闭旁路，不替换 picks |
| **S2** | 因子库扩展 | M | `v3.14.1` | 在 lvrev（低波 0.5 + 反转 0.5）之外新增至少 2 个正交因子；每个因子过 IC / ICIR 检验，进 `factor_ic` 报告，不达标不启用 |
| **S3** | 闸门参数敏感性 | M | `v3.14.2` | `apply_entry_gates` 关键阈值做敏感性扫描；产出稳健区间结论，避免过拟合单点 |
| **S4** | 行业中性化 / 风险暴露 | L | `v3.14.3` | 打分前做行业中性化与风格暴露约束；回测对照有中性化前后差异 |
| **S5** | LLM 辩论进主路径（可选） | M | `v3.14.4` | 保持默认确定性；可选路径带预算控制与降级；误判不进绩效（对齐 M-A2 口径） |

---

### 3.4 X — 选股（P2）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **X1** | 全市场选股接入 | L | `v4.0.0` | **done（2026-10-10）** 从当前 watch 宇宙扩到 `market.db` 全市场（排除 BSE）；耗时与内存有实测数字并写入文档；空宇宙 fail-closed |
| **X2** | 榜单体系对齐 | M | `v4.0.1` | **done（2026-10-10）** `research.rankings` 单点：②A 质量榜 / ②B 短线榜 / ③A 持仓 / ③B 操作建议（委派 B5 `rules`）/ ③C 观察名单；`picks` 语义不变；口径写入 `docs/contracts/rankings.md` + ADR 0056 |
| **X3** | 命中追踪接入 | M | `v4.0.2` | **done（2026-10-10）** `research.hit_tracking` 单点（`apply_hit`）＋ `SqliteHitTrackingRepository`；10 交易日≈14 日历日周期 / 周期内滑动延期 / `UNIQUE(code,session_type,pick_date)` 去重；`hit_tracking_snapshot` 三类累计（`pre_market` / `post_market` / `pre_market_in_cycle`）；契约 `docs/contracts/hit-tracking.md` + ADR 0057 |
| **X4** | 选股↔回测闭环 | M | `v4.0.4` | 每日 picks 自动进回测对照；推荐绩效与回测口径同源（承接 B5） |

---

### 3.5 L — 实盘（P3，门禁）

> **前置**：`L1` 未立项通过前，**禁止开工** `L2` / `L3`。这是对既有红线（`liveTradingEnabled=false`）的显式解禁流程，不是绕过。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **L1** | 实盘立项与券商选型 ADR | S | `v5.0.0` | 产出 ADR：券商选定（候选：富途 / 同花顺 / 其它）、解除红线的影响面清单、失败回滚方案、合规与资金上限；**经显式确认后才置 Accepted** |
| **L2** | 券商适配器实现 | L | `v5.0.1` | 实现 `BrokerPort` 适配器（订单 / 成交 / 持仓 / 账户契约）；全程可注入 transport 做离线测；缺凭据 fail-closed |
| **L3** | 实盘灰度与风控 | L | `v5.0.2` | 小额灰度；订单状态机逐态处理（接受 / 部成 / 全成 / 撤单 / 拒单 / 状态未知，剩余量结合未结订单）；每日对账 |

**承接的既有教训**（来自 `V2-code-review-20260905`，逐条必须在 `L2`/`L3` 验收）：

- 信号新鲜度必须显式校验，不能靠数据更新时间兜底
- 调度判断按窗口而非精确秒
- 跨日复核需「原计划日 / 复核日」双时间轴
- 订单状态机必须逐态处理
- 回测与在线规则共用同一实现（见 `B5`）
- 费用口径与账户实际对齐

---

### 3.6 C — 双线收口（贯穿）

**背景**：`a-stock-engine` 是当前**实际在跑**的日常线（08:30 盘前选股、15:30 盘后复盘），`stock-platform` 是**自称权威**的产品仓。二者选股内核同源（lvrev），但各有一套调度、存储、报告。这构成最大的长期风险：第五套重复实现。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **C1** | 双线职责边界定稿 | S | 随 `G3` | 产出职责表：谁是日常调度主链、谁是数据真相源、什么情况下用哪条；写入 `docs/plans/` 并互相交叉链 |
| **C2** | 数据真相源统一 | M | `v4.0.3` | **done（2026-10-10）** 确认 `daily_price`（`market.db`）为唯一历史行情真相源，派生库归属写明（引擎 `a-stock-engine.db` / `selections.db`、平台 `stock_platform.db`、引擎 `history/picks.db`）；**摄取归生产侧**、平台只读延续 ADR 0050；平台侧新增**覆盖守卫** `EngineSqliteProvider.coverage_snapshot` + `GET /api/ops/health.marketDb`（`thin` / `stale` / `empty` / `missing_table` / `error` → `degraded`）；实测破相已修复（2026-09-04~10-09 共 20 个交易日回补）；ADR 0058 + runbook `docs/ops/engine-market-db.md` |
| **C3** | 重复实现收敛清单 | M | 随 `S1` | 列出选股引擎 / 回测引擎 / 行情抓取 / 多 Agent 的重复实现，逐项标注「保留 / 降级为参考 / 废弃」；不批量删除，按里程碑渐进收敛 |

**约束**：C 域只做「定边界 + 定归属 + 列清单」，**不在本路线图内执行大规模代码合并**。

---

## 4. 依赖关系

```text
G1（环境恢复）
 ├─→ G2（env 路径）─→ B1（回测基线）─→ B2/B3/B4（指标/费用/ETF）
 │                                      └─→ B5（回测↔在线统一）─→ X4
 ├─→ G3（文档 CI）+ C1（职责边界）
 └─→ B6（可视化，依赖 B2 指标）

S1（因子 A/B）← B1 + B5
S2/S3/S4 ← S1
S5 ← S1

X1（全市场）← B1（回测可信）+ G1
X2 ← X1；X3 ← X1；X4 ← B5 + X3

L1（立项）← B5 + X4（回测与实盘口径已统一，才具备实盘前提）
L2 ← L1 Accepted；L3 ← L2

C2 ← B1；C3 ← S1
```

**关键路径**：`G1 → B1 → B5 → X4 → L1`。这条链上的每一项都是后者不可绕过的前置。

---

## 5. 版本映射建议

| 阶段 | 范围 | 建议 tag | 类型 |
|------|------|----------|------|
| G | G1–G3 | `v3.12.6`（G1+G2 合并） → `v3.12.7`（G3） | patch |
| B | B1–B6 | `v3.13.0` → `v3.13.6` | minor |
| S | S1–S5 | `v3.14.0` → `v3.14.4` | minor |
| X | X1–X4 | `v4.0.0` → `v4.0.4` | **major**（能力边界从 watch 扩到全市场） |
| C | C2（穿插） | `v4.0.3` | patch（数据治理：真相源统一 + 覆盖守卫） |
| L | L1–L3 | `v5.0.0` → `v5.0.2` | **major**（解禁实盘红线） |

每个里程碑收口时按既有流程：勾选本文件 → 更新 `CHANGELOG.md` → 更新 `VERSION` → `scripts/release_tag.ps1` → `git push --follow-tags`。

---

## 6. 红线（继承 + 新增）

**继承自 `docs/upstream-archive.md` / `capability-domain-merge-roadmap.md`**：

1. 一条数据链；东财只走 `em_get`；能力矩阵 fail-closed（典型 409）
2. 默认纸面 `SIMULATE`；不静默用 fixtures 冒充 live
3. 禁止 `pip install` Skill 仓进产品依赖；禁止平行抓取第二链
4. `market.db` 只读挂载，与 brief SQLite 分离（ADR 0049 / 0050）
5. 真实 token 不入库、不入文档、不进对话
6. 非整仓 merge；禁止 fork 出第二条产品主链

**本路线图新增**：

7. **`L1` 未立项前，任何人不得用「完善」为由触碰 `liveTradingEnabled` 与实盘券商代码。**
8. ~~**B 域回测结果在 `B5` 完成前，不得作为策略取舍的唯一依据**——因为此时回测与在线规则尚未共用同一实现。~~ **已于 `B5`（`v3.13.5`）解除**：回测与在线路径共用 `rules.py` 单点定义（退出 / 冷静期 / 持仓偏差 / 涨跌停），并由断言测试锁定两侧一致。后续任何数字比较仍须遵守 [`docs/contracts/trading-rules.md`](../contracts/trading-rules.md) §9 的不可横比铁律（须声明 `exit_policy` / `cooldown_days` / `drift_band`）。
9. **C 域不执行为收敛而做的批量删除**；只定边界、列清单，代码收敛按里程碑渐进。

---

## 7. 实测记录（本次体检，2026-10-09）

| 项 | 实测值 | 备注 |
|----|--------|------|
| `VERSION` | 3.12.5 | 对应提交 `0da5f2d` |
| 最新 tag | `v3.12.5` | 已 push，`main` 与 `origin/main` 同步 |
| 工作树 | 干净 | 仅 untracked `userinput.py` |
| 代码规模 | 131 个 .py（src 81 / tests 50），src 约 17.0k LOC | `packages` + `apps` |
| 文档规模 | 53 个 ADR（0001–0053）+ contracts / ops / plans | — |
| Workbench API | 59 个 path+method | 有全量 API 自动化测 + OpenAPI 契约测（B1 时点 58，`B6` 增至 59） |
| `.venv` 解释器 | Python 3.14.6（`D:\soft\path\miniconda3`） | pyvenv.cfg 的 home 可解析，**能启动** |
| `.venv` 依赖 | **不可用** | 5 个 `stock_platform_*` 包未安装；`fastapi`/`uvicorn`/`pytest`/`pandas`/`numpy`/`mootdx`/`tushare` 全 Missing；仅 `pydantic`/`jinja2`/`httpx`/`requests` 可用（conda base `--system-site-packages`） |
| **G1 执行结果** | **已恢复** | 5 个包 editable install 成功；`pytest packages apps` = **526 passed / 0 failed / 1 warning / 14.88s**（warning 为 fastapi testclient 的 httpx 弃用提示，非阻塞） |
| **B1 执行结果** | **已完成** | 全周期 2020-01-02～2026-09-03（1618 交易日 / 6964 码）**+90.24%**，CAGR 10.53%，MDD -17.14%，夏普 0.751，胜率 46.2%，630 笔，平均持有 35.4 天；加载 **11.5 s** + 回测 **48.6 s**（2026-10-09 加载器优化后；此前为加载 53.7 s + 回测 47.2 s）；报告 `docs/ops/backtest-baseline.md` |
| **B2 执行结果** | **已完成** | `portfolio.compute_metrics` 单点定义（`backtest.py` re-export，`is` 同一对象）；新增成交额换手 **11.28 倍/年**、平均 HHI **0.0865**、平均最大单票权重 **10.17%**、平均仓位 **80.0%**、平均持仓 **13.6 只**；口径契约 `docs/contracts/portfolio-metrics.md`；旧指标逐位不变，全周期耗时 **61.8 s** |
| **B3 执行结果** | **已完成** | `CostModel` 费用**单点定义**（`portfolio.py`，`backtest.py` re-export）＋**新增滑点**（仅改成交价）＋**修买入侧计费不对称**；CLI `--commission-rate` / `--stamp-sell-rate` / `--slippage-bps` / `--zero-cost`；**跨线互测**（静态解析 `local_backtest.py`：常量 + 30 项 ETF 前缀，四象限比对）通过；契约 `docs/contracts/cost-model.md`；默认档全周期**逐位不变**，敏感性 零成本 **+1226.93** / 滑点 5bps **−411.45** / 滑点 10bps **−1442.73**；耗时 **63.3 s** |
| **B4 执行结果** | **已完成** | `asset_class` 单点定义 + `universe`（`stock`/`etf`/`all`）+ CLI `--universe` + `by_asset` 分资产报告 + ETF 卖免印花税贯通；跨线互测 `_is_fund`/`_is_etf` 前缀表；契约 `docs/contracts/asset-classes.md`。默认档（`stock`）全周期**逐位不变**；宇宙对照 `stock` +90.24% / `all` +102.58%（ETF 0 笔）/ `etf` -16.31%；免税实测 `515250` 卖出 8.54e-05 vs 股票 5.854e-04；research **138 passed**、全量 **592 passed** |
| **B5 执行结果** | **已完成** | `rules.py` 单点定义（退出 / 冷静期 / 持仓偏差 / 涨跌停），回测与在线**双路调用同一函数**；单点定义断言（`backtest.evaluate_exit is rules.evaluate_exit` 等全为真）+ 差分一致断言（同状态同 `reason`）；新增 `cooldown_days`（默认 0）/ `drift_band`（默认 None）；冷静期对照 `cooldown_days=10` → `total_return` 0.898259（−0.41 pp）/ 终值 94912.95（**−204.69**）；契约 `docs/contracts/trading-rules.md`；默认档全周期**逐位不变**（0.902353 / 0.105348 / −0.171435 / 0.7511 / 630 / 0.4619）；research **179 passed**、全量 **633 passed** |
| **B6 执行结果** | **已完成** | `portfolio.drawdown_series` 单点定义（**瞬时**回撤 `equity/peak-1`，创新高归零；非正权益日跳过但保持索引对齐），`max_drawdown_from_curve` 委派其最小值（scalar 与 band 不可能分叉）；Workbench `#backtest` 新增组合区块（**净值曲线 + 回撤带 + 逐日表联动**，共用同一 `daily` 数组；手写 SVG，零新前端依赖）+ API `POST /api/research/backtest/portfolio`（只读 market.db，与 CLI 同路径；无 DB → 503 fail-closed）；默认档全周期**逐位不变**（0.902353 / 0.105348 / −0.171435 / 0.7511 / 630 / 0.4619 / 95117.64；加载 13.4 s + 回测 49.3 s）；**真机** 1 年窗口（2025-09-01～2026-09-03）= HTTP 200 / **18.5 s** / 245 交易日 / 85 笔 / 终值 46,502.02，`metrics.max_drawdown` −0.193254 **==** `min(daily[].drawdown)`；全量 **643 passed**；发布 `v3.13.6` |
| **X1 执行结果** | **已完成** | 宇宙解析单一入口 `market_universe.resolve_universe`（`config` 默认 / `market_db` 全市场）；providers `list_symbols`（日期窗口聚合 + `min_bars` + BSE 排除 + 裸码合并计数）与 research（资产过滤复用 B4 `asset_class` + `limit` + fail-closed）**职责切分、规则不写两遍**；CLI `stock-platform-market-universe`；实测（asof 2026-09-03）：全市场 **5227 只** / 枚举 **0.21 s** / **1.04 MB**，全市场单日 PIT panel **5209 行 / 23.0 s / 498.8 MB**，窗口聚合 0.15 s vs 全表扫描 5.12 s（34×）；契约 `docs/contracts/market-universe.md`、ADR `0055`、实测 `docs/ops/market-universe-benchmark.md`；全量 **698 passed**（+19）；发布 `v4.0.0`。⚠️ 发现 `market.db` 自 **2026-09-04** 起日覆盖塌到 14 只（引擎侧导入中断），最后可用交易日 **2026-09-03** —— `X3`/`X4` 前需先修引擎导入 |
| **G2 执行结果** | **已完成** | 仓根路径全仓迁移 14 文件；`market.db` 冒烟：`resolve_engine_market_db()` → `D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`，`get_daily(['600519'])` = **406 行**（2025-01-02～2026-09-03），`get_fundamentals_pit` 正常；`check_docs`（112 required / 139 md）+ `check_versions`（5 pkg）双绿；全量测试 **526 passed / 14.14s** |

### 7.1 G1 安装明细（2026-10-09）

| 项 | 值 |
|----|-----|
| 实际装到的版本 | numpy 2.5.3 · pandas 3.0.6 · fastapi 0.143.0 · uvicorn 0.54.0 · starlette 1.7.0 · pytest 9.1.1 · httptools 0.8.0 · websockets 17.2 |
| 必须的安装顺序 | `providers → research → agents → execution → workbench` |
| 顺序原因 | `agents` / `execution` / `workbench` 均声明依赖 `stock-platform-providers`，该名字 **PyPI 上不存在**，必须先本地 editable 安装，否则依赖解析直接失败 |
| 失败过的坑 | conda base（`D:\soft\path\miniconda3`）曾有 `stock-platform-providers 3.8.1` 失效残留；venv 为 `--system-site-packages` 故 pip 尝试卸载它 → `WinError 3 系统找不到指定的路径` → 整次安装中止。残留被该次失败卸载动作清掉后（判据：`pip show stock-platform-providers` 返回 `Package(s) not found`），重跑即成功 |
| 噪音（非故障） | 每次 pip 都会打印 `[safe-delete][SAFE_DELETE_FAIL_CLOSED] ... trash-failed`，为本机 safe-delete 拦截缓存清理所致，**不影响安装** |
| 网络 | 清华 + 阿里源，实测约 132 kB/s；numpy 12.7 MB 耗时 1 分 40 秒 |
| 复用 base 的依赖 | `pydantic` 2.46.4 / `jinja2` / `httpx` / `requests` / `anyio` / `packaging` / `pluggy` 直接来自 conda base 的 site-packages，未重复下载 |

> **修正记录**：`WORKBUDDY.md` §「虚拟环境：丢掉重建」称「两个已拷贝的 .venv 不能用」——对 `stock-platform` 而言**只对了一半**：解释器完好，缺的是依赖安装。原文建议「重建」，实测「在原 venv 上装依赖」成本更低（依赖极轻：providers 无硬依赖，research 仅 numpy+pandas，workbench 仅 fastapi+uvicorn+jinja2）。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-10-09 | 初版：体检既有规划见底 → 定义 G/B/S/X/L/C 六域里程碑；确认推进顺序 回测 → 策略 → 选股；`M-E4` 降为 `L1` 门禁项 |
| 2026-10-09 | `G1` 完成：5 个包 editable install 恢复，全量测试 526 passed；回填 §7 实测记录 |
| 2026-10-09 | `B1` 完成：组合回测引擎 + CLI + 基线报告；`apply_entry_gates` 向量化（200 s→106 s）；修 `close` 未复权导致假亏损；发布 `v3.13.0` |
| 2026-10-09 | `B1` 补强：行情库加载器 54.9 s → 12.5 s，全周期回测 106 s → 65 s（指标逐位不变）；新增 `test_backtest_cli.py` 锁定加载语义（8 passed）；发布 `v3.13.1` |
| 2026-10-09 | `G2` 完成：全仓仓根路径迁移 + 计划任务 XML 修正 + `market.db` 挂载冒烟通过；`G1`+`G2` 合并发布 `v3.12.6` |
| 2026-10-09 | `B2` 完成：指标单点化（`portfolio.py` 权威层 + `backtest.py` re-export）+ 成交额换手 / HHI 集中度 / 暴露；口径契约 `docs/contracts/portfolio-metrics.md`；发布 `v3.13.2`；`B3`–`B6` 目标 tag 顺延（`v3.13.3`–`v3.13.6`） |
| 2026-10-09 | `B3` 完成：费用与摩擦单点化（`CostModel`）+ **新增滑点** + 修买入侧计费不对称 + CLI 四参数；跨线互测（静态解析引擎常量与前缀表）；契约 `docs/contracts/cost-model.md`；里程碑方案 `docs/plans/b3-cost-model-milestone.md`；默认档逐位不变，发布 `v3.13.3` |
| 2026-10-09 | `B4` 完成：资产类型单点化（`asset_class`）+ `universe`（`stock`/`etf`/`all`）+ CLI `--universe` + 分资产 `by_asset` 报告 + ETF 免税贯通；跨线互测 `_is_fund`/`_is_etf`；契约 `docs/contracts/asset-classes.md`；默认档逐位不变，发布 `v3.13.4` |
| 2026-10-09 | `B4` 实测三条发现回填：默认门槛下 ETF 全被 `min_pick_score=0.80` 挡下（合成分 0.50 vs 0.86）；混池经截面分位改变股票入选 → **不可与 `stock` 横比**；原始 ETF 池含脏数据需先清洗（X 域议题）。`docs/contracts/asset-classes.md` §6 + `backtest-baseline.md` §3.2 |
| 2026-10-09 | `B5` 完成：`rules.py` 交易规则**单点定义**（退出 / 冷静期 / 持仓偏差 / 涨跌停）+ 在线路径 `position_review` + CLI；回测委派全部交易判断（删内联退出逻辑）；单点定义与差分一致断言齐备；契约 `docs/contracts/trading-rules.md`；默认档逐位不变，发布 `v3.13.5`；**红线 8 随之解除**（关键路径 `G1 → B1 → B5 → X4 → L1` 推进至 `X4` 前置就绪） |
| 2026-10-09 | `B6` 完成：`portfolio.drawdown_series` 单点定义 + Workbench `#backtest` 组合区块（净值曲线 / 回撤带 / 逐日表联动，手写 SVG 零新依赖）+ API `POST /api/research/backtest/portfolio`（只读 market.db，与 CLI 同路径）；真机 1 年窗口 18.5 s、`max_drawdown` 与图带最深点逐位相等；默认档逐位不变，发布 `v3.13.6`；**B 域（B1–B6）全部收官** |
| 2026-10-09 | 缺陷修复：`intel-report/crosswalk` 与 `prefill` **不带 `asof`** 时 500（`default_brief_asof` 签名于 `v3.10.1` 变更，而 `v3.12.5` 新增的调用点按旧签名写就 → 潜伏 5 个版本；UI 默认裸调用故**首屏必崩**，且全部用例都显式传 `asof` 使兜底分支零覆盖）→ 两处统一走 `_resolve_asof`；新增 AST **静态守卫** `test_signature_call_guard.py`（专杀「照旧签名写新调用点」，全包零违规）+ 两条默认 asof 行为回归；真机裸调用 200；发布 `v3.13.7` |
| 2026-10-10 | 缺陷修复（B5 遗留）：**涨跌停判定因 `pct_chg` 标度混用近乎失效**（股票=小数 / ETF=百分点，`\|x\|>0.5` 一刀切漏判 99.6%）→ 新增 `pct_scale.py` 单点定义（`close` 序列拟合投票 + 除权行剔除 + `asset_class` 回退）；`compute_features` 加 `pct_scale="auto"\|"verbatim"`（默认 `auto`）；全周期 A/B：`verbatim` 与 B1–B6 逐位一致，`auto` 总收益 +91.71%（0.917123）/ 笔数 628 / 终值 95,856.17；全量 660 passed；发布 `v3.13.8` |
| 2026-10-10 | **数据源适配层**：新增三 provider 统一接入非默认数据源 —— `workbuddy`（WorkBuddy MCP 的 JSON 缓存适配器，`STOCK_PLATFORM_WORKBUDDY_CACHE_DIR`）、`tdx`（通达信本地 `vipdoc/*/lday/*.day` 二进制）、`futu`（富途 OpenAPI 懒加载 `futu-api`）；三预设 `workbuddy`/`cn_tdx`/`cn_futu` + 能力矩阵声明 + 零网络单测；契约 `docs/contracts/data-source-adapters.md`、ADR `0054`；发布 `v3.13.9` |
| 2026-10-10 | **`X2` 完成**：榜单体系对齐 —— 新增 `research.rankings` 单点（`build_rankings` + `RankingConfig`），五榜 ②A 质量榜（默认 10）/ ②B 短线榜（默认 5，排除 ②A 头部且优先 `entry_ok`）/ ③A 持仓（含未过闸门持仓，分数为 `null`）/ ③B 操作建议（**完全委派 B5 `rules`，只收 exit/trim**）/ ③C 观察名单（默认 23）；`min_composite_score` 值域隔离（平台 `[0,1]` ≠ 引擎百分制 60）；引擎的「评分低于中位数 ⇒ 减仓」启发式**降级为 ③A 上的只读 `belowMedian`**（不写第二套可操作规则）；`picks` 语义不变（= ②A 头部）；CLI `stock-platform-rankings` + `--holdings` 流水线接线 + Workbench `?holdingsPath`/`STOCK_PLATFORM_HOLDINGS_PATH`（复用 `load_holdings` 唯一读取器）+ `#recommend` 榜单区块；契约 `docs/contracts/rankings.md` + ADR `0056`；全量 719 passed；发布 `v4.0.1` |
| 2026-10-10 | **`X1` 完成（X 域开局）**：全市场宇宙接入 —— `resolve_universe` 单一入口（`config`/`market_db`），providers `list_symbols` 与 research 过滤**职责切分**（BSE 判据归 providers、资产类别归 B4 单点，均不重复实现）；`MarketUniverse` 随结果返回出处与代价；CLI + 流水线 + `daily_cli` 接线；空宇宙一律 `UniverseEmptyError`（**禁止回落样例**）；实测 5227 只 / 0.21 s / 1.04 MB，全市场单日 panel 5209 行 / 23.0 s / 498.8 MB；契约 `docs/contracts/market-universe.md` + ADR `0055` + 实测 `docs/ops/market-universe-benchmark.md`；全量 698 passed；**major 发布 `v4.0.0`**。⚠️ 实测另发现 `market.db` 自 2026-09-04 起日覆盖塌到 14 只（引擎侧导入中断）→ 记为 `X3`/`X4` 前置阻塞（平台只读，不代抓） |
| 2026-10-10 | **`X3` 完成**：命中追踪接入 —— 新增 `research.hit_tracking` 单点（`apply_hit` 纯规则）＋ `SqliteHitTrackingRepository`（`hit_tracking` 明细 `UNIQUE(code,session_type,pick_date)` + `hit_summary` 汇总，与 brief 存档同库不同表）；规则**照搬** `a-stock-engine`（10 交易日≈14 日历日、周期内滑动延期、闭区间、`total_cycles` 仅新周期递增），仅把「先查后插」升级为硬唯一约束；`hit_tracking_snapshot` 三类累计（`pre_market` / `post_market` / `pre_market_in_cycle`）；写入口收敛（流水线默认 `track_hits=True` 记 ②A 头部、失败不外抛；`GET /brief` **不**隐式写，避免探索性选股污染周期）；CLI `stock-platform-hits` + `daily --no-track-hits` + Workbench `GET/POST /api/research/hit-tracking` + `#hits` 面板；契约 `docs/contracts/hit-tracking.md` + ADR `0057`；全量 747 passed；发布 `v4.0.2` |
| 2026-10-10 | **`C2` 完成（X4 前置阻塞解除）**：数据真相源统一 + 覆盖守卫 —— 确认 `daily_price`（`market.db`）为唯一历史行情真相源，派生库（引擎 `a-stock-engine.db`/`selections.db`/`history/picks.db`、平台 `stock_platform.db`）归属写明且禁作行情输入；**摄取归生产侧**、平台只读延续 ADR 0050；平台新增只读 `EngineSqliteProvider.coverage_snapshot`（双判据：CN 交易日齐全 + 每日 ≥ `min_rows`，滞后**按交易日**计）+ `GET /api/ops/health.marketDb`（`thin`/`stale`/`empty`/`missing_table`/`error` → `degraded`）；**实测破相已修**：`daily_price` 自 2026-09-04 起塌陷（3 个部分日各 14 行 + 17 个交易日全缺）→ 生产侧 `empirical/backfill_market_daily.py` 回补 20 交易日 / 104,301 行 / 0 失败，单位口径 `--validate` 四字段比值全 1.0000；ADR `0058` + runbook `docs/ops/engine-market-db.md`；全量 761 passed；发布 `v4.0.3`。**X4 目标 tag 顺延至 `v4.0.4`** |
