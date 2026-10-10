# 契约：策略 A/B（`S1`）

> 里程碑 `S1`（`v4.1.0`），承接 `M-R5` 旁路（ADR 0035）与 `X4` 单引擎（ADR 0059）。
> 只读 `market.db`；SIMULATE；**默认关闭**；不替换主路径 picks；非投资建议。
> 实现：`packages/research/.../strategy_ab.py` + `strategy_config.py`；
> ADR：[`docs/architecture/0060-strategy-ab-full-engine.md`](../architecture/0060-strategy-ab-full-engine.md)。

## 1. 目的

让「因子 / 闸门变更」可带**复盘对比**，并让 A/B 结果**同屏可比** —— 且与回测 /
推荐回放**同源**（同一台 `book_replay.replay_book`）。

## 2. 输入契约

### 2.1 策略配置 `StrategyConfig`

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `id` | str | — | 臂标识（必填） |
| `version` | str | `"1"` | 配置版本 |
| `top_n` | int | 1 | PIT 轻量路径每日选股数（引擎路径由 `max_picks_per_day` 决定） |
| `reversal_q` | float | 0.30 | 反转分位闸门（`apply_entry_gates`） |
| `value_factor` | bool | false | 是否启用价值因子 |
| `weights` | dict | `W_DEFAULT` | 因子权重（`vol`/`rev`/`value`/`q`/`g`） |
| **`gates`** | dict[str,float] | `{}` | **闸门**；`min_pick_score` 缺省 `0.80` |
| `universe_ref` | str? | null | 仅 PIT / 轻量路径使用 |
| `description` | str | `""` | 说明 |

- **别名**：扁平键 `min_pick_score` / `minPickScore` 会折进 `gates`。
- 非数值 / `None` 的闸门值被**跳过**（不静默变 0）。
- **裸 id 可加载**：`<id>` 与 `<id>.json` 都解析到
  `packages/research/.../strategy_configs/`。

### 2.2 引擎 A/B 入口

| 函数 | 输入 | 输出 |
|---|---|---|
| `config_entry_provider(cfg)` | 配置 | `EntryProvider`（`screener_entry_provider` 的配置化封装） |
| `run_config_book(feats, cfg, *, params)` | 特征帧 | 单臂：曲线 / 成交 / 未平仓 / `metrics` / `review` |
| `compare_strategy_ab_engine(feats, a, b, *, params)` | 特征帧 + 两配置 | 两臂 + `delta` + `winner` + `sameDefinition` |
| `compare_strategy_ab_from_bars(bars, a, b, *, universe, start, end, ...)` | bars | 同上（内部 `prepare_book_frame`） |

- `bars` 需含 `code` / `date` / `close`（可选 `pct_chg`）。
- `cfg` 可为 `StrategyConfig` / mapping / 裸 id / JSON 路径。
- entry provider 在共享循环**内部**执行 —— 无法绕过 `max_positions` / 持有去重 /
  涨停封单 / 冷静期。

## 3. 输出契约

```
{
  "ok": true,
  "a": { "configId", "tradeCount", "metrics", "review", "equityCurve", "finalEquity" },
  "b": { ...同构... },
  "delta": { <AB_METRIC_KEYS 每项 = B − A；任一侧缺值即 null> },
  "winner": "<configId>" | "tie",
  "winnerNote": "（仅当某一臂零成交时出现）",
  "sameDefinition": {
    "singleLoop": true, "singleEntryProvider": true,
    "singleMetrics": true, "singleExitDefinition": true
  },
  "replacesPicks": false,
  "panelSource": "engine",
  "environment": "SIMULATE",
  "liveTradingEnabled": false
}
```

- `AB_METRIC_KEYS`：`total_return` / `cagr` / `max_drawdown` / `sharpe` / `sortino` /
  `calmar` / `win_rate` / `n_trades` / `avg_hold_days` / `turnover_per_year` /
  `turnover_notional_per_year` / `avg_invested_ratio` / `final_equity`。
- `review`：`{ settledCount, pendingCount, directionHits, directionAccuracy, metricNote }`。
  `directionAccuracy = 已平仓净收益>0 / 已结算`；空仓为 `null`（**不填 0**）。
- `winner`：两臂都有成交时先比 `sharpe`，否则比 `final_equity`；相等 `"tie"`。

## 4. 铁律

1. **同一帧、同一引擎**：两臂只差 entry provider；`sameDefinition` 全 `true` 才算同源。
2. **默认关闭**：A/B 不进每日推荐主路径、不替换 picks。
3. **fail-closed**：空帧 → `ok=false` + 中文 `reason`；无 `market.db` → HTTP **503**；
   未知配置 → **404**。
4. **只读**：`market.db` 只读打开，绝不写入。
5. **不可横比**（承接 [`trading-rules.md`](trading-rules.md) §9）：跨运行比较必须声明
   `exit_policy` / `cooldown_days` / `drift_band` / `universe` / `pct_scale`。

## 5. HTTP / CLI

| 表面 | 说明 |
|---|---|
| `GET /api/research/strategy/configs` | 配置列表（含 `gates`） |
| `POST /api/research/strategy/compare` | 轻量 PIT 对比（`M-R5`，保留） |
| **`POST /api/research/strategy/ab-engine`** | **同源引擎 A/B（S1）**：body `{configA, configB, start?, end?, universe?, initialCapital?, maxPositions?}` |
| `stock-platform-strategy-ab` | CLI：`--config-a/--config-b --start --end --universe --json` |

## 6. 非目标

参数优化器 / 自动选优；把 A/B 插入主路径；实盘；第二套回测引擎。
