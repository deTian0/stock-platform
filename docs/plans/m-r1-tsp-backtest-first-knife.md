# M-R1：TSP 回测对照 + 唯一首刀选型

> **状态**：done（2026-09-17）  
> **约束**：非整仓；不迁 React / Polars / DuckDB；数据仍经 `packages/providers`。  
> **下一实现**：M-R2（本选型唯一能力）。

---

## 1. 对照：平台已有 vs tick-stock-panel

| 能力 | stock-platform | tick-stock-panel（参考） |
|------|----------------|---------------------------|
| PIT 多头截面回测 | `run_pit_long_only` + 防未来函数测 | `backtest/engine.py` 组合引擎 |
| 滚动推荐复盘 | U7 `run_rolling_recommend_review` / `#backtest` | 复盘服务 + 多页 UI |
| 策略配置对比 | `strategy_config` / `#strategy-compare` | 优化器网格 + 研究 API |
| Walk-forward OOS | **无**独立折切分与 IS/OOS 退化摘要 | `backtest/walkforward.py`（`generate_folds` / `aggregate_oos`） |
| 因子 IC / 分层 | **无** | `backtest/factor.py`（Polars、IC/IR、分层多空） |
| 分钟回测 | 矩阵有 `minute`，**无**分钟回测入口 | `minute_replay` / `minute_trigger` |
| 挖掘矩阵 / 优化器 | **无** | `mining*` / `optimizer*` |
| UI | Jinja Workbench | React + ECharts 全 SPA |

平台强项：日用推荐 → 复盘 → `direction_accuracy` 闭环。  
TSP 强项：研究级回测工具链（WF / IC / 分钟 / 挖掘），栈重。

---

## 2. 唯一首刀选型

### 选定：**Walk-forward 摘要（IS / OOS 退化 + 折一致性）**

**不选**因子 IC（本刀）：IC 强依赖 TSP 因子注册表 + Polars 向量栈，量级接近「半套研究引擎」，违反「每刀一种能力」。

### 验收标准（M-R2）

1. **内核**落在 `packages/research`（纯 Python / pandas 即可）：  
   - 输入：有序交易日序列 + 可插拔「训练窗目标函数」（首版可对 `run_pit_long_only` 或固定参数网格做薄包装）。  
   - `generate_folds(train_days, test_days, step_days)` 语义对齐 TSP（测试窗从训练末日**次日**起，防泄漏）。  
   - `aggregate_oos`：至少产出 `compounded_oos_return`、`degradation`（IS−OOS）、`consistency`（OOS>0 折占比）。  
2. **契约**：短文进 `docs/contracts/` 或 research README；字段名稳定。  
3. **单测**：零公网；覆盖「折切分边界」与「无效折不得伪装成 0 收益」。  
4. **Workbench**：可选只读展示（`#backtest` 旁或折叠区）；**不**插入每日 brief 主路径。  
5. **数据**：仅经已声明矩阵能力（通常 `daily` / engine）；缺能力 fail-closed。

### 明确非目标

- 不迁 React / Vite / ECharts。  
- 不迁 Polars / DuckDB / TickFlow。  
- 不实现完整 `StrategyOptimizer` 网格、分钟回测、挖掘矩阵。  
- 不恢复 a-stock-engine 每日脚本双主链。  
- 不做全市场自动扫宇宙。

### 对照来源（只读）

- `tick-stock-panel/backend/app/backtest/walkforward.py`  
- `tick-stock-panel/backend/tests/backtest/test_walkforward.py`  
- 平台：`stock_platform_research.pit` / `rolling_review`

---

## 3. 后续排队（非本刀）

| 顺序 | 能力 | 条件 |
|------|------|------|
| 2 | 因子 IC 表（精简） | M-R2 稳定 + 明确因子子集（勿整表搬） |
| 3 | empirical 基线对照手册 | M-R3 |
| Later | 分钟回测入口 / A/B 进日用主路径 | M-R4 / M-R5 |
