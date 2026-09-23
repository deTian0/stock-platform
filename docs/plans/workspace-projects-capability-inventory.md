# 工作区多仓能力盘点（合并输入）

- **目的**：为「更细致、更丰富的合并」提供输入清单。**本文件不实施合并**，不改业务逻辑。
- **盘点日期**：2026-09-15
- **方法**：实地阅读各仓 README / 目录 / pyproject·package.json / 入口 / docs·ADR·skills；对照 `docs/upstream-archive.md`。
- **权威收敛仓**：`stock-platform`（唯一产品主链）。上游只读参考 / 配方来源。
- **相关**：[`docs/upstream-archive.md`](../upstream-archive.md) · [`docs/ROADMAP.md`](../ROADMAP.md)

---

## 总表：项目 × 能力域

图例：`有` = 仓内具备可运行或权威实现 · `部分` = 有限/文档/薄适配 · `无` = 不具备  
`*` = **文档/Skill 覆盖，非运行时模块**（勿当成已接入平台）  
`†` = **审查快照内曾有实现**，相对平台多为未迁入代码

| 项目 | 数据 | 选股 | 回测 | Agent | UI | 执行 | 运维 |
|------|:----:|:----:|:----:|:-----:|:--:|:----:|:----:|
| stock-platform | 有 | 有 | 部分 | 部分 | 部分 | 部分 | 有 |
| a-stock-engine | 有 | 有 | 有 | 无 | 部分 | 无 | 部分 |
| a-stock-data | 有* | 无 | 无 | 部分* | 无 | 无 | 部分* |
| global-stock-data | 有* | 部分* | 无 | 无 | 无 | 无 | 无 |
| tick-stock-panel | 有 | 有 | 有 | 部分 | 有 | 部分 | 部分 |
| TradingAgents-astock | 有 | 部分 | 部分 | 有 | 有 | 部分 | 部分 |
| finance-quant-skills | 部分* | 部分* | 部分* | 部分* | 无 | 部分* | 无 |
| V2-code-review-20260905 | 有† | 有† | 有† | 无 | 有† | 有† | 部分† |
| market-report-dashboard | 部分* | 无 | 无 | 部分* | 部分* | 无 | 无 |

### 总表结论（一句话）

- **收敛终点**：`stock-platform` 已覆盖数据主链 + 选股简报 + 轻量回测/绩效 + 薄 Agent + 纸面执行 + 运维调度；缺口主要在 **完整 UI/回测引擎（TSP）**、**完整多 Agent LLM 图（TA）**、**引擎离线大库/实证**、**Skill 端点配方增量吸收**。
- **勿整仓并入**：Skill/文档仓（a-stock-data / global-stock-data / finance-quant-skills / **market-report-dashboard**）与 V2 审查快照；价值在配方、语义、测试用例，不是 pip 依赖。`market-report-dashboard` 已配方挂接见 MR 里程碑（v3.12.4）。
- **分阶段高价值**：`tick-stock-panel`（契约已接，SPA/回测/监控未接）；`a-stock-engine`（`market.db` + 实证基线）；`TradingAgents-astock`（角色/评级口径，禁并 dataflows）。

---

## 各项目盘点

### stock-platform

- **定位一句话**：可发布的量化**研究与纸面决策**单一产品仓——统一 Vendor、选股/PIT、Workbench API、投研 Agent 槽位、纸面执行安全模型。
- **技术栈 / 入口**
  - Python ≥3.10；版本见根 `VERSION`（盘点时约 v3.10.x）
  - 五包：`packages/{providers,research,agents,execution}` + `apps/workbench`
  - 入口：`python -m stock_platform_workbench` → `http://127.0.0.1:3018/`；`start-workbench.bat`
  - CLI：`stock-platform-{workbench,score,brief,refresh,daily,performance}`
