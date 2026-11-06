# 现行快照

> 日期：2026-11-06  
> 版本：**`v4.14.0` 已发布**（tag `v4.14.0`；收录 F1 / T3 / A1 / R5-P / 多策略影子终榜全套 / S2-P1 快照 / 影子链契约补齐，详见 [`CHANGELOG.md`](../CHANGELOG.md) `[4.14.0]`）  
> 工作区：F1/T3/A1/R5-P 已落（ADR [`0090`](architecture/0090-benchmark-identity-and-sh-fund-prefix.md) / [`0091`](architecture/0091-data-quality-scan.md) / [`0092`](architecture/0092-etf-universe-platform-side.md)）；影子终榜 ADR [`0093`](architecture/0093-multi-strategy-shadow-board.md)（含 2026-11-06 增补）；LLM ADR [`0089`](architecture/0089-llm-provider-selection.md) / [`0088`](architecture/0088-llm-sidecar-package-boundary.md)。`local/` 见 [`ops/local-runtime.md`](ops/local-runtime.md)。  
> 进行中：lvrev 增强实验**已收口**（仅 `trail_tp` 通过 → Proposed ADR [`0094`](architecture/0094-lvrev-trail-tp-exit.md) 等签核；出厂默认仍关）；影子前向账本与 S2-P1 快照**前向证据积累中**；**Y2 暂停**（无 `adopt`）。  
> 这是**现在**读仓库的入口。历史里程碑叙事留在 [`ROADMAP.md`](ROADMAP.md) 与 [`plans/trading-system-roadmap.md`](plans/trading-system-roadmap.md) 的修订记录里，不要从那些旧焦点段开工。

## 文档放哪

正式正文只在 `docs/`。按用途分目录，不把 ADR、契约、运维和计划摊成一堆。

