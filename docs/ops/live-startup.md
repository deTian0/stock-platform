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
| `EM_MIN_INTERVAL` | 东财节流间隔（默认 1.0s） |
| `EM_CIRCUIT_FAILURES` / `EM_CIRCUIT_COOLDOWN` | 熔断阈值与冷却 |
| `STOCK_PLATFORM_HTTP_TRUST_ENV` | 默认 `0`（忽略坏系统代理）；需代理时设 `1` |

美港：矩阵一次只能选一个 daily provider。生产默认 CN；切美港：

```powershell
# UI「偏好预设」选 us_hk_global_http，或：
Invoke-RestMethod -Method Post http://127.0.0.1:3018/api/settings/presets/us_hk_global_http/apply
```

## 上游失败（fail-closed）

| 情况 | HTTP |
|------|------|
| 能力不可用 / 偏好无效 | 409 |
| 标的非法 | 400 |
| 东财熔断 `CircuitOpenError` | 503 |
| `requests` 上游错误 | 502 |
| 超时 | 504 |
| 有效 provider 缺方法 | 501（不返回假空 rows） |

**不会**在 live 偏好下静默回退到 fixtures。

## CI / 测试强制 replay

```powershell
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
python -m pytest apps\workbench -q
```

GitHub Actions `workbench` job 已设置同名环境变量。Workbench 测试 fixture 也会 `monkeypatch` 该变量。