- **模块与功能清单**
  - **数据**（`packages/providers`）：`normalize_symbol`；`em_get` / 东财客户端；`AStockHttpProvider`；`ReplayProvider`；`GlobalHttp`/`GlobalReplay`；`TushareHttp`；`EngineSqliteProvider`；能力矩阵 12 项；`MarketStrategy` CN/US/HK；静态交易日历；复权 `apply_adjust`
  - **研究**（`packages/research`）：lvrev / 入场与风险闸门；宇宙；PIT 截面；盘前 brief；滚动推荐复盘；`run_pit_long_only` / 组合 PIT；策略配置对比；绩效 JSONL；refresh / daily_pipeline；SQLite brief 持久化（ADR 0049）
  - **Agent**（`packages/agents`）：研报/复盘插件；确定性 Bull/Bear/Risk 辩论；可选 LLM 辩论（预算降级）
  - **执行**（`packages/execution`）：`PaperLedger`；lifecycle / timing / transactional / admission；`BrokerPort` / `PaperBroker` / `ThsSimBroker`（mock + experimental）
  - **UI**（`apps/workbench`）：FastAPI + Jinja2/原生 JS；矩阵/行情/推荐/向导/纸面/辩论/绩效/回测/ops
  - **运维**（`scripts/`、`docs/ops/`）：日流水线 PowerShell + cron/Task Scheduler 样例；`/api/ops/health`；CI 文档/版本检查
  - **文档**：ADR 0001–0049；`docs/contracts/*`；`docs/upstream-archive.md`
- **对外接口**
  - CLI（上表）；HTTP Workbench `:3018`（`/api/market/*`、`/api/research/*`、`/api/paper/*`、agents、ops）
  - Python 可安装库（非独立 HTTP SDK）；**无 MCP Server**
  - DB：`STOCK_PLATFORM_DB_URL`（默认 `./data/stock_platform.db`）；绩效 JSONL；refresh 落盘目录；只读外部 `STOCK_PLATFORM_ENGINE_MARKET_DB`
- **数据资产**
  - Fixtures：`packages/providers/tests/fixtures/`（含 `global/`）；research 宇宙 JSON；execution `ths_sim` fixtures
  - 静态日历：`packages/providers/.../data/*_closed_days.txt`
  - 运行时（gitignore）：`data/*.db`、`recommend_decisions.jsonl`；外部大库 `a-stock-engine/data_cache/market.db`
- **与 stock-platform 当前关系**：**自身即产品主链**（已吸收上游结论，见 `docs/upstream-archive.md`）
- **合并候选价值**：**N/A（收敛目标）** — sibling 仓应单向迁入本仓，禁止平行第二主链。

---

### a-stock-engine

- **定位一句话**：已归档的 A 股 **lvrev 多因子选股 + 本地 SQLite 回测/盘前管线** 参考实现。
- **技术栈 / 入口**
  - Python 3.12+；`requirements.txt`（无 pyproject）；`config.yaml` 为配置 SSOT
  - 脚本入口：`src/daily_brief.py`、`src/afternoon_review.py`、`local_backtest.py`、`alpha_research.py`、`import_local_data.py`、`empirical/*` 等
- **模块与功能清单**
  - **数据**：`database.py`（双库路由）；`kline_cache` / `local_price_loader`；westock / tushare / akshare 提供方；PIT 基本面采集（`fundamental_store` / `pit_fundamentals`）
  - **选股**：`lvrev_scorer.py`（alpha 内核）；`multifactor.py` 分层篮子；`factor_engine` / `risk_module`
  - **回测**：`local_backtest.py`、`src/backtest.py`、walk-forward OOS / IC / 参数扫描（`empirical/`）
  - **报告**：HTML/MD 简报（`html_report` / `history/`）；单票调研、收益归因、板块轮动监控
  - **运维**：`guard.py`、`health_check.py`；盘前时间窗；无 SPA / 无执行
  - **测试**：`tests/`（pytest + functional checklist）
