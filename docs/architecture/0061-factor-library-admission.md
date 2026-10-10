# ADR 0061：因子库扩展与 IC/ICIR 正交准入

- 状态：Accepted
- 日期：2026-10-10
- 里程碑：`S2`（`v4.1.1`；[路线图](../plans/trading-system-roadmap.md) §3.3）

## 背景

lvrev 组合长期只真正加权**两个**因子（`low_vol` 0.5 + `reversal` 0.5）。任何「加因子 /
调权重」的想法都缺两样东西：

1. **没有因子定义的单点**：新因子散落在临时脚本里，口径各异，无法复用、无法审。
2. **没有准入闸门**：一个因子"有没有用"全凭观感 —— 没有 IC / ICIR 检验，也没有
   「与已有因子是否重复」的正交性检查，更没有「不达标就不启用」的硬约束。

`S1`（ADR [0060](0060-strategy-ab-full-engine.md)）之后，A/B 已能在**同一台引擎**上跑；
因子层面的「谁能进、谁不能进」因此需要一个**可复现的准入契约**，而不是又一次人工拍板。

## 决策

1. **因子库单点**：新增 `research.factors`，以 `FACTOR_LIBRARY`（`name -> FactorSpec`）为
   唯一注册表。`FactorSpec` 声明 `direction`（因子→未来收益的**意图符号**）；
   `compute` 是**纯函数**（无网络 / 无 DB / 无副作用）。
2. **基线 + 三个新增正交候选**：保留 `low_vol` / `reversal` 作基线；
   新增 `long_reversal`（6 个月反转，`-(close.shift(20)/close.shift(120)-1)`，**跳过最近一月**
   以免与 20 日反转共窗）、`max_ret`（20 日单日最大涨幅，彩票偏好，意图**负**）、
   `illiq`（Amihud 非流动性 `mean(|ret1|/amount)×1e9`，意图**正**）。
3. **IC/ICIR 准入闸门**：`factor_ic.admit_factor` 四项检查（`n_dates≥20`、`|IC|≥0.02`、
   `|ICIR|≥0.15`、**符号一致**），**全过才算启用**；失败项写中文 `reasons` 自解释。
   阈值集中在 `DEFAULT_ADMISSION`，可被调用方覆盖。
4. **正交性硬约束**：`factor_ic.select_enabled`（纯函数、贪心）按「在位者优先、新因子按
   `|ICIR|` 降序」遍历，与任一**已启用**因子 `|Spearman ρ| ≥ 0.70`（`DEFAULT_MAX_CORR`）者
   标为 **冗余** 而非启用。
5. **PIT 特征复用 X4/B1 单点**：`build_feature_frame` 薄封装 `backtest.compute_features`
   （复权与 PIT 单点），仅 `keep_extra=("vol","amount")`；`compute_features` 的 `keep_extra`
   默认空 → **既有调用点逐位不变**。
6. **scipy-free**：相关矩阵用 `frame.rank().corr()`（Spearman == 秩上的 Pearson），
   避免引入 `scipy.stats`。
7. **默认不改主路径**：库内新因子在 lvrev 中权重默认 `0`（`W_S2` 仅作接入演示）；
   `W_DEFAULT`（`vol=0.5, rev=0.5`）**逐位不变**。
8. **不做**：参数优化器 / 自动选优；把新因子直接塞进 picks 主路径；行业中性化（`S4`）。

## 后果

- 「在 lvrev 之外新增 ≥2 个正交因子，每个过 IC/ICIR，不达标不启用」从口号变成**可复现的
  报告产物**：真机 `market.db`（全周期 / `horizon=20` / 324 个采样截面）实测
  `long_reversal`（IC +0.033 / ICIR +0.198）与 `illiq`（IC +0.077 / ICIR +0.798）**启用**；
  `max_ret`（IC −0.094 / ICIR −0.572）虽过 IC/ICIR，但与 `low_vol` 相关 **+0.876** → **冗余不启用**。
  详见 [`docs/ops/factor-ic-benchmark.md`](../ops/factor-ic-benchmark.md)。
- 新增 CLI `stock-platform-factor-ic` 与 HTTP `POST /api/research/factor/admission`；
  Workbench `#factor-library` 面板同屏展示判定表 + 启用/冗余/否决 + 相关矩阵。
- 契约 [`docs/contracts/factor-library.md`](../contracts/factor-library.md)。
- 已知遗留（本 ADR 外）：新因子**权重仍为 0** —— 「启用」只表示"有资格进组合"，
  真正的加权属后续里程碑（结合 `S3` 敏感性 / `S4` 中性化）。
