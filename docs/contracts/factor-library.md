# 契约：因子库与 IC/ICIR 准入（`S2`）

> 里程碑 `S2`（`v4.1.1`），承接 `S1` 同源 A/B 与 `X4` 单引擎。
> 只读 `market.db`；SIMULATE；**不达标不启用**；不进 picks 主路径；非投资建议。
> 实现：`packages/research/.../factors.py` + `factor_ic.py`；
> ADR：[`docs/architecture/0061-factor-library-admission.md`](../architecture/0061-factor-library-admission.md)；
> 实测：[`docs/ops/factor-ic-benchmark.md`](../ops/factor-ic-benchmark.md)。

## 1. 目的

在 lvrev 真正加权的两个因子（`low_vol` 0.5 + `reversal` 0.5）之外，**新增候选因子**
并给它们一个**可复现的准入闸门**：每个因子必须过 IC / ICIR 检验、且与已启用因子**正交**，
否则**不启用**。因子定义收敛为**唯一数学单点**（`factors.py`），准入判定收敛为**唯一纯函数**
（`factor_ic.select_enabled` / `admit_factor`）。

## 2. 因子库（单点定义）

`FACTOR_LIBRARY: dict[str, FactorSpec]`（registry 顺序 = 报告顺序）。`FactorSpec` 冻结
dataclass：`name` / `label` / `direction`（**声明**方向 ±1）/ `description` / `compute`。

| name | label | direction | 口径 | 需要列 |
|---|---|---|---|---|
| `low_vol` | 低波动 | **-1** | 20 日已实现波动率（`vol20`）；越低越好（**基线**） | `vol20` |
| `reversal` | 短期反转 | **-1** | 过去 20 交易日涨跌幅（`rev_chg`）；近期弱者反弹（**基线**） | `rev_chg` |
| `long_reversal` | 6 个月反转 | **+1** | `-(close.shift(20)/close.shift(120)-1)`；**跳过最近一月**，与 20 日反转不共窗（新增） | `close` |
| `max_ret` | 极端收益 MAX | **-1** | 过去 20 日单日最大涨幅（`ret1`，彩票偏好）；越高未来收益越低（新增） | `ret1` |
| `illiq` | Amihud 非流动性 | **+1** | 过去 20 日 `mean(|ret1|/amount) × 1e9`；越不流动预期收益越高（新增） | `ret1` `amount` |

- **基线** = `BASELINE_FACTORS = ("low_vol", "reversal")`；**新增** = `NEW_FACTORS = ("long_reversal", "max_ret", "illiq")`。
- `direction` 是**对因子→未来收益关系的声明**，不是「越大越买」。准入时用它做**符号一致性**硬闸门。
- 缺列 → 该因子整列为 `NaN`（**优雅降级**，不抛异常），相关截面被自动跳过。
- 纯函数：无网络、无 DB、无副作用；`factor_spec(name)` 对未知名抛 `KeyError`。

## 3. 特征帧与因子帧

| 函数 | 输入 | 输出 |
|---|---|---|
| `build_feature_frame(bars, *, pct_scale="auto")` | bars（`code`/`date`/`close`，可选 `pct_chg`/`vol`/`amount`） | PIT 特征帧（**保留** `vol`/`amount`） |
| `build_factor_frame(feats, *, factors=None)` | 特征帧 | 每因子一列的**原始因子值** |
| `factor_correlation(frame)` | 因子帧 | 因子两两 **Spearman** 相关矩阵 |

- `build_feature_frame` 是 `backtest.compute_features`（**PIT 特征与复权单点**）的薄封装，
  仅额外 `keep_extra=("vol", "amount")`；`compute_features` 的 `keep_extra` **默认空**，
  既有调用点逐位不变。
- `factor_correlation` **scipy-free**（`frame.rank().corr()`）—— `DataFrame.corr(method="spearman")`
  会 import `scipy.stats`（本仓未装）。

## 4. 准入闸门（不达标不启用）

### 4.1 阈值 `DEFAULT_ADMISSION`

| 键 | 默认 | 含义 |
|---|---|---|
| `min_abs_ic` | **0.02** | `|mean_ic|` 下限 |
| `min_abs_icir` | **0.15** | `|ICIR|` 下限 |
| `min_dates` | **20** | 有效截面数下限 |

`DEFAULT_MAX_CORR = 0.70`：与**已启用**因子的 `|Spearman ρ|` 达到此值即**冗余**。

### 4.2 单因子判定 `admit_factor(summary, *, direction, thresholds)`

四项检查**全 true** 才 `passed`；失败项写进中文 `reasons`（自解释）：

1. `n_dates >= min_dates`
2. `|mean_ic| >= min_abs_ic`
3. `|ICIR| >= min_abs_icir`
4. **符号一致**：`sign(mean_ic) == sign(direction)`（IC 方向与声明矛盾 → **永不启用**）

