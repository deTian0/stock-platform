# 契约：Walk-forward 摘要（M-R2）

> 状态：**Accepted** · 对齐 tick-stock-panel `backtest/walkforward.py` 语义（非整仓）

## 字段

### 折切分 `generate_folds(start, end, train_days, test_days, step_days)`

| 字段 | 说明 |
|------|------|
| `index` | 折序号（从 0） |
| `train_start` / `train_end` | 训练窗（日历日） |
| `test_start` / `test_end` | 测试窗；**`test_start = train_end + 1 天`**（防同日泄漏） |

区间不足以切出一折 → `ValueError`（中文）。

### 汇总 `aggregate_oos(fold_records)`

仅传入**有效折**（`is_score` 与 `oos_objective` 均非空且无 `error`）。

| 字段 | 说明 |
|------|------|
| `n_folds` | 有效折数；0 时 `degradation=null`（不得伪装成 0 收益优势） |
| `compounded_oos_return` | 各折 `oos_stats.total_return` 复利 |
| `avg_is_objective` / `avg_oos_objective` | 均值 |
| `degradation` | 归一空间 IS−OOS（`direction=max|min`） |
| `consistency` | OOS `total_return > 0` 的折占比 |
| `oos_equity_curve` | `[{fold, date, value}]` |

## API

- `POST /api/research/backtest/walk-forward` — 折计划 + 可选 `foldRecords` 汇总  
- Workbench `#backtest` 折叠区「Walk-forward 摘要」  
- **不**插入每日 brief 主路径

## 数据

折目标函数由调用方提供；日线仍经能力矩阵 / `engine_sqlite`。缺源 fail-closed。