| 位置 | 放什么 | 不放什么 |
|------|--------|----------|
| [`docs/`](README.md) | 产品文档 SSOT | 密钥、行情缓存、SQLite |
| 仓库根 `README.md` / `AGENTS.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | 给人、给代理、给发版脚本的入口 | 里程碑正文 |
| `packages/*/README.md`、`apps/workbench/README.md` | 该包怎么装、硬约束 | 全仓路线图 |
| [`archive/`](archive/README.md) | 已经落地的交接，文中「下一块砖」作废 | 现行计划 |

`.cursor/plans` 若出现，只留指向本目录的短链，不写第二份正文。

## 自有线

| 域 | 状态 |
|----|------|
| G / B / S / X / C | 收官 |
| R | R1–R4 done。**R5-P**（平台形状）已落（ADR 0092）；全量 **R5** 仍等生产侧 ETF 日线回补 |
| T | T1、T2 done。**T3** 代码已落（`data_quality` + CLI + `loop_health.dataQuality`）；随 **`v4.14.0`** 发布 |
| Y | Y1 采纳闸门、Y3 负收益归因 done。**Y2** 落档必须等人工签核；没有 `adopt` 证据不改生产默认档 |
| L | L1 立项 `Accepted`（华宝、1 万、Phase 0 纯模拟）。L2/L3 与实盘红线仍关闭 |

下一组里程碑与技术方案：[`plans/next-milestones-t3-cli-y2-fix-r5.md`](plans/next-milestones-t3-cli-y2-fix-r5.md)。  
**多策略 Final Board（影子链）**：ADR [`0093`](architecture/0093-multi-strategy-shadow-board.md)；CLI `stock-platform-shadow-board`；S1/S5 薄规则已接，S2 日循环读 S2-P1 每日快照（回测仍空池），digest 可选影子附录；**不改**出厂 lvrev；升级仍走 Y1→Y2。  
生产接入（库默认仍关；生产调度已开）：日循环 `--shadow-board` / `STOCK_PLATFORM_SHADOW_BOARD=1`；`loop_health.shadowBoard`（最多 warn）；独立前向账本 `local/shadow/shadow_decisions.jsonl`（A/B 双轨，`--settle-daily` / `--perf-summary`）；理由 schema + 空话检测回落。  
**生产已开启影子终榜**：日期 **2026-11-05**；开启方式 = 盘前/盘后调度预设加 `-ShadowBoard`（`scripts/ops/stock-platform-daily.xml` / `stock-platform-postmarket.xml` / `Invoke-ScheduledRun.ps1` 的 `TASK_PRESETS`，由 `test_scheduler_args_contract.py` 钉住）；**回滚方式** = 移除这些预设里的 `-ShadowBoard`（或单次运行传 `-NoShadowBoard`），库出厂默认本就是关，无需改代码。**前向账本起算日 `asof=2026-11-04`**（首条 2 席 pending，T+1 未到不结算）。  
**已知偏置**：回测 402 日 `schoolCoverage` 显示 S1 有 235 天非空池却 **0 席**、S5 仅 3 席——Round2 把学校优先级排在分数之前，S3/S4 先填满 10 席。现象、证据与可选改法记在 [`plans/multi-strategy-final-board.md`](plans/multi-strategy-final-board.md) §11；**改仲裁须先签核 + ADR**，本轮未改。S2 数据源规划见 [`plans/s2-event-theme-data.md`](plans/s2-event-theme-data.md)。  
证据（2026-11-05）：walk-forward 回测 2021-01-04~2026-11-05 影子 夏普 0.198 / 总收益 10.37% / 回撤 -27.83%，lvrev 0.559 / 47.24% / -18.91%；Y1 `--include-shadow` 3×1y 判 **不采纳**（1/3 窗通过，w1/w2 夏普不达标）。**仍是影子**；缺：前向账本真实天数、S2 历史题材 DI；不降门槛、不伪造证据。

**ADR 0094 已签核 Accepted（opt-in，出厂默认关）**：开关 `STOCK_PLATFORM_LVREV_TRAIL_TP=1` 或 `run_portfolio_backtest(trail_tp=True)`，回滚去掉该环境变量；生产默认未改。
**下一刀**（v4.14.0 之后）：若要把 lvrev 出厂默认改为 `trail_tp=True`，须另开提交并先更新契约（当前不做）；此前为签核 ADR 0094（依据 [`plans/lvrev-enhancement.md`](plans/lvrev-enhancement.md) §5，其余四变体不通过、不起 ADR）；影子前向账本与 S2-P1 快照前向证据积累中（满 `MIN_MEANINGFUL_SAMPLE` 前不下结论）；S4「短期反转」候选（E1）已按事先登记标准判不通过（[`plans/shadow-s4-s5-diagnosis.md`](plans/shadow-s4-s5-diagnosis.md) §9），S5 PIT 资金流（E3）仍为后续前向研究待办；全量 R5 仍等生产侧 ETF 回补。  
**补充行情库**（ADR [`0095`](architecture/0095-aux-market-store.md)）：5 指数日线已入 `local/aux_market/`（2020-01-02~2026-11-05），离线回测超额可算；日循环 settle 仍不读、需定期跑 `stock-platform-aux-market` 增量；data_quality 读 OHLC 未接。  
**Set B 贝叶斯先验仓位**（[`plans/multi-strategy-final-board.md`](plans/multi-strategy-final-board.md) §11.9–§11.10）：离线对照判 **不通过**（总收益/夏普低于 D、回撤深于 D 超 2pp），实验开关默认关，出厂不变。  
**S3 alpha/beta 拆解**（[`plans/shadow-s3-decomposition.md`](plans/shadow-s3-decomposition.md) §8）：判**未证明选股 alpha**（段 A α 年化 −19.06%，全区间 NW t −1.04）；只读诊断，不改学校 / 仲裁 / 默认值。  
**Y2 暂停**：`local/strategy/adoption_gate.json` 现为 `adopt=0 / reject=4`，无签核对象；有 `adopt` + 你确认后再开工。

## v4.14 已落地

- **v4.14.0** F1 基准身份 / 沪基金前缀（ADR 0090）、T3 数据质量体检（ADR 0091）、A1 CLI 面、R5-P ETF 平台侧（ADR 0092）、多策略影子终榜全套（ADR 0093 + 增补：日循环 opt-in、生产调度 `-ShadowBoard`、前向影子账本、walk-forward 回测、Y1 `--include-shadow`、Round2 仲裁开关维持 D、S2-P1 快照）、绩效夹具 fallback 只读修复

## v4.13 已落地

- **v4.13.0** 简报盘前/盘后分线、②A/②B 双 profile 二次精选、③B 详解
- **v4.13.1–.3** 报告日文件名、同花顺导入块与 txt 对齐
- **v4.13.4–.6** 盘后开/收/涨跌：东财分批重试 → 腾讯/新浪 → westock 第四源
- **v4.13.7** 体检 `briefDue`：修掉每晚「brief 落后 1 日」的假阳性；裁决 `ok` 时报告只留一行结论

## LLM 边界（现行）

- **确定性主链**（默认、无 key）：`research` 日更 / digest / 回测 / attribution / adoption / 绩效；`agents` 研报·复盘·`engine=off|deterministic` 辩论；执行 SIMULATE。
- **LLM 提供商**（ADR [`0089`](architecture/0089-llm-provider-selection.md)，运维 [`ops/llm-providers.md`](ops/llm-providers.md)）：`STOCK_PLATFORM_LLM_PROVIDER` 默认 **`workbuddy`**（进程内不打商业 LLM；数据用 workbuddy bridge）。生产 LLM 选 **`deepseek`**，只用 `DEEPSEEK_*`；或 `openai` 兼容栈。另需 `STOCK_PLATFORM_LLM_DEBATE=1` + `[llm]` extra。
- **可选 LLM 侧车**：`stock_platform_agents.llm`；CLI `--debate-engine llm`；API `engine=llm` / `/api/debate/status` / deep-graph。
- **不变量**：辩论判决不进 brief / picks 账本 / 命中 / 绩效（ADR 0065 测试锁）。

## 已记账缺陷

- （F1 已收口）`exchange_prefix("588080")` → `sh`；基准身份碰撞 → alpha unavailable（ADR 0090）
- （已收口）默认运行时目录改为 `local/`；根 `conftest.py` 扩大守卫，单包 pytest 也不应再写生产 `local/` / `data/`

执行层仍是 SIMULATE，`liveTradingEnabled=false`。空库可跑 `stock-platform-init` 写入可改配置行（不打开实盘）。