- **对外接口**：脚本 CLI（非统一 Typer）；无 HTTP/MCP/pip SDK；DB 在 `data_cache/`（`market.db`、`selections.db`、`a-stock-engine.db`、`kline/*.json`）
- **数据资产**：离线 `market.db`（约百万级 `daily_price` + PIT 基本面）；`history/` 简报归档；`empirical/*_result.json`
- **与 stock-platform 当前关系**：**已接（部分）** — lvrev/闸门 → `packages/research`；`EngineSqliteProvider` 只读 `market.db`；文档 `docs/ops/engine-market-db.md`。**未接**：完整每日管线、selections 历史、PIT 基本面表暴露、westock 抓取链、HTML 简报 UI。
- **合并候选价值**：**中** — 内核已迁；剩余价值是离线结算库与实证基线，宜只读参考 + DB 路径，勿整仓并入冻结管线。

---

### a-stock-data

- **定位一句话**：**自包含 AI Skill 文档仓**（约 V3.8），把多源 A 股 HTTP/TCP 端点封装成可 exec 的内嵌 Python，供助手按需取数。
- **技术栈 / 入口**
  - 无 pip 包；权威入口 `SKILL.md`；复制到 `~/.claude/skills/a-stock-data/`
  - 验证：`python -m unittest discover -s tests`（从 SKILL 抽取代码 exec，防双实现漂移）
- **模块与功能清单**（Skill 分层，非独立服务）
  - 行情 / 研报 / 信号 / 资金筹码 / 新闻 / 基础财务 / 公告 / 打板 / 期权 / 舆情 / 宏观 / 指数与日历
  - 横切：`norm_ticker`、`em_get` 东财限流、mootdx 验活、备胎降级
  - **无**选股引擎、回测、交易执行、Web UI、常驻 HTTP
- **对外接口**：Skill 函数名即 API；无 CLI/HTTP/MCP/DB；直连公网数据源
- **数据资产**：无仓内固定 DB；测试用合成 Response；运行时缓存由会话/用户脚本自建
- **与 stock-platform 当前关系**：**已接（配方/语义，非依赖）** — `em_get`、`astock_http`、ADR 0020–0028 字段口径。**未接**：打板/期权/宏观/iwencai 等大量端点未进 12 项能力矩阵；未 pip 安装。
- **合并候选价值**：**中** — living recipe；平台继续单向吸收到 `packages/providers`，Skill 仓只读保留。

---

### global-stock-data

- **定位一句话**：给 AI 助手用的**美股/港股全栈数据 Skill**（内嵌 Python，非 pip）。
- **技术栈 / 入口**：`SKILL.md`（约 v2.0.x）；`README.md` / `README_zh.md`；依赖 `requests`
- **模块与功能清单**
  - 实时报价、K 线（新浪/Yahoo）、本地技术指标、东财/Yahoo/SEC 基本面、资金流
  - V2.0 深水区：CBOE 期权、FINRA 做空、SEC EDGAR、全市场 screener、国债/CFTC/财报日历
  - 合规分级（S/B/C）；**无** UI / 回测 / 执行 / 仓内 tests
- **对外接口**：Skill only；无 CLI/HTTP/MCP/DB
- **数据资产**：不分发行情文件；限流与 Yahoo crumb 在 Skill 内管理
- **与 stock-platform 当前关系**：**已接（语义）** — `MarketStrategy`、`GlobalReplayProvider`、datasets 契约。**未接**：期权/SEC/FINRA 刻意不搬；`global_http` live 相对 Skill 全量仍偏薄。
- **合并候选价值**：**中** — 字段与合规分级可反哺 contracts；整仓并入与「单数据主链」冲突。

---

### tick-stock-panel

- **定位一句话**：自托管 A 股「选股 + 监控 + 回测 + 因子挖掘」全栈工作台（TickFlow 适配，多源插件化）。
- **技术栈 / 入口**
  - 后端：`backend/pyproject.toml`（FastAPI + Polars + DuckDB + Parquet + APScheduler，约 v0.2.3）
  - 前端：`frontend/package.json`（React 18 + Vite + ECharts + lightweight-charts）
  - 入口：`uvicorn app.main:app --port 3018`；Docker；可选 `python -m app.desktop`
  - 规范：`CONTRIBUTING.md`、`docs/secondary-development.md`、插件/自定义数据源文档
