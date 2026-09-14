# ADR 0041：定时 refresh→brief 日流水线

- 状态：Accepted
- 日期：2026-09-14

## 背景

日用推荐不能只靠人手敲 `stock-platform-refresh` 再敲 brief。需要一条可调度、
幂等、失败可见的 refresh→brief 流水线；CI 仍零公网（replay）。

## 决策

1. **内核**：`run_daily_pipeline` — 可选 `run_refresh` → 截面面板 → `build_premarket_brief`。
2. **产物**：`{out}/briefs/{asof}/brief.json|csv|panel.csv|manifest.json`；
   `{out}/briefs/latest.json`。同 asof 重跑覆盖。
3. **失败**：fail-closed；写 `failure.json` + `latest.ok=false`；退出码非 0。
4. **CLI**：`stock-platform-daily`（`--provider replay` + `--fixtures` 为 CI 默认）。
5. **调度**：本机手跑文档在 `docs/ops/daily-pipeline.md`；Task Scheduler / cron
   运维包见 M42（`docs/ops/scheduler.md`，ADR 0044）。
6. **不做**：默认 live、后台守护进程、SPA、真实券商。

## 后果

- M42 运维包直接调度本 CLI（非交易日由包装脚本 skip）。
- 与 ADR 0030 refresh 产物目录兼容（共享 `out` 根）。
