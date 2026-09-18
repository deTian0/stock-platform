# Workbench 生产 live 启动（行情真实 / 交易纸面）

> M47 / v3.9.0：默认行情偏好为 **CN `astock_http`（经 `em_get`）**。  
> **交易仍为 SIMULATE / paper**，不会开启 `liveTradingEnabled` 或真实券商。

## 用仓库 `.venv` 启动

```powershell
cd D:\workspace\git\stock-platform
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\packages\research[dev]"
python -m pip install -e ".\packages\agents[dev]"
python -m pip install -e ".\packages\execution[dev]"
python -m pip install -e ".\apps\workbench[dev]"
python -m stock_platform_workbench
# → http://127.0.0.1:3018/
# → http://127.0.0.1:3018/api/ops/health   （defaultReplay 应为 false）
```

可选环境变量（见仓库根 `.env.example`）：

| 变量 | 含义 |
|------|------|
| （不设） | 启动偏好 = `cn_astock_http`（全 CN 能力走 live） |
| `STOCK_PLATFORM_PROVIDER_PRESET=replay` | 强制 fixtures，**CI/pytest 用** |
| `STOCK_PLATFORM_PROVIDER_PRESET=us_hk_global_http` | 美港 daily/realtime → `global_http` |
| `STOCK_PLATFORM_PROVIDER_PRESET=cn_tushare_http` | CN daily → `tushare_http`；其余 CN 仍 `astock_http` |
| `STOCK_PLATFORM_TUSHARE_URL` | Tushare 兼容基址（默认 `https://t.xiaodefa.top/`） |
| `STOCK_PLATFORM_TUSHARE_TOKEN` | Tushare token（**仅本地/密钥库**；勿提交 git） |
| `EM_MIN_INTERVAL` | 东财节流间隔（默认 1.0s） |
| `EM_HTTP_RETRIES` / `EM_HTTP_RETRY_BACKOFF` | 连接中断重试次数（默认 3）与退避基数（默认 0.5s） |
| `EM_CIRCUIT_FAILURES` / `EM_CIRCUIT_COOLDOWN` | 熔断阈值与冷却 |
| `STOCK_PLATFORM_HTTP_TRUST_ENV` | 默认 `0`（忽略坏系统代理）；需代理时设 `1` |

美港：矩阵一次只能选一个 daily provider。生产默认 CN；切美港：

```powershell
# UI「偏好预设」选 us_hk_global_http，或：
Invoke-RestMethod -Method Post http://127.0.0.1:3018/api/settings/presets/us_hk_global_http/apply
```

Tushare 日 K 补充（不改生产默认；**勿把 token 写入仓库**）：

```powershell
$env:STOCK_PLATFORM_TUSHARE_TOKEN = "<your token>"
# 可选：$env:STOCK_PLATFORM_TUSHARE_URL = "https://t.xiaodefa.top/"
Invoke-RestMethod -Method Post http://127.0.0.1:3018/api/settings/presets/cn_tushare_http/apply
```

## 上游失败（fail-closed）

| 情况 | HTTP |
|------|------|
| 能力不可用 / 偏好无效 | 409 |
| 标的非法 | 400 |
| 东财熔断 `CircuitOpenError` | 503 |
| `requests` 上游错误 | 502 |
| 向导 brief 连接中断且重试耗尽 | **503** + 中文 tip（可设 `STOCK_PLATFORM_PROVIDER_PRESET=replay` 离线；**不**静默换 fixtures） |
| 超时 | 504 |
| 有效 provider 缺方法 | 501（不返回假空 rows） |

**不会**在 live 偏好下静默回退到 fixtures。

## 日用最小步骤（商用可用最短路径）

对应计划 DoD：`.cursor/plans/usable-recommend-review-milestones.md`。

1. 复制 `.env.example` → `.env`，填入 `STOCK_PLATFORM_TUSHARE_TOKEN`（勿提交）。  
2. 建议：`STOCK_PLATFORM_PROVIDER_PRESET=cn_tushare_http`（或 UI「偏好预设」切到同名）。  
3. `.\start-workbench.bat` 或 `python -m stock_platform_workbench` → 打开 `#recommend`。  
4. 点「生成今日推荐」→ 自动落库 + 记入绩效 pending；下方「历史推荐」可「回看 / 复盘」。  
5. `#performance` 刷新可见样本；有后续行情时自动结算 pending（可配 `STOCK_PLATFORM_ENGINE_MARKET_DB` 用引擎本地日线，见 [`engine-market-db.md`](engine-market-db.md)）。  
6. `/api/ops/health` 核对 `providerPreset` / `supplementTokenConfigured` / `briefFallback`（仅布尔，无 token 明文）。  
7. **不要**设 `STOCK_PLATFORM_BRIEF_FALLBACK=replay` 冒充 live。

日批 live：见 [`daily-pipeline.md`](daily-pipeline.md)「真实日用」；默认可仍 replay。

## CI / 测试强制 replay

```powershell
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
python -m pytest apps\workbench -q
```

GitHub Actions `workbench` job 已设置同名环境变量。Workbench 测试 fixture 也会 `monkeypatch` 该变量。
