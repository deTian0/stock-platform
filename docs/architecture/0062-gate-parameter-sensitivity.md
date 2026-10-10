# ADR 0062：闸门参数敏感性扫描与稳健区间判定

- 状态：Accepted
- 日期：2026-10-10
- 里程碑：`S3`（`v4.1.2`；[路线图](../plans/trading-system-roadmap.md) §3.3）

## 背景

入场闸门 `apply_entry_gates` 的常量（`reversal_q=0.30`、距均线带宽 `0.93`、
`vol20 > 中位数` 过滤）自 `a-stock-engine lvrev_scorer` 移植以来一直是**函数体里的字面量**。
`S1`（ADR [0060](0060-strategy-ab-full-engine.md)）让闸门**可表达**（`StrategyConfig.gates`），
`S2`（ADR [0061](0061-factor-library-admission.md)）给因子加了准入闸门 —— 但两者都**没有**回答
路线图 `S3` 的问题：

> 「`apply_entry_gates` 关键阈值做敏感性扫描；产出稳健区间结论，避免过拟合单点。」

一个孤峰最优（只有某个精确取值好、邻域立刻劣化）是曲线拟合的典型特征；一片平滑高原才是
"edge 是结构性的" 该有的样子。要判断落在哪种情形，需要（a）**能把常量当旋钮动**，且
（b）**扫描本身就是单点定义** —— 否则每个脚本各扫各的，网格、容差、判据全不同，无法审。

## 决策

1. **闸门常量单点化**：`gates.EntryGateParams`（frozen dataclass）收拢
   `reversal_q` / `ma20_band` / `ma60_band` / `vol_filter`，默认值 = 原硬编码常量**逐字**。
   `apply_entry_gates(df, reversal_q=None, *, params=None)` —— 显式 `reversal_q` 覆盖
   `params.reversal_q`；两者都缺 → `0.30`。`apply_entry_gates(df)` 与
   `apply_entry_gates(df, reversal_q=0.30)` 与 `apply_entry_gates(df, params=EntryGateParams())`
   **逐位相同**（`tests/test_gates.py` 的 reference 循环等价性测试为证）。
2. **同一 provider**：`book_replay.screener_entry_provider` 增 `gate_params` 参数，
   扫描仍从**这唯一** provider 入场 —— 不复制一份闸门。
3. **扫描内核单点**：新增 `research.sensitivity`：
   - `sweep_entry_gate(feats, *, knob, values, ...)` —— 单旋钮网格扫描，每点经
     `book_replay.replay_book`（`X4` 单循环）跑完整回放；
   - `summarize_sweep(points, *, objective, direction, tolerance, min_plateau)` —— **纯函数**，
     输出 `robust / fragile / flat / insufficient` 四类判定 + 稳健区间 + 稳定性 + 单调性；
   - `build_sensitivity_report(feats, ...)` —— 多旋钮汇总，`overall` 只要有一个 `fragile` 即 `fragile`。
4. **稳健区间语义**：某点在容差带内 ⟺ `sign·(obj − best) ≥ −tolerance × |best|`；
   `robustRange` 是**包含最优点且连续**的一段网格值；连续点数 `< min_plateau(=2)` → `fragile`。
   目标方向由 `OBJECTIVE_DIRECTION` 登记（`max_drawdown → min`），未登记默认 `max`。
5. **特征帧只建一次**：`feats` 由调用方（CLI / 端点）经 `prepare_book_frame` 建好后跨点复用，
   所以两点之间**只差旋钮**，净值曲线无需二次归一。
6. **默认路径不动**：本里程碑不修改出厂闸门值（`reversal_q=0.30` 等）；`EntryGateParams()` 即 B1 基线。
7. **不做**：参数优化器 / 自动选优 / 自动改档；把扫描结论自动写回策略配置；行业中性化（`S4`）。

## 后果

- 路线图 `S3` 的「产出稳健区间结论」从人工观感变成**可复现产物**：真机 `market.db`
  三旋钮 × 5 点网格实测，每个旋钮给出 `verdict` + `robustRange` + `stability` + `monotonic`，
  并据 `overall` 给出总判。详见 [`docs/ops/gate-sensitivity-benchmark.md`](../ops/gate-sensitivity-benchmark.md)。
- 新增 CLI `stock-platform-strategy-sensitivity` 与 HTTP `POST /api/research/strategy/sensitivity`；
  Workbench `#sensitivity` 面板同屏展示「判定表 + 逐点指标表 + 原始 JSON」。
- 契约 [`docs/contracts/gate-sensitivity.md`](../contracts/gate-sensitivity.md)。
- 已知遗留：本里程碑只**诊断**，不据此改动任何出厂参数 —— 「按稳健区间调档」属后续决策，
  且需与 `S4` 中性化结果合并考量。`fragile` 也不等于"必须改"，只表示"这个最优值不可信"。
