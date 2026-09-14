# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循本仓 [`docs/versioning.md`](docs/versioning.md)。

## [Unreleased]

### Added

- （无）

## [3.8.0] - 2026-09-14

### Added

- **Phase E 日用稳定收口（M39–M46）**
  - M39：分层宇宙 + 可读推荐理由（ADR 0040）
  - M40：`stock-platform-daily` refresh→brief 流水线（ADR 0041）
  - M41：`sector_fund_flow` / `news`（ADR 0042）
  - M42：日历 2028+ + Task Scheduler/cron（ADR 0044）
  - M43：组合回测指标 + 纸面 fills 对齐绩效（ADR 0043）
  - M44：LLM 预算/截断/降级（ADR 0045）
  - M45：Workbench IA + 一键向导（ADR 0046）
  - 默认仍 paper + replay + SIMULATE；无 SPA；无真实券商；同花顺真实 transport 仍 backlog

## [3.7.0] - 2026-09-14

### Added

- **大里程碑 M45 完成**：Workbench IA + 一键向导
  - 顶栏分区：日用向导 / 推荐 / 纸面 / 运维；`#wizard` + `#ops`
  - `POST /api/research/wizard/daily`（refresh→brief→to-paper；分步可见失败）
  - ADR 0046；无 SPA；无实盘默认文案

## [3.6.0] - 2026-09-14

### Added

- **大里程碑 M44 完成**：LLM 成本/质量控制
  - 调用/token 预算；截断告警（含 Responses incomplete）；超限默认降级 deterministic
  - ADR 0045；默认仍 deterministic；`[llm]` 仍为可选 extra

## [3.5.0] - 2026-09-14

### Added

- **大里程碑 M43 完成**：组合回测加深 + 绩效对齐纸面成交
  - `portfolio_metrics` / `run_portfolio_pit`（回撤、换手、成交数）
  - `align_fills_to_performance` 从纸面 fills 回填 JSONL；`direction_accuracy` 口径不变
  - ADR 0043；默认 SIMULATE；CI fixtures

## [3.4.0] - 2026-09-14

### Added

- **大里程碑 M42 完成**：日历 2028+ + Task Scheduler/cron 运维包
  - CN/US/HK 静态休市日延伸至 2028+（provisional）
  - `scripts/ops/Invoke-DailyPipeline.ps1` + Task Scheduler XML + cron 样例
  - `docs/ops/scheduler.md` / `calendar-maintenance.md`；ADR 0044

## [3.3.0] - 2026-09-14

### Added

- **大里程碑 M41 完成**：板块资金流 / 新闻特征
  - 能力 `sector_fund_flow` / `news`；replay + `astock_http`（`em_get`）
  - 契约 + fixtures；workbench API/薄 UI；缺能力 fail-closed
  - ADR 0042；默认 replay；CI 零公网

## [3.2.0] - 2026-09-14

### Added

- **大里程碑 M40 完成**：定时 refresh→brief 日流水线
  - `run_daily_pipeline` + CLI `stock-platform-daily`；产物 `briefs/{asof}` + `latest.json`
  - 同 asof 幂等覆盖；失败 fail-closed 写 `failure.json`
  - `docs/ops/daily-pipeline.md`；ADR 0041；默认 replay

## [3.1.0] - 2026-09-14

### Added

- **大里程碑 M39 完成**：日用宇宙扩容 + 可读推荐理由
  - 分层宇宙 `core` / `watch` / `full`（`load_universe_tiers`）；样例 `universe_cn_daily.json`
  - brief `reasons[]` + `reasonSummary`（保留兼容 `reason`）；`#recommend` 展示中文摘要
  - `docs/ops/daily-universe.md`；ADR 0040；CI 仍用小 fixture；默认 replay + SIMULATE

## [3.0.0] - 2026-09-14

### Added

