# 契约：闸门参数敏感性（`S3`）

> 里程碑 `S3`（`v4.1.2`），承接 `S1` 同源 A/B 与 `S2` 因子准入。
> 只读 `market.db`；SIMULATE；**稳健区间优先于单点最优**；不进 picks 主路径；非投资建议。
> 实现：`packages/research/.../sensitivity.py`（+ `gates.py` 的 `EntryGateParams`）；
> ADR：[`docs/architecture/0062-gate-parameter-sensitivity.md`](../architecture/0062-gate-parameter-sensitivity.md)；
> 实测：[`docs/ops/gate-sensitivity-benchmark.md`](../ops/gate-sensitivity-benchmark.md)。

## 1. 目的

`S1` 让「闸门变更」可表达，`S2` 让「新因子」可准入 —— 但都没回答路线图 `S3` 的追问：
**选定的闸门取值，是坐在一片高原上，还是踩中了一个孤峰？** 孤峰是曲线拟合的典型signature；
一片平滑高原才是「edge 是结构性的、不是调出来的」该有的样子。

`S3` 把这件事收敛为**唯一扫描内核**：对入场闸门的关键阈值做网格扫描，每个网格点走
**同一台引擎**、**同一个入场 provider**（只差旋钮），再由**唯一纯函数**给出**稳健区间**判定。

## 2. 旋钮与默认网格

`SWEEP_KNOBS = ("reversal_q", "min_pick_score", "ma_band")`。

| 旋钮 | 归属 | 默认网格 `DEFAULT_GRIDS` | 语义 |
|---|---|---|---|
| `reversal_q` | `EntryGateParams.reversal_q` | `0.10 / 0.20 / 0.30 / 0.40 / 0.50` | 截面超卖分位：`rev_chg > quantile(reversal_q)` 即**否** |
| `min_pick_score` | provider 分数下限（非 gate 字段） | `0.50 / 0.60 / 0.70 / 0.80 / 0.90` | `composite_score >= floor` 才可入 |
| `ma_band` | `EntryGateParams.ma20_band` + `ma60_band` | `0.88 / 0.90 / 0.93 / 0.96 / 0.98` | **拒绝**下限：`close < ma × band` 即否（**band 越大越严**） |

- 网格**跨骑**出厂默认值（`0.30` / `0.80` / `0.93`），使判定由默认值**周围的形状**决定，而非端点。
- `ma_band` 同时改 `ma20_band` 与 `ma60_band`（出厂两者都是 `0.93`）。
- `min_pick_score` **不是** `EntryGateParams` 字段 —— 它是 provider 的分数下限，
  `gate_params_for("min_pick_score", v)` 原样返回 `base`，由 `score_floor_for` 单独路由。

## 3. 判定内核 `summarize_sweep`（纯函数）

```python
summarize_sweep(points, *, objective="sharpe", direction=None, tolerance=0.10, min_plateau=2)
```

- **目标方向**：`OBJECTIVE_DIRECTION` 默认 `sharpe/sortino/calmar/total_return/cagr/win_rate → max`，
  `max_drawdown → min`；未登记的目标默认 `max`，可用 `direction` 覆盖。
- **容差带**：某点「在高原上」当且仅当 `sign·(obj − best) ≥ −tol`，
  其中 `tol = tolerance × |best|`（**相对**最优值）；`|best| ≈ 0` 时退化为绝对 `tolerance`。
- **稳健区间 `robustRange`**：**包含最优点、且连续**的一段网格值全部在容差带内的
  `{lo, hi, n}`（`n` = 连续点数）。单点最优只会得到 `n=1`。
- `stability = 高原点数 / 可用点数`；`monotonic` = 相邻差符号一致时的方向（`+1 / -1 / 0`）。

| verdict | 条件 | 含义 |
|---|---|---|
| `insufficient` | 可用点 < 3 | 网格太稀疏 / 目标列缺失，**不下结论** |
| `flat` | 网格内目标极差 ≈ 0 | 该闸门对目标**不敏感**，任取皆可 |
| `robust` | `robustRange.n ≥ min_plateau` | 最优**非单点**，过拟合风险低 |
| `fragile` | 仅最优点落在容差带内 | **孤峰**，疑为曲线拟合，不宜据此定档 |

> 判定优先级：`insufficient` → `flat` → `robust` / `fragile`。`best=None` 只出现在
> `insufficient`（每个点都缺目标列），**绝不**凭空造一个最优。

## 4. 扫描内核 `sweep_entry_gate`

```python
sweep_entry_gate(feats, *, knob, values, base_params=None,
                 min_pick_score=0.80, weights=None, value_factor=False, params=None)
```

- `feats` 是**已构建**的特征帧（`backtest.prepare_book_frame`，`X4` 单点）——
  **只建一次**、跨点复用，所以两个点的净值曲线**只差旋钮**，无需二次归一。
- 每个点经 `book_replay.replay_book`（`X4` 单循环）+ `book_replay.screener_entry_provider`
  （**同一** provider，`S3` 新增 `gate_params` 透传）跑完整回放，取 `portfolio.compute_metrics`。
