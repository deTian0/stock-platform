# stock-platform

可发布的量化**研究与纸面决策**平台：统一 Vendor、选股/PIT、工作台 API、投研 Agent 槽位、纸面执行安全模型，收敛在单一产品仓。

> 当前版本见 [`VERSION`](VERSION)（`v4.13.7`）。现行快照 [`docs/STATUS.md`](docs/STATUS.md)；文档索引 [`docs/README.md`](docs/README.md)；历史里程碑 [`docs/ROADMAP.md`](docs/ROADMAP.md)；仍有效的计划 [`docs/plans/`](docs/plans/)；发版 [`docs/release-checklist.md`](docs/release-checklist.md)；上游归档 [`docs/upstream-archive.md`](docs/upstream-archive.md)。

## v1.0 交付面

| 组件 | 路径 | 能力 |
|------|------|------|
| Providers | `packages/providers` | CN/US/HK 归一化、replay、`em_get`、可选 live、`TradingCalendar`（CN）、能力矩阵、`MarketStrategy` |
| Research | `packages/research` | lvrev / 闸门 / PIT / 分层宇宙 / 盘前简报 / `stock-platform-daily` / refresh / performance / portfolio |
| Agents | `packages/agents` | 研报/复盘/确定性辩论；可选 LLM（预算/降级） |
| Execution | `packages/execution` | 纸面 SIMULATE、`BrokerPort` / `PaperBroker`、可选 `ths_sim`（mock） |
| Workbench | `apps/workbench` | FastAPI + 最小 UI：日用向导 / 推荐 / 纸面 / 运维 |

**默认运行时（v3.9+）**：行情偏好默认 **CN live**（`astock_http` / `em_get`）；美港可切 `global_http`。  
CI / 本地测试设 `STOCK_PLATFORM_PROVIDER_PRESET=replay` 保持零公网。详见 [`docs/ops/live-startup.md`](docs/ops/live-startup.md)。  
**明确不做**：实盘券商、默认 `ths_sim`、默认开启 LLM 辩论、React SPA、第二套行情主链、同花顺真实 HTTP（backlog）。  
**同花顺**：仅 `STOCK_PLATFORM_BROKER=ths_sim` 显式开启；默认 mock；真实 HTTP 为 experimental/pending（无稳定公开零售模拟盘 API）。分档说明见 [`docs/ops/broker-port-honesty.md`](docs/ops/broker-port-honesty.md)。**M-E4 实盘仍门禁，未开工。**
**交易**：始终 paper / SIMULATE（`liveTradingEnabled=false`）——「真实」仅指行情 API。

## 日用路径（Phase E）

```powershell
# 1) CLI 日流水线（replay / CI，零公网；默认样例宇宙对齐 fixtures）
stock-platform-daily --asof 2026-09-02 --provider replay --fixtures .\packages\providers\tests\fixtures --out $env:TEMP\sp-daily
# 细节与 --skip-refresh 变体：docs/ops/daily-pipeline.md

# 2) Windows 调度（交易日跳过休市）
powershell -NoProfile -File .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2026-09-02
# 安装步骤：docs/ops/scheduler.md

# 3) Workbench 一键向导
python -m stock_platform_workbench
# → http://127.0.0.1:3018/#wizard  （刷新→推荐→纸面；默认 skip refresh）
```

默认 **paper + SIMULATE**；行情默认 live（可用 `STOCK_PLATFORM_PROVIDER_PRESET=replay` 强制 fixtures）。日用宇宙样例见 `docs/ops/daily-universe.md`。