- **模块与功能清单**
  - **数据**：`data_providers/` 能力矩阵 + TickFlow/YAML/插件；`tickflow/` 仓库与调度
  - **指标/策略**：`indicators/` 富化流水线；`strategy/` 25+ 内置 + AI 策略 + 监控规则
  - **选股/回测**：`services/screener`；`backtest/`（因子/策略/分钟/walk-forward/挖掘矩阵）
  - **服务**：K 线同步、实时、监控通知、复盘、财务 PIT 等 40+ 模块；`api/` 约 28 路由 + SSE
  - **UI**：30+ 页面（Dashboard/Watchlist/Screener/Backtest/Factors/Monitor/…）；L1–L3 二开插槽
  - **运维**：Docker、PyInstaller/Inno、探针脚本、watchdog；`backend/tests/` 大规模
- **对外接口**：HTTP REST+SSE（无统一 Typer CLI）；消费 TickFlow SDK；无 MCP；数据目录 Parquet + DuckDB 内存视图
- **数据资产**：`{data_dir}/` 下 kline_*、adj_factor、financials、pools、backtest_results、user_data 等（git 忽略）
- **与 stock-platform 当前关系**：**已接（契约/薄壳）** — 能力矩阵语义、fail-closed、workbench 端口习惯（ADR 0006）。**未接**：完整 React SPA、Polars 回测/挖掘、监控中心、TickFlow 档位、Docker 形态。
- **合并候选价值**：**高（分阶段，非整仓）** — 产品能力最全；平台策略是里程碑吸收契约与能力，禁止 fork 双维护。

---

### TradingAgents-astock

- **定位一句话**：基于 TradingAgents 的 A 股多 Agent LLM 投研框架（7 Analyst + Bull/Bear + 三方风险辩论 → 评级报告）。
- **技术栈 / 入口**
  - `pyproject.toml`：`tradingagents-astock`（约 v0.5.17）；LangGraph + LangChain + Streamlit + mootdx
  - CLI：`tradingagents`（裸跑分析）、`tradingagents performance`；Web：`tradingagents-web` → Streamlit
- **模块与功能清单**
  - **数据**：`tradingagents/dataflows/a_stock.py`（多源 HTTP/TCP，`_em_get`）；中文 ticker 解析；未来函数/非 A 股防护
  - **Agent**：7 Analyst；bull/bear；research/portfolio manager；trader；三方风险；quality_gate；`rating.py`；记忆日志
  - **编排**：`tradingagents/graph/` LangGraph + 可选 SQLite checkpoint；`llm_clients/` 多厂商
  - **绩效**：`performance.py`（`direction_accuracy` 等，零 LLM）
  - **UI**：Streamlit 进度/报告/PDF；CLI Rich 终端
  - **测试**：`tests/`（声明基线约 361 passed / 13 skipped）
- **对外接口**：CLI + Streamlit；pip 包核心 `TradingAgentsGraph`；无独立业务 HTTP/MCP；记忆默认 `~/.tradingagents/memory/`
- **数据资产**：无 bundled fixtures；运行时 live；mootdx 名称映射缓存
- **与 stock-platform 当前关系**：**已接（薄适配）** — `packages/agents` 插件（禁内嵌 HTTP）；确定性辩论；绩效命名对齐；符号/`em_get` 口径。**未接**：完整 LangGraph LLM 图；`a_stock.py` **禁止**回灌平台（数据只走 providers）。
- **合并候选价值**：**中** — 角色提示与评级/绩效口径可移植；不适合整包依赖合并。

---

### finance-quant-skills

