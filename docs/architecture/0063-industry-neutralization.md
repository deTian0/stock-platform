# 0063 — 行业中性化与风格暴露约束（`S4`）

- **状态**：Accepted
- **日期**：2026-10-10
- **里程碑**：`S4`（目标 tag `v4.1.3`，路线图 §3.3）
- **相关**：ADR [`0060`](0060-strategy-ab-full-engine.md)（`S1` 同源引擎 A/B）·
  ADR [`0061`](0061-factor-library-admission.md)（`S2` 因子库）·
  ADR [`0062`](0062-gate-parameter-sensitivity.md)（`S3` 闸门敏感性）·
  契约 [`docs/contracts/industry-neutralization.md`](../contracts/industry-neutralization.md) ·
  实测 [`docs/ops/neutralization-benchmark.md`](../ops/neutralization-benchmark.md)
- **承接的上游约定**：`a-stock-engine/src/factor_engine.py` —— `_zscore()`（**行业分组 Z-Score**，组内 mean/std、`clip(lower=0.001)`、截断 ±3）与综合分的 `raw − groupby("sector").mean()`

---

## 背景

`lvrev` 打分（`lvrev.factor_scores` / `score_lvrev`）对全截面做**全局**百分位排名后加权。
这意味着：

1. **行业倾斜不可避免**：若某日某行业的低波 / 反转特征系统性更强，排名前列会被该行业**整片占据**，
   组合拿到的是一张行业下注，而非因子暴露。
2. **平台完全没有行业维度**：`prepare_book_frame` 只 build 价量特征，不 join 任何分类；回测 / A/B 无处
   表达「行业中性」。
3. **引擎已有该约定但平台未承接**：`a-stock-engine` 早在 `factor_engine` 里做了行业分组 z-score + 综合分
   行业去均值，平台侧是**能力缺口**。

路线图 §3.3 的 `S4` 验收标准即：*「打分前做行业中性化与风格暴露约束；回测对照有中性化前后差异」*。

---

## 决策

1. **新增单点模块 `research.neutralization`**，把「行业中性化 + 风格残差化」做成纯函数：
   - `NeutralizeParams`（frozen dataclass）：`industry_col / mode(demean|zscore) / clip / min_group_size /
     rescale(rank|none) / composite_demean / style / style_clip`；
   - `industry_neutralize_series` / `neutralize_factor_scores` / `residualize` / `resolve_groups` /
     `attach_industry` / `industry_exposure`。
   - 语义**对齐引擎**：分组去均值 / 组内 z + 截断；差异只在**承载面** —— 引擎 z 原始因子值，平台作用在
     `[0,1]` 因子分上（因为平台的因子分本就是分位），且用 `rescale="rank"` 把尺度还原回 `[0,1]`，
     使下游 `min_pick_score` 语义不变。
2. **`score_lvrev` 增 `neutralize` 参数，默认 `None`**：默认路径逐位不变（三条调用路径等价性由测试锁定）。
3. **行业数据只读接入**：`EngineSqliteProvider` 侧已有只读边界，新增 `backtest_cli.load_engine_industry()`
   读 `fundamentals(code, industry)`；缺表 **`KeyError` fail-closed**（空表会静默关掉中性化）。
   `code` 两侧经 `portfolio.norm_code` 归一（`daily_price` 带后缀、`fundamentals` 裸 6 位）。
   provider **不加**业务方法，join 由 research 层 `attach_industry` 完成 —— 保持 providers 只做 I/O。
4. **A/B 复用 `S1` 契约**：`compare_neutralization_ab` 两臂跑**同一** `replay_book`，
   `delta` / `review` / `sameDefinition` **直接 import `strategy_ab` 的实现**，不复制。
5. **暴露约束落在 provider**：`max_per_industry` 在 `max_picks_per_day` 之前按行业 `head(k)` 并重新排序 ——
   改「构成」不改「排序规则」。
6. **不做自动风格列 join**：`style` 只吃帧内已有列（实测用 `vol20`）。size / value 需 `daily_basic_pit`，
   留作后续里程碑。

---

## 后果

**正面**

- 能力缺口补齐：行业中性化 + 风格约束成为**可表达、可对照**的一等公民；默认关闭，零回归风险。
- 差异可归因：两臂同帧同循环 ⇒ `delta` 只能来自处理项；`sameDefinition` 身份块把这一点变成断言。
- 与 `S1`/`S3` 形成一致的「单点 + 默认关 + 同引擎 A/B + 契约/ADR/实测」四件套。

**代价 / 风险**

- **尺度语义**：中性化后分值移出 `[0,1]`；靠 `rescale="rank"` 还原。选 `none` 会改变 `min_pick_score` 含义 ——
  已写入契约「不可横比」铁律。
- **小组退化**：`min_group_size` 以下的行业保持原值（不中性化）。这会让「小行业」仍带倾斜；参数可调，
  但**任何调整都改变口径**。
- **实测结果不是「单调改善」**：真机 A/B 显示中性化提升收益与夏普、但**加大**了回撤、降低胜率、并**提高**
  了组合的行业集中度（HHI 0.0225 → 0.0302）。即「中性化 ≠ 更分散」，只做对照、**不据此改档**。
- **暴露画像口径**：`exposure` 按「该臂实际持有过的**全部**码」等权统计，是**持仓集合**画像，不是
  逐日权重加权暴露；两者不同，已在契约写明用途（快速看构成，不做风险归因）。

---

## 备选方案

| 方案 | 为何不选 |
|------|----------|
| 在 `prepare_book_frame` 里直接改因子值 | 会把「中性化」焊进特征层，无法默认关闭，也破坏 `X4` 单点语义 |
| 在 provider 内复制一份评分逻辑做中性化 | 正是 `C` 域警告的重复实现；且两套评分迟早分叉 |
| 只做「组合层面行业权重上限」而不做打分中性化 | 满足不了「**打分前**做行业中性化」的验收措辞；且行业上限已在 `max_per_industry` 覆盖 |
| 用 `factor_engine._zscore` 的原始值口径（z 原始因子） | 平台因子分是分位不是原始值；直接套会让 `min_pick_score` 失去基准，需重建阈值体系 |
| 引入组合优化器（行业/风格约束求解） | 越出 `S4` 边界（本里程碑只做候选上限），且显著增加实现与验证成本 |
