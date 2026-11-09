# 0097 — 持仓单一真源（`local/holdings.json`）与盘后收口

- **状态**：Accepted
- **日期**：2026-11-09
- **相关**：ADR [`0079`](0079-settle-after-on-premarket.md) · [`0093`](0093-multi-strategy-shadow-board.md) · 运维 [`../ops/local-runtime.md`](../ops/local-runtime.md) · [`../ops/scheduler.md`](../ops/scheduler.md)

---

## 背景

运行时目录在 `v4.12` 前后迁到 `local/`（[`../ops/local-runtime.md`](../ops/local-runtime.md)），但 `scripts/ops/Invoke-DailyPipeline.ps1` 给 ③A / ③B 找持仓文件时仍默认 `data\holdings.json` —— 那是迁移前的残留，最后人工编辑停在 **2026-10-28**。

2026-11-09 盘前实测后果（真账本 `local/holdings.json` = asof 2026-11-05）：

| 项 | 陈旧 `data/`（被读） | 真账本 `local/` |
|---|---|---|
| 000533 数量 | 1100 股 | **500 股**（10-29～11-04 已卖 600 股） |
| 000533 成本 | 9.977 | **11.456**（券商摊薄成本） |
| 588080 数量 | 800 股 | **100 股** |

于是 ③B 在 11-09 给出「**减仓 900 股**」，而可卖只有 500 股（不可执行）；按真实成本 11-06 收盘 9.61 计算为 **−16.1%**，早已击穿 −8% 硬止损，正确动作应是 exit 全 500 股 —— 陈旧成本（−3.68%）把止损掩盖成了「按权重 trim」。③A 的权重（91.04% vs 97.38%）与持有天数（20 vs 26）同源偏差。

第二条同时暴露：影子前向账本（ADR 0093）要求 `--settle-daily` 才结算，但该命令不在任何调度预设里。2026-11-03～11-06 共 8 条席位全部 `pending`，「攒满 `MIN_MEANINGFUL_SAMPLE`」的路线图下一步实际停摆；`local/health/` 也停在 11-06，无自动重算。

## 决策

1. **单一真源**：③A / ③B 的持仓只从 `local/holdings.json` 读（`STOCK_PLATFORM_HOLDINGS_PATH` / `-Holdings` 显式覆盖仍优先）。`Invoke-DailyPipeline.ps1` 的默认值改为 `local\holdings.json`。
2. **不做 legacy 回落**：`data\holdings.json` 不再作为兜底。文件缺失时 ③A / ③B 保持空（fail-closed），并打印明确提示。静默回落到过期账本比空榜更危险 —— 空榜是「没有数据」，错榜是「错误指令」。
3. **残留归档**：本机 `data/holdings.json` 已移至 `local/backup/holdings-legacy-2026-10-28.json`（保留取证，不入库）。
4. **盘后收口并入 18:30 回补**：`Invoke-MarketDbBackfill.ps1` 在 `-Mode apply` **成功**后追加两步，均 best-effort、**不改变回补退出码**：
   - `stock-platform-loop-health --on-ok summary` → 用刚补齐的库重算 `local/health/`（含 `dataQuality`）；
   - `stock-platform-shadow-board --settle-daily` → 用当日收盘结算 pending 席位（`local/shadow/shadow_decisions.jsonl`）。
   选 18:30 而不是 15:30：盘后流水线仍看 T-1，当日 bar 要等引擎回补才进库；结算和体检都依赖它。`-SkipPlatformPost` 可只跑引擎回补（排障用）。
5. **契约钉住**：`test_scheduler_args_contract.py` 增加断言 —— 流水线默认持仓路径必须是 `local`、不得再出现 `data\holdings.json` 默认值；回补脚本必须携带两个 post 步骤与 `-SkipPlatformPost`。调度提示词（WorkBuddy 自动化）同步改为 `local/` 路径。

## 非目标

改 ③B 的退出规则 / 仓位算法；改影子库默认或学校启用表；把 settle 挪进 15:30 流水线；打开 live；自动改 `local/holdings.json` 内容（仍由人工按券商截图维护）。

## 后果

**正面**：③A / ③B 的数量、成本、权重、止损判定重新与真实账本一致；影子前向样本开始自动累积；`local/health/` 每日随回补刷新。  
**代价**：`local/holdings.json` 成为**必须**人工维护的文件 —— 不更新就会让 ③B 用旧快照（现在至少是可解释的旧账本，而不是另一份过期文件）；18:30 任务时长增加约 10～20 s。
