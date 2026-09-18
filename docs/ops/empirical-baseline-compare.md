# Empirical 基线对照手册（M-R3）

> **状态**：done（2026-09-18）  
> **硬约束**：引擎 `empirical/*_result.json` **只读对照**；禁止双调度 / 恢复 `local_backtest` 为第二推荐主链。  
> **平台侧**：`packages/research.walkforward` / `summarize_walk_forward` +（可选）`compare_empirical_baseline`。

## 1. 目的

把 a-stock-engine 已冻结的 walk-forward OOS JSON 当作**对照基线**，核对平台 PIT / walk-forward 摘要的口径差异，而不是并行跑引擎仓。

## 2. 引擎侧输入（只读）

典型路径（sibling 仓，非本仓依赖）：

| 文件 | 含义 |
|------|------|
| `a-stock-engine/empirical/walk_forward_oos_result.json` | 校准段 + 逐年 fold 的 return / MDD / Sharpe |
| `walk_forward_oos_m2_result.json` / `*_paths_result.json` | 变体实验；对照时注明文件名 |

常用字段（引擎形状，非平台契约）：

- `calibration.return_pct` / `max_drawdown_pct` / `sharpe`
- `folds.<year>.return_pct` / `max_drawdown_pct` / `sharpe`

## 3. 平台侧输出

`summarize_walk_forward(...)` → `summary`：

- `compounded_oos_return`（小数，非百分比）
- `avg_oos_objective` / `degradation` / `consistency`
- `n_valid_folds`（无效折不得伪装成 0 收益）

对照前须统一：**引擎多为百分数**，平台摘要多为**小数**（`0.05` = 5%）。

## 4. 推荐步骤

1. 在平台用**同一日历窗**生成 fold 计划与有效折的 `oos_stats.total_return`（数据仍经 providers / engine 只读 DB）。  
2. 将引擎 JSON 与平台 `summary` 交给 `compare_empirical_baseline`（或手工表格）。  
3. 记录差异原因：宇宙、费用、复权、未来函数防护、折切规则（平台：`test_start = train_end + 1 day`）。  
4. **不要**在 Task Scheduler / 日批里调用引擎脚本。

## 5. 验收

- 文档可独立执行；有零公网单测覆盖 compare helper。  
- 无 `pip install` 引擎仓；无平行抓取。

## 6. 交叉链

- 路线图 M-R3 · M-R1 / M-R2  
- [`docs/contracts/walk-forward-summary.md`](../contracts/walk-forward-summary.md)  
- [`docs/upstream-archive.md`](../upstream-archive.md)
