# apps/workbench

量化研究工作台（规划吸收 tick-stock-panel）。安装名：`stock-platform-workbench`。

## 状态

| 版本 | 能力 |
|------|------|
| M2.1 / v0.2.1 | 最小 FastAPI 壳：health / 矩阵 / daily / realtime |
| **M2.2 / v0.2.2** | preferences、缺能力 409、禁品牌硬编码 |
| **M2.3 / v0.2.3** | API 与 ReplayProvider 同标的同日口径对齐 |
| **M4.2 / v0.4.2** | `/api/research/report`、`/api/review/report`（经 agents 插件） |
| **M6.3 / v0.6.3** | `/api/paper/*` 纸面执行（SIMULATE only） |
| **M11 / v1.3.1+** | `GET /` 最小 UI（矩阵 / 日 K / 纸面） |
| **M18.2 / v1.10.2** | `GET /api/market/minute` + UI；默认 replay |
| **M19.2 / v1.11.2** | `GET /api/market/depth5` + UI；默认 replay |
| **M20.2 / v1.12.2** | `GET /api/market/financial` + UI；默认 replay |
| **M21.2 / v1.13.2** | `GET /api/market/adj-factor` + UI；默认 replay |
| **M22.2 / v1.14.2** | `GET /api/market/full-minute` + UI；默认 replay |
| **M23.2 / v1.15.2** | `GET /api/market/daily-adjusted` + UI；默认 replay |
| **M25 / v1.18.0** | `GET /api/research/brief` 盘前简报 |
| **M26 / v1.19.0** | UI「今日推荐」`#recommend` |
| **M27 / v1.20.0** | `POST /api/research/brief/to-paper` → PaperLedger |
| **M30 / v2.2.0** | live 预设 `GET/POST /api/settings/presets*` |
| **M31 / v2.3.0** | `GET /api/ops/health` |
| **M32 / v2.4.0** | `GET /api/research/performance` + `#performance` |
| **M33 / v2.5.0** | `engine=llm` 可选辩论 + `POST /api/research/brief/debate` |
| **M34 / v2.6.0** | `GET/POST /api/research/strategy/*` + `#strategy-compare` |
| **M47 / v3.9.0** | **生产默认 CN live**（`astock_http`）；CI 用 `STOCK_PLATFORM_PROVIDER_PRESET=replay` |
| **v3.9.1** | Workbench UI 日用抛光：主流程置顶、推荐卡片、次级折叠（ADR 0047） |
| **v3.9.2** | Workbench UI 结构化扫读：向导步骤 / 运维键值 / 矩阵 pill / 绩效条 |
| **v3.9.3** | Workbench 行情查询结果可读性（表/卡片/万亿/五档着色） |
| **v3.9.4** | 向导/一键纸面自动激活默认 SIMULATE 策略（幂等；状态文案） |
| **v3.10.0** | Tushare 补充日 K + 东财瞬时断连重试 / 向导 503 tip（ADR 0048） |

## 安装与运行

```powershell
cd D:\workspace\git\stock-platform
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\packages\research[dev]"
python -m pip install -e ".\packages\agents[dev]"
python -m pip install -e ".\packages\execution[dev]"
python -m pip install -e ".\apps\workbench[dev]"
cd apps\workbench
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
python -m pytest -q
Remove-Item Env:STOCK_PLATFORM_PROVIDER_PRESET
python -m stock_platform_workbench
# → http://127.0.0.1:3018/  （UI；行情默认 live）
# → http://127.0.0.1:3018/health
# → http://127.0.0.1:3018/api/ops/health
```

生产 live 说明：[`docs/ops/live-startup.md`](../../docs/ops/live-startup.md)。

## API（当前）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 最小操作台 UI |
| GET | `/health` | 存活探针 |
| GET | `/api/ops/health` | 运维快照（默认 replay / 熔断 / lastRefresh） |
| GET | `/api/settings/capability-matrix` | 能力矩阵（含 adj_factor / minute / depth5 / financial / fund_flow / lhb / unlock） |
| GET | `/api/market/daily?symbols=` | 经矩阵 resolve(`daily`) |
| GET | `/api/market/realtime?symbols=` | 经矩阵 resolve(`realtime`) |
| GET | `/api/market/adj-factor?symbols=&kind=` | 经矩阵 resolve(`adj_factor`)；无候选仍 **409** |
| GET | `/api/market/daily-adjusted?symbols=&kind=` | `resolve(daily)` + `resolve(adj_factor)` 后 `apply_adjust`；空因子 **400** |
| GET | `/api/market/minute?symbols=&freq=` | 经矩阵 resolve(`minute`)；无候选仍 **409** |
| GET | `/api/market/depth5?symbols=` | 经矩阵 resolve(`depth5`)；无候选仍 **409** |
| GET | `/api/market/financial?symbols=&periods=` | 经矩阵 resolve(`financial`)；无候选仍 **409** |
| GET | `/api/market/fund-flow?symbols=` | 经矩阵 resolve(`fund_flow`) |
| GET | `/api/market/lhb?symbols=&asof_date=` | 经矩阵 resolve(`lhb`) |
| GET | `/api/market/unlock?symbols=&asof_date=` | 经矩阵 resolve(`unlock`) |
| GET | `/api/research/brief?asof=&symbols=&topN=` | 盘前 TopN 简报（矩阵 daily；生产默认 live） |
| POST | `/api/research/brief/to-paper` | TopN → 纸面草稿（SIMULATE；无激活时自动 ensure 默认策略） |
| GET | `/api/research/report?symbol=&asof=` | 个股研报槽（agents） |
| GET | `/api/review/report?symbol=&asof=` | 复盘槽（agents） |
| GET | `/api/debate/report?symbol=&asof=` | 确定性 Bull/Bear/Risk 辩论 |
| GET | `/api/paper/status` | 纸面状态（SIMULATE · 实盘关闭） |
| POST | `/api/paper/strategies/draft\|validate\|activate` | 草稿 / 校验 / 显式激活 |
| POST | `/api/paper/strategies/ensure-default` | 幂等：无激活时创建并激活默认 SIMULATE 策略 |
| POST | `/api/paper/drafts` | 建纸面订单草稿 |
| POST | `/api/paper/drafts/{id}/execute` | 提交（幂等） |
| PUT | `/api/settings/preferences` | 更新能力→Provider 偏好（不绕过 usable） |
| GET | `/api/settings/presets` | 列出 replay / cn_astock_http / cn_tushare_http / us_hk_global_http（启动默认 cn live） |
| POST | `/api/settings/presets/{id}/apply` | 应用到当前进程 |

## 约束

- 路由**禁止**写死数据源品牌；只调用 `WorkbenchState.resolve(capability)`
- 遵循 `docs/contracts/`
- 生产默认 Provider 为 `astock_http`（CN）；CI 设 `STOCK_PLATFORM_PROVIDER_PRESET=replay`
- 交易永远 SIMULATE；「真实」仅指行情