## 快速开始

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\packages\research[dev]"
python -m pip install -e ".\packages\agents[dev]"
python -m pip install -e ".\packages\execution[dev]"
python -m pip install -e ".\apps\workbench[dev]"
Copy-Item .env.example local\.env   # 填写 token / market.db 路径；勿提交
stock-platform-init                 # 空库 seed 可改配置行（不打开实盘）
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"   # 全量 pytest 零公网
python -m pytest packages apps -q
Remove-Item Env:STOCK_PLATFORM_PROVIDER_PRESET   # 生产启动用 live 默认
python -m stock_platform_workbench
# → http://127.0.0.1:3018/  （打开「今日推荐」）
# → http://127.0.0.1:3018/health
# → http://127.0.0.1:3018/api/ops/health
```

本机运行时目录：[`docs/ops/local-runtime.md`](docs/ops/local-runtime.md)。  
Live 运维说明：[`docs/ops/live-startup.md`](docs/ops/live-startup.md)。
日数据刷新（离线 replay fixtures）：

```powershell
stock-platform-refresh --asof 2026-09-02 --universe path\to\universe.json --out $env:TEMP\refresh --provider replay --fixtures path\to\fixtures
```

盘前简报 CLI：

```powershell
stock-platform-brief path\to\panel.csv --asof 2026-09-02 --top 10 -o picks.csv
```

自检：

```powershell
.\scripts\check_docs.ps1
.\scripts\check_versions.ps1
```

## 仓库布局

```text
stock-platform/
├── apps/workbench/
├── packages/{providers,research,agents,execution}/
├── docs/                      # 产品文档 SSOT（不要把正文摊到仓库根）
│   ├── STATUS.md              # 现行快照
│   ├── README.md              # 分类索引
│   ├── ROADMAP.md             # M0–M47（已全部 done）
│   ├── upstream-archive.md
│   ├── release-checklist.md
│   ├── versioning.md
│   ├── architecture/          # ADR
│   ├── contracts/
│   ├── ops/
│   ├── plans/                 # 仍有效的计划
│   ├── archive/               # 已落地的历史交接
│   ├── engineering/           # OpenAPI / 测试 / CI
│   └── upstream/              # 上游配方只读摘要
└── scripts/{check_docs,check_versions,release_tag}.ps1
```

## 里程碑摘要

| Tag | 里程碑 |
|-----|--------|
| v0.1.0–v0.7.0 | M0–M6（架子→数据→工作台→研究→Agent→美港→纸面执行） |
| **v1.0.0** | M7 产品收敛 / 上游归档 |
| v1.1.0–v1.16.0 | M8–M23（live HTTP、日历、UI、辩论、CN 扩展数据集、复权套价） |
| **v2.0.0** | Phase A（M24–M28）日更推荐 + 纸面闭环 |
| **v2.1.0–v2.3.0** | Phase B（M29–M31）日刷新 + live 运维稳定 |
| **v2.4.0–v2.6.0** | Phase C（M32–M34）投研稳定（绩效 / 可选 LLM / 策略对比） |
| **v3.0.0** | Phase D（M35–M38）执行端口 + ths_sim |
| **v3.1.0–v3.8.0** | Phase E 日用稳定 |
| **v3.9.0** | M47 生产 live 行情默认（交易仍 SIMULATE） |
| **v3.9.1** | Workbench UI 渐进披露 + 推荐卡片 |
| **v3.9.2** | Workbench UI 结构化扫读（步骤/键值/状态） |
| **v4.0–v4.1** | 全市场选股、策略深化、实盘立项（不解禁红线） |
| **v4.2–v4.9** | 日调度、绩效闭环、循环自足、健康度与执行台账 |
| **v4.10–v4.11** | 策略采纳闸门、负收益归因 |
| **v4.12–v4.13.7** | 盘后行情台账、简报盘前/盘后、多源 OHLC、体检到期口径 |

M0–M47 细节见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。现行开放项见 [`docs/STATUS.md`](docs/STATUS.md)。

## 上游参考（只读）

见 [`docs/upstream-archive.md`](docs/upstream-archive.md) 与配方摘要 [`docs/upstream/`](docs/upstream/)。新功能只进本仓。

## 许可

待定。合并上游代码前须核对各仓许可证（多为 Apache-2.0 / MIT）。