- **Phase D 同花顺模拟盘收口（M35–M38）**
  - M35：`BrokerPort` / `PaperBroker` / `resolve_broker`（ADR 0036）
  - M36：`ThsSimBroker` + mock transport；experimental HTTP 扩展点（ADR 0037）
  - M37：`GatedBroker` / admission 接到 `ths_sim`（ADR 0038）
  - M38：brief → broker E2E；`GET /api/broker/status`；`#broker` 只读面板（ADR 0039）
  - 默认仍 `STOCK_PLATFORM_BROKER=paper` + replay；SIMULATE；无实盘
  - 真实 THS HTTP：**experimental/pending**（无稳定公开零售模拟盘 API）

## [2.9.0] - 2026-09-14

### Added

- **大里程碑 M37 完成**：风控闸门接到外部模拟
  - `assert_sim_gates` / `GatedBroker`；ths_sim 复用 timing/window/idempotency/admission
  - ADR 0038

## [2.8.0] - 2026-09-14

### Added

- **大里程碑 M36 完成**：同花顺模拟盘适配器
  - `ThsSimBroker`；`MockThsTransport`（CI 零公网）；`ExperimentalThsHttpTransport` fail-closed
  - Env：`STOCK_PLATFORM_THS_MODE` / `STOCK_PLATFORM_THS_*`；ADR 0037

## [2.7.0] - 2026-09-14

### Added

- **大里程碑 M35 完成**：执行端口抽象
  - `BrokerPort` / `PaperBroker` / `ExternalSimBroker`；Order/Fill/Position/Account 契约
  - `STOCK_PLATFORM_BROKER=paper|ths_sim`（默认 paper）；ADR 0036

## [2.6.0] - 2026-09-14

### Added

- **Phase C 投研稳定收口（M32–M34）**
  - M32：推荐绩效 JSONL + `direction_accuracy` 口径（ADR 0033）
  - M33：可选 LLM 辩论（默认确定性；`[llm]` fail-closed；ADR 0034）
  - M34：策略配置版本化 + `run_pit_long_only` 对比入口（ADR 0035）
  - 默认仍 replay；SIMULATE；无同花顺 / 实盘 / SPA

## [2.5.0] - 2026-09-14

### Added

- **大里程碑 M33 完成**：可选 LLM 辩论挂在 TopN 之后
  - 默认仍 M12 确定性 `engine=deterministic`
  - `engine=llm` + `[llm]` optional-extra；缺依赖/密钥 fail-closed
  - `POST /api/research/brief/debate`；`GET /api/debate/report?engine=`
  - ADR 0034；mocked LLM 单测

## [2.4.0] - 2026-09-14

### Added

- **大里程碑 M32 完成**：推荐决策绩效统计
  - JSONL 决策日志 + `compute_performance`（`direction_accuracy` / `avg_return` / `up_rate` 口径）
  - CLI `stock-platform-performance`；`GET /api/research/performance`；工作台 `#performance`
  - ADR 0033；确定性 fixtures

## [2.3.0] - 2026-09-14

### Added

- **Phase B 运维稳定收口（M29–M31）**
  - M29：`stock-platform-refresh` 日 K / 复权因子 / 资金流 / full_minute 落盘（ADR 0030）
  - M30：live 偏好模板 + 东财熔断（ADR 0031）
  - M31：`GET /api/ops/health` + fixture 录制文档（ADR 0032）
  - 默认仍 replay；SIMULATE；CI 零公网

## [2.2.0] - 2026-09-14

### Added

- **大里程碑 M30 完成**：live 偏好模板 + 东财节流/熔断
  - 预设 `replay` / `cn_astock_http` / `us_hk_global_http`（启动默认仍 replay）
  - `EM_CIRCUIT_FAILURES` / `EM_CIRCUIT_COOLDOWN`；`EastmoneyClient.snapshot()`
  - workbench `GET /api/settings/presets` + `POST .../apply`

## [2.1.0] - 2026-09-14

### Added

- **大里程碑 M29 完成**：CN 日数据刷新 / full_minute 落盘
  - `run_refresh` / `stock-platform-refresh`；重试 + manifest；`STOCK_PLATFORM_REFRESH_DIR`
  - ReplayTransport 文件名；CI `--provider replay`；ADR 0030

