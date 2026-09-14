# ADR 0035：策略配置版本化 + 轻量 PIT 对比

- 状态：Accepted
- 日期：2026-09-14

## 背景

Phase C 需要可复现的策略参数版本，并在同一 fixture 面板上对比两套配置，
而不引入完整回测平台或实盘。

## 决策

1. 策略配置为版本化 JSON：`id` / `version` / `top_n` / `reversal_q` /
   `value_factor` / `weights` / `universe_ref`。
2. 默认存放于 `packages/research/.../strategy_configs/*.json`；可路径加载。
3. `run_strategy_pit` / `compare_strategy_configs` 薄封装现有
   `run_pit_long_only`（已支持 weights / value_factor）。
4. workbench：`GET /api/research/strategy/configs`、
   `POST /api/research/strategy/compare`（body 含 panel 行或使用内置 fixture 面板）。
5. **不做**：参数优化器、实盘切换、夏普/年化主指标。

## 后果

- 推荐绩效（ADR 0033）与策略 PIT 对比职责分离。
- Phase C 在 `v2.6.0` 收口。
