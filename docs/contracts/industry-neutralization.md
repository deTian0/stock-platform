# 契约：行业中性化 / 风险暴露（`S4`）

> **状态**：Accepted（2026-10-10）　**里程碑**：`S4`（路线图 §3.3）　**目标 tag**：`v4.1.3`
> **上游**：`docs/plans/trading-system-roadmap.md` §3.3 ｜ ADR [`0063`](../architecture/0063-industry-neutralization.md)
> **实测**：[`docs/ops/neutralization-benchmark.md`](../ops/neutralization-benchmark.md)
> **承接的引擎约定**：`a-stock-engine/src/factor_engine.py`（`_zscore` 行业分组 Z-Score + 综合分行业去均值）

---

## 1. 一句话

在**打分前**按行业把因子分中性化（组内去均值 / z-score），可选对风格暴露做正交残差化，
并可选限制每行业候选数；**回测对照**给出「中性化 vs 原始」的同引擎差异。

本契约定义 `S4` 的**单点定义**、默认关闭语义与不可横比的边界。

---

## 2. 数据来源（只读）

| 项 | 值 | 说明 |
|----|----|------|
| 行业分类 | `market.db` · `fundamentals.industry` | 实测 **5237 码 / 5228 有行业 / 111 个细分行业**（电气设备 324 · 元器件 289 · 专用机械 267 · 软件服务 261 · 半导体 195 …） |
| 行情 | `market.db` · `daily_price` | 与 `B1`/`X4` 同一加载器（`backtest_cli.load_engine_bars`） |
| `factor_scores.sector` / `stock_picks.sector` | **空表**（0 行） | 平台侧**不**依赖它们；真源是 `fundamentals.industry` |

### 2.1 `code` 口径（踩过的坑）

`daily_price.code` = `000001.SZ`（带交易所后缀），`fundamentals.code` = `000001`（裸 6 位）。
两边一律经 `portfolio.norm_code`（`str(x).replace(".", "")[:6]`）归一后 join —— **同一个 6 位归一化**，
就是资产分类 / 印花税豁免用的那个，不另起一套。未映射的码归入 `UNKNOWN_GROUP`（`"__UNKNOWN__"`），
保证分组**总是全覆盖**（权重恒为 1）。

---

## 3. 中性化核（单点定义）

`stock_platform_research.neutralization` —— 纯函数，无网络、无 DB、无副作用。

### 3.1 `NeutralizeParams`（frozen dataclass）

| 字段 | 默认 | 语义 |
|------|------|------|
| `industry_col` | `"industry"` | 行业标签列 |
| `mode` | `"demean"` | `demean`（组内减均值）｜`zscore`（组内 z，`clip` 截断） |
| `clip` | `3.0` | `zscore` 的截断界 |
| `min_group_size` | `5` | **组内成员 < 此值 → 该组保持原值**（小样本行业无有效截面） |
| `rescale` | `"rank"` | `rank`：中性化后按全局分位重新映射回 `[0,1]`；`none`：保留原始尺度 |
| `composite_demean` | `True` | 组合分再按行业去均值（对齐引擎 §134 的那一行） |
| `style` | `()` | 需正交的风格暴露列（如 `("vol20",)`） |
| `style_clip` | `3.0` | 风格残差的截断界（`None` = 不截断） |

`mode` / `rescale` 的非法值、`min_group_size < 1` → **构造即 `ValueError`**（fail-closed）。

### 3.2 三个核心函数

| 函数 | 作用 |
|------|------|
| `resolve_groups(source, col=…)` | 行 → 行业标签；缺失/空串 → `UNKNOWN_GROUP`；**列不存在 → 全体同一组**（退化为全局去均值，不崩、也不静默 no-op） |
| `industry_neutralize_series(s, groups, *, mode, clip, min_group_size)` | 单列中性化；小组保原值；不改输入 |
| `residualize(s, exposures, *, groups, clip, min_rows)` | 按**组内** OLS（带截距）残差；`s` 或暴露缺失的行保留原值；可用行 < `max(min_rows, k+2)` 的组**不拟合** |
| `neutralize_factor_scores(scores, source, params)` | 逐因子：行业中性化 → 可选风格残差 → 可选 `rank` 重标定；列序与索引不变 |

### 3.3 为什么默认 `rescale="rank"`

`demean` / `zscore` 会把分值移出 `[0,1]`，而下游 `min_pick_score`（默认 `0.80`）是**按 `[0,1]` 标定的**。
`rank` 把中性化后的**排序**保留、尺度还原，`min_pick_score` 语义因此不变（≈ 当日截面分位）。
选 `none` 时请自行重新标定 `min_pick_score`。

---

## 4. 打分钩子：`lvrev.score_lvrev(..., neutralize=None)`