## [2.0.0] - 2026-09-14

### Added

- **Phase A 产品稳定（M24–M28）**：日更选股推荐 + 纸面交易闭环
  - M24 宇宙 + PIT 截面面板（ADR 0029）
  - M25 盘前简报（`build_premarket_brief` / CLI / `GET /api/research/brief`）
  - M26 工作台「今日推荐」UI
  - M27 TopN → PaperLedger 草稿（SIMULATE；默认 CN）
  - 默认仍 replay；无同花顺/实盘；无 LLM；无 SPA

## [1.20.0] - 2026-09-14

### Added

- **大里程碑 M27 完成**：Recommend → PaperLedger
  - `POST /api/research/brief/to-paper`；UI 一键纸面草稿；SIMULATE only；默认 market=CN
  - 复用 timing/window/freshness；`liveTradingEnabled=false`

## [1.19.0] - 2026-09-14

### Added

- **大里程碑 M26 完成**：工作台「今日推荐」
  - UI `#recommend` + TopN 分数/理由表；链接日 K / 纸面；默认 replay

## [1.18.0] - 2026-09-14

### Added

- **大里程碑 M25 完成**：盘前简报批处理
  - `build_premarket_brief` / `stock-platform-brief`；`GET /api/research/brief`
  - lvrev + entry gates → TopN + reasons；默认 replay；CI 零公网

## [1.17.0] - 2026-09-14

### Added

- **大里程碑 M24 完成**：CN 宇宙 + PIT 日截面面板（ADR 0029；`load_universe` / `build_cross_section_panel` / CSV）
  - 空宇宙 fail-closed；注入 providers；默认仍无公网抓取

## [1.16.1] - 2026-09-14

### Added

- M24.1：CN 宇宙 + PIT 日截面面板（ADR 0029）
  - `load_universe` / `build_cross_section_panel` / `panel_to_csv`；空宇宙 fail-closed
  - 注入 daily（可选 adj_factor / fund_flow）；CI 零公网

## [1.16.0] - 2026-09-14

### Added

- **大里程碑 M23 完成**：CN 复权套价（`apply_adjust`；qfq 除 / hfq 乘；消费 daily + adj_factor）
  - ADR 0028；workbench API/UI；默认仍 replay；不新增能力 id；空因子 fail-closed

## [1.15.2] - 2026-09-14

### Added

- M23.2：workbench `GET /api/market/daily-adjusted` + UI `#daily-adjusted`；默认偏好 replay

## [1.15.1] - 2026-09-14

### Added

- M23.1：CN 复权套价 `apply_adjust`（ADR 0028）
  - qfq 除 / hfq 乘；空因子 fail-closed；不新增能力 id；CI 零公网

## [1.15.0] - 2026-09-14

### Added

- **大里程碑 M22 完成**：CN 全量分钟（能力矩阵 `full_minute`；replay + `em_get` 当日 1m 批量）
  - ADR 0027；workbench API/UI；默认仍 replay；与多频 `minute` 区分；无后台落盘 / get_intraday_latest

## [1.14.2] - 2026-09-14

### Added

- M22.2：workbench `GET /api/market/full-minute` + UI `#full-minute`；默认偏好 replay

## [1.14.1] - 2026-09-14

### Added

- M22.1：CN 全量分钟 `full_minute`（激活矩阵第七项；ADR 0027）
  - `ReplayProvider` / `AStockHttpProvider.get_full_minute`；东财 push2his `klt=1`（em_get）；fixtures；与多频 `minute` 区分；CI 零公网

## [1.14.0] - 2026-09-14

### Added

- **大里程碑 M21 完成**：CN 个股复权因子（能力矩阵 `adj_factor`；replay + 新浪 qfq/hfq HTTP）
  - ADR 0026；workbench API/UI；默认仍 replay；mootdx / 东财复权备胎 / apply_adjust 套价不做

## [1.13.2] - 2026-09-14

