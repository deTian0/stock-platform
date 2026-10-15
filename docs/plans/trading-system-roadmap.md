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

**产品目标**：把 `stock-platform` 从「里程碑全绿的研究平台」推进到「回测可信、策略可迭代、选股可日用」的状态；**`Y` 域（收益增强）**补上「**收益落地**」这一环 —— 先归因（`Y3` 说清为什么亏）、再把已验证的改进经**样本外闸门**送进生产（`Y1`）；实盘作为门禁项在 `L1` 立项后才启动。

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
| **R** | Remediation 收尾与加固 | P0/P1 | 无 |
| **T** | Trust & Ops 循环可信度与运营 | P0/P1 | 无 |
| **Y** | Yield 收益增强（研究 → 生产采纳） | P0 | 无 |

量级：**S**（≤1–2 人日） / **M**（3–5 人日） / **L**（需拆子项）。

---

## 3. 里程碑明细

### 3.1 G — 工程地基（P0 前置）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **G1** | 环境恢复与可运行基线 | S | `v3.12.6` | **done（2026-10-09）** 5 个包 editable install 全部成功；`pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）**526 passed / 0 failed / 14.88s**；详见 §7 |
| **G2** | 外部路径与 env 治理 | S | `v3.12.6` | **done（2026-10-09）** `.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB` 实测指向 `D:/workspace/stock_trading/a-stock-engine/data_cache/market.db`（3.14 GB 可读）；**全仓 14 个文件**的仓根路径 `D:\workspace\git\` → `D:\workspace\stock_trading\` 迁移；`scripts/ops/stock-platform-daily.xml` 计划任务 `WorkingDirectory` 修正 + 编码声明 `UTF-16`→`UTF-8`（原声明与 UTF-8 实际字节不符）；详见 §7 |
| **G3** | 文档与 CI 一致性 | S | `v4.0.5` | **done（2026-10-10）** `check_docs.ps1` + `check_versions.ps1` 双绿；自有主线路线图 `trading-system-roadmap.md` 挂进 `docs/ROADMAP.md` 顶部焦点区与 `docs/README.md`，`docs/plans/README.md` 陈旧状态刷新；CI `monorepo` job 确认（5 包 editable + `pytest packages apps`，`replay` 预设）；**补齐 `check_docs` 的 `$required` 三处遗漏**（主路线图 / B3 里程碑 / 新 C1 文档，128→131）。**目标 tag 由陈旧的 `v3.12.7` 顺延至 `v4.0.5`** |

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
| **S1** | 因子 A/B 完整版（U7 遗留） | L | `v4.1.0` | **done（2026-10-10）** 同源引擎 A/B：`strategy_ab.compare_strategy_ab_engine` / `compare_strategy_ab_from_bars` 用 X4 单点 `book_replay.replay_book` 跑两臂（只差 `entry_provider`）；`StrategyConfig` 增 `gates`（`min_pick_score` 缺省 `0.80`）→ **闸门变更可表达**；每臂附 `review` 复盘块（口径对齐 `performance`/U3）；`delta = B − A` + `sameDefinition` 身份块；Workbench `POST /api/research/strategy/ab-engine` + `#strategy-compare` 内「A/B 同屏」两列区块；CLI `stock-platform-strategy-ab`；**默认关闭旁路，不替换 picks**；契约 `docs/contracts/strategy-ab.md` + ADR `0060`。**目标 tag 由陈旧的 `v3.14.0` 顺延至 `v4.1.0`** |
| **S2** | 因子库扩展 | M | `v4.1.1` | **done（2026-10-10）** 新增 `research.factors` 因子库单点（`FACTOR_LIBRARY` / `FactorSpec`）：基线 `low_vol` / `reversal` + 新增 `long_reversal`（6 月反转，跳过最近一月）/ `max_ret`（20 日 MAX 彩票）/ `illiq`（Amihud 非流动性）；准入闸门 `factor_ic.admit_factor`（`n_dates≥20` / `|IC|≥0.02` / `|ICIR|≥0.15` / **符号一致**）+ 正交选择 `select_enabled`（与已启用因子 `|Spearman ρ|≥0.70` 判冗余）；`build_factor_ic_report` 出判定表 + 相关矩阵；`build_feature_frame` 复用 `compute_features`（`keep_extra`，既有调用逐位不变）；CLI `stock-platform-factor-ic` + API `POST /api/research/factor/admission` + Workbench `#factor-library` 面板；**默认不改权重**（`W_DEFAULT` 逐位不变）；契约 `docs/contracts/factor-library.md` + ADR `0061`。**真机实测**（全周期 / 324 截面）：`long_reversal` IC +0.033/ICIR +0.198、`illiq` IC +0.077/ICIR +0.798 **启用**；`max_ret` 与 `low_vol` 相关 +0.876 **冗余不启用**。**目标 tag 顺延 `v3.14.1` → `v4.1.1`** |
| **S3** | 闸门参数敏感性 | M | `v4.1.2` | **done（2026-10-10）** 入场闸门常量单点化 `gates.EntryGateParams`（`reversal_q` / `ma20_band` / `ma60_band` / `vol_filter`，默认值 = 原硬编码字面量**逐字**）→ `apply_entry_gates(df)` / `(df, reversal_q=0.30)` / `(df, params=EntryGateParams())` **逐位相同**；`book_replay.screener_entry_provider` 增 `gate_params` 透传（**同一** provider，不复制闸门）；新增 `research.sensitivity` 单点 —— `sweep_entry_gate`（单旋钮网格扫描，每点走同一 `book_replay.replay_book`，`feats` 只建一次）+ `summarize_sweep`（**纯函数**：容差带 `sign·(obj−best) ≥ −tolerance×|best|`；`robustRange` = 含最优点且**连续**的一段网格；`robust` / `fragile` / `flat` / `insufficient` 四判）+ `build_sensitivity_report`（任一 `fragile` → `overall=fragile`）；CLI `stock-platform-strategy-sensitivity` + API `POST /api/research/strategy/sensitivity` + Workbench `#sensitivity` 面板；契约 `docs/contracts/gate-sensitivity.md` + ADR `0062` + 实测 `docs/ops/gate-sensitivity-benchmark.md`。**真机实测**（2024-09-02→2026-09-08 / 489 交易日 / 3 旋钮 × 5 点 / 182.7 s）：`min_pick_score` **robust**（稳健区间 `0.5–0.7`，3 点）；`reversal_q` / `ma_band` **fragile**（各仅最优点达标）→ `overall=fragile`；出厂值 `0.30` / `0.93` / `0.80` 均**不**落在孤峰上、**不**据此改档。**目标 tag 顺延 `v3.14.2` → `v4.1.2`** |
| **S4** | 行业中性化 / 风险暴露 | L | `v4.1.3` | **done（2026-10-10）** 新增 `research.neutralization` 单点（`NeutralizeParams`：`industry_col` / `mode`(`demean`|`zscore`) / `clip` / `min_group_size` / `rescale`(`rank`|`none`) / `composite_demean` / `style` / `style_clip`）＋ `industry_neutralize_series` / `neutralize_factor_scores` / `residualize` / `resolve_groups` / `attach_industry` / `industry_exposure`；语义承接引擎 `factor_engine._zscore`（行业分组 z + 组内去均值），作用面为 `[0,1]` 因子分，`rescale="rank"` 还原尺度使 `min_pick_score` 语义不变；`lvrev.score_lvrev(..., neutralize=None)` **默认关 → 组合分逐位不变**；行业只读接入 `backtest_cli.load_engine_industry()`（读 `fundamentals.industry`，缺表 fail-closed），`code` 两侧经 `portfolio.norm_code` 归一（`daily_price` 带后缀 / `fundamentals` 裸 6 位，**原始交集 0**）；透传链 `prepare_book_frame(..., industry_map=None)` + `screener_entry_provider(..., neutralize=None, max_per_industry=None)`；暴露约束 `max_per_industry`（按行业 `head(k)` 后按 `composite_score` 重排）；A/B 单点 `research.neutralization_ab`（两臂同一 `replay_book`，`delta`/`review`/`sameDefinition` **复用 `S1` 实现**）+ 行业暴露画像；CLI `stock-platform-strategy-neutralization` + API `POST /api/research/strategy/neutralization` + Workbench `#neutralization`；契约 `docs/contracts/industry-neutralization.md` + ADR `0063` + 实测 `docs/ops/neutralization-benchmark.md`。**真机实测**（2024-09-02→2026-09-08 / 489 交易日 / 2.95 M 行 / 两轮 95.9 s）：仅中性化 `total_return` 0.3029→**0.5257**、`sharpe` 1.0599→**1.1430**，但 `max_drawdown` -0.1767→**-0.2673**、`win_rate` 0.4659→**0.3839**；叠加 `maxPerIndustry=3` → `total_return` **0.5850** / `sharpe` **1.2492**；持仓 HHI 反升 0.0225→0.0302（**「中性化 ≠ 更分散」**）；`raw` 臂两轮逐位一致；出厂权重与闸门**逐位未改**（只诊断不改档）。**目标 tag 顺延 `v3.14.3` → `v4.1.3`** |
| **S5** | LLM 辩论进主路径（可选） | M | `v4.1.5` | **done（2026-10-11）** 新增 `agents.debate_lane` **单点**（`DEBATE_LANE_ENGINES` = `off`/`deterministic`/`llm`，**默认 `off`**；`normalize_lane_engine()` 未知名抛 `AgentError` → HTTP **400**，**不静默回落**；`attach_debate_lane()` **只读** brief，返回车道载荷 `enabled`/`engine`/`requestedEngine`/`debates`/`debateCount`/`degraded`/`warnings`/`advisory`/`excludedFromPerformance`/`budget`；`debate_lane_summary()` 供 manifest 裁剪）＋ **预算提为一等公民**（`llm_debate._LlmBudget` → 公开 `LlmBudget(max_calls, max_tokens_soft)`，显式覆盖环境变量；`debate_brief_picks` 增 `budget` 形参）＋ **主链挂载走依赖注入**（`run_daily_pipeline(..., debate_runner, debate_engine, debate_max_picks)`，`stock-platform-research` **不新增**对 agents 的依赖）产出 `{asof}/debates.json` + `manifest.debates` + `DailyPipelineReport.debates`（best-effort，异常落 `report.debates["error"]`）；CLI `stock-platform-daily --debate-engine {off,deterministic,llm}` / `--debate-max-picks` + API `POST /api/research/daily/debate`（校验 **400** 先于面板 **503**）；**「误判不进绩效」锁成可断言不变量** —— 开/关辩论两轮的 `brief.json` 字节、`picks_ledger.jsonl` 字节与命中块**逐位相等**（对齐 **M-A2** 评级边界口径：判决经 `parse_rating`/`to_ternary_verdict` 归一为 `Buy|Hold|Sell` 但**不再往下走**、不转 decision 行 `rating`）；**刻意不新增手动 UI 面板**（车道定位是主链自动化；手动面板与既有 `TopN 辩论` 重复）；契约 `docs/contracts/debate-lane.md` + ADR `0065`。**目标 tag 顺延 `v3.14.4` → `v4.1.5`** |

---

