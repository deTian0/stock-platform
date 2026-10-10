# ADR 0060：策略 A/B 完整版（同源引擎 + 复盘对比 + 同屏）

- 状态：Accepted
- 日期：2026-10-10
- 里程碑：`S1`（`v4.1.0`，U7 完整版；[路线图](../plans/trading-system-roadmap.md) §3.3）

## 背景

`M-R5`（ADR [0035](0035-strategy-config-compare.md) 的延伸）给了「策略 A/B 旁路」：
默认关闭、附在推荐响应上的**轻量 PIT 面板**对比
（`strategy_config.compare_strategy_configs`）。它遗留三个 U7 缺口：

1. **口径孤立**：对比只出 PIT 的 `final_equity` / `tradeCount`，不接组合引擎、
   没有复盘维度。`B5` 之后回测与在线已同源，A/B 却仍是**另一把尺子**。
2. **闸门不可表达**：`StrategyConfig` 只有因子权重 —— 改「闸门」（如入选分下限）
   写不进配置，也就无法对比。
3. **非同屏**：Workbench 只有一行 `kv` 列表，两臂结果不能逐项并排比较。

`X4`（ADR [0059](0059-picks-backtest-parity.md)）把逐日回放抽成单点
`book_replay.replay_book` 之后，A/B 第一次有了「用**同一台引擎**跑两臂」的条件。

## 决策

1. **配置可表达闸门**：`StrategyConfig` 增 `gates: dict[str, float]`，接受扁平别名
   `min_pick_score` / `minPickScore`；`min_pick_score` 缺省继承
   `DEFAULT_MIN_PICK_SCORE = 0.80`（与 screener 基线一致）。
2. **同源引擎 A/B**：新增 `strategy_ab.config_entry_provider` / `run_config_book` /
   `compare_strategy_ab_engine` / `compare_strategy_ab_from_bars`。两臂消费**同一特征帧**
   并跑**同一个** `replay_book`，只由 entry provider 区分，因此两条曲线只差配置。
3. **带复盘对比**：每臂附 `review` 块（`directionAccuracy` / `settledCount` /
   `pendingCount`），口径对齐 `performance` / U3 的「看多收益>0 算对；缺行情 pending；
   空仓不填 0」。
4. **同屏可比**：`delta = B − A`（同口径无需二次归一）+ `sameDefinition` 身份块
   （断言两臂确实跑 `X4`/`B5` 的单点定义）。Workbench 新增
   `POST /api/research/strategy/ab-engine` 与 `#strategy-compare` 面板内的
   「A/B 同屏」区块（两列 + Δ 列 + 双净值曲线）。
5. **默认关闭**：A/B 仍是**旁路** —— 不替换主路径 picks；无 `market.db` fail-closed。
6. **不做**：参数优化器 / 自动选优；把 A/B 插入每日推荐主路径；实盘。

## 后果

- 「因子 / 闸门变更可带复盘对比」在**同一台引擎、同一帧**上成立 —— A/B、回测、
  推荐回放三者口径同源。纯一致性由 `tests/test_strategy_ab_engine.py` 钉住：
  「baseline 配置 == `run_portfolio_backtest`」在曲线 / 成交 / 指标上**逐位一致**。
- `load_strategy_config` 现在也接受**裸 id**（`<id>` 与 `<id>.json` 都解析到
  `strategy_configs/`），与 sidecar / CLI / HTTP 路由的解析保持一致。
- 新 CLI：`stock-platform-strategy-ab`。
- 非目标（本 ADR 外）：`refresh_etf_daily_prices` 的 ETF 长历史缺失，另行立项。
