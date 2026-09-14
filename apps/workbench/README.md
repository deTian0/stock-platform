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

## 安装与运行

```powershell
cd D:\workspace\git\stock-platform
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\packages\agents[dev]"
python -m pip install -e ".\packages\execution[dev]"
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
| GET | `/api/research/report?symbol=&asof=` | 个股研报槽（agents） |
| GET | `/api/review/report?symbol=&asof=` | 复盘槽（agents） |
| GET | `/api/paper/status` | 纸面状态（SIMULATE · 实盘关闭） |
| POST | `/api/paper/strategies/draft\|validate\|activate` | 草稿 / 校验 / 显式激活 |
| POST | `/api/paper/drafts` | 建纸面订单草稿 |
| POST | `/api/paper/drafts/{id}/execute` | 提交（幂等） |
| PUT | `/api/settings/preferences` | 更新能力→Provider 偏好（不绕过 usable） |

## 约束

- 路由**禁止**写死数据源品牌；只调用 `WorkbenchState.resolve(capability)`
- 遵循 `docs/contracts/`
- 默认 Provider 为 `replay`（fixtures），非 TickFlow
