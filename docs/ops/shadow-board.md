# 影子终榜与前向日结（`-ShadowBoard`）

> **状态**：ADR [`0093`](../architecture/0093-multi-strategy-shadow-board.md)；库 / CLI **出厂默认关**；生产盘前/盘后调度自 2026-11-05 起已加 `-ShadowBoard`。  
> **操作员清单**：[`workbuddy-runbook.md`](workbuddy-runbook.md) §5。  
> **红线**：只写 `local/shadow/`；不改出厂 lvrev；不混入主绩效 JSONL；Y2 须 `adopt` 签核。

## 何时

| 动作 | 时机 |
|------|------|
| 日循环写终榜 + pending | 盘前 08:30 / 盘后 15:30（调度已带 `-ShadowBoard`） |
| `--settle-daily` | 盘后或定期；结算 pending，攒前向样本 |
| `--perf-summary` | 随时只读摘要 |

目标：前向账本攒满 `MIN_MEANINGFUL_SAMPLE` 再下结论；Y2 仍等 `adopt`。

## 命令

```powershell
cd <repo-root>
# 生产等价手跑（盘后示例）
.\scripts\ops\Invoke-DailyPipeline.ps1 -MarketDb -PrevSession -SettleAfter -Digest -ShadowBoard -Session post

# 影子前向日结 + 摘要
stock-platform-shadow-board --settle-daily
stock-platform-shadow-board --perf-summary
```

单次关闭影子链：`-NoShadowBoard`（显式关优先）。回滚生产：从 XML / `TASK_PRESETS` 移除 `-ShadowBoard`（无需改代码）。

## 产物

| 路径 | 说明 |
|------|------|
| `local/shadow/final_board_{asof}.json` | 当日终榜 |
| `local/shadow/shadow_decisions.jsonl` | 前向账本（A/B 双轨） |
| `local/shadow/s2_snapshots/` | S2 日快照（影子链开启时） |

`STOCK_PLATFORM_SHADOW_DIR` 可覆盖根目录。

## 失败怎么看

- 影子异常 → 主链 brief 仍应成功；看 `DailyPipelineReport.shadowBoard` / `loop_health.shadowBoard`（最多 warn）  
- 账本无新 pending → 当日空榜或未开 `-ShadowBoard`  
- settle 无进展 → 查 `market.db` 覆盖与持有窗口（T+1 未到不结算）

## 交叉链

- 调度：[`scheduler.md`](scheduler.md)  
- 契约：[`../contracts/multi-strategy-shadow.md`](../contracts/multi-strategy-shadow.md)  
- 计划：[`../plans/multi-strategy-final-board.md`](../plans/multi-strategy-final-board.md)  
- CLI：[`cli-catalog.md`](cli-catalog.md)
