# 现行快照

> 日期：2026-11-08  
> 版本：**`v4.14.0` 已发布**（tag 未动；本晚未发版，保持 4.14.0）  
> 分支：**仅 `main`**  
> 工作区：F1/T3/A1/R5-P 已落；影子终榜 ADR [`0093`](architecture/0093-multi-strategy-shadow-board.md)；lvrev `trail_tp` ADR [`0094`](architecture/0094-lvrev-trail-tp-exit.md) **Accepted（opt-in，默认关）**；补充行情库 ADR [`0095`](architecture/0095-aux-market-store.md)；午间会话 ADR [`0096`](architecture/0096-midday-digest-session.md)；**本仓模拟舱** [`ops/paper-cabin.md`](ops/paper-cabin.md)。`local/` 见 [`ops/local-runtime.md`](ops/local-runtime.md)。  
> 进行中：影子前向账本与 S2-P1 快照**前向证据积累中**；**Y2 暂停**（无 `adopt`）。同花顺真实模拟盘**已放弃**。  
> 这是**现在**读仓库的入口。历史里程碑叙事留在 [`ROADMAP.md`](ROADMAP.md) 与 [`plans/trading-system-roadmap.md`](plans/trading-system-roadmap.md) 的修订记录里，不要从那些旧焦点段开工。

## 通宵迭代纪要（2026-11-06 → 11-07）

### 分支状态

- `git branch -a`：**仅** `main` / `origin/main`
- 工作区干净；`origin/main` 已含功能分支全部提交（含 picks 账本锁、quotes 兜底撤回、ADR 0094/0095 登记、S3/Set B 结论、午间 midday）

### 今晚完成的 commits 摘要（合入 main 后新增）

- 分支收束：功能分支 → `main`（fast-forward）并删除远端/本地功能分支
- **午间休盘简报** ADR [`0096`](architecture/0096-midday-digest-session.md) + 计划 [`plans/midday-session.md`](plans/midday-session.md) + 实现：`--session midday`、`{reportDay}-midday.md`、分钟现价经 `em_get` 限候选池、表头「现价」
- 同花顺模拟盘：mock 端到端真实试跑日志 → `local/ths_sim_trial/`（**不入库**）

#### 续轮（2026-11-07 后半夜）

- **`trail_tp` 生产 opt-in 文档化**：[`ops/lvrev-trail-tp.md`](ops/lvrev-trail-tp.md)；调度 / 日流水线交叉链。③B `review_positions` 未显式传 policy 时读 `STOCK_PLATFORM_LVREV_TRAIL_TP`（**默认仍关**）
- **midday 手动触发**：[`plans/midday-session.md`](plans/midday-session.md) §1.1；明确不装 schtask
- **同花顺**：[`ops/broker-port-honesty.md`](ops/broker-port-honesty.md) 写清 mock 手跑与接真实缺项；无桌面自动化钩子
- **候选过滤实验**：计划 [`plans/lvrev-entry-filter.md`](plans/lvrev-entry-filter.md) + CLI `stock-platform-lvrev-filter`；`near_limit7` / `amount50m` / `cooldown5` **三变体均不通过**（过滤方向收益递减，停扫）

#### 续轮（2026-11-08）

- **同花顺真实模拟盘放弃** → 本仓模拟舱：`stock-platform-paper` 扩展 buy/sell/positions/account/fills，落盘 `local/paper_cabin/`；文档 [`ops/paper-cabin.md`](ops/paper-cabin.md)；`ths_sim` mock 仅端口演示

### 测试结果

| 检查 | 结果 |
|------|------|
| `pytest packages apps -q`（清空 `STOCK_PLATFORM_ENGINE_MARKET_DB`，replay） | **1642 passed, 11 skipped**（+5 模拟舱；含 midday / trail_tp / 过滤实验） |
| `check_docs.ps1` | OK（含 `ops/paper-cabin.md` / `ops/lvrev-trail-tp.md`） |
| `check_versions.ps1` | OK（`VERSION=4.14.0`） |

### 策略实验结论

| 项 | 结论 |
|----|------|
| lvrev `trail_tp` | **通过**（既有严格对照 + aux 超额：基线超额 43.26% / trail_tp 70.52%；MaxDD 不恶化）。**出厂默认仍关**（安全优先）。**推荐生产日循环 opt-in**：设 `STOCK_PLATFORM_LVREV_TRAIL_TP=1`（步骤见 [`ops/lvrev-trail-tp.md`](ops/lvrev-trail-tp.md)）；若要改库默认须另开 ADR + 全量回测 |
| lvrev 过滤 `near_limit7` / `amount50m` / `cooldown5` | **均不通过**（near 与基线逐位相同；amount50m 收益≈0、回撤−33.6%；cooldown5 收益/夏普双降）。出厂不变；不起 ADR。详见 [`plans/lvrev-entry-filter.md`](plans/lvrev-entry-filter.md) §5 |
| S3 alpha/beta 拆解 | **不通过**（未证明选股 alpha）— 只读诊断，不改默认 |
| Set B 贝叶斯仓位 | **不通过** — 默认关；**勿再扫仓位贝叶斯 / 无假设过滤参数** |
| S4 E1 短期反转 | **不通过**（既有） |

### 模拟买卖 / 同花顺

- **主路径（推荐）**：本仓模拟舱 `stock-platform-paper`（PaperBroker）→ buy/sell/positions/account/fills；落盘 `local/paper_cabin/state.json`；说明 [`ops/paper-cabin.md`](ops/paper-cabin.md)
- **ths_sim mock（仅端口演示）**：`STOCK_PLATFORM_BROKER=ths_sim` + `THS_MODE=mock` 仍可跑 authenticate / draft / execute；**≠** 真实同花顺；见 [`ops/broker-port-honesty.md`](ops/broker-port-honesty.md)
- **已放弃**：同花顺真实模拟盘 / experimental HTTP wire-up；无桌面自动化；不伪造成交

### 建议的下一刀

1. **影子前向账本**攒满 `MIN_MEANINGFUL_SAMPLE` 再下结论；Y2 仍等 `adopt`  
2. 生产日循环确认已设 `STOCK_PLATFORM_LVREV_TRAIL_TP=1`（opt-in 观察）；改出厂默认须另 ADR + 全量回测  
3. **不要**再推进同花顺真实模拟盘；模拟买卖以本仓模拟舱为准  
4. **不要**再无新假设扫过滤/仓位贝叶斯；若再做策略实验须有新机制假说 + 事先标准

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

**ADR 0094 已签核 Accepted（opt-in，出厂默认关）**：开关 `STOCK_PLATFORM_LVREV_TRAIL_TP=1` 或 `run_portfolio_backtest(trail_tp=True)`，回滚去掉该环境变量；生产默认未改。运维步骤见 [`ops/lvrev-trail-tp.md`](ops/lvrev-trail-tp.md)。
**下一刀**（v4.14.0 之后）：① 影子前向账本攒样本；Y2 仍等 `adopt`；② 全量 R5 仍等 ETF 回补；③ `trail_tp` 生产 opt-in 观察（改出厂默认须另 ADR）；④ 过滤实验本轮已递减停扫。midday 由用户 11:30 手动触发（[`plans/midday-session.md`](plans/midday-session.md) §1.1）。  
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