- **定位一句话**：面向 AI Agent 的**金融量化 Skills 文档与辅助脚本维护仓**（[Agent Skills](https://agentskills.io) 标准）。**不是** stock-platform 运行时模块。
- **技术栈 / 入口**
  - 形态：`skills/*/SKILL.md` + `references/` + 可选 `scripts/*.py`；Claude plugin `marketplace.json`；`npx skills add …`
  - `pyproject.toml` / `package.json` 仅为文档抓取/示例脚本依赖，**非产品 pip 包**；`main.py` 为占位
- **模块与功能清单**（13 Skills）
  | Skill | 性质 |
  |-------|------|
  | akshare / baostock / tushare / jqdatasdk / tdxquant / miniqmt / pywencai | 数据 API 文档+示例脚本 |
  | joinquant-strategy / qmt-strategy | 策略平台 API 文档镜像 |
  | akquant / backtrader / rqalpha | 回测/策略框架文档 |
  | equity-researcher | 投研报告 Skill（多子 SKILL） |
  - 另有：`USAGE_EXAMPLES.md`、`AWESOME-QUANT.md`、`template/SKILL.md`
- **对外接口**：文档分发 + 示例脚本；**无**产品 CLI/HTTP/MCP/SDK/DB
- **数据资产**：无运行时落盘；仅有 API 文档镜像与示例
- **与 stock-platform 当前关系**：**未接（运行时）**；治理层已在 `docs/upstream-archive.md` 标明「不进运行时 / 不安装为依赖」
- **合并候选价值**：**中（文档）/ 低（代码）** — 可作 Cursor Skills 软链或只读参考；禁止第二抓取链或 pip 依赖。

---

### market-report-dashboard

- **定位一句话**：AI Skill——用 WebSearch 填三类深色终端 HTML 看板（A股盘前 / A股盘中 / 美股盘前），强制机会与风险可证伪表述。
- **技术栈 / 入口**：仅 `SKILL.md` + `references/` + `templates/`（7 文件）；无 pip/HTTP/DB/git（扫描时）。
- **模块**：编排红线、数据清单、搜索句式、视觉规范、三份 HTML 模板（`{{占位符}}`）。
- **交易策略**：**未发现**（叙事研判模板 ≠ 可编程策略）。
- **与 stock-platform**：**已挂接** — 模板副本 [`../upstream/market-report-templates/`](../upstream/market-report-templates/) + Workbench `#intel-report`；ADR 0053 对照 + `intel-report/crosswalk|prefill`（MR-3/MR-5，v3.12.5）。**刻意不做**：Skill 运行时 import、WebSearch 主链、M-E4 实盘。详档 [`../upstream/market-report-dashboard-capability-report.md`](../upstream/market-report-dashboard-capability-report.md)。
- **合并候选价值**：**中（UI/内容配方）/ 低（代码）** — 软链只读；禁止当第二数据主链。

### V2-code-review-20260905

- **定位一句话**：**2026-09-05 采集的 A 股行业 ETF 策略工作台代码审阅快照**（`MANIFEST.json`：`development_review_snapshot_not_release`）。**不是**可部署发行版；无完整 git 历史、真实 `data/`、账户与凭据。
- **技术栈 / 入口**
  - 前端：Next.js + React（`source/app/workbench/`）；原 macOS 启动脚本未打包
  - 后端：stdlib `ThreadingHTTPServer`（`data_service.py` `:8765`）；`auto_trading_runner.py` daemon/once
  - 依赖声明：`requirements-data.txt`（akshare / pytdx / futu-api）
  - 另有 `runtime-baseline/`（采集时本机运行中的 Python 子集）与 `SOURCE_DIFFERENCES.md`
- **模块与功能清单**
  - **策略/执行内核**：`strategy_engine.py`（大盘评分、ETF 排名、调仓、回撤刹车）；`strategy_version` / `market_timing` / `trading_calendar`；`transactional_state`；`futu_paper`（OpenD SIMULATE）；`v2_fee_upgrade`；`v3_research`（只读实验）
  - **数据**：`tdx_data.py`（pytdx + 复权校验）
  - **HTTP**：回测/稳健性/纸面草案执行/账户绩效/任务调度/策略激活
  - **UI**：Overview / Daily / Research / System 等页；IndexedDB 本地状态
  - **审阅焦点**：调度可靠性、信号新鲜度、交易日历、事务化执行、券商状态机、草稿 vs 激活、费用门槛等
  - **测试**：`source/tests/` 约 12 套 Python + 前端 HTML 测
- **对外接口**：CLI runner；HTTP `:8765`；前端 localhost；**无 MCP**；D1/Drizzle 占位空 schema；真实 `data/` **未打包**
- **数据资产**：`examples/strategy-parameters.review.json`（脱敏）；架构图；无真实账户/订单
- **与 stock-platform 当前关系**：**已接（结论）** — 执行安全 → `packages/execution`（timing/transactional/lifecycle/admission/paper）。**未接**：Futu OpenD、完整 Next.js UI、ETF 轮动规则引擎、双轨 `data_service` HTTP。
- **合并候选价值**：**低（整仓代码）/ 中（参考）** — 结论已落地；可参考策略规则与测试矩阵，禁止引入 `futu-api` 与第二数据主链。

---

## 下一步建议（仅路线，不实现）

按**能力域**做合并路线图，而不是「整仓 merge」：

1. **数据域**  
   - 以 `packages/providers` + 能力矩阵为唯一权威。  
   - 从 `a-stock-data` / `global-stock-data` **按端点增量**吸收配方（字段、限流、备胎），先扩矩阵再接线。  
   - 继续只读挂载 `a-stock-engine` 的 `market.db`；评估是否暴露 PIT 基本面表（新 ADR，非整仓拷贝）。

2. **选股 / 回测域**  
   - 主链保持 lvrev + brief + PIT。  
   - 需要更强回测/挖掘时，对照 `tick-stock-panel` 的契约与测试，**分里程碑移植能力**（非 React/Polars 整仓）。  
   - `a-stock-engine/empirical` 作基线对照，不恢复双管线。

3. **Agent 域**  
   - 默认确定性辩论 + 可选 LLM。  
   - 需要更深投研时，从 TradingAgents **移植角色提示/工具清单/评级边界**，数据强制走 providers（ADR 0009）。

4. **UI 域**  
   - 短期强化现有 Workbench 向导与可读性。  
   - 若要专业图表/监控，再开「TSP UI 子集」里程碑；避免同时维护两套前端主链。

5. **执行 / 运维域**  
   - 纸面 + `BrokerPort` 继续演进；同花顺真实 HTTP / 实盘仍延期。  
   - V2 快照仅作安全回归用例参考，不恢复 Futu。

6. **文档技能仓**  
   - `finance-quant-skills`（及 a-stock-data / global-stock-data Skill 形态）保持 **Cursor/Claude Skills 软链或只读引用**。  
   - **不要假装已是运行时模块**；禁止 `pip install` 进产品依赖、禁止平行抓取。

### 合并优先级速查

| 优先级 | 来源 | 建议动作 |
|--------|------|----------|
| P0 输入 | 本盘点 + upstream-archive 红线 | ✅ 已写：[capability-domain-merge-roadmap.md](capability-domain-merge-roadmap.md) |
| 高 | tick-stock-panel | 契约已齐；选下一刀（回测子集 / 监控 / UI 壳）→ 见路线图 M-R1 / M-U3 |
| 中 | a-stock-engine / a-stock-data / TA / global | DB 与配方/角色增量 → M-D* / M-A* |
| 低 | V2 整仓 / finance-quant-skills 代码 | 只读；Skills 软链即可 → M-E* / M-S* |

---

## 相关路线图

按能力域合并（非整仓 merge）的可执行里程碑：[`capability-domain-merge-roadmap.md`](capability-domain-merge-roadmap.md)。

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-09-15 | 初版：八仓统一模板盘点 + 能力域总表 + 下一步建议 |
| 2026-09-15 | 文末短链指向能力域合并路线图 |
| 2026-09-23 | 增补 `market-report-dashboard`（Skill HTML 看板；见 upstream 能力报告） |
| 2026-09-23 | v3.12.4：模板入库 + Workbench 情报报告入口 + MR 里程碑（非整仓） |