### Added

- M21.2：workbench `GET /api/market/adj-factor` + UI `#adj-factor`；默认偏好 replay

## [1.13.1] - 2026-09-14

### Added

- M21.1：CN 复权因子 `adj_factor`（激活矩阵第二项；ADR 0026）
  - `ReplayProvider` / `AStockHttpProvider.get_adj_factor`；新浪 qfq/hfq（非 em_get）；fixtures；CI 零公网

## [1.13.0] - 2026-09-14

### Added

- **大里程碑 M20 完成**：CN 个股财务报表（能力矩阵 `financial`；replay + 新浪三表 HTTP）
  - ADR 0025；workbench API/UI；默认仍 replay；mootdx / 东财财报备胎不做

## [1.12.2] - 2026-09-14

### Added

- M20.2：workbench `GET /api/market/financial` + UI `#financial`；默认偏好 replay

## [1.12.1] - 2026-09-14

### Added

- M20.1：CN 财务报表 `financial`（激活矩阵第六项；ADR 0025）
  - `ReplayProvider` / `AStockHttpProvider.get_financial`；新浪三表（非 em_get）；fixtures；CI 零公网

## [1.12.0] - 2026-09-14

### Added

- **大里程碑 M19 完成**：CN 个股五档盘口（能力矩阵 `depth5`；replay + `em_get` push2 stock/get）
  - ADR 0024；workbench API/UI；默认仍 replay；mootdx / 交易所官方备胎不做

## [1.11.2] - 2026-09-14

### Added

- M19.2：workbench `GET /api/market/depth5` + UI `#depth5`；默认偏好 replay

## [1.11.1] - 2026-09-14

### Added

- M19.1：CN 五档盘口 `depth5`（激活矩阵第五项；ADR 0024）
  - `ReplayProvider` / `AStockHttpProvider.get_depth5`；fixtures；量=手；CI 零公网

## [1.11.0] - 2026-09-14

### Added

- **大里程碑 M18 完成**：CN 个股分钟 K（能力矩阵 `minute`；replay + `em_get` push2his kline）
  - ADR 0023；workbench API/UI；默认仍 replay；`full_minute` / 腾讯备胎不做

## [1.10.2] - 2026-09-14

### Added

- M18.2：workbench `GET /api/market/minute` + UI `#minute`；默认偏好 replay

## [1.10.1] - 2026-09-14

### Added

- M18.1：CN 分钟 K `minute`（激活矩阵第四项；ADR 0023）
  - `ReplayProvider` / `AStockHttpProvider.get_minute`；fixtures；北京墙钟 naive；CI 零公网

## [1.10.0] - 2026-09-14

### Added

- **大里程碑 M17 完成**：CN 个股限售解禁（能力矩阵 `unlock`；replay + `em_get` datacenter）
  - ADR 0022；workbench API/UI；默认仍 replay；全市场解禁日历不做

## [1.9.2] - 2026-09-14

### Added

- M17.2：workbench `GET /api/market/unlock` + UI `#unlock`；默认偏好 replay

## [1.9.1] - 2026-09-14

### Added

- M17.1：CN 限售解禁 `unlock`（能力矩阵第十项；ADR 0022）
  - `ReplayProvider` / `AStockHttpProvider.get_unlock`；fixtures；空窗口不崩；CI 零公网

## [1.9.0] - 2026-09-14

### Added

- **大里程碑 M16 完成**：CN 个股龙虎榜（能力矩阵 `lhb`；replay + `em_get` datacenter）
  - ADR 0021；workbench API/UI；默认仍 replay；全市场日榜 / 交易所备胎不做

## [1.8.2] - 2026-09-14

### Added

- M16.2：workbench `GET /api/market/lhb` + UI `#lhb`；默认偏好 replay

## [1.8.1] - 2026-09-14

### Added

- M16.1：CN 龙虎榜 `lhb`（能力矩阵第九项；ADR 0021）
  - `ReplayProvider` / `AStockHttpProvider.get_lhb`；fixtures；空窗口不崩；CI 零公网