- 每点附带 `effective = {gateParams, minPickScore}`，把「这一点实际用了什么参数」写进产物。
- fail-closed：未知 `knob` / 空网格 → 抛 `ValueError`，**不**返回伪造的高原。

## 5. 报告 `build_sensitivity_report`

```python
build_sensitivity_report(feats, *, knobs=None, grids=None, objective="sharpe",
                         tolerance=0.10, direction=None, base_params=None,
                         min_pick_score=0.80, weights=None, value_factor=False, params=None)
```

`overall` 优先级：任一 `insufficient` → `insufficient`；否则任一 `fragile` → **`fragile`**
（一个踩中孤峰的闸门**不得**被悄悄信任）；否则任一 `robust` → `robust`；否则 `flat`。

## 6. 输出契约

```
{
  "ok": true,
  "objective": "sharpe", "tolerance": 0.10,
  "knobs": {
    "<knob>": {
      "points": [
        { "value": <float>, "nTrades": <int>, "finalEquity": <float>,
          "metrics": { "total_return","cagr","max_drawdown","sharpe","sortino","calmar",
                       "win_rate","n_trades","avg_hold_days","turnover_per_year", ... },
          "effective": { "gateParams": {...}, "minPickScore": <float> } }, ...
      ],
      "summary": {
        "objective","direction","tolerance","nPoints",
        "verdict": "robust|fragile|flat|insufficient",
        "best": <float|null>, "bestObjective": <float|null>,
        "plateau": [<float>...], "robustRange": {"lo","hi","n"}|null,
        "stability": <float|null>, "monotonic": -1|0|1, "spread": <float|null>,
        "note": "<中文自解释>"
      }
    }, ...
  },
  "verdicts": { "<knob>": "<verdict>" },
  "robust": [...], "fragile": [...], "flat": [...], "insufficient": [...],
  "overall": "robust|fragile|flat|insufficient",
  "environment": "SIMULATE", "liveTradingEnabled": false,
  "note": "闸门敏感性扫描：每点走同一 book_replay 引擎，仅旋钮不同；稳健=最优非单点，脆弱=仅最优点达标（过拟合风险）。",
  "disclaimer": "Research only; not investment advice."
}
```

## 7. 闸门常量单点：`EntryGateParams`

```python
@dataclass(frozen=True)
class EntryGateParams:
    reversal_q: float = 0.30
    ma20_band: float = 0.93
    ma60_band: float = 0.93
    vol_filter: bool = True
```

- 默认值 = `a-stock-engine lvrev_scorer` 移植期的**硬编码常量逐字** →
  `apply_entry_gates(df)` / `apply_entry_gates(df, reversal_q=0.30)` / `apply_entry_gates(df, params=EntryGateParams())`
  **三者逐位相同**（`tests/test_gates.py` 对 reference 循环的等价性测试为证）。
- 解析顺序：显式 `reversal_q` 参数 **覆盖** `params.reversal_q`；两者都缺 → 用 `0.30`。
- `screener_entry_provider(..., gate_params=...)` 让扫描仍走**同一个** provider；
  `reversal_q` 缺省由 `0.30` 改为 `None`（**有效值不变**），`gate_params` 缺省时由 `reversal_q` 合成。

## 8. HTTP / CLI

| 表面 | 说明 |
|---|---|
| `stock-platform-strategy-sensitivity` | CLI：`--db/--start/--end/--universe/--knobs/--objective/--tolerance/--min-pick-score/--initial-capital/--max-positions/--reversal-q-grid/--min-pick-score-grid/--ma-band-grid/--json` |
| **`POST /api/research/strategy/sensitivity`** | body `{start, end, universe, knobs, objective, tolerance, minPickScore, initialCapital, maxPositions, grids}`；返回报告 |

- 校验（旋钮 id / objective / universe / 窗口）**先于** DB 探测 → 未知旋钮 / 非法 objective **400**、无 DB **503**（fail-closed）。
- CLI 与端点都**不**带 `with_amount` 读 bars —— 与 `stock-platform-backtest` 的默认列集一致，保证与 B1 基线同源可比。

## 9. 铁律

1. **稳健优先于最优**：`fragile` 必须显式暴露；`overall` 只要有一个 `fragile` 就是 `fragile`。
2. **同引擎、同 provider**：两点之间只允许旋钮不同（`X4` 单循环 + 单 provider 的再申明）。
3. **默认路径逐位不变**：`EntryGateParams()` 就是 B1 基线；出厂闸门值不动。
4. **不造数据**：每点都缺目标列 → `insufficient` + `best=None`；空网格 / 未知旋钮 → 抛错。
5. **只读**：`market.db` 只读打开，绝不写入。
6. **只做诊断**：不自动选优、不自动改档；结论只进报告与 UI。

## 10. 非目标

参数**优化器** / 自动选优 / 自动改档；行业中性化与风格暴露（属 `S4`）；
LLM 辩论进主路径（属 `S5`）；把扫描结论自动写回策略配置；实盘。
