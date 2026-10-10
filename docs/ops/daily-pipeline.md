# 日流水线：refresh → brief

> Phase E / M40 · ADR [0041](../architecture/0041-daily-pipeline.md)  
> U4：日用可显式接 live（`tushare`）；**默认仍 replay** 保 CI 零公网。

## 手跑（replay / CI，零公网）

默认宇宙 `universe_cn_sample.json`（`600519` / `000001` / `510300`）已与
`packages/providers/tests/fixtures` 的 `daily_*`（≥60 根）对齐；JSON 请用 **UTF-8 无 BOM**。

```powershell
cd D:\workspace\stock_trading\stock-platform
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
# 可选：$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:\workspace\stock_trading\a-stock-engine\data_cache\market.db"

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

## X4：picks 账本与「推荐 ↔ 回测」对照

流水线每次成功会在 `{out}/picks_ledger.jsonl` **追加**当日 ②A 头部（append-only，按 `(date, code)` 去重；
同 `asof` 重跑不重复计数）。这是「每日 picks 自动进回测对照」的进料口，默认开启，
`track_picks_ledger=False` 可关。

要真正跑出对照，需再给一段**行情 DataFrame**（brief 自身没有前向窗口）：

```powershell
# CLI 方式（只读 market.db；--ledger 或 --briefs-dir 二选一）
stock-platform-picks-backtest --ledger $env:TEMP\sp-daily\picks_ledger.jsonl `
  --db D:\workspace\stock_trading\a-stock-engine\data_cache\market.db `
  --start 2026-01-01 --end 2026-10-09

# 与 lvrev 选股回测并排看（同一堆 bars，delta = picks 指标 − 回测指标）
stock-platform-picks-backtest --briefs-dir $env:TEMP\sp-daily\briefs --compare `
  --db D:\workspace\stock_trading\a-stock-engine\data_cache\market.db
```

代码侧：`run_daily_pipeline(..., replay_picks=True, replay_bars=<DataFrame>)` 会回放**累计账本**并写
`{out}/briefs/{asof}/picks_replay.json`；再加 `replay_against_screener=True` 则返回选股侧与 `delta`
（此时 `replay_kwargs` 形状为 `{"picks_kwargs": {...}, "screener_kwargs": {...}}`）。
两个阶段都是 **best-effort**：失败只落 `report.picksReplay["error"]`，**不中断** brief。

| 产物 | 说明 |
|------|------|
| `{out}/picks_ledger.jsonl` | 推荐账本（append-only，`(date, code)` 去重） |
| `{out}/briefs/{asof}/picks_replay.json` | 完整回放/对照载荷（含净值曲线与成交明细） |
| `report.picksReplay` | **裁剪摘要**（去 `equity_curve` / `trades`，加 `tradeCount` / `curvePoints`），避免撑爆 `manifest.json` |

口径与规则见契约 [`docs/contracts/picks-backtest.md`](../contracts/picks-backtest.md) 与
ADR [0059](../architecture/0059-picks-backtest-parity.md)：推荐侧与回测侧共用
`book_replay.replay_book` 一台引擎（同 `rules.evaluate_exit` / 同 `CostModel` / 同 `compute_metrics`）。
推荐侧默认 `universe=all`（推荐了 ETF 就按 ETF 回放），对照的选股侧保留 `stock` 基线 —— 差异在
`params.universe` 双侧回显，**不隐藏**。

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