### 3.4 X — 选股（P2）

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **X1** | 全市场选股接入 | L | `v4.0.0` | **done（2026-10-10）** 从当前 watch 宇宙扩到 `market.db` 全市场（排除 BSE）；耗时与内存有实测数字并写入文档；空宇宙 fail-closed |
| **X2** | 榜单体系对齐 | M | `v4.0.1` | **done（2026-10-10）** `research.rankings` 单点：②A 质量榜 / ②B 短线榜 / ③A 持仓 / ③B 操作建议（委派 B5 `rules`）/ ③C 观察名单；`picks` 语义不变；口径写入 `docs/contracts/rankings.md` + ADR 0056 |
| **X3** | 命中追踪接入 | M | `v4.0.2` | **done（2026-10-10）** `research.hit_tracking` 单点（`apply_hit`）＋ `SqliteHitTrackingRepository`；10 交易日≈14 日历日周期 / 周期内滑动延期 / `UNIQUE(code,session_type,pick_date)` 去重；`hit_tracking_snapshot` 三类累计（`pre_market` / `post_market` / `pre_market_in_cycle`）；契约 `docs/contracts/hit-tracking.md` + ADR 0057 |
| **X4** | 选股↔回测闭环 | M | `v4.0.4` | **done（2026-10-10）** 逐日回放循环单点 `research.book_replay.replay_book`（`entry_provider` 多态：`screener` vs `picks`）；`run_portfolio_backtest` 转薄封装、`run_picks_backtest` 同引擎跑推荐账本；picks 账本 JSONL + 流水线自动写入 + 可选回放对照（`delta = picks − 回测`）；契约 `docs/contracts/picks-backtest.md` + ADR 0059 |

---

### 3.5 L — 实盘（P3，门禁）

> **前置**：`L1` 未立项通过前，**禁止开工** `L2` / `L3`。这是对既有红线（`liveTradingEnabled=false`）的显式解禁流程，不是绕过。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **L1** | 实盘立项与券商选型 ADR | S | `v4.1.4`（原 `v5.0.0` 顺延，见 ADR `0064` §7） | **done（2026-10-11）** —— ADR `0064` 已置 **`Accepted`**（2026-10-11 经用户确认）：券商 = **华宝证券（国内）**、资金上限 = **1 万元（账户总资产口径，含现有持仓）**、合规边界 = **Phase 0 纯模拟盘，本次不解禁红线**；含三阶段解锁条件（P0 纯模拟 / P1 半自动人工·免报备 / P2 `QMT` 全自动·必须报备）、解除红线的影响面清单、失败回滚方案；契约 `docs/contracts/compliance-boundary.md`（§5 P0 名义参数已确认）。**已于 2026-10-11 显式确认并置 `Accepted`** |
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
| **C1** | 双线职责边界定稿 | S | 随 `G3` | **done（2026-10-10）** 新增 `docs/plans/dual-line-responsibility.md`：日常调度主链 = 引擎线（08:30/15:30）、历史行情真相源 = `market.db`·`daily_price`（平台只读）、产品/研究权威 = 平台线；含 5 组使用判据 + 数据归属表（承接 ADR 0058）+ 双方红线；与 `trading-system-roadmap` / `ROADMAP` / `README` / ADR 0058 / `engine-market-db.md` 交叉链 |
| **C2** | 数据真相源统一 | M | `v4.0.3` | **done（2026-10-10）** 确认 `daily_price`（`market.db`）为唯一历史行情真相源，派生库归属写明（引擎 `a-stock-engine.db` / `selections.db`、平台 `stock_platform.db`、引擎 `history/picks.db`）；**摄取归生产侧**、平台只读延续 ADR 0050；平台侧新增**覆盖守卫** `EngineSqliteProvider.coverage_snapshot` + `GET /api/ops/health.marketDb`（`thin` / `stale` / `empty` / `missing_table` / `error` → `degraded`）；实测破相已修复（2026-09-04~10-09 共 20 个交易日回补）；ADR 0058 + runbook `docs/ops/engine-market-db.md` |
| **C3** | 重复实现收敛清单 | M | 随 `S1` | **done（2026-10-14，由 `R2` 收口）** 列出选股引擎 / 回测引擎 / 行情抓取 / 多 Agent 的重复实现，逐项标注「保留 / 降级为参考 / 废弃」；不批量删除，按里程碑渐进收敛 |

**约束**：C 域只做「定边界 + 定归属 + 列清单」，**不在本路线图内执行大规模代码合并**。

---

### 3.7 R — 收尾与加固（Remediation，P0/P1）

**背景**：`G/B/S/X` 四域收官、`C` 域仅剩 `C3` 后，`v4.6.0` 体检暴露四类「非功能性、但直接决定平台可信度」的收尾项：
① `v4.6.0` 的名称根治只改了 `CHANGELOG`，**未落 ADR / 契约 / 路线图** —— 违反本仓「改行为必须同步文档」的硬规则；
② `C3`（重复实现收敛清单）是唯一未闭合的正式里程碑；
③ 绩效台账样本仅 **3** 条（`< MIN_MEANINGFUL_SAMPLE=20` = 噪音）⇒「这套推荐逻辑赚不赚钱」无法判断；
④ 日用循环缺一个「**今天是否自足**」的单点裁决面（现散落于 coverage 守卫 / `E1_ops_health` / 日报之间）。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **R1** | 名称权威与文档债收口 | S | `v4.6.1`（小） | **done（2026-10-14）** 新增 ADR `0072`（`symbol_master` 名称权威单点 + 回退语义）+ 契约 `docs/contracts/symbol-naming.md`（存储只存真名 / 展示走 `display_name` / 未知 `—`）；路线图补 `v4.6.0` 修订记录 + 本 R 域表；`check_docs` 登记两份新文档 |
| **R2** | `C3` 重复实现收敛清单 | S | `v4.6.2`（小） | **done（2026-10-14）** 新增 `docs/plans/duplicate-implementation-convergence.md`：逐项列 选股引擎 / 回测引擎 / 行情抓取 / 多 Agent 的重复实现，每条标「保留 / 降级为参考 / 废弃」+ 归属里程碑；**不删代码**（承接 C 域约束） |
| **R3** | 日用循环健康度单点 | M | `v4.7.0`（大） | **done（2026-10-14）** 新增 `research.loop_health` 单点 + CLI `stock-platform-loop-health`：聚合 六路信号（供数覆盖率·复用 C2 `coverage_snapshot` / 最新 brief / 命中记账 / 绩效 settled+pending / `symbol_master` 行数 / 下一个结算日提示）→ JSON + Markdown（+HTML）；`roll_up_verdict` 纯函数给 `ok/degraded/blocked` 裁决；零网络、只读、fail-closed、方法永不抛；ADR `0073` + 契约 `docs/contracts/loop-health.md`；真机实测裁决 `degraded`（供数滞后 2 交易日 + 绩效样本 3<20） |
| **R4** | 绩效代理样本增强 | M | `v4.7.1`（小） | **done（2026-10-14）** 新增 `research.performance_proxy`（`trades_to_decision_rows` / `write_proxy_ledger` / `build_proxy_view` / `render_proxy_markdown`）+ CLI `stock-platform-performance-proxy`：把**回测成交**翻译成与真实台账**逐字段同形状**的决策行（`source=backtest_proxy`），一个 ≥1 年长窗即产出 ≥`MIN_MEANINGFUL_SAMPLE=20` 条 settled；真实/代理**分栏陈列、禁止混算**（顶层无任何合并键，`comparability.combinable=false`）；两侧复用 `book_replay` 单引擎 + `performance_summary` 单算术；ADR `0074` + 契约 `docs/contracts/performance-proxy.md`；真机 1 年窗口代理 settled **83** vs 真实 **3** |
| **R5** | ETF 进宇宙与 ③A | L | `v4.8.0`（大） | universe / ③A 持仓榜支持 ETF（复用 B4 `asset_class` 单点）；`market.db` ETF 日线缺口由生产侧回补（平台只读）；缺口未补时 fail-closed 且显式标注 |

**约束（承接 C 域）**：R 域只做「补文档 + 补裁决面 + 补样本」，**不做大规模代码合并、不做 ETF 生产侧写库**；任何触库改动一律走既有只读路径。

### 3.8 T — 循环可信度与运营（Trust & Ops，P0/P1）

**背景**：`R3`（`v4.7.0`）已把日用循环五段信号聚合成**一个裁决**（`ok`/`degraded`/`blocked`），但裁决的**出口面与时间面**仍是空白：
① 裁决只在本地 `data/health/*` 落地，**Workbench 无出口**（人要看必须去翻文件）；
② 裁决是**当下快照**，无历史台账 ⇒ 分不清「持续退化」还是「偶发一次」；
③ 供数滞后与 **brief 缺日**都真实发生过（`2026-10-13`/`10-14` 连续两日无 bar → 覆盖守卫回落、brief 停在 `10-12`）；真机排查时**必须离开平台去翻 Windows 任务计划程序**，才发现 18:30 回补任务**压根没注册** —— 平台内**没有任何结构化的任务执行/回补记录入口** ⇒ 「到底是不是任务没跑」无法自证；
④ 数据侧只在 `X1`/`B4` 里**偶然发现**过单位口径（`pct_chg` 小数 vs 百分点）、ETF·指数日线缺口、原始池脏数据，**缺一份可复跑的体检**。

