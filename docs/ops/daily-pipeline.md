# 日流水线：refresh → brief

> Phase E / M40 · ADR [0041](../architecture/0041-daily-pipeline.md)

## 手跑（replay / CI）

```powershell
cd D:\workspace\git\stock-platform
python -m pip install -e .\packages\providers -e .\packages\research
stock-platform-daily --asof 2026-09-02 --provider replay --fixtures .\packages\providers\tests\fixtures --out $env:TEMP\sp-daily --skip-refresh
```

完整含 refresh 落盘（仍 replay）：

```powershell
stock-platform-daily --asof 2026-09-02 --provider replay --fixtures .\packages\providers\tests\fixtures --out $env:TEMP\sp-daily --universe .\packages\research\src\stock_platform_research\fixtures\universe_cn_sample.json
```

## 产物

| 路径 | 说明 |
|------|------|
| `{out}/{asof}/` | refresh 落盘（manifest / dataset_symbol.json） |
| `{out}/briefs/{asof}/brief.json` | 当日简报 |
| `{out}/briefs/{asof}/panel.csv` | 截面面板 |
| `{out}/briefs/{asof}/failure.json` | 失败报告（若失败） |
| `{out}/briefs/latest.json` | 最近一次运行指针 |

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 流水线失败（refresh 或 brief） |
| 2 | 参数错误（如 replay 缺 `--fixtures`） |

## 调度入口

Windows Task Scheduler / cron 包装：[`scheduler.md`](scheduler.md)
（`scripts/ops/Invoke-DailyPipeline.ps1` + XML / cron 样例；非交易日 exit 0）。
默认仍 **paper + replay + SIMULATE**。