## [1.8.0] - 2026-09-14

### Added

- **大里程碑 M15 完成**：CN 日级资金流（能力矩阵 `fund_flow`；replay + `em_get`）
  - ADR 0020；workbench API/UI；默认仍 replay；分钟/板块资金流与龙虎榜不做

## [1.7.2] - 2026-09-14

### Added

- M15.2：workbench `GET /api/market/fund-flow` + UI `#fund-flow`；默认偏好 replay

## [1.7.1] - 2026-09-14

### Added

- M15.1：CN 日级资金流 `fund_flow`（能力矩阵第八项；ADR 0020）
  - `ReplayProvider` / `AStockHttpProvider.get_fund_flow`；fixtures；CI 零公网

## [1.7.0] - 2026-09-14

### Added

- **大里程碑 M14 完成**：多市场纸面 timing（CN/US/HK 日历 + 本地时区）
  - ADR 0019；`PaperLedger` / workbench 可选 `market`（默认 CN）；半日市 / 实盘不做

## [1.6.2] - 2026-09-14

### Added

- M14.2：PaperLedger / workbench /api/paper/* 可选 market（默认 CN）；草稿 marketId

## [1.6.1] - 2026-09-14

### Added

- M14.1：纸面 timing 支持 `market=`（CN/US/HK）；`market_now` / `daily_bar_final_at`（ADR 0019）
  - 默认仍 CN；`china_now` / `CHINA_TZ` 保留为别名

## [1.6.0] - 2026-09-14

### Added

- **大里程碑 M13 完成**：US/HK 静态交易日历（对标 CN；MarketStrategy 自动生效）
  - ADR 0018；纸面默认仍 CN timing；不拉交易所 API

## [1.5.2] - 2026-09-14

### Added

- M13.2：`MarketStrategy` US/HK 假日验收；`market-strategy` / providers README / upstream-archive 同步

## [1.5.1] - 2026-09-14

### Added

- M13.1：US/HK 静态休市日表 + `get_trading_calendar` 通用加载（ADR 0018）

## [1.5.0] - 2026-09-14

### Added

- **大里程碑 M12 完成**：确定性 Bull/Bear/Risk 轻量辩论（无 LLM）
  - `/api/debate/report` + UI；ADR 0017

## [1.4.2] - 2026-09-14

### Added

- M12.2：`GET /api/debate/report` + UI `#debate` 区

## [1.4.1] - 2026-09-14

### Added

- M12.1：确定性 `build_debate_report` / Bull·Bear·Risk（ADR 0017；无 LLM）

## [1.4.0] - 2026-09-14

### Added

- **大里程碑 M11 完成**：Workbench 最小 UI（`GET /` 单页操作台）
  - 能力矩阵 / 日 K / 纸面 status；ADR 0016

## [1.3.2] - 2026-09-14

### Added

- M11.2：UI 三区交互（矩阵 / 日 K / 纸面）；409 fail-closed 可见；可切 daily 偏好

## [1.3.1] - 2026-09-14

### Added

- M11.1：workbench `GET /` Jinja2 壳 + `/static`（ADR 0016）

## [1.3.0] - 2026-09-14

### Added

- **大里程碑 M10 完成**：CN 静态交易日历（休市日表 + timing / MarketStrategy 共用）
  - ADR 0015；US/HK 假日表见后续 M13 / ADR 0018

## [1.2.2] - 2026-09-14

### Added

- M10.2：`MarketStrategy.is_trading_day` 与纸面 `timing` 共用 CN 日历
- `completed_bar_cutoff` 回退跳过非交易日；execution 依赖 providers
- 修复：包内 `data/cn_closed_days.txt` 不再被根 `.gitignore` 的 `data/` 规则忽略

## [1.2.1] - 2026-09-14

### Added

- M10.1：`TradingCalendar` / `get_trading_calendar` + 静态 `cn_closed_days.txt`（ADR 0015）

## [1.2.0] - 2026-09-14

### Added

- **大里程碑 M9 完成**：可选美港 live HTTP（`GlobalHttpProvider` / Yahoo + 新浪）
  - workbench preferences 可切 `global_http`；默认仍 replay
  - ADR 0014；`a-stock-engine` 归档横幅

## [1.1.2] - 2026-09-14

### Added

- M9.2：workbench 注册 `GlobalHttpRouter`，preferences 可切 `global_http`（默认仍 replay）

## [1.1.1] - 2026-09-14

### Added

- M9.1：`GlobalHttpProvider` / `GlobalHttpRouter`（Yahoo 日 K + 新浪实时）
- ADR 0014；能力矩阵 `global_http` usable
- `a-stock-engine` README 归档横幅（指向 stock-platform）

## [1.1.0] - 2026-09-14

### Added

- **大里程碑 M8 完成**：可选 A 股 live HTTP（`AStockHttpProvider` via `em_get`）
  - 默认仍 replay；preferences 可切 live
  - ADR 0013

### Notes

- `global_http` 仍 pending；封禁时降级 replay，禁止裸东财 URL

## [1.0.2] - 2026-09-14

### Added

- M8.2 验收：workbench 注册 `astock_http` 实例，可通过 preferences 切换（默认 replay）

## [1.0.1] - 2026-09-14

### Added

- `AStockHttpProvider`：东财日 K / 实时经 `em_get`（ADR 0013）
- 能力矩阵 `astock_http` usable；单测注入 JSON，CI 不打公网

## [1.0.0] - 2026-09-14

### Added

- **大里程碑 M7 完成 / 产品 v1.0.0**
  - 上游归档说明与 v1 产品边界（ADR 0012）
  - 产品化文档与发版检查清单
  - 版本一致性脚本接入 CI

### Notes

- v1.0 = 可发布研究与纸面决策平台骨架（默认 replay；live HTTP / 实盘仍延期）
- 自本版本起破坏契约须 MAJOR

## [0.7.3] - 2026-09-14

### Added

- M7.3 验收：`release-checklist.md`、`check_versions.ps1`、CI version job

## [0.7.2] - 2026-09-14

### Changed

- README / CONTRIBUTING / AGENTS 按 v1.0 交付面改写
- 修复 upstream-archive 示例链接（避免 docs 自检断链）

## [0.7.1] - 2026-09-14

### Added

- `docs/upstream-archive.md`：上游参考仓归档总表与红线
- ADR 0012：v1.0 产品边界
- （同树预置）产品化 README / 发版清单 / `check_versions.ps1`，验收见 0.7.2 / 0.7.3

## [0.7.0] - 2026-09-14

### Added

- **大里程碑 M6 完成**：纸面执行安全模型
  - `packages/execution` broker-free 内核（吸 V2 结论，无券商 SDK）
  - SIMULATE-only / live=false；草稿≠激活；窗口外禁补单；draftId 幂等
  - workbench `/api/paper/*`

### Notes

- Admission 通过 ≠ 策略已证明；下一步 M7 产品收敛 / 上游归档

## [0.6.3] - 2026-09-14

### Added

- M6.3 验收：workbench 纸面路由与显式激活（无 live 开关）

## [0.6.2] - 2026-09-14

### Added

- M6.2 验收：`PaperLedger` decision_only / 窗口外零订单 / draftId 幂等回放

## [0.6.1] - 2026-09-14

### Added

- `packages/execution`：纸面执行安全内核（timing / transactional / profile / lifecycle / admission）
- ADR 0011；paper-only 闸门（SIMULATE + live=false）
- （同树）`PaperLedger` 与 workbench `/api/paper/*`，验收见 0.6.2 / 0.6.3

## [0.6.0] - 2026-09-13

### Added

- **大里程碑 M5 完成**：美港 Vendor + 市场策略表
  - `MarketStrategy` 分市场 settle / limit / 时区
  - `normalize_symbol(market=US|HK)` 与 CN 隔离
  - `GlobalReplayProvider` + 能力矩阵注册

### Notes

- 节假日日历仍为工作日 stub；live `global_http` 未接线
- 下一步 M6：纸面执行安全模型（吸 V2）

## [0.5.3] - 2026-09-13

### Added

- M5.3 验收：`GlobalReplayProvider`（AAPL / 00700 fixtures）
- 能力矩阵：`global_replay` usable、`global_http` pending

## [0.5.2] - 2026-09-13

### Added

- M5.2 验收：`normalize_symbol(market="US"|"HK")`；CN 路径继续拒港美

## [0.5.1] - 2026-09-13

### Added

- `MarketStrategy` / `get_market_strategy`：CN/US/HK 时区、会话、settle、limit
- US/HK 明确 `buy_to_sell_delay_days=0`、`has_limits=False`（不套用 A 股）
- ADR 0010；契约 `market-strategy.md` 美港表定稿
- （同树预置）US/HK `normalize_symbol` 与 `GlobalReplayProvider`，验收见 0.5.2 / 0.5.3

## [0.5.0] - 2026-09-13

### Added

- **大里程碑 M4 完成**：投研 Agent 插件化（无内嵌抓取）
  - `packages/agents` 仅经 `MarketDataProvider`
  - workbench 研报 / 复盘槽位 + 历史 asof 护栏
  - ADR 0009

### Notes

- TradingAgents-astock 完整 LangGraph 辩论仍可后续接入；不得把东财 URL 写回 agents
- 下一步 M5：美港 Vendor + 市场策略表

## [0.4.2] - 2026-09-13

### Added

- M4.2 验收：workbench 个股研报 / 复盘槽位经能力矩阵 `resolve("daily")`
- 路由测试覆盖 historical asof 告警与港股拒绝

## [0.4.1] - 2026-09-13

### Added

- `packages/agents`：`ResearchAgentPlugin` / `ReviewAgentPlugin`（仅经 providers）
- 历史 `asof` 跳过 realtime 护栏；ADR 0009；CI `agents` job
- workbench 预挂 `/api/research/report`、`/api/review/report`（M4.2 验收于 `0.4.2`）

### Notes

- TradingAgents 完整辩论图仍作参考；平台槽位以本插件为准

## [0.4.0] - 2026-09-13

### Added

- **大里程碑 M3 完成**：`packages/research` 选股/回测内核
  - lvrev 评分与入场闸门（迁自 a-stock-engine）
  - PIT long-only（T 信号 / T+1 open）+ 防未来函数
  - 盘前截面批处理 CLI `stock-platform-score`

### Notes

- a-stock-engine 视为参考实现；平台权威评分路径为本包
- 下一步 M4：TradingAgents 研报插件化（去内嵌抓取）

## [0.3.3] - 2026-09-13

### Added

- `score_cross_section_csv` + 控制台入口 `stock-platform-score`（盘前批处理）

## [0.3.2] - 2026-09-13

### Added

- `run_pit_long_only` + `assert_no_lookahead_columns`（信号日/成交日分离）

## [0.3.1] - 2026-09-13

### Added

- `packages/research`：`score_lvrev` / `apply_entry_gates` / `apply_risk_gates`（迁自 a-stock-engine）
- ADR 0008；CI `research` job

## [0.3.0] - 2026-09-13

### Added

- **大里程碑 M2 完成**：工作台最小壳经能力矩阵消费 Provider
  - FastAPI health / matrix / daily / realtime
  - 缺能力 409 fail-closed；禁品牌硬编码
  - API 与 replay 同标的同日口径对齐

### Notes

- 下一步 M3：迁入选股 / PIT 回测内核（lvrev）

## [0.2.3] - 2026-09-13

### Added

- M2.3 验收：同标的同日 API daily 与 `ReplayProvider` 批处理字段对齐测试

## [0.2.2] - 2026-09-13

### Added

- `PUT /api/settings/preferences`；minute/缺能力 **409** fail-closed 护栏
- 路由源码禁止品牌字面量扫描；ADR 0007

## [0.2.1] - 2026-09-13

### Added

- `apps/workbench`：FastAPI 最小壳（health / capability-matrix / daily / realtime）
- minute 缺能力时 409 fail-closed；ADR 0006；CI `workbench` job

## [0.2.0] - 2026-09-13

### Added

- **大里程碑 M1 完成**：可安装 `stock-platform-providers`
  - ticker 归一化与港美拒绝
  - daily/realtime 录制回放契约测试
  - 东财 `em_get` 限流单点 + 能力矩阵注册
  - 文档禁止裸东财 URL

### Notes

- Live HTTP 行情适配仍为 pending（`astock_http`）；下一阶段 M2 接入工作台壳

## [0.1.3] - 2026-09-13

### Added

- `em_get` / `EastmoneyClient`：东财串行限流单点（禁非 EM URL）
- `build_capability_matrix` / `register_builtin_providers`
- `docs/contracts/eastmoney-http.md`、ADR 0005

## [0.1.2] - 2026-09-13

### Added

- `ReplayTransport` / `ReplayProvider`：daily + realtime 录制回放
- `normalize_daily_row` / `normalize_realtime_row` 契约归一化
- ADR 0004；fixtures 与 pytest 覆盖

## [0.1.1] - 2026-09-13

### Added

- `packages/providers`：可安装包 `stock-platform-providers`
- `normalize_symbol` / `exchange_prefix` / `is_bse_symbol` + pytest
- ADR 0003；CI `providers` job（含与根 `VERSION` 对齐校验）

## [0.1.0] - 2026-09-13

### Added

- **大里程碑 M0 完成**：工程架子、契约 Accepted、CI/文档自检、SemVer tag 流程可协作

### Notes

- 仍无可运行行情/选股业务；下一阶段 M1（`v0.2.0`）开始 `packages/providers` 可安装实现

## [0.0.3] - 2026-09-13

### Added

- `scripts/check_docs.ps1`：必选文件、VERSION↔CHANGELOG、Markdown 相对链接检查
- CI：docs 自检 + `release_tag.ps1 -DryRun`

### Changed

- `release_tag.ps1`：`-DryRun` 不再因 tag 已存在或脏工作区失败
- README / versioning：补充 DryRun 与自检示例

## [0.0.2] - 2026-09-13

### Added

- ADR 0002：M0.2 数据集与市场口径冻结
- 契约定稿：`datasets` / `capability-matrix` / `market-strategy`（对齐 TSP）

### Changed

- 关闭 M0.2 关键 TBD（amount 元、ex_factor、asset_type、asof_ts、usable 形状、CN 规则表）

## [0.0.1] - 2026-09-13

### Added

- 仓库骨架：`apps/`、`packages/`、`docs/`、`scripts/`
- 目标架构 ADR、契约草稿、里程碑 ROADMAP、tag 升级规则
- `VERSION` 单一版本源与 `scripts/release_tag.ps1`
- Git 初始化（`main`）与首个工程 tag `v0.0.1`

[Unreleased]: https://github.com/local/stock-platform/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/local/stock-platform/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/local/stock-platform/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/local/stock-platform/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/local/stock-platform/compare/v0.7.3...v1.0.0
[0.7.3]: https://github.com/local/stock-platform/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/local/stock-platform/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/local/stock-platform/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/local/stock-platform/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/local/stock-platform/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/local/stock-platform/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/local/stock-platform/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/local/stock-platform/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/local/stock-platform/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/local/stock-platform/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/local/stock-platform/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/local/stock-platform/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/local/stock-platform/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/local/stock-platform/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/local/stock-platform/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/local/stock-platform/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/local/stock-platform/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/local/stock-platform/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/local/stock-platform/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/local/stock-platform/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/local/stock-platform/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/local/stock-platform/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/local/stock-platform/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/local/stock-platform/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/local/stock-platform/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/local/stock-platform/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/local/stock-platform/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/local/stock-platform/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/local/stock-platform/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/local/stock-platform/releases/tag/v0.0.1
