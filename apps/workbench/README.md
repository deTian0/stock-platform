# apps/workbench

量化研究工作台（规划吸收 tick-stock-panel）。安装名：`stock-platform-workbench`。

## 状态

| 版本 | 能力 |
|------|------|
| **M2.1 / v0.2.1** | 最小 FastAPI 壳：`/health`、能力矩阵、daily/realtime；minute fail-closed |

## 安装与运行

```powershell
cd D:\workspace\git\stock-platform
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\apps\workbench[dev]"
cd apps\workbench
python -m pytest -q
python -m stock_platform_workbench
# → http://127.0.0.1:3018/health
```

## API（当前）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/settings/capability-matrix` | 七项能力矩阵 |
| GET | `/api/market/daily?symbols=` | 经矩阵 resolve(`daily`) |
| GET | `/api/market/realtime?symbols=` | 经矩阵 resolve(`realtime`) |
| GET | `/api/market/minute?symbols=` | 无候选时 **409** fail-closed |

## 约束

- 路由**禁止**写死数据源品牌；只调用 `WorkbenchState.resolve(capability)`
- 遵循 `docs/contracts/`
- 默认 Provider 为 `replay`（fixtures），非 TickFlow
