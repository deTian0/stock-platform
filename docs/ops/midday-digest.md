# 午间 midday 手跑（ADR 0096）

> **状态**：已落地；**不**注册 schtask。  
> **操作员清单**（WorkBuddy / 人）：[`workbuddy-runbook.md`](workbuddy-runbook.md) §2。  
> **计划细节**：[`../plans/midday-session.md`](../plans/midday-session.md) §1.1。

## 何时

CN **交易日约 11:30**（午间休盘）。用户或 WorkBuddy 提醒后手跑；仓库 `Register-ScheduledTasks.ps1` / XML **不含** midday。

## 命令

```powershell
cd <repo-root>
$day = Get-Date -Format "yyyy-MM-dd"
stock-platform-digest --session midday --run-date $day
```

必须显式 `--run-date`（报告日）；禁止用 `date.today()` 在代码里猜。可选：`--asof`、`--out-dir`、`--no-ths`、`--no-html`。

## 产物

| 路径 | 说明 |
|------|------|
| `{out}/{reportDay}-midday.md` / `.html` | 午间正文（默认落 `local/digests/` 或本机 digest 目录） |
| `latest-midday.*` | 最近一次 midday 指针 |
| `{reportDay}.md` / `latest.md` | 「最后一次成功渲染」别名（可能被 midday 覆盖） |

**不删除**同日 `-pre` / `-post`。现价经 `em_get` 取当日分钟线最后一根，仅候选池；失败三列 `—`，digest 仍成功。

## 交叉链

- 调度说明（明确不装 midday）：[`scheduler.md`](scheduler.md)  
- 日流水线（流水线不含 midday）：[`daily-pipeline.md`](daily-pipeline.md)  
- ADR [`0096`](../architecture/0096-midday-digest-session.md)