### 4.3 正交选择 `select_enabled(order, passed, correlation, *, max_corr)`

贪心、**纯函数**（零依赖，可脱库单测）。按 `order` **在位者优先、新因子按 `|ICIR|` 降序**遍历：
过闸门 **且** 与每个**已保留**因子 `|ρ| < max_corr` 才保留，否则记 **冗余**。
返回 `{enabled, redundant, rejected, redundancy}`（`redundancy[name] = (kept, rho)`）。

### 4.4 报告 `build_factor_ic_report(feats, *, horizon=20, factors, thresholds, sample_every=5, min_names=30, max_corr=0.7, compute_correlation=True)`

- 每个采样截面算前瞻收益 `close.shift(-horizon)/close − 1`（按 `code`），
  经 `summarize_factor_ic`（**IC 单点**）聚合。
- `sample_every` 抽样交易日（避免重叠前瞻窗主导）；`min_names` 丢退化截面。
- 先 IC/ICIR 过闸门，再正交选择；冗余因子在 `admission.checks.orthogonal=False` 且追加理由，
  并**置 `passed=False`**。

## 5. 输出契约

```
{
  "ok": true,
  "horizon": 20, "sampleEvery": 5, "minNames": 30, "maxCorr": 0.7, "nDates": <int>,
  "factors": {
    "<name>": {
      "label", "direction", "description",
      "n_dates", "mean_ic", "mean_abs_ic", "std_ic", "icir", "positive_ic_rate",
      "admission": { "passed", "checks": {"n_dates","abs_ic","abs_icir","sign"[,"orthogonal"]},
                     "reasons": [...], "direction", "mean_ic", "icir", "n_dates", "thresholds" }
    }, ...
  },
  "correlation": { "<a>": { "<b>": <float|null> } } | null,
  "enabled":   ["..."],
  "redundant": ["..."],
  "rejected":  ["..."],
  "disabled":  ["...", "..."],   // rejected + redundant
  "environment": "SIMULATE",
  "liveTradingEnabled": false,
  "note": "因子 IC/ICIR + 正交准入（S2）；SIMULATE；**不达标不启用**；不进 picks 主路径；非投资建议。",
  "disclaimer": "Research only; not investment advice."
}
```

- `enabled` ∩ `redundant` = ∅；`disabled = rejected + redundant`。
- `correlation` 为 `null`（当 `compute_correlation=False` 或因子数 < 2）。

## 6. lvrev 权重（默认不变）

| 权重档 | 说明 |
|---|---|
| `W_DEFAULT` | `vol=0.5, rev=0.5` —— **默认，逐位不变** |
| `W_S2` | `vol=0.4, rev=0.3, mom=0.3` —— **未启用为默认**，仅作接入演示 |

- `factor_scores` 现额外产出 `momentum` / `max_ret` / `illiq` 列（缺列填中性 `0.5`）；
  `score_lvrev` 用 `w.get("mom"|"max"|"illiq")`（**默认 0** → 基线精确等价）。
- 库内因子的**启用与否不自动改动 lvrev 权重** —— 权重由人决定；本契约只交付「准入闸门」。

## 7. HTTP / CLI

| 表面 | 说明 |
|---|---|
| `stock-platform-factor-ic` | CLI：`--db/--start/--end/--horizon/--sample-every/--min-names/--universe/--factors/--min-abs-ic/--min-abs-icir/--min-dates/--correlation/--json` |
| **`POST /api/research/factor/admission`** | body `{start, end, horizon, sampleEvery, minNames, universe, factors, thresholds, correlation}`；返回报告（含相关矩阵，若 `correlation=true`） |

- 校验（因子 id / universe / 窗口）**先于** DB 探测 → 未知因子 **400**、无 DB **503**（fail-closed）。
- CLI 以 `with_amount=True` 读 bars（`illiq` 需 `amount`）。

## 8. 铁律

1. **不达标不启用**：`enabled` 只会包含「过 IC/ICIR **且** 与在位者正交」的因子。
2. **符号是硬闸门**：IC 方向与 `direction` 声明矛盾 → 永不启用（防"看着有 IC 就上"）。
3. **默认关闭**：库内新因子权重默认 `0`，不改 lvrev 主路径、不进 picks。
4. **fail-closed**：未知因子 / 空帧 / 无评估截面 → `ok=false` + 中文 `reason`；HTTP 400 / 503。
5. **只读**：`market.db` 只读打开，绝不写入。
6. **scipy-free**：相关矩阵用 pandas rank 实现，保持依赖最小。

## 9. 非目标

参数优化器 / 自动选优；把新因子直接接入主路径 picks；行业中性化（属 `S4`）；
闸门敏感性（属 `S3`）；实盘。