```python
score_lvrev(df)                              # ≡ score_lvrev(df, neutralize=None)  → 逐位相同
score_lvrev(df, neutralize=NeutralizeParams())  # 行业中性化
```

- `neutralize=None`（默认）→ 组合分与 `S4` 之前**逐位相同**（`test_score_lvrev_none_is_bit_identical` 为证）。
- 中性化时：`factor_scores()` → `neutralize_factor_scores()` → 加权求和 → 可选组合分行业去均值（+ `rank` 重标定）。

---

## 5. 透传链（**不复制**中性化）

| 环节 | 变更 | 默认 |
|------|------|------|
| `backtest.prepare_book_frame(..., industry_map=None)` | `industry_map` 非空时 `attach_industry` 加一列 | `None` → 不加列（逐位不变） |
| `book_replay.screener_entry_provider(..., neutralize=None, max_per_industry=None)` | 把 `neutralize` 直传 `score_lvrev` | `None` → 逐位不变 |
| `backtest_cli.load_engine_industry(db)` | 只读 `fundamentals(code, industry)`；**缺表 → `KeyError`**（不静默返回空表） | — |

> **铁律**：中性化只有一处实现。任何路径（回测 / A/B / API / CLI）都必须经
> `screener_entry_provider` 进入**同一个** `replay_book` 循环，**不得**复制闸门或评分。

---

## 6. A/B（`neutralization_ab.py`）

`compare_neutralization_ab(feats, *, neutralize, industry_map=None, params=None, max_per_industry=None, min_pick_score=0.80, …)`

| 臂 | 定义 |
|----|------|
| `a` = `raw` | `neutralize=None`（`S4` 之前的账本） |
| `b` = `neutral` | `neutralize=params`，并施加 `max_per_industry`（若给） |

- 两臂消费**同一** `feats`、跑**同一个** `replay_book` → 曲线差异只可能来自处理项。
- `delta = b − a`，键集 = `strategy_ab.AB_METRIC_KEYS`（`delta` / `review` / `sameDefinition`
  **直接复用 `S1` 的实现**，不复制）。
- `exposure.{raw,neutral}`：各臂**实际持有过的码**（已平仓 ∪ 窗口末未平仓）的等权行业画像 ——
  `{n_codes, n_industries, max_weight, max_industry, hhi}`（`hhi = Σw²`）。
- `industryAvailable=false` 时附 `warning`：帧无行业列 → 退化为全局去均值，**行业口径不可用**。
- `winner`：两臂都有成交时先比 `sharpe`，否则比终值；`tie` 兜底。任一方零成交 → 附 `winnerNote`。

---

## 7. 暴露约束：`max_per_industry`

同一 provider 内、`max_picks_per_day` **之前**施加：按行业 `head(k)`，随后**按 `composite_score` 重排**
（保证「构成」变了而「排序规则」没变）。列不存在或 `k <= 0` → 跳过。

---

## 8. HTTP / CLI

| 入口 | 说明 |
|------|------|
| `POST /api/research/strategy/neutralization` | 请求：`start/end/universe/mode/clip/minGroupSize/rescale/compositeDemean/style/maxPerIndustry/minPickScore/initialCapital/maxPositions`；只读 `market.db`；**校验 400 先于 DB 503**；无 DB → 503 fail-closed |
| `stock-platform-strategy-neutralization` | CLI 同名参数；`--json` 出完整报告 |

两者与 `compare_neutralization_ab` 同路，不另写一套判定。

---

## 9. 铁律

1. **默认关闭**：`neutralize=None` → 组合分逐位不变；`industry_map=None` → 不加列。
2. **单点定义**：中性化核、去均值、A/B 契约各一份；`delta` / `review` / `sameDefinition` 与 `S1` 共用实现。
3. **只读**：`market.db` 以 `mode=ro` 打开，永不写；平台**不代抓、不补写**行业或行情。
4. **不可横比**：`rescale="rank"` 与 `rescale="none"` 的分值尺度不同；`min_pick_score` 只在 `rank`
   下保持原语义。跨 `mode` / `rescale` / `min_group_size` 的数字**不得直接比较**，须声明四元组
   （`mode, rescale, min_group_size, composite_demean`）。
5. **诊断不改档**：`S4` 只产出对照与结论，**不**据其调整出厂权重 / 闸门（改档须另立里程碑）。

---

## 10. 不做（本里程碑边界）

- 不做因子值的**行业内标准化替代**（现状是「对 `[0,1]` 因子分中性化」，不是重造打分公式）。
- 不做**行业权重约束优化**（只做候选数上限，不做组合优化器）。
- 不做 size/value 风格列的**自动 join**（`daily_basic_pit` 接入留给后续；`style` 只吃帧内已有列）。
- 不改每日推荐主路径的 `picks`。
