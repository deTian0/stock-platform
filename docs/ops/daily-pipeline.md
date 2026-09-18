# 日流水线：refresh → brief

> Phase E / M40 · ADR [0041](../architecture/0041-daily-pipeline.md)  
> U4：日用可显式接 live（`tushare`）；**默认仍 replay** 保 CI 零公网。

## 手跑（replay / CI，零公网）

默认宇宙 `universe_cn_sample.json`（`600519` / `000001` / `510300`）已与
`packages/providers/tests/fixtures` 的 `daily_*`（≥60 根）对齐；JSON 请用 **UTF-8 无 BOM**。

```powershell
cd D:\workspace\git\stock-platform
python -m pip install -e .\packages\providers -e .\packages\research

# 推荐：默认宇宙 + refresh + brief（产物含非空 picks）
stock-platform-daily --asof 2026-09-02 --provider replay --fixtures .\packages\providers\tests\fixtures --out $env:TEMP\sp-daily

# 仅 brief（跳过 refresh 落盘）
stock-platform-daily --asof 2026-09-02 --provider replay --fixtures .\packages\providers\tests\fixtures --out $env:TEMP\sp-daily --skip-refresh
```

显式指定样例宇宙（与默认相同）：

```powershell
stock-platform-daily --asof 2026-09-02 --provider replay --fixtures .\packages\providers\tests\fixtures --out $env:TEMP\sp-daily --universe .\packages\research\src\stock_platform_research\fixtures\universe_cn_sample.json
```

调度包装（交易日才跑；默认仍 replay）：

```powershell
powershell -NoProfile -File .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2026-09-02
```

成功时 stdout 含 `"ok": true`，且 `{out}/briefs/2026-09-02/brief.json` 的 `picks` 至少 1 条。

## 真实日用（live / Tushare）

**不要**把默认改成 live（会破坏裸跑零公网）。日用请显式指定 provider，并用本地 `.env` 配 token（勿提交）：

```powershell
# 本机 .env 或会话环境：
# $env:STOCK_PLATFORM_TUSHARE_TOKEN = "你的token"   # 勿提交 git
# 可选：$env:STOCK_PLATFORM_DAILY_PROVIDER = "tushare"
# 可选：$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:\workspace\git\a-stock-engine\data_cache\market.db"

# 一键日用（推荐）：tushare + 跳过 refresh + SQLite 落库 + 记入/结算绩效
powershell -NoProfile -File .\scripts\ops\Invoke-DailyPipeline.ps1 -LiveDay -Asof 2026-09-12

# 等价拆开写：
powershell -NoProfile -File .\scripts\ops\Invoke-DailyPipeline.ps1 `
  -Asof 2026-09-12 -Provider tushare -SkipRefresh -SettleAfter

# 等价 CLI：
stock-platform-daily --asof 2026-09-12 --provider tushare --skip-refresh --settle-after --out $env:TEMP\sp-daily-live
```

| 项 | 约定 |
|----|------|
| `-LiveDay` | 一键：`Provider=tushare`（若未指定）+ `SkipRefresh` + `SettleAfter`；**不**改变无参时的 replay 默认 |
| `-SettleAfter` / `--settle-after` | brief 成功后记入绩效 JSONL，并用日线结算可结算样本（优先 engine market.db） |
| 别名 | `tushare` / `tushare_http` / `cn_tushare_http` |
| 缺 token | **非 0 退出**，可读错误；**不**自动降级 fixtures |
| 环境变量 | `STOCK_PLATFORM_DAILY_PROVIDER`（脚本/CLI 默认 provider，未传参时） |
| 权威存档 | 与 Workbench 共用 SQLite（`STOCK_PLATFORM_DB_URL`） |

手工验收清单（不写真实 token）：

1. 未设 token 时 `-Provider tushare` / `-LiveDay` 应失败退出。  
2. 设好 token 后 `-LiveDay` 能写出 brief、upsert DB，并在 stdout 见 `settleAfter`。  
3. 非交易日脚本仍 exit 0。

## 产物

| 路径 | 说明 |
|------|------|
| `{out}/{asof}/` | refresh 落盘（manifest / dataset_symbol.json） |
| `{out}/briefs/{asof}/brief.json` | 当日简报（可选 JSON 导出） |
| `{out}/briefs/{asof}/panel.csv` | 截面面板 |
| `{out}/briefs/{asof}/failure.json` | 失败报告（若失败） |
| `{out}/briefs/latest.json` | 最近一次运行指针 |
| `STOCK_PLATFORM_DB_URL` SQLite | **权威存档**（U2）：与 Workbench 共用 `SqliteBriefRepository`；默认 `sqlite:///./data/stock_platform.db`（见 ADR 0049） |

同日重复跑会对同一 `asof` **幂等覆盖** DB 行与 JSON 导出。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 流水线失败（refresh 或 brief） |
| 2 | 参数错误（如 replay 缺 `--fixtures`） |

## 调度入口

Windows Task Scheduler / cron 包装：[`scheduler.md`](scheduler.md)
（`scripts/ops/Invoke-DailyPipeline.ps1` + XML / cron 样例；非交易日 exit 0）。
默认仍 **paper + replay + SIMULATE**；日用任务请用 `-Provider tushare`。
