# OpenAPI、测试分层与 CI

> 与 [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) 对齐；本文便于在 `docs/` 内导航，不另立第二套命令口径。

## OpenAPI（Workbench）

启动 Workbench 后：

| 路径 | 用途 |
|------|------|
| `http://127.0.0.1:3018/docs` | Swagger UI |
| `http://127.0.0.1:3018/redoc` | ReDoc |
| `http://127.0.0.1:3018/openapi.json` | OpenAPI JSON |

契约测：`apps/workbench/tests/test_openapi_contract.py`（路径存在 + 成功响应 schema 非空 object）。

全量 endpoint smoke：`apps/workbench/tests/test_all_api_endpoints.py`（OpenAPI 每个 path+method 至少一击 + 目录与 openapi 对齐门禁；`STOCK_PLATFORM_PROVIDER_PRESET=replay`）。

## 测试分层

`apps/workbench` 注册 markers：

| Marker | 含义 | 示例 |
|--------|------|------|
| `unit` | 快测：OpenAPI、纯函数/静态 UI | `pytest -m unit` |
| `integration` | 跨路由：wizard / brief→paper→broker | `pytest -m integration` |

全仓零公网：

```powershell
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
python -m pytest packages apps -q
```

仅分层：

```powershell
cd apps\workbench
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
python -m pytest -m unit -q
python -m pytest -m integration -q
```

## CI

`.github/workflows/ci.yml`：

- `monorepo` job：`pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）
- 各包 matrix 与 `workbench` job（含 OpenAPI 契约测）仍保留

本地合并前另跑：

```powershell
.\scripts\check_docs.ps1
.\scripts\check_versions.ps1
```