**定位**：T 域只做「**把已有信号接到人眼前 + 补执行台账 + 补数据体检**」，**不新增交易能力、不改任何选股/回测口径、不写行情库**（承接 ADR 0058 只读、C 域「只定边界」约束）。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **T1** | 循环健康度出口与趋势台账 | M | `v4.9.0`（大） | **done（2026-10-14）** Workbench 新增 `GET /api/ops/loop-health`（只读转发 `collect_loop_health`，**零业务逻辑**；供数段落在 `COVERAGE_HARD_FAIL` → 503 fail-closed，其余降级仍 200）+ `#health` 面板（导航「体检」：裁决徽标 + 六段表 + 近 N 天趋势 + 原始 JSON）；`loop_health` 增**趋势面** `history` —— `history.jsonl` 追加台账（`append_history`，fail-open、超 400 行裁剪）+ `read_history` / `summarize_history`（按 `asof` 去重、**含本次**）给出 `degradedStreak` / `blockedStreak` / `notOkStreak` / `streakSince` / `recent`；**`history` 不参与裁决**（裁决仍只看六路信号当下快照）；同轮修正 `coverage` 硬失败档 —— `error`（库不可读）/ `unconfigured` 曾在 `v4.7.0` 被误判 `ok`，现已并入 `COVERAGE_HARD_FAIL`；ADR `0075` + 契约 `docs/contracts/loop-health.md` 扩写（新增 §4.6 / §8）；真机实测裁决 `degraded`（brief 停更 + 真实样本 3<20，供数已恢复 ✅）、`degradedStreak=1` |
| **T2** | 调度与回补执行台账 + brief 连续性守卫 | M | `v4.9.1`（小） | **done（2026-10-14）** 新增 `research.ops_ledger` 单点 + CLI `stock-platform-ops-ledger`：append-only 台账 `data/logs/runs.jsonl`（`record_run` 唯一写、**fail-open**、`task` 为空拒绝、超 400 行裁旧）汇总「每任务最近一次 时刻/退出码/耗时/**连续失败** + 最近 N 次」（`read_runs` / `summarize_runs` 纯函数 / `collect_ops_ledger` 段形状，缺失 → `unavailable` fail-closed）；新增**调度包装器** `scripts/ops/Invoke-ScheduledRun.ps1`（任务预设 `daily` 08:30 / `postmarket` 15:30 / `marketdb-backfill` 18:30，**子进程**运行目标保证总能记行、best-effort 记账不改退出码、退出码原样透传），三个既有自动化已切到包装器；`loop_health` 增两路信号 —— `briefContinuity`（近 5 个**交易日**的 brief 覆盖，**缺日逐个列出** + `coverageRatio`）与 `opsLedger`（只读汇总）；**brief 缺日 / 任务连续失败 ≥2 次 → degraded**（观测面信号，**永不阻断**）；ADR `0076` + 契约 `docs/contracts/ops-ledger.md`；真机实测台账 `status=ok`、`briefContinuity` 标出 3 个缺日（`10-08`/`10-13`/`10-14`） |
| **T3** | 数据质量体检单点 | M | `v4.11.0`（大，**因 `Y1` 先落地而顺延**） | 新增 `research.data_quality` 单点 + CLI `stock-platform-data-quality`：**零网络只读**扫 `market.db` —— 单位口径一致性（复用 `pct_scale` 拟合投票，标出疑似 小数/百分点 混用的码）/ 停牌与零成交占比 / 除权跳变（`close` 单日跳变超阈值且无对应复权）/ 脏码（非 6 位码、ETF 前缀表外）/ 指数·ETF 覆盖缺口 → JSON + Markdown；并入 `loop_health` 作为**又一路**信号（严重项 → degraded，但**永不阻断**选股） |

**约束（承接 R 域 / C 域 / ADR 0058）**：T 域**只读** —— 体检与台账只读 `market.db`（`mode=ro`）与平台自有 `data/`；**不做生产侧回补、不写行情库**；面板不引入前端框架（手写 SVG，对齐 `B6` 口径）。

### 3.9 Y — 收益增强（Yield，P0）

**背景**：`G/B/S/X/C/R/T` 七域把**研究侧**做到了相当完整（回测可信、策略可迭代、选股可日用、循环可观测），
但**研究结论与生产默认档之间没有桥**。三个实测事实：

| 事实 | 数字 | 当时处置 |
|------|------|----------|
| `S4` 行业中性化 | `total_return` 0.3029 → **0.5257**、`sharpe` 1.06 → **1.14**（叠加 `max_per_industry=3` → **0.5850 / 1.2492**） | **只诊断不改档** |
| `S3` 闸门敏感性 | 出厂 `min_pick_score=0.80` 的 `sharpe` **1.060 是全网格最差**（`0.5/0.6/0.7` = 1.253/1.129/1.157） | **只诊断不改档** |
| `R4` 绩效代理（近一年） | `winRate=0.3735`、`avgReturn=−0.38%` | 记录，不处置 |

「不采纳」当时是**对的**（单窗口最优点可能是噪声），但由此产生更坏的结果 —— **没有任何机制**
能把「多窗口稳健成立」的改进送进生产 ⇒ 研究永远停在报告里，**平台不改进 = 赚不到钱**。

**定位**：Y 域做「**研究 → 生产的采纳闸门**」——只出**建议**，采纳是**独立的人工签核步骤**
（承接本仓「改行为必须同步 ADR / 契约 + 人工签核」硬规则）；**不改任何生产默认档**。

| ID | 名称 | 量级 | 目标 tag | 验收标准 |
|----|------|------|----------|----------|
| **Y1** | 策略采纳闸门 | M | `v4.10.0`（大） | **done（2026-10-14）** 新增 `research.adoption_gate` 单点 + CLI `stock-platform-strategy-adoption`：基线档（`neutralize=None` 的生产档）与候选档**共用同一引擎**（`run_neutralization_book` → `X4` 单点 `book_replay.replay_book`），在 `build_windows`（默认近 3 个**互不重叠**的 1 年窗口）各跑一遍；**特征只算一次**（全跨度 `prepare_book_frame` 含 `ma20`/`ma60` 预热后按日期 `slice_window` 切窗，边界**不损失**预热）；**事前登记** `AdoptionRule`（`min_sharpe_margin=0.05` / `max_drawdown_tolerance=0.05` / `max_winrate_drop=0.05` / `min_trades=8` / `require_all_windows=True`）+ **纯函数** `decide_adoption` 给 `adopt` / `reject` / `insufficient`（**样本不足不做结论**）；窗口 `pass` 需「夏普边际 + 回撤容差 + 胜率容差」**三项全过**，任一指标缺失判否；报告 `data/strategy/adoption_gate.{json,md,html}` 含逐窗 `blockingChecks`（落选原因可读）；**只出建议** —— `adoptionNote` 显式声明不动生产默认档；ADR `0077` + 契约 `docs/contracts/adoption-gate.md` |
| **Y2** | 采纳落地（命名档案 + 出厂档切换） | M | `v4.10.1`（**待人工签核**） | 把 `Y1` 判 `adopt` 的候选写进命名档案 / 出厂闸门常量；同步 ADR + 契约 + 权重**单点定义**；**无证据不落档、不签核不落档** |
| **Y3** | 收益归因 / 负收益根因诊断 | L | `v4.11.0`（大） | **done（2026-10-15）** 新增 `research.attribution` 单点 + CLI `stock-platform-attribution`：把一段窗口的亏损分解成**互不重叠、各自可处置**的少数几项原因（信号边缘 / 持有期错配 / 成本拖累 / 亏损集中度 + 赔率结构）。**两个样本集**（`gated` = 全部过闸、`picks` = 过闸且 ≥ 评分闸门=候选池）各算一遍曲线，差值即**评分闸门本身**的贡献；分值**逐日**在当日截面上打分（`score_lvrev` + `apply_entry_gates`，与生产 `screener_entry_provider` **同源**），成交侧用 `run_neutralization_book` 跑一次基线档。**两口径硬分**（真机教训）：**边缘类**结论读**超额** `meanExcess`（有没有技能），**持有期类**结论读**绝对** `meanReturn`（赚不赚钱）—— 两者不可混用，否则「熊市相对防守」会被误读成「长周期有效」而给出延长持有的**错处方**。`horizon_curve` 每行**同时**携带两个读数；`diagnose` 为**纯函数**（不碰 pandas/引擎），7 类原因码 + 事前登记阈值（`COST_SHARE_WARN=0.30` / `LOSS_CONCENTRATION_WARN=0.40` / `SPEARMAN_FLAT=0.05` / `PAYOFF_RATIO_WARN=1.0` / `WINRATE_WARN=0.50` / `MIN_MEANINGFUL_SAMPLE=20`），按「严重度 → `_CAUSE_RANK`（事前登记，impact 跨量纲不可比故**只作三级键**）→ |impact|」排序；样本不足的 horizon 标 `adequate=False` 且**不参与结论**；**单组分组永不构成「集中」**（`assetClass=stock` 恒 100% 的退化情形须显式跳过）；`reason` 按**规则名**分桶（`stop_loss(-8.1%)` 与 `stop_loss(-9.5%)` 同桶）；成交收益单位由**百分数归一为小数**（`TRADE_RET_SCALE=0.01`）。**只出归因**（`attributionNote`）—— **不改任何生产默认档、不写 brief / picks**；ADR `0078` + 契约 `docs/contracts/attribution.md`。**真机实测（近一年 `2025-10-14`~`2026-10-14`，universe=stock，`000905.SZ` 基准）**：`gated=33450` 行 / `picks=11663` 行 / 85 笔成交；**候选池绝对收益在 10 日见顶（+0.23%）后转负（20 日 −0.86%、40 日 −1.63%），而实际平均持有 32.5 天** ⇒ 主因 **`hold_too_long`**；次因 `edge_only_long_horizon`（5 日超额 −0.89%、仅 40 日 +4.77% —— **熊市相对防守**）、`score_weak`（Spearman=−0.015，接近无关联）、`concentrated_loss`（`stop_loss` 占亏损 94%）；`avgHold=32.5d` / `winRate=31.8%` / `avgWin=+9.57%` vs `avgLoss=−8.05%`（盈亏比 1.19）/ 成本仅占毛收益 2.7%（**不是**成本问题） |

**约束（承接 R / T 域 / ADR 0058）**：Y 域**只读行情**（`market.db` 仍 `mode=ro`）；
报告只写平台自有 `data/strategy/`；**不改生产默认档、不写 brief / picks、不做生产侧回补、不触实盘红线**。

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

C2 ← B1；C3 ← S1（C3 收口归 `R2`）
R1 ← `v4.6.0`（文档债）；R2 ← R1；R3 ← C2；R4 ← B1；R5 ← B4
T1 ← R3（复用 `loop_health` 单点）；T2 ← R3 + T1；T3 ← C2（复用 `coverage_snapshot`）
Y1 ← B5（规则单点）+ X4（回放单点）+ S3/S4（候选来源）；Y2 ← Y1（须签核）；Y3 ← R4（代理样本）+ X4（回放单点）+ S3（闸门口径）；Y3 → Y1（归因产出候选方向）
```

**关键路径**：`G1 → B1 → B5 → X4 → L1`。这条链上的每一项都是后者不可绕过的前置。

---

## 5. 版本映射建议

| 阶段 | 范围 | 建议 tag | 类型 |
|------|------|----------|------|
| G | G1–G3 | `v3.12.6`（G1+G2 合并） → `v3.12.7`（G3） | patch |
| B | B1–B6 | `v3.13.0` → `v3.13.6` | minor |
| S | S1–S5 | `v4.1.0` → `v4.1.5` | minor（目标 tag 顺延：X 域先于 S 域于 `v4.0.x` 收官；`v4.1.4` 由 `L1` 占用 → `S5` 顺延 `v4.1.5`）|
| X | X1–X4 | `v4.0.0` → `v4.0.4` | **major**（能力边界从 watch 扩到全市场） |
| C | C2（穿插） | `v4.0.3` | patch（数据治理：真相源统一 + 覆盖守卫） |
| R | R1–R2 / R3 / R4 / R5 | `v4.6.1` → `v4.6.2` / `v4.7.0` / `v4.7.1` / `v4.8.0` | patch（收尾/条款）与 minor（R3/R5 新能力）混编 |
| T | T1 / T2 / T3 | `v4.9.0` / `v4.9.1` / `v4.12.0` | minor（新能力）与 patch（加固）混编；**`v4.8.0`（`R5` ETF 进宇宙）被生产侧 ETF 回补卡住而顺延**；`T3` 两度顺延（先让 `Y1`、再让 `Y3`）至 `v4.12.0` |
| Y | Y1 / Y2 / Y3 | `v4.10.0` / `v4.10.1` / `v4.11.0` | minor（新能力：研究 → 生产采纳闸门、负收益归因）与 patch（落档）混编；**Y 域按完成顺序编号，`R5` 仍顺延** |
| L | L1–L3 | `v5.0.0` → `v5.0.2` | **major**（解禁实盘红线）；`L1` 为「立项（不解除能力）」故实际发布 `v4.1.4`，`v5.0.0` 保留给真正解除红线的那次（P1/P2 立项复核）|

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
| 2026-10-10 | **`X4` 完成（X 域收官）**：选股↔回测闭环 —— 逐日回放循环（复盘→盯市→建仓）抽成**唯一定义** `research.book_replay.replay_book`（`entry_provider` 多态：`screener_entry_provider` vs `picks_entry_provider`），两条路径只差入场来源、共用 B5 `rules` 与 B2 `portfolio` 单点；`backtest.run_portfolio_backtest` 转薄封装（新增 `prepare_book_frame` 共享 bars→特征帧），`picks_backtest.run_picks_backtest` 用**同一台引擎**跑推荐账本；`replay_book` 新增 `open_positions[]` 出口（窗口末仍持有仓位），`ok` 判据改为「已平仓 ∪ 未平仓」；picks 账本 append-only JSONL `{out}/picks_ledger.jsonl`（`(date,code)` 去重）＋流水线默认 `track_picks_ledger=True` 自动写 ②A 头部（best-effort）＋可选回放对照 `compare_picks_vs_screener`（`delta = picks − 回测`）；CLI `stock-platform-picks-backtest`；契约 `docs/contracts/picks-backtest.md` + ADR `0059`；**纯重构证据**：重构前 8 场景曲线/成交 sha256 fixture，**8/8 逐位一致**，另证同引擎（回灌 trades → picks 后 trades/曲线/指标/`open_positions` 逐位相等）；全量 **786 passed**；发布 `v4.0.4`。**X 域（X1–X4）全部收官，关键路径推进至 `L1`（实盘立项）前置就绪** |
| 2026-10-10 | **`G3` + `C1` 完成（G 域收官）**：文档与 CI 一致性 —— 自有主线路线图 `docs/plans/trading-system-roadmap.md` 挂进 `docs/ROADMAP.md` 顶部焦点区与 `docs/README.md`；`docs/plans/README.md` 陈旧状态刷新；**补齐 `check_docs.ps1` 的 `$required` 三处遗漏**（主路线图 / B3 里程碑 / 新 C1 文档，128→131）；CI `monorepo` job 确认（5 包 editable + `pytest packages apps`，`replay` 预设）。**`C1` 双线职责边界定稿**：新增 `docs/plans/dual-line-responsibility.md` —— 日常调度主链 = 引擎线（08:30 盘前 / 15:30 盘后）、历史行情真相源 = `market.db`·`daily_price`（平台只读）、产品/研究权威 = 平台线；5 组使用判据 + 数据归属表（承接 ADR 0058）+ 双方红线（平台不代抓不补写 / 引擎冻结新功能）；与路线图 / `ROADMAP` / `README` / ADR 0058 / `engine-market-db.md` 交叉链。发布 `v4.0.5`。**G 域（G1–G3）全部收官** |
| 2026-10-10 | **`S1` 完成（S 域开局）**：因子 / 闸门 A/B 完整版（U7 遗留）—— A/B 从「轻量 PIT 面板」升级为**同源引擎**：`strategy_ab.run_config_book` / `compare_strategy_ab_engine` / `compare_strategy_ab_from_bars` 两臂消费**同一特征帧**、跑**同一个** `book_replay.replay_book`（X4 单点定义），只由 `entry_provider` 区分；`StrategyConfig` 增 `gates`（`min_pick_score` 缺省 `0.80`，接受扁平别名）→ **闸门变更可表达**，`load_strategy_config` 接受裸 id（`<id>` / `<id>.json`）；每臂附 **`review` 复盘块**（`directionAccuracy` / `settledCount` / `pendingCount`，口径对齐 `performance`/U3，空仓不填 0）；`delta = B − A` + `sameDefinition` 身份块（`singleLoop`/`singleEntryProvider`/`singleMetrics`/`singleExitDefinition`）；Workbench 新增 `POST /api/research/strategy/ab-engine` + `#strategy-compare` 内「A/B 同屏」两列区块（指标 + Δ + 复盘表 + 双曲线，手写 SVG 零新依赖）；CLI `stock-platform-strategy-ab`；默认关闭旁路、不替换 picks；契约 `docs/contracts/strategy-ab.md` + ADR `0060`。**同源证据**：baseline 配置 vs `run_portfolio_backtest` 曲线/成交/指标/未平仓**逐位一致**，严格闸门臂入场数 ≤ 宽松臂；真机 `market.db` 1 年窗端到端（143 万行 / 6761 码 / 243 日，两臂 87 vs 93 笔）；聚焦测试 research 19 + workbench 145 全绿。发布 `v4.1.0`。**S 域（S1–S5）开局，下一块砖 `S2`（因子库扩展）** |
| 2026-10-10 | **`S2` 完成**：因子库扩展 —— 新增 `research.factors` 单点（`FACTOR_LIBRARY` / `FactorSpec` / `build_feature_frame` / `build_factor_frame` / `factor_correlation`），基线 `low_vol`+`reversal` 之外新增 `long_reversal` / `max_ret` / `illiq`；`factor_ic` 增 IC/ICIR 准入（`admit_factor`：`n_dates≥20` / `|IC|≥0.02` / `|ICIR|≥0.15` / **符号一致**，全过才启用）+ 正交选择（`select_enabled`：与已启用因子 `|ρ|≥0.70` 判冗余 → 不启用）+ `build_factor_ic_report`；`compute_features` 加 `keep_extra`（默认空，既有调用逐位不变）；`lvrev` 加 `W_S2` 且 `factor_scores` 补 `momentum`/`max_ret`/`illiq` 列（缺列填中性 0.5，默认权重 0 → 基线精确等价）；CLI `stock-platform-factor-ic` + API `POST /api/research/factor/admission`（只读 `market.db`，未知因子 400 / 无 DB 503）+ Workbench `#factor-library` 面板（判定表 + 启用/冗余/否决 + 相关矩阵）；契约 `docs/contracts/factor-library.md` + ADR `0061` + 实测 `docs/ops/factor-ic-benchmark.md`。**真机实测**（全周期 / 324 截面 / horizon 20）：`long_reversal` IC +0.033 / ICIR +0.198、`illiq` IC +0.077 / ICIR +0.798 **启用**（满足「≥2 个正交因子」）；`max_ret`（IC −0.094 / ICIR −0.572）与 `low_vol` 相关 **+0.876** → **冗余不启用**。聚焦测试 research 45 + workbench 146 全绿。发布 `v4.1.1` |
| 2026-10-10 | **`S3` 完成**：闸门参数敏感性 —— 入场闸门常量单点化 `gates.EntryGateParams`（frozen dataclass，默认值 = 原硬编码字面量逐字：`reversal_q=0.30` / `ma20_band=ma60_band=0.93` / `vol_filter=True`），`apply_entry_gates(df, reversal_q=None, *, params=None)` 三种调用路径**逐位相同**（`test_gates.py` 对 reference 循环的等价性测试为证）；`book_replay.screener_entry_provider` 增 `gate_params`（**同一** provider，不复制闸门；`reversal_q` 缺省 `0.30` → `None`，有效值不变）；新增 `research.sensitivity` 单点 —— `sweep_entry_gate`（单旋钮网格扫描，每点经 `book_replay.replay_book` X4 单循环 + 同一 provider；`feats` 由调用方建好后跨点复用，两点只差旋钮）+ `summarize_sweep`（**纯函数**：容差带 `sign·(obj−best) ≥ −tolerance×|best|`；`robustRange` = 含最优点且**连续**的一段网格；连续点数 `< min_plateau(2)` → `fragile`；`insufficient`（可用点 <3）/ `flat`（极差≈0）；`OBJECTIVE_DIRECTION` 登记方向，`max_drawdown→min`）+ `build_sensitivity_report`（多旋钮汇总，任一 `fragile` → `overall=fragile`）；CLI `stock-platform-strategy-sensitivity` + API `POST /api/research/strategy/sensitivity`（校验 400 先于 DB 503）+ Workbench `#sensitivity` 面板（判定表 + 逐点指标表 + 原始 JSON）；契约 `docs/contracts/gate-sensitivity.md` + ADR `0062` + 实测 `docs/ops/gate-sensitivity-benchmark.md`。**真机实测**（2024-09-02→2026-09-08，489 交易日 / 2.52 M 行特征帧 / 3 旋钮 × 5 点 = 15 次回放 / **182.7 s**）：`min_pick_score` **robust**（`0.5`/`0.6`/`0.7` sharpe 1.253/1.129/1.157 全在 10% 容差内 → 稳健区间 **3 点**）；`reversal_q` / `ma_band` **fragile**（各仅最优点达标）→ `overall=fragile`；出厂值 `reversal_q=0.30`（sharpe 1.060）/ `ma_band=0.93`（1.060，**全网格最差**）/ `min_pick_score=0.80`（1.060）均**不**是最优、也**不**据孤峰改档 —— 正是「避免过拟合单点」。聚焦测试 research 45 + workbench 147 全绿。发布 `v4.1.2` |
| 2026-10-10 | **`S4` 完成**：行业中性化 / 风险暴露 —— 新增 `research.neutralization` 单点（`NeutralizeParams` frozen dataclass：`industry_col` / `mode`(`demean`|`zscore`) / `clip` / `min_group_size` / `rescale`(`rank`|`none`) / `composite_demean` / `style` / `style_clip`）＋ `industry_neutralize_series` / `neutralize_factor_scores` / `residualize` / `resolve_groups` / `attach_industry` / `industry_exposure`；**语义承接** `a-stock-engine/src/factor_engine.py` 的 `_zscore`（行业分组 Z-Score：组内 mean/std、`clip(lower=0.001)`、截断 ±3）与综合分 `raw − groupby(sector).mean()`，但作用面改为 `[0,1]` 因子分并用 `rescale="rank"` 把尺度还原（**下游 `min_pick_score` 语义不变**）；`lvrev.score_lvrev(..., neutralize=None)` **默认关 → 组合分逐位不变**（等价性测试为证）；行业只读接入 `backtest_cli.load_engine_industry()`（`fundamentals(code, industry)`，缺表 **`KeyError` fail-closed** 而非空表），`code` 两侧经 `portfolio.norm_code` 归一 —— 实测 `daily_price` 为 `000001.SZ`、`fundamentals` 为 `000001`，**原始交集 0**，不归一则 join 全空；`attach_industry` 未映射 → `__UNKNOWN__` 独立组；透传链 `prepare_book_frame(..., industry_map=None)` + `screener_entry_provider(..., neutralize=None, max_per_industry=None)`（**同一 provider，不复制闸门/评分**）；暴露约束 `max_per_industry` 在 `max_picks_per_day` 之前按行业 `head(k)` 并按 `composite_score` 重排；A/B 单点 `research.neutralization_ab`（`compare_neutralization_ab` / `neutralization_ab_from_bars` / `run_neutralization_book`）两臂同一 `replay_book`，`delta` / `review` / `sameDefinition` **直接 import `strategy_ab`（`S1`）实现**，另附各臂行业暴露画像（`n_codes` / `n_industries` / `max_weight` / `max_industry` / `hhi`）；CLI `stock-platform-strategy-neutralization` + API `POST /api/research/strategy/neutralization`（校验 400 先于 DB 503）+ Workbench `#neutralization` 面板；契约 `docs/contracts/industry-neutralization.md` + ADR `0063` + 实测 `docs/ops/neutralization-benchmark.md`。**真机实测**（2024-09-02→2026-09-08，489 交易日 / 2,949,567 行 / 6,789 码 / 111 行业 / 两轮合计 95.9 s）：仅中性化 `total_return` 0.3029→**0.5257** / `sharpe` 1.0599→**1.1430** / `final_equity` 65,146→**76,287**，但 `max_drawdown` -0.1767→**-0.2673**、`win_rate` 0.4659→**0.3839**、笔数 176→224；叠加 `maxPerIndustry=3` → `total_return` **0.5850** / `sharpe` **1.2492** / MDD -0.2423；**持仓集合 HHI 反升 0.0225 → 0.0302**（+cap 0.0312）—— 「中性化 ≠ 更分散」，如实记录；`raw` 臂两轮**逐位一致**（两臂只差处理项的直接证据）；出厂 `W_DEFAULT` / `min_pick_score=0.80` / `EntryGateParams()` **逐位未改**（只诊断不改档）。聚焦测试 research 新增 28 passed、workbench **185 passed**（端点目录 64 → **65**）。发布 `v4.1.3` |
| 2026-10-10 | **`L1` 立项（`Proposed`，待显式确认）**：实盘立项与券商选型 ADR `0064` —— 券商选定 **华宝证券（国内）**（落选：富途 / 其它港美股通道，跨境与外汇合规复杂度 + 1 万本金下无意义；同花顺真机通道不在本轮边界内）；资金上限 **1 万元（账户总资产口径，含现有持仓）**，禁融资融券 / 场外配资；**合规边界 = Phase 0 纯模拟盘，本次明确不解禁红线**（`liveTradingEnabled` 维持恒 `false`、`L2`/`L3` 不开工、`execution/profile.py` 的 `ProfileBlocked` 硬闸零改动）。**关键结论**：华宝 `QMT`/`PTrade` 终端门槛 ≈ **10 万**（近 20 交易日日均证券资产）+ 6 个月 A 股经验 + 风险测评 C4/C5 → **1 万拿不到终端 → 不能自动下单 → 法定定义上不算程序化交易 → 免报备**，故 P0 是当前唯一零合规暴露路线。另交付：**三阶段解锁条件表**（P0 纯模拟 / P1 半自动人工·免报备 / P2 `QMT` 全自动·必须报备）、**解除红线影响面清单**（≈37 源文件 + 21 测试文件 + 3 份契约 + 路线图红线第 7 条）、**失败回滚方案**（P2「状态未知」一律人工介入）、**版本映射建议 `v4.1.4`**（`v5.0.0` 保留给真正解除红线的那次）。契约 `docs/contracts/compliance-boundary.md`；登记 `check_docs.ps1`（files 142→144）。**红线第 7 条继续有效。** |
| 2026-10-11 | **`L1` 收口（`Accepted`）**：实盘立项与券商选型 ADR `0064` 由 `Proposed` 置 **`Accepted`**（2026-10-11 经用户确认，路线图 §3.5「显式确认后才置 Accepted」要求已满足）—— 券商 = **华宝证券（国内）**、资金上限 = **1 万元（账户总资产口径，含现有持仓）**、合规边界 = **Phase 0 纯模拟盘，本次不解禁红线**；契约 `docs/contracts/compliance-boundary.md` 同步置 `Accepted` 且 §5 **P0 名义参数确认沿用**（单笔 ≤ 总资产 20% / ≤5 笔·日 / 深回撤 ≥15% 熔断 / 排除 ST·次新·B 股·北交所）；**版本映射落定 `v4.1.4`**（`v5.0.0` 保留给真正解除红线的那次；`S5` 若开展顺延 `v4.1.5`），发布 `v4.1.4`。**红线第 7 条继续有效。** |
| 2026-10-11 | **`S5` 完成（S 域收官）**：LLM 辩论进主路径 —— **只读顾问侧车**。新增 `agents.debate_lane` 单点（`off`/`deterministic`/`llm`，默认 `off`；未知名 → 400；`attach_debate_lane` **只读** brief）+ `LlmBudget` 公开化（显式预算覆盖环境变量）+ 主链**依赖注入**挂载（`run_daily_pipeline(debate_runner=...)`，research 不依赖 agents）+ `{asof}/debates.json` + CLI `--debate-engine` + API `POST /api/research/daily/debate`；**「误判不进绩效」由测试锁成不变量**（开/关两轮 `brief.json`/`picks_ledger.jsonl`/命中块逐位相等）；不新增手动 UI 面板（与既有 `TopN 辩论` 重复）；契约 `docs/contracts/debate-lane.md` + ADR `0065`；发布 `v4.1.5`。**S 域（S1–S5）全部收官；下一块砖 = `C3`（重复实现收敛清单）或 `L2`/`L3`（须 `L1` 指定 P1/P2 解锁）** |
| 2026-10-10 | **生产可用 P0 修复（`P0-1` / `P0-2` / `P0-3`）**：真机端到端跑测暴露两个 P0 阻塞 —— **① `run_refresh` 是双层串行同步 HTTP**（307 只样例实测 11m48s、CPU 仅 9.7s → 100% 网络 I/O → 外推全市场 5213 只 ≈ **3 小时**，08:30 盘前不可行），**根因不是并发不足而是用 HTTP 重新拉取已在本机 `market.db`（ADR `0058` 真相源）的数据**；**② CLI 不加载 `.env`**（`daily_cli` 直读 `os.environ`，全仓仅 `start-workbench.bat` 注入 → 真机 `live provider='cn_tushare_http' requires STOCK_PLATFORM_TUSHARE_TOKEN`、exit 1；`schtasks` 不注入环境变量 ⇒ 每日自动化**必然**失败）。**修复**：① 新增离线批量 provider `MarketDbBulkProvider`（`capabilities={"daily"}`、`bulk_daily` 一趟分块 SQL `_CHUNK=900`、代码归一复用 X1/ADR`0055` 单点、零网络）+ `run_refresh` 增 `workers`/`min_interval`/`bulk`/`persist`（**默认串行/持久化不变**；`RateLimiter` 跨 worker 共享锁、**提高并发不得越过上游节流**；`_bulk_daily_allowed` 单点判定、数据集不支持即 fail-closed）+ `daily_pipeline._effective_datasets` 能力裁剪（provider 未声明 capabilities → 行为不变）；② 新增 `research.dotenv` 单点（路径优先级 显式 > `STOCK_PLATFORM_DOTENV` > 仓库根向上 > cwd；**默认不覆盖**进程变量；**pytest 守卫**防真实 `.env` 泄漏；`force=True` 供自测）接入 **14 个 CLI**。**真机实测**：全市场 refresh **115 s**（带 JSON）/ `persist=False` ≈ 秒级；`daily_cli` 端到端 **12.78 s**（快路径）vs 129.94 s（带持久化）；`Invoke-DailyPipeline.ps1 -MarketDb` **14.78 s** —— 较外推 ~3 h 约 **94×–700×**；`.env` 自动加载验证 token 自动读取、`TushareHttpProvider()` 免手动 export 构造成功。契约 `docs/contracts/refresh-throughput.md` + `docs/contracts/dotenv-loading.md` + ADR `0066`；`docs/ops/scheduler.md` 更新至 `-MarketDb` 快路径（含 venv 优先 python、`-MarketDb` 开关、`ExecutionTimeLimit=PT15M`）；登记 `check_docs.ps1`（files 146→149）。全量 `pytest packages apps`（`replay`）**927 passed / 0 failed**（887→927，**+40**）；发布 `v4.1.6`。**生产可用前置已就绪；下一块砖 = 注册每日调度（8:30 盘前 / 15:30 盘后）+ 用户可读日报 + 绩效 PnL 闭环** |
| 2026-10-10 | **生产可用 P0 修复续（`P0-4`，线上路径回归）**：`v4.1.6` 收口后跑**真实 `cn_tushare_http` 每日流水线**，在 `stage: "refresh"` 失败。**两个独立根因**：**① 能力声明缺口** —— `_effective_datasets` 原仅认 provider 的 `capabilities` 属性，而线上 HTTP provider（`tushare_http`/`cn_tushare_http`）**只实现 `get_daily`、不声明任何能力** → 流水线请求全部 4 个数据集、每只票失败 3 个、整轮 fail-close；此前真机验证只覆盖 `market_db`（自带 `capabilities`）故回归静默上线。**② fail-closed 粒度错** —— `RefreshReport.ok = all(i.ok for i in items)`：单只薄票即否决整轮，而下游 `panel.py` 本就容忍空数据（空 frame 跳过、严格 PIT 只要求 `asof` 当日有 bar）。**修复**：① `_declared_capabilities` 四级解析（`capabilities` → `supports()` → **`name` 反查能力注册表** `build_capability_matrix()`（唯一真源，不重抄表）→ `None`），**解析为空一律当 `None`（永不静默收窄到零数据集）**；② 新增缺口语义 `RefreshItemResult.is_gap`（`EMPTY_BARS_MARKER` 仅对 `daily` 抛 + `TOLERABLE_GAP_DATASETS={"daily"}` 单点）+ `RefreshReport.tolerate_gaps/gaps/hard_failures`，`ok = bool(items) and not hard_failures`，`to_dict()` 增 `tolerateGaps`/`gapCount`/`gaps[]` 且 `failures[]` **只列真失败**；**缺口永不遮蔽真失败**（测试锁死）。CLI 开关 `daily_cli --refresh-tolerate-gaps|--no-refresh-tolerate-gaps`、`refresh_cli --tolerate-gaps|--no-tolerate-gaps` + 环境变量 `STOCK_PLATFORM_REFRESH_TOLERATE_GAPS`，优先级 **显式 flag ＞ 环境变量 ＞ 默认 `True`**；`GAP ...` 逐条写 stderr（别于 `FAIL`），退出码仍 0。**真机实测**：`510300` 在 `market.db` 仅 65 行、最后 bar `2026-09-08`（C2 ETF 退化）→ `lookback=5` 默认档 `ok=True gapCount=1 failCount=0`（**整轮存活**）/ 严格档 `ok=False failCount=1`（**旧行为保留**）/ `lookback=120` 两档 `ok=True`；`run_daily_pipeline`（`market_db` 快路径 + 3 标的含薄票）→ `ok=True stage="brief"`；`refresh_cli --provider market_db` 真机 `{"ok":true,"failCount":0}`（`.env` 自动加载）。更新契约 `docs/contracts/refresh-throughput.md` 至 `v4.1.7`（新增 §5 能力解析、§6 缺口 vs 真失败、§7 补有界跑数字）。全量 `pytest packages apps`（`replay`）**942 passed / 0 failed**（927→942，**+15**）；发布 `v4.1.7`。**下一块砖仍 = 注册每日调度 + 用户可读日报 + 绩效 PnL 闭环** |
| 2026-10-12 | **WorkBuddy MCP 桥接 + workbuddy 模式启动（数据源接入）**：发现 `workbuddy` provider **只读 JSON 缓存、但写缓存的那一半（"MCP bridge"）从未实现** —— 预设能启动、能路由，却永远拿不到真实数据。**补齐**：新增 `stock_platform_research.workbuddy_bridge` 调 **`westock` CLI**（WorkBuddy `finance-data` 插件自带 SHA256 校验安装的 Go 二进制，实测 `v0.0.4`）取 `kline`/`quote`，解析其 Markdown 表后经**已有的规范写入器** `write_daily_cache`/`write_realtime_cache` 落盘（**schema 单点**，不重拼 JSON）。字段映射：`last`→`close`、`change_pct` 带 `pct_unit="percent"`（÷100）、**`exchange` 丢弃**（是换手率 %，非交易所代码）。批量按 40/30 一批合并调用。**三条守卫**：① 多代码批出现无 `code` 列的行 → 告警并跳过（只有单代码批允许无列归因）；② **裸码碰撞**（`sh000001` 指数 vs `sz000001`，平台 `normalize_symbol` **有意丢弃交易所前缀**故都归一 `000001`）→ 抓取前**拒绝**歧义对；③ 显式 `--bin` 路径不存在 → 报错，绝不静默回落 PATH。**启动**：`daily_cli --provider` 直接接受 `workbuddy`（预设**不足以**让 daily 走 workbuddy —— `Invoke-DailyPipeline.ps1` 显式传 `--provider replay` 会覆盖 `STOCK_PLATFORM_PROVIDER_PRESET`，实测确认）+ `scripts/ops/Invoke-WorkbuddyBridge.ps1`（两步编排：bridge → daily）+ `start-workbuddy.bat`（双击版）。**真机实测**：桥 8/8 ok / 124 bars；往返 → provider **90 契约行** 跨度 `2026-08-21→2026-10-09`；percent→decimal `0.5741405808→0.005741405808`；碰撞守卫告警并跳过；全链路 daily `provider="workbuddy" ok:true`。契约 `docs/contracts/data-source-adapters.md` §1.4/§4.1 + ADR `0067`；全量 **972 passed**（943→972，+29）；发布 `v4.1.8`。**下一块砖仍 = 注册每日调度 + 用户可读日报 + 绩效 PnL 闭环** |
| 2026-10-12 | **每日调度正式上线 + 用户可读日报（v4.2.0）**：① **双任务注册** —— 盘前 `stock-platform-daily`（08:30，`-MarketDb -PrevSession -Digest`）+ 盘后 `stock-platform-postmarket`（15:30，新 XML，`-MarketDb -PrevSession -SettleAfter -Digest`）；`Register-ScheduledTasks.ps1`（注册/`-Status`/`-Unregister`/`-RunNow`，幂等，当前用户无需管理员）；**实测调度器按需触发 `result=0x0`**，整市 brief（5210 行截面/Top10）+ digest 全链产出。② **`-PrevSession`**：asof 解析为前一交易日 —— market.db 晚间回补，早/午后绝无当日 bar（asof=2026-10-12 废 brief `panelSize=0` 即此因）。③ **用户可读日报**：`daily_digest.py` + CLI `stock-platform-digest`，从权威 SQLite brief 仓库渲染 Markdown（推荐表/五榜/命中追踪 X3 单点/绩效计数）→ `data/digests/{asof}.md` + `latest.md`；fail-closed 占位不编造；`-Digest` 接入包装脚本，渲染失败不翻转退出码。④ 两个实测注册坑入档：PS 5.1 GBK 误读 UTF-8 XML（→ `ReadAllText`）与 `-Xml` 拒绝编码声明（→ 剥 `<?xml ?>`）。新增测试 +8（digest）；发布 `v4.2.0`。**下一块砖 = 绩效 PnL 闭环（performance JSONL → 用户可见收益归因）** |
| 2026-10-12 | **绩效 PnL 闭环（v4.3.0）**：把 `performance` JSONL 从「计数」推进到**用户可见收益归因**，回答"这套推荐逻辑赚不赚钱"。**根因定位（实测）**：① 3 条 pending **从未被结算**（盘后任务刚注册、尚未自然运行；**非**窗口/数据问题 —— 手工结算 `_holding_window` 对三条都取到合法 entry/exit）；② `alpha` 结构性恒 `null` —— `settle_pending_entries` **只在调用方传 `alpha_returns` 时才写**，而三个调用方**无一处构造基准**；③ `daily_cli` 以 `holding="1d"` 记账、其余处默认 `5d` → 口径漂移。**修复/新增**：① **基准 alpha** `alpha = raw − benchmark`，基准默认 **中证500 `000905`**（`market.db` **无** `000300`；`000905`/`000852` 完整、`000016` 止于 2026-09-30、`510300.SH` 仅 65 行）+ env `STOCK_PLATFORM_BENCHMARK_SYMBOL` 覆盖；`raw`/`alpha` 共用**同一** `_holding_window`（`_close_on_or_before` 按 entry/exit 日期取基准收盘）；② **alpha 回填**（已结算但 `alpha=null` 的历史行在下一次带基准结算中补齐，`alphaSettledNewly`）；③ **归因单点** `build_attribution`（`winRate`/`avgReturn`/`avgAlpha`/`beatBenchmarkRate` + `byRank`/`byScore`（等数量分桶）/`byDate`/`equityCurve`）并入 `performance_summary`（旧键不变）；④ **持有期单点** `DEFAULT_HOLDING="5d"`（`daily_cli` 不再写 `1d`）；⑤ **日报显示真数字**（`daily_digest.performance_summary` 增 `returns`，复用 research 单点 口径）。**真机实测**（真 `.env` + 真 `market.db`）：3 条 pending → `settledNewly=3`（`600519 +0.38%` / `300760 +2.96%` / `000001 -1.76%`）；同台账再结算 `alphaSettledNewly=3`（`+2.41%` / `+4.99%` / `-7.72%`）；`direction_accuracy` 0.667 / `avgReturn` +0.53% / `avgAlpha` −0.11% / `beatBenchmarkRate` 0.667；日报「绩效台账」出现「收益概览（已结算 3 条 / 基准 000905）…」。契约 `docs/contracts/performance-pnl.md` + ADR `0068`（ADR `0033` 补「修订」节）；登记 `check_docs.ps1`。全量 `pytest packages apps`（`replay`）**988 passed / 0 failed**（980→988，**+8**）；发布 `v4.3.0`。**下一块砖 = 让 PnL 闭环在真实每日循环里自然累积（盘前记账 / 盘后结算）+ 首个自然结算样本落地** |
| 2026-10-12 | **测试数据隔离 + 日报修复（v4.3.1）**：验收「真实每日循环」时发现**用户可见日报是空的**，而库里明明有真实 brief。**根因**：① `test_daily_pipeline.py` 的 `test_daily_cli_settle_after_logs_performance` 驱动**整个 CLI** 却**没钉 `STOCK_PLATFORM_DB_URL`**（只钉了绩效台账）→ CLI 走 cwd 默认路径 + `persist_db=True`，把 fixture brief（`universeSize=3`，`asof=2026-09-02`）**upsert 进生产存档**，并写命中；证据 = 该行 `updated_at` **精确等于全量测试的墙钟分钟**，且仓库内**无任何 `conftest.py`**；逐文件「跑 pytest + 前后哈希」在 15 个候选里**精确指认到该文件**。② **日报被遮蔽**：被写的 `asof=2026-10-12` 行（`picks=[]`）日期最新 → `list_recent(limit=1)` 取到它 → 「当日推荐（0 条）」，真实 brief（`2026-10-09` / 5235 只 / 10 picks）**没被删、只是被遮蔽**。③ `hit_summary`（日报读它）与 `hit_tracking` 是**两张表**，只清明细仍有 fixture 代码残留。**修复**：① 仓库根 `conftest.py` 在 import 时重定向两个存储到会话临时目录（`atexit` 还原）；② 驱动 CLI 的测试**额外自钉**存储位置；③ 回归测试 `test_session_never_resolves_the_repo_data_dir`（守卫被删即变红）；④ 清理污染行（**先备份 + 断言只删 `universeSize==3` + 独立只读连接复核**）。**顺带确认**：`_ensure_schema()` 与只读**不改文件**（哈希三次不变）→ 文件哈希变化 = 真实写入的可信信号；全仓**不存在任何行删除路径**（`DELETE FROM`/`DROP TABLE`/`unlink`/`rmtree` 零命中）→ 归档只增不删。**实测**：全量 **989 passed**（988→989，+1），四类存储行级**逐位不变**；真实 brief 恢复渲染（`2026-10-09`，命中追踪 10 只，绩效台账 13 条 = 待结算 10 / 已结算 3）；**首次由自动化路径**（盘后 `-SettleAfter` 而非手工）自然落 10 条 pending（`settleAfter.logged=10`、`settleSource=settle_cli`、全市场 refresh 5235 只 0 gap / 0 fail，12.5 s）。ADR `0069`。**下一块砖 = 等生产侧回补 `≥ 2026-10-16` 的 bar，验收第一个无人值守 `settledNewly > 0`** |
| 2026-10-12 | **日常循环自足（v4.4.0）**：真实循环验收暴露三个各自独立、又同属「无人值守循环不自足」的缺口，一并焊死。**P1 供数链路无守卫（危害最大）**：`stock-platform-daily`（08:30，`-PrevSession`）asof 解析为前一交易日，但本机**无任何行情回补任务**，一旦生产侧没写该日 bar，后果不是报错而是**静默写出一份空 brief**（`asof` 最新 → `list_recent(limit=1)` 取到它 → 遮蔽上一份真 brief，早上看到「当日无推荐」而真相是「数据没到」）。**修复**：覆盖率守卫放**运维层**（`Invoke-DailyPipeline.ps1`，不进 CLI——CLI 还要服务 replay / fixtures / 测试），**复用 C2 单点** `EngineSqliteProvider.coverage_snapshot()`（`ok\|thin\|stale\|empty\|missing_table`，**永不抛**），只看「解析出的 asof 本身是否可用」：可用→照常 / 不可用→**回落 `latestTradeDate` + WARN** / 回落目标也不可用→**退出 1 拒绝写 brief** / `-StrictCoverage`→不回退直接失败。**成因端**新增 `Invoke-MarketDbBackfill.ps1`（包一层引擎自己的 `empirical/backfill_market_daily.py`，幂等 + CPU-safe）+ `stock-platform-marketdb-backfill.xml`（每日 **18:30**，`PT20M`）+ `Register-ScheduledTasks.ps1 -Backfill`；**边界不变**：写库仍是引擎脚本、平台仅只读（ADR 0058）。**P2 输出只有代码没有中文名**：`backtest_cli.load_engine_names()`（读 `fundamentals.name`，**fail-open** 区别于行业列的 fail-closed）+ `daily_cli._build_name_map()`（key 归一到 6 位核）→ `run_daily_pipeline(name_map=…)` → `build_premarket_brief` / `build_rankings` / `_display_name`；**只有确实取到名称时才写 `item["name"]`**，取不到**不写键** ⇒「无 map」与「有 map 但未命中」两条路径下 brief / picks ledger / 命中周期 / 绩效 JSONL **逐字节不变**（与 ADR 0065「误判不进绩效」同一保守姿态）；日报推荐表新增「名称」列。**P3 持仓从没进日报视野**：`Invoke-DailyPipeline.ps1` 新增 `-Holdings` / `-NoHoldings`，默认探测 `data\holdings.json`（存在则追加 `--holdings`，不存在则不传 → ③A / ③B 保持空，fail-closed 不猜）；`data/` 已 gitignore ⇒ 真实持仓天然不入库、**XML 零改动**。**附带加固**：会话级测试数据隔离守卫不自愈（一个测试 `os.environ.pop` 即让后续全回落仓库 `data/`，fixture 残留 2+2 行又回来）→ 改为 **autouse 函数级 fixture 每测试前重新断言**（ADR 0069 修订），污染行按 ADR 0069 同款流程清除。**实测**：守卫 `asof=2026-10-12`（已回补 / 5224 行）`COVERAGE ok`；`asof=2026-10-13`（超库尾）回落 `latestTradeDate=2026-10-12` 且 `EXIT=0`；同输入 `-StrictCoverage` → `Write-Error` + `EXIT=1`；日报重渲染推荐表与五榜全带中文名（`000801 四川九洲` / `601318 中国平安` 等）；全量 `pytest packages apps`（`replay`）**995 passed / 0 failed**（989→995，**+6**），四类生产存储**逐位不变**。ADR `0070`。发布 `v4.4.0`。**下一块砖 = 等生产侧回补 `≥ 2026-10-16` 的 bar，验收第一个无人值守 `settledNewly > 0`；可选：命中追踪历史行名称回填 / ETF 进 ③A 的既有限制** |
| 2026-10-13 | **报告 HTML 化（v4.5.0）**：把「Markdown 报告 → 本仓报告模板样式」抽成**唯一单点**。**动机**：平台所有报告先写 Markdown（对 agent / diff 友好），但人要看的是有样式的一页；仓内已有观感基准 `static/report-templates/a-share-preopen.html`（深色面板 + 金色 accent + **A 股红涨绿跌**），而产出侧**没有出口**（digest / rankings / hits / performance 只写 `.md`），跑批器还自带一份**配色不一致的私有浅色渲染器**。**新增** 零依赖渲染器 `research/report_html.py`（`markdown_to_body` / `render_report_html` / `render_markdown_file`）：仅 stdlib（本机**无 markdown 库**、且不可为此加依赖），**先 `html.escape` 再套标签**，畸形输入 fail-open；`LOCAL_THEME` 的 `:root` token 与报告模板**逐 token 相同**（`--bg:#0b0e14` / `--accent:#4d8dff` / `--gold:#f5c451` / `--up:#ff4d4f` / `--down:#00b578`），并有测试**直接读模板比对**防漂移；行内带符号百分比按 A 股约定自动着色（`(?<![\w>])` 反向断言避免误吞 `2020-2026` 这类区间），`colorize=False` 可关；**未知主题名回落 `local`，永不抛**。**新 CLI** `stock-platform-report-html`（`--in` / `--dir` / `--title` / `--subtitle` / `--source` / `--badge` / `--theme`）可一键把任意历史 `.md` 重渲染成模板样式。**digest 默认双格式**：CLI 默认写 `{asof}.html` + `latest.html`（`--no-html` 退回只写 md），`build_digest(emit_html=…)` 库默认仍 `False`（纯增量、旧键全留）⇒ 两个计划任务与 `Invoke-DailyPipeline.ps1 -Digest` **零改动**即开始出 HTML。**跑批器改用单点**（删掉私有 `_CSS` / `md_to_html`，import 同一模块）。**实测**：`test_report_html.py` **8 项全过**；历史报告按新主题**重渲染**，每项 `.md` + `.html` 同目录、离线可开（无 CDN / 无外链）。ADR `0071`。发布 `v4.5.0` |
| 2026-10-13 | **日报「同花顺导入」行（v4.5.1）**：盘前日报（digest）在「当日推荐」顶部新增可**整块复制**的 6 位代码块，直投同花顺手机版「自选 → 导入」。**约束**：同花顺手机版**一次仅支持导入 5 只** ⇒ 按 5 只/行分组（`THS_IMPORT_PER_LINE = 5`），超出自动换行、逐行粘贴（10 只推荐 → 两行）；代码归一化为 6 位裸码（去 `.SZ` / `.SH`，**仅保留合法 6 位码**，脏码不进城）、按推荐序去重、无有效代码则整块省略（fail-closed）。Markdown 与 HTML 双份同步生效（代码块 → `<pre><code>`）。`test_daily_digest.py` **+4 项**（导入行 / 12 只按 5 分 3 行 / 后缀剥离 / 无推荐省略）。发布 `v4.5.1` |
| 2026-10-13 | **同花顺导入文件 txt（v4.5.2）**：用户实测同花顺「导入自选」支持**选择 txt 文件**（比手机端逐行粘贴省事），故把当日推荐再落成**文件**。新增单点 `daily_digest.write_ths_import(codes, *, asof, out_dir)` → `data/ths_import/{asof}.txt` + `latest.txt`（**每行 1 个 6 位码**、无表头无名称，纯 ASCII 数字）。代码归一化**复用 `_ths_codes`**（与日报导入行同源，同一去重/6 位裸码规则）；`build_digest` 新增 `emit_ths`（**库默认 `False`**）+ `ths_dir`，CLI 默认产出（`--no-ths` 退回、`--ths-dir` 覆盖）；目录默认取 digest 目录的**同级** `ths_import`（`data/digests` ↔ `data/ths_import`）。无推荐则不产出（fail-closed，不生成占位文件）；并清理目录内遗留 `*.sel`（项目统一只用 txt，此前试写的二进制 `.sel` 已废）。`Invoke-DailyPipeline.ps1 -Digest` 零改参即产出（语义只增），并设 `PYTHONIOENCODING=utf-8` 保日志编码。`test_daily_digest.py` **+7 项**。发布 `v4.5.2` |
| 2026-10-14 | **名称映射根治 + 当日战绩（v4.6.0）**：① **本地 code↔name 主表 `symbol_master`**（源=引擎只读 `market.db.fundamentals`，实测 **5237/5237** 全覆盖；表存平台 SQLite、与 brief 归档同库；`display_name()` 为名称解析**唯一入口**，优先级 = 记录真实名 > 显式 `name_map` > 本地表 > 占位 `—`；`daily_cli` 每跑批顺带刷新（失败静默）；`stock-platform-hits --backfill-names` 修历史脏行，实测修 **14 条 `hit_summary` + 20 条 `hit_tracking`**、0 残留）。**根因**：`hit_tracking._clean_name()` 名称缺失时**回退成代码**，且 `UNIQUE(code,session_type,pick_date)` 去重使后续跑批的名称**永远写不回去** ⇒ 存储层只存真名（未知存空、绝不写代码）、展示层统一走 `display_name`（未知显示 `—`）。② **当日战绩报告（选股 → 次日收盘 · 1 日窗口）**：新增 `research.sameday` + CLI `stock-platform-sameday`（`summarize_sameday` / `render_sameday_markdown`），复用 `brief_review` 单点，报告位 `A5_sameday`；`rolling_review` 同步补齐 `avgRawReturn` / `upRate` / `best` / `worst` / `avgAlpha` / `beatBenchmarkRate`（纯新增键、旧调用不变）。③ panel CSV 前导零单点 `batch.load_panel_csv()`（`symbol`/`code`/`ts_code` 固定 `dtype=str`）。新增测试 **22** 项（`test_symbol_master.py` 12 / `test_sameday.py` 4 / `hit_tracking` 名称回归 6），全量 **1037 passed**。**遗留（由 `R1` 偿还）**：未落 ADR / 契约 / 路线图 —— 违反本仓「改行为必须同步文档」硬规则 |
| 2026-10-14 | **R 域开局（收尾与加固）**：新增 **R — 收尾与加固** 域（`R1` 名称权威文档债 / `R2` `C3` 收敛清单 / `R3` 循环健康度单点 / `R4` 绩效代理样本 / `R5` ETF 进宇宙），把「v4.6.0 未落 ADR/契约」的文档债、唯一未闭合的 `C3`、绩效样本不足（3 条 < 20 = 噪音）与循环裁决面缺失四个收尾项显式立项；`release_tag.ps1` 增加 `-MessageFile`（UTF-8）以支持中文 tag 注释 |
| 2026-10-14 | **`R1` 完成（名称权威文档债收口，`v4.6.1`）**：补 `v4.6.0` 名称根治遗留的文档债 —— 新增 ADR `0072`（代码↔名称主数据表 `symbol_master` 为名称解析**唯一权威** + 回退语义 + 「源 `fundamentals` 无英文字段、故不做中英双语」的诚实边界）与契约 `docs/contracts/symbol-naming.md`（存储只存真名 / 展示走 `display_name` / 未知 `—` / 解析优先级四档）；`check_docs.ps1` 登记两份新文档；`release_tag.ps1` 增加 `-MessageFile`（UTF-8 读入 + `git tag -F`）以支持**中文 tag 注释** |
| 2026-10-14 | **`R2` 完成（`C3` 重复实现收敛清单，`v4.6.2`）**：新增 `docs/plans/duplicate-implementation-convergence.md` —— 逐项登记 选股打分 / 因子库 / 闸门 / 回测引擎 / 交易规则 / 费用 / 资产类型 / 榜单 / 命中追踪 / 行情抓取 / 真相源 / 基本面名称 / 多 Agent / 报告渲染 / 交易日历 / `.env` / 调度 / 报告跑批 **18 项**，每条标「平台侧权威单点｜引擎/上游参考｜判据｜处置」（**16 项已收敛、2 项按边界保留**）；逐条给出收敛证据（同一性断言 / sha256 逐位一致 / 跨线静态互测 / 只读派生）；**只定边界、不删代码**（承接 C 域约束）。`C3` 由此闭合 → **C 域（C1/C2/C3）全部收官** |
| 2026-10-14 | **`R3` 完成（日用循环健康度单点，`v4.7.0`）**：新增 `research.loop_health`（`collect_loop_health` / `roll_up_verdict` / `render_loop_health_markdown`）+ CLI `stock-platform-loop-health`（默认写 `data/health/loop_health.{json,md,html}`；退出码恒 0，门禁看 `verdict.status`）。把「供数 → 选股 → 命中 → 绩效 → 名称」**五段的既有只读信号**聚合成**一个裁决**：`coverage`（复用 C2 `coverage_snapshot`，引擎库不可用→`unavailable`）/ `latestBrief`（`list_recent(1)`）/ `hits`（两类 session 汇总）/ `performance`（`settledCount` vs `MIN_MEANINGFUL_SAMPLE`）/ `symbolMaster`（行数）/ `nextSettlement`（日历推算**提示**）。**裁决规则**（写进契约）：coverage 的 `unavailable/missing_table/empty` → **blocked**，`stale/thin` → degraded；brief 落后供数（按交易日）→ degraded；绩效样本 <20 → degraded；其余 warn 不 fail。**硬约束**：零网络 / 只读 / fail-closed / **每段独立 try-except（方法永不抛）** / `providers` 仅函数内导入。新增 ADR `0073` + 契约 `docs/contracts/loop-health.md`；新测试 `test_loop_health.py` **19 项**；真机一次 → 裁决 `degraded`（`warned=['coverage','performance']`：`latestTradeDate=2026-10-12` 滞后 2 交易日、样本 3<20）；`hits=14 码/20 次`、`symbolMaster=5237`、`nextSettlement=2026-10-19` 正常 |
| 2026-10-14 | **`R4` 完成（绩效代理样本增强，`v4.7.1`）**：新增 `research.performance_proxy` —— `trades_to_decision_rows` 把**回测成交**（`book_replay` 的 `trades`：`entry_idx`/`held_days`/`gross_ret`/`net_ret`）翻译成与真实台账**逐字段同形状**的决策行：`date`=建仓日（`equity_curve[entry_idx].date`）、`raw`=**扣费** `net_ret`、`holding`=真实持有天数、`pending=False`、`source="backtest_proxy"`、`alpha=null`（**不编造**）。**口径差异（四维全不同）**：信号源（实时 brief vs 历史回放）/ 出场（T+N 固定持有 vs 引擎退出规则）/ 收益（裸收益 vs 扣费净收益）/ 窗口（重叠 vs 单账户序列）⇒ 契约硬条款 **禁止混算**：`build_proxy_view` 只并排、顶层**无任何** `total/combined/merged/all/sum` 合并键，并显式 `comparability.combinable=false`；两侧复用 `book_replay` 单引擎（ADR 0059）+ `performance_summary` 单算术（ADR 0068）。新增 CLI `stock-platform-performance-proxy`（`--years` 默认 1 / `--ledger`/`--briefs-dir` 走 picks 入口 / 只读 `market.db`；产出代理台账 + `data/performance/proxy_vs_real.{json,md,html}`）；台账**覆盖写**（一次回测的完整派生，追加会重复计数）。新增 ADR `0074` + 契约 `docs/contracts/performance-proxy.md`；新测试 `test_performance_proxy.py` **19 项**（含「顶层不得出现合并键」的逐名断言）。**真机 1 年窗口**（`2025-10-14`~今，universe=stock）：代理 settled **83**（≥20 ✅）/ `winRate=0.3735` / `avgReturn=−0.38%` / `avgHold=34.3d`；真实 settled **3**（噪音区）—— 样本量问题解决，读数为**负**亦如实呈现 |
| 2026-10-14 | **`T` 域开局（循环可信度与运营）**：`R3` 交付后新增 **T — Trust & Ops** 域三项 —— `T1` 循环健康度出口与趋势台账（`v4.9.0`）/ `T2` 调度与回补执行台账 + brief 连续性守卫（`v4.9.1`）/ `T3` 数据质量体检单点（`v4.10.0`）；把「裁决无出口 / 无时间面 / 执行记录无入口 / 数据质量无体检」四个可观测性缺口显式立项；**只读、不新增交易能力、不写库**（承接 ADR 0058 + C 域约束） |
| 2026-10-14 | **`T1` 完成（循环健康度出口与趋势台账，`v4.9.0`）**：① **出口面** —— Workbench 新增 `GET /api/ops/loop-health`（`routes/ops.py`）**只读转发** `collect_loop_health`，自身零业务逻辑/零写库；**503 fail-closed** 判据 = 供数段落在 `COVERAGE_HARD_FAIL`，其余降级一律 200（裁决留在 `verdict.status`，不用 5xx 掩盖「能跑但要打折看」）；响应模型 `LoopHealthResponse` 纳入 OpenAPI 目录测（`ENDPOINT_HITS` 66→67、`n_ops+n_extra` 69→70）。主模板加 `#health` 面板（导航「体检」：裁决徽标 + 六段 `kv` 表 + 近 N 天趋势 + 原始 JSON；手写 HTML/JS，不引前端框架）。② **时间面** —— `loop_health` 增 `history` 趋势面：`read_history`（缺文件→`[]`、**读失败向上抛** → `unavailable`、坏行跳过）/ `summarize_history`（**纯函数**：按 `asof` 去重 → 并入本次 → `degradedStreak` / `blockedStreak` / `notOkStreak` / `streakSince` / `recent`）/ `append_history`（**追加**一行五字段审计记录，**fail-open**，超 `HISTORY_MAX_RECORDS=400` 裁剪最旧）；目录由 `STOCK_PLATFORM_LOOP_HEALTH_DIR` 优先、否则 `./data/health`；CLI 增 `--history-path` / `--no-history`（`--no-write` 同时不写台账）。**台账是本模块唯一写动作，只写平台自有 `data/`**；**`history` 不参与裁决**（裁决仍只看六路信号当下快照），加段不改任何既有段语义。③ **同轮修正裁决漏洞**：`coverage` 的 `error`（库存在但不可读）与 `unconfigured`（未配置路径）在 `v4.7.0` 既非 fail 也非 warn ⇒ 落到 `else` 被判 **`ok`**（「仓库打不开」被报成「供数正常」）；新增 `COVERAGE_HARD_FAIL`（含这两档）与 `COVERAGE_WARN` 常量并用于裁决。④ 文档：ADR `0075` + 契约 `docs/contracts/loop-health.md` **扩写**（新增 §4.6 趋势面 / §8 台账格式与连续段口径、§2 增「台账例外（唯一写）」、§5 表更新 coverage 档位并标注 T1 修正、§7 出口表加 API 与面板）；`check_docs` 登记（166→167）。⑤ 测试：`test_loop_health.py` 增 §9 **14 项**（台账/连续段表驱动/裁剪/坏行/隔离/渲染/CLI）+ 新文件 `test_ops_loop_health.py` **4 项**（503 fail-closed ×2 / 满窗 200 + 趋势 / thin 降级仍 200）。⑥ **真机实测**（本次重跑）：裁决 `degraded`，`warned=['latestBrief','performance']` —— 供数已恢复 ✅（`latestTradeDate=2026-10-14` / 5225 行 / lag=0，18:32 回补生效），仍告警的是 **brief 停在 `10-12`（落后 2 个交易日）** 与**真实样本 3<20**；`degradedStreak=1`、`data/health/history.jsonl` 已落首行 |
| 2026-10-14 | **`T2` 完成（调度与回补执行台账 + brief 连续性守卫，`v4.9.1`）**：① **执行台账单点** `research.ops_ledger` —— append-only `data/logs/runs.jsonl`；`record_run`（**唯一写**、**fail-open**、`task` 为空拒绝、超 `RUNS_MAX_RECORDS=400` 裁旧）/ `read_runs`（缺文件→`[]`、**读失败向上抛**、坏行跳过）/ `summarize_runs`（**纯函数**：逐任务 `failureStreak` 从最新往回数、`failingTasks` ≥ `OPERATIONAL_FAILURE_STREAK=2`、`recent`）/ `collect_ops_ledger`（段形状，缺失→`unavailable` fail-closed）/ `render_ops_ledger_markdown`；`TASK_SCHEDULES`（`daily` 08:30 / `postmarket` 15:30 / `marketdb-backfill` 18:30）**仅用于展示**，未知任务名原样保留。② **调度包装器** `scripts/ops/Invoke-ScheduledRun.ps1` —— 调度任务统一入口：预设解析目标脚本与规范参数 → **子进程**运行（目标的 `exit` 无法绕过本层，**总能记到一行**）→ best-effort 追加台账（**只报告、绝不改退出码**）→ **原样透传**目标退出码；`TargetArgs` 为**空格分隔字符串**（`powershell -File` 会把数组参数静默退化成一个 token）；未登记任务必须显式 `-Script` 否则 `exit 2`。三个既有自动化（盘前/盘后/回补）prompt 已切到包装器。③ **`loop_health` 增两路信号** —— `briefContinuity`（`_recent_trading_days` 取近 `window_days=5` 个**交易日**，`end_day` 取 `coverage.latestTradeDate`、无供数退化为 `asof`；`missingDays` **逐个列出** + `coverageRatio`，`status∈{ok,incomplete,empty,unavailable}`）与 `opsLedger`（**只读** `collect_ops_ledger`，本模块不写台账）；两路**都参与裁决但只 warn**（缺 brief 日 / 任务连续失败 → degraded，**永不 blocked** —— 观测面信号，不同于 `coverage` 的物理硬前提）。④ 文档：ADR `0076` + 契约 `docs/contracts/ops-ledger.md`；`docs/contracts/loop-health.md` 扩写（§4.7/§4.8 段定义 + §5 裁决表两行 + §1 目的「任务到底跑没跑」）；`check_docs` 登记（167→169）。⑤ 测试：新文件 `test_ops_ledger.py` + `test_loop_health.py` §10（连续性/裁决 warn-不阻断/常量对齐/段读取）+ `test_ops_loop_health.py`（连续失败降级但仍 200）。⑥ **真机实测**：跑包装器 `marketdb-backfill -Mode dry-run` → 台账 `status=ok totalRuns=1`；`loop_health` 裁决 `degraded`、`briefContinuity` 标出 3 个缺日（`2026-10-08`/`10-13`/`10-14`）。**跳号**：承接 `v4.9.0`，`v4.8.0`（`R5`）因生产侧 ETF 回补未完成而顺延 |
| 2026-10-14 | **`Y` 域开局（收益增强）**：新增 **Y — 收益增强** 域三项 —— `Y1` 策略采纳闸门（`v4.10.0`）/ `Y2` 采纳落地（`v4.10.1`，须人工签核）/ `Y3` 近期负收益根因诊断（`v4.11.x`）；把「**研究结论与生产默认档之间没有桥**」这一结构性问题显式立项 —— `S4` 中性化与 `S3` 闸门均已实测改善却「只诊断不改档」，`R4` 近一年 `avgReturn=−0.38%` 无出口；`T3` 目标 tag 顺延至 `v4.11.0` |
| 2026-10-14 | **`Y1` 完成（策略采纳闸门，`v4.10.0`）**：新增 `research.adoption_gate` 单点 + CLI `stock-platform-strategy-adoption` —— 基线档（生产档，`neutralize=None`）与候选档**共用同一引擎**，在多个**互不重叠**的样本外窗口（`build_windows`，默认近 3 × 1 年）各跑一遍；**特征全跨度算一次**再 `slice_window` 切窗（边界不损失 `ma20`/`ma60` 预热）；`AdoptionRule` **事前登记**阈值 + `decide_adoption` **纯函数**给 `adopt`/`reject`/`insufficient`（**样本不足不做结论**）；窗口 `pass` 需三项风险闸门全过、指标缺失判否；报告 `data/strategy/adoption_gate.{json,md,html}` 列逐窗 `blockingChecks`；**只出建议**（`adoptionNote`）—— **不改任何生产默认档**；ADR `0077` + 契约 `docs/contracts/adoption-gate.md`；`check_docs` 登记（169→171）。**真机实测（3 个互不重叠 1 年窗口）**：`行业中性化` **0/3 通过**（Δ夏普均 **−0.241**、Δ收益均 **−2.61%**、Δ回撤均 −0.090）⇒ **`S4` 的单窗结论未在样本外复现**（与 2024-09→2026-09 连续 2 年的 0.3029→0.5257 **相反**，差异待归因）；`闸门 0.70` **2/3 通过**（Δ夏普均 **+0.274**、Δ收益均 **+5.90%**，仅 w1 未达标）⇒ 唯一有正向证据的候选，被「全窗口要求」如实拦下；**结论：维持生产基线** —— 本次价值在于**拦住了一个单窗看起来赢、样本外实际输的改动** |
| 2026-10-15 | **`Y3` 完成（收益归因 / 负收益根因诊断，`v4.11.0`）**：新增 `research.attribution` 单点 + CLI `stock-platform-attribution` —— 把一段窗口的亏损分解成**互不重叠、各自可处置**的少数几项原因。**两个样本集**：`gated`（全部过闸，用于评分单调性）与 `picks`（过闸且 `composite_score >= score_floor`，即候选池），曲线各算一遍 ⇒ 差值是**评分闸门本身**的贡献（`S3` 说 0.80 最差却始终无法证实处）。**两口径硬分（真机教训）**：**边缘类**结论读**超额** `meanExcess`（有没有技能），**持有期类**结论读**绝对** `meanReturn`（赚不赚钱）—— 近一年实测出现「绝对收益 10 日见顶后转负，而超额只在 40 日为正」（**熊市相对防守**），若混用口径会给出「延长持有」的**错处方**；`horizon_curve` 因此每行**同时**携带两个读数。**逐日同源打分**（`score_lvrev` + `apply_entry_gates`，与 `screener_entry_provider` 一致），成交侧 `run_neutralization_book`（`X4` 单点）跑一次基线档。**纯函数裁决** `diagnose`（不碰 pandas/引擎）：7 类原因码 + 事前登记阈值；排序键 = 严重度 → `_CAUSE_RANK`（**事前登记**，`impact` 跨量纲不可比故只作三级键）→ |impact|；样本不足的 horizon 标 `adequate=False` 且**不参与结论**。**两处真机修正**：① **收益单位** —— `book_replay` 的 `gross_ret`/`net_ret` 是**百分数**，归因内部须 × `TRADE_RET_SCALE=0.01` 归一为小数，否则读数放大 100 倍（首版实测把 −2.39% 显示成 −238.55%）；② **退化分组** —— `assetClass=stock` 恒占 100%，「单组集中」必须显式跳过（`groupCount < 2`）；另把 `reason` 按**规则名**分桶（`stop_loss(-8.1%)` 与 `stop_loss(-9.5%)` 同桶，否则一条退出规则被碎成几十桶）。文档：ADR `0078` + 契约 `docs/contracts/attribution.md`；`check_docs` 登记（171→173）。测试：新文件 `test_attribution.py` **58 项**（前瞻收益分位与截尾 / 基准对齐 ffill / 面板与两样本集 / 曲线·单调性·成本·赔率·集中度各块 / `diagnose` 七类原因 + 严重度与 `rank` 排序 + 退用 `gated` 回落 + 单组跳过 / 渲染 / CLI 端到端 + 临时 SQLite）。**真机实测（近一年，universe=stock，基准 `000905.SZ`）**：`gated=33450` / `picks=11663` / 85 笔成交 ⇒ 主因 **`hold_too_long`**（候选池绝对收益 10 日见顶 +0.23%、20 日 −0.86%、40 日 −1.63%，**实际平均持有 32.5 天**）；次因 `edge_only_long_horizon` / `score_weak`（Spearman=−0.015）/ `concentrated_loss`（`stop_loss` 占亏损 94%）；**成本不是问题**（占毛收益 2.7%）、**赔率不差**（盈亏比 1.19，胜率 31.8%）—— 结论指向**持有期**而非选股或成本。`T3` 顺延至 `v4.12.0` |
