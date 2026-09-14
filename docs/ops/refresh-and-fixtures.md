# 日刷新与 fixture 录制

> 运维文档（M29/M31）。CI **禁止**打公网；默认 runtime 仍是 replay。

## 刷新流水线

本地 / 定时任务（PowerShell 示例）：

```powershell
$env:STOCK_PLATFORM_REFRESH_DIR = "D:\data\stock-platform-refresh"
# 可选：live 刷新时加大东财间隔（默认 1.0s）
$env:EM_MIN_INTERVAL = "1.5"

stock-platform-refresh `
  --asof 2026-09-14 `
  --universe path\to\universe_cn.json `
  --out $env:STOCK_PLATFORM_REFRESH_DIR `
  --datasets daily,adj_factor,fund_flow,full_minute `
  --provider replay `
  --fixtures path\to\fixtures `
  --max-attempts 3
```

- 退出码 `0`：全部 (symbol, dataset) 成功；非 0：有失败（stderr 逐条打印）。
- 产物：`{out}/{asof}/daily_{symbol}.json` 等 + `manifest.json`；`{out}/latest.json`。
- 文件名对齐 `ReplayTransport`，可将 `{out}/{asof}` 当作 fixtures 目录。

**Live 刷新（opt-in，非 CI）**：自行用 Python 构造 `AStockHttpProvider()` 调用
`run_refresh(..., provider=http_provider)`。Workbench 默认不会这么做。东财必须走 `em_get`。

## Fixture 录制（给 CI）

1. 用上面的 refresh 在**有网机器**落盘（或手工保存 vendor JSON）。
2. 只把**脱敏、小样本** JSON 拷进 `apps/workbench/tests/fixtures/` 或 providers 测试 fixtures。
3. 单测注入 `ReplayProvider` / 假 provider；GitHub Actions 不设公网、不设 live provider。
4. 不要提交 SQLite 全市场库或密钥。

## 健康检查

```powershell
# 存活
Invoke-RestMethod http://127.0.0.1:3018/health

# 运维快照（节流/熔断/最近刷新）
Invoke-RestMethod http://127.0.0.1:3018/api/ops/health
```

`liveTradingEnabled` 恒为 `false`。`defaultReplay=true` 表示当前进程未应用 live 预设。
